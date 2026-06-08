"""
AIAnalysisService
──────────────────
Thin service wrapper around the AI provider factory.
Handles provider selection, serialization, and DB persistence.
"""

import logging

from sqlalchemy.orm import Session

from app.ai import get_provider
from app.ai.base import AnalysisResult
from app.config import get_settings
from app.models.benchmark import BenchmarkRun
from app.services.benchmark_service import BenchmarkService

logger = logging.getLogger(__name__)
settings = get_settings()


class AIAnalysisService:
    def __init__(self, db: Session):
        self.db = db
        self._benchmark_svc = BenchmarkService(db)
        self._provider = self._build_provider()

    def _build_provider(self):
        name = settings.ai_provider
        kwargs = {}
        if name == "openai" and settings.openai_api_key:
            kwargs["api_key"] = settings.openai_api_key
        elif name == "anthropic" and settings.anthropic_api_key:
            kwargs["api_key"] = settings.anthropic_api_key
        return get_provider(name, **kwargs)

    def analyze_run(self, run_id: str) -> dict:
        """
        Run AI analysis on a completed benchmark and persist the result.
        Returns the analysis dict.
        """
        run: BenchmarkRun | None = self._benchmark_svc.get(run_id)
        if not run:
            raise KeyError(f"BenchmarkRun '{run_id}' not found")
        if run.status != "completed":
            raise ValueError(
                f"Cannot analyze run in '{run.status}' state. Must be 'completed'."
            )

        # Build the data dict for the provider
        benchmark_data = {
            "workload_type": run.workload_type,
            "input_size": run.input_size,
            "worker_count": run.worker_count,
            "execution_time": run.execution_time,
            "sequential_time": run.sequential_time,
            "speedup": run.speedup,
            "efficiency": run.efficiency,
            "cpu_usage": run.cpu_usage,
            "memory_usage": run.memory_usage,
            "peak_memory_mb": run.peak_memory_mb,
        }

        logger.info(
            "Analyzing run %s with provider=%s", run_id, settings.ai_provider
        )
        result: AnalysisResult = self._provider.analyze(benchmark_data)
        analysis_dict = result.to_dict()

        # Persist
        self._benchmark_svc.save_analysis(run_id, analysis_dict)
        return analysis_dict
