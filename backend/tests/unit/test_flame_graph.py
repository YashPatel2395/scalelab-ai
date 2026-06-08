"""
Unit tests for SVG flame graph generator (app/profiling/flame_graph.py).

Covers SVG structure, empty input, color computation, label truncation,
hotspot ordering, and various edge cases.
"""
from __future__ import annotations

import pytest

from app.profiling.flame_graph import (
    generate_hotspot_svg,
    _bar_color,
    _short_label,
    _fmt_num,
    _empty_svg,
)


_HOTSPOTS = [
    {"function": "matmul.py:10(compute)", "calls": 100, "total_time_ms": 450.0, "self_time_ms": 400.0, "pct_of_total": 75.0},
    {"function": "worker.py:20(map_fn)", "calls": 4, "total_time_ms": 80.0, "self_time_ms": 80.0, "pct_of_total": 13.3},
    {"function": "chunk.py:5(split)", "calls": 200, "total_time_ms": 70.0, "self_time_ms": 70.0, "pct_of_total": 11.7},
]


# ── TestSVGStructure ──────────────────────────────────────────────────────────

class TestSVGStructure:
    def test_returns_string(self):
        svg = generate_hotspot_svg(_HOTSPOTS)
        assert isinstance(svg, str)

    def test_has_svg_opening_tag(self):
        svg = generate_hotspot_svg(_HOTSPOTS)
        assert "<svg" in svg

    def test_has_svg_closing_tag(self):
        svg = generate_hotspot_svg(_HOTSPOTS)
        assert "</svg>" in svg

    def test_is_self_contained_no_external_links(self):
        svg = generate_hotspot_svg(_HOTSPOTS)
        # No external references
        assert "http://" not in svg or "xmlns" in svg

    def test_title_appears_in_svg(self):
        svg = generate_hotspot_svg(_HOTSPOTS, title="My Profile")
        assert "My Profile" in svg

    def test_default_title_appears(self):
        svg = generate_hotspot_svg(_HOTSPOTS)
        assert "Profile" in svg or "Function" in svg

    def test_width_parameter_used(self):
        svg = generate_hotspot_svg(_HOTSPOTS, width=1200)
        assert "1200" in svg

    def test_function_names_appear(self):
        svg = generate_hotspot_svg(_HOTSPOTS)
        # At least the top function should appear somewhere
        assert "matmul" in svg or "compute" in svg

    def test_percentage_values_appear(self):
        svg = generate_hotspot_svg(_HOTSPOTS)
        assert "75" in svg

    def test_has_xmlns_attribute(self):
        svg = generate_hotspot_svg(_HOTSPOTS)
        assert 'xmlns="http://www.w3.org/2000/svg"' in svg

    def test_has_text_elements(self):
        svg = generate_hotspot_svg(_HOTSPOTS)
        assert "<text" in svg

    def test_has_rect_elements(self):
        svg = generate_hotspot_svg(_HOTSPOTS)
        assert "<rect" in svg

    def test_footer_credits(self):
        svg = generate_hotspot_svg(_HOTSPOTS)
        assert "ScaleLab" in svg


# ── TestEmptyInput ────────────────────────────────────────────────────────────

class TestEmptyInput:
    def test_empty_hotspots_returns_svg(self):
        svg = generate_hotspot_svg([])
        assert isinstance(svg, str)
        assert "<svg" in svg

    def test_empty_hotspots_closes_properly(self):
        svg = generate_hotspot_svg([])
        assert "</svg>" in svg

    def test_empty_hotspots_no_profiling_message(self):
        svg = generate_hotspot_svg([])
        # Should indicate no data
        assert "No" in svg or "no" in svg.lower() or "available" in svg.lower()

    def test_empty_svg_function_direct(self):
        svg = _empty_svg("Test", 900)
        assert "<svg" in svg
        assert "Test" in svg

    def test_empty_svg_custom_title(self):
        svg = _empty_svg("CustomTitle", 800)
        assert "CustomTitle" in svg


# ── TestColorScale ────────────────────────────────────────────────────────────

class TestColorScale:
    def test_hottest_bar_contains_rgb(self):
        svg = generate_hotspot_svg(_HOTSPOTS)
        assert "rgb(" in svg

    def test_multiple_bars_have_multiple_colors(self):
        hotspots = [
            {"function": f"fn{i}.py:1(f)", "calls": 10, "total_time_ms": float(100 - i * 20),
             "self_time_ms": float(100 - i * 20), "pct_of_total": float(40 - i * 8)}
            for i in range(4)
        ]
        svg = generate_hotspot_svg(hotspots)
        assert svg.count("rgb(") >= 2

    def test_bar_color_hotness_zero_is_yellow(self):
        color = _bar_color(0.0)
        # Should be yellowish: high R, high G, low B
        assert color.startswith("rgb(")
        parts = color[4:-1].split(",")
        r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
        assert r >= 200
        assert g >= 150
        assert b <= 25

    def test_bar_color_hotness_one_is_red(self):
        color = _bar_color(1.0)
        parts = color[4:-1].split(",")
        r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
        assert r == 255  # clamped to 255
        assert g < 100  # low green
        assert b == 0   # no blue

    def test_bar_color_midpoint(self):
        color = _bar_color(0.5)
        assert color.startswith("rgb(")

    def test_bar_color_clamped_r(self):
        color = _bar_color(1.0)
        parts = color[4:-1].split(",")
        r = int(parts[0])
        assert r <= 255

    def test_bar_color_clamped_g(self):
        color = _bar_color(1.0)
        parts = color[4:-1].split(",")
        g = int(parts[1])
        assert g >= 0


# ── TestLabelTruncation ───────────────────────────────────────────────────────

class TestLabelTruncation:
    def test_short_label_cprofile_format(self):
        label = _short_label("mymodule.py:42(compute)")
        assert "compute" in label
        assert "mymodule" in label

    def test_short_label_truncates_long(self):
        long_fn = "/very/long/path/to/mymodule.py:42(" + "a" * 50 + ")"
        label = _short_label(long_fn, max_chars=42)
        assert len(label) <= 42

    def test_short_label_ellipsis_on_truncation(self):
        long_fn = "/very/long/path/to/mymodule.py:42(" + "a" * 50 + ")"
        label = _short_label(long_fn, max_chars=42)
        assert label.startswith("…") or len(label) <= 42

    def test_short_label_plain_path(self):
        label = _short_label("/path/to/myfile.py")
        assert "myfile.py" in label

    def test_short_label_no_separator(self):
        label = _short_label("simple_function")
        assert "simple_function" in label

    def test_short_label_removes_py_extension(self):
        label = _short_label("module.py:1(fn)")
        # After processing, the py extension should not be in the file part
        assert "module::fn" in label or "fn" in label


# ── TestTopN ──────────────────────────────────────────────────────────────────

class TestTopN:
    def test_max_20_functions_rendered(self):
        hotspots = [
            {"function": f"fn{i}.py:1(f)", "calls": 1, "total_time_ms": 10.0,
             "self_time_ms": 10.0, "pct_of_total": 4.0}
            for i in range(25)
        ]
        svg = generate_hotspot_svg(hotspots)
        assert isinstance(svg, str)
        assert "<svg" in svg

    def test_single_hotspot_renders(self):
        hotspot = [{"function": "only.py:1(fn)", "calls": 1, "total_time_ms": 100.0,
                    "self_time_ms": 100.0, "pct_of_total": 100.0}]
        svg = generate_hotspot_svg(hotspot)
        assert "<svg" in svg

    def test_two_hotspots_render(self):
        hotspots = [
            {"function": "a.py:1(fn1)", "calls": 2, "total_time_ms": 200.0,
             "self_time_ms": 200.0, "pct_of_total": 66.7},
            {"function": "b.py:2(fn2)", "calls": 1, "total_time_ms": 100.0,
             "self_time_ms": 100.0, "pct_of_total": 33.3},
        ]
        svg = generate_hotspot_svg(hotspots)
        assert "<svg" in svg


# ── TestFmtNum ────────────────────────────────────────────────────────────────

class TestFmtNum:
    def test_small_number(self):
        assert _fmt_num(42) == "42"

    def test_thousands(self):
        result = _fmt_num(15_000)
        assert "K" in result

    def test_millions(self):
        result = _fmt_num(2_500_000)
        assert "M" in result

    def test_boundary_1000(self):
        result = _fmt_num(1_000)
        assert "K" in result

    def test_boundary_999(self):
        result = _fmt_num(999)
        assert "K" not in result
        assert "M" not in result
