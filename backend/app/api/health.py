from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.benchmark import BenchmarkRun
from app.models.cluster_node import ClusterNode

router = APIRouter()
settings = get_settings()

_started_at = datetime.utcnow()


@router.get("/health", tags=["System"])
def health_check():
    return {
        "status": "ok",
        "service": "ScaleLab AI Backend",
        "version": "1.0.0",
        "ai_provider": settings.ai_provider,
        "uptime_seconds": round((datetime.utcnow() - _started_at).total_seconds(), 1),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/api/reliability", tags=["System"])
def reliability_metrics(db: Session = Depends(get_db)):
    """
    Real-time reliability metrics derived from actual benchmark run history
    and cluster node state — no synthetic values.
    """
    runs = db.query(BenchmarkRun).all()
    total = len(runs)

    completed = [r for r in runs if r.status == "completed"]
    failed = [r for r in runs if r.status == "failed"]
    pending = [r for r in runs if r.status in ("pending", "running")]

    success_rate = round(len(completed) / total * 100, 2) if total else 0.0
    failure_rate = round(len(failed) / total * 100, 2) if total else 0.0

    # Average benchmark duration for completed runs (wall clock: completed_at - created_at)
    durations = [
        (r.completed_at - r.created_at).total_seconds()
        for r in completed
        if r.completed_at and r.created_at
    ]
    avg_duration_s = round(sum(durations) / len(durations), 3) if durations else None

    # Average speedup + efficiency
    speedups = [r.speedup for r in completed if r.speedup is not None]
    efficiencies = [r.efficiency for r in completed if r.efficiency is not None]
    avg_speedup = round(sum(speedups) / len(speedups), 4) if speedups else None
    avg_efficiency = round(sum(efficiencies) / len(efficiencies), 2) if efficiencies else None

    # Runs with AI analysis
    analyzed = [r for r in completed if r.ai_analysis]
    analysis_coverage = round(len(analyzed) / len(completed) * 100, 1) if completed else 0.0

    # Cluster availability
    nodes = db.query(ClusterNode).all()
    online_nodes = [n for n in nodes if n.status == "online"]
    cluster_availability = (
        round(len(online_nodes) / len(nodes) * 100, 1) if nodes else 0.0
    )

    # Workload breakdown
    from collections import Counter
    workload_counts = Counter(r.workload_type for r in runs)

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "uptime_seconds": round((datetime.utcnow() - _started_at).total_seconds(), 1),
        "benchmark_runs": {
            "total": total,
            "completed": len(completed),
            "failed": len(failed),
            "in_flight": len(pending),
            "success_rate_pct": success_rate,
            "failure_rate_pct": failure_rate,
            "by_workload": dict(workload_counts),
        },
        "performance": {
            "avg_duration_s": avg_duration_s,
            "avg_speedup": avg_speedup,
            "avg_efficiency_pct": avg_efficiency,
            "analysis_coverage_pct": analysis_coverage,
        },
        "cluster": {
            "total_nodes": len(nodes),
            "online_nodes": len(online_nodes),
            "availability_pct": cluster_availability,
        },
    }
