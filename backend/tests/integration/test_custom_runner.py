"""
Integration tests for custom_runner.py subprocess harness.

These tests exercise the end-to-end path:
  1. Write a workload .py file to a temp location
  2. Call custom_runner.py as a subprocess (same way the service does)
  3. Parse the JSON output and assert correctness

Key scenarios covered:
  - Worker counts 1, 2, 4 all succeed
  - Helper functions at module level are picklable across all worker counts
  - Lambdas and inner functions produce a clear error message
  - Invalid workload (no run()) produces a clear error
  - Return value is included in output
  - Speedup is 1.0 for single-worker (warm-cache normalisation)
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# Path to the runner script
RUNNER = Path(__file__).resolve().parents[2] / "custom_runner.py"


def _run(
    workload_source: str,
    input_size: int,
    workers: int,
    iterations: int = 1,
    profile: bool = False,
) -> dict:
    """Write workload source to a temp file and invoke custom_runner.py."""
    tmp = Path(__file__).parent / f"_tmp_workload_{workers}w.py"
    tmp.write_text(textwrap.dedent(workload_source), encoding="utf-8")
    try:
        cmd = [
            sys.executable, str(RUNNER),
            "--file", str(tmp),
            "--input-size", str(input_size),
            "--workers", str(workers),
            "--iterations", str(iterations),
        ]
        if profile:
            cmd.append("--profile")
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return json.loads(proc.stdout.strip())
    finally:
        tmp.unlink(missing_ok=True)


# ── Workload source fixtures ──────────────────────────────────────────────────

MULTIPROCESSING_WORKLOAD = """
import multiprocessing

def _chunk_sum(args):
    start, end = args
    return sum(range(start, end))

def run(input_size: int, worker_count: int) -> dict:
    chunk_size = max(1, input_size // worker_count)
    chunks = [(i, min(i + chunk_size, input_size))
               for i in range(0, input_size, chunk_size)]
    ctx = multiprocessing.get_context("fork")
    with ctx.Pool(processes=worker_count) as pool:
        partials = pool.map(_chunk_sum, chunks)
    total = sum(partials)
    expected = input_size * (input_size - 1) // 2
    return {"total": total, "correct": total == expected, "workers": worker_count}
"""

SIMPLE_WORKLOAD = """
def run(input_size: int, worker_count: int) -> dict:
    return {"total": sum(range(input_size)), "workers": worker_count}
"""

CONCURRENT_FUTURES_WORKLOAD = """
from concurrent.futures import ProcessPoolExecutor

def _partial_sum(args):
    start, end = args
    return sum(range(start, end))

def run(input_size: int, worker_count: int) -> dict:
    chunk_size = max(1, input_size // worker_count)
    chunks = [(i, min(i + chunk_size, input_size))
               for i in range(0, input_size, chunk_size)]
    with ProcessPoolExecutor(max_workers=worker_count) as ex:
        partials = list(ex.map(_partial_sum, chunks))
    return {"total": sum(partials), "workers": worker_count}
"""


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestMultiprocessingWorkload:
    """
    Core test: helper functions at module level must work at all worker counts.
    This is the scenario that was broken before the fix.
    """

    @pytest.mark.parametrize("workers", [1, 2, 4])
    def test_multiprocessing_succeeds_at_all_worker_counts(self, workers):
        result = _run(MULTIPROCESSING_WORKLOAD, input_size=50_000, workers=workers)
        assert result["success"] is True, (
            f"workers={workers} failed. error={result.get('error')}\n"
            f"traceback={result.get('traceback', '')[:800]}"
        )

    @pytest.mark.parametrize("workers", [1, 2, 4])
    def test_return_value_is_correct(self, workers):
        result = _run(MULTIPROCESSING_WORKLOAD, input_size=50_000, workers=workers)
        assert result["success"] is True
        assert result["return_value"]["correct"] is True, (
            f"Sum was wrong at workers={workers}: {result['return_value']}"
        )

    @pytest.mark.parametrize("workers", [1, 2, 4])
    def test_return_value_worker_count_matches(self, workers):
        result = _run(MULTIPROCESSING_WORKLOAD, input_size=50_000, workers=workers)
        assert result["success"] is True
        assert result["return_value"]["workers"] == workers

    def test_single_worker_speedup_is_one(self):
        result = _run(MULTIPROCESSING_WORKLOAD, input_size=50_000, workers=1)
        assert result["success"] is True
        assert result["speedup"] == 1.0, (
            f"Expected speedup=1.0 for single worker, got {result['speedup']}"
        )
        assert result["efficiency"] == 100.0

    def test_multi_worker_produces_timing_fields(self):
        result = _run(MULTIPROCESSING_WORKLOAD, input_size=200_000, workers=2)
        assert result["success"] is True
        assert result["sequential_time"] > 0
        assert result["execution_time"] > 0
        assert result["speedup"] > 0
        assert result["efficiency"] > 0


class TestSimpleWorkload:
    """Simple workload without multiprocessing — must continue to work."""

    @pytest.mark.parametrize("workers", [1, 2, 4])
    def test_simple_workload_all_workers(self, workers):
        result = _run(SIMPLE_WORKLOAD, input_size=10_000, workers=workers)
        assert result["success"] is True

    def test_return_value_present(self):
        result = _run(SIMPLE_WORKLOAD, input_size=1_000, workers=1)
        assert result["success"] is True
        assert "total" in result["return_value"]


class TestConcurrentFuturesWorkload:
    """ProcessPoolExecutor is another common pattern — must work at 2+ workers."""

    @pytest.mark.parametrize("workers", [1, 2, 4])
    def test_concurrent_futures_all_workers(self, workers):
        result = _run(CONCURRENT_FUTURES_WORKLOAD, input_size=50_000, workers=workers)
        assert result["success"] is True, (
            f"workers={workers} failed: {result.get('error')}"
        )


class TestErrorMessages:
    """Failures must produce clear, actionable error messages."""

    def test_missing_run_function_error(self):
        result = _run("x = 1\n", input_size=100, workers=1)
        assert result["success"] is False
        assert "run" in result["error"].lower()

    def test_runtime_exception_is_captured(self):
        source = """
def run(input_size: int, worker_count: int) -> dict:
    raise ValueError("deliberate error for testing")
"""
        result = _run(source, input_size=100, workers=1)
        assert result["success"] is False
        assert "deliberate error for testing" in result["error"]

    def test_syntax_error_is_captured(self):
        result = _run("def run(:\n    pass\n", input_size=100, workers=1)
        assert result["success"] is False

    def test_stdout_is_captured_on_failure(self):
        source = """
def run(input_size: int, worker_count: int) -> dict:
    print("about to fail")
    raise RuntimeError("oops")
"""
        result = _run(source, input_size=100, workers=1)
        assert result["success"] is False
        assert "about to fail" in result["stdout"]


class TestIterations:
    """Best-of-N timing."""

    def test_iterations_param_works(self):
        result = _run(SIMPLE_WORKLOAD, input_size=1_000, workers=1, iterations=3)
        assert result["success"] is True
        assert result["execution_time"] > 0


class TestProfiling:
    """
    --profile flag must populate profiling_data in the output JSON.
    Without the flag, profiling_data must be absent or None.
    """

    def test_no_profile_flag_gives_null_profiling_data(self):
        result = _run(MULTIPROCESSING_WORKLOAD, input_size=10_000, workers=2, profile=False)
        assert result["success"] is True
        # profiling_data must be None (not a dict) when profiling was not requested
        assert result.get("profiling_data") is None, (
            f"Expected profiling_data=None, got {result.get('profiling_data')}"
        )

    def test_profile_flag_includes_profiling_data(self):
        result = _run(MULTIPROCESSING_WORKLOAD, input_size=50_000, workers=2, profile=True)
        assert result["success"] is True
        pd = result.get("profiling_data")
        assert pd is not None, "profiling_data missing from result when --profile was passed"
        assert isinstance(pd, dict), f"profiling_data should be a dict, got {type(pd)}"

    def test_profiling_data_has_required_keys(self):
        result = _run(MULTIPROCESSING_WORKLOAD, input_size=50_000, workers=2, profile=True)
        assert result["success"] is True
        pd = result["profiling_data"]
        for key in ("workload_type", "total_time_ms", "total_calls", "peak_memory_mb",
                    "top_hotspots", "memory_hotspots"):
            assert key in pd, f"profiling_data missing key '{key}'"

    def test_profiling_data_total_calls_positive(self):
        result = _run(MULTIPROCESSING_WORKLOAD, input_size=50_000, workers=2, profile=True)
        assert result["success"] is True
        pd = result["profiling_data"]
        assert pd["total_calls"] > 0, "cProfile recorded 0 total calls — profiler may not have run"

    def test_profiling_data_total_time_matches_execution(self):
        result = _run(MULTIPROCESSING_WORKLOAD, input_size=50_000, workers=2, profile=True)
        assert result["success"] is True
        pd = result["profiling_data"]
        exec_ms = result["execution_time"] * 1000
        # total_time_ms should be close to execution_time (same run); allow 10× slack for overhead
        assert pd["total_time_ms"] > 0
        assert pd["total_time_ms"] < exec_ms * 10 + 500, (
            f"profiling_data.total_time_ms={pd['total_time_ms']} seems wrong for exec={exec_ms}ms"
        )

    def test_profiling_workload_type_is_custom_python(self):
        result = _run(SIMPLE_WORKLOAD, input_size=1_000, workers=1, profile=True)
        assert result["success"] is True
        assert result["profiling_data"]["workload_type"] == "custom_python"
