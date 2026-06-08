"""
WorkloadProfiler
────────────────
Wraps cProfile around workload execution to identify:
  - Hottest functions by cumulative time
  - Call counts for tight loops
  - Memory allocation hotspots (via tracemalloc)

Generates a structured ProfileResult with top-N hotspot entries
suitable for serialisation and display.

Usage:
    profiler = WorkloadProfiler()
    result = profiler.profile(
        workload_type="image_processing",
        input_size=512,
        worker_count=1,
    )
    print(result.to_dict())
"""
from __future__ import annotations

import cProfile
import io
import pstats
import tracemalloc
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HotspotEntry:
    function: str          # "filename:lineno(function_name)"
    calls: int
    total_time_ms: float   # cumulative time (self + callees)
    self_time_ms: float    # time in this function only
    pct_of_total: float
    is_app: bool = True    # False = framework/runtime overhead


@dataclass
class MemoryHotspot:
    filename: str
    lineno: int
    size_kb: float
    count: int


@dataclass
class ProfileResult:
    workload_type: str
    input_size: int
    worker_count: int
    total_time_ms: float
    top_hotspots: list[HotspotEntry] = field(default_factory=list)
    memory_hotspots: list[MemoryHotspot] = field(default_factory=list)
    total_calls: int = 0
    peak_memory_mb: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "workload_type": self.workload_type,
            "input_size": self.input_size,
            "worker_count": self.worker_count,
            "total_time_ms": round(self.total_time_ms, 2),
            "total_calls": self.total_calls,
            "peak_memory_mb": round(self.peak_memory_mb, 2),
            "top_hotspots": [
                {
                    "function": h.function,
                    "calls": h.calls,
                    "total_time_ms": round(h.total_time_ms, 3),
                    "self_time_ms": round(h.self_time_ms, 3),
                    "pct_of_total": round(h.pct_of_total, 1),
                    "is_app": h.is_app,
                }
                for h in self.top_hotspots
            ],
            "memory_hotspots": [
                {
                    "filename": m.filename,
                    "lineno": m.lineno,
                    "size_kb": round(m.size_kb, 2),
                    "count": m.count,
                }
                for m in self.memory_hotspots
            ],
        }

    def summary(self) -> str:
        lines = [
            f"Profile: {self.workload_type} | N={self.input_size} | P={self.worker_count}",
            f"  Total time: {self.total_time_ms:.1f}ms | Calls: {self.total_calls:,} | Peak mem: {self.peak_memory_mb:.1f}MB",
            "  Top hotspots:",
        ]
        for i, h in enumerate(self.top_hotspots[:5], 1):
            lines.append(f"    {i}. {h.function}")
            lines.append(f"       {h.calls} calls | {h.total_time_ms:.2f}ms cumulative | {h.pct_of_total:.1f}% of total")
        return "\n".join(lines)


class WorkloadProfiler:
    """
    Profiles a single workload execution using cProfile + tracemalloc.

    Designed for development use: run once, get structured hotspot data,
    identify the bottleneck before optimising.
    """

    def profile(
        self,
        workload_type: str,
        input_size: int,
        worker_count: int = 1,
        iterations: int = 1,
        top_n: int = 20,
    ) -> ProfileResult:
        from app.workloads import WORKLOAD_REGISTRY

        if workload_type not in WORKLOAD_REGISTRY:
            raise ValueError(f"Unknown workload: {workload_type}")

        workload = WORKLOAD_REGISTRY[workload_type]()

        # ── Memory profiling ─────────────────────────────────────────────────
        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()

        # ── CPU profiling ────────────────────────────────────────────────────
        profiler = cProfile.Profile()
        t0 = time.perf_counter()
        profiler.enable()
        workload.run(
            input_size=input_size,
            worker_count=worker_count,
            iterations=iterations,
        )
        profiler.disable()
        total_ms = (time.perf_counter() - t0) * 1000

        # tracemalloc may have been stopped by multiprocessing fork/pool internals
        try:
            snapshot_after = tracemalloc.take_snapshot()
            peak_mem_bytes = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
            _mem_snapshots = (snapshot_before, snapshot_after)
        except RuntimeError:
            peak_mem_bytes = 0
            _mem_snapshots = None
            if tracemalloc.is_tracing():
                tracemalloc.stop()

        # ── Parse cProfile stats ─────────────────────────────────────────────
        sio = io.StringIO()
        ps = pstats.Stats(profiler, stream=sio)
        ps.sort_stats("cumulative")

        hotspots: list[HotspotEntry] = []
        stats_dict = ps.stats  # {(file, lineno, func): (cc, nc, tt, ct, callers)}

        entries = sorted(
            stats_dict.items(),
            key=lambda x: x[1][3],  # sort by cumulative time (ct)
            reverse=True,
        )

        total_calls = sum(v[1] for v in stats_dict.values())

        _FW_PATTERNS = (
            "multiprocessing", "concurrent", "threading", "queue", "socket",
            "pickle", "copyreg", "_bootstrap", "selectors", "signal.py",
            "socketserver", "ssl.py", "subprocess",
        )
        for (filename, lineno, funcname), (prim_calls, total_n, self_t, cum_t, _) in entries[:top_n]:
            # Skip internal Python plumbing
            fname_lower = filename.lower()
            if any(skip in fname_lower for skip in (
                "<frozen", "importlib", "encodings", "threading.py",
                "cprofile", "pstats", "_collections_abc",
            )):
                continue
            label = f"{filename}:{lineno}({funcname})"
            pct = (cum_t / (total_ms / 1000) * 100) if total_ms > 0 else 0
            is_app = "<" not in filename and not any(fw in fname_lower for fw in _FW_PATTERNS)
            hotspots.append(HotspotEntry(
                function=label,
                calls=total_n,
                total_time_ms=cum_t * 1000,
                self_time_ms=self_t * 1000,
                pct_of_total=min(pct, 100.0),
                is_app=is_app,
            ))
            if len(hotspots) >= top_n:
                break

        # ── Parse tracemalloc diff ───────────────────────────────────────────
        mem_hotspots: list[MemoryHotspot] = []
        if _mem_snapshots is not None:
            snapshot_before, snapshot_after = _mem_snapshots
            top_stats = snapshot_after.compare_to(snapshot_before, "lineno")[:10]
            for stat in top_stats:
                frame = stat.traceback[0]
                if stat.size_diff > 0:
                    mem_hotspots.append(MemoryHotspot(
                        filename=frame.filename,
                        lineno=frame.lineno,
                        size_kb=stat.size_diff / 1024,
                        count=stat.count_diff,
                    ))

        return ProfileResult(
            workload_type=workload_type,
            input_size=input_size,
            worker_count=worker_count,
            total_time_ms=total_ms,
            top_hotspots=hotspots,
            memory_hotspots=mem_hotspots,
            total_calls=total_calls,
            peak_memory_mb=peak_mem_bytes / (1024 * 1024),
        )
