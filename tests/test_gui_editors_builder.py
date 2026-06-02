"""Phase 0.4/2 — GUI Editors(Medium·Model Manager) + Builder(Community·Sandbox·Compare)
+ figure journal presets. offscreen 검증. Plan SC: SC-ME/MM/CB/CS/SC/JP.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.core.delta import DeltaResult, MetaboliteDelta  # noqa: E402
from cmig.core.medium_spec import MediumSpec  # noqa: E402
from cmig.gui.builder import (  # noqa: E402
    CommunityBuilderView,
    ConstraintSandboxView,
    ScenarioCompareView,
    SearchView,
)
from cmig.gui.editors import MediumEditor, ModelManagerPanel  # noqa: E402
from cmig.io.model_import import ModelSummary  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


# --- Medium Editor ---
def test_medium_editor_roundtrip():
    """SC-ME1: MediumSpec load → to_spec 라운드트립."""
    _app()
    ed = MediumEditor()
    ed.load_spec(MediumSpec(uptake={"EX_glc__D_e": 10.0, "EX_o2_e": 20.0}))
    assert ed.table.rowCount() == 2
    spec = ed.to_spec()
    assert spec.uptake == {"EX_glc__D_e": 10.0, "EX_o2_e": 20.0}


def test_medium_editor_validation_error():
    """SC-ME2: 음수 uptake → 검증 ValueError(silent 위장 금지)."""
    _app()
    ed = MediumEditor()
    ed.add_row("EX_glc__D_e", -5.0)
    with pytest.raises(ValueError):
        ed.to_spec()


def test_medium_editor_bad_number():
    """SC-ME3: 숫자 아닌 값 → ValueError + status 표시."""
    _app()
    ed = MediumEditor()
    ed.add_row("EX_x_e", 0.0)
    ed.table.item(0, 1).setText("not_a_number")
    with pytest.raises(ValueError):
        ed.to_spec()
    assert "Invalid" in ed.status.text()


# --- Model Manager ---
def test_model_manager_loads_summary():
    """SC-MM1: ModelSummary → 카운트·exchange·biomass 표시."""
    _app()
    mm = ModelManagerPanel()
    s = ModelSummary("e_coli_core", "sbml", "/p", 95, 72, 137,
                     ["EX_ac_e", "EX_glc__D_e"], ["BIOMASS"])
    mm.load_summary(s)
    assert "95 reactions" in mm.summary_label.text()
    assert mm.exchange_table.rowCount() == 2
    assert "BIOMASS" in mm.biomass_label.text()


# --- Community Builder ---
def test_community_builder_members_and_tradeoff():
    """SC-CB1: 멤버 추가/abundance + tradeoff 슬라이더."""
    _app()
    cb = CommunityBuilderView()
    cb.add_member("A", 0.6)
    cb.add_member("B", 0.4)
    assert cb.members() == {"A": 0.6, "B": 0.4}
    cb.f_slider.setValue(70)
    assert abs(cb.tradeoff_f() - 0.70) < 1e-9
    assert "0.70" in cb.f_label.text()
    cb.remove_member(0)
    assert set(cb.members()) == {"B"}


# --- Constraint Sandbox ---
def _delta(status: str = "ok") -> DeltaResult:
    return DeltaResult(
        profile=[
            MetaboliteDelta("ac", 5.0, 2.0, -3.0),
            MetaboliteDelta("but", 0.0, 0.0, 0.0),
        ],
        added_members=[], removed_members=[], growth_delta=-0.1,
        status=status, diagnostic=None if status == "ok" else '{"code":"infeasible"}',
    )


def test_sandbox_preview_and_commit():
    """SC-CS1: preview(비기록) + commit(run_hash) 표시 + significant 강조."""
    _app()
    sb = ConstraintSandboxView()
    sb.add_bound("EX_glc__D_e", -5.0, 1000.0)
    assert len(sb.constraints()) == 1
    sb.show_preview(_delta())
    assert "not recorded" in sb.status.text()
    assert sb.delta_view.rowCount() == 2
    sb.show_commit(_delta(), "abcdef123456")
    assert "committed" in sb.status.text()


def test_sandbox_preview_failed_explicit():
    """SC-CS2: preview 실패 → 명시(silent 위장 금지)."""
    _app()
    sb = ConstraintSandboxView()
    sb.show_preview(_delta(status="failed"))
    assert "failed" in sb.status.text()


# --- Scenario Compare ---
def test_scenario_compare():
    """SC-SC1: A/B delta + growth Δ 표시."""
    _app()
    sc = ScenarioCompareView()
    sc.load_comparison(_delta())
    assert sc.delta_view.rowCount() == 2
    assert "-0.1" in sc.growth_label.text()


def test_search_view_loads_advanced_summary():
    """SC-SR-GUI: advanced search summary → ranked table + Pareto badge."""
    _app()
    view = SearchView()
    assert view.targets_input.text() == "but"
    assert view.strategy_combo.currentText() == "auto"
    assert view.run_btn.text() == "Run Search"
    assert view.model_dir_input.placeholderText() == "Model folder"
    assert view.min_size_spin.value() == 2
    assert view.max_size_spin.value() == 2
    assert view.robustness_check.text() == "FVA"
    view.load_summary({
        "strategy": "exhaustive",
        "warnings": [],
        "top_ranked": {
            "ac": [
                {
                    "members": ["A", "B"],
                    "score": 1.2,
                    "target_flux": 1.2,
                    "community_growth": 0.4,
                    "robustness_fva_lo": 0.0,
                    "robustness_fva_hi": 2.0,
                    "robustness_status": "ok",
                    "status": "optimal",
                }
            ]
        },
        "pareto_frontier": [{"members": ["A", "B"], "ac": 1.2, "but": 0.8}],
    })
    assert view.table.rowCount() == 1
    assert view.table.item(0, 0).text() == "A+B"
    assert view.table.item(0, 5).text() == "0..2"
    assert "Pareto" in view.pareto_label.text()


# --- Journal presets ---
def test_journal_preset():
    """SC-JP1: PanelSpec.with_journal → 규격(width/height/dpi) 적용."""
    from cmig.render.client import RenderError
    from cmig.render.composer import PanelSpec
    nat = PanelSpec(kind="network").with_journal("nature")
    assert nat.width_in == 3.50 and nat.dpi == 300 and nat.journal_preset == "nature"
    with pytest.raises(RenderError, match="journal preset"):
        PanelSpec(kind="network").with_journal("bogus_journal")
