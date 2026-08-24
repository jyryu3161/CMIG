"""Round-7 T2 acceptance: first-class graph, profile charts, and real ko/en i18n."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtWebEngineWidgets")

import pyarrow as pa  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

import cmig.gui.app as app_module  # noqa: E402
import cmig.gui.graph_view as graph_view_module  # noqa: E402
from cmig.core.engine import SolveResult  # noqa: E402
from cmig.core.interactions import build_tidy  # noqa: E402
from cmig.core.tidy import PROFILE_SCHEMA  # noqa: E402
from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.graph_data import graph_payload  # noqa: E402
from cmig.gui.views import (  # noqa: E402
    DivergingProfileChart,
    ExternalProfileView,
    MemberContributionChart,
    member_contribution_rows,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _community_bundle():
    result = SolveResult(
        objective=0.9,
        member_growth={"A": 0.5, "B": 0.4},
        abundances={"A": 0.25, "B": 0.75},
        external_exchange={"ac": -1.75},
        member_exchange={"A": {"ac": 8.0}, "B": {"ac": -5.0}},
        status="optimal",
        flux_report_status="full",
        growth_solver="gurobi",
        flux_solver="gurobi",
        members=["A", "B"],
    )
    bundle = build_tidy(result)
    profile = bundle.profile.to_pylist()
    profile[0]["fva_lo"] = -2.0
    profile[0]["fva_hi"] = -1.0
    bundle.profile = pa.Table.from_pylist(profile, schema=PROFILE_SCHEMA)
    return bundle


def _stub_graph_views(monkeypatch):
    """Keep shell-wiring tests independent of Chromium; renderer tests cover the real widget."""

    class GraphStub(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._base_payload = None

        def set_bundle(self, bundle, gate=None):
            self._base_payload = graph_payload(bundle, gate)

        def set_payload(self, payload):
            self._base_payload = payload

        def clear(self):
            self._base_payload = {"elements": []}

    monkeypatch.setattr(app_module, "InteractionGraphView", GraphStub)
    monkeypatch.setattr(graph_view_module, "InteractionGraphView", GraphStub)


def test_open_run_feeds_first_class_graph_badge_and_both_profile_charts(tmp_path, monkeypatch):
    _app()
    _stub_graph_views(monkeypatch)
    bundle = _community_bundle()
    bundle.write(tmp_path)
    (tmp_path / "manifest.json").write_text(
        '{"run_hash":"round7","provenance":{"namespace":{"policy":"assume_bigg"}}}'
    )

    window = build_main_window()
    window.load_run_dir(tmp_path)

    labels = [window.tabs.tabText(index) for index in range(window.tabs.count())]
    assert "Graph" in labels
    assert window.tabs.indexOf(window.graph_tab) >= 0
    assert window.graph_view._base_payload is not None
    assert window.graph_view._base_payload["elements"]
    assert "CONFIRMED" in window.graph_gate_badge.text()
    assert window.profile_view.net_chart.has_fva is True
    assert window.profile_view.net_chart.rows[0]["fva_lo"] == -2.0
    assert window.profile_view.member_chart.rows

    contributions = {
        item["member"]: item["value"]
        for item in window.profile_view.member_chart.rows[0]["contributions"]
    }
    assert contributions == {"A": 2.0, "B": -3.75}
    assert "× recorded abundance" in window.profile_view.contribution_basis_label.text()


def test_member_contribution_bridge_excludes_allocated_cross_feeding():
    bundle = _community_bundle()
    rows, warnings = member_contribution_rows(bundle)
    assert warnings == []
    assert len(rows) == 1
    assert {item["member"]: item["value"] for item in rows[0]["contributions"]} == {
        "A": 2.0,
        "B": -3.75,
    }
    direct_edge_count = sum(
        edge["edge_type"] != "cross_feeding" for edge in bundle.edges.to_pylist()
    )
    assert direct_edge_count == 2
    assert bundle.edges.num_rows > direct_edge_count


def test_profile_charts_do_not_turn_missing_values_into_zero():
    _app()
    view = ExternalProfileView()
    view.load_profile(
        [
            {"metabolite": "missing", "net_flux": None, "fva_lo": None, "fva_hi": None},
            {"metabolite": "failed", "net_flux": float("nan")},
            {"metabolite": "measured", "net_flux": 0.0},
        ]
    )
    assert [row["metabolite"] for row in view.net_chart.rows] == ["measured"]
    assert view.table.item(0, 1).text() == "—"
    assert view.table.item(1, 1).text() == "—"


def test_qt_native_charts_paint_offscreen():
    app = _app()
    profile = DivergingProfileChart()
    profile.resize(640, 280)
    profile.set_rows(
        [
            {"metabolite": "ac", "net_flux": 4.0, "fva_lo": 3.0, "fva_hi": 5.0},
            {"metabolite": "glc", "net_flux": -8.0, "fva_lo": None, "fva_hi": None},
        ]
    )
    members = MemberContributionChart()
    members.resize(640, 280)
    members.set_rows(
        [
            {
                "metabolite": "ac",
                "contributions": [
                    {"member": "A", "value": 2.0},
                    {"member": "B", "value": -1.0},
                ],
            }
        ]
    )
    app.processEvents()
    assert not profile.grab().isNull()
    assert not members.grab().isNull()


def test_korean_tabs_toolbar_and_loaded_status_are_translated(tmp_path, monkeypatch):
    _app()
    _stub_graph_views(monkeypatch)
    _community_bundle().write(tmp_path)
    window = build_main_window(lang="ko")
    window.load_run_dir(tmp_path)
    labels = [window.tabs.tabText(index) for index in range(window.tabs.count())]
    assert labels == ["모델", "탐색", "숙주", "동역학", "그래프", "외부 프로필"]
    assert window.open_run_action.text() == "실행 열기"
    assert window.advanced_tools_action.text() == "고급 도구 표시"
    assert window.statusBar().currentMessage().startswith("실행 불러옴:")
