from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
import time
from datetime import datetime
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
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from cmig.cli.main import build_parser  # noqa: E402
from cmig.gui.agora2_dialog import (  # noqa: E402
    SEARCH_LIMIT,
    Agora2Dialog,
    Agora2Strain,
    download_estimate,
    published_bytes,
)
from cmig.gui.app import (  # noqa: E402
    _claim_agora2_batch_dir,
    _parse_catalogue,
    build_main_window,
)
from cmig.gui.project_session import RecentProjects  # noqa: E402
from cmig.io import project as proj  # noqa: E402
from cmig.io.agora2 import FetchedModel, read_manifest, write_manifest  # noqa: E402
from cmig.service import JobStatus  # noqa: E402

APP = QApplication.instance() or QApplication([])

STRAIN = "Roseburia_hominis_A2_183"
OTHER = "Roseburia_intestinalis_L1_82"
ORIGIN = "https://www.vmh.life/files/reconstructions/AGORA2/version2.01/individual/"
BATCH_NAME = re.compile(r"\d{8}-\d{6}(-\d+)?")


@pytest.fixture(autouse=True)
def _no_unexpected_prompt(monkeypatch):
    """A modal question in a test would hang it: any test that expects one patches it itself."""

    def refuse(*args, **kwargs):
        raise AssertionError(f"unexpected QMessageBox.question: {args[1:3]}")

    monkeypatch.setattr(QMessageBox, "question", staticmethod(refuse))


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


def _batches(w) -> list[Path]:
    """The download batch folders of the open project, oldest first."""
    return sorted(p for p in _agora2_dir(w).iterdir() if p.is_dir())


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


def _model_json(strain: str) -> str:
    return json.dumps({"id": strain, "reactions": [], "metabolites": []})  # passes as cobra JSON


def _writing_main(
    calls: list[list[str]],
    ids: tuple[str, ...] = (STRAIN,),
    *,
    stale: tuple[str, ...] = (),
    rc: int = 0,
    err: str = "",
):
    """A stand-in for `cmig agora2-fetch`: model files and the manifest it writes beside them.

    `stale` names files left in the folder that the manifest does not record.
    """

    def fake_main(argv: list[str]) -> int:
        calls.append(argv)
        out = Path(_arg(argv, "--out"))
        out.mkdir(parents=True, exist_ok=True)
        fetched = []
        for strain in ids:
            path = out / f"{strain}.json"
            path.write_text(_model_json(strain))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            fetched.append(FetchedModel(
                id=strain, file=path.name, source_url=f"{ORIGIN}{strain}.xml",
                source_sha256=digest, source_bytes=1, sha256=digest, bytes=1,
                encoding_repairs=0, repaired_bytes=[], namespace="bigg", format="json",
            ))
        for strain in stale:
            (out / f"{strain}.json").write_text(_model_json(strain))
        if fetched:
            write_manifest(fetched, out, namespace="bigg", file_format="json",
                           repair_encoding=True)
        if err:
            print(err, file=sys.stderr)
        return rc

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
    strains = _parse_catalogue(json.dumps(payload))
    assert strains == ["Roseburia_hominis_A2_183", "Roseburia_intestinalis_L1_82"]
    assert [s.published_size for s in strains] == ["1 MB", "1 MB"]


def test_parse_catalogue_accepts_a_bare_list_and_an_empty_selection() -> None:
    strains = _parse_catalogue(json.dumps(["A_1", {"id": "B_2"}]))
    assert strains == ["A_1", "B_2"] and [s.published_size for s in strains] == ["", ""]
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
            models = [{"id": i, "published_size": "15M"} for i in ids]
            print(json.dumps({"models": models}, indent=2))
        return rc

    return fake_main


def test_list_runs_the_cli_with_the_project_catalogue(window, monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("cmig.cli.main.main", _catalogue_main(calls, [STRAIN]))
    found = window._agora2_list("Roseburia")
    assert found == [STRAIN] and found[0].published_size == "15M"
    argv = calls[0]
    assert argv[0] == "agora2-list" and _arg(argv, "--format") == "json"
    assert _arg(argv, "--match") == "Roseburia" and "--genus" not in argv
    assert Path(_arg(argv, "--catalogue")) == _agora2_dir(window) / "agora2_catalogue.json"
    assert "--out" not in argv  # the cache location is --catalogue, nothing else


@pytest.mark.parametrize(
    ("query", "pattern"),
    [
        ("Roseb", "Roseb"),  # a partial genus
        ("Roseburia hominis", "Roseburia_hominis"),  # "Genus species" reads like the id
        ("  Roseburia   hominis ", "Roseburia_hominis"),
        ("butyr", "butyr"),
        ("a.b+c", r"a\.b\+c"),  # text, not a regular expression
        ("-bad", r"\-bad"),  # never read as an option
    ],
)
def test_list_matches_the_id_case_insensitively_for_any_query(
    window, monkeypatch, query: str, pattern: str
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("cmig.cli.main.main", _catalogue_main(calls, [STRAIN]))
    window._agora2_list(query)
    assert _arg(calls[0], "--match") == pattern
    parsed = build_parser().parse_args(calls[0])  # the real CLI accepts exactly this
    assert parsed.match == pattern and parsed.genus is None


@pytest.mark.parametrize("query", ["Roseb", "roseburia", "Roseburia hominis", "HOMINIS_a2"])
def test_a_partial_genus_or_a_genus_and_species_finds_the_id(window, monkeypatch, query) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("cmig.cli.main.main", _catalogue_main(calls, [STRAIN]))
    window._agora2_list(query)
    pattern = _arg(calls[0], "--match")
    assert re.search(pattern, STRAIN, re.IGNORECASE)  # the CLI matches with IGNORECASE
    assert not re.search(pattern, "Bacteroides_ovatus_ATCC_8483", re.IGNORECASE)


def test_list_rejects_a_blank_query(window, monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("cmig.cli.main.main", _catalogue_main(calls, [STRAIN]))
    with pytest.raises(ValueError, match="Enter part of"):
        window._agora2_list("   ")
    assert calls == []


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
    agora2 = w.session.project.models_dir / "agora2"
    assert argv[:1] == ["agora2-fetch"]
    assert argv[argv.index("--strain") + 1] == "Roseburia_hominis_A2_183"
    batch = Path(argv[argv.index("--out") + 1])  # one folder per download, under models/agora2
    assert batch.parent == agora2 and BATCH_NAME.fullmatch(batch.name)
    assert "--yes" in argv and argv[argv.index("--format") + 1] == "json"
    assert Path(_arg(argv, "--catalogue")) == agora2 / "agora2_catalogue.json"  # shared cache
    assert added and added[0][0].parent == batch
    parsed = build_parser().parse_args(argv)  # the real CLI accepts exactly this
    assert parsed.strain == "Roseburia_hominis_A2_183" and parsed.yes and parsed.format == "json"
    w.close_project()


def test_fetch_shows_the_command_in_activity_and_registers_every_file(
    window, monkeypatch
) -> None:
    ids = (STRAIN, OTHER)
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
    (batch,) = _batches(window)
    assert (batch / f"{STRAIN}.json").exists()  # the download stays beside its manifest
    assert (batch / "agora2_manifest.json").exists()


def test_each_download_keeps_its_own_batch_folder_and_manifest(window, monkeypatch) -> None:
    calls: list[list[str]] = []
    for strain in (STRAIN, OTHER):
        monkeypatch.setattr("cmig.cli.main.main", _writing_main(calls, (strain,)))
        job = window._agora2_fetch([strain])
        _wait_fetch(window, job)
        _wait_import(window)
    first, second = _batches(window)
    assert first != second and all(BATCH_NAME.fullmatch(b.name) for b in (first, second))
    assert {Path(_arg(c, "--out")) for c in calls} == {first, second}
    # the second download did not overwrite the first one's provenance
    assert [m["id"] for m in read_manifest(first)["models"]] == [STRAIN]
    assert [m["id"] for m in read_manifest(second)["models"]] == [OTHER]
    assert sorted(m.id for m in window.session.project.models) == sorted([STRAIN, OTHER])
    # the catalogue cache is shared, beside the batches
    assert {_arg(c, "--catalogue") for c in calls} == {
        str(_agora2_dir(window) / "agora2_catalogue.json")
    }


def test_batch_folders_never_reuse_a_name(tmp_path: Path, monkeypatch) -> None:
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 1, 2, 3, 4, 5)

    monkeypatch.setattr("cmig.gui.app.datetime", Frozen)
    names = [_claim_agora2_batch_dir(tmp_path / "agora2").name for _ in range(3)]
    assert names == ["20260102-030405", "20260102-030405-2", "20260102-030405-3"]


def test_a_download_that_leaves_nothing_leaves_no_batch_folder(window, monkeypatch) -> None:
    monkeypatch.setattr("cmig.cli.main.main", lambda argv: 2)
    job = window._agora2_fetch([STRAIN])
    _wait_fetch(window, job)
    assert _batches(window) == []


def test_a_fetched_model_records_the_url_it_came_from(window, monkeypatch) -> None:
    ids = (STRAIN, OTHER)
    monkeypatch.setattr("cmig.cli.main.main", _writing_main([], ids))
    job = window._agora2_fetch(list(ids))
    _wait_fetch(window, job)
    _wait_import(window)
    entries = {m.id: m for m in window.session.project.models}
    assert set(entries) == set(ids)
    for strain in ids:
        assert entries[strain].source_path == f"{ORIGIN}{strain}.xml"
        assert entries[strain].source_path.startswith("https://www.vmh.life/")


def test_source_overrides_apply_only_to_the_files_named(window, tmp_path: Path) -> None:
    named, plain = tmp_path / "named.json", tmp_path / "plain.json"
    named.write_text(_model_json("named"))
    plain.write_text(_model_json("plain"))
    job = window.add_model_paths([named, plain], source_overrides={named: "https://example.org/n"})
    assert job
    _wait_import(window)
    entries = {m.id: m for m in window.session.project.models}
    assert entries["named"].source_path == "https://example.org/n"
    assert entries["plain"].source_path == str(plain.resolve())


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


def test_a_partial_fetch_registers_only_what_the_manifest_records(window, monkeypatch) -> None:
    # Other_strain_1 failed: a file of that name is in the folder, but the manifest omits it.
    partial = _writing_main(
        [], (STRAIN,), stale=("Other_strain_1",), rc=1,
        err="Other_strain_1: repaired SBML still does not parse",
    )
    monkeypatch.setattr("cmig.cli.main.main", partial)
    job = window._agora2_fetch([STRAIN, "Other_strain_1"])
    _wait_fetch(window, job)
    # the job reads as failed, with the reason on record, but the recorded file is added
    assert window.runner.poll(job).status is JobStatus.FAILED
    assert "Other_strain_1" in window._job_logs[job]
    _wait_import(window)
    assert [m.id for m in window.session.project.models] == [STRAIN]
    (batch,) = _batches(window)
    assert (batch / "Other_strain_1.json").exists()  # left alone, not registered


def test_a_clean_exit_with_a_short_manifest_is_a_failure_that_keeps_the_recorded_part(
    window, monkeypatch
) -> None:
    monkeypatch.setattr("cmig.cli.main.main", _writing_main([], (STRAIN,)))
    job = window._agora2_fetch([STRAIN, OTHER])  # exit 0, but only one strain is recorded
    _wait_fetch(window, job)
    assert window.runner.poll(job).status is JobStatus.FAILED
    assert "only 1 of 2" in window.statusBar().currentMessage()
    _wait_import(window)
    assert [m.id for m in window.session.project.models] == [STRAIN]


def test_a_manifest_cannot_point_outside_its_batch_folder(window, monkeypatch) -> None:
    outside = _agora2_dir(window).parent / "outside.json"
    outside.write_text(_model_json("outside"))

    def lying(argv: list[str]) -> int:
        out = Path(_arg(argv, "--out"))
        out.mkdir(parents=True, exist_ok=True)
        (out / "agora2_manifest.json").write_text(json.dumps({"models": [
            {"id": STRAIN, "file": "../../outside.json", "source_url": f"{ORIGIN}x.xml"},
        ]}))
        return 0

    monkeypatch.setattr("cmig.cli.main.main", lying)
    job = window._agora2_fetch([STRAIN])
    _wait_fetch(window, job)
    assert window.runner.poll(job).status is JobStatus.FAILED
    assert not window._import_jobs and window.session.project.models == []


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
    (batch,) = _batches(window)
    assert (batch / f"{STRAIN}.json").exists()  # said, not hidden


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


# ── menu action and the size question ───────────────────────────────────────────────────

MB = 1024**2
GB = 1024**3


def _pick(monkeypatch, strains: list[Agora2Strain]) -> None:
    """Make the dialog open already searched, with every listed strain selected, and accept."""
    from cmig.gui import agora2_dialog

    def fake_exec(self) -> int:
        self._list_fn = lambda query: strains
        self.search_input.setText("Roseburia")
        self.search_btn.click()
        self.results.selectAll()
        return 1

    monkeypatch.setattr(agora2_dialog.Agora2Dialog, "exec", fake_exec)


def _ask(monkeypatch, answer: QMessageBox.StandardButton) -> list[tuple[str, object]]:
    """Answer the size question; the list collects (text, default button) of each ask."""
    asked: list[tuple[str, object]] = []

    def question(_parent, _title, text, _buttons=None, default=None):
        asked.append((text, default))
        return answer

    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
    return asked


def _record_fetches(window, monkeypatch) -> list[list[str]]:
    fetched: list[list[str]] = []
    monkeypatch.setattr(window, "_agora2_fetch", lambda strains: fetched.append(strains) or "j")
    return fetched


def test_the_dialog_hands_its_selection_to_the_fetch(window, monkeypatch) -> None:
    fetched = _record_fetches(window, monkeypatch)
    _pick(monkeypatch, [Agora2Strain(STRAIN, "15M"), Agora2Strain(OTHER, "15M")])
    window._agora2_dialog()
    assert fetched == [[STRAIN, OTHER]]
    assert all(type(s) is str for s in fetched[0])  # plain ids go to the CLI argv


def test_a_small_download_is_not_asked_about(window, monkeypatch) -> None:
    fetched = _record_fetches(window, monkeypatch)
    _pick(monkeypatch, [Agora2Strain(f"S_{i}", "100M") for i in range(10)])  # 1000 MB < 1 GB
    window._agora2_dialog()  # the autouse guard fails the test if a question is asked
    assert len(fetched) == 1


def test_exactly_one_gigabyte_is_not_asked_about(window, monkeypatch) -> None:
    fetched = _record_fetches(window, monkeypatch)
    _pick(monkeypatch, [Agora2Strain("S_1", "1G")])
    window._agora2_dialog()
    assert len(fetched) == 1


def test_a_download_over_one_gigabyte_waits_for_a_yes(window, monkeypatch) -> None:
    fetched = _record_fetches(window, monkeypatch)
    asked = _ask(monkeypatch, QMessageBox.StandardButton.No)
    _pick(monkeypatch, [Agora2Strain("S_1", "1G"), Agora2Strain("S_2", "1M")])
    window._agora2_dialog()
    assert fetched == []  # declined: nothing starts
    (text, default), = asked
    assert "2 strains" in text and "1.0 GB" in text and "very large" not in text
    assert default == QMessageBox.StandardButton.No  # Enter alone does not start it
    assert "not started" in window.statusBar().currentMessage()
    assert not window._agora2_jobs


def test_an_accepted_large_download_starts(window, monkeypatch) -> None:
    fetched = _record_fetches(window, monkeypatch)
    asked = _ask(monkeypatch, QMessageBox.StandardButton.Yes)
    _pick(monkeypatch, [Agora2Strain("S_1", "1G"), Agora2Strain("S_2", "1M")])
    window._agora2_dialog()
    assert fetched == [["S_1", "S_2"]] and len(asked) == 1


def test_eight_gigabytes_or_more_is_called_out_and_still_needs_a_yes(
    window, monkeypatch
) -> None:
    fetched = _record_fetches(window, monkeypatch)
    asked = _ask(monkeypatch, QMessageBox.StandardButton.No)
    _pick(monkeypatch, [Agora2Strain("S_1", "8G")])
    window._agora2_dialog()
    assert fetched == []
    assert "very large" in asked[0][0] and "8.0 GB" in asked[0][0]


def test_an_unknown_size_needs_a_yes_even_for_one_strain(window, monkeypatch) -> None:
    fetched = _record_fetches(window, monkeypatch)
    asked = _ask(monkeypatch, QMessageBox.StandardButton.No)
    _pick(monkeypatch, [Agora2Strain("S_1", "1M"), Agora2Strain("S_2", "")])
    window._agora2_dialog()
    assert fetched == []
    assert "1 of the 2 selected strains have no published size" in asked[0][0]
    # a bare id (no size at all) is just as unknown
    _pick(monkeypatch, [Agora2Strain("S_3")])
    window._agora2_dialog()
    assert fetched == [] and len(asked) == 2


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


@pytest.mark.parametrize(
    ("text", "expected"),
    [("15M", 15 * MB), ("1.5G", int(1.5 * GB)), ("512K", 512 * 1024), ("100", 100),
     (" 2m ", 2 * MB), ("", None), ("-", None), ("1.2.3", None), ("15 MB", None)],
)
def test_published_sizes_read_the_catalogue_notation(text: str, expected) -> None:
    assert published_bytes(text) == expected


def test_the_estimate_counts_unknown_sizes_apart() -> None:
    strains = [Agora2Strain("A_1", "10M"), Agora2Strain("A_2", ""), Agora2Strain("A_3", "5M"),
               "A_4"]
    assert download_estimate(strains) == (15 * MB, 2)


def test_the_dialog_shows_the_count_and_size_of_the_selection() -> None:
    dialog = Agora2Dialog(lambda _q: [
        Agora2Strain("A_1", "15M"), Agora2Strain("A_2", "5M"), Agora2Strain("A_3", ""),
    ])
    dialog.search_input.setText("A")
    dialog.search_btn.click()
    assert dialog.selection_summary.text() == ""
    dialog.results.item(0).setSelected(True)
    assert dialog.selection_summary.text() == "1 selected · about 15.0 MB to download"
    dialog.results.item(1).setSelected(True)
    assert dialog.selection_summary.text() == "2 selected · about 20.0 MB to download"
    dialog.results.item(2).setSelected(True)
    assert "3 selected" in dialog.selection_summary.text()
    assert "1 of unknown size, at least 20.0 MB" in dialog.selection_summary.text()
    dialog.results.clearSelection()
    assert dialog.selection_summary.text() == ""
    dialog.results.item(2).setSelected(True)
    assert dialog.selection_summary.text() == "1 selected · size unknown"
    assert [(s, s.published_size) for s in dialog.selected_entries()] == [("A_3", "")]
