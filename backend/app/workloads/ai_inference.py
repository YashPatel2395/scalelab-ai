"""
AI Inference Pipeline
──────────────────────
Simulates a RAG/LLM serving pipeline with four stages:
  1. Embedding generation  – input_size documents each get a 128-dim float32
                             unit-normalised embedding vector (seeded numpy rng).
  2. Feature enrichment    – _N_FEATURE_PASSES of Gaussian smoothing + L2
                             normalisation per chunk, simulating transformer
                             attention / layer-norm passes.  This is the
                             dominant CPU work and scales linearly with N.
  3. Vector similarity search – cosine similarity via embedding @ query_vec;
                             find top-50 candidates per worker chunk.
  4. Reranking + assembly  – cross-encoder score in parent, weighted top-10.

Parallelism mechanism:
  Module-level _AI_EMBEDDINGS and _AI_QUERY are set before the pool is forked.
  Workers inherit both arrays via copy-on-write (zero IPC cost).
  Each worker copies its slice, applies _N_FEATURE_PASSES of gaussian smoothing,
  then returns (indices_bytes, scores_bytes) for its top-k candidates.
  The parent merges candidates, performs final top-50 selection and reranking.

Sizing guidance:
  Default N=200 000 → ~1.2 s sequential on a modern laptop.
  Reliable speedup visible at N ≥ 100 000 with P = 2–4 workers.
"""

from __future__ import annotations

import time
import tracemalloc

import numpy as np
import psutil
from scipy.ndimage import gaussian_filter1d

from app.workloads.base import BaseWorkload, WorkloadResult
from app.workloads._pool import get_mp_context

# ─── Module-level shared state (populated by parent before fork) ───────────────
_AI_EMBEDDINGS: np.ndarray | None = None  # shape (N, 128) float32
_AI_QUERY: np.ndarray | None = None       # shape (128,) float32

_EMBEDDING_DIM = 128
_TOP_K_CANDIDATES = 50
_TOP_K_RERANK = 10

# Number of feature-enrichment passes applied to each chunk.
# Each pass applies gaussian_filter1d (σ=1.5, axis=1) + L2 normalisation.
# At N=200 000, D=128: 12 passes ≈ 1.2 s sequential on a modern laptop.
_N_FEATURE_PASSES = 12


# ─── Feature enrichment helper ────────────────────────────────────────────────

def _enrich_features(arr: np.ndarray, n_passes: int) -> np.ndarray:
    """
    Apply n_passes of Gaussian smoothing (σ=1.5 along feature axis) followed
    by per-row L2 normalisation.  Simulates transformer attention/layer-norm.
    Returns a new array (input is NOT modified).
    """
    a = arr.copy()
    for _ in range(n_passes):
        a = gaussian_filter1d(a, sigma=1.5, axis=1)
        norms = np.linalg.norm(a, axis=1, keepdims=True)
        a /= np.where(norms == 0, 1.0, norms)
    return a


# ─── Worker function (must be module-level for pickling) ──────────────────────

def _ai_worker(args: tuple) -> tuple[bytes, bytes]:
    """
    Worker: enrich chunk features then compute cosine similarity.

    _AI_EMBEDDINGS and _AI_QUERY are inherited via fork – no IPC cost.
    Returns (indices_bytes, scores_bytes) for the top-k candidates in this chunk.
    """
    start, end, top_k, n_passes = args
    chunk = _enrich_features(_AI_EMBEDDINGS[start:end], n_passes)

    # Cosine similarity: embeddings are unit-normalised after enrichment
    scores = chunk @ _AI_QUERY
    local_n = scores.shape[0]
    k = min(top_k, local_n)
    top_local = np.argpartition(scores, -k)[-k:]
    top_indices = (top_local + start).astype(np.int32)
    top_scores = scores[top_local].astype(np.float32)
    return top_indices.tobytes(), top_scores.tobytes()


# ─── Sequential helper ─────────────────────────────────────────────────────────

def _sequential_inference(
    embeddings: np.ndarray, query: np.ndarray, n_passes: int
) -> np.ndarray:
    """Full enrichment + matrix–vector similarity on the complete corpus."""
    enriched = _enrich_features(embeddings, n_passes)
    return enriched @ query


# ─── Workload ─────────────────────────────────────────────────────────────────

class AiInferenceWorkload(BaseWorkload):
    """
    input_size = N  →  RAG pipeline over N documents with 128-dim embeddings.
    Default N=200 000 produces ~1.2 s sequential time for reliable scaling measurement.
    """

    def run(self, input_size: int, worker_count: int, iterations: int) -> WorkloadResult:
        global _AI_EMBEDDINGS, _AI_QUERY

        n = input_size
        rng = np.random.default_rng(seed=7)

        # Stage 1 – Embedding generation (in parent process)
        raw = rng.standard_normal((n, _EMBEDDING_DIM)).astype(np.float32)
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        embeddings = raw / norms                            # unit-normalised

        query_raw = rng.standard_normal(_EMBEDDING_DIM).astype(np.float32)
        query_norm = np.linalg.norm(query_raw)
        query = query_raw / max(query_norm, 1e-9)

        # ── Sequential baseline ──────────────────────────────────────────────
        seq_times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            _sequential_inference(embeddings, query, _N_FEATURE_PASSES)
            seq_times.append(time.perf_counter() - t0)
        sequential_time = min(seq_times)

        # ── Parallel execution ────────────────────────────────────────────────
        _AI_EMBEDDINGS = embeddings
        _AI_QUERY = query

        tracemalloc.start()
        cpu_before = psutil.cpu_percent(interval=None)

        par_times = []
        final_top_indices = None
        for _ in range(iterations):
            t0 = time.perf_counter()
            final_top_indices = self._parallel_inference(n, worker_count)
            par_times.append(time.perf_counter() - t0)

        cpu_after = psutil.cpu_percent(interval=0.1)
        mem_after = psutil.virtual_memory().percent
        _, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        _AI_EMBEDDINGS = None
        _AI_QUERY = None

        parallel_time = min(par_times)

        result = WorkloadResult(
            workload_type="ai_inference",
            input_size=input_size,
            worker_count=worker_count,
            iterations=iterations,
            execution_time=round(parallel_time, 6),
            sequential_time=round(sequential_time, 6),
            cpu_usage=round((cpu_before + cpu_after) / 2, 2),
            memory_usage=round(mem_after, 2),
            peak_memory_mb=round(peak_mem / 1024 / 1024, 3),
            extra={
                "corpus_size": n,
                "embedding_dim": _EMBEDDING_DIM,
                "feature_passes": _N_FEATURE_PASSES,
                "top_k_candidates": _TOP_K_CANDIDATES,
                "top_k_rerank": _TOP_K_RERANK,
                "top_result_index": int(final_top_indices[0]) if final_top_indices is not None and len(final_top_indices) > 0 else -1,
                "pipeline_stages": ["embedding_generation", "feature_enrichment", "vector_similarity_search", "reranking"],
            },
        )
        result.compute_derived()
        return result

    @staticmethod
    def _parallel_inference(n: int, n_workers: int) -> np.ndarray:
        """
        Distribute the enrichment + similarity search across workers, then merge and rerank.
        """
        chunk_size = max(1, n // n_workers)
        tasks = []
        for i in range(0, n, chunk_size):
            end = min(i + chunk_size, n)
            tasks.append((i, end, _TOP_K_CANDIDATES, _N_FEATURE_PASSES))

        actual_workers = min(n_workers, len(tasks))

        if actual_workers == 1:
            idx_b, sc_b = _ai_worker(tasks[0])
            all_indices = np.frombuffer(idx_b, dtype=np.int32).copy()
            all_scores = np.frombuffer(sc_b, dtype=np.float32).copy()
        else:
            ctx = get_mp_context()
            with ctx.Pool(processes=actual_workers) as pool:
                results = pool.map(_ai_worker, tasks)

            parts_idx = [np.frombuffer(r[0], dtype=np.int32) for r in results]
            parts_sc = [np.frombuffer(r[1], dtype=np.float32) for r in results]
            all_indices = np.concatenate(parts_idx)
            all_scores = np.concatenate(parts_sc)

        # Final global top-50 selection
        total = all_scores.shape[0]
        k_final = min(_TOP_K_CANDIDATES, total)
        top_global = np.argpartition(all_scores, -k_final)[-k_final:]
        top_indices = all_indices[top_global]
        top_scores = all_scores[top_global]

        # Stage 4 – Reranking (parent process; operates on the top-K candidates only)
        # Enrich only the top-K candidates — fast (50 × D × N_PASSES, not N × D × N_PASSES)
        top_k_enriched = _enrich_features(_AI_EMBEDDINGS[top_indices], _N_FEATURE_PASSES)
        rerank_scores = np.empty(k_final, dtype=np.float32)
        for rank_i in range(k_final):
            emb = top_k_enriched[rank_i]
            dot_sc = float(top_scores[rank_i])
            rerank_scores[rank_i] = dot_sc + 0.15 * float(np.sum(np.abs(emb - _AI_QUERY))) * -1.0

        order = np.argsort(rerank_scores)[::-1]
        ranked_indices = top_indices[order]

        # Stage 5 – Response assembly: weighted sum of top-10 enriched embeddings
        top10 = ranked_indices[:min(_TOP_K_RERANK, len(ranked_indices))]
        top10_scores = rerank_scores[order[:len(top10)]]
        weights = top10_scores - top10_scores.min() + 1e-6
        weights /= weights.sum()
        top10_embs = _enrich_features(_AI_EMBEDDINGS[top10], _N_FEATURE_PASSES)
        _response_vec = (top10_embs * weights[:, None]).sum(axis=0)  # noqa: F841

        return ranked_indices
