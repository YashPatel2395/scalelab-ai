"""
Mock AI Provider
─────────────────
Produces algorithmically derived analysis without any API calls.
Based on Amdahl's Law, efficiency thresholds, and workload-specific heuristics.
Useful for demos, CI, and development without API keys.
"""

import math

from app.ai.base import AnalysisResult, BaseAIProvider

# Workload-specific knowledge base for realistic mock analysis
_WORKLOAD_PROFILES = {
    "matrix_multiplication": {
        "parallel_fraction": 0.95,   # Row partitioning is highly parallel
        "bound_type_hint": "compute",
        "base_recommendations": [
            "Consider BLAS-optimized libraries (OpenBLAS, MKL) for single-node acceleration.",
            "For very large matrices, evaluate block decomposition to improve cache locality.",
            "At N > 1024, communication overhead of broadcasting B to all workers becomes significant.",
        ],
    },
    "parallel_sort": {
        "parallel_fraction": 0.80,   # Merge phase is sequential
        "bound_type_hint": "compute",
        "base_recommendations": [
            "The k-way merge phase is sequential – its O(N log P) cost limits overall speedup.",
            "Bitonic sort or sample sort algorithms offer better parallel merge strategies.",
            "For production, consider Radix sort which has better parallel characteristics.",
        ],
    },
    "image_processing": {
        "parallel_fraction": 0.92,
        "bound_type_hint": "memory",
        "base_recommendations": [
            "Image processing is memory-bandwidth bound; adding more cores beyond physical limits yields diminishing returns.",
            "Increase tile/strip size to improve cache reuse per worker.",
            "Consider GPU acceleration (CUDA/OpenCL) for convolution-heavy pipelines – 10-100x over CPU.",
        ],
    },
    "graph_bfs": {
        "parallel_fraction": 0.60,   # BFS is inherently serial along the diameter
        "bound_type_hint": "communication",
        "base_recommendations": [
            "BFS is limited by graph diameter – O(diameter) sequential steps cannot be parallelized.",
            "Graph partitioning (METIS) reduces cross-partition communication in distributed BFS.",
            "Consider direction-optimizing BFS (Beamer et al.) which switches between top-down and bottom-up.",
        ],
    },
}


def _amdahl_speedup(p_frac: float, n_workers: int) -> float:
    """Amdahl's Law: S(P) = 1 / ((1 - p) + p/P)"""
    if n_workers <= 0:
        return 1.0
    serial_frac = 1.0 - p_frac
    return 1.0 / (serial_frac + p_frac / n_workers)


def _classify_bottleneck(
    efficiency: float,
    cpu_usage: float,
    memory_usage: float,
    workload_type: str,
) -> str:
    profile = _WORKLOAD_PROFILES.get(workload_type, {})
    hint = profile.get("bound_type_hint", "compute")

    if efficiency >= 80:
        return "well_balanced"
    if hint == "memory" or memory_usage > 80:
        return "memory_bound"
    if hint == "communication":
        return "communication_bound"
    return "cpu_bound"


class MockAIProvider(BaseAIProvider):
    """
    Deterministic, algorithmically-derived analysis.
    No API calls. Works offline. Safe for CI.
    """

    def analyze(self, benchmark_data: dict) -> AnalysisResult:
        workload = benchmark_data.get("workload_type", "unknown")
        workers = benchmark_data.get("worker_count", 1)
        speedup = benchmark_data.get("speedup") or 1.0
        efficiency = benchmark_data.get("efficiency") or 100.0
        cpu = benchmark_data.get("cpu_usage") or 0.0
        memory = benchmark_data.get("memory_usage") or 0.0
        seq_time = benchmark_data.get("sequential_time") or 0.0
        par_time = benchmark_data.get("execution_time") or 0.0
        n = benchmark_data.get("input_size", 0)

        profile = _WORKLOAD_PROFILES.get(workload, {
            "parallel_fraction": 0.75,
            "bound_type_hint": "compute",
            "base_recommendations": [
                "Profile with perf or py-spy to identify hot code paths.",
                "Evaluate NUMA topology – cross-socket memory access can halve bandwidth.",
                "Consider async I/O or non-blocking communication if applicable.",
            ],
        })

        p_frac = profile["parallel_fraction"]
        theoretical_max = _amdahl_speedup(p_frac, workers)
        bottleneck_type = _classify_bottleneck(efficiency, cpu, memory, workload)

        # ── Speedup explanation ──────────────────────────────────────────────
        speedup_ratio = speedup / max(theoretical_max, 0.01)
        if speedup_ratio >= 0.90:
            speedup_exp = (
                f"The measured speedup of {speedup:.2f}x with {workers} workers is "
                f"excellent, reaching {speedup_ratio*100:.0f}% of the Amdahl theoretical maximum "
                f"of {theoretical_max:.2f}x. The workload is highly parallelizable with minimal "
                f"sequential overhead at this scale."
            )
        elif speedup_ratio >= 0.65:
            speedup_exp = (
                f"The measured speedup of {speedup:.2f}x is {speedup_ratio*100:.0f}% of the "
                f"Amdahl limit ({theoretical_max:.2f}x for {workers} workers). Moderate overhead "
                f"from process spawn, data serialization, or load imbalance is reducing efficiency. "
                f"Parallel efficiency of {efficiency:.1f}% indicates room for optimization."
            )
        else:
            speedup_exp = (
                f"The measured speedup of {speedup:.2f}x is significantly below the Amdahl "
                f"ceiling of {theoretical_max:.2f}x ({speedup_ratio*100:.0f}% achieved). "
                f"At {efficiency:.1f}% efficiency with {workers} workers, overhead likely exceeds "
                f"parallelism gains for this problem size. Consider reducing worker count or "
                f"increasing input size to amortize coordination costs."
            )

        # ── Bottleneck details ───────────────────────────────────────────────
        bt_details_map = {
            "well_balanced": (
                f"This workload exhibits well-balanced parallelism at input_size={n}. "
                f"CPU utilization ({cpu:.1f}%) and memory pressure ({memory:.1f}%) are in healthy ranges. "
                f"The {efficiency:.1f}% parallel efficiency indicates near-linear scaling."
            ),
            "cpu_bound": (
                f"CPU utilization of {cpu:.1f}% confirms this is a compute-intensive workload. "
                f"The {efficiency:.1f}% parallel efficiency suggests the serial fraction "
                f"(estimated {(1-p_frac)*100:.0f}%) is becoming the dominant cost as worker count grows. "
                f"This matches Amdahl's Law: diminishing returns beyond {math.ceil(1/(1-p_frac))} workers."
            ),
            "memory_bound": (
                f"Memory pressure at {memory:.1f}% system usage indicates memory-bandwidth saturation. "
                f"The workload moves large data arrays through cache hierarchies faster than compute. "
                f"Scaling beyond the number of physical NUMA nodes ({memory:.0f}% load) yields little benefit "
                f"because all workers contend for the same memory bus."
            ),
            "communication_bound": (
                f"With {workers} workers, inter-process communication overhead dominates. "
                f"Data serialization, IPC, and result aggregation represent fixed costs that "
                f"scale with worker count. The {seq_time:.4f}s sequential vs {par_time:.4f}s parallel "
                f"gap shrinks because coordination cost grows O(P) while compute shrinks O(1/P)."
            ),
        }
        bottleneck_details = bt_details_map.get(bottleneck_type, "Analysis unavailable.")

        # ── Complexity interpretation ────────────────────────────────────────
        complexity_map = {
            "matrix_multiplication": (
                f"At N={n}, sequential complexity is O(N³) = O({n**3:,}). "
                f"Parallel complexity with {workers} workers: O(N³/P) = O({n**3//max(workers,1):,}). "
                f"Row partitioning has perfect load balance when N is divisible by P."
            ),
            "parallel_sort": (
                f"Sorting N={n:,} elements: O(N log N) ≈ O({int(n * math.log2(max(n,2))):,}) comparisons. "
                f"Parallel phase: O((N/P) log(N/P)) per worker. "
                f"Merge phase: O(N log P) = O({int(n * math.log2(max(workers,2))):,}) – this is the serial bottleneck."
            ),
            "image_processing": (
                f"Processing {n}×{n}={n*n:,} pixels. Gaussian blur: O(N² × k²) per strip. "
                f"Sobel: O(N²). Total parallel: O(N²/P) compute with O(N) halo communication per strip."
            ),
            "graph_bfs": (
                f"BFS on {n:,} nodes: O(V + E) sequential. "
                f"Parallel LS-BFS: O(diameter × V/P) compute, but diameter is serial. "
                f"For Erdős–Rényi G(N, 10/N), expected diameter ≈ O(log N) = O({math.ceil(math.log(max(n,2))):,} levels)."
            ),
        }
        complexity_interp = complexity_map.get(
            workload, f"Workload complexity at input_size={n} with {workers} workers."
        )

        # ── Recommendations ──────────────────────────────────────────────────
        recs = list(profile["base_recommendations"])
        if efficiency < 50 and workers > 2:
            recs.insert(0, f"Consider reducing worker count to {max(2, workers // 2)} – current overhead outweighs parallelism gains.")
        if efficiency > 90:
            recs.insert(0, f"Current configuration is near-optimal. Try input_size={n * 2} to test sustained scaling.")

        bottleneck_summaries = {
            "well_balanced": f"Workload scales efficiently with {workers} workers at {efficiency:.0f}% parallel efficiency.",
            "cpu_bound": f"CPU-bound: serial fraction limits speedup; Amdahl ceiling ≈ {theoretical_max:.1f}x.",
            "memory_bound": f"Memory-bandwidth bound: adding workers beyond cache/NUMA limits yields diminishing returns.",
            "communication_bound": f"Communication-bound: IPC overhead dominates for {workers} workers at this problem size.",
        }

        return AnalysisResult(
            bottleneck_type=bottleneck_type,
            bottleneck_summary=bottleneck_summaries.get(bottleneck_type, ""),
            speedup_explanation=speedup_exp,
            bottleneck_details=bottleneck_details,
            optimization_recommendations=recs,
            complexity_interpretation=complexity_interp,
            theoretical_max_speedup=round(theoretical_max, 3),
            parallel_fraction_estimate=round(p_frac, 3),
            confidence="high",
            provider="mock",
            model="algorithmic-amdahl-v1",
        )
