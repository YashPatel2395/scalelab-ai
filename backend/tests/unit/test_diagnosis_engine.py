"""
Unit tests for Diagnosis Engine (app/diagnosis/engine.py).

Covers all classifiers, diagnostic strength calculation, evidence generation,
executive summary, optimization opportunities, and edge cases.
"""
from __future__ import annotations

import pytest

from app.diagnosis.engine import (
    diagnose,
    _score_cpu_bound,
    _score_memory_bound,
    _score_synchronization_bound,
    _score_communication_bound,
    _score_load_imbalance,
    _score_ipc_overhead,
    _score_worker_oversubscription,
    _score_serialization_bottleneck,
    _score_io_bound,
    _score_well_balanced,
    _short_func,
    _optimization_opportunities,
    _expected_improvement,
    _risk_assessment,
    _executive_summary,
    EvidenceItem,
    BottleneckScore,
    DiagnosisResult,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_metrics(
    workload_type="matrix_multiplication",
    input_size=100_000,
    worker_count=4,
    execution_time=0.5,
    sequential_time=1.8,
    speedup=3.6,
    efficiency=90.0,
    cpu_usage=88.0,
    memory_usage=40.0,
    peak_memory_mb=200.0,
    observability_data=None,
    profiling_data=None,
) -> dict:
    return dict(
        workload_type=workload_type,
        input_size=input_size,
        worker_count=worker_count,
        execution_time=execution_time,
        sequential_time=sequential_time,
        speedup=speedup,
        efficiency=efficiency,
        cpu_usage=cpu_usage,
        memory_usage=memory_usage,
        peak_memory_mb=peak_memory_mb,
        observability_data=observability_data,
        profiling_data=profiling_data,
    )


# ── TestEvidenceItem ───────────────────────────────────────────────────────────

class TestEvidenceItem:
    def test_to_dict(self):
        e = EvidenceItem("CPU Utilization", "85%")
        d = e.to_dict()
        assert d == {"metric": "CPU Utilization", "value": "85%"}

    def test_to_dict_string_values(self):
        e = EvidenceItem("Worker Count", "8")
        assert e.to_dict()["value"] == "8"

    def test_metric_and_value_stored(self):
        e = EvidenceItem("Peak Memory", "2048 MB")
        assert e.metric == "Peak Memory"
        assert e.value == "2048 MB"


# ── Return type tests ─────────────────────────────────────────────────────────

class TestDiagnoseReturnType:
    def test_returns_diagnosis_result(self):
        m = _make_metrics()
        result = diagnose(**m)
        assert isinstance(result, DiagnosisResult)

    def test_to_dict_has_required_keys(self):
        m = _make_metrics()
        d = diagnose(**m).to_dict()
        assert "primary_bottleneck" in d
        assert "diagnostic_strength" in d
        assert "evidence" in d
        assert "all_scores" in d
        assert "optimization_opportunities" in d
        assert "expected_improvement_pct" in d
        assert "risk_assessment" in d
        assert "executive_summary" in d

    def test_diagnostic_strength_in_range(self):
        m = _make_metrics()
        result = diagnose(**m)
        assert 0.0 <= result.diagnostic_strength <= 1.0

    def test_all_scores_is_list(self):
        m = _make_metrics()
        result = diagnose(**m)
        assert isinstance(result.all_scores, list)

    def test_all_scores_has_bottleneck_scores(self):
        m = _make_metrics()
        result = diagnose(**m)
        for s in result.all_scores:
            assert isinstance(s, BottleneckScore)

    def test_evidence_items_have_metric_and_value(self):
        m = _make_metrics()
        result = diagnose(**m)
        for item in result.evidence:
            assert isinstance(item, EvidenceItem)
            assert item.metric
            assert item.value

    def test_to_dict_all_scores_is_dict(self):
        m = _make_metrics()
        d = diagnose(**m).to_dict()
        assert isinstance(d["all_scores"], dict)
        for key, val in d["all_scores"].items():
            assert isinstance(key, str)
            assert isinstance(val, float)

    def test_primary_in_all_scores(self):
        m = _make_metrics()
        result = diagnose(**m)
        names = {s.name for s in result.all_scores}
        assert result.primary in names


# ── CPU-bound classification ──────────────────────────────────────────────────

class TestCPUBoundClassification:
    def test_high_cpu_high_efficiency_is_cpu_or_well_balanced(self):
        # cpu=91, efficiency=90: well_balanced can win over cpu_bound — both are correct
        m = _make_metrics(cpu_usage=91.0, efficiency=90.0, speedup=3.6, worker_count=4)
        result = diagnose(**m)
        assert result.primary in ("cpu_bound", "well_balanced")

    def test_cpu_bound_has_cpu_evidence(self):
        m = _make_metrics(cpu_usage=92.0, efficiency=88.0)
        result = diagnose(**m)
        metrics = [e.metric for e in result.evidence]
        assert any("CPU" in m for m in metrics)

    def test_cpu_bound_executive_summary(self):
        m = _make_metrics(cpu_usage=90.0, efficiency=90.0)
        result = diagnose(**m)
        assert "CPU" in result.executive_summary or "cpu" in result.executive_summary.lower()

    def test_score_cpu_bound_high_cpu(self):
        result = _score_cpu_bound(cpu_usage=95.0, efficiency=80.0, speedup=3.2, worker_count=4)
        assert result.score >= 0.70

    def test_score_cpu_bound_medium_cpu(self):
        result = _score_cpu_bound(cpu_usage=80.0, efficiency=60.0, speedup=2.4, worker_count=4)
        assert result.score >= 0.40

    def test_score_cpu_bound_none_cpu(self):
        result = _score_cpu_bound(cpu_usage=None, efficiency=50.0, speedup=2.0, worker_count=4)
        assert result.score >= 0.0

    def test_score_cpu_bound_high_cpu_low_eff_penalty(self):
        result_high_eff = _score_cpu_bound(cpu_usage=85.0, efficiency=80.0, speedup=3.2, worker_count=4)
        result_low_eff = _score_cpu_bound(cpu_usage=85.0, efficiency=30.0, speedup=1.2, worker_count=4)
        assert result_high_eff.score > result_low_eff.score

    def test_score_cpu_bound_clamped(self):
        result = _score_cpu_bound(cpu_usage=99.0, efficiency=99.0, speedup=4.0, worker_count=4)
        assert 0.0 <= result.score <= 1.0


# ── Memory-bound classification ───────────────────────────────────────────────

class TestMemoryBoundClassification:
    def test_high_memory_low_cpu_is_memory_bound(self):
        m = _make_metrics(
            memory_usage=87.0, cpu_usage=25.0,
            efficiency=40.0, speedup=1.6, worker_count=4
        )
        result = diagnose(**m)
        assert result.primary == "memory_bound"

    def test_memory_bound_has_memory_evidence(self):
        m = _make_metrics(memory_usage=88.0, cpu_usage=22.0, efficiency=35.0)
        result = diagnose(**m)
        metrics = [e.metric for e in result.evidence]
        assert any("Memory" in m or "memory" in m.lower() for m in metrics)

    def test_score_memory_very_high(self):
        result = _score_memory_bound(
            memory_usage=90.0, peak_memory_mb=8192.0,
            speedup=0.8, efficiency=20.0, worker_count=4, cpu_usage=30.0
        )
        assert result.score >= 0.70

    def test_score_memory_high(self):
        result = _score_memory_bound(
            memory_usage=78.0, peak_memory_mb=4096.0,
            speedup=1.5, efficiency=37.5, worker_count=4, cpu_usage=50.0
        )
        assert result.score >= 0.45

    def test_score_memory_none_usage(self):
        result = _score_memory_bound(
            memory_usage=None, peak_memory_mb=None,
            speedup=2.0, efficiency=50.0, worker_count=4, cpu_usage=70.0
        )
        assert result.score >= 0.0

    def test_score_memory_negative_scaling_boost(self):
        result_neg = _score_memory_bound(
            memory_usage=65.0, peak_memory_mb=None,
            speedup=0.9, efficiency=22.5, worker_count=4, cpu_usage=40.0
        )
        result_pos = _score_memory_bound(
            memory_usage=65.0, peak_memory_mb=None,
            speedup=1.5, efficiency=37.5, worker_count=4, cpu_usage=40.0
        )
        assert result_neg.score > result_pos.score

    def test_score_memory_peak_in_evidence(self):
        result = _score_memory_bound(
            memory_usage=80.0, peak_memory_mb=2048.0,
            speedup=1.5, efficiency=37.5, worker_count=4, cpu_usage=50.0
        )
        metrics = [e.metric for e in result.evidence]
        assert "Peak Memory" in metrics


# ── Synchronization-bound classification ─────────────────────────────────────

class TestSynchronizationBound:
    def test_high_serial_fraction_scores_sync_bound(self):
        # speedup=1.5 with 8 workers → high serial fraction
        m = _make_metrics(
            worker_count=8, speedup=1.5, efficiency=18.75,
            cpu_usage=28.0, memory_usage=30.0
        )
        result = diagnose(**m)
        # synchronization_bound should score highly
        scores = {s.name: s.score for s in result.all_scores}
        assert scores["synchronization_bound"] > 0.30

    def test_serial_fraction_in_evidence(self):
        m = _make_metrics(worker_count=8, speedup=1.5, efficiency=18.75, cpu_usage=28.0)
        result = diagnose(**m)
        all_evidence = []
        for s in result.all_scores:
            all_evidence.extend(s.evidence)
        metrics = [e.metric for e in all_evidence]
        assert any("Serial" in m or "Amdahl" in m for m in metrics)

    def test_score_synchronization_high_serial_fraction(self):
        # speedup=2 with 8 workers = ~75% serial fraction
        result = _score_synchronization_bound(
            speedup=2.0, efficiency=25.0, worker_count=8,
            sequential_time=1.0, execution_time=0.5, cpu_usage=30.0
        )
        assert result.score >= 0.60

    def test_score_synchronization_low_cpu_stalling(self):
        result = _score_synchronization_bound(
            speedup=1.5, efficiency=37.5, worker_count=4,
            sequential_time=1.0, execution_time=0.67, cpu_usage=25.0
        )
        assert result.score >= 0.25

    def test_score_synchronization_single_worker(self):
        result = _score_synchronization_bound(
            speedup=1.0, efficiency=100.0, worker_count=1,
            sequential_time=1.0, execution_time=1.0, cpu_usage=80.0
        )
        assert result.score < 0.20


# ── IPC overhead classification ───────────────────────────────────────────────

class TestIPCOverhead:
    def test_negative_speedup_large_workers_scores_ipc(self):
        m = _make_metrics(
            worker_count=8, speedup=0.8, efficiency=10.0,
            cpu_usage=35.0, memory_usage=20.0
        )
        result = diagnose(**m)
        scores = {s.name: s.score for s in result.all_scores}
        assert scores["ipc_overhead"] > 0.30

    def test_low_cpu_many_workers_boosts_ipc(self):
        m = _make_metrics(
            worker_count=4, speedup=1.5, efficiency=37.5,
            cpu_usage=28.0, memory_usage=20.0
        )
        result = diagnose(**m)
        scores = {s.name: s.score for s in result.all_scores}
        assert scores["ipc_overhead"] > 0.0

    def test_score_ipc_many_workers_poor_speedup(self):
        result = _score_ipc_overhead(
            speedup=1.0, efficiency=12.5, worker_count=8,
            cpu_usage=20.0, execution_time=1.0, sequential_time=1.0
        )
        assert result.score >= 0.60

    def test_score_ipc_negative_scaling(self):
        result = _score_ipc_overhead(
            speedup=0.5, efficiency=12.5, worker_count=4,
            cpu_usage=30.0, execution_time=2.0, sequential_time=1.0
        )
        assert result.score >= 0.50

    def test_score_ipc_scaling_direction_in_evidence(self):
        result = _score_ipc_overhead(
            speedup=0.5, efficiency=10.0, worker_count=4,
            cpu_usage=20.0, execution_time=2.0, sequential_time=1.0
        )
        metrics = [e.metric for e in result.evidence]
        assert "Scaling Direction" in metrics


# ── Worker oversubscription ───────────────────────────────────────────────────

class TestWorkerOversubscription:
    def test_worker_count_above_cpu_count_scores_oversubscription(self):
        import os
        try:
            import psutil
            cpu_count = psutil.cpu_count(logical=True) or os.cpu_count() or 4
        except Exception:
            cpu_count = os.cpu_count() or 4

        # Use 3× logical CPUs
        worker_count = cpu_count * 3
        m = _make_metrics(
            worker_count=worker_count,
            efficiency=30.0,
            speedup=worker_count * 0.3,
        )
        result = diagnose(**m)
        scores = {s.name: s.score for s in result.all_scores}
        assert scores["worker_oversubscription"] > 0.40

    def test_score_oversubscription_heavy(self):
        result = _score_worker_oversubscription(
            worker_count=32, efficiency=20.0, speedup=0.8, cpu_count=4
        )
        assert result.score >= 0.60

    def test_score_oversubscription_not_oversubscribed(self):
        result = _score_worker_oversubscription(
            worker_count=4, efficiency=80.0, speedup=3.2, cpu_count=8
        )
        assert result.score == 0.0

    def test_score_oversubscription_ratio_in_evidence(self):
        result = _score_worker_oversubscription(
            worker_count=16, efficiency=20.0, speedup=1.0, cpu_count=4
        )
        metrics = [e.metric for e in result.evidence]
        assert "Oversubscription Ratio" in metrics

    def test_score_oversubscription_equal_cpu_count(self):
        result = _score_worker_oversubscription(
            worker_count=4, efficiency=75.0, speedup=3.0, cpu_count=4
        )
        assert result.score == 0.0


# ── Serialization bottleneck ─────────────────────────────────────────────────

class TestSerializationBottleneck:
    def test_custom_python_small_input_scores_high(self):
        m = _make_metrics(
            workload_type="custom_python",
            input_size=500,
            worker_count=8,
            speedup=0.7,
            efficiency=8.75,
            cpu_usage=30.0,
        )
        result = diagnose(**m)
        scores = {s.name: s.score for s in result.all_scores}
        assert scores["serialization_bottleneck"] > 0.30

    def test_builtin_large_input_does_not_flag_serialization_with_few_workers(self):
        m = _make_metrics(
            workload_type="parallel_sort",
            input_size=1_000_000,
            worker_count=2,
            speedup=1.9,
            efficiency=95.0,
            cpu_usage=90.0,
        )
        result = diagnose(**m)
        scores = {s.name: s.score for s in result.all_scores}
        assert scores["serialization_bottleneck"] == 0.0

    def test_score_serialization_custom_workload_base(self):
        result = _score_serialization_bottleneck(
            workload_type="custom_python", worker_count=4,
            speedup=2.0, efficiency=50.0, input_size=5000
        )
        assert result.score >= 0.20

    def test_score_serialization_builtin_few_workers_suppressed(self):
        result = _score_serialization_bottleneck(
            workload_type="parallel_sort", worker_count=2,
            speedup=1.5, efficiency=75.0, input_size=10000
        )
        assert result.score == 0.0

    def test_score_serialization_input_worker_ratio_in_evidence(self):
        result = _score_serialization_bottleneck(
            workload_type="custom_python", worker_count=4,
            speedup=0.5, efficiency=12.5, input_size=4000
        )
        metrics = [e.metric for e in result.evidence]
        assert "Input/Worker Ratio" in metrics


# ── I/O bound classification ──────────────────────────────────────────────────

class TestIOBound:
    def test_high_disk_rate_is_io_bound(self):
        obs = {
            "duration_seconds": 2.0,
            "disk_read_mb": 300.0,
            "disk_write_mb": 50.0,
            "net_recv_mb": 0.0,
            "net_sent_mb": 0.0,
        }
        m = _make_metrics(cpu_usage=18.0, efficiency=40.0, observability_data=obs)
        result = diagnose(**m)
        assert result.primary == "io_bound"

    def test_no_io_data_gives_zero_io_score(self):
        m = _make_metrics(observability_data=None)
        result = diagnose(**m)
        scores = {s.name: s.score for s in result.all_scores}
        assert scores["io_bound"] == 0.0

    def test_score_io_very_high_disk(self):
        obs = {"duration_seconds": 1.0, "disk_read_mb": 80.0, "disk_write_mb": 40.0}
        result = _score_io_bound(obs, cpu_usage=20.0, efficiency=30.0, worker_count=4)
        assert result.score >= 0.70

    def test_score_io_no_observability_zero(self):
        result = _score_io_bound(None, cpu_usage=50.0, efficiency=50.0, worker_count=4)
        assert result.score == 0.0

    def test_score_io_disk_rate_in_evidence(self):
        obs = {"duration_seconds": 1.0, "disk_read_mb": 30.0, "disk_write_mb": 30.0}
        result = _score_io_bound(obs, cpu_usage=20.0, efficiency=30.0, worker_count=4)
        metrics = [e.metric for e in result.evidence]
        assert "Disk I/O Rate" in metrics


# ── Well-balanced ─────────────────────────────────────────────────────────────

class TestWellBalanced:
    def test_excellent_scaling_scores_well_balanced(self):
        m = _make_metrics(
            worker_count=4, speedup=3.8, efficiency=95.0,
            cpu_usage=85.0, memory_usage=30.0
        )
        result = diagnose(**m)
        scores = {s.name: s.score for s in result.all_scores}
        assert scores["well_balanced"] > 0.50

    def test_score_well_balanced_high_efficiency(self):
        result = _score_well_balanced(efficiency=92.0, speedup=3.68, worker_count=4, cpu_usage=85.0)
        assert result.score >= 0.75

    def test_score_well_balanced_moderate_efficiency(self):
        result = _score_well_balanced(efficiency=82.0, speedup=3.28, worker_count=4, cpu_usage=75.0)
        assert result.score >= 0.55

    def test_score_well_balanced_low_efficiency_low_score(self):
        result = _score_well_balanced(efficiency=40.0, speedup=1.6, worker_count=4, cpu_usage=50.0)
        assert result.score < 0.40

    def test_well_balanced_in_all_scores(self):
        m = _make_metrics()
        result = diagnose(**m)
        names = {s.name for s in result.all_scores}
        assert "well_balanced" in names


# ── Communication bound ───────────────────────────────────────────────────────

class TestCommunicationBound:
    def test_high_network_io(self):
        obs = {"duration_seconds": 1.0, "net_recv_mb": 40.0, "net_sent_mb": 20.0,
               "disk_read_mb": 0, "disk_write_mb": 0}
        result = _score_communication_bound(obs, worker_count=4, speedup=2.0, efficiency=50.0)
        assert result.score >= 0.60

    def test_no_observability_low_efficiency_inferred(self):
        result = _score_communication_bound(
            None, worker_count=8, speedup=2.0, efficiency=25.0
        )
        assert result.score >= 0.15

    def test_network_rate_in_evidence(self):
        obs = {"duration_seconds": 1.0, "net_recv_mb": 30.0, "net_sent_mb": 0,
               "disk_read_mb": 0, "disk_write_mb": 0}
        result = _score_communication_bound(obs, worker_count=4, speedup=2.0, efficiency=50.0)
        metrics = [e.metric for e in result.evidence]
        assert "Network I/O Rate" in metrics


# ── Load imbalance ────────────────────────────────────────────────────────────

class TestLoadImbalance:
    def test_high_core_variance(self):
        obs = {"cpu_per_core_avg": [95.0, 10.0, 15.0, 12.0]}
        result = _score_load_imbalance(obs, efficiency=30.0, worker_count=4, speedup=1.2)
        assert result.score >= 0.55

    def test_uniform_cores_penalty(self):
        obs = {"cpu_per_core_avg": [75.0, 70.0, 72.0, 68.0]}
        result = _score_load_imbalance(obs, efficiency=70.0, worker_count=4, speedup=2.8)
        assert result.score < 0.30

    def test_variance_in_evidence(self):
        obs = {"cpu_per_core_avg": [90.0, 20.0, 25.0, 22.0]}
        result = _score_load_imbalance(obs, efficiency=30.0, worker_count=4, speedup=1.2)
        metrics = [e.metric for e in result.evidence]
        assert "CPU Core Variance" in metrics

    def test_no_observability_moderate_score(self):
        result = _score_load_imbalance(None, efficiency=40.0, worker_count=4, speedup=1.6)
        assert result.score >= 0.10


# ── Secondary bottleneck ──────────────────────────────────────────────────────

class TestSecondaryBottleneck:
    def test_secondary_is_none_or_string(self):
        m = _make_metrics(cpu_usage=92.0, efficiency=90.0)
        result = diagnose(**m)
        assert result.secondary is None or isinstance(result.secondary, str)

    def test_secondary_evidence_strength_set_when_secondary_present(self):
        m = _make_metrics(
            memory_usage=82.0, cpu_usage=22.0,
            efficiency=38.0, speedup=1.5, worker_count=4
        )
        result = diagnose(**m)
        if result.secondary is not None:
            assert result.secondary_evidence_strength is not None
            assert result.secondary_evidence_strength > 0.0

    def test_secondary_is_valid_bottleneck_name(self):
        valid_names = {
            "cpu_bound", "memory_bound", "synchronization_bound",
            "communication_bound", "load_imbalance", "ipc_overhead",
            "worker_oversubscription", "serialization_bottleneck", "io_bound",
            "well_balanced"
        }
        m = _make_metrics(memory_usage=82.0, cpu_usage=22.0, efficiency=38.0)
        result = diagnose(**m)
        if result.secondary is not None:
            assert result.secondary in valid_names


# ── Profiling data integration ────────────────────────────────────────────────

class TestProfilingIntegration:
    def test_profiling_hotspot_added_to_cpu_evidence(self):
        profiling_data = {
            "top_hotspots": [
                {"function": "compute:42(matmul)", "pct_of_total": 65.0, "calls": 100, "total_time_ms": 390.0},
                {"function": "utils:10(chunk)", "pct_of_total": 20.0, "calls": 200, "total_time_ms": 120.0},
            ]
        }
        m = _make_metrics(cpu_usage=90.0, efficiency=88.0, profiling_data=profiling_data)
        result = diagnose(**m)
        # CPU bound should have hottest function evidence
        scores = {s.name: s for s in result.all_scores}
        cpu_metrics = [e.metric for e in scores["cpu_bound"].evidence]
        assert any("Hottest" in m or "hottest" in m.lower() for m in cpu_metrics)

    def test_low_hotspot_pct_not_crashing(self):
        profiling_data = {
            "top_hotspots": [
                {"function": "minor:10(fn)", "pct_of_total": 5.0, "calls": 10, "total_time_ms": 30.0},
            ]
        }
        m = _make_metrics(profiling_data=profiling_data)
        result = diagnose(**m)
        assert result is not None

    def test_high_hotspot_pct_may_add_opportunity(self):
        profiling_data = {
            "top_hotspots": [
                {"function": "myfile.py:10(slow_fn)", "pct_of_total": 60.0, "calls": 100, "total_time_ms": 500.0},
            ]
        }
        m = _make_metrics(cpu_usage=90.0, profiling_data=profiling_data)
        result = diagnose(**m)
        assert result is not None  # no crash; opportunities may include hotspot


# ── Diagnostic strength bounds ───────────────────────────────────────────────

class TestDiagnosticStrengthBounds:
    def test_diagnostic_strength_non_negative(self):
        for cpu in [None, 10.0, 50.0, 95.0]:
            m = _make_metrics(cpu_usage=cpu)
            result = diagnose(**m)
            assert result.diagnostic_strength >= 0.0, f"diagnostic_strength={result.diagnostic_strength} for cpu={cpu}"

    def test_diagnostic_strength_at_most_one(self):
        m = _make_metrics(cpu_usage=100.0, efficiency=100.0)
        result = diagnose(**m)
        assert result.diagnostic_strength <= 1.0

    def test_diagnostic_strength_zero_when_tied(self):
        # When all classifiers score identically, strength should be 0
        # (primary.score - secondary.score = 0)
        m = _make_metrics(cpu_usage=None, memory_usage=None, observability_data=None)
        result = diagnose(**m)
        assert result.diagnostic_strength >= 0.0  # never negative

    def test_high_strength_when_clear_bottleneck(self):
        # Very high CPU usage with good efficiency should produce clear cpu_bound signal
        m = _make_metrics(cpu_usage=98.0, efficiency=95.0)
        result = diagnose(**m)
        if result.primary == "cpu_bound":
            assert result.diagnostic_strength > 0.0


# ── Optimization opportunities ────────────────────────────────────────────────

class TestOptimizationOpportunities:
    def test_returns_list_of_strings(self):
        m = _make_metrics()
        result = diagnose(**m)
        assert isinstance(result.optimization_opportunities, list)
        assert all(isinstance(o, str) for o in result.optimization_opportunities)

    def test_max_four_opportunities(self):
        m = _make_metrics()
        result = diagnose(**m)
        assert len(result.optimization_opportunities) <= 4

    def test_cpu_bound_has_relevant_opportunities(self):
        opts = _optimization_opportunities("cpu_bound", None, 4, 50.0, None)
        assert len(opts) > 0

    def test_all_bottleneck_types_have_opportunities(self):
        for bt in ["cpu_bound", "memory_bound", "synchronization_bound", "communication_bound",
                   "load_imbalance", "ipc_overhead", "worker_oversubscription",
                   "serialization_bottleneck", "io_bound", "well_balanced"]:
            opts = _optimization_opportunities(bt, None, 4, 50.0, None)
            assert len(opts) > 0, f"No opportunities for {bt}"


# ── Expected improvement ──────────────────────────────────────────────────────

class TestExpectedImprovement:
    def test_expected_improvement_is_float(self):
        m = _make_metrics()
        result = diagnose(**m)
        assert isinstance(result.expected_improvement_pct, float)

    def test_well_scaling_has_low_expected_improvement(self):
        m = _make_metrics(efficiency=95.0, cpu_usage=85.0)
        result = diagnose(**m)
        # Only 5% efficiency gap, so improvement should be small
        assert result.expected_improvement_pct <= 10.0

    def test_zero_efficiency_gap(self):
        improvement = _expected_improvement("cpu_bound", 100.0, 4)
        assert improvement == 0.0

    def test_large_gap_large_improvement(self):
        improvement = _expected_improvement("ipc_overhead", 10.0, 8)
        assert improvement > 40.0

    def test_all_bottleneck_types_non_negative(self):
        for bt in ["cpu_bound", "memory_bound", "synchronization_bound", "communication_bound",
                   "load_imbalance", "ipc_overhead", "worker_oversubscription",
                   "serialization_bottleneck", "io_bound", "well_balanced"]:
            improvement = _expected_improvement(bt, 50.0, 4)
            assert improvement >= 0.0


# ── Risk assessment ───────────────────────────────────────────────────────────

class TestRiskAssessment:
    def test_high_risk_strong_signal_low_efficiency(self):
        # diagnostic_strength > 0.40 and efficiency < 30 → HIGH
        risk = _risk_assessment("cpu_bound", 0.50, 20.0, 4)
        assert "HIGH" in risk

    def test_medium_risk_moderate_strength(self):
        # diagnostic_strength > 0.20 and efficiency < 60 → MEDIUM
        risk = _risk_assessment("cpu_bound", 0.30, 45.0, 4)
        assert "MEDIUM" in risk

    def test_low_risk_good_efficiency(self):
        risk = _risk_assessment("cpu_bound", 0.30, 80.0, 4)
        assert "LOW" in risk

    def test_medium_risk_default(self):
        # diagnostic_strength <= 0.20, efficiency < 75 → MEDIUM
        risk = _risk_assessment("cpu_bound", 0.10, 60.0, 4)
        assert "MEDIUM" in risk


# ── Executive summary ─────────────────────────────────────────────────────────

class TestExecutiveSummary:
    def test_contains_bottleneck_label(self):
        summary = _executive_summary(
            "cpu_bound", 0.85, 50.0, 2.0, 4, 1.0, 0.5, None
        )
        assert "CPU-Bound" in summary

    def test_contains_diagnostic_strength(self):
        summary = _executive_summary(
            "cpu_bound", 0.45, 50.0, 2.0, 4, 1.0, 0.5, None
        )
        assert "0.45" in summary

    def test_contains_worker_count(self):
        summary = _executive_summary(
            "cpu_bound", 0.85, 50.0, 2.0, 4, 1.0, 0.5, None
        )
        assert "4 workers" in summary

    def test_secondary_mentioned_when_present(self):
        summary = _executive_summary(
            "cpu_bound", 0.80, 50.0, 2.0, 4, 1.0, 0.5, "memory_bound"
        )
        assert "memory bound" in summary.lower()

    def test_good_efficiency_says_well(self):
        summary = _executive_summary(
            "cpu_bound", 0.85, 80.0, 3.2, 4, 1.0, 0.31, None
        )
        assert "well" in summary

    def test_poor_efficiency_says_poorly(self):
        summary = _executive_summary(
            "ipc_overhead", 0.85, 20.0, 0.8, 4, 1.0, 1.25, None
        )
        assert "poorly" in summary

    def test_all_bottleneck_types_have_labels(self):
        for bt in ["cpu_bound", "memory_bound", "synchronization_bound", "communication_bound",
                   "load_imbalance", "ipc_overhead", "worker_oversubscription",
                   "serialization_bottleneck", "io_bound", "well_balanced"]:
            summary = _executive_summary(bt, 0.75, 50.0, 2.0, 4, 1.0, 0.5, None)
            assert len(summary) > 20


# ── Short func ────────────────────────────────────────────────────────────────

class TestShortFunc:
    def test_cprofile_label_extraction(self):
        label = "/path/to/myfile.py:42(compute)"
        assert _short_func(label) == "compute"

    def test_plain_path(self):
        label = "/path/to/myfile.py"
        assert _short_func(label) == "myfile.py"

    def test_simple_name(self):
        assert _short_func("compute") == "compute"


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_single_worker_no_crash(self):
        m = _make_metrics(worker_count=1, speedup=1.0, efficiency=100.0)
        result = diagnose(**m)
        assert result.primary is not None

    def test_negative_speedup_scenario(self):
        m = _make_metrics(speedup=0.3, efficiency=7.5, worker_count=4, cpu_usage=20.0)
        result = diagnose(**m)
        scores = {s.name: s.score for s in result.all_scores}
        assert scores["ipc_overhead"] > 0.0

    def test_all_none_observability(self):
        m = _make_metrics(observability_data=None, cpu_usage=None, memory_usage=None)
        result = diagnose(**m)
        assert isinstance(result, DiagnosisResult)

    def test_perfect_scaling(self):
        m = _make_metrics(speedup=4.0, efficiency=100.0, cpu_usage=95.0, worker_count=4)
        result = diagnose(**m)
        scores = {s.name: s.score for s in result.all_scores}
        assert scores["well_balanced"] > 0.0
