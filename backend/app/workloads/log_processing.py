"""
Log Processing Pipeline
────────────────────────
Simulates a high-throughput log analytics job with four stages:
  1. Parse/filter  – extract error records (status_code >= 400) and slow records.
  2. Group         – by (service_id, endpoint_id, hour_bucket)
                     where hour_bucket = timestamp // 3600.
  3. Aggregate     – count, error_count, sum_latency, max_latency per group.
                     availability_pct = 1 - error_count / count.
  4. Rank          – top-20 worst endpoints by error_rate descending.

Parallelism mechanism:
  Five module-level numpy arrays (_LOG_SERVICE, _LOG_ENDPOINT, _LOG_STATUS,
  _LOG_LATENCY, _LOG_TS) are set before fork.  Workers get (start, end) and
  return JSON-encoded per-group aggregations.  Parent merges dicts and ranks.

P95 latency is approximated as mean + 2 * std for merged groups (no raw arrays
need to be returned from workers).
"""

import json
import time
import tracemalloc

import numpy as np
import psutil

from app.workloads.base import BaseWorkload, WorkloadResult
from app.workloads._pool import get_mp_context

# ─── Module-level shared state ─────────────────────────────────────────────────
_LOG_SERVICE: np.ndarray | None = None    # int16 (N,)  service_id   0-15
_LOG_ENDPOINT: np.ndarray | None = None   # int16 (N,)  endpoint_id  0-63
_LOG_STATUS: np.ndarray | None = None     # int16 (N,)  status code
_LOG_LATENCY: np.ndarray | None = None    # float32 (N,) latency_ms
_LOG_TS: np.ndarray | None = None         # int32 (N,)  unix timestamp

_STATUS_CODES = np.array([200, 301, 400, 404, 500, 503], dtype=np.int16)
_ERROR_THRESHOLD = 400


# ─── Worker function ──────────────────────────────────────────────────────────

def _log_worker(args: tuple) -> bytes:
    """
    Worker: aggregate log slice into per-group stats.

    Group key: "svc:ep:hour"
    Value: [count, error_count, sum_latency, max_latency, sum_lat_sq]
      sum_lat_sq enables parent to compute variance / p95 approximation.
    Returns JSON bytes.
    """
    start, end = args

    svc  = _LOG_SERVICE[start:end]
    ep   = _LOG_ENDPOINT[start:end]
    stat = _LOG_STATUS[start:end]
    lat  = _LOG_LATENCY[start:end]
    ts   = _LOG_TS[start:end]

    hour = ts // 3600

    agg: dict[str, list] = {}
    for i in range(end - start):
        key = f"{int(svc[i])}:{int(ep[i])}:{int(hour[i])}"
        lat_val = float(lat[i])
        is_err  = 1 if int(stat[i]) >= _ERROR_THRESHOLD else 0

        if key in agg:
            rec = agg[key]
            rec[0] += 1
            rec[1] += is_err
            rec[2] += lat_val
            if lat_val > rec[3]:
                rec[3] = lat_val
            rec[4] += lat_val * lat_val
        else:
            agg[key] = [1, is_err, lat_val, lat_val, lat_val * lat_val]

    return json.dumps(agg).encode()


# ─── Sequential helper ─────────────────────────────────────────────────────────

def _sequential_log(
    service: np.ndarray,
    endpoint: np.ndarray,
    status: np.ndarray,
    latency: np.ndarray,
    ts: np.ndarray,
) -> dict[str, list]:
    """Full single-pass aggregation. Returns merged dict."""
    hour = ts // 3600
    agg: dict[str, list] = {}
    n = service.shape[0]
    for i in range(n):
        key = f"{int(service[i])}:{int(endpoint[i])}:{int(hour[i])}"
        lat_val = float(latency[i])
        is_err  = 1 if int(status[i]) >= _ERROR_THRESHOLD else 0

        if key in agg:
            rec = agg[key]
            rec[0] += 1
            rec[1] += is_err
            rec[2] += lat_val
            if lat_val > rec[3]:
                rec[3] = lat_val
            rec[4] += lat_val * lat_val
        else:
            agg[key] = [1, is_err, lat_val, lat_val, lat_val * lat_val]
    return agg


def _merge_log_agg(merged: dict[str, list], partial: dict[str, list]) -> None:
    """Merge partial aggregation dict into merged in-place."""
    for key, rec in partial.items():
        if key in merged:
            m = merged[key]
            m[0] += rec[0]
            m[1] += rec[1]
            m[2] += rec[2]
            if rec[3] > m[3]:
                m[3] = rec[3]
            m[4] += rec[4]
        else:
            merged[key] = list(rec)


def _rank_groups(agg: dict[str, list], top_n: int = 20) -> list[dict]:
    """Rank groups by error_rate descending; return top_n as list of dicts."""
    ranked = []
    for key, (cnt, err_cnt, sum_lat, max_lat, sum_lat_sq) in agg.items():
        parts = key.split(":")
        svc_id, ep_id, hour = int(parts[0]), int(parts[1]), int(parts[2])
        mean_lat = sum_lat / max(cnt, 1)
        variance = (sum_lat_sq / max(cnt, 1)) - mean_lat ** 2
        p95_approx = mean_lat + 2.0 * (variance ** 0.5 if variance > 0 else 0.0)
        error_rate = err_cnt / max(cnt, 1)
        availability = 1.0 - error_rate
        ranked.append({
            "service_id": svc_id,
            "endpoint_id": ep_id,
            "hour_bucket": hour,
            "count": cnt,
            "error_count": err_cnt,
            "error_rate": round(error_rate, 6),
            "mean_latency_ms": round(mean_lat, 3),
            "max_latency_ms": round(max_lat, 3),
            "p95_latency_ms": round(p95_approx, 3),
            "availability_pct": round(availability * 100, 4),
        })
    ranked.sort(key=lambda x: x["error_rate"], reverse=True)
    return ranked[:top_n]


# ─── Workload ──────────────────────────────────────────────────────────────────

class LogProcessingWorkload(BaseWorkload):
    """
    input_size = N  →  log analytics over N structured log records.
    """

    def run(self, input_size: int, worker_count: int, iterations: int) -> WorkloadResult:
        global _LOG_SERVICE, _LOG_ENDPOINT, _LOG_STATUS, _LOG_LATENCY, _LOG_TS

        n = input_size
        rng = np.random.default_rng(seed=99)

        service  = rng.integers(0, 16, size=n, dtype=np.int16)
        endpoint = rng.integers(0, 64, size=n, dtype=np.int16)
        # Status codes: weight toward 200 (70%), 301 (10%), errors (20%)
        status_idx = rng.choice(
            len(_STATUS_CODES),
            size=n,
            p=[0.60, 0.10, 0.08, 0.07, 0.10, 0.05],
        )
        status   = _STATUS_CODES[status_idx]
        latency  = rng.exponential(scale=50.0, size=n).astype(np.float32)
        # Timestamps: 24 hours of data
        ts       = rng.integers(0, 86400, size=n, dtype=np.int32)

        # ── Sequential baseline ──────────────────────────────────────────────
        seq_times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            _sequential_log(service, endpoint, status, latency, ts)
            seq_times.append(time.perf_counter() - t0)
        sequential_time = min(seq_times)

        # ── Parallel execution ────────────────────────────────────────────────
        _LOG_SERVICE  = service
        _LOG_ENDPOINT = endpoint
        _LOG_STATUS   = status
        _LOG_LATENCY  = latency
        _LOG_TS       = ts

        tracemalloc.start()
        cpu_before = psutil.cpu_percent(interval=None)

        par_times = []
        merged_agg: dict[str, list] = {}
        for _ in range(iterations):
            t0 = time.perf_counter()
            merged_agg = self._parallel_log(n, worker_count)
            par_times.append(time.perf_counter() - t0)

        cpu_after = psutil.cpu_percent(interval=0.1)
        mem_after = psutil.virtual_memory().percent
        _, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        _LOG_SERVICE  = None
        _LOG_ENDPOINT = None
        _LOG_STATUS   = None
        _LOG_LATENCY  = None
        _LOG_TS       = None

        parallel_time = min(par_times)

        # Stage 4 – Rank top-20 worst endpoints
        top_endpoints = _rank_groups(merged_agg, top_n=20)

        result = WorkloadResult(
            workload_type="log_processing",
            input_size=input_size,
            worker_count=worker_count,
            iterations=iterations,
            execution_time=round(parallel_time, 6),
            sequential_time=round(sequential_time, 6),
            cpu_usage=round((cpu_before + cpu_after) / 2, 2),
            memory_usage=round(mem_after, 2),
            peak_memory_mb=round(peak_mem / 1024 / 1024, 3),
            extra={
                "log_lines": n,
                "distinct_groups": len(merged_agg),
                "pipeline_stages": ["parsing", "error_filtering", "service_grouping", "incident_ranking"],
                "top_error_endpoint": top_endpoints[0] if top_endpoints else None,
            },
        )
        result.compute_derived()
        return result

    @staticmethod
    def _parallel_log(n: int, n_workers: int) -> dict[str, list]:
        """Distribute log processing across workers, merge in parent."""
        chunk_size = max(1, n // n_workers)
        tasks = [(i, min(i + chunk_size, n)) for i in range(0, n, chunk_size)]
        actual_workers = min(n_workers, len(tasks))

        if actual_workers == 1:
            return json.loads(_log_worker(tasks[0]).decode())

        ctx = get_mp_context()
        with ctx.Pool(processes=actual_workers) as pool:
            results = pool.map(_log_worker, tasks)

        merged: dict[str, list] = {}
        for agg_bytes in results:
            partial: dict[str, list] = json.loads(agg_bytes.decode())
            _merge_log_agg(merged, partial)
        return merged
