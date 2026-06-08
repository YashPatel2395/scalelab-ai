"""Tests for Scalability Certification Service — grade formula and report structure."""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from app.services.certification_service import (
    CertificationService,
    _grade,
    _optimal_worker_count,
    _max_useful_workers,
    _grade_description,
)


# ── Grade formula tests ───────────────────────────────────────────────────────

class TestGradeFormula:
    def test_a_plus_requires_high_pf_and_efficiency(self):
        grade, _ = _grade(parallel_fraction=0.97, best_efficiency=85.0, speedup_degraded=False)
        assert grade == "A+"

    def test_a_high_pf(self):
        grade, _ = _grade(parallel_fraction=0.92, best_efficiency=70.0, speedup_degraded=False)
        assert grade == "A"

    def test_a_high_efficiency(self):
        grade, _ = _grade(parallel_fraction=0.70, best_efficiency=76.0, speedup_degraded=False)
        assert grade == "A"

    def test_b_moderate_pf(self):
        grade, _ = _grade(parallel_fraction=0.82, best_efficiency=55.0, speedup_degraded=False)
        assert grade == "B"

    def test_b_good_efficiency(self):
        grade, _ = _grade(parallel_fraction=0.60, best_efficiency=61.0, speedup_degraded=False)
        assert grade == "B"

    def test_c_fair(self):
        grade, _ = _grade(parallel_fraction=0.67, best_efficiency=42.0, speedup_degraded=False)
        assert grade == "C"

    def test_d_poor(self):
        grade, _ = _grade(parallel_fraction=0.40, best_efficiency=28.0, speedup_degraded=False)
        assert grade == "D"

    def test_f_failing_efficiency(self):
        grade, _ = _grade(parallel_fraction=0.20, best_efficiency=15.0, speedup_degraded=False)
        assert grade == "F"

    def test_f_speedup_degraded_overrides(self):
        # Even if efficiency is good, speedup degradation → F
        grade, rationale = _grade(parallel_fraction=0.90, best_efficiency=80.0, speedup_degraded=True)
        assert grade == "F"
        assert "degraded" in rationale.lower() or "negative" in rationale.lower()

    def test_rationale_is_nonempty_string(self):
        for pf in [0.97, 0.91, 0.82, 0.67, 0.40, 0.20]:
            grade, rationale = _grade(parallel_fraction=pf, best_efficiency=50.0, speedup_degraded=False)
            assert isinstance(rationale, str)
            assert len(rationale) > 10

    def test_none_parallel_fraction_handled(self):
        grade, _ = _grade(parallel_fraction=None, best_efficiency=55.0, speedup_degraded=False)
        assert grade in ("B", "C", "D", "F", "A", "A+")


# ── Optimal worker count ──────────────────────────────────────────────────────

class TestOptimalWorkerCount:
    def test_returns_int(self):
        fit_result = {
            "predictions": [
                {"worker_count": 1, "predicted_speedup": 1.0},
                {"worker_count": 2, "predicted_speedup": 1.85},
                {"worker_count": 4, "predicted_speedup": 3.2},
                {"worker_count": 8, "predicted_speedup": 4.5},
                {"worker_count": 16, "predicted_speedup": 4.8},
            ]
        }
        result = _optimal_worker_count(fit_result, [1, 2, 4, 8, 16])
        assert isinstance(result, int)

    def test_empty_predictions_returns_last_worker_count(self):
        result = _optimal_worker_count({"predictions": []}, [1, 2, 4, 8])
        assert result == 8

    def test_optimal_not_beyond_diminishing_returns(self):
        fit_result = {
            "predictions": [
                {"worker_count": 1, "predicted_speedup": 1.0},
                {"worker_count": 2, "predicted_speedup": 1.85},
                {"worker_count": 4, "predicted_speedup": 3.2},
                {"worker_count": 8, "predicted_speedup": 3.5},   # marginal gain < 8%
                {"worker_count": 16, "predicted_speedup": 3.6},
            ]
        }
        result = _optimal_worker_count(fit_result, [1, 2, 4, 8, 16])
        assert result <= 8


# ── Max useful workers ────────────────────────────────────────────────────────

class TestMaxUsefulWorkers:
    def test_none_parallel_fraction_returns_none(self):
        assert _max_useful_workers(None) is None

    def test_fully_parallel_returns_none(self):
        # 100% parallel → scales forever
        result = _max_useful_workers(1.0)
        assert result is None

    def test_50_percent_parallel_is_bounded(self):
        result = _max_useful_workers(0.50, efficiency_threshold=0.50)
        assert isinstance(result, int)
        assert result >= 1

    def test_zero_parallel_returns_one(self):
        result = _max_useful_workers(0.0)
        assert result == 1

    def test_high_parallel_fraction_gives_more_workers(self):
        low = _max_useful_workers(0.70)
        high = _max_useful_workers(0.95)
        assert (high is None) or (high > low)


# ── Grade descriptions ────────────────────────────────────────────────────────

class TestGradeDescriptions:
    def test_all_grades_have_description(self):
        for grade in ("A+", "A", "B", "C", "D", "F"):
            desc = _grade_description(grade)
            assert isinstance(desc, str)
            assert len(desc) > 10

    def test_unknown_grade_returns_string(self):
        desc = _grade_description("Z")
        assert isinstance(desc, str)


# ── CertificationService.generate() ──────────────────────────────────────────

def _make_mock_run(
    id_="run1",
    worker_count=4,
    speedup=3.6,
    efficiency=90.0,
    execution_time=0.5,
    sequential_time=1.8,
    workload_type="matrix_multiplication",
    input_size=10000,
    status="completed",
    cpu_usage=85.0,
    memory_usage=40.0,
    peak_memory_mb=200.0,
    workload_name=None,
    observability_data=None,
    created_at=None,
):
    run = MagicMock()
    run.id = id_
    run.worker_count = worker_count
    run.speedup = speedup
    run.efficiency = efficiency
    run.execution_time = execution_time
    run.sequential_time = sequential_time
    run.workload_type = workload_type
    run.input_size = input_size
    run.status = status
    run.cpu_usage = cpu_usage
    run.memory_usage = memory_usage
    run.peak_memory_mb = peak_memory_mb
    run.workload_name = workload_name
    run.observability_data = observability_data
    run.created_at = created_at or datetime(2024, 1, 1, 12, 0, 0)
    return run


class TestCertificationServiceGenerate:
    def _make_svc(self, runs):
        db = MagicMock()
        query_chain = MagicMock()
        query_chain.all.return_value = runs
        db.query.return_value.filter.return_value.filter.return_value = query_chain
        return CertificationService(db)

    def test_raises_on_empty_runs(self):
        svc = self._make_svc([])
        with pytest.raises(ValueError, match="No completed"):
            svc.generate(["nonexistent"])

    def test_report_has_required_keys(self):
        runs = [
            _make_mock_run("r1", worker_count=1, speedup=1.0, efficiency=100.0),
            _make_mock_run("r2", worker_count=2, speedup=1.85, efficiency=92.5),
            _make_mock_run("r3", worker_count=4, speedup=3.4, efficiency=85.0),
        ]
        svc = self._make_svc(runs)
        report = svc.generate(["r1", "r2", "r3"])
        for key in ("workload_name", "workload_type", "certification", "analysis", "diagnosis",
                    "recommendations", "scaling_data", "export_markdown", "export_html"):
            assert key in report, f"Missing key: {key}"

    def test_certification_grade_is_valid(self):
        runs = [
            _make_mock_run("r1", worker_count=1, speedup=1.0, efficiency=100.0),
            _make_mock_run("r2", worker_count=4, speedup=3.6, efficiency=90.0),
        ]
        svc = self._make_svc(runs)
        report = svc.generate(["r1", "r2"])
        assert report["certification"]["grade"] in ("A+", "A", "B", "C", "D", "F")

    def test_export_markdown_contains_grade(self):
        runs = [
            _make_mock_run("r1", worker_count=1, speedup=1.0, efficiency=100.0),
            _make_mock_run("r2", worker_count=4, speedup=3.6, efficiency=90.0),
        ]
        svc = self._make_svc(runs)
        report = svc.generate(["r1", "r2"])
        grade = report["certification"]["grade"]
        assert grade in report["export_markdown"]

    def test_export_html_is_valid_html(self):
        runs = [
            _make_mock_run("r1", worker_count=1, speedup=1.0, efficiency=100.0),
            _make_mock_run("r2", worker_count=4, speedup=3.6, efficiency=90.0),
        ]
        svc = self._make_svc(runs)
        report = svc.generate(["r1", "r2"])
        html = report["export_html"]
        assert "<!DOCTYPE html>" in html
        assert "<body>" in html
        assert "</html>" in html

    def test_workload_display_name_overrides_type(self):
        runs = [_make_mock_run("r1", worker_count=1, speedup=1.0, efficiency=100.0)]
        svc = self._make_svc(runs)
        report = svc.generate(["r1"], workload_display_name="My Custom Pipeline")
        assert report["workload_name"] == "My Custom Pipeline"

    def test_scaling_data_sorted_by_workers(self):
        runs = [
            _make_mock_run("r3", worker_count=4, speedup=3.2, efficiency=80.0),
            _make_mock_run("r1", worker_count=1, speedup=1.0, efficiency=100.0),
            _make_mock_run("r2", worker_count=2, speedup=1.9, efficiency=95.0),
        ]
        svc = self._make_svc(runs)
        report = svc.generate(["r1", "r2", "r3"])
        workers = [row["worker_count"] for row in report["scaling_data"]]
        assert workers == sorted(workers)

    def test_speedup_degradation_detected(self):
        # speedup goes: 1.0 → 1.5 → 1.2 → 0.9 (degraded at 2+ steps)
        runs = [
            _make_mock_run("r1", worker_count=1, speedup=1.0, efficiency=100.0),
            _make_mock_run("r2", worker_count=2, speedup=1.5, efficiency=75.0),
            _make_mock_run("r3", worker_count=4, speedup=1.2, efficiency=30.0),
            _make_mock_run("r4", worker_count=8, speedup=0.9, efficiency=11.25),
        ]
        svc = self._make_svc(runs)
        report = svc.generate(["r1", "r2", "r3", "r4"])
        assert report["analysis"]["speedup_degraded"] is True
        assert report["certification"]["grade"] == "F"

    def test_single_run_generates_report(self):
        runs = [_make_mock_run("r1", worker_count=4, speedup=3.8, efficiency=95.0)]
        svc = self._make_svc(runs)
        report = svc.generate(["r1"])
        assert "certification" in report

    def test_report_best_speedup_is_max(self):
        runs = [
            _make_mock_run("r1", worker_count=1, speedup=1.0, efficiency=100.0),
            _make_mock_run("r2", worker_count=2, speedup=1.85, efficiency=92.5),
            _make_mock_run("r3", worker_count=4, speedup=3.6, efficiency=90.0),
        ]
        svc = self._make_svc(runs)
        report = svc.generate(["r1", "r2", "r3"])
        assert report["analysis"]["best_speedup"] == pytest.approx(3.6, rel=0.01)

    def test_recommendations_has_optimization_priorities(self):
        runs = [
            _make_mock_run("r1", worker_count=1, speedup=1.0, efficiency=100.0),
            _make_mock_run("r2", worker_count=4, speedup=3.0, efficiency=75.0),
        ]
        svc = self._make_svc(runs)
        report = svc.generate(["r1", "r2"])
        assert isinstance(report["recommendations"]["optimization_priorities"], list)
        assert len(report["recommendations"]["optimization_priorities"]) > 0

    def test_markdown_contains_worker_table(self):
        runs = [
            _make_mock_run("r1", worker_count=1, speedup=1.0, efficiency=100.0),
            _make_mock_run("r2", worker_count=4, speedup=3.5, efficiency=87.5),
        ]
        svc = self._make_svc(runs)
        report = svc.generate(["r1", "r2"])
        md = report["export_markdown"]
        assert "Workers" in md
        assert "Speedup" in md

    def test_markdown_contains_bottleneck_diagnosis(self):
        runs = [
            _make_mock_run("r1", worker_count=1, speedup=1.0, efficiency=100.0),
            _make_mock_run("r2", worker_count=4, speedup=3.5, efficiency=87.5),
        ]
        svc = self._make_svc(runs)
        report = svc.generate(["r1", "r2"])
        md = report["export_markdown"]
        assert "Diagnosis" in md

    def test_html_contains_scaling_table(self):
        runs = [
            _make_mock_run("r1", worker_count=1, speedup=1.0, efficiency=100.0),
            _make_mock_run("r2", worker_count=4, speedup=3.5, efficiency=87.5),
        ]
        svc = self._make_svc(runs)
        report = svc.generate(["r1", "r2"])
        html = report["export_html"]
        assert "<table>" in html

    def test_diagnosis_has_primary_bottleneck(self):
        runs = [
            _make_mock_run("r1", worker_count=1, speedup=1.0, efficiency=100.0),
            _make_mock_run("r2", worker_count=4, speedup=3.5, efficiency=87.5),
        ]
        svc = self._make_svc(runs)
        report = svc.generate(["r1", "r2"])
        assert "primary_bottleneck" in report["diagnosis"]

    def test_diagnosis_uses_diagnostic_strength_pct_not_confidence(self):
        """Verify the renamed field: confidence_pct → diagnostic_strength_pct."""
        runs = [
            _make_mock_run("r1", worker_count=1, speedup=1.0, efficiency=100.0),
            _make_mock_run("r2", worker_count=4, speedup=3.5, efficiency=87.5),
        ]
        svc = self._make_svc(runs)
        report = svc.generate(["r1", "r2"])
        d = report["diagnosis"]
        assert "diagnostic_strength_pct" in d, "Field 'diagnostic_strength_pct' missing from diagnosis"
        assert "confidence_pct" not in d, "Old field 'confidence_pct' should not be in diagnosis"
        assert isinstance(d["diagnostic_strength_pct"], float)
        assert 0 <= d["diagnostic_strength_pct"] <= 100

    def test_markdown_uses_diagnostic_strength_not_confidence(self):
        runs = [
            _make_mock_run("r1", worker_count=1, speedup=1.0, efficiency=100.0),
            _make_mock_run("r2", worker_count=4, speedup=3.5, efficiency=87.5),
        ]
        svc = self._make_svc(runs)
        report = svc.generate(["r1", "r2"])
        md = report["export_markdown"]
        assert "confidence" not in md.lower(), (
            f"Markdown export still contains 'confidence': {[l for l in md.splitlines() if 'confidence' in l.lower()]}"
        )
        assert "diagnostic strength" in md.lower()

    def test_html_uses_diagnostic_strength_not_confidence(self):
        runs = [
            _make_mock_run("r1", worker_count=1, speedup=1.0, efficiency=100.0),
            _make_mock_run("r2", worker_count=4, speedup=3.5, efficiency=87.5),
        ]
        svc = self._make_svc(runs)
        report = svc.generate(["r1", "r2"])
        html = report["export_html"]
        assert "confidence" not in html.lower(), (
            "HTML export still contains 'confidence'"
        )

    def test_no_speedup_degradation_on_monotone(self):
        # Strictly increasing speedup
        runs = [
            _make_mock_run("r1", worker_count=1, speedup=1.0, efficiency=100.0),
            _make_mock_run("r2", worker_count=2, speedup=1.8, efficiency=90.0),
            _make_mock_run("r3", worker_count=4, speedup=3.2, efficiency=80.0),
        ]
        svc = self._make_svc(runs)
        report = svc.generate(["r1", "r2", "r3"])
        assert report["analysis"]["speedup_degraded"] is False

    def test_grade_a_plus_produces_a_plus_in_report(self):
        runs = [
            _make_mock_run("r1", worker_count=1, speedup=1.0, efficiency=100.0),
            _make_mock_run("r2", worker_count=2, speedup=1.97, efficiency=98.5),
            _make_mock_run("r3", worker_count=4, speedup=3.88, efficiency=97.0),
        ]
        svc = self._make_svc(runs)
        report = svc.generate(["r1", "r2", "r3"])
        # High pf and high efficiency → A+
        assert report["certification"]["grade"] in ("A+", "A")

    def test_workload_name_from_run_when_no_override(self):
        runs = [_make_mock_run("r1", worker_count=1, speedup=1.0, efficiency=100.0,
                               workload_name="My Pipeline")]
        svc = self._make_svc(runs)
        report = svc.generate(["r1"])
        assert report["workload_name"] == "My Pipeline"
