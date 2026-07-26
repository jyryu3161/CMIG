"""Round-5 track P2 regression tests — GUI presentation must not discard or fabricate.

Every test here pins a defect confirmed by the round-5 P2 reviewers (and by the
coordinator log CC-6 / CC-8 / CC-9 / CC-10). The shared class of defect is:
*the honest signal exists in the run artifact and the Qt presentation layer drops it,
or lets the user overwrite it*. These tests fail on the pre-fix tree.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QAbstractItemView, QApplication  # noqa: E402

from cmig.gui.app import (  # noqa: E402
    _abundance_impact_summary_for_search_view,
    _host_search_summary_for_search_view,
    _strain_growth_summary_for_search_view,
    build_main_window,
)
from cmig.service import JobRunner, JobStatus  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _wait(runner: JobRunner, jid: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if runner.poll(jid).status not in (JobStatus.PENDING, JobStatus.RUNNING):
            return
        time.sleep(0.01)
    raise AssertionError(f"job {jid} did not finish within {timeout}s")


# --------------------------------------------------------------------------------------
# CC-8 — gene-KO argv must be frozen at click time, not read off live widgets on a worker
# --------------------------------------------------------------------------------------


def test_gene_ko_argv_is_frozen_at_click_time(monkeypatch, tmp_path):
    """CC-8 (P0): spin-box values must be snapshotted in the GUI thread before submit.

    Pre-fix, `--max-genes`/`--top-k` were read inside the worker closure, so a queued run
    silently executed parameters the researcher never confirmed (and read QWidgets off the
    GUI thread, which is undefined behaviour in Qt).
    """
    import cmig.cli.main

    seen: dict[str, list[str]] = {}
    release = threading.Event()

    def fake_main(argv):
        seen["argv"] = list(argv)
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "gene_ko_summary.json").write_text(
            json.dumps({"target": "ac", "top_ranked": [], "warnings": []})
        )
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    # Occupy the single worker so the gene-KO job is queued, exactly like a busy session.
    runner.submit("occupy", lambda ctx: release.wait(timeout=20))
    w.search_view.model_dir_input.setText(str(tmp_path))
    w.search_view.ko_members_input.setText("iHN637")
    w.search_view.targets_input.setText("ac")
    w.search_view.ko_max_genes_spin.setValue(50)
    w.search_view.top_k_spin.setValue(3)
    jid = w.run_gene_ko_search()
    assert jid
    # The researcher now prepares the *next* run while the first is still queued.
    w.search_view.ko_max_genes_spin.setValue(5000)
    w.search_view.top_k_spin.setValue(97)
    release.set()
    _wait(runner, jid)
    argv = seen["argv"]
    assert argv[argv.index("--max-genes") + 1] == "50"
    assert argv[argv.index("--top-k") + 1] == "3"
    runner.shutdown()


# --------------------------------------------------------------------------------------
# Warnings and per-row diagnostics must reach the researcher
# --------------------------------------------------------------------------------------


def test_search_view_adapters_forward_cli_warnings():
    """P0: three of four SearchView adapters hardcoded `warnings: []`."""
    payload = {"warnings": ["pfba_stage_failed; reporting non-parsimonious flux distribution"]}
    for adapter in (
        _host_search_summary_for_search_view,
        _strain_growth_summary_for_search_view,
        _abundance_impact_summary_for_search_view,
    ):
        summary = adapter(dict(payload))
        assert summary["warnings"] == payload["warnings"], adapter.__name__


def test_solver_failed_row_is_not_displayed_as_optimal():
    """P0: a row carrying a solver_error diagnostic rendered `Status: optimal`."""
    _app()
    w = build_main_window()
    diagnostic = {
        "code": "solver_error",
        "message": "pFBA flux stage failed: GurobiError: Unable to retrieve attribute 'X'",
    }
    w.search_view.load_summary({
        "strategy": "abundance-impact",
        "target": "ac",
        "top_ranked": [
            {
                "members": ["iHN637@0.25"],
                "score": 0.5,
                "target_flux": 7.144,
                "community_growth": 0.5768,
                "status": "optimal",
                "diagnostic": diagnostic,
            },
            {
                "members": ["iHN637@0.5"],
                "score": 0.5,
                "target_flux": 3.8,
                "community_growth": 0.5,
                "status": "optimal",
            },
        ],
    })
    flagged = w.search_view.table.item(0, 6)
    clean = w.search_view.table.item(1, 6)
    assert flagged.text() != "optimal", "diagnostic-bearing row must not read as a clean optimal"
    assert "solver_error" in (flagged.toolTip() or "")
    assert clean.text() == "optimal"
    # a warning count must also be visible when the summary carries warnings
    assert w.search_view.status.text()


def test_flux_column_does_not_fall_back_to_score():
    """P0: a null target_flux was rendered as the Score value, not as `—`."""
    _app()
    w = build_main_window()
    w.search_view.load_summary({
        "strategy": "strain-growth",
        "target": "growth",
        "top_ranked": [{
            "members": ["iX"],
            "score": 0.42,
            "target_flux": None,
            "community_growth": 0.9,
            "status": "optimal",
        }],
    })
    assert w.search_view.table.item(0, 3).text() == "—"


def test_abundance_impact_surfaces_community_target_exchange():
    """P0: the GUI showed the *member* exchange under a *community* target label."""
    summary = _abundance_impact_summary_for_search_view({
        "target": "ac",
        "target_member": "iHN637",
        "rows": [{
            "target_abundance": 0.25,
            "target_influence_share": 0.5,
            "target_member_exchange": 7.1444,
            "community_target_exchange": 0.0,
            "community_growth": 0.5768,
            "status": "optimal",
        }],
    })
    labels = summary.get("column_labels")
    assert labels is not None, "per-workflow column labels are required"
    _app()
    w = build_main_window()
    w.search_view.load_summary(summary)
    headers = [
        w.search_view.table.horizontalHeaderItem(c).text()
        for c in range(w.search_view.table.columnCount())
    ]
    assert headers == list(labels)
    row = [w.search_view.table.item(0, c).text() for c in range(7)]
    assert "7.144" in row[3]
    assert "0" == row[5] or row[5].startswith("0"), (
        f"community_target_exchange must be visible next to the member exchange; got {row}"
    )


# --------------------------------------------------------------------------------------
# Result tables must be read-only; a typed number must not look computed
# --------------------------------------------------------------------------------------


def test_result_tables_are_read_only():
    """P0: a double-click + keystroke replaced a solved flux with an arbitrary value."""
    _app()
    w = build_main_window()
    w._set_advanced_tabs_visible(True)
    none = QAbstractItemView.EditTrigger.NoEditTriggers
    result_tables = {
        "search": w.search_view.table,
        "profile": w.profile_view.table,
        "dynamics": w.dynamics_view.table,
        "sweep": w.sweep_view.table,
        "host_iface": w.host_view.iface_table,
        "host_cross": w.host_view.cross_table,
        "sandbox_delta": w.sandbox_view.delta_view,
        "compare_delta": w.scenario_compare.delta_view,
        "model_exchanges": w.model_manager.exchange_table,
        "jobs": w.jobs_panel,
    }
    editable = {
        name: str(table.editTriggers())
        for name, table in result_tables.items()
        if table.editTriggers() != none
    }
    assert editable == {}, f"result tables must be read-only: {editable}"
    # input tables stay editable
    assert w.medium_editor.table.editTriggers() != none
    assert w.sandbox_view.bound_table.editTriggers() != none
    assert w.community_builder.table.editTriggers() != none


# --------------------------------------------------------------------------------------
# Host tab — export must follow the displayed run; a missing host block is not a conclusion
# --------------------------------------------------------------------------------------


def test_failed_host_load_does_not_advance_the_export_pointer(tmp_path):
    """P0: `current_host_microbe_dir` advanced before the summary was validated, so
    Export Figure could write run B's SVG while the tables still showed run A."""
    _app()
    w = build_main_window()
    run_a = tmp_path / "runA"
    run_a.mkdir()
    (run_a / "host_microbe_bigg_summary.json").write_text(json.dumps({
        "host": {"viable": True, "status": "optimal", "objective_value": 0.77},
        "microbe_to_host": {"ac": 1.0},
        "microbial_secretion": {"ac": 1.0},
    }))
    (run_a / "interaction_circle.svg").write_text("<svg><!--RUN-A-FIGURE--></svg>")
    run_b = tmp_path / "runB"
    run_b.mkdir()
    (run_b / "host_microbe_bigg_summary.json").write_text("{ truncated")
    (run_b / "interaction_circle.svg").write_text("<svg><!--RUN-B-FIGURE--></svg>")

    assert w.load_host_microbe_bigg_dir(run_a) is True
    assert w.load_host_microbe_bigg_dir(run_b) is False
    assert w.host_view.current_run_dir == run_a.resolve()
    assert w.current_host_microbe_dir == run_a.resolve()


def test_host_summary_without_host_block_is_not_reported_as_non_viable(tmp_path):
    """P0: absence of a `host` block was rendered as the biological conclusion
    'non-viable — microbiome support insufficient'."""
    _app()
    w = build_main_window()
    run = tmp_path / "run"
    run.mkdir()
    (run / "host_microbe_bigg_summary.json").write_text(
        json.dumps({"microbe_to_host": {"ac": 1.0}})
    )
    assert w.load_host_microbe_bigg_dir(run) is False
    assert "microbiome support insufficient" not in w.host_view.viability_label.text()
    assert "host" in w.statusBar().currentMessage().lower()


# --------------------------------------------------------------------------------------
# Stale results must not survive an input change
# --------------------------------------------------------------------------------------


def test_search_results_are_cleared_when_answer_inputs_change(tmp_path):
    """P0: the ranked table survived a change of target, pool and combination size."""
    _app()
    w = build_main_window()
    w.search_view.load_summary({
        "strategy": "exhaustive",
        "top_ranked": {"ac": [{
            "members": ["iHN637", "iYO844"],
            "score": 12.11,
            "target_flux": 12.11,
            "community_growth": 0.297,
            "status": "optimal",
        }]},
    }, run_dir=tmp_path)
    assert w.search_view.table.rowCount() == 1
    w.search_view.targets_input.setText("but2")  # default is "but"; must actually change
    assert w.search_view.table.rowCount() == 0
    assert w.search_view.current_run_dir is None
    assert "re-run" in w.search_view.status.text().lower()


def test_dfba_results_are_cleared_when_answer_inputs_change(tmp_path):
    _app()
    w = build_main_window()
    w.dynamics_view.load_dfba_summary(
        {"status": "completed", "final_t": 1.0, "final_biomass": 2.5,
         "final_concentrations": {"EX_glc__D_e": 3.0}, "warnings": []},
        run_dir=tmp_path,
    )
    assert w.dynamics_view.table.rowCount() == 1
    w.dynamics_view.t_end_spin.setValue(9.0)
    assert w.dynamics_view.table.rowCount() == 0


def test_host_results_are_cleared_when_answer_inputs_change():
    _app()
    w = build_main_window()
    w.host_view.load_host_result(
        SimpleNamespace(viable=True, biomass=1.234, status="optimal", interface_fluxes=[])
    )
    assert "1.234" in w.host_view.viability_label.text()
    w.host_view.host_path_input.setText("/tmp/new-host.xml")
    assert "1.234" not in w.host_view.viability_label.text()


def test_failed_run_load_clears_previous_provenance(tmp_path):
    """P0: after a failed `load_run_dir` the previous run's manifest/profile stayed on screen."""
    _app()
    w = build_main_window()
    w.current_manifest = {"run_hash": "29844e2910360332"}
    w.profile_view.load_profile([{"metabolite": "ac", "net_flux": 5.153, "label": "secretion"}])
    broken = tmp_path / "broken"
    broken.mkdir()
    w.load_run_dir(broken)
    assert w.current_manifest is None
    assert w.profile_view.table.rowCount() == 0


# --------------------------------------------------------------------------------------
# CC-6 — dFBA "NOT interpretable" verdict must be surfaced and fixable
# --------------------------------------------------------------------------------------


def test_dfba_untracked_uptake_warning_is_surfaced(tmp_path):
    """CC-6 (P0): the GUI showed an explicitly not-interpretable dFBA run as `completed`."""
    _app()
    w = build_main_window()
    w.dynamics_view.load_dfba_summary({
        "status": "completed",
        "final_t": 0.1,
        "final_biomass": 0.010876095314013482,
        "final_concentrations": {"EX_glc__D_e": 9.9},
        "n_untracked_uptake": 14,
        "warnings": [
            "growth was supported by 14 UNCONSTRAINED default-medium substrates outside the "
            "tracked set: a Km sweep on the tracked substrate is NOT interpretable."
        ],
    }, run_dir=tmp_path)
    status = w.dynamics_view.status.text()
    assert "warning" in status.lower()
    assert "14" in status
    # the caveat itself must be visible, not only counted
    assert w.dynamics_view.warning_label.isVisible() or w.dynamics_view.warning_label.text()
    assert "NOT interpretable" in w.dynamics_view.warning_label.text()
    row = [w.dynamics_view.table.item(0, c).text() for c in range(4)]
    assert row[1] != "completed", f"status cell must flag the warning, got {row}"


def test_dfba_request_exposes_close_untracked_uptake(monkeypatch, tmp_path):
    """CC-6 (P0): the GUI must expose the control that makes the run interpretable."""
    import cmig.cli.main

    seen: dict[str, list[str]] = {}

    def fake_main(argv):
        seen["argv"] = list(argv)
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "dfba_summary.json").write_text(json.dumps({
            "status": "completed", "final_t": 0.1, "final_biomass": 0.01,
            "final_concentrations": {}, "warnings": [], "n_untracked_uptake": 0,
        }))
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    assert hasattr(w.dynamics_view, "close_untracked_check")
    request = w.dynamics_view.dfba_request()
    assert "close_untracked_uptake" in request
    w.dynamics_view.model_path_input.setText(str(tmp_path / "m.xml"))
    w.dynamics_view.out_dir_input.setText(str(tmp_path / "out"))
    w.dynamics_view.close_untracked_check.setChecked(True)
    jid = w.run_dfba()
    _wait(runner, jid)
    assert "--close-untracked-uptake" in seen["argv"]
    runner.shutdown()


# --------------------------------------------------------------------------------------
# CC-9 — the Constraint Sandbox must not solve on the Qt main thread
# --------------------------------------------------------------------------------------


def test_sandbox_preview_does_not_block_the_event_loop(monkeypatch):
    """CC-9 (P1/blocking): the sandbox solved synchronously in its slot (2190 ms measured,
    0 heartbeat ticks). It must go through JobRunner like every other solve view."""
    from PySide6.QtCore import QTimer

    import cmig.service
    from cmig.core.delta import DeltaResult

    class SlowEngineService:
        def sandbox_fixture(self, *, reaction_id, lower, upper, commit, out_dir):
            time.sleep(0.6)
            return SimpleNamespace(
                delta=DeltaResult([], [], [], 0.0), run_hash="hash" if commit else None
            )

    monkeypatch.setattr(cmig.service, "EngineService", SlowEngineService)
    app = _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    w.sandbox_view.add_bound("EX_glc__D_e", -1.0, 1000.0)
    ticks: list[float] = []
    timer = QTimer(w)
    timer.setInterval(20)
    timer.timeout.connect(lambda: ticks.append(time.monotonic()))
    timer.start()
    t0 = time.monotonic()
    w._run_sandbox(commit=False)
    elapsed = time.monotonic() - t0
    assert elapsed < 0.3, f"the slot itself must not solve; it blocked for {elapsed:.3f}s"
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and w._sandbox_jobs:
        app.processEvents()
        w._poll_completed_jobs()
        time.sleep(0.02)
    timer.stop()
    assert ticks, "the event loop must keep delivering timer ticks during the sandbox solve"
    assert "preview" in w.sandbox_view.status.text()
    runner.shutdown()


def test_sandbox_non_numeric_bound_reports_instead_of_raising(monkeypatch):
    """P1: `float('-')` escaped the Qt slot and left the previous delta on screen."""
    import cmig.service
    from cmig.core.delta import DeltaResult

    class FakeEngineService:
        def sandbox_fixture(self, **kwargs):
            raise AssertionError("must not solve with an invalid bound")

    monkeypatch.setattr(cmig.service, "EngineService", FakeEngineService)
    _app()
    w = build_main_window()
    w.sandbox_view.delta_view.load_delta(DeltaResult([], [], [], 0.0))
    w.sandbox_view.add_bound("EX_glc__D_e", -1.0, 1000.0)
    w.sandbox_view.bound_table.item(0, 1).setText("-")
    w._run_sandbox(commit=False)  # must not raise
    assert "not a number" in w.sandbox_view.status.text().lower()


# --------------------------------------------------------------------------------------
# Community Builder — the namespace gate must be reachable
# --------------------------------------------------------------------------------------


def test_community_solve_blocks_until_namespace_is_confirmed(tmp_path):
    """P0/P1: the tab always failed at the CLI namespace gate because neither
    `--assume-bigg-namespace` nor `--namespace-decisions` was reachable from the GUI."""
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    pool = tmp_path / "pool"
    pool.mkdir()
    (pool / "iHN637.xml").write_text("<sbml/>")
    w.community_builder.model_dir_input.setText(str(pool))
    assert hasattr(w.community_builder, "assume_bigg_check")
    jid = w.run_community_solve()
    assert jid == ""
    assert "namespace" in w.community_builder.status.text().lower()
    runner.shutdown()


def test_community_solve_passes_namespace_confirmation(monkeypatch, tmp_path):
    import cmig.cli.main

    seen: dict[str, list[str]] = {}

    def fake_main(argv):
        seen["argv"] = list(argv)
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "manifest.json").write_text(json.dumps({"run_hash": "abc123def456"}))
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    pool = tmp_path / "pool"
    pool.mkdir()
    (pool / "iHN637.xml").write_text("<sbml/>")
    (pool / "iYO844.xml").write_text("<sbml/>")
    w.community_builder.model_dir_input.setText(str(pool))
    w.community_builder.assume_bigg_check.setChecked(True)
    jid = w.run_community_solve()
    runner.result(jid, timeout=10)
    assert "--assume-bigg-namespace" in seen["argv"]
    runner.shutdown()


def test_community_invalid_abundance_reports_instead_of_raising(tmp_path):
    """P1: `float('0.5x')` escaped the Run Community slot as a raw traceback."""
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    pool = tmp_path / "pool"
    pool.mkdir()
    (pool / "iHN637.xml").write_text("<sbml/>")
    w.community_builder.model_dir_input.setText(str(pool))
    w.community_builder.assume_bigg_check.setChecked(True)
    w.community_builder.add_member("iHN637", 0.5)
    w.community_builder.table.item(0, 1).setText("0.5x")
    jid = w.run_community_solve()  # must not raise
    assert jid == ""
    assert "not a number" in w.community_builder.status.text().lower()
    runner.shutdown()


# --------------------------------------------------------------------------------------
# Target handling — never substitute or truncate a scientific request
# --------------------------------------------------------------------------------------


def test_multi_target_text_is_rejected_not_truncated(tmp_path):
    """P0/P2: `ac,but` silently became an acetate-only experiment."""
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    w.search_view.model_dir_input.setText(str(tmp_path))
    w.search_view.targets_input.setText("ac,but")
    assert w.run_search_fixture() == ""
    assert "single metabolite" in w.search_view.status.text().lower()
    runner.shutdown()


def test_empty_target_is_rejected_by_every_search_button(tmp_path):
    """P2: an empty Target box meant `but` for Run Search and `ac` for Rank Gene KOs."""
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    w.search_view.model_dir_input.setText(str(tmp_path))
    w.search_view.ko_members_input.setText("iHN637")
    w.search_view.growth_member_input.setText("iHN637")
    w.search_view.targets_input.setText("")
    assert w.run_search_fixture() == ""
    assert w.run_gene_ko_search() == ""
    assert w.run_abundance_impact() == ""
    runner.shutdown()


# --------------------------------------------------------------------------------------
# Provenance — a GUI-only run must be able to tell the user where its manifest went
# --------------------------------------------------------------------------------------


def test_search_export_refuses_an_invalidated_run(monkeypatch, tmp_path):
    """V-1 (P1): the invalidation fix introduced its own F4-class defect on the Search tab.

    After an input edit clears the table and prints "Inputs changed — previous result
    cleared", Export Figure still resolved through the window-level `current_search_dir`
    fallback and happily wrote the discarded run's SVG, reporting success. The Host tab
    already refuses in the same state; Search must too.
    """
    from PySide6.QtWidgets import QFileDialog

    _app()
    w = build_main_window()
    run_dir = tmp_path / "search"
    run_dir.mkdir()
    (run_dir / "search_plot.svg").write_text("<svg><!--DISCARDED-RUN--></svg>")
    target = tmp_path / "export.svg"
    w.current_search_dir = run_dir
    w.search_view.load_summary({
        "strategy": "exhaustive",
        "top_ranked": [{"members": ["A", "B"], "score": 7.25, "target_flux": 7.25,
                        "community_growth": 0.42, "status": "optimal"}],
    }, run_dir=run_dir)
    assert w.search_view.table.rowCount() == 1

    w.search_view.targets_input.setText("succ")           # invalidates the displayed result
    assert w.search_view.table.rowCount() == 0
    assert w.search_view.current_run_dir is None

    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), "SVG (*.svg)")
    )
    w._export_search_figure()
    assert not target.exists(), "must not export a run the user was told was discarded"
    assert "No search result is loaded" in w.search_view.status.text()


def test_search_result_from_a_superseded_request_is_labelled(monkeypatch, tmp_path):
    """codex race 1 (P0 completeness): invalidation only covers the *idle* case. A search
    that is already running keeps its result, and on completion the table was repopulated
    with numbers for the OLD inputs sitting under the NEW ones with no indication."""
    import cmig.cli.main

    release = threading.Event()

    def fake_main(argv):
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "search_summary.json").write_text(json.dumps({
            "strategy": "exhaustive", "target": "but",
            "top_ranked": [{"members": ["A", "B"], "score": 7.25, "target_flux": 7.25,
                            "community_growth": 0.42, "status": "optimal"}],
            "warnings": [],
        }))
        release.wait(timeout=20)
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    w.search_view.model_dir_input.setText(str(tmp_path))
    w.search_view.targets_input.setText("but")
    jid = w.run_search_fixture()
    # the researcher retargets while the first search is still solving
    w.search_view.targets_input.setText("succ")
    w.search_view.min_size_spin.setValue(3)
    release.set()
    _wait(runner, jid)
    w._poll_completed_jobs()
    assert w.search_view.table.rowCount() == 1, "a real run must not be silently discarded"
    status = w.search_view.status.text()
    assert "but" in status and "succ" in status, (
        f"the status must name the request the numbers belong to; got {status!r}"
    )
    assert "changed" in status.lower()
    runner.shutdown()


def test_sandbox_preview_names_the_bound_it_was_computed_for(monkeypatch):
    """codex race 2 (P1): making the sandbox asynchronous created an input/result race —
    the delta for the OLD bound landed under a NEWLY typed bound with no indication."""
    import cmig.service
    from cmig.core.delta import DeltaResult

    release = threading.Event()

    class SlowEngineService:
        def sandbox_fixture(self, *, reaction_id, lower, upper, commit, out_dir):
            release.wait(timeout=20)
            return SimpleNamespace(delta=DeltaResult([], [], [], 0.0), run_hash=None)

    monkeypatch.setattr(cmig.service, "EngineService", SlowEngineService)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    w.sandbox_view.add_bound("EX_ac_e", -1.0, 1000.0)
    jid = w._run_sandbox(commit=False)
    assert jid
    # the researcher edits the bound while the solve is in flight
    w.sandbox_view.bound_table.item(0, 1).setText("-8.0")
    release.set()
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and w._sandbox_jobs:
        w._poll_completed_jobs()
        time.sleep(0.01)
    status = w.sandbox_view.status.text()
    assert "EX_ac_e" in status, f"the preview must name its own bound; got {status!r}"
    assert "changed" in status.lower(), (
        f"a bound edited during the solve must be flagged; got {status!r}"
    )
    runner.shutdown()


def test_sandbox_done_with_no_result_releases_the_buttons(monkeypatch):
    """Verifier nit: a DONE job whose result is None matched neither poll branch, so the
    job stayed in `_sandbox_jobs` forever and both buttons stayed disabled."""
    import cmig.service

    class NullEngineService:
        def sandbox_fixture(self, **kwargs):
            return None

    monkeypatch.setattr(cmig.service, "EngineService", NullEngineService)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    w.sandbox_view.add_bound("EX_ac_e", -1.0, 1000.0)
    jid = w._run_sandbox(commit=False)
    _wait(runner, jid)
    w._poll_completed_jobs()
    assert not w._sandbox_jobs
    assert w.sandbox_view.preview_btn.isEnabled()
    assert w.sandbox_view.commit_btn.isEnabled()
    assert "no result" in w.sandbox_view.status.text().lower()
    runner.shutdown()


def test_release_payload_keeps_result_callable(tmp_path):
    """V-2 (P2): `release_payload` popped `_futures`, so a later `JobRunner.result(jid)`
    raised a bare KeyError — a public-API break for anything holding the job id."""
    runner = JobRunner(max_workers=1)
    jid = runner.submit("calc", lambda ctx: {"big": "payload"})
    assert runner.result(jid, timeout=5) == {"big": "payload"}
    runner.release_payload(jid)
    assert runner.result(jid, timeout=5) is None      # released, but no KeyError
    assert runner.poll(jid).status is JobStatus.DONE
    runner.shutdown()


def test_read_only_guarantee_holds_at_item_level():
    """Verifier nit: `setEditTriggers(NoEditTriggers)` blocks every *user* edit path, but
    `QAbstractItemView.edit(index)` passes AllEditTriggers and bypasses it, and the items
    still carry ItemIsEditable.

    Assert the full guarantee on every *populated* read-only table: no edit trigger, no
    editor obtainable even programmatically, and both the item and the model reporting the
    cell as non-editable. Each table is populated first — an empty table proves nothing.
    """
    from PySide6.QtCore import Qt

    from cmig.core.delta import DeltaResult, MetaboliteDelta

    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    w._set_advanced_tabs_visible(True)
    w.search_view.load_summary({"strategy": "x", "top_ranked": [
        {"members": ["A"], "score": 1.0, "target_flux": 12.11,
         "community_growth": 0.3, "status": "optimal"}]})
    w.profile_view.load_profile([{"metabolite": "ac", "net_flux": 5.153, "label": "secretion"}])
    w.dynamics_view.load_dfba_summary(
        {"status": "completed", "final_t": 1.0, "final_biomass": 2.5,
         "final_concentrations": {"EX_glc__D_e": 3.0}, "warnings": []}, run_dir=Path("/tmp"))
    w.sweep_view.load_results(
        [SimpleNamespace(condition_id="c0", value=1.0, status="ok", cache_hit=False)])
    w.host_view.load_host_result(SimpleNamespace(
        viable=True, biomass=1.2, status="optimal",
        interface_fluxes=[SimpleNamespace(
            interface="lumen", metabolite="ac", flux=1.0, label="uptake")]))
    w.host_view.load_impact(SimpleNamespace(microbe_to_host={"ac": 1.0}))
    delta = DeltaResult([MetaboliteDelta("ac", 1.0, 2.0, 1.0)], [], [], 0.0)
    w.sandbox_view.delta_view.load_delta(delta)
    w.scenario_compare.delta_view.load_delta(delta)
    w.model_manager.load_summary(SimpleNamespace(
        model_id="m", source_format="sbml", n_reactions=1, n_metabolites=1, n_genes=1,
        exchanges=["EX_ac_e"], biomass_reactions=["BIO"], as_dict=lambda: {}))
    w.bridge.track(runner.submit("noop", lambda ctx: None))
    w.bridge.refresh()

    read_only = {
        "search": w.search_view.table, "profile": w.profile_view.table,
        "dynamics": w.dynamics_view.table, "sweep": w.sweep_view.table,
        "host_iface": w.host_view.iface_table, "host_cross": w.host_view.cross_table,
        "sandbox_delta": w.sandbox_view.delta_view,
        "compare_delta": w.scenario_compare.delta_view,
        "model_exchanges": w.model_manager.exchange_table, "jobs": w.jobs_panel,
    }
    problems: list[str] = []
    for name, table in read_only.items():
        if table.rowCount() == 0:
            problems.append(f"{name}: not populated, guarantee unverified")
            continue
        index = table.model().index(0, 0)
        if table.editTriggers() != QAbstractItemView.EditTrigger.NoEditTriggers:
            problems.append(f"{name}: edit triggers enabled")
        if table.edit(index, QAbstractItemView.EditTrigger.AllEditTriggers, None) is not False:
            problems.append(f"{name}: programmatic edit produced an editor")
        if table.item(0, 0).flags() & Qt.ItemFlag.ItemIsEditable:
            problems.append(f"{name}: item still carries ItemIsEditable")
        if table.model().flags(index) & Qt.ItemFlag.ItemIsEditable:
            problems.append(f"{name}: model reports the cell as editable")
    assert problems == []

    # input tables must remain genuinely editable
    for name, table in {"medium": w.medium_editor.table,
                        "bounds": w.sandbox_view.bound_table,
                        "community": w.community_builder.table}.items():
        assert table.editTriggers() != QAbstractItemView.EditTrigger.NoEditTriggers, name
    runner.shutdown()


def test_cancel_after_artifacts_are_written_reports_a_complete_run(monkeypatch, tmp_path):
    """P1/P2: a cancel arriving after `main(argv)` wrote manifest.json made JobRunner drop
    the outcome and record CANCELLED — a durable contradiction with the run on disk."""
    import cmig.cli.main

    started = threading.Event()

    def fake_main(argv):
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "search_summary.json").write_text(json.dumps({
            "strategy": "exhaustive", "target": "but", "top_ranked": [], "warnings": [],
        }))
        (out / "manifest.json").write_text(json.dumps({"run_hash": "deadbeefcafe"}))
        started.set()
        time.sleep(0.3)  # the solver is still inside its non-interruptible call
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    w.search_view.model_dir_input.setText(str(tmp_path))
    w.search_view.targets_input.setText("but")
    jid = w.run_search_fixture()
    assert started.wait(timeout=10)
    runner.cancel(jid)
    _wait(runner, jid)
    assert runner.poll(jid).status is JobStatus.DONE
    w._poll_completed_jobs()
    assert w.current_search_dir is not None
    assert (w.current_search_dir / "manifest.json").exists()
    runner.shutdown()


def test_jobs_panel_marks_a_cancel_request_as_cancelling():
    """P1: the panel showed plain `running` after Cancel, so the request looked like a no-op."""
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    started = threading.Event()

    def wait_until_cancelled(ctx):
        started.set()
        while not ctx.cancelled:
            time.sleep(0.01)
        ctx.raise_if_cancelled()

    jid = w.submit_job("wait", wait_until_cancelled)
    assert started.wait(timeout=5)
    w.bridge.refresh()
    w.jobs_panel.selectRow(0)
    w._cancel_selected_job()
    assert "cancelling" in w.jobs_panel.item(0, 2).text()
    assert "cannot be interrupted mid-solve" in w.statusBar().currentMessage()
    _wait(runner, jid)
    runner.shutdown()


def test_jobs_panel_does_not_fake_progress():
    """P2: every job reported (0,1) then (1,1); the panel showed `0/1` for the whole run,
    implying measured progress that does not exist."""
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    jid = w.submit_job("calc", lambda ctx: ctx.report_progress(0, 1))
    runner.result(jid, timeout=5)
    w.bridge.refresh()
    assert w.jobs_panel.item(0, 3).text() == "—"
    runner.shutdown()


def test_close_event_stops_timers_and_shuts_down_the_pool():
    """P1: closing the window left non-daemon executor threads and both QTimers running,
    so the process stayed alive and invisible."""
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    w.close()
    assert not w._completion_timer.isActive()
    assert not w.bridge._timer.isActive()
    with pytest.raises(RuntimeError):
        runner.submit("after-shutdown", lambda ctx: None)


def test_search_run_directory_is_reported_to_the_user(monkeypatch, tmp_path):
    """P1: artifacts + manifest.json landed in an unnamed OS temp dir never shown anywhere."""
    import cmig.cli.main

    def fake_main(argv):
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "search_summary.json").write_text(json.dumps({
            "strategy": "exhaustive", "target": "but", "top_ranked": [], "warnings": [],
        }))
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    w.search_view.model_dir_input.setText(str(tmp_path))
    w.search_view.targets_input.setText("but")
    jid = w.run_search_fixture()
    runner.result(jid, timeout=10)
    w._poll_completed_jobs()
    out_dir = w.current_search_dir
    assert out_dir is not None
    assert str(out_dir) in w.statusBar().currentMessage()
    runs_root = w.explorer.topLevelItem(2)
    labels = [runs_root.child(i).text(0) for i in range(runs_root.childCount())]
    assert out_dir.name in labels
    runner.shutdown()
