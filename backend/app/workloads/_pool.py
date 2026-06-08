"""
Shared multiprocessing context helper.

On macOS/Linux, 'fork' starts processes in ~5ms vs 'spawn' at ~500ms.
This is safe for our use case because workload workers are pure functions
with no shared state and no thread synchronization.

On Windows, 'spawn' is always used because fork is unavailable.
"""

import multiprocessing
import platform
import sys


def get_mp_context():
    """Return the fastest available multiprocessing context."""
    system = platform.system()
    if system == "Windows":
        return multiprocessing.get_context("spawn")
    # macOS and Linux – use fork for minimal overhead
    return multiprocessing.get_context("fork")
