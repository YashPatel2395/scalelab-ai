"""
ProfilingService
────────────────
Manages profiling execution and storage for benchmark runs.

For built-in workloads:
  Uses WorkloadProfiler (cProfile + tracemalloc) to profile the workload
  in-process. Generates SVG flame chart.

For custom workloads:
  Accepts profiling data from the custom_runner.py subprocess output.
  Generates SVG from the profile data.

Results are stored in BenchmarkRun.profiling_data (JSON) and
BenchmarkRun.flame_graph_svg (Text).
"""

from __future__ import annotations

import traceback
from typing import Any

from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models.benchmark import BenchmarkRun
from app.profiling.flame_graph import generate_hotspot_svg
from app.profiling.profiler import WorkloadProfiler

logger = get_logger(__name__)


class ProfilingService:
    def __init__(self, db: Session):
        self.db = db

    def profile_benchmark(
        self,
        run_id: str,
        top_n: int = 20,
    ) -> dict[str, Any] | None:
        """
        Profile a completed benchmark run (built-in workloads only).

        Runs cProfile on the workload with the same parameters as the original
        benchmark, stores result in the BenchmarkRun record, generates SVG.

        Returns the profiling result dict, or None if profiling failed.
        """
        run = self.db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
        if not run:
            raise KeyError(f"BenchmarkRun '{run_id}' not found")

        if run.workload_type == "custom_python":
            raise ValueError(
                "Custom Python workloads cannot be profiled via this endpoint. "
                "Enable profiling in the run request instead."
            )

        try:
            profiler = WorkloadProfiler()
            result = profiler.profile(
                workload_type=run.workload_type,
                input_size=run.input_size,
                worker_count=run.worker_count,
                iterations=1,
                top_n=top_n,
            )
            profile_dict = result.to_dict()

            svg = generate_hotspot_svg(
                hotspots=profile_dict.get("top_hotspots", []),
                title=f"{run.workload_type} @ N={run.input_size}, P={run.worker_count}",
            )

            run.profiling_data = profile_dict
            run.flame_graph_svg = svg
            self.db.commit()
            self.db.refresh(run)

            logger.info(
                "Profiled run %s: %d hotspots, peak_mem=%.1f MB",
                run_id, len(profile_dict.get("top_hotspots", [])),
                profile_dict.get("peak_memory_mb", 0)
            )
            return profile_dict

        except Exception as exc:
            logger.error("Profiling failed for run %s: %s", run_id, exc)
            raise RuntimeError(f"Profiling failed: {exc}") from exc

    def store_profile_data(
        self,
        run_id: str,
        profile_data: dict[str, Any],
        title: str | None = None,
    ) -> None:
        """
        Store pre-computed profiling data (e.g. from custom_runner.py).
        Generates SVG flame chart automatically.
        """
        run = self.db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
        if not run:
            raise KeyError(f"BenchmarkRun '{run_id}' not found")

        svg_title = title or f"{run.workload_type} profile"
        svg = generate_hotspot_svg(
            hotspots=profile_data.get("top_hotspots", []),
            title=svg_title,
        )
        run.profiling_data = profile_data
        run.flame_graph_svg = svg
        self.db.commit()

    def get_profile(self, run_id: str) -> dict[str, Any] | None:
        """Retrieve profiling data for a run (None if not profiled)."""
        run = self.db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
        if not run:
            raise KeyError(f"BenchmarkRun '{run_id}' not found")
        return run.profiling_data

    def get_flame_graph_svg(self, run_id: str) -> str | None:
        """Retrieve SVG flame chart for a run."""
        run = self.db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
        if not run:
            raise KeyError(f"BenchmarkRun '{run_id}' not found")
        return run.flame_graph_svg
