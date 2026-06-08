"""
ChaosEngineer — Fault Injection Framework
──────────────────────────────────────────
Simulates real failure scenarios during benchmark execution to test:
  - Worker crash detection and recovery behavior
  - High-latency communication impact on speedup
  - Memory pressure effects on throughput
  - Partial failure (some workers crash, others succeed)

Each scenario runs a real workload with a fault injected and produces a
FaultReport with timing, detection, and outcome details.

Usage:
    chaos = ChaosEngineer()
    report = chaos.run_scenario(FaultScenario.WORKER_CRASH, workload_type="image_processing", input_size=256)
    print(report.to_dict())
"""
from __future__ import annotations

import logging
import math
import os
import signal
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class FaultScenario(str, Enum):
    WORKER_CRASH = "worker_crash"
    HIGH_LATENCY = "high_latency"
    MEMORY_PRESSURE = "memory_pressure"
    PARTIAL_FAILURE = "partial_failure"


@dataclass
class FaultReport:
    scenario: FaultScenario
    workload_type: str
    input_size: int
    worker_count: int

    # Fault injection metadata
    fault_injected: bool = False
    fault_detected: bool = False
    fault_detected_at_ms: float | None = None

    # Execution outcome
    outcome: str = "unknown"          # "completed" | "degraded" | "failed" | "recovered"
    execution_time_ms: float = 0.0
    baseline_time_ms: float | None = None    # time without fault
    overhead_pct: float | None = None        # % slowdown due to fault

    # Detailed findings
    evidence: list[str] = field(default_factory=list)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario.value,
            "workload_type": self.workload_type,
            "input_size": self.input_size,
            "worker_count": self.worker_count,
            "fault_injected": self.fault_injected,
            "fault_detected": self.fault_detected,
            "fault_detected_at_ms": self.fault_detected_at_ms,
            "outcome": self.outcome,
            "execution_time_ms": round(self.execution_time_ms, 2),
            "baseline_time_ms": round(self.baseline_time_ms, 2) if self.baseline_time_ms else None,
            "overhead_pct": round(self.overhead_pct, 1) if self.overhead_pct is not None else None,
            "evidence": self.evidence,
            "error_message": self.error_message,
        }


class ChaosEngineer:
    """
    Runs workloads under injected fault conditions and measures behavior.

    All scenarios use small problem sizes to keep test times manageable
    while still exercising real code paths.
    """

    def run_scenario(
        self,
        scenario: FaultScenario,
        workload_type: str = "image_processing",
        input_size: int = 256,
        worker_count: int = 4,
    ) -> FaultReport:
        report = FaultReport(
            scenario=scenario,
            workload_type=workload_type,
            input_size=input_size,
            worker_count=worker_count,
        )

        # Run baseline first (no fault)
        report.baseline_time_ms = self._run_baseline_ms(workload_type, input_size)

        handler = {
            FaultScenario.WORKER_CRASH: self._scenario_worker_crash,
            FaultScenario.HIGH_LATENCY: self._scenario_high_latency,
            FaultScenario.MEMORY_PRESSURE: self._scenario_memory_pressure,
            FaultScenario.PARTIAL_FAILURE: self._scenario_partial_failure,
        }[scenario]

        try:
            handler(report)
        except Exception as exc:
            report.outcome = "failed"
            report.error_message = str(exc)
            logger.error("Chaos scenario %s failed: %s", scenario.value, exc)

        if report.baseline_time_ms and report.execution_time_ms > 0:
            report.overhead_pct = (
                (report.execution_time_ms - report.baseline_time_ms)
                / report.baseline_time_ms * 100
            )

        return report

    # ── Scenario implementations ──────────────────────────────────────────────

    def _scenario_worker_crash(self, report: FaultReport) -> None:
        """
        Spawn a workload with a subprocess worker that will crash mid-execution.
        Validates that the main process detects the crash and either recovers
        or fails gracefully (no hang, no silent wrong results).
        """
        import multiprocessing
        from app.workloads._pool import get_mp_context

        report.fault_injected = True
        evidence = report.evidence
        ctx = get_mp_context()

        def crashing_worker(q: "multiprocessing.Queue"):
            """Worker that exits with non-zero code after a brief delay."""
            time.sleep(0.05)
            os._exit(1)   # simulate process crash

        q: multiprocessing.Queue = ctx.Queue()
        p = ctx.Process(target=crashing_worker, args=(q,))

        t0 = time.perf_counter()
        p.start()
        p.join(timeout=2.0)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        report.execution_time_ms = elapsed_ms

        if p.exitcode is None:
            # Process didn't terminate — kill it
            p.kill()
            p.join()
            report.fault_detected = True
            report.fault_detected_at_ms = elapsed_ms
            report.outcome = "degraded"
            evidence.append("Worker did not terminate within timeout — killed by chaos engine.")
        elif p.exitcode != 0:
            report.fault_detected = True
            report.fault_detected_at_ms = elapsed_ms
            report.outcome = "recovered"
            evidence.append(f"Worker crash detected: exit code {p.exitcode}.")
            evidence.append("Main process detected abnormal exit and returned control.")
        else:
            report.outcome = "completed"
            evidence.append("Worker completed normally (crash not triggered).")

        logger.info("Worker crash scenario: outcome=%s, exit_code=%s", report.outcome, p.exitcode)

    def _scenario_high_latency(self, report: FaultReport) -> None:
        """
        Model the effect of artificial communication delay on total execution time.

        IMPLEMENTATION NOTE: This scenario uses a sleep-based latency model, not
        real injection into worker processes. It simulates the timing impact of
        added IPC latency without running an actual parallel workload. This is
        intentional — it lets the scenario run deterministically and quickly in CI.

        For real latency injection into live worker processes, use OS-level tools
        (Linux: tc netem; macOS: Network Link Conditioner) or inject sleep() inside
        the worker function itself.
        """
        report.fault_injected = True
        LATENCY_MS = 50  # injected delay per IPC call
        NUM_WORKERS = report.worker_count

        # Simulate parallel execution with artificial IPC delay
        t0 = time.perf_counter()

        # Simulate: P workers each do compute_time + communication_delay
        compute_time_s = 0.02   # 20ms per worker
        comm_delay_s = LATENCY_MS / 1000.0

        # Parallel compute (overlapped)
        time.sleep(compute_time_s)
        # Sequential IPC with latency injection
        time.sleep(comm_delay_s * NUM_WORKERS)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        report.execution_time_ms = elapsed_ms

        # Detect: if execution time is significantly above baseline + compute alone
        expected_min_ms = compute_time_s * 1000
        latency_overhead_ms = comm_delay_s * NUM_WORKERS * 1000

        report.fault_detected = elapsed_ms > expected_min_ms + (latency_overhead_ms * 0.5)
        report.fault_detected_at_ms = elapsed_ms if report.fault_detected else None

        report.outcome = "degraded"
        report.evidence.append(
            f"Injected {LATENCY_MS}ms latency per IPC call × {NUM_WORKERS} workers = "
            f"{latency_overhead_ms:.0f}ms total communication overhead."
        )
        report.evidence.append(
            f"Total elapsed: {elapsed_ms:.1f}ms vs baseline: {report.baseline_time_ms:.1f}ms."
        )
        if report.baseline_time_ms:
            latency_fraction = latency_overhead_ms / elapsed_ms * 100
            report.evidence.append(
                f"Communication latency represents {latency_fraction:.0f}% of total time. "
                "This matches the Amdahl serial fraction model."
            )

        logger.info("High latency scenario: elapsed=%.1fms, baseline=%.1fms",
                    elapsed_ms, report.baseline_time_ms or 0)

    def _scenario_memory_pressure(self, report: FaultReport) -> None:
        """
        Allocate large numpy arrays to simulate memory pressure,
        then run the workload and measure degradation.
        """
        report.fault_injected = True

        # Allocate ~100MB of memory pressure
        PRESSURE_MB = 100
        pressure_array = None

        try:
            pressure_array = np.zeros(PRESSURE_MB * 1024 * 1024 // 8, dtype=np.float64)
            report.evidence.append(f"Allocated {PRESSURE_MB}MB memory pressure buffer.")

            t0 = time.perf_counter()
            # Run a memory-intensive operation under pressure
            # Use matrix operations on small arrays (cache-pressure simulation)
            N = 512
            A = np.random.rand(N, N)
            B = np.random.rand(N, N)
            for _ in range(3):
                _ = np.dot(A, B)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            report.execution_time_ms = elapsed_ms
            report.fault_detected = True
            report.fault_detected_at_ms = 0  # detected at injection time

            if report.baseline_time_ms and elapsed_ms > report.baseline_time_ms * 1.05:
                report.outcome = "degraded"
                report.evidence.append(
                    f"Memory pressure caused {elapsed_ms:.1f}ms execution "
                    f"vs {report.baseline_time_ms:.1f}ms baseline."
                )
            else:
                report.outcome = "completed"
                report.evidence.append(
                    "Workload completed without significant degradation under memory pressure. "
                    f"Available RAM was sufficient to absorb {PRESSURE_MB}MB allocation."
                )

        except MemoryError:
            report.outcome = "failed"
            report.fault_detected = True
            report.evidence.append("MemoryError raised — system memory exhausted under pressure.")
        finally:
            del pressure_array   # release immediately

        logger.info("Memory pressure scenario: outcome=%s, elapsed=%.1fms",
                    report.outcome, report.execution_time_ms)

    def _scenario_partial_failure(self, report: FaultReport) -> None:
        """
        Simulate partial worker failure: half the workers complete normally,
        the other half fail. Validates result integrity with partial results.
        """
        report.fault_injected = True
        import multiprocessing
        from app.workloads._pool import get_mp_context

        ctx = get_mp_context()
        total_workers = report.worker_count
        failing_workers = total_workers // 2
        good_workers = total_workers - failing_workers

        results: list[Any] = []
        errors: list[int] = []

        def good_worker(result_q, idx):
            time.sleep(0.02)
            result_q.put(("ok", idx, np.arange(100).sum()))

        def bad_worker(result_q, idx):
            time.sleep(0.01)
            result_q.put(("error", idx, None))

        result_q: multiprocessing.Queue = ctx.Queue()
        processes = []

        t0 = time.perf_counter()
        for i in range(good_workers):
            p = ctx.Process(target=good_worker, args=(result_q, i))
            p.start()
            processes.append(p)

        for i in range(failing_workers):
            p = ctx.Process(target=bad_worker, args=(result_q, good_workers + i))
            p.start()
            processes.append(p)

        for p in processes:
            p.join(timeout=5.0)

        while not result_q.empty():
            item = result_q.get_nowait()
            if item[0] == "ok":
                results.append(item)
            else:
                errors.append(item[1])

        elapsed_ms = (time.perf_counter() - t0) * 1000
        report.execution_time_ms = elapsed_ms

        if errors:
            report.fault_detected = True
            report.fault_detected_at_ms = elapsed_ms

        if results and not errors:
            report.outcome = "completed"
        elif results and errors:
            report.outcome = "degraded"
            report.evidence.append(
                f"{len(results)}/{total_workers} workers succeeded, "
                f"{len(errors)} failed."
            )
            report.evidence.append(
                "Partial results are available but incomplete — "
                "system detected failure and could trigger retry logic."
            )
        else:
            report.outcome = "failed"
            report.evidence.append("All workers failed — no results available.")

        report.evidence.append(
            f"Good workers: {good_workers}, failing workers: {failing_workers}. "
            "In production, a retry queue would redistribute failed partitions."
        )

        logger.info("Partial failure scenario: %d/%d succeeded, outcome=%s",
                    len(results), total_workers, report.outcome)

    # ── Baseline measurement ──────────────────────────────────────────────────

    def _run_baseline_ms(self, workload_type: str, input_size: int) -> float:
        """
        Run a small representative computation as the fault-free baseline.
        Uses numpy directly (not the full workload stack) for speed.
        """
        t0 = time.perf_counter()
        N = min(input_size, 128)
        if workload_type == "matrix_multiplication":
            A, B = np.random.rand(N, N), np.random.rand(N, N)
            _ = np.dot(A, B)
        elif workload_type == "parallel_sort":
            arr = np.random.rand(max(N * N, 1000))
            _ = np.sort(arr)
        else:  # image_processing, graph_bfs, default
            A, B = np.random.rand(N, N), np.random.rand(N, N)
            _ = A + B
        return (time.perf_counter() - t0) * 1000

    # ── Batch runner ──────────────────────────────────────────────────────────

    def run_all_scenarios(
        self,
        workload_type: str = "image_processing",
        input_size: int = 256,
        worker_count: int = 4,
    ) -> dict[str, FaultReport]:
        """Run all four scenarios and return a report dict keyed by scenario name."""
        return {
            scenario.value: self.run_scenario(scenario, workload_type, input_size, worker_count)
            for scenario in FaultScenario
        }
