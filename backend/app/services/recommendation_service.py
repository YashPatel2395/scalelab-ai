"""
RecommendationService
─────────────────────
Combines the ScalabilityAgent and historical data to recommend the
optimal worker count for a given (workload_type, input_size) pair.

Uses the same curve-fitting approach as ScalabilityAgent but focuses
on finding the "knee" of the efficiency curve — the point beyond which
adding more workers yields < 10% relative speedup improvement.
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.benchmark import BenchmarkRun
from app.ai.scalability_agent import predict_scalability

logger = logging.getLogger(__name__)

_CANDIDATE_WORKERS = [1, 2, 4, 6, 8, 12, 16, 24, 32]


class RecommendationService:
    def __init__(self, db: Session):
        self.db = db

    def recommend(
        self,
        workload_type: str,
        input_size: int,
        available_workers: int = 32,
    ) -> dict[str, Any]:
        data_points = self._fetch_data_points(workload_type, input_size)

        candidates = [w for w in _CANDIDATE_WORKERS if w <= available_workers]
        if not candidates:
            candidates = [available_workers]

        prediction = predict_scalability(data_points, candidates)

        predictions = prediction.get("predictions", [])
        if not predictions:
            return {
                "workload_type": workload_type,
                "input_size": input_size,
                "optimal_worker_count": 1,
                "expected_speedup": 1.0,
                "expected_efficiency": 1.0,
                "reasoning": "No data available for this workload configuration.",
                "alternative_counts": [],
                "data_points_used": 0,
            }

        # Find the efficiency "knee": largest worker count where
        # marginal speedup per added worker is still >= 10%
        best = self._find_knee(predictions)
        alt = [
            {
                "workers": p["worker_count"],
                "speedup": p["predicted_speedup"],
                "efficiency": p["predicted_efficiency"],
            }
            for p in predictions
            if p["worker_count"] != best["worker_count"]
        ]

        reasoning = self._build_reasoning(best, predictions, prediction)

        return {
            "workload_type": workload_type,
            "input_size": input_size,
            "optimal_worker_count": best["worker_count"],
            "expected_speedup": best["predicted_speedup"],
            "expected_efficiency": best["predicted_efficiency"],
            "reasoning": reasoning,
            "alternative_counts": alt,
            "data_points_used": prediction.get("data_points_used", 0),
        }

    def _fetch_data_points(
        self, workload_type: str, input_size: int
    ) -> list[dict[str, Any]]:
        runs = (
            self.db.query(BenchmarkRun)
            .filter(
                BenchmarkRun.workload_type == workload_type,
                BenchmarkRun.input_size == input_size,
                BenchmarkRun.status == "completed",
                BenchmarkRun.speedup != None,  # noqa: E711
            )
            .all()
        )

        # If not enough data for exact input_size, broaden to same workload_type
        if len(runs) < 3:
            broader = (
                self.db.query(BenchmarkRun)
                .filter(
                    BenchmarkRun.workload_type == workload_type,
                    BenchmarkRun.status == "completed",
                    BenchmarkRun.speedup != None,  # noqa: E711
                )
                .all()
            )
            runs = broader

        return [
            {"worker_count": r.worker_count, "speedup": r.speedup}
            for r in runs
            if r.speedup and r.speedup > 0
        ]

    @staticmethod
    def _find_knee(predictions: list[dict]) -> dict:
        """
        Walk predictions sorted by worker count.
        Return the last point where marginal speedup is >= 10% of previous.
        Falls back to the point with highest efficiency.
        """
        sorted_p = sorted(predictions, key=lambda x: x["worker_count"])
        best = sorted_p[0]
        for i in range(1, len(sorted_p)):
            prev_s = sorted_p[i - 1]["predicted_speedup"]
            curr_s = sorted_p[i]["predicted_speedup"]
            marginal_gain = (curr_s - prev_s) / max(prev_s, 1e-9)
            if marginal_gain >= 0.10:
                best = sorted_p[i]
            else:
                break   # diminishing returns threshold crossed
        return best

    @staticmethod
    def _build_reasoning(
        best: dict,
        all_predictions: list[dict],
        prediction: dict,
    ) -> str:
        model = prediction.get("model_used", "unknown")
        r2 = prediction.get("r_squared")
        p_frac = prediction.get("parallel_fraction")
        theo_max = prediction.get("theoretical_max_speedup")

        lines = [
            f"Optimal worker count: {best['worker_count']} "
            f"(predicted {best['predicted_speedup']:.2f}× speedup, "
            f"{best['predicted_efficiency'] * 100:.1f}% efficiency)."
        ]

        if model == "amdahl" and p_frac is not None:
            lines.append(
                f"Fitted Amdahl model (p={p_frac:.1%}, R²={r2:.2f}). "
                f"Theoretical maximum speedup: {theo_max or '∞'}×."
            )
        elif model == "gustafson":
            alpha = prediction.get("serial_overhead")
            lines.append(
                f"Gustafson's Law fit (α={alpha:.2f}, R²={r2:.2f}). "
                "Workload scales well with problem size."
            )
        elif model == "insufficient_data":
            lines.append(
                "Recommendation is based on limited data. Run more benchmarks for accuracy."
            )

        # Warn if efficiency drops sharply beyond recommendation
        recommended_w = best["worker_count"]
        higher = [p for p in all_predictions if p["worker_count"] > recommended_w]
        if higher and higher[0]["predicted_efficiency"] < 0.5:
            lines.append(
                f"Efficiency drops to {higher[0]['predicted_efficiency']*100:.0f}% "
                f"at {higher[0]['worker_count']} workers — over-provisioning not recommended."
            )

        return " ".join(lines)
