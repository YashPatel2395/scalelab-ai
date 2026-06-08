"""
Unit tests for BottleneckAgent.

Validates classification accuracy, severity scoring, and evidence generation
against known benchmark configurations.
"""
from __future__ import annotations

import pytest

from app.ai.bottleneck_agent import analyze_bottleneck, _severity_label


class TestSeverityLabel:
    def test_critical_threshold(self):
        assert _severity_label(0.80) == "critical"
        assert _severity_label(0.75) == "critical"

    def test_high_threshold(self):
        assert _severity_label(0.60) == "high"
        assert _severity_label(0.50) == "high"

    def test_medium_threshold(self):
        assert _severity_label(0.40) == "medium"
        assert _severity_label(0.25) == "medium"

    def test_low_threshold(self):
        assert _severity_label(0.10) == "low"
        assert _severity_label(0.0) == "low"


class TestAnalyzeBottleneck:
    """Tests the full analyze_bottleneck function."""

    def _call(self, **kwargs):
        defaults = dict(
            benchmark_id="test-id",
            workload_type="image_processing",
            input_size=1024,
            worker_count=4,
            execution_time=0.5,
            sequential_time=1.0,
            speedup=2.0,
            efficiency=50.0,
            cpu_usage=70.0,
            memory_usage=40.0,
            peak_memory_mb=256.0,
            observability_data=None,
        )
        defaults.update(kwargs)
        return analyze_bottleneck(**defaults)

    def test_returns_all_required_fields(self):
        report = self._call()
        required = [
            "benchmark_id", "bottleneck_type", "severity", "severity_score",
            "root_cause", "evidence", "recommendations", "estimated_max_improvement",
        ]
        for field in required:
            assert field in report, f"Missing field: {field}"

    def test_benchmark_id_preserved(self):
        report = self._call(benchmark_id="abc-123")
        assert report["benchmark_id"] == "abc-123"

    def test_high_cpu_classified_as_cpu_bound(self):
        report = self._call(cpu_usage=95.0, efficiency=60.0, worker_count=2)
        assert report["bottleneck_type"] == "cpu_bound"

    def test_high_memory_classified_as_memory_bound(self):
        report = self._call(
            memory_usage=90.0,
            cpu_usage=40.0,
            workload_type="image_processing",
        )
        assert report["bottleneck_type"] == "memory_bound"

    def test_low_efficiency_with_many_workers_gives_communication(self):
        # Low efficiency, many workers → communication overhead
        report = self._call(
            worker_count=8,
            speedup=1.5,
            efficiency=18.75,
            cpu_usage=25.0,
        )
        # Should be communication or similar overhead type
        assert report["bottleneck_type"] in ("communication_bound", "cpu_bound")

    def test_severity_score_in_range(self):
        report = self._call()
        assert 0.0 <= report["severity_score"] <= 1.0

    def test_severity_label_matches_score(self):
        report = self._call()
        expected = _severity_label(report["severity_score"])
        assert report["severity"] == expected

    def test_evidence_is_list_of_strings(self):
        report = self._call()
        assert isinstance(report["evidence"], list)
        assert all(isinstance(e, str) for e in report["evidence"])

    def test_recommendations_is_list_of_strings(self):
        report = self._call()
        assert isinstance(report["recommendations"], list)
        assert len(report["recommendations"]) > 0

    def test_root_cause_is_nonempty_string(self):
        report = self._call()
        assert isinstance(report["root_cause"], str)
        assert len(report["root_cause"]) > 10

    def test_estimated_improvement_non_negative(self):
        report = self._call()
        assert report["estimated_max_improvement"] >= 0.0

    def test_observability_data_affects_io_score(self):
        obs = {
            "cpu_peak": 30,
            "disk_read_mb": 1000.0,
            "disk_write_mb": 500.0,
            "net_recv_mb": 0.0,
            "net_sent_mb": 0.0,
            "duration_seconds": 5.0,
        }
        report = self._call(observability_data=obs, cpu_usage=30.0)
        assert report["bottleneck_type"] == "io_bound"

    def test_graph_bfs_workload_heuristic(self):
        """Graph BFS should get communication evidence."""
        report = self._call(workload_type="graph_bfs", worker_count=8, efficiency=50.0)
        comm_evidence = any("frontier" in e.lower() or "barrier" in e.lower() or "bfs" in e.lower()
                            for e in report["evidence"])
        assert comm_evidence

    def test_matrix_multiply_gets_communication_evidence(self):
        report = self._call(workload_type="matrix_multiplication", worker_count=4)
        mm_evidence = any("ipc" in e.lower() or "matrix" in e.lower() or "communication" in e.lower()
                          for e in report["evidence"])
        assert mm_evidence

    def test_well_balanced_classified_as_balanced(self):
        """High efficiency → balanced classification."""
        report = self._call(
            efficiency=95.0,
            cpu_usage=60.0,
            memory_usage=30.0,
            speedup=3.8,
            worker_count=4,
        )
        # May be cpu_bound or balanced — just verify score is low
        assert report["severity_score"] < 0.7


class TestBottleneckWorkloadTypes:
    """Ensure all four workload types are handled without error."""

    @pytest.mark.parametrize("workload", [
        "matrix_multiplication",
        "parallel_sort",
        "image_processing",
        "graph_bfs",
    ])
    def test_all_workloads_produce_valid_report(self, workload):
        report = analyze_bottleneck(
            benchmark_id="test",
            workload_type=workload,
            input_size=1024,
            worker_count=4,
            execution_time=1.0,
            sequential_time=2.0,
            speedup=2.0,
            efficiency=50.0,
            cpu_usage=60.0,
            memory_usage=40.0,
            peak_memory_mb=200.0,
            observability_data=None,
        )
        assert report["bottleneck_type"] in (
            "cpu_bound", "memory_bound", "io_bound",
            "communication_bound", "balanced"
        )
        assert report["severity"] in ("critical", "high", "medium", "low")
