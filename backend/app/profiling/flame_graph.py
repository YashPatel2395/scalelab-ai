"""
Flame Graph SVG Generator
──────────────────────────
Generates an SVG visualization of cProfile hotspot data.

Since cProfile measures cumulative time (not stack samples), this renders
a "Top-Down Profile" chart — a horizontal bar chart sorted by cumulative
time with a warm color scale.  This is technically accurate for cProfile
and commonly called a "profile flame chart" in performance tooling.

Output: a self-contained SVG string, no external assets.
"""

from __future__ import annotations

import html
import math
from typing import Any


def _bar_color(hotness: float, is_app: bool = True) -> str:
    """Map hotness [0,1] to bar color.
    App functions: teal→cyan (high-visibility).
    Framework functions: dark slate (muted).
    """
    if is_app:
        # Dark teal → bright cyan as hotness increases
        r = int(8 + 14 * hotness)
        g = int(100 + 112 * hotness)
        b = int(130 + 82 * hotness)
        return f"rgb({min(r,255)},{min(g,255)},{min(b,255)})"
    else:
        # Very muted dark-slate regardless of hotness
        v = int(42 + 25 * hotness)
        return f"rgb({v},{int(v + 6)},{int(v + 16)})"


def generate_hotspot_svg(
    hotspots: list[dict[str, Any]],
    title: str = "Function Profile",
    width: int = 900,
    bar_height: int = 24,
    padding: int = 8,
) -> str:
    """
    Generate a self-contained SVG flame chart from cProfile hotspot data.

    Parameters
    ----------
    hotspots:
        List of dicts with keys: function, calls, total_time_ms, self_time_ms, pct_of_total
    title:
        Chart title.
    width:
        SVG width in pixels.

    Returns
    -------
    SVG string (utf-8 text).
    """
    if not hotspots:
        return _empty_svg(title, width)

    top_n = hotspots[:20]
    max_pct = max(h.get("pct_of_total", 0) for h in top_n) or 1.0

    label_width = 320
    bar_area = width - label_width - 140  # 140 for stats columns

    header_height = 50
    footer_height = 30
    total_height = header_height + len(top_n) * (bar_height + padding) + footer_height

    lines: list[str] = []
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{total_height}" '
        f'style="background:#0f172a;font-family:monospace,sans-serif;">'
    )

    # Title
    lines.append(
        f'<text x="{width//2}" y="28" text-anchor="middle" '
        f'fill="#94a3b8" font-size="14" font-weight="bold">{html.escape(title)}</text>'
    )

    # Column headers
    header_y = header_height - 4
    lines.append(f'<text x="{label_width - 4}" y="{header_y}" text-anchor="end" fill="#475569" font-size="10">Function</text>')
    lines.append(f'<text x="{label_width + bar_area + 4}" y="{header_y}" fill="#475569" font-size="10">Calls</text>')
    lines.append(f'<text x="{label_width + bar_area + 50}" y="{header_y}" fill="#475569" font-size="10">Total</text>')
    lines.append(f'<text x="{label_width + bar_area + 96}" y="{header_y}" fill="#475569" font-size="10">%</text>')

    for i, h in enumerate(top_n):
        y = header_height + i * (bar_height + padding)
        pct = h.get("pct_of_total", 0)
        hotness = pct / max_pct
        is_app = h.get("is_app", True)
        color = _bar_color(hotness, is_app)
        bar_w = max(2, int(bar_area * pct / max_pct))

        # Function label (truncated)
        fn_raw = h.get("function", "")
        fn_label = _short_label(fn_raw, max_chars=42)

        # Background row (alternating)
        bg = "#1e293b" if i % 2 == 0 else "#0f172a"
        lines.append(
            f'<rect x="0" y="{y}" width="{width}" height="{bar_height}" fill="{bg}"/>'
        )

        # Bar
        lines.append(
            f'<rect x="{label_width}" y="{y + 4}" width="{bar_w}" height="{bar_height - 8}" '
            f'fill="{color}" rx="2" opacity="0.9">'
            f'<title>{html.escape(fn_raw)}</title>'
            f'</rect>'
        )

        # Function label
        text_y = y + bar_height // 2 + 4
        label_fill = "#cbd5e1" if is_app else "#64748b"
        lines.append(
            f'<text x="{label_width - 6}" y="{text_y}" text-anchor="end" '
            f'fill="{label_fill}" font-size="11">{html.escape(fn_label)}</text>'
        )

        # Stats: calls, total_ms, pct
        calls_str = _fmt_num(h.get("calls", 0))
        ms_str = f'{h.get("total_time_ms", 0):.1f}ms'
        pct_str = f'{pct:.1f}%'

        lines.append(
            f'<text x="{label_width + bar_area + 4}" y="{text_y}" '
            f'fill="#64748b" font-size="10">{calls_str}</text>'
        )
        lines.append(
            f'<text x="{label_width + bar_area + 50}" y="{text_y}" '
            f'fill="#64748b" font-size="10">{ms_str}</text>'
        )
        lines.append(
            f'<text x="{label_width + bar_area + 96}" y="{text_y}" '
            f'fill="{color}" font-size="10" font-weight="bold">{pct_str}</text>'
        )

    # Footer
    footer_y = total_height - 10
    lines.append(
        f'<text x="{width//2}" y="{footer_y}" text-anchor="middle" '
        f'fill="#334155" font-size="9">Generated by ScaleLab AI Profiler — '
        f'cProfile cumulative-time chart</text>'
    )
    lines.append('</svg>')

    return "\n".join(lines)


def _empty_svg(title: str, width: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="80" '
        f'style="background:#0f172a;">'
        f'<text x="{width//2}" y="45" text-anchor="middle" fill="#475569" font-size="13">'
        f'No profiling data available for {html.escape(title)}</text>'
        f'</svg>'
    )


def _short_label(fn: str, max_chars: int = 42) -> str:
    """Shorten a cProfile label 'file:lineno(func)' for display."""
    if "(" in fn and fn.endswith(")"):
        func_name = fn.split("(")[-1][:-1]
        # Get filename short form
        file_part = fn.split(":")[0].split("/")[-1].replace(".py", "")
        label = f"{file_part}::{func_name}"
    else:
        label = fn.split("/")[-1]

    if len(label) > max_chars:
        label = "…" + label[-(max_chars - 1):]
    return label


def _fmt_num(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n/1_000:.0f}K"
    return str(n)
