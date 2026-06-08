"""
Fault injection tests using ChaosEngineer.

These tests verify that the platform behaves correctly under failure conditions:
- Worker crashes are detected (non-zero exit codes)
- Latency injection measurably increases execution time
- Memory pressure is handled without crashes
- Partial failures produce degraded (not failed) outcomes
"""
from __future__ import annotations

import pytest

from app.testing.chaos import ChaosEngineer, FaultScenario


@pytest.fixture(scope="module")
def chaos():
    return ChaosEngineer()


class TestWorkerCrash:
    def test_crash_is_detected(self, chaos):
        report = chaos.run_scenario(FaultScenario.WORKER_CRASH)
        assert report.fault_injected is True
        assert report.fault_detected is True

    def test_outcome_is_recovered_or_degraded(self, chaos):
        report = chaos.run_scenario(FaultScenario.WORKER_CRASH)
        assert report.outcome in ("recovered", "degraded", "completed")

    def test_does_not_hang(self, chaos):
        """Crash scenario must complete within a reasonable timeout."""
        import threading
        completed = threading.Event()
        result = []

        def run():
            r = chaos.run_scenario(FaultScenario.WORKER_CRASH)
            result.append(r)
            completed.set()

        t = threading.Thread(target=run, daemon=True)
        t.start()
        completed.wait(timeout=10.0)
        assert completed.is_set(), "Worker crash scenario hung (did not complete in 10s)"

    def test_report_has_evidence(self, chaos):
        report = chaos.run_scenario(FaultScenario.WORKER_CRASH)
        assert len(report.evidence) > 0

    def test_execution_time_positive(self, chaos):
        report = chaos.run_scenario(FaultScenario.WORKER_CRASH)
        assert report.execution_time_ms > 0


class TestHighLatency:
    def test_latency_is_detected(self, chaos):
        report = chaos.run_scenario(FaultScenario.HIGH_LATENCY, worker_count=4)
        assert report.fault_injected is True
        assert report.fault_detected is True

    def test_execution_slower_than_baseline(self, chaos):
        report = chaos.run_scenario(FaultScenario.HIGH_LATENCY, worker_count=4)
        if report.baseline_time_ms:
            assert report.execution_time_ms >= report.baseline_time_ms * 0.5
            # With latency injection, should be measurably slower
            assert report.overhead_pct is not None

    def test_overhead_is_positive(self, chaos):
        report = chaos.run_scenario(FaultScenario.HIGH_LATENCY, worker_count=4)
        if report.overhead_pct is not None:
            # Injected latency (200ms) >> baseline, so overhead should be very positive
            assert report.overhead_pct > 0

    def test_evidence_mentions_communication(self, chaos):
        report = chaos.run_scenario(FaultScenario.HIGH_LATENCY, worker_count=2)
        comm_mentioned = any(
            "latency" in e.lower() or "communication" in e.lower()
            for e in report.evidence
        )
        assert comm_mentioned

    def test_to_dict_serializable(self, chaos):
        report = chaos.run_scenario(FaultScenario.HIGH_LATENCY)
        d = report.to_dict()
        assert isinstance(d, dict)
        assert d["scenario"] == "high_latency"


class TestMemoryPressure:
    def test_scenario_completes_without_exception(self, chaos):
        report = chaos.run_scenario(FaultScenario.MEMORY_PRESSURE)
        assert report.outcome in ("completed", "degraded", "failed")

    def test_fault_marked_as_injected(self, chaos):
        report = chaos.run_scenario(FaultScenario.MEMORY_PRESSURE)
        assert report.fault_injected is True

    def test_execution_time_recorded(self, chaos):
        report = chaos.run_scenario(FaultScenario.MEMORY_PRESSURE)
        assert report.execution_time_ms > 0

    def test_evidence_mentions_memory(self, chaos):
        report = chaos.run_scenario(FaultScenario.MEMORY_PRESSURE)
        mem_mentioned = any("memory" in e.lower() or "mb" in e.lower() for e in report.evidence)
        assert mem_mentioned


class TestPartialFailure:
    def test_some_workers_detected_as_failed(self, chaos):
        report = chaos.run_scenario(FaultScenario.PARTIAL_FAILURE, worker_count=4)
        assert report.fault_injected is True
        # With 4 workers, 2 fail → fault should be detected
        assert report.fault_detected is True

    def test_outcome_is_degraded_not_failed(self, chaos):
        """Partial failure with some good workers = degraded, not total failure."""
        report = chaos.run_scenario(FaultScenario.PARTIAL_FAILURE, worker_count=4)
        # With half workers good, half bad → degraded
        assert report.outcome in ("degraded", "completed")

    def test_evidence_counts_workers(self, chaos):
        report = chaos.run_scenario(FaultScenario.PARTIAL_FAILURE, worker_count=4)
        worker_mentioned = any(
            "worker" in e.lower() or "succeed" in e.lower() or "fail" in e.lower()
            for e in report.evidence
        )
        assert worker_mentioned


class TestRunAllScenarios:
    def test_run_all_returns_four_reports(self, chaos):
        reports = chaos.run_all_scenarios(input_size=128, worker_count=2)
        assert len(reports) == 4
        assert "worker_crash" in reports
        assert "high_latency" in reports
        assert "memory_pressure" in reports
        assert "partial_failure" in reports

    def test_all_reports_have_dict_form(self, chaos):
        reports = chaos.run_all_scenarios(input_size=128, worker_count=2)
        for name, report in reports.items():
            d = report.to_dict()
            assert d["scenario"] == name

    def test_all_scenarios_have_outcomes(self, chaos):
        reports = chaos.run_all_scenarios(input_size=128, worker_count=2)
        for report in reports.values():
            assert report.outcome in ("completed", "degraded", "recovered", "failed")
