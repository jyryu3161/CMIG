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
    assert w.explorer.topLevelItemCount() == 3        # 모델·시나리오·실행
    assert w.jobs_panel.columnCount() == 4
    assert [w.tabs.tabText(i) for i in range(w.tabs.count())] == [
        "Models", "Search", "Host", "Dynamics", "Profile"
    ]
    assert w.tabs.currentWidget() is w.search_view
    assert w.sweep_view.runner is w.runner
    assert w.search_view is not None
    assert "CMIG" in w.windowTitle()


def test_i18n_ko_en():
    """SC-AP2: GUI surface defaults to English labels."""
    _app()
    ko = build_main_window(lang="ko").tr_map["explorer"]
    en = build_main_window(lang="en").tr_map["explorer"]
    assert ko == "Project Explorer" and en == "Project Explorer"


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
        "Models", "Search", "Host", "Dynamics", "Profile"
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
    (tmp_path / "host_microbe_bigg_summary.json").write_text(json.dumps({
        "host": {
            "status": "optimal",
            "viable": True,
            "objective_value": 12.5,
            "lumen_uptake": {"ac": 1.25},
        },
        "microbe_to_host": {"ac": 1.25},
        "unused_secretion": {},
    }))
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
    (tmp_path / "dfba_summary.json").write_text(json.dumps({
        "status": "completed",
        "final_t": 1.0,
        "final_biomass": 0.02,
        "final_concentrations": {"EX_glc__D_e": 9.5},
    }))
    w = build_main_window()
    assert w.load_dfba_dir(tmp_path) is True
    assert w.tabs.currentWidget() is w.dynamics_view
    assert w.dynamics_view.table.item(0, 0).text() == "dFBA"
    assert "biomass=0.02" in w.dynamics_view.table.item(0, 3).text()


def test_load_spatial_dir_updates_dynamics_tab(tmp_path):
    import json

    _app()
    (tmp_path / "spatial_summary.json").write_text(json.dumps({
        "status": "completed",
        "final_t": 8.0,
        "final_min": 0.0,
        "final_max": 10.0,
    }))
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
        (out / "spatial_summary.json").write_text(json.dumps({
            "status": "completed",
            "final_t": 1.0,
            "final_min": 0.0,
            "final_max": 10.0,
        }))
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
        return ModelSummary(
            "toy", "sbml", str(path), 2, 2, 0, ["EX_ac_e"], ["BIOMASS"])

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
    w = build_main_window()
    w.sandbox_view.add_bound("EX_glc__D_e", -1.0, 1000.0)
    w.sandbox_view.preview_btn.click()
    assert "preview" in w.sandbox_view.status.text()


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
    w.search_view.robustness_check.setChecked(True)
    jid = w.run_search_fixture()
    runner.result(jid, timeout=5)
    w._poll_completed_jobs()
    assert seen["argv"][0] == "search"
    assert seen["argv"][seen["argv"].index("--model-dir") + 1] == str(tmp_path)
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
        (out / "host_microbe_bigg_summary.json").write_text(json.dumps({
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
        }))
        (out / "host_uptake.csv").write_text("metabolite,uptake_flux\nac,1.0\n")
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    w.host_view.host_path_input.setText(str(tmp_path / "Recon3D.xml"))
    w.host_view.model_dir_input.setText(str(tmp_path / "models"))
    w.host_view.out_dir_input.setText(str(tmp_path / "out"))
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
    assert w.tabs.currentWidget() is w.host_view
    assert w.host_view.cross_table.rowCount() == 1
    assert w.host_view.network_payload is not None
    runner.shutdown()


def test_host_figure_export_copies_selected_svg(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    _app()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "interaction_heatmap.svg").write_text("<svg>heatmap</svg>")
    target = tmp_path / "export.svg"
    w = build_main_window()
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


def test_jobrunner_qt_bridge_reflects_job():
    """SC-AP4: JobRunner→Qt bridge 가 실 job 상태 표시(orphan UI 아님)."""
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    jid = w.submit_job("calc", lambda ctx: 21 * 2)
    runner.result(jid, timeout=5)                     # 완료 대기
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
