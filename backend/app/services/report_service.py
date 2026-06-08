"""
ReportService
──────────────
Generates a structured JSON report for a benchmark run.
Designed to be renderable as a PDF, Markdown, or JSON export.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.benchmark import BenchmarkRun
from app.services.benchmark_service import BenchmarkService


class ReportService:
    def __init__(self, db: Session):
        self.db = db
        self._benchmark_svc = BenchmarkService(db)

    def generate(self, run_id: str) -> dict:
        run: BenchmarkRun | None = self._benchmark_svc.get(run_id)
        if not run:
            raise KeyError(f"BenchmarkRun '{run_id}' not found")

        return {
            "benchmark_id": run.id,
            "workload_type": run.workload_type,
            "generated_at": datetime.utcnow().isoformat(),
            "configuration": {
                "workload_type": run.workload_type,
                "input_size": run.input_size,
                "worker_count": run.worker_count,
                "iterations": run.iterations,
                "submitted_at": run.created_at.isoformat(),
            },
            "metrics": {
                "status": run.status,
                "execution_time_s": run.execution_time,
                "sequential_time_s": run.sequential_time,
                "speedup": run.speedup,
                "efficiency_pct": run.efficiency,
                "cpu_usage_pct": run.cpu_usage,
                "memory_usage_pct": run.memory_usage,
                "peak_memory_mb": run.peak_memory_mb,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "wall_time_s": (
                    (run.completed_at - run.created_at).total_seconds()
                    if run.completed_at else None
                ),
            },
            "analysis": run.ai_analysis or {
                "note": "No AI analysis has been run for this benchmark. "
                        "POST to /api/benchmarks/{id}/analyze to generate one."
            },
            "performance_grade": self._grade(run),
            "error": run.error_message,
        }

    @staticmethod
    def _grade(run: BenchmarkRun) -> str:
        if run.status != "completed":
            return "N/A"
        eff = run.efficiency or 0.0
        if eff >= 85:
            return "A"
        if eff >= 70:
            return "B"
        if eff >= 50:
            return "C"
        if eff >= 30:
            return "D"
        return "F"
