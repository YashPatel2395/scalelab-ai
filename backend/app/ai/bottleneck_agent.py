"""
BottleneckAgent
───────────────
Root-cause analysis engine that classifies performance bottlenecks from
benchmark metrics and observability data.

Bottleneck types:
  cpu_bound           – CPU is the limiting resource
  memory_bound        – memory bandwidth / capacity constrains throughput
  io_bound            – disk or network I/O dominates
  communication_bound – inter-process communication overhead > compute time
  balanced            – no single dominating bottleneck

Each bottleneck is assigned a severity score (0.0–1.0):
  0.75–1.0  → critical
  0.50–0.75 → high
  0.25–0.50 → medium
  0.00–0.25 → low
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

_SEVERITY_THRESHOLDS = {
    "critical": 0.75,
    "high": 0.50,
    "medium": 0.25,
    "low": 0.0,
}


def _severity_label(score: float) -> str:
    for label, threshold in _SEVERITY_THRESHOLDS.items():
        if score >= threshold:
            return label
    return "low"


def analyze_bottleneck(
    benchmark_id: str,
    workload_type: str,
    input_size: int,
    worker_count: int,
    execution_time: float,
    sequential_time: float,
    speedup: float,
    efficiency: float,
    cpu_usage: float | None,
    memory_usage: float | None,
    peak_memory_mb: float | None,
    observability_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Classify the bottleneck and produce a structured root-cause report.

    Parameters are drawn directly from a completed BenchmarkRun record.
    observability_data is the JSON blob stored by ResourceSampler.

    Returns a dict matching BottleneckReport schema.
    """
    evidence: list[str] = []
    scores: dict[str, float] = {
        "cpu_bound": 0.0,
        "memory_bound": 0.0,
        "io_bound": 0.0,
        "communication_bound": 0.0,
        "balanced": 0.0,
    }

    # ── Parallel efficiency analysis ──────────────────────────────────────────
    theoretical_speedup = float(worker_count)
    efficiency_pct = efficiency  # already in %

    efficiency_fraction = min(efficiency_pct / 100.0, 1.0) if efficiency_pct else 0.0
    parallelism_loss = 1.0 - efficiency_fraction

    if efficiency_fraction < 0.3:
        evidence.append(
            f"Parallel efficiency is very low ({efficiency_pct:.1f}%) — "
            f"speedup {speedup:.2f}× vs theoretical {theoretical_speedup:.0f}×."
        )
    elif efficiency_fraction < 0.6:
        evidence.append(
            f"Parallel efficiency is moderate ({efficiency_pct:.1f}%) — "
            f"significant overhead is limiting parallel gains."
        )

    # ── CPU utilisation analysis ──────────────────────────────────────────────
    if cpu_usage is not None:
        if cpu_usage > 90:
            scores["cpu_bound"] += 0.6
            evidence.append(
                f"CPU utilisation is very high ({cpu_usage:.1f}%) — "
                "workload is CPU-bound; more cores would directly help."
            )
        elif cpu_usage > 70:
            scores["cpu_bound"] += 0.3
            evidence.append(
                f"CPU utilisation is elevated ({cpu_usage:.1f}%) — "
                "partially CPU-bound."
            )
        elif cpu_usage < 30 and worker_count > 1:
            # Low CPU with parallel workers → waiting / synchronisation
            scores["communication_bound"] += 0.4
            scores["io_bound"] += 0.2
            evidence.append(
                f"CPU utilisation is low ({cpu_usage:.1f}%) despite {worker_count} "
                "workers — workers are likely waiting (IPC, I/O, or synchronisation)."
            )

    # ── Memory analysis ───────────────────────────────────────────────────────
    if memory_usage is not None and peak_memory_mb is not None:
        if memory_usage > 85:
            scores["memory_bound"] += 0.7
            evidence.append(
                f"Memory utilisation is critical ({memory_usage:.1f}%, "
                f"peak {peak_memory_mb:.0f} MB) — system may be swapping."
            )
        elif memory_usage > 60:
            scores["memory_bound"] += 0.3
            evidence.append(
                f"Memory utilisation is high ({memory_usage:.1f}%, "
                f"peak {peak_memory_mb:.0f} MB)."
            )

    # ── Observability time-series analysis ───────────────────────────────────
    if observability_data:
        obs_cpu_peak = observability_data.get("cpu_peak", 0)
        obs_net_recv = observability_data.get("net_recv_mb", 0)
        obs_net_sent = observability_data.get("net_sent_mb", 0)
        obs_disk_r = observability_data.get("disk_read_mb", 0)
        obs_disk_w = observability_data.get("disk_write_mb", 0)
        duration = observability_data.get("duration_seconds", 1) or 1

        net_mb_per_sec = (obs_net_recv + obs_net_sent) / duration
        disk_mb_per_sec = (obs_disk_r + obs_disk_w) / duration

        if disk_mb_per_sec > 100:
            scores["io_bound"] += 0.6
            evidence.append(
                f"Disk I/O rate is high ({disk_mb_per_sec:.1f} MB/s) — "
                "storage is a bottleneck."
            )
        elif disk_mb_per_sec > 20:
            scores["io_bound"] += 0.3
            evidence.append(
                f"Moderate disk I/O detected ({disk_mb_per_sec:.1f} MB/s)."
            )

        if net_mb_per_sec > 50:
            scores["communication_bound"] += 0.5
            evidence.append(
                f"Network traffic is significant ({net_mb_per_sec:.1f} MB/s) — "
                "inter-process communication is expensive."
            )

        if obs_cpu_peak < 50 and worker_count > 2:
            scores["communication_bound"] += 0.3

    # ── Communication overhead analysis (from speedup regression) ─────────────
    if worker_count > 1 and sequential_time and execution_time:
        # Amdahl decomposition: estimate serial fraction from actual speedup
        # S = 1 / ((1-p) + p/P)  →  p = (1/S - 1) / (1/P - 1)
        S = speedup
        P = float(worker_count)
        if S > 0 and S < P:
            denom = (1.0 / P) - 1.0
            if abs(denom) > 1e-6:
                p_est = ((1.0 / S) - 1.0) / denom
                serial_frac = 1.0 - max(0.0, min(1.0, p_est))
                if serial_frac > 0.3:
                    scores["communication_bound"] += serial_frac * 0.8
                    evidence.append(
                        f"Amdahl analysis estimates {serial_frac:.0%} serial fraction — "
                        "high IPC or synchronisation overhead."
                    )

    # ── Workload-specific heuristics ──────────────────────────────────────────
    if workload_type == "matrix_multiplication":
        scores["communication_bound"] += 0.2
        evidence.append(
            "Matrix multiply has O(N²) IPC cost (result slabs) — "
            "communication overhead grows quadratically with matrix size."
        )
    elif workload_type == "graph_bfs":
        scores["communication_bound"] += 0.15
        evidence.append(
            "Level-synchronous BFS requires barrier synchronisation at every "
            "frontier level — high synchronisation cost for shallow graphs."
        )
    elif workload_type == "parallel_sort":
        if input_size > 5_000_000:
            scores["cpu_bound"] += 0.2
        else:
            scores["communication_bound"] += 0.15
            evidence.append(
                "Small sort workloads have high IPC:compute ratio — "
                "overhead dominates for N < 5M elements."
            )
    elif workload_type == "image_processing":
        scores["cpu_bound"] += 0.2
        evidence.append(
            "Convolution-heavy image processing is compute-bound — "
            "good candidate for further parallelism."
        )

    # ── Select dominant bottleneck ─────────────────────────────────────────────
    # If no score is strongly dominant, classify as balanced
    max_score = max(scores.values())
    if max_score < 0.2:
        scores["balanced"] = 0.25
        max_score = 0.25

    bottleneck_type = max(scores, key=lambda k: scores[k])

    # Severity accounts for efficiency loss + raw score
    severity_score = min(1.0, max_score + parallelism_loss * 0.3)
    severity = _severity_label(severity_score)

    # Root cause narrative
    root_cause_map = {
        "cpu_bound": (
            f"The workload is CPU-limited. With {worker_count} workers at "
            f"{cpu_usage or 0:.0f}% CPU utilisation, compute throughput is the "
            "primary constraint."
        ),
        "memory_bound": (
            f"Memory pressure (peak {peak_memory_mb or 0:.0f} MB, "
            f"{memory_usage or 0:.0f}% utilisation) is limiting performance. "
            "Cache misses and bandwidth saturation reduce effective throughput."
        ),
        "io_bound": (
            "Disk or network I/O dominates the execution profile. "
            "Storage latency or bandwidth is the primary bottleneck."
        ),
        "communication_bound": (
            f"Inter-process communication overhead is limiting parallel speedup. "
            f"With {worker_count} workers achieving only {speedup:.2f}× speedup "
            f"({efficiency:.1f}% efficiency), serialisation and IPC cost are dominant."
        ),
        "balanced": (
            f"No single bottleneck dominates. Parallel efficiency of "
            f"{efficiency:.1f}% reflects moderate overhead across multiple dimensions."
        ),
    }

    recommendations_map = {
        "cpu_bound": [
            "Increase worker count — workload can absorb more parallelism.",
            "Use SIMD / vectorised numpy operations to maximise per-core throughput.",
            "Consider GPU acceleration for compute-intensive kernels.",
        ],
        "memory_bound": [
            "Reduce working set size or use chunked/streaming processing.",
            "Optimise data layout for cache locality (row-major access patterns).",
            "Avoid unnecessary data copies between processes.",
        ],
        "io_bound": [
            "Use memory-mapped files or in-memory data structures to avoid disk I/O.",
            "Prefetch data before compute phases to overlap I/O and CPU.",
            "Consider compressing data to reduce I/O volume.",
        ],
        "communication_bound": [
            "Increase granularity — reduce number of IPC calls by batching work.",
            "Use shared-memory (fork) instead of multiprocessing.Queue/Pipe for data transfer.",
            "Profile Scatter/Gather communication in MPI runs to isolate overhead.",
            "Consider reducing worker count to lower synchronisation cost.",
        ],
        "balanced": [
            "Profile with line_profiler to identify the hottest sections.",
            "Experiment with worker counts between current value and half/double.",
            "Consider problem-size scaling — larger input may shift the bottleneck.",
        ],
    }

    # Estimated max improvement: if bottleneck eliminated
    # Based on efficiency gap from ideal
    efficiency_gap_pct = max(0.0, 100.0 - efficiency_pct)
    estimated_max_improvement = round(efficiency_gap_pct * 0.7, 1)  # conservative 70%

    return {
        "benchmark_id": benchmark_id,
        "bottleneck_type": bottleneck_type,
        "severity": severity,
        "severity_score": round(severity_score, 3),
        "root_cause": root_cause_map[bottleneck_type],
        "evidence": evidence,
        "recommendations": recommendations_map[bottleneck_type],
        "estimated_max_improvement": estimated_max_improvement,
    }
