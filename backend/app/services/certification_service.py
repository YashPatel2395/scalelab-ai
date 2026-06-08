"""
Scalability Certification Service
──────────────────────────────────
Generates a Scalability Certification Report from a set of completed
benchmark runs spanning multiple worker counts.

Report includes:
  - Amdahl/Gustafson curve fit
  - Primary bottleneck diagnosis
  - Certification grade (A+ to F)
  - Optimization recommendations
  - Export in JSON, Markdown, and HTML formats

Grade formula (documented in docs/SCALABILITY_MODEL.md):
  A+  parallel_fraction >= 0.95  AND  best_efficiency >= 80%
  A   parallel_fraction >= 0.90  OR   best_efficiency >= 75%
  B   parallel_fraction >= 0.80  OR   best_efficiency >= 60%
  C   parallel_fraction >= 0.65  OR   best_efficiency >= 45%
  D   best_efficiency >= 25%
  F   best_efficiency < 25%  OR  speedup degraded at 2+ worker counts
"""

from __future__ import annotations

import html as _html
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.ai.scalability_agent import predict_scalability
from app.diagnosis.engine import diagnose
from app.logging_config import get_logger
from app.models.benchmark import BenchmarkRun

logger = get_logger(__name__)


def _grade(
    parallel_fraction: float | None,
    best_efficiency: float,
    speedup_degraded: bool,
) -> tuple[str, str]:
    """Returns (grade, rationale) from scaling metrics."""
    if speedup_degraded:
        return "F", "Speedup degraded at higher worker counts — negative scaling detected."

    pf = parallel_fraction or 0.0

    if pf >= 0.95 and best_efficiency >= 80:
        return "A+", f"Exceptional: {pf:.0%} parallel fraction, {best_efficiency:.0f}% peak efficiency."
    if pf >= 0.90 or best_efficiency >= 75:
        return "A", f"Excellent: {pf:.0%} parallel fraction, {best_efficiency:.0f}% peak efficiency."
    if pf >= 0.80 or best_efficiency >= 60:
        return "B", f"Good: {pf:.0%} parallel fraction, {best_efficiency:.0f}% peak efficiency."
    if pf >= 0.65 or best_efficiency >= 45:
        return "C", f"Fair: {pf:.0%} parallel fraction, {best_efficiency:.0f}% peak efficiency."
    if best_efficiency >= 25:
        return "D", f"Poor: {best_efficiency:.0f}% peak efficiency — significant overhead."
    return "F", f"Failing: {best_efficiency:.0f}% peak efficiency — parallelism is counterproductive."


class CertificationService:
    def __init__(self, db: Session):
        self.db = db

    def generate(
        self,
        run_ids: list[str],
        workload_display_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate a full Scalability Certification Report.

        Parameters
        ----------
        run_ids:
            IDs of completed BenchmarkRun records (one per worker count).
        workload_display_name:
            Optional human-readable workload name (overrides workload_type).

        Returns
        -------
        A dict with all report fields plus export_markdown and export_html keys.
        """
        runs = (
            self.db.query(BenchmarkRun)
            .filter(BenchmarkRun.id.in_(run_ids))
            .filter(BenchmarkRun.status == "completed")
            .all()
        )
        if not runs:
            raise ValueError("No completed benchmark runs found for the given IDs.")

        runs_sorted = sorted(runs, key=lambda r: r.worker_count)

        # ── Extract data points ─────────────────────────────────────────────────
        workload_type = runs_sorted[0].workload_type
        input_size = runs_sorted[0].input_size
        workload_name = (
            workload_display_name
            or (runs_sorted[0].workload_name)
            or workload_type
        )

        data_points = [
            {"worker_count": r.worker_count, "speedup": r.speedup or 1.0}
            for r in runs_sorted
            if r.speedup is not None
        ]
        worker_counts = [dp["worker_count"] for dp in data_points]
        speedups = [dp["speedup"] for dp in data_points]
        efficiencies = [
            (r.speedup or 1.0) / r.worker_count * 100
            for r in runs_sorted
            if r.speedup is not None
        ]

        # ── Curve fit ──────────────────────────────────────────────────────────
        target_wc = sorted(set(worker_counts + [16, 32]))
        fit_result = predict_scalability(data_points, target_wc)

        parallel_fraction = fit_result.get("parallel_fraction")
        serial_fraction = (1.0 - parallel_fraction) if parallel_fraction is not None else None
        r_squared = fit_result.get("r_squared")
        theoretical_max = fit_result.get("theoretical_max_speedup")

        # ── Best run for diagnosis ─────────────────────────────────────────────
        best_run = max(runs_sorted, key=lambda r: r.speedup or 0.0)
        best_efficiency = max(efficiencies) if efficiencies else 0.0
        best_speedup = max(speedups) if speedups else 1.0
        worst_worker_count = worker_counts[-1] if worker_counts else 1

        # ── Detect speedup degradation ─────────────────────────────────────────
        speedup_degraded = False
        if len(speedups) >= 3:
            # Check if speedup decreases in 2+ consecutive steps
            degradations = sum(1 for i in range(1, len(speedups)) if speedups[i] < speedups[i-1])
            speedup_degraded = degradations >= 2

        # ── Diagnosis ──────────────────────────────────────────────────────────
        obs = best_run.observability_data or {}
        diag = diagnose(
            workload_type=workload_type,
            input_size=input_size,
            worker_count=best_run.worker_count,
            execution_time=best_run.execution_time or 0.001,
            sequential_time=best_run.sequential_time or 0.001,
            speedup=best_run.speedup or 1.0,
            efficiency=best_run.efficiency or 0.0,
            cpu_usage=best_run.cpu_usage,
            memory_usage=best_run.memory_usage,
            peak_memory_mb=best_run.peak_memory_mb,
            observability_data=obs or None,
        )

        # ── Grade ──────────────────────────────────────────────────────────────
        grade, grade_rationale = _grade(parallel_fraction, best_efficiency, speedup_degraded)

        # ── Per-worker breakdown ───────────────────────────────────────────────
        breakdown = []
        for r in runs_sorted:
            if r.speedup is not None:
                eff = (r.speedup / r.worker_count) * 100
                breakdown.append({
                    "worker_count": r.worker_count,
                    "execution_time_s": round(r.execution_time or 0.0, 6),
                    "speedup": round(r.speedup, 4),
                    "efficiency_pct": round(eff, 1),
                    "benchmark_id": r.id,
                })

        # ── Amdahl ceiling prediction ──────────────────────────────────────────
        amdahl_ceiling_text = (
            f"Theoretical maximum speedup ≈ {theoretical_max:.1f}× (Amdahl's Law)"
            if theoretical_max else "Insufficient data for ceiling prediction."
        )

        optimal_workers = _optimal_worker_count(fit_result, worker_counts)
        max_useful_workers = _max_useful_workers(parallel_fraction, efficiency_threshold=0.50)

        # ── Build report ───────────────────────────────────────────────────────
        report: dict[str, Any] = {
            "workload_name": workload_name,
            "workload_type": workload_type,
            "input_size": input_size,
            "benchmark_date": runs_sorted[0].created_at.isoformat(),
            "generated_at": datetime.utcnow().isoformat(),
            "run_ids": run_ids,
            "worker_counts_tested": worker_counts,
            "scaling_data": breakdown,
            "analysis": {
                "parallel_fraction": round(parallel_fraction, 4) if parallel_fraction is not None else None,
                "serial_fraction": round(serial_fraction, 4) if serial_fraction is not None else None,
                "best_speedup": round(best_speedup, 4),
                "best_efficiency_pct": round(best_efficiency, 1),
                "theoretical_ceiling": theoretical_max,
                "amdahl_ceiling_note": amdahl_ceiling_text,
                "model_fit": fit_result.get("model_used"),
                "r_squared": round(r_squared, 4) if r_squared is not None else None,
                "speedup_degraded": speedup_degraded,
            },
            "diagnosis": {
                "primary_bottleneck": diag.primary,
                "diagnostic_strength_pct": round(diag.diagnostic_strength * 100, 1),
                "secondary_bottleneck": diag.secondary,
                "evidence": [e.to_dict() for e in diag.evidence],
                "executive_summary": diag.executive_summary,
            },
            "certification": {
                "grade": grade,
                "rationale": grade_rationale,
                "grade_description": _grade_description(grade),
            },
            "recommendations": {
                "optimal_worker_count": optimal_workers,
                "max_useful_worker_count": max_useful_workers,
                "expected_scaling_limit": amdahl_ceiling_text,
                "optimization_priorities": diag.optimization_opportunities,
                "expected_improvement_pct": diag.expected_improvement_pct,
            },
        }

        report["export_markdown"] = _to_markdown(report)
        report["export_html"] = _to_html(report)

        return report


# ── Helper functions ──────────────────────────────────────────────────────────

def _optimal_worker_count(fit_result: dict, worker_counts: list[int]) -> int:
    """Find worker count where marginal efficiency gain drops below 10%."""
    predictions = fit_result.get("predictions", [])
    if not predictions:
        return worker_counts[-1] if worker_counts else 1

    best_wc = 1
    prev_speedup = 1.0
    for p in sorted(predictions, key=lambda x: x["worker_count"]):
        wc = p["worker_count"]
        sp = p["predicted_speedup"]
        if wc <= 1:
            prev_speedup = sp
            best_wc = wc
            continue
        marginal_gain = (sp - prev_speedup) / prev_speedup if prev_speedup > 0 else 0
        if marginal_gain < 0.08:  # < 8% gain
            break
        best_wc = wc
        prev_speedup = sp
    return best_wc


def _max_useful_workers(parallel_fraction: float | None, efficiency_threshold: float = 0.50) -> int | None:
    """Compute max workers where efficiency stays above threshold."""
    if parallel_fraction is None:
        return None
    pf = parallel_fraction
    if pf <= 0:
        return 1
    # Amdahl: efficiency = S(P)/P = 1/(P*(1-p) + p)
    # Find P where efficiency = threshold:
    # threshold = 1 / (P*(1-pf) + pf)
    # P*(1-pf) + pf = 1/threshold
    # P = (1/threshold - pf) / (1-pf)
    if abs(1 - pf) < 1e-9:
        return None  # 100% parallel — scales forever
    p_max = (1.0 / efficiency_threshold - pf) / (1.0 - pf)
    return max(1, int(p_max))


def _grade_description(grade: str) -> str:
    return {
        "A+": "Exceptional scaling — workload is highly parallelizable with minimal overhead.",
        "A": "Excellent scaling — strong parallel efficiency, ready for production multi-core deployment.",
        "B": "Good scaling — benefits significantly from parallelism with manageable overhead.",
        "C": "Fair scaling — parallel gains exist but overhead limits scalability.",
        "D": "Poor scaling — marginal parallel benefit, significant overhead present.",
        "F": "Failing — workload does not benefit from parallelism or scaling is negative.",
    }.get(grade, "Unknown grade.")


def _to_markdown(report: dict) -> str:
    """Generate Markdown export of the certification report."""
    a = report["analysis"]
    d = report["diagnosis"]
    c = report["certification"]
    r = report["recommendations"]

    lines = [
        f"# Scalability Certification Report",
        f"",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Workload | **{report['workload_name']}** |",
        f"| Type | `{report['workload_type']}` |",
        f"| Input Size | {report['input_size']:,} |",
        f"| Benchmark Date | {report['benchmark_date'][:10]} |",
        f"| Generated | {report['generated_at'][:19]} UTC |",
        f"",
        f"## Certification Grade",
        f"",
        f"### **{c['grade']}** — {c['grade_description']}",
        f"",
        f"_{c['rationale']}_",
        f"",
        f"## Scaling Analysis",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Best Speedup | {a['best_speedup']:.2f}× |",
        f"| Best Efficiency | {a['best_efficiency_pct']:.1f}% |",
        f"| Parallel Fraction | {a['parallel_fraction']:.1%} |" if a['parallel_fraction'] else "| Parallel Fraction | N/A |",
        f"| Serial Fraction | {a['serial_fraction']:.1%} |" if a['serial_fraction'] else "| Serial Fraction | N/A |",
        f"| Model Fit | {a['model_fit']} (R²={a['r_squared']}) |" if a['r_squared'] else f"| Model Fit | {a['model_fit']} |",
        f"| Theoretical Ceiling | {a['theoretical_ceiling']:.1f}× |" if a['theoretical_ceiling'] else "| Theoretical Ceiling | N/A |",
        f"",
        f"## Worker Count Results",
        f"",
        f"| Workers | Time (s) | Speedup | Efficiency |",
        f"|---------|----------|---------|------------|",
    ]
    for row in report["scaling_data"]:
        lines.append(
            f"| {row['worker_count']} | {row['execution_time_s']:.4f} | "
            f"{row['speedup']:.2f}× | {row['efficiency_pct']:.1f}% |"
        )

    lines += [
        f"",
        f"## Diagnosis",
        f"",
        f"**Primary Bottleneck:** {d['primary_bottleneck'].replace('_', ' ').title()} "
        f"(diagnostic strength: {d['diagnostic_strength_pct']:.0f}%)",
        f"",
        f"**Evidence:**",
        f"",
    ]
    for e in d["evidence"]:
        lines.append(f"- {e['metric']} = {e['value']}")

    lines += [
        f"",
        f"> {d['executive_summary']}",
        f"",
        f"## Recommendations",
        f"",
        f"| Recommendation | Value |",
        f"|----------------|-------|",
        f"| Optimal Workers | {r['optimal_worker_count']} |",
        f"| Max Useful Workers | {r['max_useful_worker_count'] or 'Unbounded'} |",
        f"| Expected Improvement | {r['expected_improvement_pct']:.0f}% |",
        f"",
        f"**Optimization Priorities:**",
        f"",
    ]
    for i, opt in enumerate(r["optimization_priorities"], 1):
        lines.append(f"{i}. {opt}")

    lines += [
        f"",
        f"---",
        f"*Generated by ScaleLab AI Performance Engineering Platform*",
    ]
    return "\n".join(lines)


def _to_html(report: dict) -> str:
    """Generate branded PDF-ready HTML certificate — all inline styles, no CSS classes for layout."""
    grade = report["certification"]["grade"]
    grade_colors = {
        "A+": "#10b981", "A": "#22c55e", "B": "#84cc16",
        "C": "#eab308", "D": "#f97316", "F": "#ef4444",
    }
    grade_color = grade_colors.get(grade, "#94a3b8")
    grade_bg = grade_colors.get(grade, "#94a3b8") + "22"

    pf = report["analysis"]["parallel_fraction"]
    pf_str = f"{pf:.0%}" if pf is not None else "—"

    TD  = "border:1px solid #e2e8f0;padding:9px 14px;color:#334155;font-size:13px;"
    TH  = "background:#f8fafc;border:1px solid #e2e8f0;padding:9px 14px;text-align:left;font-weight:600;color:#475569;font-size:11px;text-transform:uppercase;letter-spacing:0.3px;"

    scaling_rows = "".join(
        f"<tr>"
        f"<td style='{TD}'>{r['worker_count']}×</td>"
        f"<td style='{TD}'>{r['execution_time_s']:.4f} s</td>"
        f"<td style='{TD}color:{grade_color};font-weight:700;'>{r['speedup']:.2f}×</td>"
        f"<td style='{TD}'>{r['efficiency_pct']:.1f}%</td>"
        f"</tr>"
        for r in report["scaling_data"]
    )
    rec_items = "".join(
        f"<li style='margin-bottom:4px;color:#334155;font-size:13px;'>{_html.escape(o)}</li>"
        for o in report["recommendations"]["optimization_priorities"]
    )

    def kpi(value: str, label: str, color: str = "#0f172a") -> str:
        return (
            f"<td style='width:25%;background:#f8fafc;border:1px solid #e2e8f0;"
            f"border-radius:8px;padding:16px 14px;text-align:center;'>"
            f"<div style='font-size:22px;font-weight:700;color:{color};line-height:1;'>{value}</div>"
            f"<div style='font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;margin-top:5px;'>{label}</div>"
            f"</td>"
        )

    logo_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="48" height="48">
  <path fill="#22d3ee" d="M225 512H15c-8.285 0-15-6.715-15-15V287c0-8.285 6.715-15 15-15h210c8.285 0 15 6.715 15 15v210c0 8.285-6.715 15-15 15z"/>
  <path fill="#0891b2" d="M4.395 507.605A14.953 14.953 0 0 0 15 512h210c8.285 0 15-6.715 15-15V287c0-4.133-1.672-7.875-4.375-10.586z"/>
  <path fill="#3b82f6" d="M497 420H107c-8.285 0-15-6.715-15-15V15c0-8.285 6.715-15 15-15h390c8.285 0 15 6.715 15 15v390c0 8.285-6.715 15-15 15z"/>
  <path fill="#1d4ed8" d="M96.402 415.613A14.951 14.951 0 0 0 107 420h390c8.285 0 15-6.715 15-15V15c0-4.121-1.664-7.852-4.355-10.563z"/>
  <path fill="#ffffff" d="M422.773 73.02h-65.847c-8.285 0-15 6.714-15 15 0 8.285 6.715 15 15 15h30.34L261.145 229.145c-5.86 5.855-5.86 15.355 0 21.21 2.93 2.93 6.765 4.395 10.605 4.395s7.68-1.465 10.605-4.395l125.418-125.414v28.84c0 8.285 6.715 15 15 15 8.286 0 15-6.715 15-15V88.02c0-8.286-6.714-15-15-15z"/>
  <path fill="#bfdbfe" d="M261.43 250.613a14.937 14.937 0 0 0 10.32 4.137c3.84 0 7.68-1.465 10.605-4.395l125.418-125.417v28.843c0 8.281 6.715 15 15 15 8.286 0 15-6.719 15-15V88.02c0-3.817-1.437-7.29-3.785-9.938z"/>
</svg>"""

    S = "font-family:'Segoe UI',system-ui,sans-serif;"  # base font shorthand

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Scalability Certificate — {_html.escape(report['workload_name'])}</title>
<style>* {{margin:0;padding:0;box-sizing:border-box;}} body {{background:#f8fafc;width:860px;}}</style>
</head>
<body>
<!-- PAGE WRAPPER -->
<div style="{S}background:#fff;border-radius:12px;border:1px solid #e2e8f0;overflow:hidden;margin:32px;">

  <!-- ── HEADER ── -->
  <table style="width:100%;background:linear-gradient(135deg,#0f172a,#1e3a5f);border-collapse:collapse;">
    <tr>
      <td style="padding:24px 36px;vertical-align:middle;">
        <table style="border-collapse:collapse;"><tr>
          <td style="vertical-align:middle;padding-right:14px;">{logo_svg}</td>
          <td style="vertical-align:middle;">
            <div style="{S}color:#f1f5f9;font-size:22px;font-weight:700;line-height:1.2;">ScaleLab<span style="color:#22d3ee;"> AI</span></div>
            <div style="{S}color:#64748b;font-size:11px;letter-spacing:2px;text-transform:uppercase;margin-top:3px;">Performance Intelligence</div>
          </td>
        </tr></table>
      </td>
      <td style="padding:24px 36px;vertical-align:middle;text-align:right;">
        <div style="{S}color:#94a3b8;font-size:11px;letter-spacing:2px;text-transform:uppercase;">Official Report</div>
        <div style="{S}color:#e2e8f0;font-size:15px;font-weight:600;margin-top:4px;">Scalability Certification</div>
      </td>
    </tr>
  </table>

  <!-- ── GRADE HERO ── -->
  <table style="width:100%;border-collapse:collapse;border-bottom:1px solid #f1f5f9;">
    <tr>
      <td style="padding:32px 36px;vertical-align:middle;width:160px;">
        <!-- Grade badge: outer div clips border-radius, inner table centers text -->
        <div style="width:96px;height:96px;border-radius:12px;border:3px solid {grade_color};background:{grade_bg};overflow:hidden;">
          <table style="width:96px;height:90px;border-collapse:collapse;"><tr>
            <td style="{S}text-align:center;vertical-align:middle;font-size:56px;font-weight:900;color:{grade_color};letter-spacing:-2px;line-height:1;">{grade}</td>
          </tr></table>
        </div>
      </td>
      <td style="padding:32px 36px 32px 0;vertical-align:middle;">
        <div style="{S}font-size:18px;font-weight:700;color:#0f172a;margin-bottom:5px;">{_html.escape(report['certification']['grade_description'])}</div>
        <div style="{S}color:#475569;font-size:13px;line-height:1.55;">{_html.escape(report['certification']['rationale'])}</div>
        <table style="border-collapse:collapse;margin-top:12px;"><tr>
          <td style="{S}font-size:12px;color:#64748b;padding-right:24px;"><strong style="color:#334155;">Workload</strong> {_html.escape(report['workload_name'])}</td>
          <td style="{S}font-size:12px;color:#64748b;padding-right:24px;"><strong style="color:#334155;">Input Size</strong> {report['input_size']:,}</td>
          <td style="{S}font-size:12px;color:#64748b;padding-right:24px;"><strong style="color:#334155;">Date</strong> {report['benchmark_date'][:10]}</td>
          <td style="{S}font-size:12px;color:#64748b;"><strong style="color:#334155;">Runs</strong> {len(report['scaling_data'])}</td>
        </tr></table>
      </td>
    </tr>
  </table>

  <!-- ── BODY ── -->
  <div style="padding:28px 36px;">

    <!-- KPI row -->
    <table style="width:100%;border-collapse:separate;border-spacing:10px 0;margin-left:-10px;margin-bottom:28px;">
      <tr>
        {kpi(f"{report['analysis']['best_speedup']:.2f}×", "Best Speedup", grade_color)}
        {kpi(f"{report['analysis']['best_efficiency_pct']:.1f}%", "Peak Efficiency")}
        {kpi(pf_str, "Parallel Fraction")}
        {kpi(str(report['recommendations']['optimal_worker_count']), "Optimal Workers")}
      </tr>
    </table>

    <!-- Scaling Results -->
    <div style="{S}font-size:12px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #f1f5f9;">Scaling Results</div>
    <table style="border-collapse:collapse;width:100%;margin-bottom:24px;">
      <tr>
        <th style="{TH}">Workers</th>
        <th style="{TH}">Execution Time</th>
        <th style="{TH}">Speedup</th>
        <th style="{TH}">Efficiency</th>
      </tr>
      {scaling_rows}
    </table>

    <!-- Diagnosis -->
    <div style="{S}font-size:12px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #f1f5f9;">Bottleneck Diagnosis</div>
    <div style="background:#f8fafc;border-left:4px solid {grade_color};border-radius:0 8px 8px 0;padding:14px 18px;margin-bottom:24px;">
      <div style="{S}font-size:14px;font-weight:700;color:#0f172a;margin-bottom:6px;">{report['diagnosis']['primary_bottleneck'].replace('_',' ').title()} &nbsp;·&nbsp; {report['diagnosis']['diagnostic_strength_pct']:.0f}% confidence</div>
      <div style="{S}font-size:13px;color:#334155;line-height:1.55;">{_html.escape(report['diagnosis']['executive_summary'])}</div>
    </div>

    <!-- Recommendations -->
    <div style="{S}font-size:12px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #f1f5f9;">Optimization Priorities</div>
    <ol style="padding-left:20px;">{rec_items}</ol>

  </div>

  <!-- ── FOOTER ── -->
  <table style="width:100%;border-collapse:collapse;background:#f8fafc;border-top:1px solid #e2e8f0;">
    <tr>
      <td style="{S}padding:12px 36px;font-size:11px;color:#94a3b8;">Generated by ScaleLab AI &nbsp;·&nbsp; {_html.escape(report['generated_at'][:19])} UTC</td>
      <td style="{S}padding:12px 36px;font-size:11px;color:#94a3b8;text-align:right;">scalelab-ai &nbsp;·&nbsp; Distributed Performance Intelligence</td>
    </tr>
  </table>

</div>
</body>
</html>"""
