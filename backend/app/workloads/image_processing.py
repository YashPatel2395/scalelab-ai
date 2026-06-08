"""
Parallel Image Processing
──────────────────────────
Strategy: Partition a synthetic grayscale image into P horizontal strips.
Each worker applies:
  1. Gaussian blur  (scipy.ndimage.gaussian_filter, σ=1.5)
  2. Sobel edge detection (scipy.ndimage.sobel on both axes → hypot)

Parallelism mechanism:
  Uses multiprocessing.Pool with 'fork' on Unix/macOS.
  Workers inherit the full image array from the parent via copy-on-write.
  Workers receive only (start_row, end_row) index ranges.
  Only processed strips (same size as input strips) are returned.

Sequential baseline: same pipeline on the full image.

Honest limitation:
  Strip boundary pixels miss halo context from adjacent strips.
  For Gaussian σ=1.5, the halo is ~3px – negligible vs strip height.

Speedup sweet spot: N >= 1024 with P = 2–4.
"""

import time
import tracemalloc

import numpy as np
import psutil
from scipy.ndimage import gaussian_filter, sobel

from app.workloads.base import BaseWorkload, WorkloadResult
from app.workloads._pool import get_mp_context

# ─── Module-level shared state ────────────────────────────────────────────────
_IMAGE: np.ndarray | None = None


def _process_strip(args: tuple) -> bytes:
    """
    Worker: apply Gaussian blur + Sobel to one horizontal strip.
    _IMAGE is inherited via fork – no copy needed.
    """
    start_row, end_row = args
    strip = _IMAGE[start_row:end_row].copy()  # copy-on-write for these pages
    blurred = gaussian_filter(strip, sigma=1.5)
    sx = sobel(blurred, axis=0)
    sy = sobel(blurred, axis=1)
    result = np.hypot(sx, sy).astype(np.float32)
    return result.tobytes()


def _process_full(image: np.ndarray) -> np.ndarray:
    """Sequential version – same pipeline, no partitioning."""
    blurred = gaussian_filter(image, sigma=1.5)
    sx = sobel(blurred, axis=0)
    sy = sobel(blurred, axis=1)
    return np.hypot(sx, sy).astype(np.float32)


# ─── Workload ─────────────────────────────────────────────────────────────────


class ImageProcessingWorkload(BaseWorkload):
    """
    input_size = N  →  process an N×N synthetic float32 image.
    """

    def run(self, input_size: int, worker_count: int, iterations: int) -> WorkloadResult:
        global _IMAGE
        n = input_size
        rng = np.random.default_rng(seed=99)
        _IMAGE = rng.random((n, n), dtype=np.float32)

        # ── Sequential baseline ──────────────────────────────────────────────
        seq_times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            _process_full(_IMAGE)
            seq_times.append(time.perf_counter() - t0)
        sequential_time = min(seq_times)

        # ── Parallel execution ───────────────────────────────────────────────
        tracemalloc.start()
        cpu_before = psutil.cpu_percent(interval=None)

        par_times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            self._parallel_process(n, worker_count)
            par_times.append(time.perf_counter() - t0)

        cpu_after = psutil.cpu_percent(interval=0.1)
        mem_after = psutil.virtual_memory().percent
        _, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        _IMAGE = None
        parallel_time = min(par_times)

        result = WorkloadResult(
            workload_type="image_processing",
            input_size=input_size,
            worker_count=worker_count,
            iterations=iterations,
            execution_time=round(parallel_time, 6),
            sequential_time=round(sequential_time, 6),
            cpu_usage=round((cpu_before + cpu_after) / 2, 2),
            memory_usage=round(mem_after, 2),
            peak_memory_mb=round(peak_mem / 1024 / 1024, 3),
            extra={
                "image_shape": f"{n}x{n}",
                "operations": ["gaussian_blur_sigma1.5", "sobel_edge_detection"],
                "dtype": "float32",
            },
        )
        result.compute_derived()
        return result

    @staticmethod
    def _parallel_process(n: int, n_workers: int) -> np.ndarray:
        strip_height = max(1, n // n_workers)
        tasks = [
            (i, min(i + strip_height, n))
            for i in range(0, n, strip_height)
        ]
        actual_workers = min(n_workers, len(tasks))

        if actual_workers == 1:
            results = [_IMAGE]  # processed inline in caller
            return _process_full(_IMAGE)

        ctx = get_mp_context()
        with ctx.Pool(processes=actual_workers) as pool:
            result_bytes = pool.map(_process_strip, tasks)

        dtype = np.float32
        strips = [
            np.frombuffer(rb, dtype=dtype).reshape(
                (tasks[i][1] - tasks[i][0], n)
            )
            for i, rb in enumerate(result_bytes)
        ]
        return np.vstack(strips)
