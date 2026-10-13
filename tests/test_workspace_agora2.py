from __future__ import annotations

import json
import os
import sys
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
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.agora2_dialog import SEARCH_LIMIT, Agora2Dialog  # noqa: E402
from cmig.gui.app import _parse_catalogue, build_main_window  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402
from cmig.io import project as proj  # noqa: E402
from cmig.service import JobStatus  # noqa: E402

APP = QApplication.instance() or QApplication([])

STRAIN = "Roseburia_hominis_A2_183"


@pytest.fixture
def window(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(proj, "check_model_file", ok_check)
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "recent.ini"), QSettings.Format.IniFormat))
    make_project(tmp_path / "p", [])
    assert w.open_project(tmp_path / "p")
    yield w
    w.close_project()


def _agora2_dir(w) -> Path:
    return w.session.project.models_dir / "agora2"


def _arg(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


def _wait_fetch(w, job: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while job in w._agora2_jobs and time.time() < deadline:
        APP.processEvents()
        w._poll_completed_jobs()
        time.sleep(0.02)
    assert job not in w._agora2_jobs, "AGORA2 job did not finish"


def _wait_import(w, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while w._import_jobs and time.time() < deadline:
        APP.processEvents()
        w._poll_completed_jobs()
        time.sleep(0.02)
    assert not w._import_jobs, "import job did not finish"


def _writing_main(calls: list[list[str]], ids: tuple[str, ...] = (STRAIN,)):
    def fake_main(argv: list[str]) -> int:
        calls.append(argv)
        out = Path(_arg(argv, "--out"))
        out.mkdir(parents=True, exist_ok=True)
        for strain in ids:  # a stub that passes as a cobra JSON model
            (out / f"{strain}.json").write_text('{"id": "x", "reactions": [], "metabolites": []}')
        return 0

    return fake_main


# ── dialog ──────────────────────────────────────────────────────────────────────────────


def test_dialog_searches_and_returns_selection() -> None:
    queries: list[str] = []

    def list_fn(query: str) -> list[str]:
        queries.append(query)
        return ["Roseburia_hominis_A2_183", "Roseburia_intestinalis_L1_82"]

    dialog = Agora2Dialog(list_fn)
    dialog.search_input.setText("Roseburia")
    dialog.search_btn.click()
    assert queries == ["Roseburia"]
    assert dialog.results.count() == 2
    assert not dialog.add_btn.isEnabled()
    dialog.results.item(1).setSelected(True)
    assert dialog.add_btn.isEnabled()
    assert dialog.selected_strains() == ["Roseburia_intestinalis_L1_82"]


def test_dialog_ignores_a_blank_query() -> None:
    queries: list[str] = []
    dialog = Agora2Dialog(lambda q: queries.append(q) or [])
    dialog.search_input.setText("   ")
    dialog.search_btn.click()
    assert queries == []


def test_dialog_shows_a_failed_lookup_and_drops_the_stale_list() -> None:
    answers = iter([["A_1", "A_2"], RuntimeError("offline")])

    def list_fn(_query: str) -> list[str]:
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    dialog = Agora2Dialog(list_fn)
    dialog.search_input.setText("A")
    dialog.search_btn.click()
    dialog.results.item(0).setSelected(True)
    dialog.search_btn.click()  # the second lookup fails
    assert "Catalogue lookup failed: offline" in dialog.status.text()
    assert dialog.results.count() == 0  # a stale list must not stay selectable
    assert dialog.selected_strains() == []
    assert not dialog.add_btn.isEnabled()
    assert dialog.search_btn.isEnabled()


def test_dialog_shows_a_busy_cursor_during_the_lookup_and_always_restores_it() -> None:
    seen: list[object] = []

    def ok(_query: str) -> list[str]:
        seen.append(QApplication.overrideCursor())
        return ["A_1"]

    def boom(_query: str) -> list[str]:
        seen.append(QApplication.overrideCursor())
        raise RuntimeError("offline")

    for fn in (ok, boom):
        dialog = Agora2Dialog(fn)
        dialog.search_input.setText("A")
        dialog.search_btn.click()
        assert QApplication.overrideCursor() is None
    assert len(seen) == 2 and all(cursor is not None for cursor in seen)


def test_dialog_says_when_the_list_was_cut_at_the_limit() -> None:
    dialog = Agora2Dialog(lambda _q: [f"S_{i}" for i in range(SEARCH_LIMIT)])
    dialog.search_input.setText("S")
    dialog.search_btn.click()
    assert f"first {SEARCH_LIMIT}" in dialog.status.text()


# ── catalogue parsing ───────────────────────────────────────────────────────────────────


def test_parse_catalogue_reads_the_agora2_list_json_shape() -> None:
    payload = {
        "catalogue": "x.json", "n_selected": 2,
        "models": [
            {"id": "Roseburia_hominis_A2_183", "file": "Roseburia_hominis_A2_183.xml",
             "genus": "Roseburia", "species": "hominis", "published_size": "1 MB", "url": "u"},
            {"id": "Roseburia_intestinalis_L1_82", "file": "b.xml", "genus": "Roseburia",
             "species": "intestinalis", "published_size": "1 MB", "url": "u"},
        ],
    }
    assert _parse_catalogue(json.dumps(payload)) == [
        "Roseburia_hominis_A2_183", "Roseburia_intestinalis_L1_82"
    ]


def test_parse_catalogue_accepts_a_bare_list_and_an_empty_selection() -> None:
    assert _parse_catalogue(json.dumps(["A_1", {"id": "B_2"}])) == ["A_1", "B_2"]
    assert _parse_catalogue(json.dumps({"models": []})) == []


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        json.dumps({"n_selected": 3}),  # no strain list: not the same as "no matches"
        json.dumps({"models": "A_1"}),
        json.dumps({"models": [{"file": "a.xml"}]}),  # an entry without an id is not dropped
        json.dumps({"models": [7]}),
    ],
)
def test_parse_catalogue_rejects_what_it_cannot_read(text: str) -> None:
    with pytest.raises(ValueError):
        _parse_catalogue(text)


# ── agora2-list ─────────────────────────────────────────────────────────────────────────


def _catalogue_main(calls: list[list[str]], ids: list[str], rc: int = 0, err: str = ""):
    def fake_main(argv: list[str]) -> int:
        calls.append(argv)
        if err:
            print(err, file=sys.stderr)
        if rc == 0:
            print(json.dumps({"models": [{"id": i} for i in ids]}, indent=2))
        return rc

    return fake_main


def test_list_runs_the_cli_with_the_project_catalogue(window, monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("cmig.cli.main.main", _catalogue_main(calls, [STRAIN]))
    assert window._agora2_list("Roseburia") == [STRAIN]
    argv = calls[0]
    assert argv[0] == "agora2-list" and _arg(argv, "--format") == "json"
    assert _arg(argv, "--genus") == "Roseburia"
    assert Path(_arg(argv, "--catalogue")) == _agora2_dir(window) / "agora2_catalogue.json"
    assert "--out" not in argv  # the cache location is --catalogue, nothing else
    window._agora2_list("butyr")
    assert _arg(calls[1], "--match") == "butyr" and "--genus" not in calls[1]
    assert Path(_arg(calls[1], "--catalogue")) == _agora2_dir(window) / "agora2_catalogue.json"


def test_list_failure_raises_with_the_cli_message_and_restores_stdout(
    window, monkeypatch
) -> None:
    before = sys.stdout
    monkeypatch.setattr(
        "cmig.cli.main.main", _catalogue_main([], [], rc=2, err="catalogue unreachable")
    )
    with pytest.raises(RuntimeError, match="catalogue unreachable"):
        window._agora2_list("Roseburia")
    assert sys.stdout is before


def test_list_restores_stdout_when_the_cli_raises(window, monkeypatch) -> None:
    before = sys.stdout

    def boom(_argv: list[str]) -> int:
        print("partial output")
        raise OSError("network down")

    monkeypatch.setattr("cmig.cli.main.main", boom)
    with pytest.raises(OSError, match="network down"):
        window._agora2_list("Roseburia")
    assert sys.stdout is before


def test_list_turns_an_argparse_exit_into_an_error(window, monkeypatch) -> None:
    def usage_error(_argv: list[str]) -> int:
        print("cmig agora2-list: error: argument --match: expected one argument",
              file=sys.stderr)
        raise SystemExit(2)

    monkeypatch.setattr("cmig.cli.main.main", usage_error)
    with pytest.raises(RuntimeError, match="expected one argument"):
        window._agora2_list("-bad")


def test_list_rejects_an_unreadable_payload(window, monkeypatch) -> None:
    def junk(_argv: list[str]) -> int:
        print("this is not json")
        return 0

    monkeypatch.setattr("cmig.cli.main.main", junk)
    with pytest.raises(ValueError):
        window._agora2_list("Roseburia")


# ── agora2-fetch ────────────────────────────────────────────────────────────────────────


def test_fetch_uses_cli_into_project_agora2_folder(tmp_path: Path, monkeypatch) -> None:
    make_project(tmp_path / "p", [])
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "recent.ini"), QSettings.Format.IniFormat))
    w.open_project(tmp_path / "p")
    calls: list[list[str]] = []

    monkeypatch.setattr("cmig.cli.main.main", _writing_main(calls))
    added: list[list[Path]] = []
    monkeypatch.setattr(w, "add_model_paths", lambda paths, **k: added.append(paths) or "job")
    job = w._agora2_fetch(["Roseburia_hominis_A2_183"])
    w.runner.result(job, timeout=10)
    w._poll_completed_jobs()
    argv = calls[0]
    assert argv[:1] == ["agora2-fetch"]
    assert argv[argv.index("--strain") + 1] == "Roseburia_hominis_A2_183"
    assert Path(argv[argv.index("--out") + 1]) == w.session.project.models_dir / "agora2"
    assert "--yes" in argv and argv[argv.index("--format") + 1] == "json"
    assert Path(_arg(argv, "--catalogue")) == (
        w.session.project.models_dir / "agora2" / "agora2_catalogue.json"
    )
    assert added and added[0][0].parent == w.session.project.models_dir / "agora2"
    w.close_project()


def test_fetch_shows_the_command_in_activity_and_registers_every_file(
    window, monkeypatch
) -> None:
    ids = (STRAIN, "Roseburia_intestinalis_L1_82")
    monkeypatch.setattr("cmig.cli.main.main", _writing_main([], ids))
    added: list[list[Path]] = []
    monkeypatch.setattr(window, "add_model_paths", lambda paths, **k: added.append(paths) or "j")
    job = window._agora2_fetch(list(ids))
    assert window._job_commands[job].startswith("cmig agora2-fetch ")
    assert "--catalogue" in window._job_commands[job]
    _wait_fetch(window, job)
    assert window.runner.poll(job).status is JobStatus.DONE
    assert [p.name for p in added[0]] == [f"{i}.json" for i in ids]
    assert not window._agora2_jobs


def test_a_fetch_joins_the_project_once_it_is_registered(window, monkeypatch) -> None:
    monkeypatch.setattr("cmig.cli.main.main", _writing_main([]))
    job = window._agora2_fetch([STRAIN])
    _wait_fetch(window, job)
    _wait_import(window)
    assert [m.id for m in window.session.project.models] == [STRAIN]
    assert (_agora2_dir(window) / f"{STRAIN}.json").exists()  # the download stays as provenance


def test_the_gate_stays_closed_from_fetch_through_registration(window, monkeypatch) -> None:
    monkeypatch.setattr("cmig.cli.main.main", _writing_main([]))
    job = window._agora2_fetch([STRAIN])
    window.runner.result(job, timeout=10)
    # While the fetch is unfinished from the GUI's side, an import must be refused.
    stray = _agora2_dir(window).parent / "stray.json"
    stray.write_text("{}")
    assert window.add_model_paths([stray]) == ""
    assert "download is already running" in window.statusBar().currentMessage()
    window._poll_completed_jobs()
    # The same poll that retired the fetch has started the registration import.
    assert not window._agora2_jobs and len(window._import_jobs) == 1
    assert window.add_model_paths([stray]) == ""
    assert "import is already running" in window.statusBar().currentMessage()
    _wait_import(window)


def test_a_fetch_is_refused_while_an_import_runs(window, monkeypatch, tmp_path: Path) -> None:
    gate = threading.Event()

    def slow(path: Path) -> proj.ModelCheck:
        gate.wait(10)
        return ok_check(path)

    monkeypatch.setattr(proj, "check_model_file", slow)
    calls: list[list[str]] = []
    monkeypatch.setattr("cmig.cli.main.main", _writing_main(calls))
    src = tmp_path / "m.xml"
    src.write_text("<sbml/>")
    assert window.add_model_paths([src])
    assert window._agora2_fetch([STRAIN]) == ""
    assert "import is already running" in window.statusBar().currentMessage()
    assert calls == [] and not window._agora2_jobs
    gate.set()
    _wait_import(window)


def test_a_second_fetch_is_refused_while_one_runs(window, monkeypatch) -> None:
    release = threading.Event()
    calls: list[list[str]] = []
    inner = _writing_main(calls)

    def slow_main(argv: list[str]) -> int:
        release.wait(10)
        return inner(argv)

    monkeypatch.setattr("cmig.cli.main.main", slow_main)
    first = window._agora2_fetch([STRAIN])
    assert first
    assert window._agora2_fetch(["Other_strain_1"]) == ""
    assert "download is already running" in window.statusBar().currentMessage()
    release.set()
    _wait_fetch(window, first)
    _wait_import(window)
    assert len(calls) == 1


def test_fetch_without_a_project_is_refused(tmp_path: Path) -> None:
    w = build_main_window()
    assert w._agora2_fetch([STRAIN]) == ""
    assert "project" in w.statusBar().currentMessage().lower()


def test_a_failed_fetch_is_not_a_success(window, monkeypatch) -> None:
    def failing(argv: list[str]) -> int:
        print("not in the AGORA2 catalogue: ['Nope']", file=sys.stderr)
        return 2

    monkeypatch.setattr("cmig.cli.main.main", failing)
    added: list[list[Path]] = []
    monkeypatch.setattr(window, "add_model_paths", lambda paths, **k: added.append(paths) or "j")
    job = window._agora2_fetch(["Nope"])
    _wait_fetch(window, job)
    assert window.runner.poll(job).status is JobStatus.FAILED
    assert added == []
    message = window.statusBar().currentMessage()
    assert "failed" in message and "not in the AGORA2 catalogue" in message
    assert "not in the AGORA2 catalogue" in window._job_logs[job]
    # the gate is released for the next attempt
    assert not window._agora2_jobs
    monkeypatch.setattr("cmig.cli.main.main", _writing_main([]))
    retry = window._agora2_fetch([STRAIN])
    assert retry
    _wait_fetch(window, retry)
    assert [p.name for p in added[0]] == [f"{STRAIN}.json"]


def test_a_fetch_that_raises_is_a_failure_with_its_message(window, monkeypatch) -> None:
    def boom(_argv: list[str]) -> int:
        raise OSError("connection reset")

    monkeypatch.setattr("cmig.cli.main.main", boom)
    job = window._agora2_fetch([STRAIN])
    _wait_fetch(window, job)
    assert window.runner.poll(job).status is JobStatus.FAILED
    assert "connection reset" in window.statusBar().currentMessage()
    assert "connection reset" in window._job_logs[job]
    assert not window._import_jobs


def test_a_clean_exit_that_produced_no_file_is_a_failure(window, monkeypatch) -> None:
    monkeypatch.setattr("cmig.cli.main.main", lambda argv: 0)
    job = window._agora2_fetch([STRAIN])
    _wait_fetch(window, job)
    assert window.runner.poll(job).status is JobStatus.FAILED
    assert "no model file" in window.statusBar().currentMessage()
    assert not window._import_jobs
    assert window.session.project.models == []


def test_a_partial_fetch_registers_what_arrived_and_reports_the_rest(
    window, monkeypatch
) -> None:
    inner = _writing_main([], (STRAIN,))

    def partial(argv: list[str]) -> int:
        inner(argv)
        print("Other_strain_1: repaired SBML still does not parse", file=sys.stderr)
        return 1

    monkeypatch.setattr("cmig.cli.main.main", partial)
    job = window._agora2_fetch([STRAIN, "Other_strain_1"])
    _wait_fetch(window, job)
    # the job reads as failed, with the reason on record, but the file that did arrive is added
    assert window.runner.poll(job).status is JobStatus.FAILED
    assert "Other_strain_1" in window._job_logs[job]
    _wait_import(window)
    assert [m.id for m in window.session.project.models] == [STRAIN]


def test_a_cancelled_fetch_is_cancelled_and_adds_nothing(window, monkeypatch) -> None:
    release = threading.Event()
    started = threading.Event()
    inner = _writing_main([])

    def slow_main(argv: list[str]) -> int:
        started.set()
        release.wait(10)
        return inner(argv)

    monkeypatch.setattr("cmig.cli.main.main", slow_main)
    job = window._agora2_fetch([STRAIN])
    assert started.wait(5)
    window._cancel_job_id(job)
    assert "cannot be interrupted" in window.statusBar().currentMessage()
    release.set()
    _wait_fetch(window, job)
    assert window.runner.poll(job).status is JobStatus.CANCELLED
    assert "cancelled" in window.statusBar().currentMessage()
    assert not window._import_jobs and window.session.project.models == []
    assert (_agora2_dir(window) / f"{STRAIN}.json").exists()  # said, not hidden


def test_closing_the_project_during_a_fetch_adds_nothing_elsewhere(
    window, monkeypatch, tmp_path: Path
) -> None:
    release = threading.Event()
    inner = _writing_main([])

    def slow_main(argv: list[str]) -> int:
        release.wait(10)
        return inner(argv)

    monkeypatch.setattr("cmig.cli.main.main", slow_main)
    job = window._agora2_fetch([STRAIN])
    window.session.close()
    make_project(tmp_path / "q", [])
    assert window.open_project(tmp_path / "q")
    release.set()
    _wait_fetch(window, job)
    assert "project was closed" in window.statusBar().currentMessage()
    assert not window._import_jobs and window.session.project.models == []
    assert (window.session.project.models_dir / "agora2").exists() is False


# ── menu action ─────────────────────────────────────────────────────────────────────────


def test_the_dialog_hands_its_selection_to_the_fetch(window, monkeypatch) -> None:
    from cmig.gui import agora2_dialog

    fetched: list[list[str]] = []
    monkeypatch.setattr(window, "_agora2_fetch", lambda strains: fetched.append(strains) or "j")

    def fake_exec(self) -> int:
        self.search_input.setText("Roseburia")
        self._list_fn = lambda query: [STRAIN, "Other_1"]
        self.search_btn.click()
        self.results.item(0).setSelected(True)
        return 1

    monkeypatch.setattr(agora2_dialog.Agora2Dialog, "exec", fake_exec)
    window._agora2_dialog()
    assert fetched == [[STRAIN]]


def test_the_dialog_is_not_opened_while_a_job_holds_the_gate(window, monkeypatch) -> None:
    from cmig.gui import agora2_dialog

    opened: list[bool] = []
    monkeypatch.setattr(agora2_dialog.Agora2Dialog, "exec", lambda self: opened.append(True) or 0)
    window._import_jobs["job-x"] = []
    try:
        window._agora2_dialog()
    finally:
        window._import_jobs.clear()
    assert opened == []
    assert "import is already running" in window.statusBar().currentMessage()


def test_the_dialog_needs_a_project(monkeypatch) -> None:
    from cmig.gui import agora2_dialog

    w = build_main_window()
    opened: list[bool] = []
    monkeypatch.setattr(agora2_dialog.Agora2Dialog, "exec", lambda self: opened.append(True) or 0)
    w._agora2_dialog()
    assert opened == []
