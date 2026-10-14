"""A job of a project closed since it started never shows on the open project's pages."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402
from cmig.service import JobStatus  # noqa: E402

APP = QApplication.instance() or QApplication([])

_RANKED = {"target": "but", "ko_level": "gene", "warnings": [],
           "top_ranked": [{"member": "a", "gene": "g1", "score": 1.0, "target_flux": 2.0,
                           "community_growth": 0.3, "evaluation_status": "optimal"}]}

#: kind -> (job dict, entry for an out_dir, the page's status label, its run button, result)
_KINDS: dict[str, tuple[str, Callable[[Any, Path], Any], Callable[[Any], Any],
                        Callable[[Any], Any], Any]] = {
    "search": ("_search_jobs", lambda w, d: (d, w.search_view.request_fields("search")),
               lambda w: w.search_view.status, lambda w: w.search_view.run_btn, {}),
    "gene_ko": ("_gene_ko_jobs", lambda w, d: (d, w.gene_ko_page.request_fields("gene_ko")),
                lambda w: w.gene_ko_page.status, lambda w: w.gene_ko_page.run_btn, _RANKED),
    "host": ("_host_microbe_jobs", lambda w, d: d, lambda w: w.host_view.status,
             lambda w: w.host_view.run_btn, {}),
    "dfba": ("_dfba_jobs", lambda w, d: d, lambda w: w.dynamics_view.status,
             lambda w: w.dynamics_view.run_btn, {}),
    "spatial": ("_spatial_jobs", lambda w, d: d, lambda w: w.spatial_page.status,
                lambda w: w.spatial_page.run_btn, {}),
    "community": ("_community_jobs", lambda w, d: d, lambda w: w.community_builder.status,
                  lambda w: w.community_builder.run_btn, {}),
    "sweep": ("_sweep_jobs", lambda w, d: (d, "real"), lambda w: w.sweep_view.status,
              lambda w: w.sweep_view.run_btn, {}),
    "medium_growth": ("_medium_growth_jobs", lambda w, d: (d, {}),
                      lambda w: w.medium_editor.growth_label,
                      lambda w: w.medium_editor.check_growth_btn,
                      {"growth": 0.5, "status": "optimal", "cli_rc": 0}),
    "minimal_medium": ("_minimal_medium_jobs", lambda w, d: d,
                       lambda w: w.medium_editor.minimal_status,
                       lambda w: w.medium_editor.minimal_medium_btn,
                       {"status": "optimal", "cli_rc": 0, "exchanges": []}),
}


@pytest.mark.parametrize("outcome", ["done", "failed"])
@pytest.mark.parametrize("kind", sorted(_KINDS))
def test_a_previous_projects_job_never_shows_on_the_new_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, outcome: str
) -> None:
    jobs_name, entry, status, button, result = _KINDS[kind]
    make_project(tmp_path / "p1", ["a", "b"])
    make_project(tmp_path / "p2", ["x"])
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(tmp_path / "p1")
    gate = threading.Event()

    def _job(_ctx: Any) -> Any:
        gate.wait(10)
        if outcome == "failed":
            raise RuntimeError("the solve failed")
        return dict(result)

    jid = w.submit_job(kind, _job)
    out_dir = (tmp_path / "p1" / "runs" / f"{kind}-20261014-000000").resolve()
    out_dir.mkdir(parents=True)
    getattr(w, jobs_name)[jid] = entry(w, out_dir)
    button(w).setEnabled(False)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    assert w.open_project(tmp_path / "p2")
    # Were the job's result readable, it would be drawn: only the project decides.
    monkeypatch.setattr(w, "_inspect_gui_run", lambda d: {"artifact_integrity": "verified"})
    shown_page = w.pages.currentWidget()
    shown_status = status(w).text()  # the new project's own text (Sweep has a hint)
    p2_runs = [run.path for run in w.session.runs()]
    gate.set()
    deadline = time.time() + 10
    while w.runner.poll(jid).status not in (
        JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED
    ) and time.time() < deadline:
        time.sleep(0.02)
    w._poll_completed_jobs_pass()
    try:
        assert jid not in getattr(w, jobs_name)
        assert button(w).isEnabled()
        assert status(w).text() == shown_status
        assert "failed" not in shown_status and "complete" not in shown_status
        assert w.pages.currentWidget() is shown_page
        assert [run.path for run in w.session.runs()] == p2_runs
        assert w._external_runs == []
        assert not any(page.results.has_results() for page in w.analysis_pages.values())
    finally:
        w.close_project()
