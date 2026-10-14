from __future__ import annotations

import csv
import os
import time
from pathlib import Path

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
def setup(tmp_path: Path, monkeypatch):
    make_project(tmp_path / "p", ["a", "b", "c", "host"], statuses={"c": "failed"})
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "recent.ini"), QSettings.Format.IniFormat))
    w.open_project(tmp_path / "p")
    calls: list[list[str]] = []

    def recorder(argv: list[str]) -> int:
        calls.append(list(argv))
        return 2  # stop after argv is recorded; the failure path is exercised elsewhere

    monkeypatch.setattr("cmig.cli.main.main", recorder)
    yield w, calls
    w.close_project()


def _wait_calls(w, calls, n: int = 1) -> list[str]:
    deadline = time.time() + 10
    while len(calls) < n and time.time() < deadline:
        APP.processEvents()
        time.sleep(0.02)
    w._poll_completed_jobs()
    assert len(calls) >= n
    return calls[-1]


def _taxonomy_ids(argv: list[str]) -> list[str]:
    path = Path(argv[argv.index("--taxonomy") + 1])
    return [row["id"] for row in csv.DictReader(path.open())]


def test_search_uses_selected_models_and_project_runs(setup) -> None:
    w, calls = setup
    project = w.session.project
    w.show_analysis("search")
    assert w.search_view.model_picker.selected_ids() == ["a", "b", "host"], \
        "default = every selectable model; failed c is excluded"
    w.search_view.model_picker.set_selected(["a", "b"])
    w.search_view.medium_picker.set_ref("preset:western_diet")
    w.run_search_fixture()
    argv = _wait_calls(w, calls)
    assert argv[0] == "search" and "--model-dir" not in argv
    assert _taxonomy_ids(argv) == ["a", "b"]
    out = Path(argv[argv.index("--out") + 1])
    assert out.parent == project.runs_dir and out.name.startswith("search-")
    assert Path(argv[argv.index("--medium") + 1]).name == "western_diet.csv"
    assert (project.inputs_dir / f"{out.name}-taxonomy.csv").exists()
    assert w.session.settings("search")["models"] == ["a", "b"]


def test_no_models_selected_is_refused_before_running(setup) -> None:
    w, calls = setup
    w.show_analysis("search")
    w.search_view.model_picker.set_selected([])
    assert w.run_search_fixture() == ""
    assert "Select at least one model" in w.search_view.status.text()
    assert calls == []


def test_gene_ko_strain_ratio_use_taxonomy(setup) -> None:
    w, calls = setup
    w.gene_ko_page.model_picker.set_selected(["a", "b"])
    w.gene_ko_page.members_picker.set_selected(["a", "b"])
    w.run_gene_ko_search()
    argv = _wait_calls(w, calls, 1)
    assert argv[0] == "gene-ko-search" and _taxonomy_ids(argv) == ["a", "b"]
    assert Path(argv[argv.index("--out") + 1]).name.startswith("gene-ko-")
    w.strain_growth_page.model_picker.set_selected(["a", "b"])
    w.run_strain_growth_report()
    argv = _wait_calls(w, calls, 2)
    assert argv[0] == "strain-growth" and "--taxonomy" in argv


def test_host_uses_host_and_microbe_pickers(setup) -> None:
    w, calls = setup
    project = w.session.project
    w.show_analysis("host")
    w.host_view.host_picker.set_selected(["host"])
    w.host_view.model_picker.set_selected(["a", "b"])
    w.host_view.biomass_basis_kind_combo.setCurrentIndex(1)
    w.host_view.biomass_basis_source_input.setText("lab record 12")
    w.host_view.microbial_biomass_spin.setValue(0.5)
    w.host_view.host_biomass_spin.setValue(10.0)
    w.run_host_microbe_bigg()
    argv = _wait_calls(w, calls)
    assert Path(argv[argv.index("--host") + 1]) == project.root / project.model("host").file
    assert _taxonomy_ids(argv) == ["a", "b"]
    assert Path(argv[argv.index("--out") + 1]).parent == project.runs_dir


def test_host_cannot_be_a_microbe_too(setup) -> None:
    w, calls = setup
    w.host_view.host_picker.set_selected(["host"])
    w.host_view.model_picker.set_selected(["a", "host"])
    assert w.run_host_microbe_bigg() == ""
    assert "also selected as a microbe" in w.host_view.run_status.text()


def test_dfba_uses_single_model(setup) -> None:
    w, calls = setup
    project = w.session.project
    w.dynamics_view.model_picker.set_selected(["a"])
    w.run_dfba()
    argv = _wait_calls(w, calls)
    assert Path(argv[argv.index("--model") + 1]) == project.root / project.model("a").file
    assert Path(argv[argv.index("--out") + 1]).name.startswith("dfba-")


def test_community_writes_abundances(setup) -> None:
    w, calls = setup
    w.community_builder.model_picker.set_selected(["a", "b"])
    w.community_builder.set_abundance("a", 0.25)
    w.community_builder.assume_bigg_check.setChecked(True)
    w.run_community_solve()
    argv = _wait_calls(w, calls)
    path = Path(argv[argv.index("--taxonomy") + 1])
    rows = {r["id"]: float(r["abundance"]) for r in csv.DictReader(path.open())}
    assert rows == {"a": 0.25, "b": 1.0}


def test_selection_change_invalidates_displayed_search(setup) -> None:
    w, _calls = setup
    w.search_view.table.setRowCount(1)
    w.search_view.current_run_dir = Path("/tmp/x")
    w.search_view._displayed_kind = "search"
    w.search_view._displayed_request = w.search_view.request_fields("search")
    w.search_view.model_picker.set_selected(["a"])
    assert w.search_view.table.rowCount() == 0


def test_picker_choices_follow_project_changes(setup) -> None:
    w, _calls = setup
    w.session.remove_models(["b"])
    assert "b" not in w.search_view.model_picker.selected_ids()
    w.session.undo_stack.undo()
    labels = w.search_view.model_picker.choice_ids()
    assert "b" in labels


def test_search_with_selected_from_sidebar(setup) -> None:
    w, _calls = setup
    w._search_with_models(["b", "host"])
    assert w.pages.currentWidget() is w.search_view
    assert w.search_view.model_picker.selected_ids() == ["b", "host"]


def _runs_listing(project) -> list[str]:
    return sorted(p.name for p in project.runs_dir.iterdir())


def test_changed_model_copy_is_refused_and_leaves_no_run(setup) -> None:
    w, calls = setup
    project = w.session.project
    (project.root / project.model("b").file).write_text("<sbml id='edited'/>")
    w.search_view.model_picker.set_selected(["a", "b"])
    assert w.run_search_fixture() == ""
    assert "'b' is not selectable: its file changed" in w.search_view.status.text()
    assert calls == []
    assert _runs_listing(project) == ["_inputs"]
    assert list(project.inputs_dir.iterdir()) == []
    # the model is now shown as changed and dropped from the picker
    assert w.search_view.model_picker.selected_ids() == ["a"]


def test_changed_host_copy_is_refused(setup) -> None:
    w, calls = setup
    project = w.session.project
    w.host_view.host_picker.set_selected(["host"])
    w.host_view.model_picker.set_selected(["a"])
    w.host_view.biomass_basis_kind_combo.setCurrentIndex(1)
    w.host_view.biomass_basis_source_input.setText("lab record 12")
    w.host_view.microbial_biomass_spin.setValue(0.5)
    w.host_view.host_biomass_spin.setValue(10.0)
    (project.root / project.model("host").file).unlink()
    assert w.run_host_microbe_bigg() == ""
    assert "'host' is not selectable: its file is missing" in w.host_view.run_status.text()
    assert calls == []
    assert _runs_listing(project) == ["_inputs"]
    assert w.host_view.host_picker.selected_ids() == []


def test_changed_project_medium_is_refused_not_passed(setup, tmp_path: Path) -> None:
    from gui_project_helpers import add_test_medium

    w, calls = setup
    project = w.session.project
    ref = add_test_medium(w, tmp_path / "defined.csv")
    w.search_view.medium_picker.set_ref(ref)
    (project.root / project.media[0].file).write_text("id,flux\nEX_o2_e,1000\n")
    assert w.run_search_fixture() == ""
    assert "cannot be used: its file changed" in w.search_view.status.text()
    assert calls == []
    assert _runs_listing(project) == ["_inputs"]
    # still the chosen medium (never silently replaced by the model default), but greyed out
    assert w.search_view.medium_picker.current_ref() == ref
    assert w.search_view.medium_picker.currentText().endswith("(changed)")


def test_unknown_medium_ref_is_refused_not_replaced() -> None:
    from cmig.gui.pickers import MediumPicker

    picker = MediumPicker()
    picker.set_choices(["western_diet"], [])
    picker.set_ref("preset:western_diet")
    with pytest.raises(ValueError, match="no medium choice"):
        picker.set_ref("preset:western")
    assert picker.current_ref() == "preset:western_diet"


def test_command_is_recorded_for_activity_and_the_run(setup) -> None:
    from cmig.gui.activity import command_line

    w, calls = setup
    w.dynamics_view.model_picker.set_selected(["a"])
    jid = w.run_dfba()
    argv = _wait_calls(w, calls)
    out = Path(argv[argv.index("--out") + 1])
    assert w._job_commands[jid] == command_line(argv)
    assert w._run_commands[str(out)] == command_line(argv)
    w._show_run_in_inspector(out)
    assert w.inspector.current_command() == command_line(argv)


def test_choices_are_remembered_per_analysis(tmp_path: Path) -> None:
    make_project(tmp_path / "p", ["a", "b", "host"])
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "recent.ini"), QSettings.Format.IniFormat))
    w.open_project(tmp_path / "p")
    w.search_view.model_picker.set_selected(["b"])
    w.search_view.medium_picker.set_ref("preset:high_fiber")
    w.host_view.host_picker.set_selected(["host"])
    w.dynamics_view.model_picker.set_selected(["a"])
    w.close_project()
    assert w.search_view.model_picker.selected_ids() == []
    w.open_project(tmp_path / "p")
    assert w.search_view.model_picker.selected_ids() == ["b"]
    assert w.search_view.medium_picker.current_ref() == "preset:high_fiber"
    assert w.host_view.host_picker.selected_ids() == ["host"]
    assert w.dynamics_view.model_picker.selected_ids() == ["a"]
    # an analysis the user never touched still offers every runnable model
    assert w.community_builder.model_picker.selected_ids() == ["a", "b", "host"]
    w.close_project()


def test_failed_settings_save_is_reported_not_raised(setup, monkeypatch) -> None:
    from cmig.io.project import ProjectError

    w, _calls = setup

    def fail(*_args, **_kwargs):
        raise ProjectError("disk full")

    monkeypatch.setattr(w.session, "store_settings", fail)
    w.search_view.model_picker.set_selected(["a"])  # a Qt slot: must not raise
    assert "disk full" in w.statusBar().currentMessage()


def test_refused_community_abundance_keeps_runs_clean(setup) -> None:
    w, calls = setup
    project = w.session.project
    w.community_builder.model_picker.set_selected(["a"])
    # The table follows the picker: an unselected model has no abundance row to run with.
    assert "b" not in w.community_builder.members()
    with pytest.raises(KeyError):
        w.community_builder.set_abundance("b", 0.5)
    w.community_builder.assume_bigg_check.setChecked(True)
    w.community_builder.set_abundance("a", 0.0)
    assert w.run_community_solve() == ""
    assert "greater than 0" in w.community_builder.status.text()
    assert calls == []
    assert _runs_listing(project) == ["_inputs"]


def _reopen(w, tmp_path: Path) -> None:
    w.close_project()
    w.open_project(tmp_path / "p")


def _action(picker, model_id: str):
    return next(a for a in picker.menu().actions() if a.isCheckable() and a.text() == model_id)


def test_single_picker_never_holds_two_models_after_reopen(setup, tmp_path: Path) -> None:
    w, _calls = setup
    w.dynamics_view.model_picker.set_selected(["b"])
    _reopen(w, tmp_path)
    picker = w.dynamics_view.model_picker
    assert picker.selected_ids() == ["b"]
    _action(picker, "host").trigger()  # the user picks another model from the menu
    assert picker.selected_ids() == ["host"]
    assert picker.text() == "Model: host"
    assert w.session.settings("dfba")["models"] == ["host"]
    picker.set_selected(["c", "a", "b"])  # c failed: the first runnable one is kept
    assert picker.selected_ids() == ["a"]


def test_remembered_model_that_stops_running_is_reported(setup, tmp_path: Path) -> None:
    w, _calls = setup
    project = w.session.project
    w.search_view.model_picker.set_selected(["a", "b"])
    w.dynamics_view.model_picker.set_selected(["b"])
    w.close_project()
    (project.root / project.model("b").file).write_text("<sbml id='edited'/>")
    w.open_project(tmp_path / "p")
    assert w.search_view.model_picker.selected_ids() == ["a"]
    assert w.dynamics_view.model_picker.selected_ids() == []
    message = w.statusBar().currentMessage()
    assert "b (Search)" in message and "b (dFBA)" in message
    w.statusBar().clearMessage()
    w.refresh_workspace()  # reported once, not on every refresh
    assert w.statusBar().currentMessage() == ""


def test_host_model_is_not_a_default_microbe(setup, tmp_path: Path) -> None:
    w, _calls = setup
    w.host_view.host_picker.set_selected(["host"])
    _reopen(w, tmp_path)  # nothing remembered for Microbes: the default leaves the host out
    assert w.host_view.host_picker.selected_ids() == ["host"]
    assert w.host_view.model_picker.selected_ids() == ["a", "b"]


def test_choosing_a_host_unticks_it_from_microbes(setup) -> None:
    w, _calls = setup
    assert "a" in w.host_view.model_picker.selected_ids()
    w.host_view.host_picker.set_selected(["a"])
    assert w.host_view.model_picker.selected_ids() == ["b", "host"]
    assert w.session.settings("host")["models"] == ["b", "host"]
    w.host_view.model_picker.set_selected(["a", "b"])  # re-ticked on purpose: refused at run
    assert w.run_host_microbe_bigg() == ""
    assert "also selected as a microbe" in w.host_view.run_status.text()


# ── final review: remembered selections do not go stale ───────────────────────────────────
def test_renamed_model_stays_selected_where_it_was_remembered(setup) -> None:
    w, _calls = setup
    w.search_view.model_picker.set_selected(["a", "b"])
    w.dynamics_view.model_picker.set_selected(["b"])
    w.session.rename_model("b", "Bifido")
    assert w.search_view.model_picker.selected_ids() == ["a", "Bifido"]
    assert w.dynamics_view.model_picker.selected_ids() == ["Bifido"]
    assert "left out" not in w.statusBar().currentMessage()
    w.session.undo_stack.undo()
    assert w.search_view.model_picker.selected_ids() == ["a", "b"]
    assert w.dynamics_view.model_picker.selected_ids() == ["b"]


def test_search_run_does_not_freeze_the_default_selection(setup, tmp_path: Path) -> None:
    from gui_project_helpers import ok_check

    from cmig.io import project as proj

    w, calls = setup
    assert "search" not in w.session.project.analysis_settings
    assert w.run_search_fixture()
    _wait_calls(w, calls)
    assert "search" not in w.session.project.analysis_settings, "a run is not a choice"
    source = tmp_path / "late.xml"
    source.write_text("<sbml id='late'/>")
    entry = proj.add_model_file(w.session.project, source, check=ok_check)
    w.session.project.models.remove(entry)  # add it the way an import does
    w.session.add_entries([entry])
    assert w.search_view.model_picker.selected_ids() == ["a", "b", "host", "late"]
