# Diagnosis Engine — Technical Documentation

## Overview

The Diagnosis Engine (`app/diagnosis/engine.py`) implements a Stage 1 algorithmic bottleneck classifier that operates entirely on measured benchmark metrics — no LLM required.

It classifies workload bottlenecks into nine categories, computing a confidence score from measured data and emitting structured evidence for each classification.

## Architecture

### Input

```python
diagnose(
    workload_type: str,      # e.g. "matrix_multiplication"
    input_size: int,         # problem size N
    worker_count: int,       # number of parallel workers P
    execution_time: float,   # parallel wall-clock time (seconds)
    sequential_time: float,  # single-worker time (seconds)
    speedup: float,          # sequential_time / execution_time
    efficiency: float,       # speedup / worker_count * 100 (percent)
    cpu_usage: float | None, # average CPU utilization (percent)
    memory_usage: float | None,    # average memory utilization (percent)
    peak_memory_mb: float | None,  # peak RSS (MB)
    observability_data: dict | None,  # from ResourceSampler
    profiling_data: dict | None,      # from WorkloadProfiler
)
```

### Output

Returns a `DiagnosisResult` dataclass with:

- `primary`: Name of the dominant bottleneck
- `confidence`: Float [0.40, 0.99] representing diagnostic certainty
- `evidence`: List of `EvidenceItem(metric, value)` supporting the classification
- `secondary`: Optional co-bottleneck name (if score > 0.15 and gap < 20pp)
- `secondary_confidence`: Confidence for secondary bottleneck
- `all_scores`: Dict mapping all 9 classifier names to their scores [0,1]
- `optimization_opportunities`: List of actionable recommendations (up to 4)
- `expected_improvement_pct`: Conservative estimate of improvement if bottleneck eliminated
- `risk_assessment`: HIGH / MEDIUM / LOW risk string
- `executive_summary`: Human-readable summary paragraph

## Nine Bottleneck Classifiers

### 1. `cpu_bound`

**Signals:**
- CPU utilization > 90% → +0.70 score
- CPU utilization > 75% → +0.45 score
- CPU utilization > 55% → +0.20 score
- High efficiency (≥70%) + CPU ≥ 60% → +0.15 (confirms saturation)
- CPU ≥ 80% but efficiency < 40% → -0.10 (another factor limits efficiency)

**Interpretation:** Workload is consuming all available CPU cycles. Adding more workers or using vectorized operations will help.

### 2. `memory_bound`

**Signals:**
- Memory utilization > 85% → +0.70 score
- Memory utilization > 75% → +0.50 score
- Memory utilization > 60% → +0.25 score
- Negative scaling (speedup < 1) + memory ≥ 60% → +0.25
- High memory + low CPU + low efficiency → +0.20 (bandwidth saturation)

**Interpretation:** Memory bandwidth or capacity is the limiting resource.

### 3. `synchronization_bound`

**Signals:**
- Serial fraction (Amdahl inversion) ≥ 40% → +0.65
- Serial fraction ≥ 25% → +0.40
- Serial fraction ≥ 15% → +0.20
- CPU < 35% + efficiency < 40% + workers > 1 → +0.30 (workers stalling at barriers)

**Serial Fraction Formula (Amdahl Inversion):**
```
Given speedup S and worker count P:
p_par = ((1/S) - 1) / ((1/P) - 1)
serial_fraction = 1 - p_par
```

### 4. `communication_bound`

**Signals (with observability data):**
- Network I/O rate > 50 MB/s → +0.65
- Network I/O rate > 20 MB/s → +0.40
- Network I/O rate > 5 MB/s → +0.15
- Disk I/O rate > 100 MB/s → +0.20 (bonus)

**Signals (without observability):**
- Workers ≥ 4 + efficiency < 30% → +0.20 (inferred IPC cost)

### 5. `load_imbalance`

**Signals:**
- Per-core CPU variance ≥ 30pp → +0.60
- Per-core CPU variance ≥ 20pp → +0.40
- Per-core CPU variance ≥ 10pp → +0.20
- Workers ≥ 4 + efficiency < 50% → +0.15
- All cores ≥ 60% utilized → -0.20 (penalty: imbalance unlikely if all cores busy)

### 6. `ipc_overhead`

**Signals:**
- Workers ≥ 4 + speedup < 0.5×workers → +0.35
- Workers ≥ 8 + speedup < 0.3×workers → +0.25
- CPU < 40% + workers ≥ 4 → +0.25
- Negative scaling + workers > 2 → +0.25

### 7. `worker_oversubscription`

**Signals:**
- Oversubscription ratio ≥ 2× → +0.65
- Oversubscription ratio ≥ 1.5× → +0.45
- Oversubscription ratio > 1× → +0.25
- Efficiency < 50% when oversubscribed → +0.15

Uses `psutil.cpu_count(logical=True)` to determine the machine's logical CPU count.

### 8. `serialization_bottleneck`

**Signals:**
- Custom Python workload → +0.20 (base: pickle overhead likely)
- Workers ≥ 4 + input_size < 10,000 → +0.25 (small input amortization failure)
- Efficiency < 15% + workers ≥ 4 → +0.25
- Speedup < 0.5 + workers ≥ 2 → +0.20
- Non-custom workload + workers < 4 → score = 0.0 (suppressed)

### 9. `io_bound`

**Signals (requires observability data):**
- Disk I/O rate > 100 MB/s → +0.75
- Disk I/O rate > 50 MB/s → +0.50
- Disk I/O rate > 20 MB/s → +0.30
- CPU < 30% + disk rate > 20 MB/s → +0.15 (waiting on I/O)

## Confidence Calculation

```
confidence = primary_score / sum(top3_scores)
confidence = clamp(confidence, 0.40, 0.99)
```

This normalizes the primary score against competition from the top 3 classifiers. High confidence (>0.80) means one bottleneck clearly dominates.

## Secondary Bottleneck Detection

A secondary bottleneck is reported when:
1. The second-highest classifier score > 0.15
2. AND (gap between primary and secondary < 0.20pp OR secondary score > 0.35)

Secondary confidence is clamped to [0.10, 0.60] to reflect uncertainty.

## Profiling Data Integration

When `profiling_data` (from `WorkloadProfiler`) is provided:
- The hottest function (by cumulative time %) is appended to `cpu_bound` evidence
- If top hotspot > 30% runtime, an additional optimization opportunity is generated

## Expected Improvement Estimation

```
efficiency_gap = max(0, 100 - efficiency)
improvement = efficiency_gap * factor

Factors by bottleneck:
  io_bound:                0.75
  ipc_overhead:            0.70
  load_imbalance:          0.65
  cpu_bound:               0.60
  serialization_bottleneck: 0.60
  synchronization_bound:   0.55
  memory_bound:            0.50
  communication_bound:     0.50
  worker_oversubscription: 0.45
```

## Risk Assessment

| Condition | Risk Level |
|-----------|------------|
| confidence > 0.80 AND efficiency < 30% | HIGH |
| confidence > 0.65 AND efficiency < 60% | MEDIUM |
| efficiency >= 75% | LOW |
| Otherwise | MEDIUM |
