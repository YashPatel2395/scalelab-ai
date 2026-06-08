"""
Custom Workloads API
────────────────────
Endpoints for uploading, validating, and executing user-provided Python
workload files.

Execution model
───────────────
POST /{id}/run creates a BenchmarkRun record (status=pending) and returns
immediately (202 Accepted).  A background thread calls the subprocess harness,
updates all timing/metric fields, and sets status=completed or failed.
Poll GET /api/benchmarks/{run_id} until the run reaches a terminal state.
This means custom workload runs appear in Benchmark History, Dashboard stats,
Analytics, Research Mode, and Experiments — exactly like built-in workloads.

Security notice
───────────────
Custom workloads run in a subprocess on the same machine as the API server.
AST validation blocks common dangerous patterns but is NOT a full sandbox.
Only run workloads from sources you trust.
See docs/SECURITY_WARNING.md for the complete threat model.
"""

import logging
import threading
import traceback
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

_dbg = logging.getLogger(__name__)

from app.database import get_db
from app.models.benchmark import BenchmarkRun
from app.observability.sampler import ResourceSampler
from app.schemas.benchmark import BenchmarkRunResponse
from app.schemas.custom_workload import (
    CustomWorkloadResponse,
    CustomWorkloadRunRequest,
)
from app.services.benchmark_service import BenchmarkService
from app.services.custom_workload_service import CustomWorkloadService

router = APIRouter(prefix="/api/custom-workloads", tags=["Custom Workloads"])

_MAX_FILE_SIZE_BYTES = 128 * 1024  # 128 KB — plenty for a workload function


# ── Background execution ───────────────────────────────────────────────────────

def _run_custom_workload_in_background(
    bench_run_id: str,
    custom_workload_id: str,
    input_size: int,
    worker_count: int,
    iterations: int,
    timeout_seconds: int,
    enable_profiling: bool,
    db_factory,
) -> None:
    """
    Executed in a daemon thread with its own DB session.
    Calls the custom_runner.py subprocess, persists all metrics into the
    BenchmarkRun record, and transitions status to completed/failed.
    """
    _dbg.info(
        "[PROFILING_DEBUG] bg_thread START bench_run_id=%s workload_id=%s enable_profiling=%s",
        bench_run_id, custom_workload_id, enable_profiling,
    )
    db = db_factory()
    try:
        run = db.query(BenchmarkRun).filter(BenchmarkRun.id == bench_run_id).first()
        if not run:
            return

        run.status = "running"
        db.commit()

        svc = CustomWorkloadService(db)
        record = svc.get(custom_workload_id)

        sampler = ResourceSampler(run_id=bench_run_id, interval=0.5)
        result: dict = {}
        try:
            sampler.start()
            result = svc.run(
                workload_id=custom_workload_id,
                input_size=input_size,
                worker_count=worker_count,
                iterations=iterations,
                timeout_seconds=timeout_seconds,
                enable_profiling=enable_profiling,
            )
        except Exception as exc:
            result = {
                "success": False,
                "error": f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}",
            }
        finally:
            sampler.stop()

        obs_summary = sampler.get_summary()
        obs_dict = obs_summary.to_dict()

        # Store custom workload provenance in observability_data
        obs_dict["custom_workload_id"] = custom_workload_id
        obs_dict["custom_workload_name"] = record.name if record else ""
        obs_dict["custom_workload_filename"] = record.filename if record else ""
        obs_dict["stdout"] = result.get("stdout") or ""
        obs_dict["return_value"] = result.get("return_value")

        if result.get("success"):
            run.execution_time = result.get("execution_time")
            run.sequential_time = result.get("sequential_time")
            run.speedup = result.get("speedup")
            run.efficiency = result.get("efficiency")
            run.cpu_usage = obs_summary.cpu_avg
            run.memory_usage = obs_summary.memory_avg_pct
            run.peak_memory_mb = obs_summary.memory_peak_mb

            # Normalize single-worker warm-cache artifact (same as built-in workloads)
            if worker_count == 1 and (result.get("speedup") or 0.0) > 1.1:
                run.speedup = 1.0
                run.efficiency = 100.0
                obs_dict["speedup_normalized"] = True
                obs_dict["speedup_normalization_reason"] = (
                    "Single-worker speedup was >1.1× and has been normalized to 1.0. "
                    "Root cause: baseline and parallel run share the same process and "
                    "warm memory caches, making the second call artificially faster."
                )

            run.observability_data = obs_dict
            run.status = "completed"

            # Store profiling data if the runner produced it.
            # Save run.profiling_data BEFORE SVG generation so a rendering failure
            # never silently discards the captured profiling data.
            profile_data = result.get("profiling_data")
            _dbg.info(
                "[PROFILING_DEBUG] bg_thread SAVE run_id=%s "
                "profiling_data type=%s total_calls=%s hotspots_len=%s",
                bench_run_id,
                type(profile_data).__name__,
                profile_data.get("total_calls") if isinstance(profile_data, dict) else "N/A",
                len(profile_data.get("top_hotspots", [])) if isinstance(profile_data, dict) else "N/A",
            )
            if profile_data is not None:  # profiling ran — store even if no hotspots
                run.profiling_data = profile_data
                try:
                    from app.profiling.flame_graph import generate_hotspot_svg
                    svg_title = f"{record.name if record else 'custom'} @ N={input_size}, P={worker_count}"
                    svg = generate_hotspot_svg(
                        hotspots=profile_data.get("top_hotspots", []),
                        title=svg_title,
                    )
                    run.flame_graph_svg = svg
                except Exception as prof_exc:
                    import logging
                    logging.getLogger(__name__).warning(
                        "Could not generate flame graph SVG for run %s: %s", bench_run_id, prof_exc
                    )
        else:
            run.status = "failed"
            run.error_message = result.get("error") or "Custom workload execution failed"
            run.observability_data = obs_dict

        run.completed_at = datetime.utcnow()
        _dbg.info(
            "[PROFILING_DEBUG] bg_thread PRE_COMMIT run_id=%s status=%s "
            "profiling_data_set=%s flame_graph_set=%s",
            bench_run_id, run.status,
            run.profiling_data is not None,
            run.flame_graph_svg is not None,
        )
        db.commit()
        _dbg.info("[PROFILING_DEBUG] bg_thread COMMIT_OK run_id=%s", bench_run_id)

    except Exception as exc:
        # Last-resort: mark failed so the run doesn't stay pending forever
        try:
            run = db.query(BenchmarkRun).filter(BenchmarkRun.id == bench_run_id).first()
            if run:
                run.status = "failed"
                run.error_message = f"Background thread error: {exc}"
                run.completed_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post(
    "/upload",
    response_model=CustomWorkloadResponse,
    status_code=201,
    summary="Upload a custom Python workload file",
)
async def upload_workload(
    name: str = Form(..., description="Human-readable workload name"),
    file: UploadFile = File(..., description="Python file with run(input_size, worker_count)"),
    db: Session = Depends(get_db),
):
    """
    Upload a Python file that exposes:

        def run(input_size: int, worker_count: int) -> dict:
            ...

    ScaleLab will:
    1. Validate the file with AST analysis (syntax, signature, blocked imports).
    2. Store it server-side.
    3. Execute it asynchronously when you POST to /{id}/run.

    **Security notice:** Custom workloads run as the server process user.
    Do not upload untrusted code. See /docs for the security model.
    """
    if not file.filename or not file.filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="Only .py files are accepted.")

    raw = await file.read()
    if len(raw) > _MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(raw)} bytes). Maximum is {_MAX_FILE_SIZE_BYTES} bytes.",
        )

    try:
        source_code = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be valid UTF-8 text.")

    svc = CustomWorkloadService(db)
    try:
        record = svc.create(
            name=name,
            filename=file.filename,
            source_code=source_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return record


@router.get(
    "",
    response_model=list[CustomWorkloadResponse],
    summary="List all uploaded custom workloads",
)
def list_workloads(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return CustomWorkloadService(db).list(limit=limit, offset=offset)


@router.get(
    "/{workload_id}",
    response_model=CustomWorkloadResponse,
    summary="Get a single custom workload",
)
def get_workload(workload_id: str, db: Session = Depends(get_db)):
    record = CustomWorkloadService(db).get(workload_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Custom workload '{workload_id}' not found")
    return record


@router.post(
    "/{workload_id}/run",
    response_model=BenchmarkRunResponse,
    status_code=202,
    summary="Execute a custom workload benchmark",
)
def run_workload(
    workload_id: str,
    payload: CustomWorkloadRunRequest,
    db: Session = Depends(get_db),
):
    """
    Submit a custom workload benchmark run. Returns immediately with status='pending'.
    Execution happens asynchronously — poll GET /api/benchmarks/{id} for results.

    The completed run will appear in Benchmark History, Dashboard stats, Analytics,
    Research Mode, and Experiments alongside built-in workload runs.
    """
    svc = CustomWorkloadService(db)
    record = svc.get(workload_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Custom workload '{workload_id}' not found")
    if record.validation_status != "passed":
        raise HTTPException(
            status_code=422,
            detail=(
                f"Workload '{workload_id}' did not pass validation "
                f"(status={record.validation_status}). Fix validation errors before running."
            ),
        )

    bench_svc = BenchmarkService(db)
    run = bench_svc.create_for_custom_workload(
        custom_workload_id=workload_id,
        input_size=payload.input_size,
        worker_count=payload.worker_count,
        iterations=payload.iterations,
        workload_name=record.name,
    )

    from app.database import SessionLocal

    t = threading.Thread(
        target=_run_custom_workload_in_background,
        args=(
            run.id,
            workload_id,
            payload.input_size,
            payload.worker_count,
            payload.iterations,
            payload.timeout_seconds,
            payload.enable_profiling,
            SessionLocal,
        ),
        daemon=True,
        name=f"custom-workload-{run.id[:8]}",
    )
    t.start()

    db.refresh(run)
    return run


@router.delete(
    "/{workload_id}",
    status_code=204,
    summary="Delete a custom workload",
)
def delete_workload(workload_id: str, db: Session = Depends(get_db)):
    deleted = CustomWorkloadService(db).delete(workload_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Custom workload '{workload_id}' not found")
