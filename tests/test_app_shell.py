"""Phase 0.3 — App Shell offscreen 실행 검증. Plan SC: SC-AP1~AP6.

QT_QPA_PLATFORM=offscreen(conftest)에서 PySide6 셸을 *실제로* 생성·소비. JobRunner→Qt bridge 가
실 job 상태를 표시하는지 검증. offscreen = 실행 증거지 human 시각 QA(G-7b) 아님(정직).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import CmigMainWindow, build_main_window  # noqa: E402
from cmig.service import JobRunner, JobStatus  # noqa: E402
from cmig.service.jobrunner import JobCancelled  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_shell_constructs_offscreen():
    """SC-AP1: 3-pane 셸 offscreen 생성(예외 없음) + 패널 존재."""
    _app()
    w = build_main_window(lang="ko")
    assert isinstance(w, CmigMainWindow)
    assert w.explorer.topLevelItemCount() == 3  # 모델·시나리오·실행
    assert w.jobs_panel.columnCount() == 4
    assert [w.tabs.tabText(i) for i in range(w.tabs.count())] == [
        "모델",
        "탐색",
        "숙주",
        "동역학",
        "그래프",
        "외부 프로필",
    ]
    assert w.tabs.currentWidget() is w.search_view
    assert w.sweep_view.runner is w.runner
    assert w.search_view is not None
    assert "CMIG" in w.windowTitle()


def test_i18n_ko_en():
    """SC-AP2: Korean is real translation; the no-argument factory defaults to English."""
    _app()
    ko = build_main_window(lang="ko")
    en = build_main_window(lang="en")
    default = build_main_window()
    assert ko.tr_map["explorer"] == "프로젝트 탐색기"
    assert en.tr_map["explorer"] == "Project Explorer"
    assert ko.open_run_action.text() == "실행 열기"
    assert default.open_run_action.text() == "Open Run"
    assert ko.statusBar().currentMessage() == "준비됨"
    assert default.statusBar().currentMessage() == "Ready"


def test_project_explorer_add_model():
    """SC-AP3: ProjectExplorer 모델 추가."""
    _app()
    w = build_main_window()
    w.explorer.add_model("e_coli_core")
    models_root = w.explorer.topLevelItem(0)
    assert models_root.childCount() == 1
    assert models_root.child(0).text(0) == "e_coli_core"


def test_shell_has_file_workflow_actions():
    """GUI shell 이 파일 열기/fixture 실행 액션을 노출한다."""
    _app()
    w = build_main_window()
    assert w.import_model_action.text() == "Import Model"
    assert w.open_run_action.text() == "Open Run"
    assert w.run_fixture_action.text() == "Run Fixture"
    assert w.advanced_tools_action.text() == "Show Advanced Tools"


def test_advanced_tabs_are_hidden_until_requested():
    """Non-primary tools should not look like unfinished default workflows."""
    _app()
    w = build_main_window()
    assert w.tabs.indexOf(w.community_builder) == -1
    assert w.tabs.indexOf(w.medium_editor) == -1
    assert w.tabs.indexOf(w.sweep_view) == -1
    assert w.tabs.indexOf(w.sandbox_view) == -1
    assert w.tabs.indexOf(w.scenario_compare) == -1
    w.advanced_tools_action.setChecked(True)
    labels = [w.tabs.tabText(i) for i in range(w.tabs.count())]
    assert {"Community", "Medium", "Sweep", "Sandbox", "Compare"} <= set(labels)
    assert w.advanced_tools_action.text() == "Hide Advanced Tools"
    assert "Advanced preview" in w.community_builder.status.text()
    assert "Advanced editor" in w.medium_editor.status.text()
    assert "Advanced result view" in w.sweep_view.status.text()
    assert "Advanced sandbox" in w.sandbox_view.status.text()
    assert "Advanced preview" in w.scenario_compare.status.text()
    w.advanced_tools_action.setChecked(False)
    assert [w.tabs.tabText(i) for i in range(w.tabs.count())] == [
        "Models",
        "Search",
        "Host",
        "Dynamics",
        "Graph",
        "Profile",
    ]
    assert w.advanced_tools_action.text() == "Show Advanced Tools"


def test_load_run_dir_updates_profile_and_explorer(tmp_path):
    """Open Run 워크플로: tidy run 디렉터리 → Profile 탭 + run explorer."""
    from cmig.core.tidy import empty_bundle

    _app()
    empty_bundle().write(tmp_path)
    w = build_main_window()
    (tmp_path / "manifest.json").write_text('{"run_hash": "abc1234567890"}\n')
    w.load_run_dir(tmp_path)
    runs_root = w.explorer.topLevelItem(2)
    assert runs_root.childCount() == 1
    assert runs_root.child(0).text(0) == tmp_path.name
    assert w.profile_view.table.rowCount() == 0
    assert w.current_manifest["run_hash"] == "abc1234567890"
    assert "elements" in w.current_graph_payload
    assert w.tabs.currentWidget() is w.profile_view


def test_project_explorer_run_double_click_reopens_run(tmp_path):
    """Runs in Project Explorer should reopen their stored output directory."""
    from cmig.core.tidy import empty_bundle

    _app()
    empty_bundle().write(tmp_path)
    (tmp_path / "manifest.json").write_text('{"run_hash": "abc1234567890"}\n')
    w = build_main_window()
    w.load_run_dir(tmp_path)
    w.tabs.setCurrentWidget(w.search_view)
    item = w.explorer.topLevelItem(2).child(0)
    w._open_explorer_item(item, 0)
    assert w.tabs.currentWidget() is w.profile_view
    assert w.explorer.topLevelItem(2).childCount() == 1


def test_load_host_microbe_bigg_dir_updates_host_tab(tmp_path):
    """Open Run can load host-microbe BiGG outputs into the Host tab."""
    import json

    _app()
    (tmp_path / "host_microbe_bigg_summary.json").write_text(
        json.dumps(
            {
                "host": {
                    "status": "optimal",
                    "viable": True,
                    "objective_value": 12.5,
                    "lumen_uptake": {"ac": 1.25},
                },
                "microbe_to_host": {"ac": 1.25},
                "unused_secretion": {},
            }
        )
    )
    (tmp_path / "host_uptake.csv").write_text("metabolite,uptake_flux\nac,1.25\n")
    w = build_main_window()
    assert w.load_host_microbe_bigg_dir(tmp_path) is True
    assert w.tabs.currentWidget() is w.host_view
    assert w.host_view.iface_table.rowCount() == 1
    assert w.host_view.cross_table.rowCount() == 1
    assert w.host_view.cross_table.item(0, 0).text() == "ac"
    assert w.explorer.topLevelItem(2).child(0).text(0) == tmp_path.name


def test_load_dfba_dir_updates_dynamics_tab(tmp_path):
    import json

    _app()
    (tmp_path / "dfba_summary.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "final_t": 1.0,
                "final_biomass": 0.02,
                "final_concentrations": {"EX_glc__D_e": 9.5},
            }
        )
    )
    w = build_main_window()
    assert w.load_dfba_dir(tmp_path) is True
    assert w.tabs.currentWidget() is w.dynamics_view
    assert w.dynamics_view.table.item(0, 0).text() == "dFBA"
    assert "biomass=0.02" in w.dynamics_view.table.item(0, 3).text()


def test_load_spatial_dir_updates_dynamics_tab(tmp_path):
    import json

    _app()
    (tmp_path / "spatial_summary.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "final_t": 8.0,
                "final_min": 0.0,
                "final_max": 10.0,
            }
        )
    )
    w = build_main_window()
    assert w.load_spatial_dir(tmp_path) is True
    assert w.tabs.currentWidget() is w.dynamics_view
    assert w.dynamics_view.table.item(0, 0).text() == "Spatial"
    assert "range=0..10" in w.dynamics_view.table.item(0, 3).text()


def test_run_spatial_preview_passes_dt_to_cli(monkeypatch, tmp_path):
    import json

    import cmig.cli.main

    seen = {"argv": []}

    def fake_main(argv):
        seen["argv"] = list(argv)
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "spatial_summary.json").write_text(
            json.dumps(
                {
                    "status": "completed",
                    "final_t": 1.0,
                    "final_min": 0.0,
                    "final_max": 10.0,
                }
            )
        )
        (out / "spatial_snapshots.svg").write_text("<svg/>")
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    w.dynamics_view.spatial_dt_spin.setValue(0.25)
    jid = w.run_spatial_preview()
    runner.result(jid, timeout=5)
    w._poll_completed_jobs()
    assert seen["argv"][0] == "spatial-preview"
    assert seen["argv"][seen["argv"].index("--dt") + 1] == "0.25"
    assert w.dynamics_view.run_spatial_btn.isEnabled()
    runner.shutdown()


def test_import_model_file_updates_model_manager(monkeypatch):
    from cmig.io.model_import import ModelSummary

    _app()
    w = build_main_window()

    def fake_import_model(path):
        return ModelSummary("toy", "sbml", str(path), 2, 2, 0, ["EX_ac_e"], ["BIOMASS"])

    monkeypatch.setattr("cmig.io.model_import.import_model", fake_import_model)
    assert w.import_model_file("/tmp/toy.xml") is True
    assert "toy" in w.model_manager.summary_label.text()
    assert w.explorer.topLevelItem(0).child(0).text(0) == "toy"
    assert w.current_model_review["model"]["model_id"] == "toy"


def test_run_fixture_uses_jobrunner_and_loads_completed_run(tmp_path, monkeypatch):
    """Run Fixture 워크플로는 GUI thread 직접 solve 대신 JobRunner 를 사용한다."""
    from types import SimpleNamespace

    import cmig.service
    from cmig.core.tidy import empty_bundle

    class FakeEngineService:
        def solve_fixture(self, *, solver, out_dir):
            empty_bundle().write(out_dir)
            manifest = out_dir / "manifest.json"
            manifest.write_text("{}\n")
            return SimpleNamespace(status="ok", manifest_path=manifest, diagnostic=None)

    monkeypatch.setattr(cmig.service, "EngineService", FakeEngineService)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    jid = w.run_fixture(tmp_path)
    assert w.runner.poll(jid).kind == "solve_fixture"
    runner.result(jid, timeout=5)
    assert w.load_completed_fixture(jid) is True
    assert w.explorer.topLevelItem(2).childCount() == 1
    runner.shutdown()


def test_poll_completed_fixture_auto_loads_run(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import cmig.service
    from cmig.core.tidy import empty_bundle

    class FakeEngineService:
        def solve_fixture(self, *, solver, out_dir):
            empty_bundle().write(out_dir)
            manifest = out_dir / "manifest.json"
            manifest.write_text('{"run_hash": "fixturehash"}\n')
            return SimpleNamespace(status="ok", manifest_path=manifest, diagnostic=None)

    monkeypatch.setattr(cmig.service, "EngineService", FakeEngineService)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    jid = w.run_fixture(tmp_path)
    runner.result(jid, timeout=5)
    w._poll_completed_jobs()
    assert jid not in w._fixture_jobs
    assert w.explorer.topLevelItem(2).childCount() == 1
    assert w.current_manifest["run_hash"] == "fixturehash"
    runner.shutdown()


def _drain_sandbox_job(w, runner, timeout: float = 10.0) -> None:
    """Round-5 P2: the sandbox now solves through JobRunner instead of freezing the Qt main
    thread, so the preview result arrives via `_poll_completed_jobs` like every other view."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and w._sandbox_jobs:
        w._poll_completed_jobs()
        time.sleep(0.01)
    assert not w._sandbox_jobs, "sandbox job did not complete"


def test_sandbox_preview_button_runs_service(monkeypatch):
    from types import SimpleNamespace

    import cmig.service
    from cmig.core.delta import DeltaResult

    class FakeEngineService:
        def sandbox_fixture(self, *, reaction_id, lower, upper, commit, out_dir):
            return SimpleNamespace(
                delta=DeltaResult([], [], [], 0.0),
                run_hash="hash" if commit else None,
            )

    monkeypatch.setattr(cmig.service, "EngineService", FakeEngineService)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    w.sandbox_view.add_bound("EX_glc__D_e", -1.0, 1000.0)
    w.sandbox_view.preview_btn.click()
    _drain_sandbox_job(w, runner)
    assert "preview" in w.sandbox_view.status.text()
    runner.shutdown()


def test_sandbox_rejects_multiple_bounds_before_silent_ignore(monkeypatch):
    import cmig.service

    called = {"value": False}

    class FakeEngineService:
        def sandbox_fixture(self, **kwargs):
            called["value"] = True
            raise AssertionError("should not run with multiple constraints")

    monkeypatch.setattr(cmig.service, "EngineService", FakeEngineService)
    _app()
    w = build_main_window()
    w.sandbox_view.add_bound("EX_a", -1.0, 1000.0)
    w.sandbox_view.add_bound("EX_b", -2.0, 1000.0)
    w.sandbox_view.preview_btn.click()
    assert called["value"] is False
    assert "one bound" in w.sandbox_view.status.text()


def test_sandbox_debounce_triggers_preview_after_bound_edit(monkeypatch):
    """The `_debounce` QTimer must not be dead code: an edit restarts it, and its timeout
    programmatically clicks Preview (reusing the existing preview wiring/JobRunner path)."""
    from types import SimpleNamespace

    from PySide6.QtCore import QEventLoop, QTimer

    import cmig.service
    from cmig.core.delta import DeltaResult

    calls = {"n": 0}

    class FakeEngineService:
        def sandbox_fixture(self, *, reaction_id, lower, upper, commit, out_dir):
            calls["n"] += 1
            return SimpleNamespace(
                delta=DeltaResult([], [], [], 0.0),
                run_hash="hash" if commit else None,
            )

    monkeypatch.setattr(cmig.service, "EngineService", FakeEngineService)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    w.sandbox_view._debounce.setInterval(20)
    w.sandbox_view.add_bound("EX_glc__D_e", -1.0, 1000.0)
    loop = QEventLoop()
    w.sandbox_view._debounce.timeout.connect(loop.quit)
    QTimer.singleShot(2000, loop.quit)
    loop.exec()
    _drain_sandbox_job(w, runner)
    assert calls["n"] == 1
    assert "preview" in w.sandbox_view.status.text()
    runner.shutdown()


def test_search_button_requires_model_folder(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    jid = w.run_search_fixture()
    assert jid == ""
    assert "Select a model folder" in w.search_view.status.text()
    assert not (tmp_path / ".run").exists()
    runner.shutdown()


def test_search_button_uses_model_dir_product_command(monkeypatch, tmp_path):
    import json

    import cmig.cli.main

    seen = {"argv": []}

    def fake_main(argv):
        seen["argv"] = list(argv)
        out = argv[argv.index("--out") + 1]
        payload = {
            "strategy": "exhaustive",
            "target": "but",
            "top_ranked": [
                {
                    "members": ["A", "B"],
                    "score": 2.0,
                    "target_flux": 2.0,
                    "status": "optimal",
                }
            ],
            "warnings": [],
        }
        from pathlib import Path

        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / "search_summary.json").write_text(json.dumps(payload))
        (Path(out) / "search_plot.svg").write_text("<svg>ranking</svg>")
        (Path(out) / "search_scatter.svg").write_text("<svg>scatter</svg>")
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    w.search_view.model_dir_input.setText(str(tmp_path))
    w.search_view.targets_input.setText("but")
    w.search_view.min_size_spin.setValue(200)
    w.search_view.max_size_spin.setValue(200)
    w.search_view.robustness_check.setChecked(True)
    jid = w.run_search_fixture()
    runner.result(jid, timeout=5)
    w._poll_completed_jobs()
    assert seen["argv"][0] == "search"
    assert seen["argv"][seen["argv"].index("--model-dir") + 1] == str(tmp_path)
    assert seen["argv"][seen["argv"].index("--min-size") + 1] == "200"
    assert seen["argv"][seen["argv"].index("--max-size") + 1] == "200"
    assert "--robustness-fva" in seen["argv"]
    assert w.search_view.table.item(0, 1).text() == "but"
    assert w.current_search_dir is not None
    assert (w.current_search_dir / "search_plot.svg").exists()
    assert w.search_view.current_run_dir == w.current_search_dir
    assert w.search_view.run_btn.isEnabled()
    runner.shutdown()


def test_strain_growth_button_uses_model_dir_command(monkeypatch, tmp_path):
    import json

    import cmig.cli.main

    seen = {"argv": []}

    def fake_main(argv):
        seen["argv"] = list(argv)
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        payload = {
            "status": "optimal",
            "members": [
                {
                    "member": "producer",
                    "single_growth": 1.0,
                    "community_member_growth": 0.5,
                    "community_growth": 0.5,
                    "community_status": "optimal",
                }
            ],
            "artifacts": ["strain_growth_plot.svg"],
        }
        (out / "strain_growth_summary.json").write_text(json.dumps(payload))
        (out / "strain_growth_plot.svg").write_text("<svg>growth</svg>")
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    w.search_view.model_dir_input.setText(str(tmp_path))
    jid = w.run_strain_growth_report()
    runner.result(jid, timeout=5)
    w._poll_completed_jobs()
    assert seen["argv"][0] == "strain-growth"
    assert seen["argv"][seen["argv"].index("--model-dir") + 1] == str(tmp_path)
    assert w.search_view.table.item(0, 0).text() == "producer"
    assert w.search_view.table.item(0, 1).text() == "growth"
    assert w.search_view.run_growth_btn.isEnabled()
    runner.shutdown()


def test_abundance_impact_button_uses_member_and_fractions(monkeypatch, tmp_path):
    import json

    import cmig.cli.main

    seen = {"argv": []}

    def fake_main(argv):
        seen["argv"] = list(argv)
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        payload = {
            "status": "ok",
            "target_member": "producer",
            "target": "ac",
            "rows": [
                {
                    "target_abundance": 0.2,
                    "target_influence_share": 0.7,
                    "target_member_exchange": 1.2,
                    "community_growth": 0.5,
                    "status": "optimal",
                }
            ],
            "artifacts": ["abundance_impact_plot.svg"],
        }
        (out / "abundance_impact_summary.json").write_text(json.dumps(payload))
        (out / "abundance_impact_plot.svg").write_text("<svg>impact</svg>")
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    w.search_view.model_dir_input.setText(str(tmp_path))
    w.search_view.growth_member_input.setText("producer")
    w.search_view.abundance_fractions_input.setText("0.2,0.8")
    w.search_view.targets_input.setText("ac")
    jid = w.run_abundance_impact()
    runner.result(jid, timeout=5)
    w._poll_completed_jobs()
    assert seen["argv"][0] == "abundance-impact"
    assert seen["argv"][seen["argv"].index("--member") + 1] == "producer"
    assert seen["argv"][seen["argv"].index("--fractions") + 1] == "0.2,0.8"
    assert w.search_view.table.item(0, 0).text() == "producer@0.2"
    assert w.search_view.table.item(0, 1).text() == "ac"
    assert w.search_view.run_abundance_btn.isEnabled()
    runner.shutdown()


def test_search_figure_export_copies_selected_svg(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    _app()
    run_dir = tmp_path / "search"
    run_dir.mkdir()
    (run_dir / "search_scatter.svg").write_text("<svg>scatter</svg>")
    target = tmp_path / "export.svg"
    w = build_main_window()
    # Round-5 P2 / verifier V-1: the export is keyed to the run the Search table is
    # *displaying*, so that an invalidated result cannot be exported after the user has been
    # told it was discarded. `current_run_dir` is what a real completed run sets.
    w.search_view.current_run_dir = run_dir
    w.current_search_dir = run_dir
    w.search_view.figure_mode_combo.setCurrentText("Scatter")
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(target), "SVG (*.svg)"),
    )
    w._export_search_figure()
    assert target.read_text() == "<svg>scatter</svg>"
    assert "Exported figure" in w.search_view.status.text()


def test_host_microbe_run_button_uses_product_command(monkeypatch, tmp_path):
    import json

    import cmig.cli.main

    seen = {"argv": []}

    def fake_main(argv):
        seen["argv"] = list(argv)
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "host_microbe_bigg_summary.json").write_text(
            json.dumps(
                {
                    "host": {
                        "status": "optimal",
                        "viable": True,
                        "objective_value": 3.0,
                        "lumen_uptake": {"ac": 1.0},
                    },
                    "microbial_secretion": {"ac": 1.0},
                    "microbe_to_host": {"ac": 1.0},
                    "unused_secretion": {},
                    "warnings": [],
                }
            )
        )
        (out / "host_uptake.csv").write_text("metabolite,uptake_flux\nac,1.0\n")
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    w.host_view.host_path_input.setText(str(tmp_path / "Recon3D.xml"))
    w.host_view.model_dir_input.setText(str(tmp_path / "models"))
    w.host_view.out_dir_input.setText(str(tmp_path / "out"))
    w.host_view.microbial_biomass_spin.setValue(0.25)
    w.host_view.host_biomass_spin.setValue(4.0)
    w.host_view.biomass_basis_kind_combo.setCurrentText("measured")
    w.host_view.biomass_basis_source_input.setText("Methods section dry-mass assay")
    w.host_view.recursive_check.setChecked(True)
    w.host_view.include_currency_check.setChecked(True)
    jid = w.run_host_microbe_bigg()
    runner.result(jid, timeout=5)
    w._poll_completed_jobs()
    assert seen["argv"][0] == "host-microbe-bigg"
    assert seen["argv"][seen["argv"].index("--host") + 1].endswith("Recon3D.xml")
    assert seen["argv"][seen["argv"].index("--model-dir") + 1].endswith("models")
    assert "--recursive" in seen["argv"]
    assert "--include-currency-metabolites" in seen["argv"]
    assert seen["argv"][seen["argv"].index("--biomass-basis-kind") + 1] == "measured"
    assert "Methods section" in seen["argv"][seen["argv"].index("--biomass-basis-source") + 1]
    assert w.tabs.currentWidget() is w.host_view
    assert w.host_view.cross_table.rowCount() == 1
    assert w.host_view.network_payload is not None
    runner.shutdown()


def test_host_microbe_gui_blocks_missing_biomass_provenance(tmp_path):
    _app()
    w = build_main_window()
    w.host_view.host_path_input.setText(str(tmp_path / "host.xml"))
    w.host_view.model_dir_input.setText(str(tmp_path / "models"))
    w.host_view.out_dir_input.setText(str(tmp_path / "out"))

    assert w.run_host_microbe_bigg() == ""
    assert "basis kind, and source are required" in w.host_view.run_status.text()


def test_host_figure_export_copies_selected_svg(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    _app()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "interaction_heatmap.svg").write_text("<svg>heatmap</svg>")
    target = tmp_path / "export.svg"
    w = build_main_window()
    # Round-5 P2: the export is keyed to the run the Host tab is *displaying*, not to a
    # window-level pointer that a failed load could have advanced past it.
    w.host_view.current_run_dir = run_dir
    w.current_host_microbe_dir = run_dir
    w.host_view.figure_mode_combo.setCurrentText("Heatmap")
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(target), "SVG (*.svg)"),
    )
    w._export_host_figure()
    assert target.read_text() == "<svg>heatmap</svg>"
    assert "Exported figure" in w.host_view.run_status.text()


def test_community_solve_button_requires_model_folder():
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    jid = w.run_community_solve()
    assert jid == ""
    assert "model folder" in w.community_builder.status.text().lower()
    runner.shutdown()


def test_community_solve_button_writes_taxonomy_and_overrides_abundance(monkeypatch, tmp_path):
    import csv
    import json

    import cmig.cli.main

    pool_dir = tmp_path / "pool"
    pool_dir.mkdir()
    (pool_dir / "iML1515.xml").write_text("<sbml/>")
    (pool_dir / "iHN637.xml").write_text("<sbml/>")

    seen = {"argv": []}

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
    w.community_builder.model_dir_input.setText(str(pool_dir))
    # Round-5 P2: `cmig solve` refuses to run without an explicit namespace decision, and the
    # GUI now mirrors that gate instead of always failing at rc=2. The GUI must never supply
    # the confirmation on the user's behalf, so the test confirms it explicitly.
    w.community_builder.assume_bigg_check.setChecked(True)
    w.community_builder.add_member("iML1515", 0.75)
    w.community_builder.f_slider.setValue(30)
    jid = w.run_community_solve()
    runner.result(jid, timeout=5)
    w._poll_completed_jobs()
    assert seen["argv"][0] == "solve"
    assert "--assume-bigg-namespace" in seen["argv"]
    assert seen["argv"][seen["argv"].index("--tradeoff-f") + 1] == "0.3"
    tax_path = Path(seen["argv"][seen["argv"].index("--taxonomy") + 1])
    assert tax_path.exists()
    rows = {r["id"]: r for r in csv.DictReader(tax_path.open())}
    assert rows["iML1515"]["abundance"] == "0.75"  # overridden from the member table
    assert rows["iHN637"]["abundance"] == "1.0"  # untouched discovered default
    assert "run_hash" in w.community_builder.status.text()
    assert w.community_builder.run_btn.isEnabled()
    runner.shutdown()


def test_sweep_fixture_button_launches_and_loads_result_matrix(monkeypatch, tmp_path):
    import json

    import pyarrow as pa
    import pyarrow.parquet as pq

    import cmig.cli.main

    seen = {"argv": []}

    def fake_main(argv):
        seen["argv"] = list(argv)
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        table = pa.table(
            {
                "schema_version": ["1.0", "1.0"],
                "condition_id": ["cond-0", "cond-1"],
                "axis_medium_variant": [None, None],
                "axis_abundance": [None, None],
                "axis_member_set": [None, None],
                "axis_bounds": [None, None],
                "axis_tradeoff_f": [0.3, 0.5],
                "axis_solver": ["gurobi", "gurobi"],
                "metric": ["growth", "growth"],
                "value": [0.41, 0.52],
                "run_hash": ["h0", "h1"],
                "status": ["ok", "ok"],
                "diagnostic": [None, None],
                "cache_hit": [False, True],
            }
        )
        pq.write_table(table, out / "sweep.parquet")
        (out / "sweep_summary.json").write_text(json.dumps({"status": "ok", "n_runs": 2}))
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    w.sweep_view.tradeoff_fs_input.setText("0.3,0.5")
    jid = w.run_sweep_fixture()
    runner.result(jid, timeout=5)
    w._poll_completed_jobs()
    assert seen["argv"][0] == "sweep-fixture"
    assert seen["argv"][seen["argv"].index("--tradeoff-fs") + 1] == "0.3,0.5"
    assert w.sweep_view.table.rowCount() == 2
    assert w.sweep_view.table.item(0, 3).text() == "miss"
    assert w.sweep_view.table.item(1, 3).text() == "hit"  # cache_hit column surfaced
    assert w.sweep_view.run_btn.isEnabled()
    runner.shutdown()


def test_medium_growth_check_requires_model():
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    jid = w.run_medium_growth_check()
    assert jid == ""
    assert "model" in w.medium_editor.growth_label.text().lower()
    runner.shutdown()


def test_medium_growth_check_invalid_uptake_shows_status_not_exception(tmp_path):
    """argparse SystemExit isn't the risk here — a raw to_spec() ValueError must not escape
    the slot either; the guard must show a status message instead (no crash)."""
    _app()
    w = build_main_window()
    model_path = tmp_path / "model.xml"
    model_path.write_text("<sbml/>")
    w.medium_editor.model_path_input.setText(str(model_path))
    w.medium_editor.add_row("EX_glc__D_e", 0.0)
    w.medium_editor.table.item(0, 1).setText("not_a_number")
    jid = w.run_medium_growth_check()
    assert jid == ""
    assert "Invalid" in w.medium_editor.status.text()


def test_medium_growth_check_button_uses_strain_growth_command(monkeypatch, tmp_path):
    import json

    import cmig.cli.main

    model_path = tmp_path / "model.xml"
    model_path.write_text("<sbml/>")
    seen = {"argv": []}

    def fake_main(argv):
        seen["argv"] = list(argv)
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        payload = {
            "status": "optimal",
            "members": [
                {
                    "member": "model",
                    "single_growth": 0.87,
                    "single_status": "optimal",
                    "community_member_growth": 0.87,
                    "community_growth": 0.87,
                    "community_status": "optimal",
                }
            ],
        }
        (out / "strain_growth_summary.json").write_text(json.dumps(payload))
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    w.medium_editor.model_path_input.setText(str(model_path))
    w.medium_editor.add_row("EX_glc__D_e", 10.0)
    jid = w.run_medium_growth_check()
    runner.result(jid, timeout=5)
    w._poll_completed_jobs()
    assert seen["argv"][0] == "strain-growth"
    assert "--medium" in seen["argv"]
    assert "0.87" in w.medium_editor.growth_label.text()
    assert w.medium_editor.check_growth_btn.isEnabled()
    runner.shutdown()


def test_scenario_compare_requires_both_run_dirs():
    _app()
    w = build_main_window()
    w.run_scenario_compare()
    assert "select both" in w.scenario_compare.status.text().lower()
    assert w.scenario_compare.delta_view.rowCount() == 0


def test_scenario_compare_button_computes_real_delta(tmp_path):
    from cmig.core.engine import SolveResult
    from cmig.core.interactions import build_tidy

    baseline = SolveResult(
        objective=0.5,
        member_growth={"A": 0.5},
        abundances={"A": 1.0},
        external_exchange={"ac": 5.0},
        member_exchange={"A": {"ac": 5.0}},
        status="optimal",
        flux_report_status="full",
        growth_solver="gurobi",
        flux_solver="gurobi",
        members=["A"],
    )
    modified = SolveResult(
        objective=0.8,
        member_growth={"A": 0.8},
        abundances={"A": 1.0},
        external_exchange={"ac": 2.0},
        member_exchange={"A": {"ac": 2.0}},
        status="optimal",
        flux_report_status="full",
        growth_solver="gurobi",
        flux_solver="gurobi",
        members=["A"],
    )
    dir_a, dir_b = tmp_path / "run_a", tmp_path / "run_b"
    build_tidy(baseline).write(dir_a)
    build_tidy(modified).write(dir_b)
    _app()
    w = build_main_window()
    w.scenario_compare.run_a_input.setText(str(dir_a))
    w.scenario_compare.run_b_input.setText(str(dir_b))
    w.run_scenario_compare()
    assert w.scenario_compare.delta_view.rowCount() == 1
    assert "+0.3" in w.scenario_compare.growth_label.text()
    assert "compare complete" in w.scenario_compare.status.text()


def test_jobrunner_qt_bridge_reflects_job():
    """SC-AP4: JobRunner→Qt bridge 가 실 job 상태 표시(orphan UI 아님)."""
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    jid = w.submit_job("calc", lambda ctx: 21 * 2)
    runner.result(jid, timeout=5)  # 완료 대기
    w.bridge.refresh()
    assert w.jobs_panel.rowCount() == 1
    assert w.jobs_panel.item(0, 0).text() == jid
    assert w.jobs_panel.item(0, 2).text() == JobStatus.DONE.value
    runner.shutdown()


def test_cancel_selected_job_requests_jobrunner_cancel():
    import threading
    import time

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
    started.wait(timeout=2)
    w.bridge.refresh()
    w.jobs_panel.selectRow(0)
    w._cancel_selected_job()
    with pytest.raises(JobCancelled):
        runner.result(jid, timeout=5)
    assert runner.poll(jid).status is JobStatus.CANCELLED
    runner.shutdown()


def test_set_central_widget():
    """SC-AP5: 중앙 위젯 교체(그래프 뷰 도킹 지점)."""
    from PySide6.QtWidgets import QLabel

    _app()
    w = build_main_window()
    label = QLabel("graph")
    w.set_central(label)
    assert w.central_stack.currentWidget() is label


def test_status_bar():
    """SC-AP6: 상태바 준비 메시지."""
    _app()
    w = build_main_window()
    assert w.statusBar().currentMessage() == "Ready"
