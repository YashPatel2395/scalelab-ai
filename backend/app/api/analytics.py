"""
Analytics API
─────────────
Scalability predictions, worker-count recommendations, and bottleneck
deep-dive reports backed by real benchmark history.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.benchmark import BenchmarkRun
from app.schemas.prediction import ScalabilityPredictionRequest, ScalabilityPredictionResponse
from app.schemas.recommendation import BottleneckReport, RecommendationRequest, RecommendationResponse
from app.ai.scalability_agent import predict_scalability
from app.ai.bottleneck_agent import analyze_bottleneck
from app.services.recommendation_service import RecommendationService
from app.workloads.mpi_runner import run_mpi_benchmark

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# ── Scalability prediction ─────────────────────────────────────────────────────

@router.post("/predict", response_model=ScalabilityPredictionResponse)
def predict_scaling(
    payload: ScalabilityPredictionRequest,
    db: Session = Depends(get_db),
):
    """
    Fit Amdahl / Gustafson curves to historical benchmark data and
    return predicted speedup for the requested worker counts.

    Data quality requirements for a meaningful prediction:
    - Same workload_type AND same input_size (mixing sizes invalidates the model)
    - At least 3 distinct worker counts (e.g. 1, 2, 4)
    - R² ≥ 0.3 for the fitted model

    If requirements are not met, returns model_used='insufficient_data' with
    a clear explanation instead of silently producing a low-quality prediction.
    Use the 'Generate Scaling Study' feature to collect clean data.
    """
    # Filter by BOTH workload_type AND input_size — mixing sizes produces
    # nonsensical curve fits (the core bug that caused R² = -9.35 in validation).
    runs = (
        db.query(BenchmarkRun)
        .filter(
            BenchmarkRun.workload_type == payload.workload_type,
            BenchmarkRun.input_size == payload.input_size,
            BenchmarkRun.status == "completed",
            BenchmarkRun.speedup != None,  # noqa: E711
        )
        .all()
    )

    data_points = [
        {"worker_count": r.worker_count, "speedup": r.speedup}
        for r in runs
        if r.speedup and r.speedup > 0
    ]

    # Count distinct worker counts — a valid scaling study needs coverage
    distinct_workers = len({dp["worker_count"] for dp in data_points})

    if distinct_workers < 3:
        insufficient_msg = (
            f"Insufficient scaling data for {payload.workload_type} "
            f"at input_size={payload.input_size}: "
            f"found {distinct_workers} distinct worker count(s), need at least 3. "
            "Run a Scaling Study (worker counts 1, 2, 4, 8) at this exact input size "
            "to generate valid prediction data."
        )
        return ScalabilityPredictionResponse(
            workload_type=payload.workload_type,
            input_size=payload.input_size,
            model_used="insufficient_data",
            parallel_fraction=None,
            serial_overhead=None,
            r_squared=None,
            data_points_used=distinct_workers,
            predictions=[
                {
                    "worker_count": w,
                    "predicted_speedup": float(w),  # optimistic linear
                    "predicted_efficiency": 1.0,
                    "confidence": 0.0,
                }
                for w in sorted(payload.target_worker_counts)
            ],
            theoretical_max_speedup=None,
            recommendation=insufficient_msg,
        )

    result = predict_scalability(data_points, payload.target_worker_counts)

    # If R² is low, override recommendation to explain the problem clearly
    r2 = result.get("r_squared")
    if r2 is not None and r2 < 0.3:
        result["recommendation"] = (
            f"Low fit quality (R²={r2:.2f}). This usually means the benchmarks were run "
            f"at mixed input sizes, or results are inconsistent. "
            f"Run a Scaling Study at a single input_size={payload.input_size} "
            "across worker counts 1, 2, 4, 8 for reliable predictions."
        )

    return ScalabilityPredictionResponse(
        workload_type=payload.workload_type,
        input_size=payload.input_size,
        **result,
    )


# ── Recommendation ─────────────────────────────────────────────────────────────

@router.post("/recommend", response_model=RecommendationResponse)
def recommend_workers(
    payload: RecommendationRequest,
    db: Session = Depends(get_db),
):
    """
    Recommend optimal worker count for the given workload using
    historical data and scalability law curve-fitting.
    """
    svc = RecommendationService(db)
    result = svc.recommend(
        workload_type=payload.workload_type,
        input_size=payload.input_size,
        available_workers=payload.available_workers,
    )
    return RecommendationResponse(**result)


# ── Bottleneck analysis ────────────────────────────────────────────────────────

@router.get("/bottleneck/{benchmark_id}", response_model=BottleneckReport)
def bottleneck_analysis(benchmark_id: str, db: Session = Depends(get_db)):
    """
    Deep-dive bottleneck root-cause analysis for a completed benchmark run.
    Uses resource observability data + metric heuristics.
    """
    run = db.query(BenchmarkRun).filter(BenchmarkRun.id == benchmark_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    if run.status != "completed":
        raise HTTPException(
            status_code=422,
            detail=f"Run is not completed (status={run.status}). Cannot analyze.",
        )

    obs_data = getattr(run, "observability_data", None)

    report = analyze_bottleneck(
        benchmark_id=run.id,
        workload_type=run.workload_type,
        input_size=run.input_size,
        worker_count=run.worker_count,
        execution_time=run.execution_time or 0.0,
        sequential_time=run.sequential_time or 0.0,
        speedup=run.speedup or 1.0,
        efficiency=run.efficiency or 0.0,
        cpu_usage=run.cpu_usage,
        memory_usage=run.memory_usage,
        peak_memory_mb=run.peak_memory_mb,
        observability_data=obs_data,
    )

    return BottleneckReport(**report)


# ── MPI timing ────────────────────────────────────────────────────────────────

@router.get("/mpi")
def mpi_timing(
    n_processes: int = 4,
    matrix_size: int = 512,
):
    """
    Run a real MPI matrix-multiply and return timing breakdown:
    computation / communication / synchronisation.
    Falls back to modelled estimates if mpiexec is not installed.
    """
    if n_processes < 1 or n_processes > 32:
        raise HTTPException(status_code=422, detail="n_processes must be 1–32")
    if matrix_size < 64 or matrix_size > 4096:
        raise HTTPException(status_code=422, detail="matrix_size must be 64–4096")

    result = run_mpi_benchmark(n_processes=n_processes, matrix_size=matrix_size)
    response = {
        "n_processes": result.n_processes,
        "matrix_size": result.matrix_size,
        "computation_time": result.computation_time,
        "communication_time": result.communication_time,
        "synchronization_time": result.synchronization_time,
        "total_time": result.total_time,
        "mpi_available": result.mpi_available,
        "breakdown_pct": {
            "computation": round(
                result.computation_time / max(result.total_time, 1e-9) * 100, 1
            ),
            "communication": round(
                result.communication_time / max(result.total_time, 1e-9) * 100, 1
            ),
            "synchronization": round(
                result.synchronization_time / max(result.total_time, 1e-9) * 100, 1
            ),
        },
    }
    if not result.mpi_available:
        response["estimation_note"] = (
            "mpi4py not installed or mpiexec failed. All timing values are "
            "analytically estimated (10 GB/s bandwidth model). "
            "Install mpi4py for real MPI measurements."
        )
    return response
