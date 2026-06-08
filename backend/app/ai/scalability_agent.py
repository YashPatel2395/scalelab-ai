"""
ScalabilityAgent
────────────────
Fits Amdahl's Law and Gustafson's Law to historical benchmark data
using scipy.optimize.curve_fit.  Returns predictions for arbitrary
worker counts along with goodness-of-fit metrics.

Amdahl's Law:   S(P) = 1 / ((1 - p) + p/P)
Gustafson's Law: S(P) = P - α * (P - 1)    where α = serial fraction

Both models are fit to actual (worker_count, speedup) data points
collected from completed benchmark runs.  If fewer than 3 data points
exist the agent returns a graceful "insufficient data" response with
linear extrapolation from the single known point.
"""

import math
import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# ── Model functions ───────────────────────────────────────────────────────────

def _amdahl(P: np.ndarray, p: float) -> np.ndarray:
    """Amdahl speedup: S = 1 / ((1-p) + p/P)"""
    p = np.clip(p, 0.0, 0.9999)
    return 1.0 / ((1.0 - p) + p / P)


def _gustafson(P: np.ndarray, alpha: float) -> np.ndarray:
    """Gustafson speedup: S = P - alpha*(P-1)"""
    alpha = np.clip(alpha, 0.0, 1.0)
    return P - alpha * (P - 1.0)


def _r_squared(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot < 1e-10:
        return 1.0
    return float(1.0 - ss_res / ss_tot)


# ── Main agent ────────────────────────────────────────────────────────────────

def predict_scalability(
    data_points: list[dict[str, Any]],   # [{"worker_count": P, "speedup": S}]
    target_worker_counts: list[int],
) -> dict[str, Any]:
    """
    Fit scaling laws to historical data and return predictions.

    Parameters
    ----------
    data_points:
        List of dicts with 'worker_count' and 'speedup' from completed runs.
    target_worker_counts:
        Worker counts to predict speedup for.

    Returns
    -------
    dict matching ScalabilityPredictionResponse schema.
    """
    if not data_points:
        return _insufficient_data_response(target_worker_counts, data_points=0)

    # Deduplicate: for same worker_count, take median speedup
    bucket: dict[int, list[float]] = {}
    for dp in data_points:
        w = int(dp["worker_count"])
        s = float(dp["speedup"])
        bucket.setdefault(w, []).append(s)

    unique_workers = sorted(bucket.keys())
    unique_speedups = [float(np.median(bucket[w])) for w in unique_workers]

    P = np.array(unique_workers, dtype=np.float64)
    S = np.array(unique_speedups, dtype=np.float64)

    n = len(P)

    if n < 3:
        return _insufficient_data_response(target_worker_counts, data_points=n, P=P, S=S)

    # ── Fit Amdahl ────────────────────────────────────────────────────────────
    try:
        from scipy.optimize import curve_fit

        popt_a, _ = curve_fit(
            _amdahl, P, S,
            p0=[0.8],
            bounds=([0.0], [0.9999]),
            maxfev=2000,
        )
        p_amdahl = float(popt_a[0])
        s_amdahl_fit = _amdahl(P, p_amdahl)
        r2_amdahl = _r_squared(S, s_amdahl_fit)
    except Exception:
        p_amdahl = 0.8
        r2_amdahl = 0.0

    # ── Fit Gustafson ─────────────────────────────────────────────────────────
    try:
        popt_g, _ = curve_fit(
            _gustafson, P, S,
            p0=[0.2],
            bounds=([0.0], [1.0]),
            maxfev=2000,
        )
        alpha_gustafson = float(popt_g[0])
        s_gustafson_fit = _gustafson(P, alpha_gustafson)
        r2_gustafson = _r_squared(S, s_gustafson_fit)
    except Exception:
        alpha_gustafson = 0.2
        r2_gustafson = 0.0

    # ── Choose best model ─────────────────────────────────────────────────────
    if r2_amdahl >= r2_gustafson:
        model_used = "amdahl"
        r2 = r2_amdahl
    else:
        model_used = "gustafson"
        r2 = r2_gustafson

    # ── Generate predictions ──────────────────────────────────────────────────
    predictions = []
    for w in sorted(target_worker_counts):
        wp = float(w)
        if model_used == "amdahl":
            pred_s = float(_amdahl(np.array([wp]), p_amdahl)[0])
        else:
            pred_s = float(_gustafson(np.array([wp]), alpha_gustafson)[0])

        pred_e = pred_s / wp if wp > 0 else 1.0
        # Confidence scales with R² and number of data points
        confidence = min(1.0, r2 * (1.0 - 1.0 / max(n, 2)))

        predictions.append({
            "worker_count": w,
            "predicted_speedup": round(pred_s, 4),
            "predicted_efficiency": round(min(1.0, pred_e), 4),
            "confidence": round(confidence, 3),
        })

    # Theoretical max speedup (Amdahl ceiling)
    theo_max = round(1.0 / (1.0 - p_amdahl), 2) if p_amdahl < 1.0 else None

    # Recommendation text
    if r2 < 0.5:
        rec = (
            "Fit quality is low (R²={:.2f}). Collect more data points across "
            "different worker counts for reliable predictions.".format(r2)
        )
    elif model_used == "amdahl":
        rec = (
            "Amdahl's Law fits well (R²={:.2f}, p={:.1%}). "
            "Theoretical speedup ceiling ≈ {:.1f}×. "
            "{}".format(
                r2,
                p_amdahl,
                theo_max or float("inf"),
                "Scaling beyond 8 workers offers diminishing returns." if p_amdahl < 0.9 else
                "High parallel fraction — further scaling still beneficial.",
            )
        )
    else:
        rec = (
            "Gustafson's Law fits better (R²={:.2f}, α={:.2f}). "
            "Workload scales well with problem size — weak-scaling regime.".format(r2, alpha_gustafson)
        )

    return {
        "model_used": model_used,
        "parallel_fraction": round(p_amdahl, 4) if model_used == "amdahl" else None,
        "serial_overhead": round(alpha_gustafson, 4) if model_used == "gustafson" else None,
        "r_squared": round(r2, 4),
        "data_points_used": n,
        "predictions": predictions,
        "theoretical_max_speedup": theo_max,
        "recommendation": rec,
    }


def _insufficient_data_response(
    target_worker_counts: list[int],
    data_points: int = 0,
    P: np.ndarray | None = None,
    S: np.ndarray | None = None,
) -> dict[str, Any]:
    predictions = []
    for w in sorted(target_worker_counts):
        if P is not None and len(P) == 1:
            # Linear extrapolation from one point
            known_speedup = float(S[0])
            known_workers = float(P[0])
            pred_s = known_speedup * (w / known_workers)
        else:
            pred_s = float(w)  # optimistic linear assumption
        pred_e = pred_s / w if w > 0 else 1.0
        predictions.append({
            "worker_count": w,
            "predicted_speedup": round(pred_s, 4),
            "predicted_efficiency": round(min(1.0, pred_e), 4),
            "confidence": 0.1,
        })
    return {
        "model_used": "insufficient_data",
        "parallel_fraction": None,
        "serial_overhead": None,
        "r_squared": None,
        "data_points_used": data_points,
        "predictions": predictions,
        "theoretical_max_speedup": None,
        "recommendation": (
            f"Only {data_points} data point(s) available. Run benchmarks with at "
            "least 3 different worker counts (e.g. 1, 2, 4) to enable curve fitting."
        ),
    }
