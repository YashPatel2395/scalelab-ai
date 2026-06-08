# Profiling System — Architecture Documentation

## Overview

ScaleLab AI includes a two-tier profiling system:

1. **WorkloadProfiler** (`app/profiling/profiler.py`) — cProfile + tracemalloc wrapper for built-in workloads
2. **ProfilingService** (`app/services/profiling_service.py`) — service layer that orchestrates profiling, stores results, and generates SVG
3. **Flame Graph Generator** (`app/profiling/flame_graph.py`) — SVG visualization of hotspot data

## WorkloadProfiler

Profiles a single workload execution using two Python stdlib tools:

### cProfile
- Instruments every function call
- Records: call count, total time (cumulative), self time
- Output: sorted by cumulative time, top-N hotspots
- Label format: `filename:lineno(function_name)`

### tracemalloc
- Tracks memory allocations per line of source code
- Reports allocation diffs (before/after workload execution)
- Output: top-10 memory allocation sites by size delta

### ProfileResult Schema

```json
{
  "workload_type": "matrix_multiplication",
  "input_size": 512,
  "worker_count": 4,
  "total_time_ms": 1234.5,
  "total_calls": 50000,
  "peak_memory_mb": 128.3,
  "top_hotspots": [
    {
      "function": "/path/to/file.py:42(my_function)",
      "calls": 1000,
      "total_time_ms": 800.0,
      "self_time_ms": 200.0,
      "pct_of_total": 64.8
    }
  ],
  "memory_hotspots": [
    {
      "filename": "/path/to/file.py",
      "lineno": 15,
      "size_kb": 4096.0,
      "count": 1
    }
  ]
}
```

### Filtered Functions

The following cProfile entries are filtered out as internal Python plumbing:
- `<frozen` (frozen importlib modules)
- `importlib`
- `encodings`
- `threading.py`
- `cprofile`
- `pstats`
- `_collections_abc`

## ProfilingService

The service layer manages profiling for both built-in and custom workloads.

### Built-in Workloads

```
POST /api/profiling/{run_id}
```

1. Loads the `BenchmarkRun` record
2. Validates workload_type != "custom_python"
3. Runs `WorkloadProfiler.profile()` with same parameters
4. Stores `profiling_data` (JSON) in the run record
5. Generates SVG flame chart, stores in `flame_graph_svg`
6. Commits to database

### Custom Workloads

Custom workloads execute in subprocesses (security isolation). Profiling data is passed back via the subprocess result JSON and stored via `store_profile_data()`.

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/profiling/{run_id}` | Profile a built-in workload run |
| GET | `/api/profiling/{run_id}` | Get profiling JSON data |
| GET | `/api/profiling/{run_id}/flame-graph` | Get SVG flame chart |

## Flame Graph Generator

`generate_hotspot_svg()` generates a self-contained SVG bar chart (no external dependencies).

### Visual Design

- Dark background (`#0f172a`) for readability
- Warm color scale: yellow (cool) → orange → red (hot)
- Horizontal bars proportional to `pct_of_total`
- Columns: Function name, Call count, Total time (ms), Percentage
- Alternating row backgrounds for readability
- Truncated function labels (max 42 chars, ellipsis prefix)

### Color Formula

```python
r = int(205 + 50 * hotness)       # 205→255 (yellow→red)
g = int(220 * (1.0 - hotness * 0.8))  # 220→44
b = int(20 * (1.0 - hotness))     # 20→0
```

Where `hotness = pct / max_pct` normalizes relative to the hottest function.

### Label Shortening

For cProfile labels in format `file:lineno(func)`:
```
/path/to/mymodule.py:42(compute) → mymodule::compute
```

For paths without parentheses:
```
/path/to/mymodule.py → mymodule.py
```

Labels > 42 characters are truncated with a leading ellipsis (`…`).

### Number Formatting

| Range | Format |
|-------|--------|
| ≥ 1,000,000 | `1.5M` |
| ≥ 1,000 | `15K` |
| < 1,000 | `150` |

## Database Storage

New columns added to `benchmark_runs`:

| Column | Type | Description |
|--------|------|-------------|
| `profiling_data` | JSON | Full profiling result dict |
| `flame_graph_svg` | TEXT | Self-contained SVG string |

Both columns are nullable. A run without profiling data will have `null` for both.

## Integration with Diagnosis Engine

When `profiling_data` is present in a run, the Diagnosis Engine uses it to:
1. Append the hottest function to `cpu_bound` evidence
2. Generate a hotspot-specific optimization opportunity if the top function > 30% runtime
