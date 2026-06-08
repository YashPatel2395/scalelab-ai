"""
Graph BFS Traversal
────────────────────
Graph model: Erdős–Rényi random graph G(N, p) with p = 10/N (sparse, ~10 edges/node avg).

Sequential baseline: Standard FIFO queue BFS from node 0.

Parallel implementation: Level-Synchronous BFS (LS-BFS).
  Each BFS level (frontier) is expanded in parallel.
  Workers receive a partition of the frontier nodes and their adjacency slices.
  Results are merged to form the next frontier.

Parallelism mechanism:
  Uses multiprocessing.Pool with 'fork' on Unix/macOS.
  Workers inherit the full adjacency list from the parent.
  Only (start_idx, end_idx) index ranges are sent per task.

Honest limitations (documented per spec):
  - BFS is bounded by graph diameter O(log N) for Erdős–Rényi graphs.
  - Parallelism helps only on wide frontiers (dense or social graphs).
  - For sparse graphs, frontier width often limits parallel efficiency.
  - Real distributed BFS (Pregel, GraphX) uses partition-aware message passing;
    this simulates the pattern to demonstrate the concept clearly.
"""

import time
import tracemalloc
from collections import deque

import numpy as np
import psutil

from app.workloads.base import BaseWorkload, WorkloadResult
from app.workloads._pool import get_mp_context

# ─── Module-level shared state ────────────────────────────────────────────────
_ADJ: list[list[int]] | None = None


def _build_adjacency_list(n_nodes: int, seed: int = 42) -> list[list[int]]:
    """Build an Erdős–Rényi adjacency list. p ≈ 10/N for sparse connectivity."""
    rng = np.random.default_rng(seed)
    p = min(10.0 / max(n_nodes, 1), 0.05)
    adj: list[list[int]] = [[] for _ in range(n_nodes)]
    for u in range(n_nodes):
        neighbors = np.where(rng.random(n_nodes) < p)[0]
        for v in neighbors.tolist():
            if v != u:
                adj[u].append(v)
                adj[v].append(u)
    for u in range(n_nodes):
        adj[u] = list(set(adj[u]))
    return adj


def _sequential_bfs(adj: list[list[int]], source: int) -> dict[int, int]:
    """Standard BFS. Returns {node: depth} for all reachable nodes."""
    dist: dict[int, int] = {source: 0}
    queue = deque([source])
    while queue:
        u = queue.popleft()
        d = dist[u]
        for v in adj[u]:
            if v not in dist:
                dist[v] = d + 1
                queue.append(v)
    return dist


def _expand_frontier_partition(args: tuple) -> list[int]:
    """
    Worker: expand a partition of the current frontier.
    _ADJ is inherited via fork – no copy needed for the adjacency list.
    Returns flat list of discovered neighbor IDs.
    """
    node_partition = args  # list of node IDs to expand
    neighbors = []
    for u in node_partition:
        neighbors.extend(_ADJ[u])
    return neighbors


def _parallel_bfs(
    n_nodes: int, source: int, n_workers: int
) -> dict[int, int]:
    """Level-Synchronous BFS with parallel frontier expansion."""
    dist: dict[int, int] = {source: 0}
    frontier = [source]
    depth = 0

    while frontier:
        depth += 1
        chunk_size = max(1, len(frontier) // n_workers)
        partitions = [
            frontier[i : i + chunk_size]
            for i in range(0, len(frontier), chunk_size)
        ]
        actual = min(n_workers, len(partitions))

        if actual == 1 or len(frontier) < 32:
            all_neighbors: list[int] = []
            for p in partitions:
                all_neighbors.extend(_expand_frontier_partition(p))
        else:
            ctx = get_mp_context()
            with ctx.Pool(processes=actual) as pool:
                results = pool.map(_expand_frontier_partition, partitions)
            all_neighbors = [n for batch in results for n in batch]

        next_frontier = []
        for v in all_neighbors:
            if v not in dist:
                dist[v] = depth
                next_frontier.append(v)
        frontier = list(set(next_frontier))

    return dist


# ─── Workload ─────────────────────────────────────────────────────────────────


class GraphBFSWorkload(BaseWorkload):
    """
    input_size = N  →  BFS on a random graph with N nodes.
    """

    def run(self, input_size: int, worker_count: int, iterations: int) -> WorkloadResult:
        global _ADJ
        n = input_size
        _ADJ = _build_adjacency_list(n)
        total_edges = sum(len(nb) for nb in _ADJ) // 2

        # ── Sequential baseline ──────────────────────────────────────────────
        seq_times = []
        seq_result = {}
        for _ in range(iterations):
            t0 = time.perf_counter()
            seq_result = _sequential_bfs(_ADJ, source=0)
            seq_times.append(time.perf_counter() - t0)
        sequential_time = min(seq_times)

        # ── Parallel BFS ─────────────────────────────────────────────────────
        tracemalloc.start()
        cpu_before = psutil.cpu_percent(interval=None)

        par_times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            _parallel_bfs(n, source=0, n_workers=worker_count)
            par_times.append(time.perf_counter() - t0)

        cpu_after = psutil.cpu_percent(interval=0.1)
        mem_after = psutil.virtual_memory().percent
        _, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        _ADJ = None
        parallel_time = min(par_times)
        reachable = len(seq_result)

        import math
        result = WorkloadResult(
            workload_type="graph_bfs",
            input_size=input_size,
            worker_count=worker_count,
            iterations=iterations,
            execution_time=round(parallel_time, 6),
            sequential_time=round(sequential_time, 6),
            cpu_usage=round((cpu_before + cpu_after) / 2, 2),
            memory_usage=round(mem_after, 2),
            peak_memory_mb=round(peak_mem / 1024 / 1024, 3),
            extra={
                "nodes": n,
                "edges": total_edges,
                "reachable_from_source": reachable,
                "avg_degree": round(total_edges * 2 / max(n, 1), 2),
                "estimated_diameter": math.ceil(math.log2(max(n, 2))),
                "parallelism_note": (
                    "Level-synchronous BFS; speedup limited by graph diameter and frontier width. "
                    "Sparse Erdős–Rényi graphs have O(log N) diameter – frontier size peaks at mid-BFS."
                ),
            },
        )
        result.compute_derived()
        return result
