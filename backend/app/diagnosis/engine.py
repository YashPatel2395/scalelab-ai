"""
Diagnosis Engine  v2
────────────────────
Stage 1 algorithmic diagnosis — no LLM required.

Nine bottleneck classifiers. Each returns a score [0,1] and a list of
EvidenceItem(metric, value) drawn strictly from measured data.

Diagnostic Strength = primary_score - secondary_score (absolute margin, range [0,1]).
This measures the separation between the top two classifiers — not statistical confidence.
A value of 0 means two classifiers are tied; a value near 1 means unambiguous diagnosis.

Bottleneck taxonomy
───────────────────
cpu_bound               CPU utilisation > 85%  or  high efficiency at high CPU
memory_bound            Memory utilisation > 75%  or  negative scaling pattern
synchronization_bound   Amdahl serial fraction > 35%  and  low efficiency
communication_bound     Net I/O > 20 MB/s  or  IPC cost evident in serial fraction
load_imbalance          Per-core CPU variance > 25pp  or  non-monotone speedup
ipc_overhead            Workers > 4  and  speedup < 0.5 × workers  and  low CPU
worker_oversubscription Workers > logical_cpu_count (from psutil)
serialization_bottleneck custom_python workload  and  ipc_overhead indicators
io_bound                Disk I/O rate > 20 MB/s

Two outputs are emitted:
  primary   — highest-scoring classifier
  secondary — second-highest if score > 0.15 (co-bottleneck)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

try:
    import psutil
    _CPU_COUNT = psutil.cpu_count(logical=True) or os.cpu_count() or 4
except Exception:
    _CPU_COUNT = os.cpu_count() or 4


@dataclass
class EvidenceItem:
    metric: str   # e.g. "Memory Utilization"
    value: str    # e.g. "82%"

    def to_dict(self) -> dict[str, str]:
        return {"metric": self.metric, "value": self.value}


@dataclass
class BottleneckScore:
    name: str
    score: float
    evidence: list[EvidenceItem] = field(default_factory=list)


@dataclass
class DiagnosisResult:
    primary: str
    diagnostic_strength: float           # 0.0–1.0 — absolute margin between primary and secondary score
    evidence: list[EvidenceItem]
    secondary: str | None
    secondary_evidence_strength: float | None   # absolute score of secondary classifier
    all_scores: list[BottleneckScore]    # full list, sorted descending by score
    optimization_opportunities: list[str]
    expected_improvement_pct: float
    risk_assessment: str
    executive_summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_bottleneck": self.primary,
            "diagnostic_strength": round(self.diagnostic_strength, 3),
            "evidence": [e.to_dict() for e in self.evidence],
            "secondary_bottleneck": self.secondary,
            "secondary_evidence_strength": round(self.secondary_evidence_strength, 3) if self.secondary_evidence_strength is not None else None,
            "all_scores": {s.name: round(s.score, 3) for s in self.all_scores},
            "optimization_opportunities": self.optimization_opportunities,
            "expected_improvement_pct": self.expected_improvement_pct,
            "risk_assessment": self.risk_assessment,
            "executive_summary": self.executive_summary,
        }


# ── Individual classifiers ─────────────────────────────────────────────────────

def _score_cpu_bound(
    cpu_usage: float | None,
    efficiency: float,
    speedup: float,
    worker_count: int,
) -> BottleneckScore:
    score = 0.0
    evidence: list[EvidenceItem] = []

    if cpu_usage is not None:
        evidence.append(EvidenceItem("CPU Utilization", f"{cpu_usage:.1f}%"))
        if cpu_usage >= 90:
            score += 0.70
        elif cpu_usage >= 75:
            score += 0.45
        elif cpu_usage >= 55:
            score += 0.20

    evidence.append(EvidenceItem("Efficiency", f"{efficiency:.1f}%"))
    evidence.append(EvidenceItem("Speedup", f"{speedup:.2f}×"))
    evidence.append(EvidenceItem("Worker Count", str(worker_count)))

    # High efficiency AND high CPU → confirmed CPU-bound with headroom saturated
    if efficiency >= 70 and cpu_usage is not None and cpu_usage >= 60:
        score += 0.15  # confirms CPU is being used efficiently

    # CPU at ceiling (>= 90%) confirms the resource is truly saturated
    if cpu_usage is not None and cpu_usage >= 90 and efficiency >= 65:
        score += 0.15  # CPU saturation bonus: resource is genuinely limiting

    # CPU high but efficiency low → not purely cpu_bound, but cpu is involved
    if cpu_usage is not None and cpu_usage >= 80 and efficiency < 40:
        score -= 0.10  # other factor limiting efficiency

    return BottleneckScore("cpu_bound", max(0.0, min(1.0, score)), evidence)


def _score_memory_bound(
    memory_usage: float | None,
    peak_memory_mb: float | None,
    speedup: float,
    efficiency: float,
    worker_count: int,
    cpu_usage: float | None,
) -> BottleneckScore:
    score = 0.0
    evidence: list[EvidenceItem] = []

    if memory_usage is not None:
        evidence.append(EvidenceItem("Memory Utilization", f"{memory_usage:.1f}%"))
        if memory_usage >= 85:
            score += 0.70
        elif memory_usage >= 75:
            score += 0.50
        elif memory_usage >= 60:
            score += 0.25

    if peak_memory_mb is not None:
        evidence.append(EvidenceItem("Peak Memory", f"{peak_memory_mb:.0f} MB"))

    evidence.append(EvidenceItem("Efficiency", f"{efficiency:.1f}%"))
    evidence.append(EvidenceItem("Speedup", f"{speedup:.2f}×"))
    evidence.append(EvidenceItem("Worker Count", str(worker_count)))

    # Negative scaling (speedup < 1) with high memory = memory contention
    if speedup < 1.0 and memory_usage is not None and memory_usage >= 60:
        score += 0.25

    # High memory + low CPU + low efficiency = memory bandwidth saturation
    if (memory_usage is not None and memory_usage >= 70
            and cpu_usage is not None and cpu_usage < 50
            and efficiency < 50):
        score += 0.20

    return BottleneckScore("memory_bound", max(0.0, min(1.0, score)), evidence)


def _score_synchronization_bound(
    speedup: float,
    efficiency: float,
    worker_count: int,
    sequential_time: float | None,
    execution_time: float | None,
    cpu_usage: float | None,
    observability_data: dict[str, Any] | None = None,
) -> BottleneckScore:
    score = 0.0
    evidence: list[EvidenceItem] = []

    evidence.append(EvidenceItem("Worker Count", str(worker_count)))
    evidence.append(EvidenceItem("Speedup", f"{speedup:.2f}×"))
    evidence.append(EvidenceItem("Efficiency", f"{efficiency:.1f}%"))

    # Estimate serial fraction from Amdahl inversion
    serial_fraction = None
    if worker_count > 1 and speedup > 0 and speedup < worker_count:
        P = float(worker_count)
        S = float(speedup)
        denom = (1.0 / P) - 1.0
        if abs(denom) > 1e-9:
            p_par = ((1.0 / S) - 1.0) / denom
            serial_fraction = 1.0 - max(0.0, min(1.0, p_par))

    if serial_fraction is not None:
        evidence.append(EvidenceItem("Serial Fraction (Amdahl)", f"{serial_fraction:.1%}"))
        if serial_fraction >= 0.40:
            score += 0.65
        elif serial_fraction >= 0.25:
            score += 0.40
        elif serial_fraction >= 0.15:
            score += 0.20

    # Low CPU with poor efficiency → synchronization stall
    if cpu_usage is not None and cpu_usage < 35 and efficiency < 40 and worker_count > 1:
        score += 0.30
        evidence.append(EvidenceItem("CPU Utilization", f"{cpu_usage:.1f}% (low — workers stalling)"))

    # Defer to I/O classifiers when observability shows high disk or network throughput.
    # Amdahl inversion fires whenever speedup is low — but if I/O is the bottleneck,
    # the Amdahl score is a false positive, not genuine synchronization overhead.
    if observability_data:
        duration = max(observability_data.get("duration_seconds", 1) or 1, 0.01)
        disk_rate = (
            (observability_data.get("disk_read_mb", 0) or 0) +
            (observability_data.get("disk_write_mb", 0) or 0)
        ) / duration
        net_rate = (
            (observability_data.get("net_sent_mb", 0) or 0) +
            (observability_data.get("net_recv_mb", 0) or 0)
        ) / duration
        if disk_rate > 50:
            score *= 0.45  # disk I/O is the bottleneck — Amdahl serial fraction is misleading
            evidence.append(EvidenceItem("I/O Deferral", f"disk={disk_rate:.0f} MB/s suppresses sync score"))
        elif net_rate > 20:
            score *= 0.55  # network I/O is the bottleneck
            evidence.append(EvidenceItem("I/O Deferral", f"net={net_rate:.0f} MB/s suppresses sync score"))

    return BottleneckScore("synchronization_bound", max(0.0, min(1.0, score)), evidence)


def _score_communication_bound(
    observability_data: dict[str, Any] | None,
    worker_count: int,
    speedup: float,
    efficiency: float,
) -> BottleneckScore:
    score = 0.0
    evidence: list[EvidenceItem] = []

    evidence.append(EvidenceItem("Worker Count", str(worker_count)))
    evidence.append(EvidenceItem("Speedup", f"{speedup:.2f}×"))

    if observability_data:
        duration = observability_data.get("duration_seconds", 1) or 1
        net_mb = (observability_data.get("net_recv_mb", 0) + observability_data.get("net_sent_mb", 0))
        disk_mb = (observability_data.get("disk_read_mb", 0) + observability_data.get("disk_write_mb", 0))

        net_rate = net_mb / duration
        disk_rate = disk_mb / duration

        if net_rate > 50:
            score += 0.80   # strong signal — this beats Amdahl-based sync_bound
            evidence.append(EvidenceItem("Network I/O Rate", f"{net_rate:.1f} MB/s"))
        elif net_rate > 20:
            score += 0.55
            evidence.append(EvidenceItem("Network I/O Rate", f"{net_rate:.1f} MB/s"))
        elif net_rate > 5:
            score += 0.20
            evidence.append(EvidenceItem("Network I/O Rate", f"{net_rate:.1f} MB/s"))

        if disk_rate > 100:
            score += 0.20  # disk is more io_bound, small bonus here
    else:
        # Without observability, infer from Amdahl
        if worker_count >= 4 and efficiency < 30:
            score += 0.20
            evidence.append(EvidenceItem("Efficiency", f"{efficiency:.1f}% (suggests high IPC cost)"))

    return BottleneckScore("communication_bound", max(0.0, min(1.0, score)), evidence)


def _score_load_imbalance(
    observability_data: dict[str, Any] | None,
    efficiency: float,
    worker_count: int,
    speedup: float,
) -> BottleneckScore:
    score = 0.0
    evidence: list[EvidenceItem] = []

    evidence.append(EvidenceItem("Worker Count", str(worker_count)))
    evidence.append(EvidenceItem("Efficiency", f"{efficiency:.1f}%"))

    if observability_data:
        per_core = observability_data.get("cpu_per_core_avg", [])
        if per_core and len(per_core) >= 2:
            vals = [v for v in per_core if isinstance(v, (int, float))]
            if vals:
                variance = max(vals) - min(vals)
                evidence.append(EvidenceItem("CPU Core Variance", f"{variance:.1f}pp"))
                if variance >= 30:
                    score += 0.60
                elif variance >= 20:
                    score += 0.40
                elif variance >= 10:
                    score += 0.20

    # Non-monotone scaling indicator: if efficiency << theoretical at moderate workers
    if worker_count >= 4 and efficiency < 50:
        score += 0.15

    # Penalty: if CPU is uniformly high, it's NOT load imbalance
    if observability_data:
        per_core = observability_data.get("cpu_per_core_avg", [])
        if per_core:
            vals = [v for v in per_core if isinstance(v, (int, float))]
            if vals and min(vals) >= 60:
                score -= 0.20  # all cores busy, not imbalance

    return BottleneckScore("load_imbalance", max(0.0, min(1.0, score)), evidence)


def _score_ipc_overhead(
    speedup: float,
    efficiency: float,
    worker_count: int,
    cpu_usage: float | None,
    execution_time: float | None,
    sequential_time: float | None,
) -> BottleneckScore:
    score = 0.0
    evidence: list[EvidenceItem] = []

    evidence.append(EvidenceItem("Worker Count", str(worker_count)))
    evidence.append(EvidenceItem("Speedup", f"{speedup:.2f}×"))
    evidence.append(EvidenceItem("Efficiency", f"{efficiency:.1f}%"))

    # IPC overhead: many workers but speedup << workers, low CPU
    if worker_count >= 4 and speedup < 0.5 * worker_count:
        score += 0.35
    if worker_count >= 8 and speedup < 0.3 * worker_count:
        score += 0.25

    if cpu_usage is not None:
        evidence.append(EvidenceItem("CPU Utilization", f"{cpu_usage:.1f}%"))
        if cpu_usage < 40 and worker_count >= 4:
            score += 0.25  # workers not doing compute, paying IPC cost

    # Sub-linear speedup with negative scaling is a strong IPC signal
    if speedup < 1.0 and worker_count > 2:
        score += 0.25
        evidence.append(EvidenceItem("Scaling Direction", "Negative (parallel slower than sequential)"))

    return BottleneckScore("ipc_overhead", max(0.0, min(1.0, score)), evidence)


def _score_worker_oversubscription(
    worker_count: int,
    efficiency: float,
    speedup: float,
    cpu_count: int = _CPU_COUNT,
) -> BottleneckScore:
    score = 0.0
    evidence: list[EvidenceItem] = []

    evidence.append(EvidenceItem("Worker Count", str(worker_count)))
    evidence.append(EvidenceItem("Logical CPU Count", str(cpu_count)))
    evidence.append(EvidenceItem("Efficiency", f"{efficiency:.1f}%"))

    if worker_count > cpu_count:
        oversubscription_ratio = worker_count / cpu_count
        evidence.append(EvidenceItem("Oversubscription Ratio", f"{oversubscription_ratio:.1f}×"))
        if oversubscription_ratio >= 2.0:
            score += 0.65
        elif oversubscription_ratio >= 1.5:
            score += 0.45
        else:
            score += 0.25

        if efficiency < 50:
            score += 0.15

    return BottleneckScore("worker_oversubscription", max(0.0, min(1.0, score)), evidence)


def _score_serialization_bottleneck(
    workload_type: str,
    worker_count: int,
    speedup: float,
    efficiency: float,
    input_size: int,
) -> BottleneckScore:
    score = 0.0
    evidence: list[EvidenceItem] = []

    evidence.append(EvidenceItem("Workload Type", workload_type))
    evidence.append(EvidenceItem("Worker Count", str(worker_count)))
    evidence.append(EvidenceItem("Input Size", str(input_size)))
    evidence.append(EvidenceItem("Speedup", f"{speedup:.2f}×"))

    is_custom = workload_type == "custom_python"
    if is_custom:
        score += 0.20  # custom workloads use pickle by default

    # Small input + many workers → serialization dominates
    if worker_count >= 4 and input_size < 10_000:
        score += 0.25
        evidence.append(EvidenceItem("Input/Worker Ratio", f"{input_size // worker_count} items/worker"))

    # Very poor efficiency with moderate worker count
    if efficiency < 15 and worker_count >= 4:
        score += 0.25

    if speedup < 0.5 and worker_count >= 2:
        score += 0.20

    if not is_custom and worker_count < 4:
        score = 0.0  # serialization bottleneck unlikely for built-in small worker counts

    return BottleneckScore("serialization_bottleneck", max(0.0, min(1.0, score)), evidence)


def _score_io_bound(
    observability_data: dict[str, Any] | None,
    cpu_usage: float | None,
    efficiency: float,
    worker_count: int,
) -> BottleneckScore:
    score = 0.0
    evidence: list[EvidenceItem] = []

    if observability_data:
        duration = observability_data.get("duration_seconds", 1) or 1
        disk_r = observability_data.get("disk_read_mb", 0)
        disk_w = observability_data.get("disk_write_mb", 0)
        disk_rate = (disk_r + disk_w) / duration

        if disk_rate > 100:
            score += 0.75
            evidence.append(EvidenceItem("Disk I/O Rate", f"{disk_rate:.1f} MB/s"))
        elif disk_rate > 50:
            score += 0.50
            evidence.append(EvidenceItem("Disk I/O Rate", f"{disk_rate:.1f} MB/s"))
        elif disk_rate > 20:
            score += 0.30
            evidence.append(EvidenceItem("Disk I/O Rate", f"{disk_rate:.1f} MB/s"))

        if cpu_usage is not None and cpu_usage < 30 and disk_rate > 20:
            score += 0.15  # low CPU + high disk = I/O waiting
            evidence.append(EvidenceItem("CPU Utilization", f"{cpu_usage:.1f}% (low — waiting on I/O)"))
    else:
        # Without observability data, I/O is unlikely (most in-memory workloads)
        pass

    return BottleneckScore("io_bound", max(0.0, min(1.0, score)), evidence)


def _score_well_balanced(
    efficiency: float,
    speedup: float,
    worker_count: int,
    cpu_usage: float | None,
) -> BottleneckScore:
    """
    Pseudo-classifier: scores high when the workload is scaling well.
    This is NOT a bottleneck — it indicates good parallel performance.
    Reported when efficiency >= 75% and no dominant bottleneck is found.
    """
    score = 0.0
    evidence: list[EvidenceItem] = []

    evidence.append(EvidenceItem("Efficiency", f"{efficiency:.1f}%"))
    evidence.append(EvidenceItem("Speedup", f"{speedup:.2f}×"))
    evidence.append(EvidenceItem("Worker Count", str(worker_count)))

    if efficiency >= 90:
        score += 0.80
    elif efficiency >= 80:
        score += 0.65
    elif efficiency >= 70:
        score += 0.45

    if cpu_usage is not None and cpu_usage >= 75:
        evidence.append(EvidenceItem("CPU Utilization", f"{cpu_usage:.1f}%"))
        score += 0.10  # well utilized

    # CPU at or above saturation ceiling is NOT "balanced" — it is the limiting resource.
    # A workload is well-balanced only when CPU is active but not maxed out.
    if cpu_usage is not None and cpu_usage >= 90:
        score -= 0.25
        evidence.append(EvidenceItem("CPU Ceiling Warning", f"{cpu_usage:.0f}% — CPU is bottleneck"))

    return BottleneckScore("well_balanced", max(0.0, min(1.0, score)), evidence)


# ── Main entry point ──────────────────────────────────────────────────────────

def diagnose(
    workload_type: str,
    input_size: int,
    worker_count: int,
    execution_time: float,
    sequential_time: float,
    speedup: float,
    efficiency: float,
    cpu_usage: float | None = None,
    memory_usage: float | None = None,
    peak_memory_mb: float | None = None,
    observability_data: dict[str, Any] | None = None,
    profiling_data: dict[str, Any] | None = None,
) -> DiagnosisResult:
    """
    Run the Stage 1 algorithmic diagnosis.

    All inputs must come from measurable benchmark metrics.
    No LLM is involved at this stage.
    """
    scores: list[BottleneckScore] = [
        _score_cpu_bound(cpu_usage, efficiency, speedup, worker_count),
        _score_memory_bound(memory_usage, peak_memory_mb, speedup, efficiency, worker_count, cpu_usage),
        _score_synchronization_bound(speedup, efficiency, worker_count, sequential_time, execution_time, cpu_usage, observability_data),
        _score_communication_bound(observability_data, worker_count, speedup, efficiency),
        _score_load_imbalance(observability_data, efficiency, worker_count, speedup),
        _score_ipc_overhead(speedup, efficiency, worker_count, cpu_usage, execution_time, sequential_time),
        _score_worker_oversubscription(worker_count, efficiency, speedup),
        _score_serialization_bottleneck(workload_type, worker_count, speedup, efficiency, input_size),
        _score_io_bound(observability_data, cpu_usage, efficiency, worker_count),
        _score_well_balanced(efficiency, speedup, worker_count, cpu_usage),
    ]

    # Add profiling hotspot evidence to relevant classifiers
    if profiling_data and profiling_data.get("top_hotspots"):
        hotspots = profiling_data["top_hotspots"]
        if hotspots:
            top_fn = hotspots[0].get("function", "")
            top_pct = hotspots[0].get("pct_of_total", 0)
            for s in scores:
                if s.name == "cpu_bound":
                    s.evidence.append(EvidenceItem(
                        "Hottest Function",
                        f"{_short_func(top_fn)} ({top_pct:.0f}% runtime)"
                    ))

    sorted_scores = sorted(scores, key=lambda s: s.score, reverse=True)
    primary = sorted_scores[0]

    # Diagnostic Strength: absolute margin between primary and secondary score.
    # Measures how unambiguously the primary classifier leads the next competitor.
    # 0.0 = tied classifiers (ambiguous); ~1.0 = unambiguous (secondary near zero).
    # No artificial floor — if two classifiers tie, strength is genuinely 0.
    secondary_score = sorted_scores[1].score if len(sorted_scores) >= 2 else 0.0
    diagnostic_strength = max(0.0, primary.score - secondary_score)

    # Secondary bottleneck (if score gap < 20pp and score > 0.15)
    secondary = None
    secondary_evidence_strength = None
    if len(sorted_scores) >= 2 and sorted_scores[1].score > 0.15:
        gap = primary.score - sorted_scores[1].score
        if gap < 0.20 or sorted_scores[1].score > 0.35:
            secondary = sorted_scores[1].name
            # Evidence strength for secondary = its raw absolute score (not normalized)
            secondary_evidence_strength = sorted_scores[1].score

    # Optimization opportunities
    opt = _optimization_opportunities(primary.name, secondary, worker_count, efficiency, profiling_data)

    # Expected improvement
    exp_improvement = _expected_improvement(primary.name, efficiency, worker_count)

    # Risk assessment
    risk = _risk_assessment(primary.name, diagnostic_strength, efficiency, worker_count)

    # Executive summary
    summary = _executive_summary(
        primary.name, diagnostic_strength, efficiency, speedup, worker_count,
        sequential_time, execution_time, secondary
    )

    return DiagnosisResult(
        primary=primary.name,
        diagnostic_strength=diagnostic_strength,
        evidence=primary.evidence,
        secondary=secondary,
        secondary_evidence_strength=secondary_evidence_strength,
        all_scores=sorted_scores,
        optimization_opportunities=opt,
        expected_improvement_pct=exp_improvement,
        risk_assessment=risk,
        executive_summary=summary,
    )


def _short_func(label: str) -> str:
    """Extract just the function name from a cProfile label like 'file:lineno(name)'."""
    if "(" in label and label.endswith(")"):
        return label.split("(")[-1][:-1]
    return label.split("/")[-1] if "/" in label else label


def _optimization_opportunities(
    primary: str,
    secondary: str | None,
    worker_count: int,
    efficiency: float,
    profiling_data: dict[str, Any] | None,
) -> list[str]:
    base = {
        "cpu_bound": [
            "Increase worker count — workload can absorb more parallelism.",
            "Use NumPy vectorized operations to maximize per-core throughput.",
            "Consider GPU acceleration for compute-intensive kernels.",
            "Profile with cProfile to find the hottest functions.",
        ],
        "memory_bound": [
            "Reduce working set size — use chunked or streaming processing.",
            "Optimize data layout for cache locality (row-major access, contiguous arrays).",
            "Avoid unnecessary data copies between processes (use shared memory).",
            "Consider memory-mapped files for large datasets.",
        ],
        "synchronization_bound": [
            "Reduce barrier frequency — merge synchronization points.",
            "Use lock-free data structures where possible.",
            "Increase granularity — reduce the number of synchronization calls.",
            "Consider task-parallel models (Dask, Ray) with async coordination.",
        ],
        "communication_bound": [
            "Increase chunk size to reduce IPC call frequency.",
            "Use multiprocessing shared memory (Python 3.8+) instead of Pipes/Queues.",
            "Batch results before returning from workers.",
            "Reduce worker count to lower communication overhead.",
        ],
        "load_imbalance": [
            "Use dynamic work-stealing or task queues instead of static partitioning.",
            "Profile per-worker execution time to quantify imbalance.",
            "Sort input by difficulty before partitioning (larger items first).",
            "Use adaptive chunk sizes based on worker performance.",
        ],
        "ipc_overhead": [
            "Increase input size — fork/IPC overhead is amortized over larger inputs.",
            "Reduce worker count to cut IPC setup cost.",
            "Move result aggregation inside workers to reduce return payload size.",
            "Use in-process threading (threading module) for small workloads.",
        ],
        "worker_oversubscription": [
            f"Reduce worker count to match CPU count ({_CPU_COUNT} logical cores available).",
            "Context switching overhead is limiting throughput.",
            "Run a scaling study: benchmark at 1×, 0.75×, 0.5× CPU count.",
            "Use process affinity (taskset/numactl) to pin workers to cores.",
        ],
        "serialization_bottleneck": [
            "Reduce data transferred per worker — compute locally, return scalars.",
            "Use numpy arrays directly (faster pickle than Python objects).",
            "Consider multiprocessing.shared_memory for zero-copy data sharing.",
            "Replace pool.map() with pool.starmap() to avoid tuple wrapping overhead.",
        ],
        "io_bound": [
            "Use memory-mapped files (mmap) to avoid disk reads.",
            "Prefetch data before compute phases to overlap I/O and CPU.",
            "Compress data to reduce I/O volume.",
            "Use SSD-optimized I/O patterns (sequential access over random).",
        ],
        "well_balanced": [
            "Workload is scaling well — continue current parallelization strategy.",
            "Consider scaling beyond current worker count for further gains.",
            "Run a profiling session to confirm no hidden bottlenecks.",
            "Benchmark at higher input sizes to stress-test scalability ceiling.",
        ],
    }

    opportunities = list(base.get(primary, []))

    # Add profiling-specific opportunity
    if profiling_data and profiling_data.get("top_hotspots"):
        hotspots = profiling_data["top_hotspots"]
        if hotspots:
            top = hotspots[0]
            pct = top.get("pct_of_total", 0)
            if pct > 30:
                fn = _short_func(top.get("function", ""))
                opportunities.append(
                    f"Profile hotspot '{fn}' consumes {pct:.0f}% of runtime — "
                    "prioritize optimization here for maximum impact."
                )

    return opportunities[:4]


def _expected_improvement(primary: str, efficiency: float, worker_count: int) -> float:
    """Conservative estimate of improvement if primary bottleneck is eliminated."""
    efficiency_gap = max(0.0, 100.0 - efficiency)
    factors = {
        "cpu_bound": 0.60,
        "memory_bound": 0.50,
        "synchronization_bound": 0.55,
        "communication_bound": 0.50,
        "load_imbalance": 0.65,
        "ipc_overhead": 0.70,
        "worker_oversubscription": 0.45,
        "serialization_bottleneck": 0.60,
        "io_bound": 0.75,
        "well_balanced": 0.10,
    }
    factor = factors.get(primary, 0.50)
    return round(efficiency_gap * factor, 1)


def _risk_assessment(primary: str, diagnostic_strength: float, efficiency: float, worker_count: int) -> str:
    # diagnostic_strength is the absolute margin between primary and secondary score.
    # > 0.40 = clear single bottleneck; > 0.20 = moderate separation; <= 0.20 = ambiguous.
    if diagnostic_strength > 0.40 and efficiency < 30:
        return "HIGH — bottleneck is unambiguous and efficiency is critically low. Immediate action recommended."
    elif diagnostic_strength > 0.20 and efficiency < 60:
        return "MEDIUM — bottleneck identified with clear separation. Optimization will yield measurable gains."
    elif efficiency >= 75:
        return "LOW — workload is scaling well. Further optimization has diminishing returns."
    else:
        return "MEDIUM — multiple factors contribute to overhead. Profile-guided optimization recommended."


def _executive_summary(
    primary: str,
    diagnostic_strength: float,
    efficiency: float,
    speedup: float,
    worker_count: int,
    sequential_time: float | None,
    execution_time: float | None,
    secondary: str | None,
) -> str:
    label_map = {
        "cpu_bound": "CPU-Bound",
        "memory_bound": "Memory-Bound",
        "synchronization_bound": "Synchronization-Bound",
        "communication_bound": "Communication-Bound",
        "load_imbalance": "Load-Imbalanced",
        "ipc_overhead": "IPC-Overhead-Limited",
        "worker_oversubscription": "Worker-Oversubscribed",
        "serialization_bottleneck": "Serialization-Bottlenecked",
        "io_bound": "I/O-Bound",
        "well_balanced": "Well-Balanced",
    }
    label = label_map.get(primary, primary.replace("_", " ").title())
    sec_note = f" A secondary {secondary.replace('_', ' ')} pattern is also present." if secondary else ""
    efficiency_note = (
        "well" if efficiency >= 75
        else "acceptably" if efficiency >= 50
        else "poorly"
    )
    # Describe diagnostic clarity from the margin between classifiers
    if diagnostic_strength >= 0.40:
        clarity = "clearly"
    elif diagnostic_strength >= 0.20:
        clarity = "likely"
    else:
        clarity = "tentatively"

    return (
        f"This workload is {clarity} classified as {label} "
        f"(diagnostic strength: {diagnostic_strength:.2f}). "
        f"With {worker_count} workers, it is scaling {efficiency_note} "
        f"({speedup:.2f}× speedup, {efficiency:.1f}% efficiency).{sec_note} "
        f"See Optimization Opportunities for actionable next steps."
    )
