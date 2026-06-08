"""
Fraud Detection Pipeline
─────────────────────────
Simulates a real-time fraud scoring engine with four stages:
  1. Feature extraction  – 20 base features + 10 pairwise interaction terms.
  2. Risk scoring        – weighted linear combination; sigmoid normalisation.
  3. Threshold ranking   – sort by risk_score; classify into low/medium/high.
  4. Top-K review queue  – return top-100 highest-risk transaction indices.

Feature matrix columns (0-indexed):
  0  amount_norm          1  velocity_1h          2  velocity_24h
  3  geo_dist             4  time_since_last      5  merchant_risk
  6  card_age             7  is_foreign           8  is_online
  9  is_weekend          10  hour_of_day_sin      11  hour_of_day_cos
  12 amount_vs_avg       13 decl_rate             14 device_fingerprint_score
  15 ip_risk             16 shipping_mismatch     17 addr_mismatch
  18 high_value_flag     19 new_merchant_flag

Parallelism mechanism:
  Module-level _FRAUD_FEATURES and _FRAUD_WEIGHTS are set before fork.
  Workers get (start, end) and return (indices_bytes, scores_bytes).
  Parent concatenates, does final ranking and tier classification.
"""

import time
import tracemalloc

import numpy as np
import psutil
from scipy.ndimage import gaussian_filter1d

from app.workloads.base import BaseWorkload, WorkloadResult
from app.workloads._pool import get_mp_context

# ─── Module-level shared state ─────────────────────────────────────────────────
_FRAUD_FEATURES: np.ndarray | None = None  # shape (N, 20) float32
_FRAUD_WEIGHTS: np.ndarray | None = None   # shape (30,) float32 — 20 feats + 10 interactions

_N_FEATURES    = 20
_N_INTERACTIONS = 10
_TOP_K_REVIEW  = 100

# Fixed interaction pairs (feature index pairs to multiply)
_INTERACTION_PAIRS = [
    (0, 1),   # amount_norm × velocity_1h
    (0, 5),   # amount_norm × merchant_risk
    (0, 3),   # amount_norm × geo_dist
    (1, 2),   # velocity_1h × velocity_24h
    (5, 15),  # merchant_risk × ip_risk
    (7, 8),   # is_foreign × is_online
    (13, 5),  # decl_rate × merchant_risk
    (18, 0),  # high_value_flag × amount_norm
    (19, 5),  # new_merchant_flag × merchant_risk
    (16, 17), # shipping_mismatch × addr_mismatch
]

# Pre-defined weights for reproducibility
_BASE_WEIGHTS = np.array([
    0.25, 0.18, 0.12, 0.08, 0.06, 0.22, -0.05, 0.15, 0.10, 0.07,
    0.03, 0.03, 0.14, 0.20, -0.09, 0.19, 0.16, 0.17, 0.21, 0.18,
], dtype=np.float32)

_INTERACTION_WEIGHTS = np.array([
    0.12, 0.15, 0.10, 0.08, 0.13, 0.09, 0.11, 0.14, 0.13, 0.11,
], dtype=np.float32)

# Combined weight vector: first 20 base features, then 10 interactions
_COMBINED_WEIGHTS = np.concatenate([_BASE_WEIGHTS, _INTERACTION_WEIGHTS])

# Risk thresholds for tier classification
_THRESHOLD_LOW  = 0.30
_THRESHOLD_HIGH = 0.70

# Feature-enrichment passes: Gaussian smoothing + L2 normalisation along feature
# axis, simulating interaction-aware preprocessing layers. Dominant CPU work.
# At N=1 000 000, D=30: 8 passes ≈ 1.2 s sequential.
_N_FEATURE_PASSES = 8


def _enrich_features(arr: np.ndarray, n_passes: int) -> np.ndarray:
    """Apply n_passes of gaussian smoothing + row-L2-normalisation to feature matrix."""
    a = arr.copy()
    for _ in range(n_passes):
        a = gaussian_filter1d(a, sigma=1.5, axis=1)
        norms = np.linalg.norm(a, axis=1, keepdims=True)
        a /= np.where(norms == 0, 1.0, norms)
    return a


# ─── Helper: compute interaction terms for a feature matrix slice ─────────────

def _compute_interactions(x: np.ndarray) -> np.ndarray:
    """Return (n, 10) float32 matrix of interaction terms."""
    interactions = np.empty((x.shape[0], _N_INTERACTIONS), dtype=np.float32)
    for k, (i, j) in enumerate(_INTERACTION_PAIRS):
        interactions[:, k] = x[:, i] * x[:, j]
    return interactions


def _score_chunk(x: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Compute risk scores for a feature matrix chunk. Returns float32 (n,)."""
    inters = _compute_interactions(x)
    combined = np.concatenate([x, inters], axis=1)   # (n, 30)
    linear = combined @ weights                        # (n,)
    # Sigmoid
    risk = (1.0 / (1.0 + np.exp(-linear.astype(np.float64)))).astype(np.float32)
    return risk


# ─── Worker function ──────────────────────────────────────────────────────────

def _fraud_worker(args: tuple) -> tuple[bytes, bytes]:
    """
    Worker: enrich features then score a slice of transactions.

    _FRAUD_FEATURES and _FRAUD_WEIGHTS are inherited via fork.
    Returns (indices_bytes int32, scores_bytes float32).
    """
    start, end, n_passes = args
    chunk = _enrich_features(_FRAUD_FEATURES[start:end], n_passes)
    scores = _score_chunk(chunk, _FRAUD_WEIGHTS)
    local_n = scores.shape[0]
    k = min(_TOP_K_REVIEW, local_n)
    top_local = np.argpartition(scores, -k)[-k:]
    top_indices = (top_local + start).astype(np.int32)
    top_scores  = scores[top_local].astype(np.float32)
    return top_indices.tobytes(), top_scores.tobytes()


# ─── Sequential helper ─────────────────────────────────────────────────────────

def _sequential_fraud(features: np.ndarray, weights: np.ndarray, n_passes: int) -> np.ndarray:
    """Enrich features then score all transactions. Returns risk score array (N,)."""
    enriched = _enrich_features(features, n_passes)
    return _score_chunk(enriched, weights)


# ─── Workload ──────────────────────────────────────────────────────────────────

class FraudDetectionWorkload(BaseWorkload):
    """
    input_size = N  →  fraud scoring pipeline over N transactions with 20 features.
    """

    def run(self, input_size: int, worker_count: int, iterations: int) -> WorkloadResult:
        global _FRAUD_FEATURES, _FRAUD_WEIGHTS

        n = input_size
        rng = np.random.default_rng(seed=42)

        features = rng.random((n, _N_FEATURES), dtype=np.float32)
        # Binary flags: clamp columns 7-9, 16-19 to {0, 1}
        for col in (7, 8, 9, 16, 17, 18, 19):
            features[:, col] = (features[:, col] > 0.5).astype(np.float32)

        weights = _COMBINED_WEIGHTS.copy()

        # ── Sequential baseline ──────────────────────────────────────────────
        seq_times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            _sequential_fraud(features, weights, _N_FEATURE_PASSES)
            seq_times.append(time.perf_counter() - t0)
        sequential_time = min(seq_times)

        # ── Parallel execution ────────────────────────────────────────────────
        _FRAUD_FEATURES = features
        _FRAUD_WEIGHTS  = weights

        tracemalloc.start()
        cpu_before = psutil.cpu_percent(interval=None)

        par_times = []
        top_indices_final: np.ndarray | None = None
        top_scores_final: np.ndarray | None = None
        for _ in range(iterations):
            t0 = time.perf_counter()
            top_indices_final, top_scores_final = self._parallel_fraud(n, worker_count)
            par_times.append(time.perf_counter() - t0)

        cpu_after = psutil.cpu_percent(interval=0.1)
        mem_after = psutil.virtual_memory().percent
        _, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        _FRAUD_FEATURES = None
        _FRAUD_WEIGHTS  = None

        parallel_time = min(par_times)

        # Tier classification on top results
        tier_counts = {"low": 0, "medium": 0, "high": 0}
        if top_scores_final is not None:
            for sc in top_scores_final:
                if sc < _THRESHOLD_LOW:
                    tier_counts["low"] += 1
                elif sc < _THRESHOLD_HIGH:
                    tier_counts["medium"] += 1
                else:
                    tier_counts["high"] += 1

        result = WorkloadResult(
            workload_type="fraud_detection",
            input_size=input_size,
            worker_count=worker_count,
            iterations=iterations,
            execution_time=round(parallel_time, 6),
            sequential_time=round(sequential_time, 6),
            cpu_usage=round((cpu_before + cpu_after) / 2, 2),
            memory_usage=round(mem_after, 2),
            peak_memory_mb=round(peak_mem / 1024 / 1024, 3),
            extra={
                "transactions": n,
                "features": _N_FEATURES,
                "interaction_terms": _N_INTERACTIONS,
                "feature_passes": _N_FEATURE_PASSES,
                "top_k_review": _TOP_K_REVIEW,
                "review_queue_size": len(top_indices_final) if top_indices_final is not None else 0,
                "tier_distribution": tier_counts,
                "pipeline_stages": ["feature_extraction", "risk_scoring", "threshold_classification", "top_k_queue"],
                "highest_risk_score": round(float(top_scores_final.max()), 6) if top_scores_final is not None and len(top_scores_final) > 0 else 0.0,
            },
        )
        result.compute_derived()
        return result

    @staticmethod
    def _parallel_fraud(n: int, n_workers: int) -> tuple[np.ndarray, np.ndarray]:
        """Distribute feature enrichment + scoring across workers, merge and rank in parent."""
        chunk_size = max(1, n // n_workers)
        tasks = [(i, min(i + chunk_size, n), _N_FEATURE_PASSES) for i in range(0, n, chunk_size)]
        actual_workers = min(n_workers, len(tasks))

        if actual_workers == 1:
            idx_b, sc_b = _fraud_worker(tasks[0])
            all_indices = np.frombuffer(idx_b, dtype=np.int32).copy()
            all_scores  = np.frombuffer(sc_b, dtype=np.float32).copy()
        else:
            ctx = get_mp_context()
            with ctx.Pool(processes=actual_workers) as pool:
                results = pool.map(_fraud_worker, tasks)

            parts_idx = [np.frombuffer(r[0], dtype=np.int32) for r in results]
            parts_sc  = [np.frombuffer(r[1], dtype=np.float32) for r in results]
            all_indices = np.concatenate(parts_idx)
            all_scores  = np.concatenate(parts_sc)

        # Final global top-K
        total  = all_scores.shape[0]
        k_final = min(_TOP_K_REVIEW, total)
        top_k_pos = np.argpartition(all_scores, -k_final)[-k_final:]
        top_indices = all_indices[top_k_pos]
        top_scores  = all_scores[top_k_pos]

        order = np.argsort(top_scores)[::-1]
        return top_indices[order], top_scores[order]
