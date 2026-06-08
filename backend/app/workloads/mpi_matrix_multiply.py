"""
mpi_matrix_multiply.py
──────────────────────
Standalone MPI script.  Run via:
    mpiexec -n <P> python mpi_matrix_multiply.py <N> <output_json>

Each rank measures its own computation time (np.dot slab), communication
time (Scatter / Gather), and synchronisation time (Barrier), writes a JSON
file that MPIWorkloadRunner reads back.

Rank 0 is the coordinator:
  1. Generate N×N matrices A and B (seeded for reproducibility).
  2. Scatter row-slabs of A to all ranks (including itself).
  3. Broadcast full B to all ranks.
  4. Each rank: time the local np.dot.
  5. Gather partial results back to rank 0.
  6. Write timing JSON to output_json.
"""

import json
import sys
import time

import numpy as np

try:
    from mpi4py import MPI
except ImportError:
    print("mpi4py not installed", file=sys.stderr)
    sys.exit(1)

comm = MPI.COMM_WORLD
rank = comm.Get_rank()
size = comm.Get_size()


def main() -> None:
    if len(sys.argv) < 3:
        if rank == 0:
            print("Usage: mpi_matrix_multiply.py <N> <output_json>", file=sys.stderr)
        sys.exit(1)

    N = int(sys.argv[1])
    output_path = sys.argv[2]

    rng = np.random.default_rng(42)

    # ── Rank 0 generates data ──────────────────────────────────────────────
    if rank == 0:
        A = rng.random((N, N), dtype=np.float64)
        B = rng.random((N, N), dtype=np.float64)

        # Pad rows so A splits evenly across ranks
        pad_rows = (size - N % size) % size
        if pad_rows:
            A = np.vstack([A, np.zeros((pad_rows, N), dtype=np.float64)])

        rows_per_rank = A.shape[0] // size
        # Flatten for Scatter
        A_flat = A.reshape(-1).astype(np.float64)
    else:
        B = None
        A_flat = None
        rows_per_rank = None

    # ── Broadcast B and rows_per_rank ─────────────────────────────────────
    comm_start = time.perf_counter()
    B = comm.bcast(B, root=0)
    rows_per_rank = comm.bcast(rows_per_rank, root=0)
    bcast_time = time.perf_counter() - comm_start

    # ── Scatter A slabs ───────────────────────────────────────────────────
    local_A_flat = np.empty(rows_per_rank * (N if rank == 0 else B.shape[0]),
                            dtype=np.float64)
    scatter_start = time.perf_counter()
    comm.Scatter(
        A_flat if rank == 0 else None,
        local_A_flat,
        root=0,
    )
    scatter_time = time.perf_counter() - scatter_start

    local_A = local_A_flat.reshape(rows_per_rank, B.shape[0])

    # ── Barrier sync before compute ───────────────────────────────────────
    sync_start = time.perf_counter()
    comm.Barrier()
    sync_time_pre = time.perf_counter() - sync_start

    # ── Local computation ─────────────────────────────────────────────────
    compute_start = time.perf_counter()
    local_C = np.dot(local_A, B)
    compute_time = time.perf_counter() - compute_start

    # ── Barrier sync after compute ────────────────────────────────────────
    sync_start2 = time.perf_counter()
    comm.Barrier()
    sync_time_post = time.perf_counter() - sync_start2

    # ── Gather results ────────────────────────────────────────────────────
    gather_start = time.perf_counter()
    all_C_flat = None
    if rank == 0:
        all_C_flat = np.empty(rows_per_rank * size * B.shape[0], dtype=np.float64)
    comm.Gather(local_C.reshape(-1).astype(np.float64), all_C_flat, root=0)
    gather_time = time.perf_counter() - gather_start

    # ── Aggregate timings across all ranks (max latency = bottleneck) ─────
    local_times = np.array(
        [compute_time, scatter_time + gather_time + bcast_time, sync_time_pre + sync_time_post],
        dtype=np.float64,
    )
    all_times = None
    if rank == 0:
        all_times = np.empty((size, 3), dtype=np.float64)
    comm.Gather(local_times, all_times, root=0)

    if rank == 0:
        # Max across ranks gives the critical path for each phase
        max_compute = float(all_times[:, 0].max())
        max_comm = float(all_times[:, 1].max())
        max_sync = float(all_times[:, 2].max())
        total = max_compute + max_comm + max_sync

        result = {
            "n_processes": size,
            "matrix_size": N,
            "computation_time": round(max_compute, 6),
            "communication_time": round(max_comm, 6),
            "synchronization_time": round(max_sync, 6),
            "total_time": round(total, 6),
            "status": "ok",
        }
        with open(output_path, "w") as fh:
            json.dump(result, fh)


if __name__ == "__main__":
    main()
