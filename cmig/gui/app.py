"""CMIG App Shell — PySide6 3-pane 데스크톱 셸 (Roadmap Phase 0.3, §11).

Design Ref: §11 (Project Explorer·Runtime&Jobs·셸) / cmig-app-shell.design. Plan SC: SC-AP1~AP6.

QMainWindow 3-pane(ProjectExplorer | 중앙 | Runtime&Jobs) + JobRunner→Qt bridge(jobs_bridge) +
i18n(한/영) + 상태바. service(Qt 비의존) 소비. offscreen 실행 검증(QT_QPA_PLATFORM=offscreen) —
*실행 증거*지 human 시각 QA(G-7b) 아님(별도, 정직 표기).

[정직성] 본 셸은 service facade/JobRunner 를 실제로 소비(orphan UI 아님): RuntimeJobsPanel 이
JobRunner.poll 로 실 job 상태를 표시.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cmig.service import JobRunner

I18N: dict[str, dict[str, str]] = {
    "ko": {
        "title": "CMIG — 군집 대사 상호작용", "explorer": "프로젝트 탐색기",
        "models": "모델", "scenarios": "시나리오", "runs": "실행 기록",
        "jobs": "런타임 & 작업", "welcome": "프로젝트를 열거나 모델을 import 하세요.",
        "col_job": "작업", "col_kind": "종류", "col_status": "상태", "col_progress": "진행률",
        "ready": "준비됨",
    },
    "en": {
        "title": "CMIG — Community Metabolic Interaction", "explorer": "Project Explorer",
        "models": "Models", "scenarios": "Scenarios", "runs": "Runs",
        "jobs": "Runtime & Jobs", "welcome": "Open a project or import a model.",
        "col_job": "Job", "col_kind": "Kind", "col_status": "Status", "col_progress": "Progress",
        "ready": "Ready",
    },
}


class ProjectExplorer(QTreeWidget):
    """좌측 프로젝트 트리(모델·시나리오·실행)."""

    def __init__(self, tr: dict[str, str]) -> None:
        super().__init__()
        self.setHeaderLabel(tr["explorer"])
        self._roots: dict[str, QTreeWidgetItem] = {}
        for key in ("models", "scenarios", "runs"):
            item = QTreeWidgetItem([tr[key]])
            self.addTopLevelItem(item)
            self._roots[key] = item

    def add_model(self, label: str) -> None:
        self._roots["models"].addChild(QTreeWidgetItem([label]))


class RuntimeJobsPanel(QTableWidget):
    """우측 런타임&작업 패널 — JobRunner job 상태 표시(실 소비)."""

    def __init__(self, tr: dict[str, str]) -> None:
        super().__init__(0, 4)
        self.setHorizontalHeaderLabels(
            [tr["col_job"], tr["col_kind"], tr["col_status"], tr["col_progress"]])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def refresh(self, runner: JobRunner, job_ids: list[str]) -> None:
        """JobRunner.poll 로 각 job 의 실제 상태를 표에 반영(orphan 아님)."""
        self.setRowCount(len(job_ids))
        for row, jid in enumerate(job_ids):
            job = runner.poll(jid)
            prog = f"{job.progress[0]}/{job.progress[1]}" if job.progress else "—"
            for col, text in enumerate([job.job_id, job.kind, job.status.value, prog]):
                self.setItem(row, col, QTableWidgetItem(text))


class JobsBridge(QObject):
    """JobRunner(Qt 비의존) → Qt 패널 bridge. QTimer 폴링(GUI 비차단)."""

    def __init__(self, runner: JobRunner, panel: RuntimeJobsPanel, interval_ms: int = 500) -> None:
        super().__init__()
        self._runner = runner
        self._panel = panel
        self._job_ids: list[str] = []
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.refresh)

    def track(self, job_id: str) -> None:
        self._job_ids.append(job_id)
        self.refresh()

    def refresh(self) -> None:
        self._panel.refresh(self._runner, self._job_ids)

    def start(self) -> None:
        self._timer.start()


class CmigMainWindow(QMainWindow):
    """3-pane 메인 윈도우. service(JobRunner) 소비."""

    def __init__(self, runner: JobRunner | None = None, lang: str = "ko") -> None:
        super().__init__()
        self.tr_map = I18N.get(lang, I18N["ko"])
        self.runner = runner if runner is not None else JobRunner(max_workers=2)
        self.setWindowTitle(self.tr_map["title"])

        self.explorer = ProjectExplorer(self.tr_map)
        self.jobs_panel = RuntimeJobsPanel(self.tr_map)
        self.bridge = JobsBridge(self.runner, self.jobs_panel)

        center = QWidget()
        layout = QVBoxLayout(center)
        self.central_stack = QStackedWidget()
        welcome = QLabel(self.tr_map["welcome"])
        welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.central_stack.addWidget(welcome)
        layout.addWidget(self.central_stack)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.explorer)
        splitter.addWidget(center)
        splitter.addWidget(self.jobs_panel)
        splitter.setSizes([200, 600, 250])
        self.setCentralWidget(splitter)
        self.statusBar().showMessage(self.tr_map["ready"])

    def set_central(self, widget: QWidget) -> None:
        """중앙 위젯 교체(예: Interaction Graph Viewer 도킹)."""
        self.central_stack.addWidget(widget)
        self.central_stack.setCurrentWidget(widget)

    def submit_job(self, kind: str, fn: Any) -> str:
        """facade 작업을 JobRunner 로 제출 + bridge 추적(실 소비)."""
        jid = self.runner.submit(kind, fn)
        self.bridge.track(jid)
        return jid


def build_main_window(runner: JobRunner | None = None, lang: str = "ko") -> CmigMainWindow:
    """메인 윈도우 팩토리(offscreen 검증·진입점)."""
    return CmigMainWindow(runner=runner, lang=lang)
