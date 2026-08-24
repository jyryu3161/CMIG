"""Round-8 U5 acceptance: real sweep, flux heatmap, and delta overlays."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets")

import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

import cmig.gui.app as app_module  # noqa: E402
import cmig.gui.graph_view as graph_view_module  # noqa: E402
from cmig.core.delta import DeltaResult, MetaboliteDelta  # noqa: E402
from cmig.core.sweep import SWEEP_SCHEMA  # noqa: E402
from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.views import ExternalProfileView, FluxHeatmap, SweepView  # noqa: E402
from cmig.service import JobRunner  # noqa: E402

_QT_APP: QApplication | None = None


def _app() -> QApplication:
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


@pytest.fixture(autouse=True)
def _deterministic_qt_teardown():
    """Destroy every window inside the test, not at interpreter exit.

    This module builds several CmigMainWindow instances; leaving their C++ side
    to be reaped during Python shutdown segfaults the otherwise-green run
    (exit 139) on macOS. Closing and draining deleteLater inside the session
    keeps teardown deterministic.
    """
    yield
    app = QApplication.instance()
    if app is not None:
        for widget in app.topLevelWidgets():
            widget.close()
            widget.deleteLater()
        app.processEvents()


def _stub_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep these QWidget contracts independent of QtWebEngine/Chromium."""

    class GraphStub(QWidget):
        def set_bundle(self, _bundle, gate=None):
            return None

        def set_payload(self, _payload):
            return None

        def clear(self):
            return None

    monkeypatch.setattr(app_module, "InteractionGraphView", GraphStub)
    monkeypatch.setattr(graph_view_module, "InteractionGraphView", GraphStub)


def _write_sweep(path: Path, *, failed: bool = False) -> None:
    status = "failed" if failed else "ok"
    value = None if failed else 0.42
    diagnostic = '{"code":"infeasible"}' if failed else None
    table = pa.Table.from_pylist(
        [
            {
                "schema_version": "1.0",
                "condition_id": "cond-0000",
                "axis_medium_variant": "western.csv",
                "axis_abundance": "abundance.json",
                "axis_member_set": "A+B",
                "axis_bounds": "bounds.json",
                "axis_tradeoff_f": 0.3,
                "axis_solver": "gurobi",
                "metric": "growth",
                "value": value,
                "run_hash": "hash",
                "status": status,
                "diagnostic": diagnostic,
                "cache_hit": False,
            }
        ],
        schema=SWEEP_SCHEMA,
    )
    path.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path / "sweep.parquet")
    (path / "sweep_summary.json").write_text(
        json.dumps(
            {
                "status": status,
                "n_runs": 1,
                "warnings": ["cond-0000 did not solve"] if failed else [],
            }
        )
    )


def test_sweep_view_exposes_real_axes_and_fixture_is_opt_in():
    _app()
    view = SweepView()
    assert view.fixture_check.isChecked() is False
    assert view.taxonomy_input.placeholderText() == "Taxonomy CSV"
    assert view.mediums_input is not None
    assert view.abundance_variants_input is not None
    assert view.member_sets_input is not None
    assert view.bounds_variants_input is not None
    assert view.tradeoff_fs_input.text() == "0.3,0.5"
    assert view.solvers_input.text() == "gurobi"
    view.runner.shutdown()


def test_real_sweep_launches_cli_with_every_axis(monkeypatch, tmp_path):
    import cmig.cli.main

    _app()
    _stub_graph(monkeypatch)
    seen: dict[str, list[str]] = {}

    def fake_main(argv):
        seen["argv"] = list(argv)
        out = Path(argv[argv.index("--out") + 1])
        _write_sweep(out)
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    taxonomy = tmp_path / "taxonomy.csv"
    taxonomy.write_text("id,file\nA,A.xml\n")
    runner = JobRunner(max_workers=1)
    window = build_main_window(runner=runner)
    view = window.sweep_view
    view.taxonomy_input.setText(str(taxonomy))
    view.mediums_input.setText("western.csv,eastern.json")
    view.abundance_variants_input.setText("abundance.json")
    view.member_sets_input.setText("A+B;A+C")
    view.bounds_variants_input.setText("bounds.json")
    view.tradeoff_fs_input.setText("0.3,0.7")
    view.solvers_input.setText("gurobi,osqp")
    view.assume_bigg_check.setChecked(True)
    view.fva_check.setChecked(True)
    view.fva_metabolites_input.setText("ac,but")
    view.exact_medium_check.setChecked(True)

    view.run_btn.click()
    assert len(window._sweep_jobs) == 1
    jid = next(iter(window._sweep_jobs))
    runner.result(jid, timeout=5)
    window._poll_completed_jobs()

    argv = seen["argv"]
    assert argv[0] == "sweep"
    expected = {
        "--taxonomy": str(taxonomy),
        "--mediums": "western.csv,eastern.json",
        "--abundance-variants": "abundance.json",
        "--member-sets": "A+B;A+C",
        "--bounds-variants": "bounds.json",
        "--tradeoff-fs": "0.3,0.7",
        "--solvers": "gurobi,osqp",
        "--fva-metabolites": "ac,but",
    }
    for flag, value in expected.items():
        assert argv[argv.index(flag) + 1] == value
    assert "--assume-bigg-namespace" in argv
    assert "--fva" in argv
    assert "--exact-medium" in argv
    assert window.sweep_view.table.rowCount() == 1
    assert window.sweep_view.table.item(0, 4).text() == "western.csv"
    assert window.sweep_view.table.item(0, 9).text() == "gurobi"
    assert window.sweep_view.run_btn.isEnabled()
    runner.shutdown()


def test_model_folder_source_is_converted_to_taxonomy_in_worker(monkeypatch, tmp_path):
    import pandas as pd

    import cmig.cli.main
    import cmig.core.model_pool

    _app()
    _stub_graph(monkeypatch)
    seen: dict[str, list[str]] = {}

    monkeypatch.setattr(
        cmig.core.model_pool,
        "taxonomy_from_model_dir",
        lambda _path, recursive=False: pd.DataFrame(
            [{"id": "A", "file": str(tmp_path / "A.xml"), "abundance": 1.0}]
        ),
    )

    def fake_main(argv):
        seen["argv"] = list(argv)
        taxonomy = Path(argv[argv.index("--taxonomy") + 1])
        assert taxonomy.read_text().startswith("id,file,abundance")
        _write_sweep(Path(argv[argv.index("--out") + 1]))
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    runner = JobRunner(max_workers=1)
    window = build_main_window(runner=runner)
    window.sweep_view.model_dir_input.setText(str(tmp_path))
    window.sweep_view.assume_bigg_check.setChecked(True)
    jid = window.run_sweep()
    runner.result(jid, timeout=5)
    window._poll_completed_jobs()
    assert seen["argv"][0] == "sweep"
    runner.shutdown()


def test_failed_real_sweep_keeps_failed_job_and_displays_recorded_diagnostic(monkeypatch, tmp_path):
    import cmig.cli.main

    _app()
    _stub_graph(monkeypatch)

    def fake_main(argv):
        _write_sweep(Path(argv[argv.index("--out") + 1]), failed=True)
        return 3

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    taxonomy = tmp_path / "taxonomy.csv"
    taxonomy.write_text("id,file\nA,A.xml\n")
    runner = JobRunner(max_workers=1)
    window = build_main_window(runner=runner)
    window.sweep_view.taxonomy_input.setText(str(taxonomy))
    window.sweep_view.assume_bigg_check.setChecked(True)
    jid = window.run_sweep()
    with pytest.raises(RuntimeError, match="rc=3"):
        runner.result(jid, timeout=5)
    window._poll_completed_jobs()
    assert window.sweep_view.table.rowCount() == 1
    assert window.sweep_view.table.item(0, 2).text() == "failed"
    assert "infeasible" in window.sweep_view.table.item(0, 10).text()
    assert "Displaying 1 recorded" in window.sweep_view.status.text()
    runner.shutdown()


def test_heatmap_keeps_missing_blank_and_measured_zero_distinct():
    app = _app()
    heatmap = FluxHeatmap()
    heatmap.resize(640, 280)
    heatmap.set_profile_rows(
        [
            {"metabolite": "missing", "net_flux": None},
            {"metabolite": "zero", "net_flux": 0.0},
            {"metabolite": "secreted", "net_flux": 2.0},
            {"metabolite": "taken_up", "net_flux": -3.0},
        ]
    )
    app.processEvents()
    flattened = [value for row in heatmap.values for value in row]
    assert None in flattened
    assert 0.0 in flattened
    assert heatmap.missing_count == 1
    assert not heatmap.grab().isNull()


def test_member_heatmap_uses_sparse_blank_cells_not_zero_fill():
    _app()
    view = ExternalProfileView()
    view.load_profile(
        [{"metabolite": "ac", "net_flux": 2.0}, {"metabolite": "glc", "net_flux": -1.0}],
        member_contributions=[
            {"metabolite": "ac", "contributions": [{"member": "A", "value": 2.0}]},
            {"metabolite": "glc", "contributions": [{"member": "B", "value": -1.0}]},
        ],
    )
    assert view.heatmap.columns == ["A", "B"]
    assert view.heatmap.missing_count == 2
    assert sum(value is None for row in view.heatmap.values for value in row) == 2


def test_delta_overlay_labels_baseline_variant_and_restores_member_view():
    _app()
    view = ExternalProfileView()
    view.load_profile(
        [{"metabolite": "ac", "net_flux": 1.0}],
        member_contributions=[
            {"metabolite": "ac", "contributions": [{"member": "A", "value": 1.0}]}
        ],
    )
    delta = DeltaResult([MetaboliteDelta("ac", 1.0, -2.0, -3.0)])
    view.show_delta_overlay(delta, baseline_label="Run A", variant_label="Run B")
    assert view.net_chart.delta_rows == [
        {"metabolite": "ac", "baseline": 1.0, "variant": -2.0}
    ]
    assert view.heatmap.columns == ["Run A", "Run B"]
    assert view.member_chart.rows == []
    assert "Run A" in view.delta_note.text() and "Run B" in view.delta_note.text()
    assert view.clear_delta_btn.isVisible() is False  # parent view is not shown offscreen
    assert not view.clear_delta_btn.isHidden()

    view.clear_delta_overlay()
    assert view.net_chart.delta_rows == []
    assert view.member_chart.rows
    assert view.heatmap.columns == ["A"]
    assert view.clear_delta_btn.isHidden()


def test_sandbox_result_activates_profile_overlay(monkeypatch):
    import cmig.service

    _app()
    _stub_graph(monkeypatch)
    delta = DeltaResult([MetaboliteDelta("ac", 1.0, 2.0, 1.0)])

    class FakeEngineService:
        def sandbox_fixture(self, **_kwargs):
            return SimpleNamespace(delta=delta, run_hash=None)

    monkeypatch.setattr(cmig.service, "EngineService", FakeEngineService)
    runner = JobRunner(max_workers=1)
    window = build_main_window(runner=runner)
    window.sandbox_view.add_bound("EX_ac_e", -1.0, 1000.0)
    jid = window._run_sandbox(commit=False)
    runner.result(jid, timeout=5)
    window._poll_completed_jobs()
    assert window.profile_view.net_chart.delta_rows
    assert window.profile_view.heatmap.columns == ["Fixture baseline", "Sandbox preview"]
    assert "External Profile" in window.sandbox_view.status.text()
    runner.shutdown()


def test_scenario_compare_activates_profile_overlay(monkeypatch, tmp_path):
    _app()
    _stub_graph(monkeypatch)
    run_a, run_b = tmp_path / "run_a", tmp_path / "run_b"
    run_a.mkdir()
    run_b.mkdir()
    (run_a / "profile.parquet").touch()
    (run_b / "profile.parquet").touch()

    def solve_like(path: Path):
        value = 1.0 if path == run_a else -2.0
        return SimpleNamespace(
            external_exchange={"ac": value},
            members=["A"],
            status="optimal",
            objective=abs(value),
        )

    monkeypatch.setattr(app_module, "_solve_result_like_from_run_dir", solve_like)
    window = build_main_window()
    window.scenario_compare.run_a_input.setText(str(run_a))
    window.scenario_compare.run_b_input.setText(str(run_b))
    window.run_scenario_compare()
    assert window.profile_view.net_chart.delta_active is True
    assert window.profile_view.heatmap.columns == ["Baseline: run_a", "Variant: run_b"]
    assert "External Profile" in window.scenario_compare.status.text()
    window.runner.shutdown()


def test_new_surfaces_have_real_korean_catalogue(monkeypatch):
    _app()
    _stub_graph(monkeypatch)
    window = build_main_window(lang="ko")
    assert window.sweep_view.title.text() == "매개변수 스윕"
    assert window.sweep_view.run_btn.text() == "스윕 실행"
    assert window.profile_view.chart_tabs.tabText(1) == "히트맵"
    assert window.profile_view.clear_delta_btn.text() == "비교 오버레이 지우기"
    window.runner.shutdown()
