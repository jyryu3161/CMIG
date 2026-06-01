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
    assert "CMIG" in w.windowTitle()


def test_i18n_ko_en():
    """SC-AP2: i18n — 한/영 타이틀 상이."""
    _app()
    ko = build_main_window(lang="ko").tr_map["explorer"]
    en = build_main_window(lang="en").tr_map["explorer"]
    assert ko == "프로젝트 탐색기" and en == "Project Explorer"


def test_project_explorer_add_model():
    """SC-AP3: ProjectExplorer 모델 추가."""
    _app()
    w = build_main_window()
    w.explorer.add_model("e_coli_core")
    models_root = w.explorer.topLevelItem(0)
    assert models_root.childCount() == 1
    assert models_root.child(0).text(0) == "e_coli_core"


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
    w = build_main_window(lang="en")
    assert w.statusBar().currentMessage() == "Ready"
