"""Focused regressions for the 2026-09-25 GUI workflow audit."""

from __future__ import annotations

import json
import runpy
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.core.workflow_manifest import artifact_result_digest  # noqa: E402
from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.builder import SearchView  # noqa: E402
from cmig.service import JobRunner, JobStatus  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _small_dfba_run(path: Path) -> None:
    path.mkdir()
    (path / "dfba_summary.json").write_text(json.dumps({
        "status": "completed", "final_t": 1.0, "final_biomass": 0.2,
        "final_concentrations": {"glc": 1.0}, "warnings": [],
    }))
    digest = artifact_result_digest(path, "dfba", ["dfba_summary.json"])
    (path / "manifest.json").write_text(json.dumps({
        "manifest_schema_version": "1.2", "manifest_scope": "workflow",
        "workflow_kind": "dfba", "artifacts": ["dfba_summary.json"],
        "result_digest": digest, "status": "ok",
    }))


def _search_run(path: Path, summary: dict[str, object]) -> None:
    path.mkdir()
    (path / "search_summary.json").write_text(json.dumps(summary))
    (path / "manifest.json").write_text(json.dumps({
        "manifest_scope": "workflow", "manifest_schema_version": "1.2",
        "workflow_kind": "search", "artifacts": ["search_summary.json"],
        "result_digest": artifact_result_digest(path, "search", ["search_summary.json"]),
    }))


def test_adjacent_workflows_forward_only_applicable_frozen_settings(monkeypatch, tmp_path):
    import cmig.cli.main

    _app()
    seen: list[list[str]] = []

    def fake_main(argv):
        seen.append(list(argv))
        out = Path(argv[argv.index("--out") + 1])
        filename = {
            "gene-ko-search": "gene_ko_summary.json",
            "strain-growth": "strain_growth_summary.json",
            "abundance-impact": "abundance_impact_summary.json",
        }[argv[0]]
        (out / filename).write_text(json.dumps({"target": "ac", "top_ranked": [],
                                                "warnings": []}))
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    runner = JobRunner(max_workers=1)
    release = threading.Event()
    runner.submit("block", lambda ctx: release.wait(10))
    window = build_main_window(runner=runner)
    view = window.search_view
    view.model_dir_input.setText(str(tmp_path))
    view.medium_input.setText(str(tmp_path / "defined-medium.csv"))
    view.targets_input.setText("ac")
    view.direction_combo.setCurrentText("min_uptake")
    view.growth_fraction_spin.setValue(0.75)
    view.cooperative_tradeoff_spin.setValue(0.65)
    growth_request = view.request_fields("strain_growth")
    view.direction_combo.setCurrentText("max_secretion")
    view.growth_fraction_spin.setValue(0.6)
    assert view.superseded_note(growth_request, "strain_growth") == ""
    view.direction_combo.setCurrentText("min_uptake")
    view.growth_fraction_spin.setValue(0.75)
    view.ko_members_input.setText("member_a")
    view.growth_member_input.setText("member_a")
    jobs = [window.run_gene_ko_search(), window.run_strain_growth_report(),
            window.run_abundance_impact()]
    view.medium_input.setText("changed.csv")
    view.direction_combo.setCurrentText("max_secretion")
    view.cooperative_tradeoff_spin.setValue(0.8)
    release.set()
    for job in jobs:
        runner.result(job, timeout=20)
    window._poll_completed_jobs()
    assert len(seen) == 3
    for argv in seen:
        assert argv[argv.index("--medium") + 1] == str(tmp_path / "defined-medium.csv")
        assert "--exact-medium" in argv
    ko, growth, ratio = seen
    assert ko[ko.index("--direction") + 1] == "min_uptake"
    assert ko[ko.index("--growth-fraction") + 1] == "0.75"
    assert "--direction" not in growth and "--direction" not in ratio
    assert "--growth-fraction" not in growth and "--growth-fraction" not in ratio
    assert growth[growth.index("--tradeoff-f") + 1] == "0.65"
    assert ratio[ratio.index("--tradeoff-f") + 1] == "0.65"
    assert growth[growth.index("--single-medium") + 1] == "community"
    assert "cooperative tradeoff f=0.65" in view.details.toPlainText()
    assert "superseded request" in view.details.toPlainText()
    window.close()


def test_ratio_exact_medium_reaches_existing_cli_context(monkeypatch, tmp_path):
    import cmig.cli.main
    from cmig.core.medium_spec import requested_medium_application_mode

    modes: list[str | None] = []

    def handler(args):
        modes.append(requested_medium_application_mode(has_custom_medium=bool(args.medium)))
        return 0

    monkeypatch.setattr(cmig.cli.main, "_cmd_abundance_impact", handler)
    args = ["abundance-impact", "--model-dir", str(tmp_path), "--member", "member_a",
            "--medium", str(tmp_path / "medium.csv"), "--exact-medium", "--out",
            str(tmp_path / "out")]
    assert cmig.cli.main.main(args) == 0
    assert modes == ["exact_boundary_isolation"]


def test_full_window_fits_with_long_warnings_and_hidden_host(tmp_path):
    app = _app()
    for lang in ("en", "ko"):
        window = build_main_window(lang=lang)
        summary = {"strategy": "pareto", "status": "degraded", "top_ranked": [],
                   "warnings": ["long warning " + "x" * 500 for _ in range(4)],
                   "n_candidates_failed": 3, "n_pareto_attempts": 10,
                   "n_pareto_resolved_attempts": 8, "n_pareto_failed_attempts": 2,
                   "candidate_sampling_status": {"A+B": "partial"}}
        window.search_view.load_summary(summary, run_dir=tmp_path / ("x" * 90))
        for size in ((1280, 800), (1500, 950)):
            window.resize(*size)
            window.show()
            app.processEvents()
            assert (window.width(), window.height()) == size
            assert "Warning 4:" in window.search_view.details.toPlainText()
            assert "n_pareto_failed_attempts: 2" in window.search_view.details.toPlainText()
            assert window.host_view.scroll_area is not None
        window.close()


def test_missing_figure_clears_preview_and_disables_export(tmp_path):
    _app()
    view = SearchView()
    assert view.figure_mode_combo.count() == 0
    for filename in ("search_plot.svg", "search_scatter.svg"):
        (tmp_path / filename).write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50">'
            '<rect width="100" height="50" fill="red"/></svg>'
        )
    view.load_summary({"strategy": "exhaustive", "top_ranked": []}, run_dir=tmp_path)
    assert [view.figure_mode_combo.itemText(i)
            for i in range(view.figure_mode_combo.count())] == ["Ranking", "Scatter"]
    assert view.export_figure_btn.isEnabled()
    (tmp_path / "search_scatter.svg").unlink()
    view.figure_mode_combo.setCurrentText("Scatter")
    assert view.figure_stack.currentWidget() is view.figure_placeholder
    assert not view.export_figure_btn.isEnabled()
    assert "missing" in view.figure_placeholder.text()
    view.invalidate_results()
    assert view.figure_mode_combo.count() == 0


@pytest.mark.parametrize("width,height", [(400, 100), (100, 400)])
def test_svg_preview_preserves_drawn_content_aspect(tmp_path, width, height):
    app = _app()
    view = SearchView()
    (tmp_path / "search_plot.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" fill="red"/></svg>'
    )
    view.resize(800, 700)
    view.show()
    view.load_summary({"strategy": "exhaustive", "top_ranked": []}, run_dir=tmp_path)
    app.processEvents()
    assert hasattr(view.figure_view, "renderer")
    image = view.figure_view.grab().toImage()
    points = [
        (x, y) for y in range(image.height()) for x in range(image.width())
        if (lambda c: c.red() > 200 and c.green() < 100 and c.blue() < 100)(
            image.pixelColor(x, y)
        )
    ]
    assert points
    drawn_width = max(x for x, _ in points) - min(x for x, _ in points) + 1
    drawn_height = max(y for _, y in points) - min(y for _, y in points) + 1
    assert abs(drawn_width / drawn_height - width / height) < 0.15
    view.close()


def test_integrity_and_malformed_manifest_are_distinct(tmp_path):
    _app()
    window = build_main_window()
    run = tmp_path / "run"
    _small_dfba_run(run)
    assert window.load_dfba_dir(run)
    assert window.integrity_label.text() == "Integrity: verified"
    (run / "dfba_summary.json").write_text(json.dumps({
        "status": "completed", "final_t": 2.0, "final_biomass": 0.2,
        "final_concentrations": {}, "warnings": [],
    }))
    assert window.load_dfba_dir(run)
    assert window.integrity_label.text() == "Integrity: mismatch"
    assert "dfba_summary.json" in window._integrity_detail
    modern_without_digest = json.loads((run / "manifest.json").read_text())
    modern_without_digest.pop("result_digest")
    (run / "manifest.json").write_text(json.dumps(modern_without_digest))
    assert window.load_dfba_dir(run) is False
    assert window.integrity_label.text() == "Integrity: invalid/unreadable"
    (run / "manifest.json").write_text("null")
    assert window.load_dfba_dir(run) is False
    assert window.integrity_label.text() == "Integrity: invalid/unreadable"
    assert window.dynamics_view.table.rowCount() == 0
    (run / "manifest.json").write_text("[]")
    assert window.load_dfba_dir(run) is False
    assert window.integrity_label.text() == "Integrity: invalid/unreadable"
    (run / "manifest.json").unlink()
    assert window.load_dfba_dir(run)
    assert window.integrity_label.text() == "Integrity: not_recorded"
    (run / "dfba_summary.json").write_text(json.dumps({
        "status": "failed", "final_t": None, "final_biomass": None,
        "final_concentrations": {"glc": None}, "warnings": [],
    }))
    assert window.load_dfba_dir(run)
    assert "biomass=unknown" in window.dynamics_view.table.item(0, 3).text()
    (run / "dfba_summary.json").write_text(json.dumps({"status": "ok"}))
    assert window.load_dfba_dir(run) is False
    assert window.dynamics_view.table.rowCount() == 0
    window.close()


def test_missing_declared_artifact_is_mismatch_and_host_null_is_unknown(tmp_path):
    from types import SimpleNamespace

    from cmig.gui.host_view import HostImpactView, host_microbe_network_payload

    _app()
    run = tmp_path / "run"
    _small_dfba_run(run)
    (run / "extra.csv").write_text("recorded\n")
    digest = artifact_result_digest(run, "dfba", ["dfba_summary.json", "extra.csv"])
    manifest = json.loads((run / "manifest.json").read_text())
    manifest["artifacts"] = ["dfba_summary.json", "extra.csv"]
    manifest["result_digest"] = digest
    (run / "manifest.json").write_text(json.dumps(manifest))
    (run / "extra.csv").unlink()
    window = build_main_window()
    assert window.load_dfba_dir(run)
    assert window.integrity_label.text() == "Integrity: mismatch"
    assert "missing=extra.csv" in window._integrity_detail
    window.close()

    host = HostImpactView()
    host.load_host_result(SimpleNamespace(viable=True, biomass=None, status="degraded",
                                          interface_fluxes=[]))
    host.load_impact(SimpleNamespace(microbe_to_host={"ac": None}))
    assert "unknown" in host.viability_label.text()
    assert host.cross_table.item(0, 1).text() == "unknown"
    graph = host_microbe_network_payload({
        "host": {"lumen_uptake": {"ac": None}}, "microbe_to_host": {"ac": None},
        "microbial_secretion": {"ac": 1.0}, "unused_secretion": {},
    })
    assert not any(edge["data"].get("etype") == "cross_feeding"
                   for edge in graph["elements"])


def test_spatial_and_host_direct_readback_report_integrity(tmp_path):
    _app()
    window = build_main_window()
    spatial = tmp_path / "spatial"
    spatial.mkdir()
    (spatial / "spatial_summary.json").write_text(json.dumps({
        "status": "ok", "final_t": 1, "final_min": 0, "final_max": 1,
        "warnings": [],
    }))
    assert window.load_spatial_dir(spatial)
    assert window.integrity_label.text() == "Integrity: not_recorded"
    digest = artifact_result_digest(spatial, "spatial", ["spatial_summary.json"])
    (spatial / "manifest.json").write_text(json.dumps({
        "manifest_scope": "workflow", "manifest_schema_version": "1.2",
        "workflow_kind": "spatial", "artifacts": ["spatial_summary.json"],
        "result_digest": digest,
    }))
    assert window.load_spatial_dir(spatial)
    assert window.integrity_label.text() == "Integrity: verified"
    (spatial / "spatial_summary.json").write_text(json.dumps({
        "status": "degraded", "final_t": 1, "final_min": 0, "final_max": 1,
        "warnings": ["changed after recording"],
    }))
    assert window.load_spatial_dir(spatial)
    assert window.integrity_label.text() == "Integrity: mismatch"

    host = tmp_path / "host"
    host.mkdir()
    host_summary = host / "host_microbe_bigg_summary.json"
    host_summary.write_text(json.dumps({
        "host": {"viable": True, "status": "degraded", "objective_value": None,
                 "lumen_uptake": {"ac": None}},
        "microbe_to_host": {"ac": None}, "microbe_to_host_ranges": {"ac": [0, 1]},
        "microbial_secretion": {"ac": 1.0}, "warnings": ["transfer ambiguous"],
    }))
    assert window.load_host_microbe_bigg_dir(host)
    assert window.integrity_label.text() == "Integrity: not_recorded"
    assert "unknown [0, 1]" == window.host_view.cross_table.item(0, 1).text()
    digest = artifact_result_digest(host, "host_microbe_bigg", [host_summary.name])
    (host / "manifest.json").write_text(json.dumps({
        "manifest_scope": "workflow", "manifest_schema_version": "1.2",
        "workflow_kind": "host_microbe_bigg", "artifacts": [host_summary.name],
        "result_digest": digest,
    }))
    assert window.load_host_microbe_bigg_dir(host)
    assert window.integrity_label.text() == "Integrity: verified"
    host_summary.write_text(host_summary.read_text() + "\n")
    assert window.load_host_microbe_bigg_dir(host)
    assert window.integrity_label.text() == "Integrity: mismatch"
    window.close()


def test_host_search_null_transfer_keeps_range_and_identifiability():
    from cmig.gui.app import _host_search_summary_for_search_view

    adapted = _host_search_summary_for_search_view({
        "target": "ac", "status": "degraded", "top_ranked": [{
            "members": ["A"], "score": 1.0, "target_transfer": None,
            "target_transfer_range": [0.0, 2.0],
            "target_identifiability": "ambiguous", "target_reason": "alternate optima",
            "evaluation_status": "optimal",
        }],
    })
    row = adapted["top_ranked"][0]
    assert row["target_flux"] is None
    assert row["robustness_fva_lo"] == 0.0
    assert row["robustness_fva_hi"] == 2.0
    assert "ambiguous" in row["status"]
    assert row["diagnostic"] == "alternate optima"


def test_tidy_readback_rejects_wrong_manifest_nested_type_without_stale_state(tmp_path):
    from cmig.core.tidy import empty_bundle

    _app()
    window = build_main_window()
    good = tmp_path / "good"
    empty_bundle().write(good)
    (good / "manifest.json").write_text(json.dumps({"run_hash": "good", "provenance": {}}))
    window.load_run_dir(good)
    assert window.current_manifest is not None
    bad = tmp_path / "bad"
    empty_bundle().write(bad)
    (bad / "manifest.json").write_text(json.dumps({
        "run_hash": "bad", "provenance": ["wrong type"],
    }))
    window.load_run_dir(bad)
    assert window.current_manifest is None
    assert window.integrity_label.text() == "Integrity: invalid/unreadable"
    assert window.profile_view.table.rowCount() == 0
    window.close()


def test_search_readback_rejects_bad_nested_summary_without_stale_figure(tmp_path):
    _app()
    window = build_main_window()
    valid = tmp_path / "valid"
    valid.mkdir()
    (valid / "search_summary.json").write_text(json.dumps({
        "status": "ok", "strategy": "exhaustive", "top_ranked": [], "warnings": [],
    }))
    assert window.load_search_dir(valid)
    assert window.search_view.current_run_dir == valid.resolve()
    invalid = tmp_path / "invalid"
    invalid.mkdir()
    (invalid / "search_summary.json").write_text(json.dumps({
        "status": "ok", "strategy": "pareto", "top_ranked": {"ac": "wrong type"},
        "warnings": ["warning"],
    }))
    assert window.load_search_dir(invalid) is False
    assert window.search_view.current_run_dir is None
    assert window.search_view.figure_stack.currentWidget() is window.search_view.figure_placeholder
    window.close()


def test_large_digest_inspection_keeps_qt_event_loop_responsive(monkeypatch, tmp_path):
    import cmig.cli.main

    _app()
    large = tmp_path / "large.dat"
    with large.open("wb") as stream:
        stream.truncate(16 * 1024 * 1024 + 1)
    (tmp_path / "manifest.json").write_text(json.dumps({
        "manifest_scope": "workflow", "manifest_schema_version": "1.2",
        "workflow_kind": "dfba", "artifacts": [large.name],
        "result_digest": {"digest": "recorded", "artifacts": {}},
    }))
    monkeypatch.setattr(cmig.cli.main, "_inspect_run_dir", lambda path: (
        time.sleep(0.2) or {"artifact_integrity": "verified", "result_digest": None}
    ))
    window = build_main_window()
    callback_ran: list[bool] = []
    QTimer.singleShot(20, lambda: callback_ran.append(True))
    result = window._inspect_gui_run(tmp_path)
    assert result is not None
    assert callback_ran == [True]
    window.close()


def test_failed_job_keeps_artifact_result_and_status():
    from cmig.service.jobrunner import ArtifactJobFailure, JobFailed

    runner = JobRunner(max_workers=1)
    jid = runner.submit(
        "search", lambda ctx: (_ for _ in ()).throw(
            ArtifactJobFailure("scientific failure", {"status": "failed", "output_dir": "/tmp/run"})
        ),
    )
    with pytest.raises(JobFailed):
        runner.result(jid, timeout=5)
    job = runner.poll(jid)
    assert job.status is JobStatus.FAILED
    assert job.result["output_dir"] == "/tmp/run"
    runner.shutdown()


def test_search_cli_exit_two_retains_actionable_request_detail(monkeypatch, tmp_path):
    import cmig.cli.main
    from cmig.service.jobrunner import JobFailed

    monkeypatch.setattr(cmig.cli.main, "main", lambda argv: 2)
    _app()
    runner = JobRunner(max_workers=1)
    window = build_main_window(runner=runner)
    window.search_view.model_dir_input.setText(str(tmp_path))
    window.search_view.targets_input.setText("ac")
    jid = window.run_search_fixture()
    with pytest.raises(JobFailed):
        runner.result(jid, timeout=5)
    window._poll_completed_jobs()
    assert runner.poll(jid).status is JobStatus.FAILED
    assert "Invalid Search request" in window.search_view.details.toPlainText()
    assert "output_dir" in window.search_view.details.toPlainText()
    assert window.explorer.topLevelItem(2).childCount() == 1
    window.close()


def test_real_host_writer_sparse_fva_ranges_round_trip(tmp_path, monkeypatch):
    import cobra
    import pandas as pd

    from cmig.cli.main import _write_host_microbe_bigg_outputs

    cobra.Configuration().processes = 1
    science = runpy.run_path(str(Path(__file__).with_name("test_remediation_host_cli.py")))
    result = science["coupling"](
        science["alternative_host"](), {"ac": 5.0, "but": 5.0}
    )
    result.community_secretion = {"ac": 5.0, "but": 5.0}
    result.member_secretion = {"A": {"ac": 5.0, "but": 5.0}}
    result.objective_reactions = ["BIOMASS"]
    result.objective_warning = None
    result.coupling_scale = None
    run = tmp_path / "host"
    names = _write_host_microbe_bigg_outputs(
        result, pd.DataFrame([{"id": "A", "abundance": 1.0}]), run
    )
    (run / "manifest.json").write_text(json.dumps({
        "manifest_scope": "workflow", "manifest_schema_version": "1.2",
        "workflow_kind": "host_microbe_bigg", "artifacts": names,
        "result_digest": artifact_result_digest(run, "host_microbe_bigg", names),
    }))
    _app()
    window = build_main_window()
    assert window.load_host_microbe_bigg_dir(run)
    assert "5" in window.host_view.viability_label.text()
    rows = {
        window.host_view.cross_table.item(i, 0).text():
        window.host_view.cross_table.item(i, 1).text()
        for i in range(window.host_view.cross_table.rowCount())
    }
    assert rows == {"ac": "unknown [0.0, 5.0]", "but": "unknown [0.0, 5.0]"}
    assert window.host_view.iface_table.rowCount() == 0
    assert window.integrity_label.text() == "Integrity: verified"
    json_only = tmp_path / "json_only"
    json_only.mkdir()
    (json_only / "host_microbe_bigg_summary.json").write_bytes(
        (run / "host_microbe_bigg_summary.json").read_bytes()
    )
    assert window.load_host_microbe_bigg_dir(json_only)
    assert window.host_view.cross_table.rowCount() == 2
    zero = tmp_path / "identified_zero"
    zero.mkdir()
    identified = json.loads((run / "host_microbe_bigg_summary.json").read_text())
    identified["microbe_to_host"] = {"ac": 0.0}
    identified["microbe_to_host_ranges"] = {"ac": [0.0, 0.0]}
    identified["ambiguous_metabolites"] = []
    (zero / "host_microbe_bigg_summary.json").write_text(json.dumps(identified))
    assert window.load_host_microbe_bigg_dir(zero)
    assert window.host_view.cross_table.rowCount() == 1
    assert window.host_view.cross_table.item(0, 1).text() == "0"
    assert window.integrity_label.text() == "Integrity: not_recorded"
    contradictory = tmp_path / "contradictory_point"
    contradictory.mkdir()
    identified["microbe_to_host"] = {"ac": 2.0}
    identified["microbe_to_host_ranges"] = {"ac": [0.0, 5.0]}
    (contradictory / "host_microbe_bigg_summary.json").write_text(json.dumps(identified))
    assert window.load_host_microbe_bigg_dir(contradictory)
    assert window.host_view.cross_table.item(0, 1).text() == "unknown [0.0, 5.0]"
    invalid = tmp_path / "invalid_interval"
    invalid.mkdir()
    identified["microbe_to_host_ranges"] = {"ac": [5.0, 0.0]}
    (invalid / "host_microbe_bigg_summary.json").write_text(json.dumps(identified))
    assert not window.load_host_microbe_bigg_dir(invalid)
    assert window.host_view.cross_table.item(0, 1).text() == "unknown [0.0, 5.0]"

    # Actual LP/FVA [0,0] evidence has no acetate entry in its positive-only point map.
    model = science["alternative_host"]()
    model.reactions.acT.upper_bound = 0
    measured_zero = science["coupling"](model, {"ac": 5.0, "but": 5.0})
    assert measured_zero.impact.microbe_to_host_ranges["ac"] == pytest.approx((0, 0))
    assert "ac" not in measured_zero.impact.microbe_to_host
    window.host_view.load_impact(measured_zero.impact)
    live_zero = {
        window.host_view.cross_table.item(i, 0).text():
        window.host_view.cross_table.item(i, 1).text()
        for i in range(window.host_view.cross_table.rowCount())
    }
    assert live_zero["ac"] == "0"
    measured_zero.community_secretion = {"ac": 5.0, "but": 5.0}
    measured_zero.member_secretion = {"A": {"ac": 5.0, "but": 5.0}}
    measured_zero.objective_reactions = ["BIOMASS"]
    measured_zero.objective_warning = None
    measured_zero.coupling_scale = None
    real_zero_dir = tmp_path / "real_zero"
    zero_names = _write_host_microbe_bigg_outputs(
        measured_zero, pd.DataFrame([{"id": "A", "abundance": 1.0}]), real_zero_dir
    )
    (real_zero_dir / "manifest.json").write_text(json.dumps({
        "manifest_scope": "workflow", "manifest_schema_version": "1.2",
        "workflow_kind": "host_microbe_bigg", "artifacts": zero_names,
        "result_digest": artifact_result_digest(
            real_zero_dir, "host_microbe_bigg", zero_names
        ),
    }))
    with (real_zero_dir / "microbe_to_host.csv").open(newline="") as stream:
        import csv
        transfer_rows = {row["metabolite"]: row for row in csv.DictReader(stream)}
    assert float(transfer_rows["ac"]["transfer_flux"]) == pytest.approx(0)
    assert transfer_rows["ac"]["identifiable"] == "True"
    assert json.loads((real_zero_dir / "host_microbe_bigg_summary.json").read_text())[
        "microbe_to_host"
    ].get("ac") is None
    assert window.load_host_microbe_bigg_dir(real_zero_dir)
    zero_cells = {
        window.host_view.cross_table.item(i, 0).text():
        window.host_view.cross_table.item(i, 1).text()
        for i in range(window.host_view.cross_table.rowCount())
    }
    assert zero_cells["ac"] == "0"
    assert window.integrity_label.text() == "Integrity: verified"
    assert not any(
        element.get("data", {}).get("etype") == "cross_feeding"
        and element["data"].get("metabolite") == "ac"
        for element in window.host_view.network_payload["elements"]
    )

    import cmig.core.host_coupling as host_coupling

    def unavailable(*args, **kwargs):
        raise RuntimeError("injected FVA failure")

    monkeypatch.setattr(host_coupling, "_uptake_fva_ranges", unavailable)
    no_fva = science["coupling"](science["alternative_host"](), {"ac": 5.0})
    assert "ac" not in no_fva.impact.microbe_to_host_ranges
    no_fva.community_secretion = {"ac": 5.0}
    no_fva.member_secretion = {"A": {"ac": 5.0}}
    no_fva.objective_reactions = ["BIOMASS"]
    no_fva.objective_warning = None
    no_fva.coupling_scale = None
    unavailable_dir = tmp_path / "unavailable"
    unavailable_names = _write_host_microbe_bigg_outputs(
        no_fva, pd.DataFrame([{"id": "A", "abundance": 1.0}]), unavailable_dir
    )
    (unavailable_dir / "manifest.json").write_text(json.dumps({
        "manifest_scope": "workflow", "manifest_schema_version": "1.2",
        "workflow_kind": "host_microbe_bigg", "artifacts": unavailable_names,
        "result_digest": artifact_result_digest(
            unavailable_dir, "host_microbe_bigg", unavailable_names
        ),
    }))
    assert window.load_host_microbe_bigg_dir(unavailable_dir)
    assert window.host_view.cross_table.rowCount() == 0
    window.close()


@pytest.mark.parametrize("kind", ["abundance_impact", "strain_growth", "search"])
def test_completed_workflow_invalidates_only_applicable_edits(tmp_path, kind):
    _app()
    view = SearchView()
    request = view.request_fields(kind)
    view.load_summary(
        {"top_ranked": [], "strategy": kind}, run_dir=tmp_path,
        workflow_kind=kind, executed_request=request,
    )
    if kind == "search":
        view.cooperative_tradeoff_spin.setValue(0.8)
        assert view.current_run_dir == tmp_path.resolve()
        view.direction_combo.setCurrentText("min_uptake")
    else:
        view.direction_combo.setCurrentText("min_uptake")
        view.growth_fraction_spin.setValue(0.8)
        assert view.current_run_dir == tmp_path.resolve()
        view.cooperative_tradeoff_spin.setValue(0.8)
    assert view.current_run_dir is None
    view.close()


def test_irrelevant_edit_keeps_completed_superseded_ratio_result(tmp_path):
    _app()
    view = SearchView()
    executed = view.request_fields("abundance_impact")
    view.medium_input.setText(str(tmp_path / "later-medium.csv"))
    view.cooperative_tradeoff_spin.setValue(0.9)
    view.load_summary(
        {"top_ranked": [], "strategy": "ratio"}, run_dir=tmp_path,
        workflow_kind="abundance_impact", executed_request=executed,
        request_note=view.superseded_note(executed, "abundance_impact"),
    )
    assert "superseded" in view.details.toPlainText()
    view.direction_combo.setCurrentText("min_uptake")
    assert view.current_run_dir == tmp_path.resolve()
    assert "superseded" in view.details.toPlainText()
    view.cooperative_tradeoff_spin.setValue(0.8)
    assert view.current_run_dir is None
    view.close()


def test_present_search_conditions_survive_direct_and_adapted_details(tmp_path):
    from cmig.gui.app import _abundance_impact_summary_for_search_view, _with_search_conditions

    source = {
        "status": "degraded", "top_ranked": [], "warnings": ["one", "two"],
        "solution_semantics": "Pareto reporting order", "metric": "weighted_flux",
        "directions": {"ac": "max_secretion"}, "weights": {"ac": 2.0},
        "normalization_ranges": {"ac": [0, 5]}, "ga_metadata": {"seed": 37},
        "n_pareto_attempts": 16, "n_pareto_resolved_attempts": 1,
        "n_pareto_failed_attempts": 15,
    }
    _app()
    view = SearchView()
    adapted = _with_search_conditions(_abundance_impact_summary_for_search_view(source), source)
    for payload, recorded in ((source, None), (adapted, source)):
        view.load_summary(payload, run_dir=tmp_path, source_summary=recorded)
        details = view.details.toPlainText()
        for key in ("solution_semantics", "metric", "directions", "weights",
                    "normalization_ranges", "ga_metadata"):
            assert f"{key}:" in details
        assert "seed': 37" in details
        assert "Warning 2: two" in details
        assert 'Recorded summary JSON:' in details
        assert '"solution_semantics": "Pareto reporting order"' in details
    view.close()


@pytest.mark.parametrize("missing", ["medium", "pool"])
def test_real_cli_input_failure_retains_exact_path(tmp_path, missing):
    from cmig.service.jobrunner import JobFailed

    _app()
    runner = JobRunner(max_workers=1)
    window = build_main_window(runner=runner)
    prior = tmp_path / "prior_search"
    _search_run(prior, {"status": "ok", "strategy": "exhaustive", "top_ranked": [],
                        "warnings": []})
    assert window.load_search_dir(prior)
    assert window.integrity_label.text() == "Integrity: verified"
    pool = tmp_path / "pool"
    pool.mkdir()
    if missing == "medium":
        (pool / "member.xml").write_text("model placeholder")
        path = tmp_path / "NONEXISTENT_review_medium.csv"
        window.search_view.medium_input.setText(str(path))
    else:
        path = pool
    window.search_view.model_dir_input.setText(str(pool))
    window.search_view.targets_input.setText("ac")
    jid = window.run_search_fixture()
    with pytest.raises(JobFailed):
        runner.result(jid, timeout=15)
    window._poll_completed_jobs()
    assert runner.poll(jid).status is JobStatus.FAILED
    assert "input_diagnostic:" in window.search_view.details.toPlainText()
    assert str(path) in window.search_view.details.toPlainText()
    assert str(path) in (runner.poll(jid).error or "")
    assert window.search_view.table.rowCount() == 0
    failed_run = Path(runner.poll(jid).result["output_dir"]).resolve()
    assert window.search_view.current_run_dir == failed_run
    assert window.current_search_dir == failed_run
    assert window.integrity_label.text() == "Integrity: not_recorded"
    assert str(failed_run) in window._integrity_detail
    assert "no_manifest" in window._integrity_detail
    assert str(prior) not in window._integrity_detail
    assert str(failed_run) in window.search_view.details.toPlainText()
    assert "search failed (rc=2)" in window.search_view.status.text()
    assert window.explorer.topLevelItem(2).childCount() == 2
    assert not window.search_view.export_figure_btn.isEnabled()
    window.close()


@pytest.mark.parametrize("change", [
    [5],
    [{"members": ["A"], "score": {}, "target_flux": 3,
      "community_growth": 1, "status": "optimal"}],
    [{"members": ["A"], "score": 3, "target_flux": {},
      "community_growth": 1, "status": "optimal"}],
    [{"members": ["A"], "weighted_score": [], "target_flux": 3}],
    [{"members": ["A"], "target_fluxes": {"ac": {}}, "score": 3}],
    [{"members": ["A"], "community_growth": {}}],
    [{"members": ["A"], "robustness_fva_lo": {}}],
    [{"members": {}}],
    [{"members": ["A"], "diagnostic": []}],
])
def test_verified_search_rejects_malformed_rank_records_after_good_run(tmp_path, change):
    _app()
    window = build_main_window()
    prior = tmp_path / "prior"
    bad = tmp_path / "bad"
    _search_run(prior, {"status": "ok", "top_ranked": [], "warnings": []})
    _search_run(bad, {"status": "ok", "top_ranked": change, "warnings": []})
    assert window.load_search_dir(prior)
    assert window.load_search_dir(bad) is False
    assert window.search_view.current_run_dir is None
    assert window.current_search_dir is None
    assert window.search_view.table.rowCount() == 0
    assert not window.search_view.export_figure_btn.isEnabled()
    assert window.integrity_label.text() == "Readback: invalid/unreadable"
    assert f"Run: {bad}" in window._integrity_detail
    assert "Artifact digest: verified" in window._integrity_detail
    assert window.explorer.topLevelItem(2).childCount() == 1
    window.close()


def test_search_nullable_numeric_readouts_remain_unknown(tmp_path):
    _app()
    window = build_main_window()
    run = tmp_path / "nullable"
    _search_run(run, {"status": "ok", "top_ranked": [{
        "members": ["A"], "score": None, "target_flux": None,
        "community_growth": None, "robustness_fva_lo": None,
        "robustness_fva_hi": None, "status": "optimal",
    }, {"members": ["B"], "weighted_score": "2.5", "target_flux": "3.5"}],
        "warnings": []})
    assert window.load_search_dir(run)
    assert [window.search_view.table.item(0, i).text() for i in (2, 3, 4)] == [
        "—", "—", "—"]
    assert window.search_view.table.item(1, 2).text() == "2.5"
    assert window.search_view.table.item(1, 3).text() == "3.5"
    assert window.integrity_label.text() == "Integrity: verified"
    window.close()


@pytest.mark.parametrize("invalid_rank", [[5], [{"members": ["A"], "score": {}}],
                                          [{"members": ["A"], "target_flux": {}}]])
def test_completed_search_rejects_verified_malformed_rank(monkeypatch, tmp_path, invalid_rank):
    import cmig.cli.main

    def fake_main(argv):
        out = Path(argv[argv.index("--out") + 1])
        (out / "search_summary.json").write_text(json.dumps({
            "status": "ok", "top_ranked": invalid_rank, "warnings": [],
        }))
        (out / "manifest.json").write_text(json.dumps({
            "manifest_scope": "workflow", "manifest_schema_version": "1.2",
            "workflow_kind": "search", "artifacts": ["search_summary.json"],
            "result_digest": artifact_result_digest(out, "search", ["search_summary.json"]),
        }))
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    _app()
    runner = JobRunner(max_workers=1)
    window = build_main_window(runner=runner)
    prior = tmp_path / "prior"
    _search_run(prior, {"status": "ok", "top_ranked": [], "warnings": []})
    assert window.load_search_dir(prior)
    window.search_view.model_dir_input.setText(str(tmp_path))
    window.search_view.targets_input.setText("ac")
    jid = window.run_search_fixture()
    runner.result(jid, timeout=5)
    out_dir = window._search_jobs[jid][0]
    window._poll_completed_jobs()
    assert window.search_view.current_run_dir is None
    assert window.current_search_dir is None
    assert window.search_view.table.rowCount() == 0
    assert not window.search_view.export_figure_btn.isEnabled()
    assert window.integrity_label.text() == "Readback: invalid/unreadable"
    assert str(out_dir) in window._integrity_detail
    assert "Artifact digest: verified" in window._integrity_detail
    assert window.explorer.topLevelItem(2).childCount() == 1
    window.close()


def test_failed_search_rejects_verified_malformed_rank(monkeypatch, tmp_path):
    import cmig.cli.main
    from cmig.service.jobrunner import JobFailed

    def fake_main(argv):
        out = Path(argv[argv.index("--out") + 1])
        (out / "search_summary.json").write_text(json.dumps({
            "status": "failed", "top_ranked": [{"score": {}}], "warnings": [],
        }))
        (out / "manifest.json").write_text(json.dumps({
            "manifest_scope": "workflow", "manifest_schema_version": "1.2",
            "workflow_kind": "search", "artifacts": ["search_summary.json"],
            "result_digest": artifact_result_digest(out, "search", ["search_summary.json"]),
        }))
        return 3

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    _app()
    runner = JobRunner(max_workers=1)
    window = build_main_window(runner=runner)
    prior = tmp_path / "prior"
    _search_run(prior, {"status": "ok", "top_ranked": [], "warnings": []})
    assert window.load_search_dir(prior)
    window.search_view.model_dir_input.setText(str(tmp_path))
    window.search_view.targets_input.setText("ac")
    jid = window.run_search_fixture()
    with pytest.raises(JobFailed):
        runner.result(jid, timeout=5)
    out_dir = window._search_jobs[jid][0]
    window._poll_completed_jobs()
    assert window.search_view.current_run_dir is None
    assert window.current_search_dir is None
    assert window.integrity_label.text() == "Readback: invalid/unreadable"
    assert str(out_dir) in window._integrity_detail
    assert "Artifact digest: verified" in window._integrity_detail
    assert window.explorer.topLevelItem(2).childCount() == 1
    window.close()


def test_rejected_host_objective_keeps_complete_previous_view(tmp_path):
    _app()
    window = build_main_window()
    good = tmp_path / "host_good"
    bad = tmp_path / "host_bad"
    for run, objective in ((good, 5.0), (bad, {})):
        run.mkdir()
        (run / "host_microbe_bigg_summary.json").write_text(json.dumps({
            "host": {"viable": True, "status": "optimal", "objective_value": objective,
                     "lumen_uptake": {"ac": 1.0}},
            "microbe_to_host": {"ac": 1.0}, "microbial_secretion": {"ac": 1.0},
            "warnings": [],
        }))
        digest = artifact_result_digest(run, "host_microbe_bigg", [
            "host_microbe_bigg_summary.json"
        ])
        (run / "manifest.json").write_text(json.dumps({
            "manifest_scope": "workflow", "manifest_schema_version": "1.2",
            "workflow_kind": "host_microbe_bigg",
            "artifacts": ["host_microbe_bigg_summary.json"], "result_digest": digest,
        }))
    assert window.load_host_microbe_bigg_dir(good)
    before = (window.integrity_label.text(), window._integrity_detail,
              window.host_view.current_run_dir, window.current_host_microbe_dir,
              window.host_view.viability_label.text())
    assert window.load_host_microbe_bigg_dir(bad) is False
    assert before == (window.integrity_label.text(), window._integrity_detail,
                      window.host_view.current_run_dir, window.current_host_microbe_dir,
                      window.host_view.viability_label.text())
    assert str(bad) in window.statusBar().currentMessage()
    window.close()


@pytest.mark.parametrize("kind", ["search", "dfba", "spatial"])
def test_valid_digest_cannot_certify_invalid_summary_schema(tmp_path, kind):
    _app()
    window = build_main_window()
    filename = f"{kind}_summary.json"
    summary = {
        "search": {"status": "ok", "top_ranked": {"ac": "bad"}, "warnings": []},
        "dfba": {"status": "ok", "final_t": {}, "final_biomass": 1,
                 "final_concentrations": {}, "warnings": []},
        "spatial": {"status": "ok", "final_t": {}, "final_min": 0,
                    "final_max": 1, "warnings": []},
    }[kind]
    prior_summary = {
        "search": {"status": "ok", "top_ranked": [], "warnings": []},
        "dfba": {"status": "ok", "final_t": 1, "final_biomass": 1,
                 "final_concentrations": {}, "warnings": []},
        "spatial": {"status": "ok", "final_t": 1, "final_min": 0,
                    "final_max": 1, "warnings": []},
    }[kind]
    prior = tmp_path / "prior"
    prior.mkdir()
    (prior / filename).write_text(json.dumps(prior_summary))
    (prior / "manifest.json").write_text(json.dumps({
        "manifest_scope": "workflow", "manifest_schema_version": "1.2",
        "workflow_kind": kind, "artifacts": [filename],
        "result_digest": artifact_result_digest(prior, kind, [filename]),
    }))
    assert getattr(window, f"load_{kind}_dir")(prior)
    assert window.integrity_label.text() == "Integrity: verified"
    run = tmp_path / kind
    run.mkdir()
    (run / filename).write_text(json.dumps(summary))
    (run / "manifest.json").write_text(json.dumps({
        "manifest_scope": "workflow", "manifest_schema_version": "1.2",
        "workflow_kind": kind, "artifacts": [filename],
        "result_digest": artifact_result_digest(run, kind, [filename]),
    }))
    loaded = getattr(window, f"load_{kind}_dir")(run)
    assert loaded is False
    assert window.integrity_label.text() == "Readback: invalid/unreadable"
    assert "Artifact digest: verified" in window._integrity_detail
    view_status = (window.search_view.status if kind == "search"
                   else window.dynamics_view.status).text()
    assert "Readback invalid/unreadable" in view_status
    assert (window.search_view.current_run_dir if kind == "search"
            else window.dynamics_view.table.rowCount()) in (None, 0)
    window.close()


def test_failed_search_invalid_manifest_is_not_published(monkeypatch, tmp_path):
    import cmig.cli.main
    from cmig.service.jobrunner import JobFailed

    def fake_main(argv):
        out = Path(argv[argv.index("--out") + 1])
        (out / "manifest.json").write_text("null")
        (out / "search_summary.json").write_text(json.dumps({
            "status": "failed", "top_ranked": [], "warnings": [],
        }))
        return 3

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    _app()
    runner = JobRunner(max_workers=1)
    window = build_main_window(runner=runner)
    window.search_view.model_dir_input.setText(str(tmp_path))
    window.search_view.targets_input.setText("ac")
    jid = window.run_search_fixture()
    with pytest.raises(JobFailed):
        runner.result(jid, timeout=5)
    window._poll_completed_jobs()
    assert window.current_search_dir is None
    assert window.search_view.current_run_dir is None
    assert window.explorer.topLevelItem(2).childCount() == 0
    assert window.integrity_label.text() == "Integrity: invalid/unreadable"
    window.close()


def test_missing_essential_tidy_nodes_is_readback_failure(tmp_path):
    from cmig.core.tidy import empty_bundle

    _app()
    run = tmp_path / "tidy"
    run.mkdir()
    empty_bundle().write(run)
    names = sorted(p.name for p in run.glob("*.parquet"))
    (run / "manifest.json").write_text(json.dumps({
        "manifest_scope": "workflow", "manifest_schema_version": "1.2",
        "workflow_kind": "solve", "artifacts": names,
        "result_digest": artifact_result_digest(run, "solve", names),
    }))
    (run / "nodes.parquet").unlink()
    window = build_main_window()
    window.load_run_dir(run)
    assert window.integrity_label.text() == "Readback: invalid/unreadable"
    assert "missing essential nodes.parquet" in window._integrity_detail
    assert window.current_manifest is None
    assert window.explorer.topLevelItem(2).childCount() == 0
    window.close()
