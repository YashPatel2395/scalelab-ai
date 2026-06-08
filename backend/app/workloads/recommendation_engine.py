"""
Recommendation Engine
──────────────────────
Simulates a collaborative-filtering recommendation service with four stages:
  1. Candidate generation – item_features @ user_profile (dot product affinity).
  2. Multi-factor ranking – final_score = 0.6*affinity + 0.25*popularity + 0.15*recency.
                            recency_score = 1 / (1 + log1p(item_age_days)).
  3. Diversity re-ranking – Maximal Marginal Relevance (MMR) on top-200 candidates.
                            Penalises items too similar to already-selected items.
                            O(K²·D) but K=200, D=32 — fast in parent.
  4. Assembly             – top-20 recommendations with scores.

Parallelism mechanism:
  Module-level _RECO_ITEMS, _RECO_USER, _RECO_POPULARITY, _RECO_RECENCY are set
  before fork.  Workers get (start, end); compute affinity + multi-factor score
  for their chunk; return top-200 (indices_bytes int32, scores_bytes float32).
  Parent merges candidates and performs MMR re-ranking.
"""

import time
import tracemalloc

import numpy as np
import psutil
from scipy.ndimage import gaussian_filter1d

from app.workloads.base import BaseWorkload, WorkloadResult
from app.workloads._pool import get_mp_context

# ─── Module-level shared state ─────────────────────────────────────────────────
_RECO_ITEMS: np.ndarray | None = None       # shape (N, 32) float32
_RECO_USER: np.ndarray | None = None        # shape (32,) float32
_RECO_POPULARITY: np.ndarray | None = None  # shape (N,) float32
_RECO_RECENCY: np.ndarray | None = None     # shape (N,) float32 — pre-computed

_ITEM_FACTORS   = 64    # latent factor dimension (doubled for richer representation)
_TOP_CANDIDATES = 200   # fed into MMR
_TOP_RECS       = 20    # final output

# Feature-enrichment passes: Gaussian smoothing + L2 normalisation along item
# factor axis. Simulates learned feature mixing in embedding layers.
# At N=300 000, D=64: 12 passes ≈ 1.0 s sequential.
_N_FEATURE_PASSES = 12


def _enrich_item_features(arr: np.ndarray, n_passes: int) -> np.ndarray:
    """Apply n_passes of gaussian smoothing + row-L2-normalisation to item feature matrix."""
    a = arr.copy()
    for _ in range(n_passes):
        a = gaussian_filter1d(a, sigma=1.5, axis=1)
        norms = np.linalg.norm(a, axis=1, keepdims=True)
        a /= np.where(norms == 0, 1.0, norms)
    return a

# Ranking weights
_W_AFFINITY    = 0.6
_W_POPULARITY  = 0.25
_W_RECENCY     = 0.15

# MMR lambda: trade-off between relevance and diversity
_MMR_LAMBDA = 0.7


# ─── Worker function ──────────────────────────────────────────────────────────

def _reco_worker(args: tuple) -> tuple[bytes, bytes]:
    """
    Worker: enrich item features, then compute multi-factor scores for a chunk.

    _RECO_ITEMS, _RECO_USER, _RECO_POPULARITY, _RECO_RECENCY are fork-inherited.
    Returns (indices_bytes int32, scores_bytes float32) for top-200 in chunk.
    """
    start, end, n_passes = args
    items      = _enrich_item_features(_RECO_ITEMS[start:end], n_passes)  # (chunk_n, 64)
    popularity = _RECO_POPULARITY[start:end]
    recency    = _RECO_RECENCY[start:end]

    # Stage 2: affinity on enriched features
    affinity = items @ _RECO_USER                # (chunk_n,)

    # Stage 2: multi-factor score
    score = (_W_AFFINITY * affinity
             + _W_POPULARITY * popularity
             + _W_RECENCY * recency).astype(np.float32)

    local_n = score.shape[0]
    k = min(_TOP_CANDIDATES, local_n)
    top_local  = np.argpartition(score, -k)[-k:]
    top_indices = (top_local + start).astype(np.int32)
    top_scores  = score[top_local].astype(np.float32)
    return top_indices.tobytes(), top_scores.tobytes()


# ─── MMR re-ranking (parent process) ─────────────────────────────────────────

def _mmr_rerank(
    item_features: np.ndarray,
    candidates: np.ndarray,
    candidate_scores: np.ndarray,
    top_k: int,
    lmbda: float = _MMR_LAMBDA,
) -> np.ndarray:
    """
    Greedy Maximal Marginal Relevance selection.

    Returns an array of top_k item indices chosen to balance
    relevance (score) and diversity (max cosine similarity to already-selected).
    """
    selected: list[int] = []
    selected_vecs: list[np.ndarray] = []
    remaining = list(range(len(candidates)))

    # Normalise candidate embeddings once
    vecs = item_features[candidates].astype(np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    vecs_norm = vecs / norms

    while len(selected) < min(top_k, len(remaining)):
        best_idx_in_remaining = -1
        best_mmr = -np.inf

        if not selected_vecs:
            # First pick: highest relevance score
            rel_scores = np.array([candidate_scores[r] for r in remaining])
            best_idx_in_remaining = int(np.argmax(rel_scores))
        else:
            sel_mat = np.array(selected_vecs)   # (k_sel, D)
            for pos, r in enumerate(remaining):
                relevance = float(candidate_scores[r])
                sims = sel_mat @ vecs_norm[r]   # cosine sims to selected
                max_sim = float(np.max(sims))
                mmr_val = lmbda * relevance - (1.0 - lmbda) * max_sim
                if mmr_val > best_mmr:
                    best_mmr = mmr_val
                    best_idx_in_remaining = pos

        chosen_pos = remaining.pop(best_idx_in_remaining)
        selected.append(chosen_pos)
        selected_vecs.append(vecs_norm[chosen_pos])

    return candidates[np.array(selected)]


# ─── Sequential helper ─────────────────────────────────────────────────────────

def _sequential_reco(
    items: np.ndarray,
    user: np.ndarray,
    popularity: np.ndarray,
    recency: np.ndarray,
    n_passes: int,
) -> np.ndarray:
    """Enrich item features then score all items. Returns score array (N,)."""
    enriched = _enrich_item_features(items, n_passes)
    affinity = enriched @ user
    return (_W_AFFINITY * affinity + _W_POPULARITY * popularity + _W_RECENCY * recency).astype(np.float32)


# ─── Workload ──────────────────────────────────────────────────────────────────

class RecommendationEngineWorkload(BaseWorkload):
    """
    input_size = N  →  collaborative-filtering rec engine over N catalog items.
    """

    def run(self, input_size: int, worker_count: int, iterations: int) -> WorkloadResult:
        global _RECO_ITEMS, _RECO_USER, _RECO_POPULARITY, _RECO_RECENCY

        n = input_size
        rng = np.random.default_rng(seed=17)

        # Item latent factors (unit-normalised)
        raw_items = rng.standard_normal((n, _ITEM_FACTORS)).astype(np.float32)
        norms = np.linalg.norm(raw_items, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        items = raw_items / norms

        # User preference vector (unit-normalised)
        raw_user = rng.standard_normal(_ITEM_FACTORS).astype(np.float32)
        user_norm = np.linalg.norm(raw_user)
        user = raw_user / max(user_norm, 1e-9)

        # Popularity score: power-law distributed (common in rec systems)
        popularity = (rng.power(0.5, size=n)).astype(np.float32)

        # Recency: item_age_days ~ exponential; recency = 1 / (1 + log1p(age))
        item_age = rng.exponential(scale=30.0, size=n).astype(np.float32)
        recency = (1.0 / (1.0 + np.log1p(item_age))).astype(np.float32)

        # ── Sequential baseline ──────────────────────────────────────────────
        seq_times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            _sequential_reco(items, user, popularity, recency, _N_FEATURE_PASSES)
            seq_times.append(time.perf_counter() - t0)
        sequential_time = min(seq_times)

        # ── Parallel execution ────────────────────────────────────────────────
        _RECO_ITEMS      = items
        _RECO_USER       = user
        _RECO_POPULARITY = popularity
        _RECO_RECENCY    = recency

        tracemalloc.start()
        cpu_before = psutil.cpu_percent(interval=None)

        par_times = []
        final_recs: np.ndarray | None = None
        for _ in range(iterations):
            t0 = time.perf_counter()
            final_recs = self._parallel_reco(n, worker_count, items)
            par_times.append(time.perf_counter() - t0)

        cpu_after = psutil.cpu_percent(interval=0.1)
        mem_after = psutil.virtual_memory().percent
        _, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        _RECO_ITEMS      = None
        _RECO_USER       = None
        _RECO_POPULARITY = None
        _RECO_RECENCY    = None

        parallel_time = min(par_times)

        result = WorkloadResult(
            workload_type="recommendation_engine",
            input_size=input_size,
            worker_count=worker_count,
            iterations=iterations,
            execution_time=round(parallel_time, 6),
            sequential_time=round(sequential_time, 6),
            cpu_usage=round((cpu_before + cpu_after) / 2, 2),
            memory_usage=round(mem_after, 2),
            peak_memory_mb=round(peak_mem / 1024 / 1024, 3),
            extra={
                "catalog_size": n,
                "item_factors": _ITEM_FACTORS,
                "feature_passes": _N_FEATURE_PASSES,
                "top_candidates": _TOP_CANDIDATES,
                "final_recommendations": _TOP_RECS,
                "mmr_lambda": _MMR_LAMBDA,
                "top_rec_indices": final_recs[:5].tolist() if final_recs is not None and len(final_recs) >= 5 else [],
                "pipeline_stages": ["candidate_generation", "affinity_scoring", "multi_factor_ranking", "mmr_reranking"],
            },
        )
        result.compute_derived()
        return result

    @staticmethod
    def _parallel_reco(n: int, n_workers: int, items: np.ndarray) -> np.ndarray:
        """Distribute feature enrichment + scoring across workers; merge top-200; MMR in parent."""
        chunk_size = max(1, n // n_workers)
        tasks = [(i, min(i + chunk_size, n), _N_FEATURE_PASSES) for i in range(0, n, chunk_size)]
        actual_workers = min(n_workers, len(tasks))

        if actual_workers == 1:
            idx_b, sc_b = _reco_worker(tasks[0])
            all_indices = np.frombuffer(idx_b, dtype=np.int32).copy()
            all_scores  = np.frombuffer(sc_b, dtype=np.float32).copy()
        else:
            ctx = get_mp_context()
            with ctx.Pool(processes=actual_workers) as pool:
                results = pool.map(_reco_worker, tasks)

            parts_idx = [np.frombuffer(r[0], dtype=np.int32) for r in results]
            parts_sc  = [np.frombuffer(r[1], dtype=np.float32) for r in results]
            all_indices = np.concatenate(parts_idx)
            all_scores  = np.concatenate(parts_sc)

        # Global top-200 before MMR
        total   = all_scores.shape[0]
        k_merge = min(_TOP_CANDIDATES, total)
        top_pos = np.argpartition(all_scores, -k_merge)[-k_merge:]
        candidates  = all_indices[top_pos]
        cand_scores = all_scores[top_pos]

        # Stage 3 – MMR diversity re-ranking (parent process)
        # Enrich only the top-200 candidates for MMR similarity (fast: 200 × D × N_PASSES)
        top_items_enriched = _enrich_item_features(items[candidates], _N_FEATURE_PASSES)
        final_indices = _mmr_rerank(top_items_enriched, np.arange(len(candidates), dtype=np.int32), cand_scores, top_k=_TOP_RECS)
        # Map back to original global indices
        return candidates[final_indices]
