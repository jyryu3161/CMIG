"""Phase 1.3 — Figure Composer (ggraph/ComplexHeatmap/circlize 다중 패널). Plan SC: SC-FC1~FC5.

실제 R 렌더링 검증(Rscript + .Rlib 패키지). R 부재 시 skip(패널은 R 전용 — fallback 없음, 정직).
"""

from __future__ import annotations

import json

import pytest

from cmig.render.client import RenderError, rscript_available
from cmig.render.composer import PANEL_KINDS, FigureComposer, PanelSpec

_EDGES = [
    {"source_id": "A", "target_id": "pool", "weight": 5.0, "edge_type": "secretion"},
    {"source_id": "pool", "target_id": "B", "weight": 3.0, "edge_type": "uptake"},
    {"source_id": "A", "target_id": "B", "weight": 2.0, "edge_type": "cross_feeding"},
]
_MATRIX = [
    {"row_key": "A", "col_key": "ac", "value": 5.0},
    {"row_key": "A", "col_key": "glc", "value": -10.0},
    {"row_key": "B", "col_key": "ac", "value": -3.0},
    {"row_key": "B", "col_key": "but", "value": 4.0},
]

_needs_r = pytest.mark.skipif(not rscript_available(), reason="Rscript 부재 — R 전용 패널")


def test_panel_kinds():
    assert PANEL_KINDS == ("network", "heatmap", "chord")


def test_invalid_kind_rejected(tmp_path):
    """SC-FC4: 미지원 kind → RenderError."""
    with pytest.raises(RenderError, match="panel kind"):
        FigureComposer().render_panel(_EDGES, PanelSpec(kind="bogus"), tmp_path / "x.svg")


def test_render_unavailable_is_explicit(tmp_path):
    """SC-FC5: Rscript 부재 → RenderError(matplotlib fallback 없음 — 정직, silent 위장 금지)."""
    fc = FigureComposer(rscript="")          # 강제 unavailable
    with pytest.raises(RenderError, match="Rscript 부재"):
        fc.render_panel(_EDGES, PanelSpec(kind="network"), tmp_path / "x.svg")


@_needs_r
def test_render_network(tmp_path):
    """SC-FC1: ggraph network → SVG + figure_spec sidecar."""
    out = FigureComposer().render_panel(_EDGES, PanelSpec(kind="network"), tmp_path / "net.svg")
    assert out.exists() and out.stat().st_size > 1000
    sidecar = out.with_name(out.name + ".figure_spec.json")
    assert sidecar.exists() and json.loads(sidecar.read_text())["kind"] == "network"


@_needs_r
def test_render_chord(tmp_path):
    """SC-FC2: circlize chord → SVG."""
    out = FigureComposer().render_panel(_EDGES, PanelSpec(kind="chord"), tmp_path / "chord.svg")
    assert out.exists() and out.stat().st_size > 1000


@_needs_r
def test_render_heatmap(tmp_path):
    """SC-FC3: ComplexHeatmap → SVG (long→wide matrix)."""
    out = FigureComposer().render_panel(_MATRIX, PanelSpec(kind="heatmap"), tmp_path / "hm.svg")
    assert out.exists() and out.stat().st_size > 1000


@_needs_r
def test_render_panels_multi(tmp_path):
    """SC-FC1-3: 다중 패널 Figure Composer → 파일 목록."""
    panels = [
        (PanelSpec(kind="network", title="Net"), _EDGES),
        (PanelSpec(kind="chord", title="Chord"), _EDGES),
        (PanelSpec(kind="heatmap", title="HM"), _MATRIX),
    ]
    out = FigureComposer().render_panels(panels, tmp_path / "panels")
    assert len(out) == 3 and all(p.exists() and p.stat().st_size > 1000 for p in out)
