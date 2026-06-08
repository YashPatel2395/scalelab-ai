"""Diagnosis API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.diagnosis.engine import diagnose
from app.models.benchmark import BenchmarkRun

router = APIRouter(prefix="/api/diagnosis", tags=["Diagnosis"])


@router.get("/{run_id}")
def get_diagnosis(run_id: str, db: Session = Depends(get_db)):
    """
    Run Stage 1 algorithmic diagnosis on a completed benchmark run.
    Returns structured bottleneck classification with evidence and diagnostic strength.
    """
    run = db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"BenchmarkRun '{run_id}' not found")
    if run.status != "completed":
        raise HTTPException(
            status_code=422,
            detail=f"Run status is '{run.status}' — diagnosis requires completed run."
        )

    result = diagnose(
        workload_type=run.workload_type,
        input_size=run.input_size,
        worker_count=run.worker_count,
        execution_time=run.execution_time or 0.001,
        sequential_time=run.sequential_time or 0.001,
        speedup=run.speedup or 1.0,
        efficiency=run.efficiency or 0.0,
        cpu_usage=run.cpu_usage,
        memory_usage=run.memory_usage,
        peak_memory_mb=run.peak_memory_mb,
        observability_data=run.observability_data,
        profiling_data=run.profiling_data,
    )
    return result.to_dict()
