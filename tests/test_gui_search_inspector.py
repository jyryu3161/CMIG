"""Search Pareto figure choice and the read-only candidate inspector (GUI).

The GUI never computes anything here: every value shown comes from the synthetic
`search_summary.json` / `search_evaluations.json` written by the test.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.core.workflow_manifest import artifact_result_digest  # noqa: E402
from cmig.gui.app import build_main_window  # noqa: E402
from cmig.service import JobRunner  # noqa: E402

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20">'
       '<rect width="40" height="20" fill="red"/></svg>')


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


SINGLE: dict[str, Any] = {
    "status": "ok", "strategy": "exhaustive", "target": "ac", "warnings": [],
    "top_ranked": [
        {"rank": 1, "members": ["A", "B"], "score": 1.5, "target_flux": 1.5,
         "community_growth": 0.2, "robustness_fva_lo": 1.25, "robustness_fva_hi": 1.75,
         "robustness_status": "optimal", "status": "optimal", "diagnostic": None,
         "effective_members": ["A", "B"], "member_growth": {"A": 0.11, "B": 0.09},
         "abundances": {"A": 0.55, "B": 0.45}},
        {"rank": 2, "members": ["A", "C"], "score": 0.75, "target_flux": 0.75,
         "community_growth": 0.3, "status": "optimal", "diagnostic": "slow_solve: took long"},
    ],
}
SINGLE_EVALS = {"policy": "p", "rows": [
    {"rank": 1, "members": ["A", "B"], "score": 1.5, "target_flux": 1.5,
     "timings": {"solve_s": 3.25}},
    {"rank": 2, "members": ["A", "C"], "score": 0.75, "target_flux": 0.75,
     "timings": {"solve_s": 4.5}},
]}


def _multi_row(rank: int, members: list[str], fluxes: dict[str, float],
               scores: dict[str, float], **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "rank": rank, "members": members, "weighted_score": sum(scores.values()),
        "effective_members": members, "member_growth": {m: 0.1 * (i + 1)
                                                        for i, m in enumerate(members)},
        "abundances": {m: round(1 / len(members), 3) for m in members},
        "pareto": False, "community_growth": 0.25, "status": "optimal",
        "target_fluxes": fluxes, "target_scores": scores, "missing_targets": [],
        "flux_basis": "joint_weighted_lp", "diagnostic": None, "sampling_status": "complete",
    }
    row.update(extra)
    return row


MULTI: dict[str, Any] = {
    "kind": "multi_target_model_pool_search", "status": "ok", "strategy": "exhaustive",
    "targets": ["ac", "but"], "metric": "normalized_weighted", "warnings": [],
    "top_ranked": [
        _multi_row(1, ["A", "B"], {"ac": 1.25, "but": 2.5}, {"ac": 0.375, "but": 0.5}),
        _multi_row(2, ["A", "C"], {"ac": 0.5, "but": 3.5}, {"ac": 0.125, "but": 0.625},
                   flux_basis="per_target_capability_not_simultaneous",
                   missing_targets=["ac"], sampling_status="partial"),
    ],
}
MULTI_EVALS = {"policy": "p", "rows": [
    dict(MULTI["top_ranked"][0], timings={"solve_s": 1.5}),
    dict(MULTI["top_ranked"][1], timings={"solve_s": 2.5}),
]}

PARETO: dict[str, Any] = {
    "kind": "multi_target_model_pool_search", "status": "ok", "strategy": "exhaustive",
    "targets": ["ac", "but"], "metric": "pareto", "warnings": [],
    "top_ranked": [
        _multi_row(1, ["A", "B"], {"ac": 4.25, "but": 0.5}, {"ac": 4.25, "but": 0.5},
                   pareto=True),
        _multi_row(2, ["A", "B"], {"ac": 0.75, "but": 3.75}, {"ac": 0.75, "but": 3.75},
                   pareto=True),
        _multi_row(3, ["A", "C"], {"ac": 1.0, "but": 1.0}, {"ac": 1.0, "but": 1.0}),
    ],
}
PARETO_EVALS = {
    "policy": "p",
    "rows": [dict(r, timings={}) for r in PARETO["top_ranked"]],
    "pareto_attempts": [
        {"members": ["A", "B"], "attempt_key": "A|B:0000", "order": 0, "phase": "anchor",
         "target": "ac", "direction": "max_secretion", "objective_weights": {"ac": 1.0},
         "constraint_floors": {}, "raw_status": "optimal", "outcome": "optimal",
         "diagnostic": None, "achieved_vector": {"ac": 4.25, "but": 0.5}},
        {"members": ["A", "B"], "attempt_key": "A|B:0001", "order": 1, "phase": "epsilon",
         "target": "but", "direction": "max_secretion", "objective_weights": {"but": 1.0},
         "constraint_floors": {"ac": 0.7}, "raw_status": "time_limit", "outcome": "timeout",
         "diagnostic": "time limit", "achieved_vector": None},
        {"members": ["A", "C"], "attempt_key": "A|C:0000", "order": 0, "phase": "anchor",
         "target": "ac", "direction": "max_secretion", "objective_weights": {"ac": 1.0},
         "constraint_floors": {}, "raw_status": "optimal", "outcome": "optimal",
         "diagnostic": None, "achieved_vector": {"ac": 1.0, "but": 1.0}},
    ],
    "candidate_sampling_status": {"A+B": "complete", "A+C": "complete"},
}


def _publish(out: Path, summary: dict[str, Any], evaluations: Any = None,
             extra: dict[str, str] | None = None) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    (out / "search_summary.json").write_text(json.dumps(summary))
    if isinstance(evaluations, str):
        (out / "search_evaluations.json").write_text(evaluations)
    elif evaluations is not None:
        (out / "search_evaluations.json").write_text(json.dumps(evaluations))
    for name, text in (extra or {}).items():
        (out / name).write_text(text)
    (out / "manifest.json").write_text(json.dumps({
        "manifest_scope": "workflow", "manifest_schema_version": "1.2",
        "workflow_kind": "search", "artifacts": ["search_summary.json"],
        "result_digest": artifact_result_digest(out, "search", ["search_summary.json"]),
    }))
    return out


@pytest.fixture
def window():
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    yield w
    w.close()
    runner.shutdown()


def _open(w, run: Path) -> None:
    w.load_run_dir(run)
    assert w.current_search_dir == run.resolve()


def _row_for(view, rank: int) -> int:
    """Locate the table row whose *displayed* flux belongs to recorded rank `rank`."""
    for r in range(view.table.rowCount()):
        if view.table.item(r, 0).data(Qt.ItemDataRole.UserRole) is not None:
            record = view.row_record(r)
            if record is not None and record.get("rank") == rank:
                return r
    raise AssertionError(f"no row for rank {rank}")


def _inspect(view, row: int) -> str:
    view.table.clearSelection()
    view.table.selectRow(row)
    return view.inspector.toPlainText()


# ------------------------------------------------------------------ figure choice


def _choices(view) -> list[tuple[str, str]]:
    combo = view.figure_mode_combo
    return [(combo.itemText(i), combo.itemData(i)) for i in range(combo.count())]


def test_pareto_figure_choice_only_when_file_exists(window, tmp_path):
    view = window.search_view
    run = _publish(tmp_path / "with", PARETO, PARETO_EVALS,
                   {"search_plot.svg": SVG, "search_pareto.svg": SVG})
    _open(window, run)
    assert ("Pareto trade-off", "search_pareto.svg") in _choices(view)
    index = view.figure_mode_combo.findData("search_pareto.svg")
    view.figure_mode_combo.setCurrentIndex(index)
    assert view.selected_figure_artifact() == "search_pareto.svg"
    assert view.export_figure_btn.isEnabled()
    assert view.figure_stack.currentWidget() is view.figure_view

    run2 = _publish(tmp_path / "without", PARETO, PARETO_EVALS, {"search_plot.svg": SVG})
    _open(window, run2)
    assert "search_pareto.svg" not in [data for _, data in _choices(view)]


def test_unreadable_pareto_figure_clears_preview_and_disables_export(window, tmp_path):
    view = window.search_view
    run = _publish(tmp_path / "bad", PARETO, PARETO_EVALS,
                   {"search_pareto.svg": "<svg not really"})
    _open(window, run)
    view.figure_mode_combo.setCurrentIndex(view.figure_mode_combo.findData("search_pareto.svg"))
    if hasattr(view.figure_view, "renderer"):
        assert view.figure_stack.currentWidget() is view.figure_placeholder
        assert not view.export_figure_btn.isEnabled()


# ------------------------------------------------------------------ inspector content


def test_inspector_empty_until_a_row_is_selected(window, tmp_path):
    view = window.search_view
    _open(window, _publish(tmp_path / "r", MULTI, MULTI_EVALS))
    assert view.inspector.isReadOnly()
    assert view.inspector.toPlainText() == ""


def test_single_target_inspector_shows_recorded_fields(window, tmp_path):
    view = window.search_view
    _open(window, _publish(tmp_path / "r", SINGLE, SINGLE_EVALS))
    text = _inspect(view, _row_for(view, 1))
    assert "Members: A + B" in text
    assert "Effective members: A + B" in text
    assert "Target flux: 1.5" in text
    assert "Community growth: 0.2" in text
    assert "FVA range: 1.25..1.75" in text
    assert "Member growth: A=0.11, B=0.09" in text
    assert "Abundances: A=0.55, B=0.45" in text
    assert "Timings: solve_s=3.25" in text
    text2 = _inspect(view, _row_for(view, 2))
    assert "Members: A + C" in text2
    assert "Diagnostic: slow_solve: took long" in text2
    # Not recorded for this row: never shown as 0.
    assert "FVA range: not recorded" in text2
    assert "Member growth: not recorded" in text2
    assert "Abundances: not recorded" in text2
    assert "Effective members: not recorded" in text2
    assert "Timings: solve_s=4.5" in text2


def test_multi_target_inspector_shows_fluxes_scores_and_basis(window, tmp_path):
    view = window.search_view
    _open(window, _publish(tmp_path / "r", MULTI, MULTI_EVALS))
    text = _inspect(view, _row_for(view, 1))
    assert "Rank: 1" in text
    assert "ac: flux 1.25 · contribution 0.375" in text
    assert "but: flux 2.5 · contribution 0.5" in text
    assert "achieved together in one solution" in text
    assert "Missing targets: none" in text
    assert "Sampling status: complete" in text
    assert "Diagnostic: none" in text
    assert "Timings: solve_s=1.5" in text
    text2 = _inspect(view, _row_for(view, 2))
    assert "each target solved separately" in text2
    assert "not simultaneously achievable" in text2
    assert "Missing targets: ac" in text2
    assert "Sampling status: partial" in text2
    assert "Pareto" not in text2  # not a pareto-metric run


def test_pareto_rows_with_identical_members_show_their_own_records(window, tmp_path):
    view = window.search_view
    _open(window, _publish(tmp_path / "r", PARETO, PARETO_EVALS))
    first = _inspect(view, _row_for(view, 1))
    second = _inspect(view, _row_for(view, 2))
    assert first != second
    assert "ac: flux 4.25" in first and "ac: flux 0.75" not in first
    assert "ac: flux 0.75" in second and "ac: flux 4.25" not in second
    for text in (first, second):
        assert "A|B:0000" in text and "A|B:0001" in text
        assert "A|C:0000" not in text
        assert "timeout" in text
        assert "floors: ac=0.7" in text
    third = _inspect(view, _row_for(view, 3))
    assert "A|C:0000" in third and "A|B:0000" not in third


def test_record_mapping_survives_table_reordering(window, tmp_path):
    view = window.search_view
    _open(window, _publish(tmp_path / "r", PARETO, PARETO_EVALS))
    view.table.sortItems(3, Qt.SortOrder.DescendingOrder)
    for rank, flux in ((1, "ac: flux 4.25"), (2, "ac: flux 0.75"), (3, "ac: flux 1")):
        row = _row_for(view, rank)
        assert flux in _inspect(view, row)
        # The displayed flux cell of this row is the inspected record's own flux.
        assert flux.split("flux ")[1] in view.table.item(row, 3).text()


def test_clicking_a_single_cell_inspects_its_row(window, tmp_path):
    view = window.search_view
    _open(window, _publish(tmp_path / "r", PARETO, PARETO_EVALS))
    row = _row_for(view, 2)
    view.table.clearSelection()
    view.table.setCurrentCell(row, 4)
    assert "ac: flux 0.75" in view.inspector.toPlainText()


def test_missing_fields_show_not_recorded(window, tmp_path):
    view = window.search_view
    bare = {"status": "ok", "strategy": "exhaustive", "targets": ["ac", "but"],
            "metric": "pareto", "warnings": [],
            "top_ranked": [{"members": ["A", "B"], "target_fluxes": {"ac": 1.0, "but": None},
                            "status": "optimal"}]}
    _open(window, _publish(tmp_path / "r", bare, {"policy": "p", "rows": []}))
    text = _inspect(view, 0)
    for label in ("Rank", "Effective members", "Community growth", "Member growth",
                  "Abundances", "Flux basis", "Missing targets", "Sampling status",
                  "Diagnostic", "Timings", "Pareto ε attempts"):
        assert f"{label}: not recorded" in text, label
    assert "but: flux not recorded · contribution not recorded" in text
    assert "ac: flux 1 · contribution not recorded" in text


def test_corrupt_evaluations_show_unreadable(window, tmp_path):
    view = window.search_view
    _open(window, _publish(tmp_path / "r", PARETO, "{not json"))
    text = _inspect(view, _row_for(view, 1))
    assert "unreadable" in text
    assert "ac: flux 4.25" in text  # summary-recorded fields still shown
    _open(window, _publish(tmp_path / "r2", PARETO, json.dumps(["not", "an", "object"])))
    assert "unreadable" in _inspect(view, _row_for(view, 1))


def test_missing_evaluations_show_unreadable(window, tmp_path):
    view = window.search_view
    _open(window, _publish(tmp_path / "r", MULTI))
    assert "search_evaluations.json: unreadable" in _inspect(view, _row_for(view, 1))


def test_invalidation_clears_inspector(window, tmp_path):
    view = window.search_view
    _open(window, _publish(tmp_path / "r", MULTI, MULTI_EVALS))
    assert _inspect(view, 0)
    view.invalidate_results()
    assert view.inspector.toPlainText() == ""
    assert view.row_record(0) is None


def test_just_finished_run_matches_reopened_run(window, tmp_path, monkeypatch):
    import cmig.cli.main

    def fake_main(argv: list[str]) -> int:
        out = Path(argv[argv.index("--out") + 1])
        _publish(out, PARETO, PARETO_EVALS, {"search_pareto.svg": SVG})
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    view = window.search_view
    pool = tmp_path / "pool"
    pool.mkdir()
    view.model_dir_input.setText(str(pool))
    view.set_target_rows([("ac",), ("but",)])
    jid = window.run_search_fixture()
    assert jid
    window.runner.result(jid, timeout=10)
    window._poll_completed_jobs()
    out = window.current_search_dir
    assert out is not None
    assert "search_pareto.svg" in [data for _, data in _choices(view)]
    fresh = [_inspect(view, _row_for(view, rank)) for rank in (1, 2, 3)]
    view.invalidate_results()
    assert view.inspector.toPlainText() == ""
    _open(window, out)
    reopened = [_inspect(view, _row_for(view, rank)) for rank in (1, 2, 3)]
    assert fresh == reopened


def test_korean_mode_inspector(tmp_path):
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner, lang="ko")
    try:
        run = _publish(tmp_path / "r", PARETO, PARETO_EVALS, {"search_pareto.svg": SVG})
        _open(w, run)
        view = w.search_view
        assert "Pareto trade-off" in [view.figure_mode_combo.itemText(i)
                                      for i in range(view.figure_mode_combo.count())]
        assert "A|B:0001" in _inspect(view, _row_for(view, 1))
    finally:
        w.close()
        runner.shutdown()


def test_window_fits_with_inspector_content(tmp_path):
    app = _app()
    long = copy.deepcopy(PARETO)
    long["top_ranked"][0]["diagnostic"] = "x" * 2000
    run = _publish(tmp_path / "r", long, PARETO_EVALS, {"search_pareto.svg": SVG})
    for lang in ("en", "ko"):
        window = build_main_window(lang=lang)
        window.load_run_dir(run)
        view = window.search_view
        _inspect(view, _row_for(view, 1))
        window.tabs.setCurrentWidget(view)
        for size in ((1280, 800), (1500, 950)):
            window.resize(*size)
            window.show()
            app.processEvents()
            assert (window.width(), window.height()) == size
        window.close()
