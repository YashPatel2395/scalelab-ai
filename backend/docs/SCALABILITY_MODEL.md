# Scalability Model — Mathematical Reference

## Overview

ScaleLab AI uses two classical parallel scaling models to predict performance at untested worker counts and grade workload scalability.

## Amdahl's Law

**Formula:**
```
S(P) = 1 / ((1 - p) + p/P)
```

Where:
- `S(P)` = speedup with P workers
- `p` = parallel fraction (0 to 1)
- `P` = number of parallel workers
- `(1 - p)` = serial fraction

**Theoretical Maximum Speedup:**
```
S_max = lim(P→∞) S(P) = 1 / (1 - p)
```

**Serial Fraction Inversion (from measured speedup):**
```
Given measured speedup S at P workers:
p_par = ((1/S) - 1) / ((1/P) - 1)
serial_fraction = 1 - p_par
```

**Amdahl Efficiency:**
```
E(P) = S(P) / P = 1 / (P*(1-p) + p)
```

**Maximum Useful Workers (50% efficiency threshold):**
```
E(P) = 0.50  →  P_max = (1/0.50 - p) / (1 - p) = (2 - p) / (1 - p)
```

## Gustafson's Law

**Formula:**
```
S(P) = P - α*(P - 1)
```

Where:
- `α` = serial overhead fraction
- `P` = number of parallel workers

**Characteristics:**
- Models weak-scaling (problem size grows with P)
- No hard ceiling — speedup grows linearly with P
- Appropriate when workload scales with available resources

## Model Selection

Both models are fit using `scipy.optimize.curve_fit`. The model with higher R² is selected:

```python
if r2_amdahl >= r2_gustafson:
    model_used = "amdahl"
else:
    model_used = "gustafson"
```

**R² Goodness-of-Fit:**
```
R² = 1 - SS_res / SS_tot
SS_res = Σ(y_true - y_pred)²
SS_tot = Σ(y_true - mean(y_true))²
```

## Certification Grade Criteria

Grades are awarded based on the Amdahl parallel fraction and peak observed efficiency:

| Grade | Condition |
|-------|-----------|
| A+ | parallel_fraction ≥ 0.95 AND best_efficiency ≥ 80% |
| A  | parallel_fraction ≥ 0.90 OR best_efficiency ≥ 75% |
| B  | parallel_fraction ≥ 0.80 OR best_efficiency ≥ 60% |
| C  | parallel_fraction ≥ 0.65 OR best_efficiency ≥ 45% |
| D  | best_efficiency ≥ 25% |
| F  | best_efficiency < 25% OR speedup degraded at 2+ worker counts |

**Speedup Degradation:** Speedup is considered degraded if it decreases at 2 or more consecutive worker count steps (negative scaling).

## Confidence Score for Predictions

```
prediction_confidence = min(1.0, R² * (1 - 1/max(n, 2)))
```

Where `n` is the number of unique data points used for fitting. Confidence grows with both R² and number of data points.

## Efficiency Metrics

```
speedup = sequential_time / parallel_time
efficiency = (speedup / worker_count) * 100  (percent)
```

**Single-Worker Normalization:**
When `worker_count == 1` and measured `speedup > 1.1`, speedup is clamped to 1.0. This corrects for warm-cache artifacts where the baseline and parallel run share the same process.

## Optimal Worker Count Algorithm

The optimal worker count is found by iterating predictions and stopping when the marginal speedup gain drops below 8%:

```python
marginal_gain = (speedup_at_P - speedup_at_P_prev) / speedup_at_P_prev
if marginal_gain < 0.08:
    stop
```
