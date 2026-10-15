"""dFBA does not start a run the CLI is certain to refuse.

User report: the dFBA page's default initial concentrations name glucose, oxygen and lactate
exchanges; on iAF987 (Geobacter, none of those) every run failed in the CLI with exit 2 and the
page showed a solver error. The page now checks the ids against the model's browse index first
and says which ones the model lacks. Without a usable index it runs as before (the CLI still
refuses), so the check can only remove a certain failure, never block a valid run.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import (  # noqa: E402
    _deterministic_qt_teardown,  # noqa: F401
    open_test_project,
)
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.service import JobRunner  # noqa: E402

APP = QApplication.instance() or QApplication([])

DEFAULT_INITIAL = "EX_glc__D_e=10,EX_o2_e=20,EX_ac_e=0,EX_lac__D_e=0"


def test_initial_ids_are_read_like_the_cli_reads_them():
    from cmig.gui.precheck import initial_exchange_ids

    assert initial_exchange_ids(" EX_glc__D_e=10, EX_o2_e = 20,,EX_ac_e=0") == [
        "EX_glc__D_e", "EX_o2_e", "EX_ac_e",
    ]
    assert initial_exchange_ids("") == []


def test_missing_ids_come_from_the_index_reactions_and_an_unusable_index_says_nothing():
    from cmig.gui.precheck import missing_from_index

    index = {"reactions": [{"id": "EX_ac_e"}, {"id": "PGI"}], "exchanges": ["EX_ac_e"]}
    assert missing_from_index(["EX_glc__D_e", "EX_ac_e"], index) == ["EX_glc__D_e"]
    assert missing_from_index(["EX_glc__D_e"], None) is None
    assert missing_from_index(["EX_glc__D_e"], {"reactions": [], "exchanges": []}) is None


@pytest.fixture
def w(tmp_path: Path):
    window = build_main_window(runner=JobRunner(max_workers=1))
    open_test_project(window, tmp_path / "p", ["iAF987", "b"])
    yield window
    window.close_project()


def _index(window, model_id: str, reactions: list[str]) -> None:
    from cmig.io import model_index

    project = window.session.require()
    entry = project.model(model_id)
    model_index.write_index(project.root, entry.sha256, entry.id, {
        "reactions": [{"id": rid} for rid in reactions], "metabolites": [], "genes": [],
        "exchanges": [rid for rid in reactions if rid.startswith("EX_")], "objective": [],
    })
    window._index_cache.pop(entry.sha256, None)


def test_dfba_names_the_ids_the_model_lacks_and_does_not_run(w, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr("cmig.cli.main.main", lambda argv: calls.append(argv) or 0)
    _index(w, "iAF987", ["EX_ac_e", "EX_fe3_e", "BIOMASS"])
    runs_before = sorted(p.name for p in w.session.require().runs_dir.iterdir())
    w.dynamics_view.model_picker.set_selected(["iAF987"])
    w.dynamics_view.initial_input.setText(DEFAULT_INITIAL)
    assert w.run_dfba() == ""
    status = w.dynamics_view.status.text()
    assert status.startswith("Not in iAF987: EX_glc__D_e, EX_o2_e, EX_lac__D_e."), status
    assert "Exchanges" in status  # the hint says where the model's own ids are listed
    assert not calls, "a run the CLI would refuse was started"
    assert sorted(p.name for p in w.session.require().runs_dir.iterdir()) == runs_before


def test_dfba_runs_when_every_id_is_in_the_model(w, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr("cmig.cli.main.main", lambda argv: calls.append(argv) or 2)
    _index(w, "iAF987", ["EX_ac_e", "EX_fe3_e", "BIOMASS"])
    w.dynamics_view.model_picker.set_selected(["iAF987"])
    w.dynamics_view.initial_input.setText("EX_ac_e=10,EX_fe3_e=20")
    assert w.run_dfba()


def test_dfba_without_a_usable_index_runs_as_before(w, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr("cmig.cli.main.main", lambda argv: calls.append(argv) or 2)
    w.dynamics_view.model_picker.set_selected(["b"])  # its index lists no reactions
    w.dynamics_view.initial_input.setText(DEFAULT_INITIAL)
    assert w.run_dfba()
