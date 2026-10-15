from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402
from cmig.io import project as proj  # noqa: E402

APP = QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path: Path, monkeypatch):
    make_project(tmp_path / "p", ["a", "b"])
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(tmp_path / "p")
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    calls: list[list[str]] = []

    def fake_single(argv: list[str]) -> int:
        calls.append(list(argv))
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "single_summary.json").write_text(json.dumps({
            "status": "ok", "solver": "gurobi", "growth_feasible": True,
            "growth_threshold": 1e-6, "warnings": [],
            "methods": {"FBA": {"status": "optimal", "objective": 0.5}},
        }))
        return 0

    monkeypatch.setattr("cmig.cli.main.main", fake_single)
    monkeypatch.setattr(w, "_inspect_gui_run", lambda _d: {"artifact_integrity": "verified"})
    yield w, calls
    w.close_project()


def _wait_text(w, needle: str) -> None:
    deadline = time.time() + 10
    while needle not in w.model_browser.growth_label.text() and time.time() < deadline:
        APP.processEvents()
        time.sleep(0.02)
        w._poll_completed_jobs()


def test_unconfirmed_model_is_refused(window) -> None:
    w, calls = window
    w.sidebar.select("models", "a")
    assert not w.model_browser.check_growth_btn.isEnabled()
    assert w.run_check_growth("a") == ""
    assert "Confirm" in w.model_browser.growth_label.text()
    assert calls == []


def test_confirm_then_check_growth(window) -> None:
    w, calls = window
    w.sidebar.select("models", "a")
    w.model_browser.confirm_btn.click()
    assert proj.namespace_confirmed(w.session.require().model("a"))
    assert w.model_browser.check_growth_btn.isEnabled()
    w.model_browser.medium_picker.set_ref("preset:western_diet")
    assert w.run_check_growth("a")
    _wait_text(w, "Growth 0.5")
    argv = calls[0]
    assert argv[:2] == ["single", "--model"]
    assert argv[argv.index("--medium") + 1].endswith("western_diet.csv")
    assert "--exact-medium" in argv and "--assume-bigg-namespace" in argv
    assert "--allow-unknown-medium" not in argv
    assert Path(argv[argv.index("--out") + 1]).name.startswith("check-growth-")
    assert "western_diet (exact)" in w.model_browser.growth_label.text()


def test_last_result_comes_back_after_reselect(window) -> None:
    w, _calls = window
    w.sidebar.select("models", "a")
    w.model_browser.confirm_btn.click()
    assert w.run_check_growth("a")
    _wait_text(w, "Growth 0.5")
    w.sidebar.select("models", "b")
    assert "not checked yet" in w.model_browser.growth_label.text()
    w.sidebar.select("models", "a")
    assert "Growth 0.5" in w.model_browser.growth_label.text()


@pytest.mark.parametrize("reason", [
    "medium exchange has no counterpart in the target model (matched on metabolite): ['EX_x_e']",
    # Round 11: what `cmig single` refuses now — a medium that matches nothing, or a near miss.
    "none of the medium's 1 exchange ids matches an exchange of the model (matched on "
    "metabolite), so the medium and the models are probably in different namespaces",
    "medium exchange ids written in another notation of exchanges the selected models have "
    "(VMH `glc_D`/`(e)` vs BiGG `glc__D`/`_e`): EX_glc_D_m -> EX_glc__D_m",
])
def test_refusal_for_unknown_medium_suggests_the_option(window, monkeypatch, reason) -> None:
    w, _calls = window

    def refuse(argv: list[str]) -> int:
        import sys

        print(reason, file=sys.stderr)
        return 2

    monkeypatch.setattr("cmig.cli.main.main", refuse)
    w.sidebar.select("models", "a")
    w.model_browser.confirm_btn.click()
    assert w.run_check_growth("a")
    _wait_text(w, "Failed")
    text = w.model_browser.growth_label.text()
    assert text.startswith("✗ Failed")
    assert "Skip medium metabolites this model lacks" in text


def test_changed_file_voids_pretick_and_check_growth(window) -> None:
    w, _calls = window
    project = w.session.require()
    w.session.confirm_namespace("a")
    w.session.confirm_namespace("b")
    w.community_builder.model_picker.set_selected(["a", "b"])
    assert w.community_builder.assume_bigg_check.isChecked()
    assert "All 2 models confirmed" in w.community_builder.namespace_note.text()
    (project.root / project.model("b").file).write_text("<sbml id='edited'/>")
    proj.verify_checksums(project)
    w.refresh_workspace()
    assert proj.confirmation_state(project.model("b")) == "changed"
    assert "b" not in w.community_builder.model_picker.selected_ids(), "a changed copy drops out"
    assert w.community_builder.namespace_note.text() == "a is confirmed in this project"
    w.sidebar.select("models", "b")
    assert not w.model_browser.check_growth_btn.isEnabled()
    assert "Changed since confirmed" in w.model_browser.namespace_label.text()


def test_user_choice_holds_until_the_selection_changes(window) -> None:
    w, _calls = window
    w.session.confirm_namespace("a")
    view = w.community_builder
    view.model_picker.set_selected(["a"])
    assert view.assume_bigg_check.isChecked()
    view.assume_bigg_check.click()  # the user unticks it
    w.refresh_workspace()
    assert not view.assume_bigg_check.isChecked()
    view.model_picker.set_selected(["a", "b"])
    view.model_picker.set_selected(["a"])
    assert view.assume_bigg_check.isChecked(), "a new selection recomputes the default"


def test_medium_editor_pretick(window) -> None:
    w, _calls = window
    w.session.confirm_namespace("a")
    editor = w.medium_editor
    editor.model_picker.set_selected(["a"])
    editor.single_model_picker.set_selected(["a"])
    assert editor.assume_bigg_check.isChecked()
    editor.model_picker.set_selected(["a", "b"])
    assert not editor.assume_bigg_check.isChecked()
    assert "b not confirmed" in editor.namespace_note.text()


def test_revoke_is_undoable(window) -> None:
    w, _calls = window
    w.sidebar.select("models", "a")
    w.model_browser.confirm_btn.click()
    w.model_browser.revoke_btn.click()
    assert not proj.namespace_confirmed(w.session.require().model("a"))
    w.session.undo_stack.undo()
    assert proj.namespace_confirmed(w.session.require().model("a"))


def test_runs_label_names_the_model(window) -> None:
    w, _calls = window
    w.sidebar.select("models", "a")
    w.model_browser.confirm_btn.click()
    assert w.run_check_growth("a")
    _wait_text(w, "Growth 0.5")
    labels = [e.label for e in w.session.runs()]
    assert any(label.startswith("Check Growth · a · ") for label in labels)


def test_undo_redraws_the_browsed_models_header(window) -> None:
    w, _calls = window
    w.sidebar.select("models", "a")
    w.model_browser.confirm_btn.click()
    assert w.model_browser.check_growth_btn.isEnabled()
    w.session.undo_stack.undo()
    assert not proj.namespace_confirmed(w.session.require().model("a"))
    assert not w.model_browser.check_growth_btn.isEnabled()
    assert w.model_browser.namespace_label.text().startswith("Namespace not confirmed")


def test_runs_opens_a_check_growth_run_in_its_models_browser(window) -> None:
    w, _calls = window
    w.sidebar.select("models", "a")
    w.model_browser.confirm_btn.click()
    assert w.run_check_growth("a")
    _wait_text(w, "Growth 0.5")
    run_dir = next(e.path for e in w.session.runs() if e.label.startswith("Check Growth · a"))
    w.sidebar.select("models", "b")
    w._open_run_entry(run_dir)
    assert w.pages.currentWidget() is w.model_browser
    assert w.model_browser.model_id() == "a"
    assert "Growth 0.5" in w.model_browser.growth_label.text()


def test_check_growth_of_a_model_not_on_show_is_refused(window) -> None:
    w, calls = window
    w.session.confirm_namespace("a")
    w.sidebar.select("models", "b")
    assert w.run_check_growth("a") == ""
    assert calls == []


def _write_infeasible(argv: list[str]) -> int:
    out = Path(argv[argv.index("--out") + 1])
    out.mkdir(parents=True, exist_ok=True)
    (out / "single_summary.json").write_text(json.dumps({
        "status": "failed", "solver": "gurobi", "growth_feasible": False,
        "growth_threshold": 1e-6, "warnings": ["FBA status=infeasible: FBA status=infeasible"],
        "methods": {"FBA": {"status": "infeasible", "objective": None,
                            "diagnostic": "FBA status=infeasible"}},
    }))
    import sys

    print("  analysis failed: artifacts were written … pass --allow-failed-run to exit 0 "
          "anyway", file=sys.stderr)
    return 3


def test_infeasible_run_reads_infeasible_now_and_after_reselect(window, monkeypatch) -> None:
    w, _calls = window
    monkeypatch.setattr("cmig.cli.main.main", _write_infeasible)
    w.sidebar.select("models", "a")
    w.model_browser.confirm_btn.click()
    w.model_browser.medium_picker.set_ref("preset:western_diet")
    assert w.run_check_growth("a")
    _wait_text(w, "Infeasible")
    text = w.model_browser.growth_label.text()
    assert text.startswith("✗ Infeasible")
    assert "western_diet (exact)" in text and "allow-failed-run" not in text
    w.sidebar.select("models", "b")
    w.sidebar.select("models", "a")
    assert w.model_browser.growth_label.text().startswith("✗ Infeasible")


def test_changed_result_is_never_growth(window, monkeypatch) -> None:
    w, _calls = window
    monkeypatch.setattr(w, "_inspect_gui_run", lambda _d: {"artifact_integrity": "mismatch"})
    w.sidebar.select("models", "a")
    w.model_browser.confirm_btn.click()
    assert w.run_check_growth("a")
    _wait_text(w, "Result changed")
    assert (w.model_browser.growth_label.text()
            == "✗ Result changed since the run — see the inspector")


def test_skipped_metabolites_are_named_and_the_record_names_the_model(window) -> None:
    w, _calls = window
    w.sidebar.select("models", "a")
    w.model_browser.confirm_btn.click()
    w.model_browser.medium_picker.set_ref("preset:western_diet")
    w.model_browser.skip_unknown_check.setChecked(True)
    assert w.run_check_growth("a")
    _wait_text(w, "Growth 0.5")
    assert ("western_diet (exact, model-lacking metabolites skipped)"
            in w.model_browser.growth_label.text())
    run_dir = next(e.path for e in w.session.runs() if e.label.startswith("Check Growth · a"))
    record, _problem = proj.read_run_request(run_dir)
    assert record is not None and record["models"] == ["a"]
