#!/usr/bin/env python3
"""
custom_runner.py — Subprocess harness for user-provided workloads.

Usage:
    python custom_runner.py --file /path/to/workload.py \
        --input-size 1000 --workers 4

Output (stdout): exactly one JSON line
    {
      "success": true,
      "sequential_time": 1.234,
      "execution_time": 0.678,
      "speedup": 1.82,
      "efficiency": 90.8,
      "stdout": "...",
      "return_value": {...}
    }

On failure:
    {"success": false, "error": "...", "traceback": "...", "stdout": "..."}

Multiprocessing safety
──────────────────────
The uploaded file is copied into a temporary directory as ``workload_module.py``
and that directory is added to BOTH ``sys.path`` and ``PYTHONPATH`` before the
module is imported.

Why this matters:
  When user code calls multiprocessing.Pool.map(helper_fn, chunks), Python
  pickles helper_fn by recording its __module__ attribute. The pickle module
  then verifies the function is re-importable by executing
  ``import <__module__>``.  If the module was loaded via
  importlib.util.spec_from_file_location("_custom_workload", path) — a
  synthetic name with no sys.path entry — that verification fails with:
    PicklingError: Can't pickle <function helper_fn>:
                   import of module '_custom_workload' failed

  Copying to ``workload_module.py`` and adding the directory to sys.path
  gives the module a real, importable name. ``fork`` workers inherit the
  modified sys.path. ``spawn`` workers (default on macOS Python 3.12+) need
  PYTHONPATH set in the environment, which we also do here.

Design notes
────────────
- Sequential baseline is measured by calling run(input_size, 1) before the
  parallel run. This keeps both measurements in the same warm process state.
- When worker_count == 1, speedup is clamped to 1.0 (warm-cache artifact).
- stdout from the workload is captured and returned (capped at 8 KB).
- Stdlib only — no third-party dependencies.
"""

import argparse
import cProfile
import importlib
import io
import json
import os
import pstats
import shutil
import sys
import tempfile
import time
import traceback


# Stable module name used for every run.  Functions defined at module level
# inside uploaded files will have __module__ == 'workload_module', which is
# always importable as long as work_dir is on sys.path / PYTHONPATH.
_MODULE_NAME = "workload_module"


def _install_workload(src_file: str) -> str:
    """
    Copy the workload file into a fresh temp directory as workload_module.py.

    Inserts the directory into sys.path[0] and sets PYTHONPATH so that both
    fork-based and spawn-based multiprocessing workers can import the module.

    Returns the path to the temp directory (caller must clean up).
    """
    work_dir = tempfile.mkdtemp(prefix="scalelab_run_")
    dest = os.path.join(work_dir, f"{_MODULE_NAME}.py")
    shutil.copy2(src_file, dest)

    # Fork workers inherit sys.path from the parent process.
    sys.path.insert(0, work_dir)

    # Spawn workers (default on macOS ≥ Python 3.12) start a fresh interpreter;
    # they need PYTHONPATH to find workload_module.
    existing = os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONPATH"] = work_dir + (":" + existing if existing else "")

    return work_dir


def _import_workload():
    """Import workload_module after _install_workload has set up sys.path."""
    # Evict any cached version from a prior run in the same process.
    sys.modules.pop(_MODULE_NAME, None)
    return importlib.import_module(_MODULE_NAME)


def _timed_call(
    fn, input_size: int, worker_count: int
) -> tuple[float, str, object, Exception | None]:
    """
    Call fn(input_size, worker_count) with stdout captured.

    Returns (wall_seconds, captured_stdout, return_value, exception_or_None).
    Never raises — the caller inspects the exception and re-raises after
    appending captured_stdout to all_stdout.  This ensures stdout is never
    lost when fn raises an exception.
    """
    buf = io.StringIO()
    saved = sys.stdout
    sys.stdout = buf
    elapsed = 0.0
    rv = None
    exc: Exception | None = None
    try:
        t0 = time.perf_counter()
        rv = fn(input_size, worker_count)
        elapsed = time.perf_counter() - t0
    except Exception as e:
        elapsed = time.perf_counter() - t0
        exc = e
    finally:
        sys.stdout = saved
    return elapsed, buf.getvalue(), rv, exc


def _classify_mp_error(tb: str) -> str | None:
    """
    Return a plain-English hint when the traceback indicates a known
    multiprocessing / pickling failure pattern.
    """
    markers = {
        "PicklingError": (
            "A function or object could not be pickled for multiprocessing. "
            "Make sure helper functions are defined at module level (not inside "
            "run() or another function). The fix is usually to move helper "
            "functions to the top of your file."
        ),
        "AttributeError: Can't pickle": (
            "Pickle could not find a helper function in the module. "
            "Define all functions that are passed to pool.map() at module level."
        ),
        "_pickle.PicklingError": (
            "A function or lambda could not be pickled. "
            "Replace lambda functions with named top-level functions."
        ),
        "Can't get attribute": (
            "A worker process could not find a function or class. "
            "Make sure all helper functions are defined at the top of your file, "
            "not inside run() or conditionally."
        ),
        "BrokenPipeError": (
            "A worker process exited unexpectedly. "
            "Check that your workload does not raise unhandled exceptions inside workers."
        ),
        "RemoteTraceback": (
            "An exception was raised inside a worker process. "
            "See the traceback above for the root cause."
        ),
    }
    for marker, hint in markers.items():
        if marker in tb:
            return hint
    return None


def _parse_profile_stats(profiler: cProfile.Profile, total_ms: float, top_n: int = 20) -> dict:
    """
    Parse cProfile stats into the same format as ProfileResult.to_dict().
    Compatible with ProfilingService.store_profile_data() and the frontend.
    """
    sio = io.StringIO()
    ps = pstats.Stats(profiler, stream=sio)
    ps.sort_stats("cumulative")

    stats_dict = ps.stats  # type: ignore[attr-defined]
    entries = sorted(stats_dict.items(), key=lambda x: x[1][3], reverse=True)
    total_calls = sum(v[1] for v in stats_dict.values())

    _SKIP = ("<frozen", "importlib", "encodings", "threading.py", "cprofile", "pstats", "_collections_abc")
    _FRAMEWORK = (
        "multiprocessing", "concurrent", "threading", "queue", "socket",
        "pickle", "copyreg", "_bootstrap", "selectors", "signal.py",
        "socketserver", "ssl.py", "subprocess", "<string>",
    )
    hotspots = []
    for (filename, lineno, funcname), (_, total_n, self_t, cum_t, _callers) in entries:
        if any(s in filename.lower() for s in _SKIP):
            continue
        label = f"{filename}:{lineno}({funcname})"
        pct = (cum_t / (total_ms / 1000) * 100) if total_ms > 0 else 0
        fname_lower = filename.lower()
        is_app = "workload_module" in fname_lower or (
            "<" not in filename and
            not any(fw in fname_lower for fw in _FRAMEWORK)
        )
        hotspots.append({
            "function": label,
            "calls": total_n,
            "total_time_ms": round(cum_t * 1000, 3),
            "self_time_ms": round(self_t * 1000, 3),
            "pct_of_total": round(min(pct, 100.0), 1),
            "is_app": is_app,
        })
        if len(hotspots) >= top_n:
            break

    return {
        "workload_type": "custom_python",
        "total_time_ms": round(total_ms, 2),
        "total_calls": total_calls,
        "peak_memory_mb": 0.0,
        "top_hotspots": hotspots,
        "memory_hotspots": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="ScaleLab custom workload runner")
    parser.add_argument("--file", required=True)
    parser.add_argument("--input-size", type=int, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--profile", action="store_true", default=False,
                        help="Wrap the parallel run with cProfile and include hotspot data in output")
    args = parser.parse_args()

    all_stdout: list[str] = []
    work_dir: str | None = None

    try:
        work_dir = _install_workload(args.file)
        module = _import_workload()

        if not hasattr(module, "run") or not callable(module.run):
            raise AttributeError(
                "Workload file must define a callable run(input_size, worker_count) function"
            )

        fn = module.run

        # ── Sequential baseline ───────────────────────────────────────────────
        seq_times: list[float] = []
        for _ in range(args.iterations):
            call_workers = 1 if args.workers > 1 else args.workers
            t, out, _, exc = _timed_call(fn, args.input_size, call_workers)
            all_stdout.append(out)   # always captured, even if exc is set
            if exc is not None:
                raise exc
            seq_times.append(t)
        sequential_time = min(seq_times)  # best-of

        # ── Parallel run ──────────────────────────────────────────────────────
        par_times: list[float] = []
        last_rv = None
        _profiler: cProfile.Profile | None = None

        if args.profile:
            _profiler = cProfile.Profile()

        for i in range(args.iterations):
            # Only profile the first iteration to avoid double-counting
            if args.profile and i == 0 and _profiler is not None:
                _profiler.enable()
            t, out, rv, exc = _timed_call(fn, args.input_size, args.workers)
            if args.profile and i == 0 and _profiler is not None:
                _profiler.disable()
            all_stdout.append(out)   # always captured
            if exc is not None:
                raise exc
            par_times.append(t)
            last_rv = rv
        execution_time = min(par_times)  # best-of

        # ── Derived metrics ───────────────────────────────────────────────────
        speedup = round(sequential_time / execution_time, 4) if execution_time > 0 else 1.0
        efficiency = round((speedup / args.workers) * 100.0, 2)

        # Clamp single-worker to 1.0 (warm-cache artifact; see benchmark_service.py)
        if args.workers == 1:
            speedup = 1.0
            efficiency = 100.0

        # Serialize return value safely
        try:
            rv_serializable = json.loads(json.dumps(last_rv, default=str))
        except Exception:
            rv_serializable = str(last_rv)

        result: dict = {
            "success": True,
            "sequential_time": round(sequential_time, 6),
            "execution_time": round(execution_time, 6),
            "speedup": speedup,
            "efficiency": efficiency,
            "stdout": "".join(all_stdout)[:8192],
            "return_value": rv_serializable,
            "profiling_data": (
                _parse_profile_stats(_profiler, execution_time * 1000)
                if _profiler is not None else None
            ),
        }

    except Exception as exc:
        tb = traceback.format_exc()
        hint = _classify_mp_error(tb)

        error_msg = f"{type(exc).__name__}: {exc}"
        if hint:
            error_msg = f"{error_msg}\n\nHint: {hint}"

        result = {
            "success": False,
            "error": error_msg,
            "traceback": tb[-4096:],
            "stdout": "".join(all_stdout)[:8192],
        }

    finally:
        # Clean up temp directory regardless of success/failure.
        if work_dir and os.path.isdir(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)

    print(json.dumps(result))
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
