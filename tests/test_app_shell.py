"""Phase 0.3 — App Shell offscreen 실행 검증. Plan SC: SC-AP1~AP6.

QT_QPA_PLATFORM=offscreen(conftest)에서 PySide6 셸을 *실제로* 생성·소비. JobRunner→Qt bridge 가
실 job 상태를 표시하는지 검증. offscreen = 실행 증거지 human 시각 QA(G-7b) 아님(정직).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import CmigMainWindow, build_main_window  # noqa: E402
from cmig.service import JobRunner, JobStatus  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_shell_constructs_offscreen():
    """SC-AP1: 3-pane 셸 offscreen 생성(예외 없음) + 패널 존재."""
    _app()
    w = build_main_window(lang="ko")
    assert isinstance(w, CmigMainWindow)
    assert w.explorer.topLevelItemCount() == 3        # 모델·시나리오·실행
    assert w.jobs_panel.columnCount() == 4
    assert w.tabs.count() >= 7
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


def test_search_button_runs_job_and_loads_summary(monkeypatch):
    import json

    import cmig.cli.main

    def fake_main(argv):
        out = argv[argv.index("--out") + 1]
        payload = {
            "strategy": "exhaustive",
            "top_ranked": {
                "ac": [{"members": ["A", "B"], "score": 1.0, "target_flux": 1.0}]
            },
            "pareto_frontier": [],
            "warnings": [],
        }
        from pathlib import Path
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / "search_advanced_summary.json").write_text(json.dumps(payload))
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    jid = w.run_search_fixture()
    runner.result(jid, timeout=5)
    w._poll_completed_jobs()
    assert w.search_view.table.rowCount() == 1
    assert w.tabs.currentWidget() is w.search_view
    runner.shutdown()


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
