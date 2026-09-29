"""Search output folder, path pickers, checkpoint pre-checks and run reopening (GUI).

The GUI never computes anything: these tests record the argv handed to
`cmig.cli.main.main` and inspect the folders the GUI creates around it.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import cmig.gui.app as gui_app  # noqa: E402
from cmig.core.workflow_manifest import artifact_result_digest  # noqa: E402
from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.builder import MERGE_MEDIUM_WARNING, SearchView  # noqa: E402
from cmig.service import JobRunner, JobStatus  # noqa: E402

CHECKPOINT_EXISTS = "checkpoint exists; enable Resume or choose a new path"


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _deterministic_qt_teardown():
    """Destroy every window inside the test, not at interpreter exit (macOS exit 139).

    Same pattern as tests/test_round8_gui_sweep_overlays.py.
    """
    yield
    app = QApplication.instance()
    if app is not None:
        for widget in app.topLevelWidgets():
            widget.close()
            widget.deleteLater()
        app.processEvents()


def _publish(out: Path, summary: dict[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "search_summary.json").write_text(json.dumps(summary))
    (out / "manifest.json").write_text(json.dumps({
        "manifest_scope": "workflow", "manifest_schema_version": "1.2",
        "workflow_kind": "search", "artifacts": ["search_summary.json"],
        "result_digest": artifact_result_digest(out, "search", ["search_summary.json"]),
    }))


SINGLE = {"status": "ok", "strategy": "exhaustive", "target": "ac", "warnings": [],
          "top_ranked": [{"members": ["A", "B"], "score": 1.5, "target_flux": 1.5,
                          "community_growth": 0.2, "status": "optimal"}]}
MULTI = {"status": "ok", "strategy": "exhaustive", "warnings": [],
         "top_ranked": [{"members": ["A", "B"], "score": 0.7,
                         "target_fluxes": {"ac": 1.0, "but": 2.0},
                         "community_growth": 0.2, "status": "optimal"},
                        {"members": ["A", "C"], "score": 0.5,
                         "target_fluxes": {"ac": 0.5, "but": 2.5},
                         "community_growth": 0.1, "status": "optimal"}]}


class _Recorder:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, summary: dict[str, Any] | None = None,
                 staged: bool = False) -> None:
        import cmig.cli.main

        self.calls: list[list[str]] = []
        self.summary = summary or SINGLE
        self.staged = staged
        monkeypatch.setattr(cmig.cli.main, "main", self)

    def __call__(self, argv: list[str]) -> int:
        self.calls.append(list(argv))
        out = Path(argv[argv.index("--out") + 1])
        if self.staged:
            from cmig.io.run_transaction import staged_run

            with staged_run(out, artifacts=frozenset({"search_summary.json",
                                                      "manifest.json"})) as stage:
                (stage / "search_summary.json").write_text(json.dumps(self.summary))
            _publish(out, self.summary)
        else:
            _publish(out, self.summary)
        return 0


@pytest.fixture
def window(tmp_path):
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    pool = tmp_path / "pool"
    pool.mkdir()
    w.search_view.model_dir_input.setText(str(pool))
    yield w
    w.close()
    runner.shutdown()


def _run(w) -> str:
    jid = w.run_search_fixture()
    if jid:
        w.runner.result(jid, timeout=10)
        w._poll_completed_jobs()
    return jid


def _out(argv: list[str]) -> Path:
    return Path(argv[argv.index("--out") + 1])


def _explorer_paths(w) -> list[str]:
    root = w.explorer._roots["runs"]
    return [str(root.child(i).data(0, Qt.ItemDataRole.UserRole)) for i in range(root.childCount())]


# ------------------------------------------------------------------ output folder


def test_output_folder_widgets_are_search_only():
    _app()
    view = SearchView()
    assert view.output_dir_input.text() == ""
    assert "Search only" in view.output_dir_label.text()
    note = view.output_dir_note.text()
    for other in ("Gene KO", "Strain Growth", "Ratio Impact"):
        assert other in note
    assert "output_dir" not in view.request_fields("search")
    for kind in view.REQUEST_FIELDS:
        assert "output_dir" not in view.REQUEST_FIELDS[kind]
    view.close()


def test_blank_output_folder_uses_temp_root(window, monkeypatch):
    rec = _Recorder(monkeypatch)
    assert _run(window)
    out = _out(rec.calls[0])
    assert out.parent == gui_app._search_temp_root().resolve()
    assert out.name.startswith("cmig-search-")


def test_chosen_output_folder_gets_a_new_subfolder_each_run(window, monkeypatch, tmp_path):
    rec = _Recorder(monkeypatch)
    parent = tmp_path / "results"
    parent.mkdir()
    keep = parent / "notes.txt"
    keep.write_text("mine")
    window.search_view.output_dir_input.setText(str(parent))
    assert _run(window)
    assert _run(window)
    first, second = _out(rec.calls[0]), _out(rec.calls[1])
    assert first != second
    for out in (first, second):
        assert out.parent == parent.resolve()
        assert re.fullmatch(r"search-\d{8}-\d{6}(-\d+)?", out.name)
        assert (out / "search_summary.json").is_file()
    assert keep.read_text() == "mine"
    assert (first / "search_summary.json").is_file()  # the earlier run is not replaced


def test_existing_subfolder_is_never_reused(window, monkeypatch, tmp_path):
    rec = _Recorder(monkeypatch)
    monkeypatch.setattr(gui_app, "_search_run_stamp", lambda: "20260929-120000")
    parent = tmp_path / "results"
    old = parent / "search-20260929-120000"
    old.mkdir(parents=True)
    (old / "old.txt").write_text("previous run")
    window.search_view.output_dir_input.setText(str(parent))
    assert _run(window)
    assert _run(window)
    assert [_out(c).name for c in rec.calls] == [
        "search-20260929-120000-2", "search-20260929-120000-3"]
    assert (old / "old.txt").read_text() == "previous run"
    assert sorted(p.name for p in old.iterdir()) == ["old.txt"]


def test_missing_output_folder_is_refused(window, monkeypatch, tmp_path):
    rec = _Recorder(monkeypatch)
    missing = tmp_path / "nope"
    window.search_view.output_dir_input.setText(str(missing))
    assert window.run_search_fixture() == ""
    assert rec.calls == []
    assert "does not exist" in window.search_view.status.text()
    assert not missing.exists()


def test_file_as_output_folder_is_refused(window, monkeypatch, tmp_path):
    rec = _Recorder(monkeypatch)
    afile = tmp_path / "a.txt"
    afile.write_text("x")
    window.search_view.output_dir_input.setText(str(afile))
    assert window.run_search_fixture() == ""
    assert rec.calls == []
    assert "not a folder" in window.search_view.status.text()


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="needs POSIX non-root")
def test_unwritable_output_folder_is_refused(window, monkeypatch, tmp_path):
    rec = _Recorder(monkeypatch)
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        window.search_view.output_dir_input.setText(str(locked))
        assert window.run_search_fixture() == ""
        assert rec.calls == []
        assert "not writable" in window.search_view.status.text()
        assert list(locked.iterdir()) == []
    finally:
        locked.chmod(0o700)


def test_home_directory_as_output_parent_works(window, monkeypatch, tmp_path):
    from cmig.io.run_transaction import staged_run

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    # staged_run itself still refuses the home directory as --out ...
    with pytest.raises(ValueError), staged_run(fake_home):
        pass
    # ... but a fresh subfolder inside it is a dedicated run directory.
    rec = _Recorder(monkeypatch, staged=True)
    window.search_view.output_dir_input.setText(str(fake_home))
    jid = _run(window)
    assert jid
    assert window.runner.poll(jid).status is JobStatus.DONE
    out = _out(rec.calls[0])
    assert out.parent == fake_home.resolve()
    assert (out / "search_summary.json").is_file()


def test_changing_only_output_folder_keeps_displayed_result(window, monkeypatch, tmp_path):
    _Recorder(monkeypatch)
    view = window.search_view
    assert _run(window)
    run_dir = view.current_run_dir
    assert run_dir is not None and view.table.rowCount() == 1
    requested = view.request_fields("search")
    other = tmp_path / "elsewhere"
    other.mkdir()
    view.output_dir_input.setText(str(other))
    assert view.current_run_dir == run_dir
    assert view.table.rowCount() == 1
    assert view.superseded_note(requested, "search") == ""


def test_output_folder_does_not_apply_to_other_workflows(window, monkeypatch, tmp_path):
    import cmig.cli.main

    seen: list[list[str]] = []

    def fake_main(argv):
        seen.append(list(argv))
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        name = {"gene-ko-search": "gene_ko_summary.json",
                "strain-growth": "strain_growth_summary.json",
                "abundance-impact": "abundance_impact_summary.json"}[argv[0]]
        (out / name).write_text(json.dumps({"top_ranked": [], "warnings": []}))
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    parent = tmp_path / "results"
    parent.mkdir()
    view = window.search_view
    view.output_dir_input.setText(str(parent))
    view.ko_members_input.setText("a,b")
    view.growth_member_input.setText("a")
    for method in ("run_gene_ko_search", "run_strain_growth_report", "run_abundance_impact"):
        jid = getattr(window, method)()
        assert jid
        window.runner.result(jid, timeout=10)
    assert len(seen) == 3
    for argv in seen:
        assert _out(argv).parent == gui_app._search_temp_root().resolve()
    assert list(parent.iterdir()) == []


# ------------------------------------------------------------------ browse buttons


def test_browse_buttons_fill_paths(window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    calls: dict[str, Any] = {}

    def existing_dir(*args, **kwargs):
        calls["dir"] = args
        return str(tmp_path / "out")

    def open_file(*args, **kwargs):
        calls["open"] = args
        return str(tmp_path / "medium.csv"), ""

    def save_file(*args, **kwargs):
        calls["save"] = (args, kwargs)
        return str(tmp_path / "ck.json"), ""

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(existing_dir))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(open_file))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(save_file))
    view = window.search_view
    view.browse_output_btn.click()
    view.browse_medium_btn.click()
    view.browse_checkpoint_btn.click()
    assert view.output_dir_input.text() == str(tmp_path / "out")
    assert view.medium_input.text() == str(tmp_path / "medium.csv")
    assert view.checkpoint_input.text() == str(tmp_path / "ck.json")
    medium_filter = " ".join(str(a) for a in calls["open"])
    assert "*.csv" in medium_filter and "*.json" in medium_filter
    save_args = " ".join(str(a) for a in calls["save"][0])
    assert "*.json" in save_args


def test_cancelled_browse_keeps_existing_paths(window, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", "")))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    view = window.search_view
    view.output_dir_input.setText("/keep/out")
    view.medium_input.setText("/keep/m.csv")
    view.checkpoint_input.setText("/keep/ck.json")
    view.browse_output_btn.click()
    view.browse_medium_btn.click()
    view.browse_checkpoint_btn.click()
    assert view.output_dir_input.text() == "/keep/out"
    assert view.medium_input.text() == "/keep/m.csv"
    assert view.checkpoint_input.text() == "/keep/ck.json"


# ------------------------------------------------------------------ checkpoint checks


def test_existing_checkpoint_without_resume_is_refused(window, monkeypatch, tmp_path):
    rec = _Recorder(monkeypatch)
    ck = tmp_path / "ck.json"
    ck.write_text("{}")
    view = window.search_view
    view.checkpoint_input.setText(str(ck))
    assert window.run_search_fixture() == ""
    assert rec.calls == []
    assert CHECKPOINT_EXISTS in view.status.text()
    assert ck.read_text() == "{}"


def test_resume_runs_into_a_new_subfolder(window, monkeypatch, tmp_path):
    rec = _Recorder(monkeypatch)
    parent = tmp_path / "results"
    parent.mkdir()
    ck = tmp_path / "ck.json"
    view = window.search_view
    view.output_dir_input.setText(str(parent))
    view.checkpoint_input.setText(str(ck))
    assert _run(window)  # checkpoint does not exist yet: allowed without Resume
    ck.write_text("{}")  # the (cancelled) run left a checkpoint behind
    view.resume_check.setChecked(True)
    assert _run(window)
    first, second = rec.calls
    assert "--resume" not in first
    assert "--resume" in second
    assert second[second.index("--checkpoint") + 1] == str(ck)
    assert _out(second) != _out(first)
    assert _out(second).parent == parent.resolve()


def test_checkpoint_inside_this_runs_out_is_refused(window, monkeypatch, tmp_path):
    rec = _Recorder(monkeypatch)
    monkeypatch.setattr(gui_app, "_search_run_stamp", lambda: "20260929-120000")
    parent = tmp_path / "results"
    parent.mkdir()
    view = window.search_view
    view.output_dir_input.setText(str(parent))
    view.checkpoint_input.setText(str(parent / "search-20260929-120000" / "ck.json"))
    assert window.run_search_fixture() == ""
    assert rec.calls == []
    assert "inside this run's output folder" in view.status.text()
    assert list(parent.iterdir()) == []  # nothing left behind


def test_checkpoint_equal_to_out_is_refused_for_temp_runs(window, monkeypatch, tmp_path):
    rec = _Recorder(monkeypatch)
    root = tmp_path / "tmproot"
    root.mkdir()
    monkeypatch.setattr(gui_app, "_search_temp_root", lambda: root)
    monkeypatch.setattr(gui_app.tempfile, "mkdtemp",
                        lambda prefix, dir: str(Path(dir) / f"{prefix}fixed"))
    fixed = root / "cmig-search-fixed"
    fixed.mkdir()  # mkdtemp stand-in creates nothing; pretend it did
    window.search_view.checkpoint_input.setText(str(fixed / "ck.json"))
    assert window.run_search_fixture() == ""
    assert rec.calls == []
    assert "inside this run's output folder" in window.search_view.status.text()


# ------------------------------------------------------------------ explorer / reopen


@pytest.mark.parametrize("summary,rows", [(SINGLE, [("ac",)]),
                                          (MULTI, [("ac",), ("but",)])])
def test_completed_run_in_chosen_folder_registers_and_reopens(window, monkeypatch, tmp_path,
                                                              summary, rows):
    rec = _Recorder(monkeypatch, summary=summary)
    parent = tmp_path / "results"
    parent.mkdir()
    view = window.search_view
    view.set_target_rows(rows)
    view.output_dir_input.setText(str(parent))
    assert _run(window)
    out = _out(rec.calls[0]).resolve()
    assert str(out) in _explorer_paths(window)
    assert window.current_search_dir == out
    expected_rows = view.table.rowCount()
    assert expected_rows == len(summary["top_ranked"])
    view.invalidate_results()
    assert view.table.rowCount() == 0
    root = window.explorer._roots["runs"]
    item = next(root.child(i) for i in range(root.childCount())
                if root.child(i).data(0, Qt.ItemDataRole.UserRole) == str(out))
    window._open_explorer_item(item, 0)
    assert window.current_search_dir == out
    assert view.table.rowCount() == expected_rows


@pytest.mark.parametrize("summary", [SINGLE, MULTI])
def test_open_run_reopens_synthetic_search_dirs(window, tmp_path, summary):
    run = tmp_path / "chosen" / "search-20260929-120000"
    _publish(run, summary)
    window.load_run_dir(run)
    assert window.current_search_dir == run.resolve()
    assert window.search_view.table.rowCount() == len(summary["top_ranked"])
    assert str(run.resolve()) in _explorer_paths(window)


# ------------------------------------------------------------------ spec fixes


def test_fva_is_single_target_only(window, monkeypatch):
    rec = _Recorder(monkeypatch)
    view = window.search_view
    view.robustness_check.setChecked(True)
    assert view.robustness_check.isEnabled()
    assert _run(window)
    assert "--robustness-fva" in rec.calls[-1]
    view.set_target_rows([("ac",), ("but",)])
    assert not view.robustness_check.isEnabled()
    assert view.robustness_check.toolTip() == "FVA is single-target only"
    assert _run(window)
    assert "--robustness-fva" not in rec.calls[-1]
    view.set_target_rows([("ac",)])
    assert view.robustness_check.isEnabled()


def test_medium_mode_visible_with_advanced_collapsed(window, monkeypatch, tmp_path):
    _Recorder(monkeypatch)
    medium = tmp_path / "m.csv"
    medium.write_text("id,flux\n")
    view = window.search_view
    assert view.advanced_box.isHidden()
    view.medium_input.setText(str(medium))
    summary = view.medium_mode_summary
    assert not summary.isHidden()
    assert "exact" in summary.text()
    view.medium_mode_combo.setCurrentIndex(1)
    assert "merge" in summary.text() and MERGE_MEDIUM_WARNING in summary.text()
    jid = window.run_search_fixture()
    assert jid
    assert "medium: merge" in view.status.text()
    assert MERGE_MEDIUM_WARNING in view.status.text()
    window.runner.result(jid, timeout=10)
    window._poll_completed_jobs()
    details = view.details.toPlainText()
    assert "Medium mode: merge" in details and MERGE_MEDIUM_WARNING in details
    view.medium_mode_combo.setCurrentIndex(0)
    jid = window.run_search_fixture()
    assert "medium: exact" in view.status.text()
    window.runner.result(jid, timeout=10)
    window._poll_completed_jobs()
    assert "Medium mode: exact" in view.details.toPlainText()
    view.medium_input.setText("")
    assert "not applied" in summary.text()


# ------------------------------------------------------------------ ko / geometry


def test_korean_mode_output_paths(monkeypatch, tmp_path):
    _app()
    rec = _Recorder(monkeypatch)
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner, lang="ko")
    try:
        view = w.search_view
        pool = tmp_path / "pool"
        pool.mkdir()
        view.model_dir_input.setText(str(pool))
        view.output_dir_input.setText(str(tmp_path / "missing"))
        assert w.run_search_fixture() == ""
        parent = tmp_path / "results"
        parent.mkdir()
        view.output_dir_input.setText(str(parent))
        ck = tmp_path / "ck.json"
        ck.write_text("{}")
        view.checkpoint_input.setText(str(ck))
        assert w.run_search_fixture() == ""
        assert CHECKPOINT_EXISTS in view.status.text()
        view.resume_check.setChecked(True)
        jid = w.run_search_fixture()
        assert jid
        runner.result(jid, timeout=10)
        w._poll_completed_jobs()
        out = _out(rec.calls[0]).resolve()
        assert str(out) in _explorer_paths(w)
        w.load_run_dir(out)
        assert w.current_search_dir == out
    finally:
        w.close()
        runner.shutdown()


def test_window_fits_with_long_output_folder():
    app = _app()
    for lang in ("en", "ko"):
        window = build_main_window(lang=lang)
        window.search_view.output_dir_input.setText("/x" * 200)
        window.search_view.checkpoint_input.setText("/y" * 200)
        window.search_view.medium_input.setText("/z" * 200)
        window.search_view.medium_mode_combo.setCurrentIndex(1)
        window.search_view.set_target_rows([("ac",), ("but",)])
        window.tabs.setCurrentWidget(window.search_view)
        for size in ((1280, 800), (1500, 950)):
            window.resize(*size)
            window.show()
            app.processEvents()
            assert (window.width(), window.height()) == size
        window.close()
