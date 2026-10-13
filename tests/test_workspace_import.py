from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import (  # noqa: E402,F401
    _deterministic_qt_teardown,
    make_project,
    ok_check,
)
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402
from cmig.io import project as proj  # noqa: E402

APP = QApplication.instance() or QApplication([])


def _wait(window, job_id: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while job_id in window._import_jobs and time.time() < deadline:
        APP.processEvents()
        window._poll_completed_jobs()
        time.sleep(0.02)
    assert job_id not in window._import_jobs, "import job did not finish"


@pytest.fixture
def window(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(proj, "check_model_file", ok_check)
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "recent.ini"), QSettings.Format.IniFormat))
    make_project(tmp_path / "p", [])
    assert w.open_project(tmp_path / "p")
    yield w
    w.close_project()


def _models(folder: Path, names: list[str]) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for name in names:
        path = folder / name
        path.write_text(f"<sbml id='{name}'/>")
        out.append(path)
    return out


def _hold(monkeypatch, name: str) -> threading.Event:
    """Make the model check of file ``name`` block until the returned event is set."""
    gate = threading.Event()

    def slow(path: Path) -> proj.ModelCheck:
        if path.name == name:
            gate.wait(10)
        return ok_check(path)

    monkeypatch.setattr(proj, "check_model_file", slow)
    return gate


def _wait_progress(window, job: str, at_least: int) -> None:
    deadline = time.time() + 5
    while time.time() < deadline:
        APP.processEvents()
        progress = window.runner.poll(job).progress
        if progress and progress[0] >= at_least:
            return
        time.sleep(0.01)
    raise AssertionError("import never reported progress")


def test_add_models_dialog_imports_many_files(window, tmp_path: Path, monkeypatch) -> None:
    files = _models(tmp_path / "in", ["a.xml", "b.json.xml", "c.mat"])
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        lambda *a, **k: ([str(p) for p in files], ""))
    window.add_models_action.trigger()
    _wait(window, next(iter(window._import_jobs)))
    assert [m.id for m in window.session.project.models] == ["a", "b_json", "c"]
    assert window.sidebar.topLevelItem(0).text(0) == "MODELS (3)"
    assert window._pending_imports == []
    assert proj.open_project(window.session.project.root).models[0].status == "ok"


def test_folder_import_reports_skipped_failed_and_duplicates(
    window, tmp_path: Path, monkeypatch
) -> None:
    folder = tmp_path / "pool"
    _models(folder, ["good.xml", "dup1.xml"])
    (folder / "dup2.xml").write_text("<sbml id='dup1.xml'/>")  # same bytes as dup1
    (folder / "readme.txt").write_text("x")

    def flaky(path: Path) -> proj.ModelCheck:
        if path.name.startswith("good"):
            return ok_check(path)
        return proj.ModelCheck("failed", "ValueError: bad SBML", None, None, None, [], None, [])

    monkeypatch.setattr(proj, "check_model_file", flaky)
    job = window.add_model_paths([folder])
    _wait(window, job)
    statuses = {m.id: m.status for m in window.session.project.models}
    assert statuses == {"dup1": "failed", "good": "ok"}
    message = window.statusBar().currentMessage()
    assert "2 added" in message and "1 duplicate" in message and "1 skipped" in message
    assert "1 failed" in message


def test_import_reports_progress_and_cancel_stops_remaining(
    window, tmp_path: Path, monkeypatch
) -> None:
    files = _models(tmp_path / "many", [f"m{i:03d}.xml" for i in range(200)])
    gate = _hold(monkeypatch, "m002.xml")
    job = window.add_model_paths(files)
    _wait_progress(window, job, 2)
    assert window.runner.poll(job).progress[1] == 200
    assert not window.activity.isHidden(), "activity pane opens when an import starts"
    window._cancel_job_id(job)
    gate.set()
    _wait(window, job)
    count = len(window.session.project.models)
    assert 2 <= count < 200
    assert "cancelled" in window.statusBar().currentMessage()


def test_drop_on_window_starts_import(window, tmp_path: Path, monkeypatch) -> None:
    files = _models(tmp_path / "drop", ["x.xml"])
    window.sidebar.files_dropped.emit(files)
    _wait(window, next(iter(window._import_jobs)))
    assert [m.id for m in window.session.project.models] == ["x"]


def test_add_medium_dialog(window, tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "diet.csv"
    src.write_text("exchange,uptake\nEX_glc__D_e,10\n")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(src)], ""))
    window.add_medium_action.trigger()
    assert [m.id for m in window.session.project.media] == ["diet"]


def test_without_project_import_is_refused(tmp_path: Path) -> None:
    w = build_main_window()
    assert w.add_model_paths([tmp_path]) == ""


def test_folder_dialog_honours_the_subfolder_choice(window, tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "tree"
    _models(folder, ["top.xml"])
    _models(folder / "sub", ["deep.xml"])
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(folder))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    window.add_models_folder_action.trigger()
    _wait(window, next(iter(window._import_jobs)))
    assert [m.id for m in window.session.project.models] == ["top"]


def test_folder_without_models_and_unreadable_folder_report_in_the_status_bar(
    window, tmp_path: Path, monkeypatch
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "notes.txt").write_text("x")
    _wait(window, window.add_model_paths([empty]))  # folders are searched in the job
    assert "No SBML, JSON or MAT model files found" in window.statusBar().currentMessage()
    assert window.session.project.models == []
    assert window.add_model_paths([empty / "notes.txt"]) == "", "no folder, no model suffix"
    assert "No SBML, JSON or MAT model files found" in window.statusBar().currentMessage()

    def unreadable(paths, *, recursive=True):
        raise proj.ProjectError(f"cannot read folder {paths[0]}: Permission denied")

    monkeypatch.setattr(proj, "supported_model_paths", unreadable)
    job = window.add_model_paths([empty])
    _wait(window, job)
    assert "Permission denied" in window.statusBar().currentMessage()
    assert window._import_jobs == {} and window._pending_imports == []
    assert window.runner.poll(job).status.value == "failed", "an unreadable folder is a failure"


def test_pending_rows_show_while_importing_and_undo_removes_the_batch(
    window, tmp_path: Path, monkeypatch
) -> None:
    files = _models(tmp_path / "in", ["a.xml", "b.xml", "c.xml"])
    gate = _hold(monkeypatch, "b.xml")
    job = window.add_model_paths(files)
    assert window._pending_imports == ["a.xml", "b.xml", "c.xml"]
    group = window.sidebar.topLevelItem(0)
    assert [group.child(i).text(0) for i in range(group.childCount())] == [
        "… a.xml", "… b.xml", "… c.xml",
    ]
    gate.set()
    _wait(window, job)
    assert window._pending_imports == []
    assert window.session.undo_stack.undoText() == "Add 3 Models"
    window.session.undo_stack.undo()
    assert window.session.project.models == []
    models_dir = window.session.project.models_dir
    assert sorted(p.name for p in models_dir.iterdir()) == ["a.xml", "b.xml", "c.xml"], (
        "undo takes the models off the list; the copied files stay"
    )


def test_a_second_import_is_refused_while_one_is_running(
    window, tmp_path: Path, monkeypatch
) -> None:
    first = _models(tmp_path / "first", ["a.xml", "b.xml"])
    second = _models(tmp_path / "second", ["c.xml"])
    gate = _hold(monkeypatch, "a.xml")
    job = window.add_model_paths(first)
    assert window.add_model_paths(second) == ""
    assert "already running" in window.statusBar().currentMessage()
    gate.set()
    _wait(window, job)
    assert [m.id for m in window.session.project.models] == ["a", "b"]


def test_import_finishing_after_its_project_closed_adds_nothing(
    window, tmp_path: Path, monkeypatch
) -> None:
    files = _models(tmp_path / "in", ["a.xml", "b.xml", "c.xml"])
    gate = _hold(monkeypatch, "b.xml")
    job = window.add_model_paths(files)
    _wait_progress(window, job, 1)
    window.close_project()
    assert window._pending_imports == []
    other = make_project(tmp_path / "other", ["keep"])
    assert window.open_project(other.root)
    gate.set()
    _wait(window, job)
    assert [m.id for m in window.session.project.models] == ["keep"]
    assert "closed" in window.statusBar().currentMessage()
    assert window._pending_imports == []


def test_save_failure_is_reported_not_raised(window, tmp_path: Path, monkeypatch) -> None:
    files = _models(tmp_path / "in", ["a.xml"])

    def refuse(entries):
        raise proj.ProjectError("cannot save project: disk full")

    monkeypatch.setattr(window.session, "add_entries", refuse)
    job = window.add_model_paths(files)
    _wait(window, job)
    message = window.statusBar().currentMessage()
    assert "disk full" in message and "not added" in message
    assert window._pending_imports == []


def test_models_taken_while_importing_are_reported_not_added_twice(
    window, tmp_path: Path, monkeypatch
) -> None:
    files = _models(tmp_path / "in", ["x.xml", "y.xml"])
    gate = _hold(monkeypatch, "y.xml")
    job = window.add_model_paths(files)
    _wait_progress(window, job, 1)
    taken = proj.ModelEntry(id="x", file="models/other.xml", source_path="", sha256="ab" * 32,
                            format="xml", added="2026-01-01T00:00:00+00:00")
    window.session.add_entries([taken])  # the project gains id "x" while the import runs
    gate.set()
    _wait(window, job)
    assert sorted(m.id for m in window.session.project.models) == ["x", "y"]
    assert window.session.project.model("x").sha256 == "ab" * 32
    assert len({m.id for m in proj.open_project(window.session.project.root).models}) == 2
    assert "1 failed" in window.statusBar().currentMessage()


def test_failures_stay_readable_when_the_job_row_is_selected(
    window, tmp_path: Path, monkeypatch
) -> None:
    folder = tmp_path / "pool"
    _models(folder, ["one.xml"])
    (folder / "two.xml").write_text("<sbml id='one.xml'/>")  # duplicate of one.xml
    job = window.add_model_paths([folder])
    _wait(window, job)
    assert "two.xml: already in the project as one" in window.activity.log_view.toPlainText()
    window.activity.log_view.clear()
    window.jobs_panel.clearSelection()
    window.jobs_panel.selectRow(0)
    assert "two.xml: already in the project as one" in window.activity.log_view.toPlainText()
    assert "Add 2 model file(s)" in window.activity.command_label.text()


def test_model_overview_lists_the_project_models(window, tmp_path: Path) -> None:
    panel = window.model_manager
    assert panel.exchange_table.rowCount() == 0
    job = window.add_model_paths(_models(tmp_path / "in", ["a.xml", "b.xml"]))
    _wait(window, job)
    assert panel.summary_label.text() == "2 models in this project"
    assert [panel.exchange_table.horizontalHeaderItem(c).text() for c in range(4)] == [
        "Model", "Check", "Reactions", "File",
    ]
    assert panel.exchange_table.item(0, 0).text() == "a"
    assert panel.exchange_table.item(0, 1).text() == "ok"
    assert panel.exchange_table.item(0, 2).text() == "10"
    assert panel.exchange_table.item(1, 3).text() == "models/b.xml"
    assert window.pages.currentWidget() is panel


def test_model_overview_shows_integrity_problems_and_unchecked_sizes() -> None:
    from cmig.gui.editors import ModelManagerPanel

    def entry(model_id: str, **fields) -> proj.ModelEntry:
        return proj.ModelEntry(id=model_id, file=f"models/{model_id}.xml", source_path="",
                               sha256="0" * 64, format="xml", added="t", **fields)

    panel = ModelManagerPanel()
    panel.show_project_models([entry("fine", status="ok", n_reactions=7),
                               entry("edited", status="ok", integrity="changed"),
                               entry("pending")])
    def column(c: int) -> list[str]:
        return [panel.exchange_table.item(r, c).text() for r in range(3)]

    assert column(1) == ["ok", "changed", "pending"]
    assert column(2) == ["7", "—", "—"]


def _job_row_status(window, job: str) -> str:
    window.bridge.refresh()
    panel = window.jobs_panel
    for row in range(panel.rowCount()):
        if panel.item(row, 0).text() == job:
            return panel.item(row, 2).text()
    raise AssertionError(f"no Activity row for {job}")


def test_cancelled_import_never_reads_as_done_in_activity(
    window, tmp_path: Path, monkeypatch
) -> None:
    files = _models(tmp_path / "many", [f"m{i:03d}.xml" for i in range(200)])
    gate = _hold(monkeypatch, "m002.xml")
    job = window.add_model_paths(files)
    _wait_progress(window, job, 2)
    window._cancel_job_id(job)
    # Import-specific wording: nothing here is a solver call.
    message = window.statusBar().currentMessage()
    assert "Cancelling import" in message and "solver" not in message.lower()
    running = _job_row_status(window, job)
    assert "cancelling" in running and "solver" not in running
    gate.set()
    _wait(window, job)
    status = _job_row_status(window, job)
    assert status.startswith("cancelled") and "not imported" in status
    assert status != "done"
    assert "not imported" in window.activity.log_view.toPlainText()
    assert window.jobs_panel.selected_job_id() == job
    kept = len(window.session.project.models)
    assert 2 <= kept < 200, "models imported before the cancel are kept"
    assert f"{200 - kept} of 200" in status


def test_completed_import_still_reads_done_in_activity(window, tmp_path: Path) -> None:
    job = window.add_model_paths(_models(tmp_path / "in", ["a.xml", "b.xml"]))
    _wait(window, job)
    assert _job_row_status(window, job) == "done"


# ── final review: folders are searched and JSON is parsed in the import job only ──────────
def _cobra_json(folder: Path, names: list[str]) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for name in names:
        path = folder / name
        path.write_text(f'{{"id": "{name}", "reactions": [], "metabolites": [], "genes": []}}')
        out.append(path)
    return out


def test_json_pool_import_scans_off_the_gui_thread_and_cancels(
    window, tmp_path: Path, monkeypatch
) -> None:
    import cmig.core.model_pool as model_pool

    main = threading.main_thread()
    parsed_on: list[threading.Thread] = []
    real = model_pool._is_cobra_json_candidate

    def spy(path: Path) -> bool:
        parsed_on.append(threading.current_thread())
        return real(path)

    monkeypatch.setattr(model_pool, "_is_cobra_json_candidate", spy)
    pool = tmp_path / "pool"
    _cobra_json(pool, [f"m{i:03d}.json" for i in range(200)])
    (pool / "manifest.json").write_text('{"models": []}')  # JSON that is not a model: skipped
    gate = _hold(monkeypatch, "m002.json")
    job = window.add_model_paths([pool])
    assert parsed_on == [] or main not in parsed_on, "nothing is parsed on the GUI thread"
    assert window._pending_imports == ["pool"]
    _wait_progress(window, job, 2)
    assert window.runner.poll(job).progress[1] == 200
    window._poll_completed_jobs()
    assert len(window._pending_imports) == 200, "one placeholder per file once the scan is done"
    window._cancel_job_id(job)
    gate.set()
    _wait(window, job)
    assert main not in parsed_on and len(parsed_on) >= 201  # the scan, then each copy's check
    count = len(window.session.project.models)
    assert 2 <= count < 200
    status = _job_row_status(window, job)
    assert status == f"cancelled ({200 - count} of 200 not imported)"
    assert "1 skipped" in window.statusBar().currentMessage()


def test_drag_enter_on_the_window_does_not_scan(window, tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
    from PySide6.QtGui import QDragEnterEvent

    import cmig.core.model_pool
    import cmig.gui.sidebar

    def refuse(*_args, **_kwargs):
        raise AssertionError("a drag must not scan folders or parse model files")

    for module, name in ((proj, "supported_model_paths"), (proj, "_files_under"),
                         (proj, "is_supported_model_file"),
                         (cmig.gui.sidebar, "supported_model_paths"),
                         (cmig.core.model_pool, "_is_cobra_json_candidate")):
        if hasattr(module, name):
            monkeypatch.setattr(module, name, refuse)
    pool = tmp_path / "pool"
    _cobra_json(pool, ["a.json"])
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(pool))])
    enter = QDragEnterEvent(QPoint(5, 5), Qt.DropAction.CopyAction, mime,
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    window.dragEnterEvent(enter)
    assert enter.isAccepted()
