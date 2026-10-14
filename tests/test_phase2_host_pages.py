from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402

APP = QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path: Path):
    make_project(tmp_path / "p", ["a", "b", "host"])
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(tmp_path / "p")
    yield w
    w.close_project()


def test_two_host_pages(window) -> None:
    w = window
    assert w.analysis_pages["host"] is w.host_view
    assert w.analysis_pages["host_search"] is w.host_search_page
    assert not hasattr(w.host_view, "run_search_btn")
    assert w.host_search_page.target_input.text() == "ac"


def test_host_search_has_its_own_host_choice(window) -> None:
    w = window
    w.host_search_page.host_picker.set_selected(["host"])
    assert "host" not in w.host_search_page.model_picker.selected_ids()
    assert w.session.settings("host_search_model")["models"] == ["host"]


def test_host_search_result_goes_to_its_page(window, tmp_path: Path) -> None:
    w = window
    payload = {"target": "ac", "metric": "target_transfer", "status": "ok", "warnings": [],
               "top_ranked": [{"members": ["a"], "score": 1.0, "target_transfer": 0.5,
                               "community_growth": 0.2, "evaluation_status": "optimal",
                               "target_identifiability": "identified"}]}
    w._show_ranked("host_search", payload, tmp_path,
                   w.host_search_page.request_fields("host_search"))
    assert w.pages.currentWidget() is w.host_search_page
    assert w.host_search_page.results_panel.table.rowCount() == 1


def test_host_table_headers_fit_and_keep_units(window) -> None:
    view = window.host_view
    headers = [view.iface_table.horizontalHeaderItem(i).text() for i in range(4)]
    assert headers == ["Interface", "Metabolite", "Flux", "Direction"]
    assert "mmol gDW" in view.iface_table.horizontalHeaderItem(2).toolTip()
    assert view.cross_table.horizontalHeaderItem(1).text() == "Lumen transfer"
    assert "mmol gDW" in view.cross_table.horizontalHeaderItem(1).toolTip()


def test_host_pages_start_without_result_tables(window) -> None:
    assert not window.host_view.results.has_results()
    assert not window.host_search_page.results.has_results()


_RANKED = {"target": "ac", "metric": "target_transfer", "status": "ok", "warnings": [],
           "top_ranked": [{"members": ["a"], "score": 1.0, "target_transfer": 0.5,
                           "community_growth": 0.2, "evaluation_status": "optimal",
                           "target_identifiability": "identified"}]}


def _draw_host_result(view) -> None:
    view.load_host_result(SimpleNamespace(viable=True, biomass=1.5, status="optimal",
                                          interface_fluxes=[]))
    view.load_impact(SimpleNamespace(microbe_to_host={"ac": 1.0}))


def test_host_result_is_shown_then_cleared_by_an_edit(window) -> None:
    view = window.host_view
    _draw_host_result(view)
    assert view.results.has_results()
    view.tradeoff_spin.setValue(0.7)
    assert not view.results.has_results()
    assert view.cross_table.rowCount() == 0
    assert view.status.text() == "Inputs changed — previous result cleared; re-run to update."


def test_failed_host_rerun_clears_the_previous_result(window, monkeypatch) -> None:
    w = window
    view = w.host_view
    view.host_picker.set_selected(["host"])
    view.model_picker.set_selected(["a"])
    view.biomass_basis_kind_combo.setCurrentText("measured")
    view.biomass_basis_source_input.setText("lab record 12")
    view.microbial_biomass_spin.setValue(0.5)
    view.host_biomass_spin.setValue(10.0)
    _draw_host_result(view)
    monkeypatch.setattr("cmig.cli.main.main", lambda argv: 2)
    assert w.run_host_microbe_bigg()
    deadline = time.time() + 10
    while not view.run_btn.isEnabled() and time.time() < deadline:
        APP.processEvents()
        w._poll_completed_jobs()
        time.sleep(0.02)
    assert "host-microbe failed" in view.status.text()
    assert not view.results.has_results()
    assert view.cross_table.rowCount() == 0 and view.current_run_dir is None


def test_project_switch_clears_both_host_pages(window, tmp_path: Path) -> None:
    w = window
    _draw_host_result(w.host_view)
    page = w.host_search_page
    w._show_ranked("host_search", _RANKED, tmp_path, page.request_fields("host_search"))
    assert page.results.has_results()
    make_project(tmp_path / "p2", ["x"])
    assert w.open_project(tmp_path / "p2")
    for view in (w.host_view, page):
        assert not view.results.has_results()
        assert view.status.text() == ""
    assert w.host_view.cross_table.rowCount() == 0
    assert page.results_panel.table.rowCount() == 0


def test_host_search_refuses_the_host_as_a_microbe(window, monkeypatch) -> None:
    w = window
    calls: list[list[str]] = []
    monkeypatch.setattr("cmig.cli.main.main", lambda argv: (calls.append(list(argv)), 2)[1])
    page = w.host_search_page
    page.host_picker.set_selected(["host"])
    page.model_picker.set_selected(["a", "host"])  # re-ticked on purpose
    assert w.run_host_search_bigg() == ""
    assert "also selected as a microbe" in page.status.text()
    assert calls == []


def test_host_search_default_microbes_leave_out_the_host(window, tmp_path: Path) -> None:
    w = window
    w.host_search_page.host_picker.set_selected(["host"])
    w.session.store_settings("host_search", {})  # no remembered microbes: the default applies
    w.close_project()
    assert w.open_project(tmp_path / "p")
    page = w.host_search_page
    assert page.host_picker.selected_ids() == ["host"]
    assert page.model_picker.selected_ids() == ["a", "b"]


def test_a_non_viable_host_result_paints_no_interface_flux(window) -> None:
    from PySide6.QtCore import Qt

    from cmig.core.host import InterfaceFlux

    view = window.host_view
    flux = InterfaceFlux(exchange_id="EX_ac_e", interface="bigg_external", metabolite="ac",
                         flux=-2.0, label="uptake")
    view.load_host_result(SimpleNamespace(viable=True, biomass=1.5, status="optimal",
                                          interface_fluxes=[flux]))
    assert view.iface_table.item(0, 2).data(Qt.ItemDataRole.ForegroundRole) is not None
    view.load_host_result(SimpleNamespace(viable=False, biomass=None, status="infeasible",
                                          interface_fluxes=[flux]))
    assert view.iface_table.item(0, 2).text() == "-2"
    assert view.iface_table.item(0, 2).data(Qt.ItemDataRole.ForegroundRole) is None
