import threading
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.benchmark import (
    BenchmarkRunCreate,
    BenchmarkRunResponse,
    BenchmarkRunSummary,
    AIAnalysisResponse,
    ReportResponse,
)
from app.schemas.custom_workload import ScalingStudyRequest, ScalingStudyResponse
from app.services.benchmark_service import BenchmarkService
from app.services.ai_analysis_service import AIAnalysisService
from app.services.report_service import ReportService
from app.services.experiment_service import ExperimentService
from app.schemas.experiment import ExperimentCreate

router = APIRouter(prefix="/api/benchmarks", tags=["Benchmarks"])
logger = logging.getLogger(__name__)


def _run_benchmark_in_background(run_id: str, db_factory) -> None:
    """
    Executed in a daemon thread so it gets its own DB session.
    FastAPI BackgroundTasks share the request session which may close early.
    """
    db = db_factory()
    try:
        svc = BenchmarkService(db)
        svc.execute(run_id)
    finally:
        db.close()


@router.post("", response_model=BenchmarkRunResponse, status_code=202)
def run_benchmark(
    payload: BenchmarkRunCreate,
    db: Session = Depends(get_db),
):
    """
    Submit a new benchmark run. Returns immediately with status='pending'.
    Execution happens asynchronously – poll GET /api/benchmarks/{id} for results.
    """
    svc = BenchmarkService(db)
    try:
        run = svc.create(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Use a real thread so the DB session is independent
    from app.database import SessionLocal
    t = threading.Thread(
        target=_run_benchmark_in_background,
        args=(run.id, SessionLocal),
        daemon=True,
        name=f"benchmark-{run.id[:8]}",
    )
    t.start()

    db.refresh(run)
    return run


@router.get("", response_model=list[BenchmarkRunSummary])
def list_benchmarks(
    limit: int = 100,
    offset: int = 0,
    workload_type: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    """List benchmark runs with optional filtering."""
    svc = BenchmarkService(db)
    return svc.list(limit=limit, offset=offset, workload_type=workload_type, status=status)


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Aggregate statistics across all benchmark runs."""
    return BenchmarkService(db).get_summary_stats()


@router.get("/{run_id}", response_model=BenchmarkRunResponse)
def get_benchmark(run_id: str, db: Session = Depends(get_db)):
    run = BenchmarkService(db).get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Benchmark '{run_id}' not found")
    return run


@router.post("/{run_id}/analyze", response_model=AIAnalysisResponse)
def analyze_benchmark(run_id: str, db: Session = Depends(get_db)):
    """Run AI bottleneck analysis on a completed benchmark."""
    try:
        analysis = AIAnalysisService(db).analyze_run(run_id)
        return AIAnalysisResponse(benchmark_id=run_id, analysis=analysis)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/{run_id}/report", response_model=ReportResponse)
def get_report(run_id: str, db: Session = Depends(get_db)):
    """Generate a structured performance report for a benchmark run."""
    try:
        report = ReportService(db).generate(run_id)
        return report
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{run_id}", status_code=204)
def delete_benchmark(run_id: str, db: Session = Depends(get_db)):
    deleted = BenchmarkService(db).delete(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Benchmark '{run_id}' not found")


@router.post("/scaling-study", response_model=ScalingStudyResponse, status_code=202)
def create_scaling_study(
    payload: ScalingStudyRequest,
    db: Session = Depends(get_db),
):
    """
    Generate a controlled scaling study by submitting one benchmark run per
    requested worker count, all at the same input_size. Runs are grouped into
    an Experiment so results can be compared and fed into scalability prediction.

    Recommended worker_counts: [1, 2, 4, 8] — gives 4 data points for curve fitting.
    All runs are dispatched asynchronously. Poll each run_id for completion.
    After all runs complete, use POST /api/analytics/predict with the same
    workload_type and input_size to get Amdahl/Gustafson curve fits.
    """
    from app.workloads import WORKLOAD_REGISTRY

    if payload.workload_type not in WORKLOAD_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown workload '{payload.workload_type}'. "
                   f"Available: {list(WORKLOAD_REGISTRY.keys())}",
        )

    worker_counts = sorted(set(max(1, w) for w in payload.worker_counts))
    if not worker_counts:
        raise HTTPException(status_code=400, detail="worker_counts must not be empty")

    # Create experiment to group all runs
    exp_name = payload.experiment_name or (
        f"Scaling Study — {payload.workload_type} @ size={payload.input_size} "
        f"({datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC)"
    )
    exp_svc = ExperimentService(db)
    experiment = exp_svc.create(
        ExperimentCreate(
            name=exp_name,
            description=(
                f"Auto-generated scaling study: {payload.workload_type}, "
                f"input_size={payload.input_size}, "
                f"worker_counts={worker_counts}"
            ),
            workload_type=payload.workload_type,
            tags=["scaling-study", "auto-generated"],
        )
    )

    # Submit one run per worker count
    run_ids: list[str] = []
    bench_svc = BenchmarkService(db)
    from app.database import SessionLocal

    for wc in worker_counts:
        run = bench_svc.create(
            BenchmarkRunCreate(
                workload_type=payload.workload_type,
                input_size=payload.input_size,
                worker_count=wc,
                iterations=payload.iterations,
            )
        )
        run_ids.append(run.id)
        t = threading.Thread(
            target=_run_benchmark_in_background,
            args=(run.id, SessionLocal),
            daemon=True,
            name=f"scaling-study-{run.id[:8]}",
        )
        t.start()

    # Add all runs to the experiment
    exp_svc.add_runs(experiment.id, run_ids)

    return ScalingStudyResponse(
        experiment_id=experiment.id,
        experiment_name=exp_name,
        run_ids=run_ids,
        workload_type=payload.workload_type,
        input_size=payload.input_size,
        worker_counts=worker_counts,
        message=(
            f"Submitted {len(run_ids)} benchmark runs. "
            "Poll each run_id until status='completed', then use "
            "POST /api/analytics/predict to fit scalability curves."
        ),
    )
