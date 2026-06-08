"""
mpi_runner.py
─────────────
MPIWorkloadRunner: launches mpi_matrix_multiply.py via subprocess and
returns timing breakdown (computation / communication / synchronisation).

Graceful fallback: if mpiexec is not in PATH the runner falls back to the
regular fork-based matrix multiplication workload so the rest of the
platform keeps working without an MPI install.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MPITimingBreakdown:
    n_processes: int
    matrix_size: int
    computation_time: float       # pure numpy.dot wall time (max across ranks)
    communication_time: float     # Scatter + Gather + Bcast wall time
    synchronization_time: float   # Barrier wall time
    total_time: float
    mpi_available: bool


_WORKER_SCRIPT = Path(__file__).parent / "mpi_matrix_multiply.py"


def _mpiexec_binary() -> str | None:
    """Return path to mpiexec/mpirun, or None if not found."""
    for name in ("mpiexec", "mpirun"):
        path = shutil.which(name)
        if path:
            return path
    return None


def run_mpi_benchmark(
    n_processes: int,
    matrix_size: int,
    timeout: int = 120,
) -> MPITimingBreakdown:
    """
    Run the MPI matrix-multiply script and return timing breakdown.

    Falls back to a single-process estimation if MPI is unavailable.
    """
    mpiexec = _mpiexec_binary()

    if not mpiexec:
        return _fallback_timing(n_processes, matrix_size)

    with tempfile.NamedTemporaryFile(
        suffix=".json", delete=False, mode="w"
    ) as tmp:
        output_path = tmp.name

    try:
        cmd = [
            mpiexec,
            "-n", str(n_processes),
            "--oversubscribe",          # allow >physical-core counts
            "python",
            str(_WORKER_SCRIPT),
            str(matrix_size),
            output_path,
        ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "OPENBLAS_NUM_THREADS": "1"},
        )

        if proc.returncode != 0:
            # MPI failed — fall back gracefully
            return _fallback_timing(n_processes, matrix_size)

        with open(output_path) as fh:
            data = json.load(fh)

        return MPITimingBreakdown(
            n_processes=data["n_processes"],
            matrix_size=data["matrix_size"],
            computation_time=data["computation_time"],
            communication_time=data["communication_time"],
            synchronization_time=data["synchronization_time"],
            total_time=data["total_time"],
            mpi_available=True,
        )

    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        return _fallback_timing(n_processes, matrix_size)

    finally:
        try:
            os.unlink(output_path)
        except OSError:
            pass


def _fallback_timing(n_processes: int, matrix_size: int) -> MPITimingBreakdown:
    """
    Estimate timing without MPI using numpy in the current process.
    Communication and synchronisation overhead are modelled analytically.
    """
    import numpy as np

    rng = np.random.default_rng(42)
    A = rng.random((matrix_size, matrix_size))
    B = rng.random((matrix_size, matrix_size))

    t0 = time.perf_counter()
    _ = np.dot(A, B)
    compute_time = time.perf_counter() - t0

    # Approximate communication cost:  O(N^2 / P) bytes × 2 (scatter+gather)
    bytes_transferred = (matrix_size * matrix_size * 8 * 2) / n_processes
    # Assume 10 GB/s effective bandwidth for shared-memory MPI
    comm_time = bytes_transferred / (10 * 1024 ** 3)
    sync_time = 0.0001 * n_processes   # small barrier overhead

    total = compute_time + comm_time + sync_time

    return MPITimingBreakdown(
        n_processes=n_processes,
        matrix_size=matrix_size,
        computation_time=round(compute_time, 6),
        communication_time=round(comm_time, 6),
        synchronization_time=round(sync_time, 6),
        total_time=round(total, 6),
        mpi_available=False,
        # NOTE: all timing values above are analytically estimated, not measured.
        # Install mpi4py and ensure mpiexec is in PATH for real MPI execution.
    )
