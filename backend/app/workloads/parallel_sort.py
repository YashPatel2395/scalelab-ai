"""
Parallel Sample Sort
─────────────────────
Strategy: Sample the data to find P-1 quantile partition boundaries.
Each worker is assigned a value range [lo, hi) and sorts all elements in that range.
Results are concatenated in order – no merge step needed.

This is a partition-based parallel sort (similar to parallel radix sort conceptually).

Parallelism mechanism:
  On Unix/macOS – multiprocessing.Pool with 'fork'.
  Workers inherit the full numpy array from the parent via copy-on-write.
  Workers receive only (lo, hi, is_last) value bounds – trivial IPC.
  Workers return sorted numpy chunks as bytes.

Sequential baseline: np.sort on the full array.

Limitations:
  - Load imbalance possible if data is skewed (quantile sampling mitigates this).
  - Data return IPC: each sorted chunk is N/P × 8 bytes.
  - Sweet spot: N ≥ 10M with P = 2–4.
"""

import time
import tracemalloc

import numpy as np
import psutil

from app.workloads.base import BaseWorkload, WorkloadResult
from app.workloads._pool import get_mp_context

# ─── Module-level shared state ────────────────────────────────────────────────
_SORT_DATA: np.ndarray | None = None


def _sort_partition(args: tuple) -> bytes:
    """
    Worker: filter elements in value range [lo, hi), sort them, return bytes.
    _SORT_DATA is inherited via fork – zero IPC cost to read it.
    Only the sorted partition bytes are returned.
    """
    lo, hi, is_last = args
    if is_last:
        mask = _SORT_DATA >= lo
    else:
        mask = (_SORT_DATA >= lo) & (_SORT_DATA < hi)
    chunk = _SORT_DATA[mask].copy()
    chunk.sort()
    return chunk.tobytes()


# ─── Workload ─────────────────────────────────────────────────────────────────


class ParallelSortWorkload(BaseWorkload):
    """
    input_size = N  →  sort an array of N random int64 values.
    """

    def run(self, input_size: int, worker_count: int, iterations: int) -> WorkloadResult:
        global _SORT_DATA
        rng = np.random.default_rng(seed=7)
        _SORT_DATA = rng.integers(0, 10_000_000, size=input_size, dtype=np.int64)

        # ── Sequential baseline ──────────────────────────────────────────────
        seq_times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            np.sort(_SORT_DATA)
            seq_times.append(time.perf_counter() - t0)
        sequential_time = min(seq_times)

        # ── Parallel sort ────────────────────────────────────────────────────
        tracemalloc.start()
        cpu_before = psutil.cpu_percent(interval=None)

        par_times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            self._parallel_sort(input_size, worker_count)
            par_times.append(time.perf_counter() - t0)

        cpu_after = psutil.cpu_percent(interval=0.1)
        mem_after = psutil.virtual_memory().percent
        _, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        _SORT_DATA = None
        parallel_time = min(par_times)

        result = WorkloadResult(
            workload_type="parallel_sort",
            input_size=input_size,
            worker_count=worker_count,
            iterations=iterations,
            execution_time=round(parallel_time, 6),
            sequential_time=round(sequential_time, 6),
            cpu_usage=round((cpu_before + cpu_after) / 2, 2),
            memory_usage=round(mem_after, 2),
            peak_memory_mb=round(peak_mem / 1024 / 1024, 3),
            extra={
                "array_length": input_size,
                "algorithm": "quantile-partitioned parallel sort (no merge step)",
                "partition_strategy": "numpy.quantile boundaries",
            },
        )
        result.compute_derived()
        return result

    @staticmethod
    def _parallel_sort(n: int, n_workers: int) -> np.ndarray:
        dtype_str = _SORT_DATA.dtype.str

        if n_workers == 1:
            return np.sort(_SORT_DATA)

        # Sample quantile boundaries to partition value space
        quantiles = np.linspace(0, 1, n_workers + 1)[1:-1]
        boundaries = np.quantile(_SORT_DATA, quantiles).tolist()

        tasks: list[tuple] = []
        lo = float(_SORT_DATA.min())
        for hi in boundaries:
            tasks.append((lo, float(hi), False))
            lo = float(hi)
        tasks.append((lo, float(_SORT_DATA.max()) + 1.0, True))

        actual_workers = min(n_workers, len(tasks))
        ctx = get_mp_context()
        with ctx.Pool(processes=actual_workers) as pool:
            result_bytes = pool.map(_sort_partition, tasks)

        sorted_chunks = [
            np.frombuffer(rb, dtype=dtype_str) for rb in result_bytes
        ]
        return np.concatenate(sorted_chunks)
