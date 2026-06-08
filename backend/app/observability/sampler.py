"""
ResourceSampler
───────────────
High-frequency psutil sampler that runs in a daemon thread alongside
a benchmark execution. Collects CPU, RAM, disk I/O, and network I/O
at configurable intervals and returns a statistical summary.

Usage:
    sampler = ResourceSampler(run_id="abc123", interval=0.5)
    sampler.start()
    # ... workload runs ...
    sampler.stop()
    summary = sampler.get_summary()
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Any

import psutil


@dataclass
class ResourceSample:
    timestamp: float
    cpu_percent: float           # system-wide CPU %
    cpu_per_core: list[float]    # per-logical-core CPU %
    memory_percent: float
    memory_used_mb: float
    disk_read_bytes: int
    disk_write_bytes: int
    net_bytes_sent: int
    net_bytes_recv: int
    process_count: int


@dataclass
class ResourceSummary:
    cpu_avg: float
    cpu_peak: float
    cpu_per_core_avg: list[float]
    memory_avg_pct: float
    memory_peak_pct: float
    memory_peak_mb: float
    disk_read_mb: float          # total MB read during the run
    disk_write_mb: float         # total MB written during the run
    net_sent_mb: float           # total MB sent
    net_recv_mb: float           # total MB received
    sample_count: int
    duration_seconds: float
    timeline: list[dict]         # sparse timeline for charting (max 60 points)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpu_avg": round(self.cpu_avg, 2),
            "cpu_peak": round(self.cpu_peak, 2),
            "cpu_per_core_avg": [round(v, 2) for v in self.cpu_per_core_avg],
            "memory_avg_pct": round(self.memory_avg_pct, 2),
            "memory_peak_pct": round(self.memory_peak_pct, 2),
            "memory_peak_mb": round(self.memory_peak_mb, 1),
            "disk_read_mb": round(self.disk_read_mb, 3),
            "disk_write_mb": round(self.disk_write_mb, 3),
            "net_sent_mb": round(self.net_sent_mb, 3),
            "net_recv_mb": round(self.net_recv_mb, 3),
            "sample_count": self.sample_count,
            "duration_seconds": round(self.duration_seconds, 3),
            "timeline": self.timeline,
        }


class ResourceSampler:
    """
    Thread-safe resource sampler.
    Designed to run concurrently with a workload execution.

    SCOPE: All metrics are system-wide (psutil global counters), not process-specific.
    CPU usage reflects all active processes on the host — background tasks, the FastAPI
    server, and all benchmark workers are included in the same number. Similarly,
    disk and network I/O are host-wide totals. On an idle developer machine this is a
    reasonable approximation; under concurrent load or on a shared server the numbers
    will be polluted by unrelated activity.

    For process-isolated metrics, replace psutil.cpu_percent() with
    psutil.Process(pid).cpu_percent() aggregated over the worker pool PIDs.
    """

    def __init__(self, run_id: str = "", interval: float = 0.5):
        self.run_id = run_id
        self.interval = interval
        self._samples: list[ResourceSample] = []
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._started_at: float = 0.0
        self._stopped_at: float = 0.0

        # Baseline disk/net counters (delta measurement)
        try:
            self._disk_base = psutil.disk_io_counters()
        except Exception:
            self._disk_base = None
        try:
            self._net_base = psutil.net_io_counters()
        except Exception:
            self._net_base = None

    def start(self) -> None:
        self._stop_event.clear()
        self._samples.clear()
        self._started_at = time.monotonic()
        self._thread = threading.Thread(
            target=self._collect_loop,
            name=f"sampler-{self.run_id[:8]}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._stopped_at = time.monotonic()
        if self._thread:
            self._thread.join(timeout=self.interval * 3)

    def get_summary(self) -> ResourceSummary:
        samples = list(self._samples)  # snapshot
        if not samples:
            return ResourceSummary(
                cpu_avg=0, cpu_peak=0, cpu_per_core_avg=[],
                memory_avg_pct=0, memory_peak_pct=0, memory_peak_mb=0,
                disk_read_mb=0, disk_write_mb=0, net_sent_mb=0, net_recv_mb=0,
                sample_count=0,
                duration_seconds=self._stopped_at - self._started_at,
                timeline=[],
            )

        cpu_vals = [s.cpu_percent for s in samples]
        mem_pct_vals = [s.memory_percent for s in samples]
        mem_mb_vals = [s.memory_used_mb for s in samples]

        # Per-core averages
        n_cores = len(samples[0].cpu_per_core) if samples else 0
        core_avgs = []
        for core_idx in range(n_cores):
            vals = [s.cpu_per_core[core_idx] for s in samples if len(s.cpu_per_core) > core_idx]
            core_avgs.append(sum(vals) / len(vals) if vals else 0.0)

        # Disk/net deltas: use _disk_base/_net_base captured at construction time
        # so I/O in the first sample interval (0–500ms) is not missed.
        disk_base_r = self._disk_base.read_bytes if self._disk_base else samples[0].disk_read_bytes
        disk_base_w = self._disk_base.write_bytes if self._disk_base else samples[0].disk_write_bytes
        net_base_s = self._net_base.bytes_sent if self._net_base else samples[0].net_bytes_sent
        net_base_r = self._net_base.bytes_recv if self._net_base else samples[0].net_bytes_recv
        disk_read_mb = (samples[-1].disk_read_bytes - disk_base_r) / 1_048_576
        disk_write_mb = (samples[-1].disk_write_bytes - disk_base_w) / 1_048_576
        net_sent_mb = (samples[-1].net_bytes_sent - net_base_s) / 1_048_576
        net_recv_mb = (samples[-1].net_bytes_recv - net_base_r) / 1_048_576

        # Sparse timeline for charting (cap at 60 points)
        step = max(1, len(samples) // 60)
        timeline = [
            {
                "t": round(s.timestamp - self._started_at, 2),
                "cpu": round(s.cpu_percent, 1),
                "mem": round(s.memory_percent, 1),
            }
            for s in samples[::step]
        ]

        duration = (
            (self._stopped_at - self._started_at)
            if self._stopped_at > self._started_at
            else (time.monotonic() - self._started_at)
        )

        return ResourceSummary(
            cpu_avg=sum(cpu_vals) / len(cpu_vals),
            cpu_peak=max(cpu_vals),
            cpu_per_core_avg=core_avgs,
            memory_avg_pct=sum(mem_pct_vals) / len(mem_pct_vals),
            memory_peak_pct=max(mem_pct_vals),
            memory_peak_mb=max(mem_mb_vals),
            disk_read_mb=max(0.0, disk_read_mb),
            disk_write_mb=max(0.0, disk_write_mb),
            net_sent_mb=max(0.0, net_sent_mb),
            net_recv_mb=max(0.0, net_recv_mb),
            sample_count=len(samples),
            duration_seconds=duration,
            timeline=timeline,
        )

    def _collect_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._samples.append(self._take_sample())
            except Exception:
                pass
            self._stop_event.wait(self.interval)

    def _take_sample(self) -> ResourceSample:
        cpu_all = psutil.cpu_percent(percpu=True)
        cpu_total = sum(cpu_all) / max(len(cpu_all), 1)
        mem = psutil.virtual_memory()

        try:
            disk = psutil.disk_io_counters()
            disk_r = disk.read_bytes if disk else 0
            disk_w = disk.write_bytes if disk else 0
        except Exception:
            disk_r = disk_w = 0

        try:
            net = psutil.net_io_counters()
            net_s = net.bytes_sent if net else 0
            net_r = net.bytes_recv if net else 0
        except Exception:
            net_s = net_r = 0

        return ResourceSample(
            timestamp=time.monotonic(),
            cpu_percent=cpu_total,
            cpu_per_core=list(cpu_all),
            memory_percent=mem.percent,
            memory_used_mb=mem.used / 1_048_576,
            disk_read_bytes=disk_r,
            disk_write_bytes=disk_w,
            net_bytes_sent=net_s,
            net_bytes_recv=net_r,
            process_count=len(psutil.pids()),
        )
