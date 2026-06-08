from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# ── Quality score thresholds ───────────────────────────────────────────────────
# Sequential runtime below these thresholds means process-fork overhead or cache
# effects dominate the measurement, making speedup figures unreliable.
_THRESHOLD_RELIABLE_S = 0.500   # ≥ 500 ms  → Reliable
_THRESHOLD_MARGINAL_S = 0.050   # ≥  50 ms  → Marginal  (< 500 ms)
                                 # <  50 ms  → Invalid


@dataclass
class WorkloadResult:
    """All measurable outcomes from a single workload execution."""

    workload_type: str
    input_size: int
    worker_count: int
    iterations: int

    # Timing (seconds, microsecond precision stored as float)
    execution_time: float = 0.0      # parallel wall-clock time
    sequential_time: float = 0.0     # single-worker baseline

    # Derived
    speedup: float = 0.0
    efficiency: float = 0.0

    # Resource (% or MB)
    cpu_usage: float = 0.0
    memory_usage: float = 0.0        # system memory %
    peak_memory_mb: float = 0.0

    # Benchmark quality
    quality_score: str = "Unknown"      # "Reliable" | "Marginal" | "Invalid"
    measurement_warning: str | None = None

    # Optional extra metadata
    extra: dict = field(default_factory=dict)

    def compute_derived(self) -> None:
        """Calculate speedup, efficiency, and benchmark quality from raw timing."""
        if self.execution_time > 0 and self.sequential_time > 0:
            self.speedup = round(self.sequential_time / self.execution_time, 4)
            if self.worker_count > 0:
                self.efficiency = round(
                    (self.speedup / self.worker_count) * 100, 2
                )
        else:
            self.speedup = 1.0
            self.efficiency = 100.0

        self._compute_quality()

    def _compute_quality(self) -> None:
        """Classify measurement reliability based on sequential runtime duration."""
        seq = self.sequential_time

        if seq < _THRESHOLD_MARGINAL_S:
            self.quality_score = "Invalid"
            seq_us = seq * 1_000_000
            self.measurement_warning = (
                f"Workload too small for reliable scalability analysis. "
                f"Sequential runtime is {seq_us:.0f} µs — "
                "process-fork overhead dominates computation at this size. "
                "Increase input size until sequential runtime exceeds 500 ms."
            )
        elif seq < _THRESHOLD_RELIABLE_S:
            self.quality_score = "Marginal"
            seq_ms = seq * 1_000
            self.measurement_warning = (
                f"Sequential runtime is {seq_ms:.1f} ms — "
                "below the 500 ms reliability threshold. "
                "Speedup and efficiency figures may be skewed by process-fork "
                "overhead and CPU cache warm-up effects."
            )
        else:
            self.quality_score = "Reliable"
            self.measurement_warning = None


class BaseWorkload(ABC):
    """Contract every workload must satisfy."""

    @abstractmethod
    def run(self, input_size: int, worker_count: int, iterations: int) -> WorkloadResult:
        """Execute the workload and return a fully populated WorkloadResult."""
        ...
