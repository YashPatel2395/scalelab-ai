"""
ETL Data Pipeline
──────────────────
Simulates a data-warehouse ETL job with four stages:
  1. Ingest     – float32 columnar records already in memory (seeded numpy).
  2. Transform  – revenue computation, tier classification, amount normalisation.
  3. Aggregate  – group by (category_id % 20, timestamp_bucket % 24) → 480 buckets.
                  Per-bucket: count, sum_revenue, mean_revenue, max_revenue.
  4. Export     – serialise group stats to list of dicts (simulates write).

Columns (index → field):
  0 amount, 1 quantity, 2 unit_price, 3 discount, 4 tax,
  5 user_id, 6 category_id, 7 timestamp_bucket

Parallelism mechanism:
  Module-level _ETL_RECORDS is set before fork.
  Workers receive (start, end) range; process their slice; return
    (transformed_chunk_bytes, aggregation_json_bytes).
  Parent deserialises + merges dicts: sum counts/revenues, take max.
"""

import json
import time
import tracemalloc
from typing import Any

import numpy as np
import psutil

from app.workloads.base import BaseWorkload, WorkloadResult
from app.workloads._pool import get_mp_context

# ─── Module-level shared state ─────────────────────────────────────────────────
_ETL_RECORDS: np.ndarray | None = None  # shape (N, 8) float32

_N_CATEGORY_GROUPS = 20
_N_TIME_BUCKETS = 24

# Revenue thresholds for tier classification
_TIER_LOW = 100.0
_TIER_HIGH = 1000.0


# ─── Worker function ──────────────────────────────────────────────────────────

def _etl_worker(args: tuple) -> tuple[bytes, bytes]:
    """
    Worker: process a slice of ETL records.

    Returns:
      transformed_bytes : float32 revenue array for the chunk.
      agg_json_bytes    : JSON-encoded aggregation dict keyed by "cat,ts".
    """
    start, end = args
    chunk = _ETL_RECORDS[start:end].copy()   # (chunk_n, 8)

    amount      = chunk[:, 0]
    quantity    = chunk[:, 1]
    unit_price  = chunk[:, 2]
    discount    = chunk[:, 3]
    tax         = chunk[:, 4]
    category_id = chunk[:, 6].astype(np.int32)
    ts_bucket   = chunk[:, 7].astype(np.int32)

    # Stage 2 – Transform: revenue
    revenue = (amount * quantity * unit_price) * (1.0 - discount) * (1.0 + tax)

    # Tier classification (stored as int: 0=low, 1=mid, 2=high) – unused in agg
    # but kept for completeness / memory-bandwidth simulation
    _tier = np.where(revenue < _TIER_LOW, 0, np.where(revenue < _TIER_HIGH, 1, 2))  # noqa: F841

    # Normalise amount to [0,1] within the chunk
    a_min, a_max = amount.min(), amount.max()
    _amount_norm = (amount - a_min) / max(a_max - a_min, 1e-9)  # noqa: F841

    # Stage 3 – Aggregate
    group_cat = category_id % _N_CATEGORY_GROUPS
    group_ts  = ts_bucket  % _N_TIME_BUCKETS

    agg: dict[str, list] = {}   # "cat,ts" → [count, sum_rev, max_rev]
    for i in range(revenue.shape[0]):
        key = f"{int(group_cat[i])},{int(group_ts[i])}"
        rev_val = float(revenue[i])
        if key in agg:
            agg[key][0] += 1
            agg[key][1] += rev_val
            if rev_val > agg[key][2]:
                agg[key][2] = rev_val
        else:
            agg[key] = [1, rev_val, rev_val]

    return revenue.astype(np.float32).tobytes(), json.dumps(agg).encode()


# ─── Sequential helper ─────────────────────────────────────────────────────────

def _sequential_etl(records: np.ndarray) -> dict[str, list]:
    """Process the full records array in one pass. Returns aggregation dict."""
    amount      = records[:, 0]
    quantity    = records[:, 1]
    unit_price  = records[:, 2]
    discount    = records[:, 3]
    tax         = records[:, 4]
    category_id = records[:, 6].astype(np.int32)
    ts_bucket   = records[:, 7].astype(np.int32)

    revenue = (amount * quantity * unit_price) * (1.0 - discount) * (1.0 + tax)

    group_cat = category_id % _N_CATEGORY_GROUPS
    group_ts  = ts_bucket  % _N_TIME_BUCKETS

    agg: dict[str, list] = {}
    for i in range(revenue.shape[0]):
        key = f"{int(group_cat[i])},{int(group_ts[i])}"
        rev_val = float(revenue[i])
        if key in agg:
            agg[key][0] += 1
            agg[key][1] += rev_val
            if rev_val > agg[key][2]:
                agg[key][2] = rev_val
        else:
            agg[key] = [1, rev_val, rev_val]
    return agg


def _merge_agg(merged: dict[str, list], partial: dict[str, list]) -> None:
    """Merge a partial aggregation dict into the accumulated result in-place."""
    for key, (cnt, sum_rev, max_rev) in partial.items():
        if key in merged:
            merged[key][0] += cnt
            merged[key][1] += sum_rev
            if max_rev > merged[key][2]:
                merged[key][2] = max_rev
        else:
            merged[key] = [cnt, sum_rev, max_rev]


# ─── Workload ──────────────────────────────────────────────────────────────────

class EtlPipelineWorkload(BaseWorkload):
    """
    input_size = N  →  ETL pipeline over N float32 records with 8 columns.
    """

    def run(self, input_size: int, worker_count: int, iterations: int) -> WorkloadResult:
        global _ETL_RECORDS

        n = input_size
        rng = np.random.default_rng(seed=13)

        # Generate records: float32 (N, 8)
        # Columns bounded to realistic ranges to keep revenue finite
        records = rng.random((n, 8), dtype=np.float32)
        records[:, 0] *= 500.0          # amount       [0, 500]
        records[:, 1]  = (records[:, 1] * 9 + 1).astype(np.float32)  # quantity [1, 10]
        records[:, 2] *= 50.0           # unit_price   [0, 50]
        records[:, 3] *= 0.5            # discount     [0, 0.5]
        records[:, 4] *= 0.3            # tax          [0, 0.3]
        records[:, 5]  = (records[:, 5] * 10000).astype(np.float32)   # user_id
        records[:, 6]  = (records[:, 6] * 100).astype(np.float32)     # category_id
        records[:, 7]  = (records[:, 7] * 168).astype(np.float32)     # timestamp_bucket (hours)

        # ── Sequential baseline ──────────────────────────────────────────────
        seq_times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            _sequential_etl(records)
            seq_times.append(time.perf_counter() - t0)
        sequential_time = min(seq_times)

        # ── Parallel execution ────────────────────────────────────────────────
        _ETL_RECORDS = records

        tracemalloc.start()
        cpu_before = psutil.cpu_percent(interval=None)

        par_times = []
        merged_agg: dict[str, list] = {}
        for _ in range(iterations):
            t0 = time.perf_counter()
            merged_agg = self._parallel_etl(n, worker_count)
            par_times.append(time.perf_counter() - t0)

        cpu_after = psutil.cpu_percent(interval=0.1)
        mem_after = psutil.virtual_memory().percent
        _, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        _ETL_RECORDS = None
        parallel_time = min(par_times)

        # Stage 4 – Export: compute mean_revenue and serialise top buckets
        export_rows = []
        for key, (cnt, sum_rev, max_rev) in list(merged_agg.items())[:20]:
            cat_s, ts_s = key.split(",")
            export_rows.append({
                "category_group": int(cat_s),
                "hour_bucket": int(ts_s),
                "count": cnt,
                "sum_revenue": round(sum_rev, 4),
                "mean_revenue": round(sum_rev / max(cnt, 1), 4),
                "max_revenue": round(max_rev, 4),
            })

        result = WorkloadResult(
            workload_type="etl_pipeline",
            input_size=input_size,
            worker_count=worker_count,
            iterations=iterations,
            execution_time=round(parallel_time, 6),
            sequential_time=round(sequential_time, 6),
            cpu_usage=round((cpu_before + cpu_after) / 2, 2),
            memory_usage=round(mem_after, 2),
            peak_memory_mb=round(peak_mem / 1024 / 1024, 3),
            extra={
                "records": n,
                "columns": 8,
                "group_buckets": _N_CATEGORY_GROUPS * _N_TIME_BUCKETS,
                "distinct_groups_found": len(merged_agg),
                "pipeline_stages": ["ingestion", "transformation", "aggregation", "export"],
                "sample_export_rows": export_rows[:5],
            },
        )
        result.compute_derived()
        return result

    @staticmethod
    def _parallel_etl(n: int, n_workers: int) -> dict[str, list]:
        """Distribute ETL processing across workers, merge aggregations in parent."""
        chunk_size = max(1, n // n_workers)
        tasks = [(i, min(i + chunk_size, n)) for i in range(0, n, chunk_size)]
        actual_workers = min(n_workers, len(tasks))

        if actual_workers == 1:
            _rev_bytes, agg_bytes = _etl_worker(tasks[0])
            partial: dict[str, list] = json.loads(agg_bytes.decode())
            return partial

        ctx = get_mp_context()
        with ctx.Pool(processes=actual_workers) as pool:
            results = pool.map(_etl_worker, tasks)

        merged: dict[str, list] = {}
        for _rev_bytes, agg_bytes in results:
            partial = json.loads(agg_bytes.decode())
            _merge_agg(merged, partial)
        return merged
