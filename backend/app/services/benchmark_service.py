"""
BenchmarkService
─────────────────
Orchestrates the full lifecycle of a benchmark run:
  1. Create a 'pending' record in the database
  2. Transition to 'running'
  3. Dispatch to the appropriate workload implementation
  4. Persist results and transition to 'completed' or 'failed'
"""

import threading
import traceback
from datetime import datetime

from sqlalchemy.orm import Session

from app.logging_config import BenchmarkTimer, get_logger
from app.models.benchmark import BenchmarkRun
from app.observability.sampler import ResourceSampler
from app.schemas.benchmark import BenchmarkRunCreate
from app.workloads import WORKLOAD_REGISTRY

logger = get_logger(__name__)

# Limit concurrent benchmark executions to prevent OOM under rapid POST floods.
# A run that arrives when the semaphore is exhausted fails immediately with a
# clear error rather than spawning unbounded worker processes.
_MAX_CONCURRENT_EXECUTIONS = 4
_EXECUTION_SEMAPHORE = threading.Semaphore(_MAX_CONCURRENT_EXECUTIONS)


class BenchmarkService:
    def __init__(self, db: Session):
        self.db = db

    # ── Create ────────────────────────────────────────────────────────────────

    def create(self, payload: BenchmarkRunCreate) -> BenchmarkRun:
        """Persist a new benchmark run in 'pending' state."""
        if payload.workload_type not in WORKLOAD_REGISTRY:
            raise ValueError(
                f"Unknown workload '{payload.workload_type}'. "
                f"Available: {list(WORKLOAD_REGISTRY.keys())}"
            )

        run = BenchmarkRun(
            workload_type=payload.workload_type,
            input_size=payload.input_size,
            worker_count=payload.worker_count,
            iterations=payload.iterations,
            status="pending",
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        logger.info("Created benchmark run %s (%s)", run.id, run.workload_type)
        return run

    # ── Execute ───────────────────────────────────────────────────────────────

    def execute(self, run_id: str) -> BenchmarkRun:
        """
        Execute the workload for an existing run.
        Intended to be called from a background thread – updates DB in-place.
        """
        acquired = _EXECUTION_SEMAPHORE.acquire(blocking=False)
        if not acquired:
            run = self._get_or_raise(run_id)
            run.status = "failed"
            run.error_message = (
                f"Server at capacity: {_MAX_CONCURRENT_EXECUTIONS} benchmarks already running. "
                "Retry after a current run completes."
            )
            run.completed_at = datetime.utcnow()
            self.db.commit()
            logger.warning("Run %s rejected: execution semaphore exhausted", run_id)
            return run

        # Semaphore acquired. All paths from here MUST release it — including
        # exceptions raised before the inner try (e.g., _get_or_raise, db.commit).
        try:
            run = self._get_or_raise(run_id)
            run.status = "running"
            self.db.commit()

            sampler = ResourceSampler(run_id=run_id, interval=0.5)
            try:
                workload_cls = WORKLOAD_REGISTRY[run.workload_type]
                workload = workload_cls()
                sampler.start()
                with BenchmarkTimer(run_id, run.workload_type):
                    result = workload.run(
                        input_size=run.input_size,
                        worker_count=run.worker_count,
                        iterations=run.iterations,
                    )
                sampler.stop()
                obs_summary = sampler.get_summary()

                run.execution_time = result.execution_time
                run.sequential_time = result.sequential_time
                run.speedup = result.speedup
                run.efficiency = result.efficiency
                run.cpu_usage = result.cpu_usage or obs_summary.cpu_avg
                run.memory_usage = result.memory_usage or obs_summary.memory_avg_pct
                run.peak_memory_mb = result.peak_memory_mb or obs_summary.memory_peak_mb
                run.quality_score = result.quality_score
                run.measurement_warning = result.measurement_warning

                obs_dict = obs_summary.to_dict()

                # ── Normalize single-worker warm-cache artifact ────────────────
                # When worker_count == 1 the baseline and the "parallel" run
                # execute back-to-back in the same process.  The second call
                # benefits from warm CPU caches / BLAS buffers and can report
                # speedup >> 1.0, which is physically meaningless.
                # We clamp to 1.0 and record the reason so the data is honest.
                if run.worker_count == 1 and (result.speedup or 0.0) > 1.1:
                    run.speedup = 1.0
                    run.efficiency = 100.0
                    obs_dict["speedup_normalized"] = True
                    obs_dict["speedup_normalization_reason"] = (
                        "Single-worker speedup was >1.1× and has been normalized to 1.0. "
                        "Root cause: baseline and parallel run share the same process and "
                        "warm memory caches, making the second call artificially faster. "
                        "Option A fix (cold-subprocess baseline) is tracked as future work."
                    )

                run.observability_data = obs_dict
                run.status = "completed"
                run.completed_at = datetime.utcnow()

                logger.info(
                    "Run %s completed: %.3fs parallel, %.3fx speedup, %.1f%% efficiency",
                    run.id,
                    run.execution_time,
                    run.speedup,
                    run.efficiency,
                )

            except Exception as exc:
                sampler.stop()
                run.status = "failed"
                run.error_message = f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"
                run.completed_at = datetime.utcnow()
                logger.error("Run %s failed: %s", run.id, exc, exc_info=True)

            self.db.commit()
            self.db.refresh(run)
            return run

        finally:
            _EXECUTION_SEMAPHORE.release()

    def create_for_custom_workload(
        self,
        custom_workload_id: str,
        input_size: int,
        worker_count: int,
        iterations: int = 1,
        workload_name: str | None = None,
    ) -> BenchmarkRun:
        """Persist a pending BenchmarkRun for a custom Python workload."""
        run = BenchmarkRun(
            workload_type="custom_python",
            workload_name=workload_name,
            input_size=input_size,
            worker_count=worker_count,
            iterations=iterations,
            status="pending",
            observability_data={"custom_workload_id": custom_workload_id},
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        logger.info(
            "Created custom benchmark run %s (custom_workload=%s)", run.id, custom_workload_id
        )
        return run

    # ── Query ─────────────────────────────────────────────────────────────────

    def list(
        self,
        limit: int = 100,
        offset: int = 0,
        workload_type: str | None = None,
        status: str | None = None,
    ) -> list[BenchmarkRun]:
        query = self.db.query(BenchmarkRun)
        if workload_type:
            query = query.filter(BenchmarkRun.workload_type == workload_type)
        if status:
            query = query.filter(BenchmarkRun.status == status)
        return (
            query.order_by(BenchmarkRun.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def get(self, run_id: str) -> BenchmarkRun | None:
        return self.db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()

    def delete(self, run_id: str) -> bool:
        run = self.get(run_id)
        if not run:
            return False
        self.db.delete(run)
        self.db.commit()
        return True

    def save_analysis(self, run_id: str, analysis_dict: dict) -> BenchmarkRun:
        run = self._get_or_raise(run_id)
        run.ai_analysis = analysis_dict
        self.db.commit()
        self.db.refresh(run)
        return run

    # ── Summary stats ─────────────────────────────────────────────────────────

    def get_summary_stats(self) -> dict:
        all_runs = self.db.query(BenchmarkRun).all()
        completed = [r for r in all_runs if r.status == "completed"]
        failed = [r for r in all_runs if r.status == "failed"]

        best_speedup = max((r.speedup or 0.0 for r in completed), default=0.0)
        avg_efficiency = (
            sum(r.efficiency or 0.0 for r in completed) / len(completed)
            if completed else 0.0
        )

        slowest = max(completed, key=lambda r: r.execution_time or 0.0, default=None)

        return {
            "total_runs": len(all_runs),
            "completed_runs": len(completed),
            "failed_runs": len(failed),
            "best_speedup": round(best_speedup, 3),
            "average_efficiency": round(avg_efficiency, 2),
            "most_expensive_workload": slowest.workload_type if slowest else None,
            "most_expensive_time": round(slowest.execution_time or 0.0, 4) if slowest else None,
        }

    # ── Private ───────────────────────────────────────────────────────────────

    def _get_or_raise(self, run_id: str) -> BenchmarkRun:
        run = self.get(run_id)
        if not run:
            raise KeyError(f"BenchmarkRun '{run_id}' not found")
        return run
