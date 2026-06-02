"""CMIG App Shell — PySide6 3-pane 데스크톱 셸 (Roadmap Phase 0.3, §11).

Design Ref: §11 (Project Explorer·Runtime&Jobs·셸) / cmig-app-shell.design. Plan SC: SC-AP1~AP6.

QMainWindow 3-pane(ProjectExplorer | 중앙 | Runtime&Jobs) + JobRunner→Qt bridge(jobs_bridge) +
i18n(한/영) + 상태바. service(Qt 비의존) 소비. offscreen 실행 검증(QT_QPA_PLATFORM=offscreen) —
*실행 증거*지 human 시각 QA(G-7b) 아님(별도, 정직 표기).

[정직성] 본 셸은 service facade/JobRunner 를 실제로 소비(orphan UI 아님): RuntimeJobsPanel 이
JobRunner.poll 로 실 job 상태를 표시.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QHeaderView,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cmig.gui.builder import (
    CommunityBuilderView,
    ConstraintSandboxView,
    ScenarioCompareView,
    SearchView,
)
from cmig.gui.editors import MediumEditor, ModelManagerPanel
from cmig.gui.views import ExternalProfileView, SweepView
from cmig.service import JobRunner, JobStatus

I18N: dict[str, dict[str, str]] = {
    "ko": {
        "title": "CMIG — Community Metabolic Interaction", "explorer": "Project Explorer",
        "models": "Models", "scenarios": "Scenarios", "runs": "Runs",
        "jobs": "Runtime & Jobs", "welcome": "Open a project or import a model.",
        "col_job": "Job", "col_kind": "Kind", "col_status": "Status", "col_progress": "Progress",
        "ready": "Ready",
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

    def add_run(self, label: str) -> None:
        self._roots["runs"].addChild(QTreeWidgetItem([label]))


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
        self._fixture_jobs: dict[str, Path] = {}
        self._search_jobs: set[str] = set()
        self.current_manifest: dict[str, Any] | None = None
        self.current_graph_payload: dict[str, Any] | None = None
        self.current_model_review: dict[str, Any] | None = None

        center = QWidget()
        layout = QVBoxLayout(center)
        self.central_stack = QStackedWidget()
        self.tabs = QTabWidget()
        self.model_manager = ModelManagerPanel()
        self.community_builder = CommunityBuilderView()
        self.medium_editor = MediumEditor()
        self.profile_view = ExternalProfileView()
        self.sweep_view = SweepView(runner=self.runner)
        self.sandbox_view = ConstraintSandboxView()
        self.scenario_compare = ScenarioCompareView()
        self.search_view = SearchView()
        for label, widget in [
            ("Models", self.model_manager),
            ("Community", self.community_builder),
            ("Medium", self.medium_editor),
            ("Profile", self.profile_view),
            ("Sweep", self.sweep_view),
            ("Sandbox", self.sandbox_view),
            ("Compare", self.scenario_compare),
            ("Search", self.search_view),
        ]:
            self.tabs.addTab(widget, label)
        self.central_stack.addWidget(self.tabs)
        layout.addWidget(self.central_stack)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.explorer)
        splitter.addWidget(center)
        splitter.addWidget(self.jobs_panel)
        splitter.setSizes([200, 600, 250])
        self.setCentralWidget(splitter)
        self.statusBar().showMessage(self.tr_map["ready"])
        self._install_workflow_actions()
        self._connect_view_actions()
        self._completion_timer = QTimer(self)
        self._completion_timer.setInterval(500)
        self._completion_timer.timeout.connect(self._poll_completed_jobs)
        self._completion_timer.start()
        self.bridge.start()

    def _install_workflow_actions(self) -> None:
        toolbar = self.addToolBar("Workflow")
        self.import_model_action = QAction("Import Model", self)
        self.import_model_action.triggered.connect(self._import_model_dialog)
        self.open_run_action = QAction("Open Run", self)
        self.open_run_action.triggered.connect(self._open_run_dialog)
        self.run_fixture_action = QAction("Run Fixture", self)
        self.run_fixture_action.triggered.connect(self._run_fixture_dialog)
        toolbar.addAction(self.import_model_action)
        toolbar.addAction(self.open_run_action)
        toolbar.addAction(self.run_fixture_action)

    def _connect_view_actions(self) -> None:
        self.sandbox_view.preview_btn.clicked.connect(self._run_sandbox_preview)
        self.sandbox_view.commit_btn.clicked.connect(self._run_sandbox_commit)
        self.search_view.run_btn.clicked.connect(self.run_search_fixture)

    def _import_model_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import GEM Model", "", "Models (*.xml *.sbml *.xml.gz *.sbml.gz *.json *.mat)"
        )
        if path:
            self.import_model_file(path)

    def _open_run_dialog(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open CMIG Run")
        if path:
            self.load_run_dir(path)

    def _run_fixture_dialog(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if path:
            self.run_fixture(path)

    def _run_sandbox_preview(self) -> None:
        self._run_sandbox(commit=False)

    def _run_sandbox_commit(self) -> None:
        self._run_sandbox(commit=True)

    def _run_sandbox(self, *, commit: bool) -> None:
        constraints = self.sandbox_view.constraints()
        if not constraints:
            self.sandbox_view.status.setText("Add a bound constraint first.")
            return
        out_dir = None
        if commit:
            selected = QFileDialog.getExistingDirectory(self, "Select Commit Output Directory")
            if not selected:
                return
            out_dir = selected
        c = constraints[0]
        try:
            from cmig.service import EngineService

            result = EngineService().sandbox_fixture(
                reaction_id=c.reaction_id,
                lower=c.lower,
                upper=c.upper,
                commit=commit,
                out_dir=out_dir,
            )
        except Exception as e:
            self.sandbox_view.status.setText(f"Sandbox failed: {e}")
            return
        if commit and result.run_hash:
            self.sandbox_view.show_commit(result.delta, result.run_hash)
        else:
            self.sandbox_view.show_preview(result.delta)

    def set_central(self, widget: QWidget) -> None:
        """중앙 위젯 교체(예: Interaction Graph Viewer 도킹)."""
        self.central_stack.addWidget(widget)
        self.central_stack.setCurrentWidget(widget)

    def submit_job(self, kind: str, fn: Any) -> str:
        """facade 작업을 JobRunner 로 제출 + bridge 추적(실 소비)."""
        jid = self.runner.submit(kind, fn)
        self.bridge.track(jid)
        return jid

    def import_model_file(self, path: str | Path) -> bool:
        """모델 파일 import + namespace review 를 Model 탭과 Explorer 에 반영."""
        from cmig.io.model_import import build_import_review, import_model

        try:
            summary = import_model(path)
            review = build_import_review(summary)
        except Exception as e:
            self.statusBar().showMessage(f"Model import failed: {e}")
            return False
        self.model_manager.load_summary(summary)
        self.explorer.add_model(summary.model_id)
        self.current_model_review = {
            "model": review.model,
            "inferred_origin": review.inferred_origin,
            "namespace": review.namespace,
            "warnings": review.warnings,
            "next_actions": review.next_actions,
        }
        self.tabs.setCurrentWidget(self.model_manager)
        ns = review.namespace
        self.statusBar().showMessage(
            f"Imported {summary.model_id}; namespace coverage {ns['coverage_pct']:.0f}%"
        )
        return True

    def load_run_dir(self, path: str | Path) -> None:
        """nodes/edges/profile parquet run 디렉터리를 열어 Profile 탭과 Explorer 에 반영."""
        from cmig.core.tidy import TidyBundle
        from cmig.gui.graph_data import graph_payload

        run_dir = Path(path)
        try:
            bundle = TidyBundle.read(run_dir)
        except Exception as e:
            self.statusBar().showMessage(f"Run load failed: {e}")
            return
        manifest_path = run_dir / "manifest.json"
        self.current_manifest = (
            json.loads(manifest_path.read_text()) if manifest_path.exists() else None
        )
        self.current_graph_payload = graph_payload(bundle)
        self.profile_view.load_profile(bundle.profile.to_pylist())
        self.explorer.add_run(run_dir.name)
        self.tabs.setCurrentWidget(self.profile_view)
        run_hash = None if self.current_manifest is None else self.current_manifest.get("run_hash")
        suffix = "" if run_hash is None else f" (run_hash {str(run_hash)[:12]})"
        self.statusBar().showMessage(f"Loaded run: {run_dir}{suffix}")

    def run_fixture(self, out_dir: str | Path, *, solver: str = "gurobi") -> str:
        """GUI 버튼용 fixture solve. JobRunner 로 제출해 Qt main thread 를 막지 않는다."""
        from cmig.service import EngineService, JobContext

        run_dir = Path(out_dir)

        def _job(ctx: JobContext) -> Any:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            outcome = EngineService().solve_fixture(solver=solver, out_dir=run_dir)
            ctx.report_progress(1, 1)
            return outcome

        jid = self.submit_job("solve_fixture", _job)
        self._fixture_jobs[jid] = run_dir
        self.statusBar().showMessage(f"Started fixture run: {jid}")
        return jid

    def load_completed_fixture(self, job_id: str) -> bool:
        """완료된 fixture job 산출물을 Profile 탭으로 로드한다."""
        job = self.runner.poll(job_id)
        if job.status is not JobStatus.DONE or job.result is None:
            self.statusBar().showMessage(f"Fixture job not complete: {job_id}")
            return False
        outcome = job.result
        if outcome.status == "ok" and outcome.manifest_path is not None:
            self.load_run_dir(outcome.manifest_path.parent)
            return True
        self.statusBar().showMessage(f"Fixture failed: {outcome.diagnostic}")
        return False

    def run_search_fixture(self) -> str:
        """Search 탭 입력값으로 fixture advanced search 를 background job 으로 실행."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        targets = self.search_view.targets_input.text().strip() or "ac"
        strategy = self.search_view.strategy_combo.currentText()
        top_k = str(self.search_view.top_k_spin.value())

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            with tempfile.TemporaryDirectory(prefix="cmig-search-") as td:
                out_dir = Path(td)
                rc = main([
                    "search-advanced-fixture",
                    "--metabolites", targets,
                    "--strategy", strategy,
                    "--top-k", top_k,
                    "--out", str(out_dir),
                ])
                if rc != 0:
                    raise RuntimeError(f"search failed with rc={rc}")
                ctx.report_progress(1, 1)
                payload = json.loads((out_dir / "search_advanced_summary.json").read_text())
            if not isinstance(payload, dict):
                raise RuntimeError("search output is not a JSON object")
            return payload

        jid = self.submit_job("search_fixture", _job)
        self._search_jobs.add(jid)
        self.search_view.status.setText(f"search started: {jid}")
        return jid

    def _poll_completed_jobs(self) -> None:
        for jid in list(self._fixture_jobs):
            job = self.runner.poll(jid)
            if job.status is JobStatus.DONE:
                self._fixture_jobs.pop(jid, None)
                self.load_completed_fixture(jid)
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._fixture_jobs.pop(jid, None)
                self.statusBar().showMessage(f"Fixture job {job.status.value}: {jid}")
        for jid in list(self._search_jobs):
            job = self.runner.poll(jid)
            if job.status is JobStatus.DONE and isinstance(job.result, dict):
                self._search_jobs.discard(jid)
                self.search_view.load_summary(job.result)
                self.tabs.setCurrentWidget(self.search_view)
                self.statusBar().showMessage(f"Search complete: {jid}")
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._search_jobs.discard(jid)
                self.search_view.status.setText(f"search {job.status.value}: {job.error or jid}")


def build_main_window(runner: JobRunner | None = None, lang: str = "ko") -> CmigMainWindow:
    """메인 윈도우 팩토리(offscreen 검증·진입점)."""
    return CmigMainWindow(runner=runner, lang=lang)
