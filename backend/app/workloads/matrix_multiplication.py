"""
Distributed Matrix Multiplication
──────────────────────────────────
Strategy: Row-partition matrix A across P workers.
Each worker computes its slab of rows multiplied by the full B matrix.

Parallelism mechanism:
  On Unix/macOS – uses multiprocessing.Pool with 'fork' start method.
  Workers inherit B from the parent via copy-on-write (zero transfer cost).
  Only A slabs (N/P × N) are sent via IPC; results (N/P × N) come back.
  This gives true parallel numpy.dot across CPU cores.

  On Windows – falls back to spawn + full data transfer (expect lower efficiency).

Sequential baseline: numpy.dot(A, B) on full matrices.

Speedup sweet spot: N >= 1024 with P = 2–4.
At N < 512, computation time << IPC overhead → efficiency < 1.
"""

import time
import tracemalloc

import numpy as np
import psutil

from app.workloads.base import BaseWorkload, WorkloadResult
from app.workloads._pool import get_mp_context

# ─── Module-level shared state (populated by parent before fork) ──────────────
_MATRIX_B: np.ndarray | None = None


def _multiply_slab(args: tuple) -> bytes:
    """
    Worker: multiply one slab of A by the globally inherited B.
    B lives in parent-process memory and is inherited zero-cost via fork.
    """
    a_bytes, a_shape, dtype_str = args
    a_slab = np.frombuffer(a_bytes, dtype=dtype_str).reshape(a_shape).copy()
    result = np.dot(a_slab, _MATRIX_B)  # B is in forked memory, no IPC needed
    return result.tobytes()


# ─── Workload ─────────────────────────────────────────────────────────────────


class MatrixMultiplicationWorkload(BaseWorkload):
    """
    input_size = N  →  multiply two random N×N float64 matrices.
    """

    def run(self, input_size: int, worker_count: int, iterations: int) -> WorkloadResult:
        global _MATRIX_B
        n = input_size

        rng = np.random.default_rng(seed=42)
        A = rng.random((n, n), dtype=np.float64)
        B = rng.random((n, n), dtype=np.float64)

        # ── Sequential baseline ──────────────────────────────────────────────
        seq_times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            np.dot(A, B)
            seq_times.append(time.perf_counter() - t0)
        sequential_time = min(seq_times)

        # ── Parallel execution ───────────────────────────────────────────────
        # Set global B BEFORE forking so workers inherit it for free
        _MATRIX_B = B

        tracemalloc.start()
        cpu_before = psutil.cpu_percent(interval=None)

        par_times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            self._parallel_multiply(A, worker_count)
            par_times.append(time.perf_counter() - t0)

        cpu_after = psutil.cpu_percent(interval=0.1)
        mem_after = psutil.virtual_memory().percent
        _, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        _MATRIX_B = None  # Release reference

        parallel_time = min(par_times)

        result = WorkloadResult(
            workload_type="matrix_multiplication",
            input_size=input_size,
            worker_count=worker_count,
            iterations=iterations,
            execution_time=round(parallel_time, 6),
            sequential_time=round(sequential_time, 6),
            cpu_usage=round((cpu_before + cpu_after) / 2, 2),
            memory_usage=round(mem_after, 2),
            peak_memory_mb=round(peak_mem / 1024 / 1024, 3),
            extra={"matrix_shape": f"{n}x{n}", "dtype": "float64"},
        )
        result.compute_derived()
        return result

    @staticmethod
    def _parallel_multiply(A: np.ndarray, n_workers: int) -> np.ndarray:
        n = A.shape[0]
        slab_size = max(1, n // n_workers)
        slabs = [A[i : i + slab_size] for i in range(0, n, slab_size)]
        actual_workers = min(n_workers, len(slabs))

        if actual_workers == 1:
            # Single worker: skip process overhead, run inline
            return np.dot(A, _MATRIX_B)

        tasks = [
            (slab.tobytes(), slab.shape, slab.dtype.str)
            for slab in slabs
        ]

        ctx = get_mp_context()
        with ctx.Pool(processes=actual_workers) as pool:
            result_bytes = pool.map(_multiply_slab, tasks)

        dtype = A.dtype
        pieces = [
            np.frombuffer(rb, dtype=dtype).reshape(tasks[i][1])
            for i, rb in enumerate(result_bytes)
        ]
        return np.vstack(pieces)
