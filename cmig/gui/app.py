"""CMIG App Shell — PySide6 3-pane 데스크톱 셸 (Roadmap Phase 0.3, §11).

Design Ref: §11 (Project Explorer·Runtime&Jobs·셸) / cmig-app-shell.design. Plan SC: SC-AP1~AP6.

QMainWindow 3-pane(ProjectExplorer | 중앙 | Runtime&Jobs) + JobRunner→Qt bridge(jobs_bridge) +
i18n(한/영) + 상태바. service(Qt 비의존) 소비. offscreen 실행 검증(QT_QPA_PLATFORM=offscreen) —
*실행 증거*지 human 시각 QA(G-7b) 아님(별도, 정직 표기).

[정직성] 본 셸은 service facade/JobRunner 를 실제로 소비(orphan UI 아님): RuntimeJobsPanel 이
JobRunner.poll 로 실 job 상태를 표시.
"""

from __future__ import annotations

import csv
import json
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from PySide6.QtCore import QObject, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QHeaderView,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QTableWidget,
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
    make_read_only,
    read_only_item,
)
from cmig.gui.editors import MediumEditor, ModelManagerPanel
from cmig.gui.host_view import HostImpactView
from cmig.gui.views import DfbaSpatialView, ExternalProfileView, SweepView
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


def _single_target(text: str) -> tuple[str, str]:
    """Parse the Target box into (target, error_message) without ever substituting a default.

    The box used to mean two different metabolites depending on which button was pressed
    ("but" for Run Search, "ac" for Rank Gene KOs) and silently truncated `ac,but` to `ac`.
    A scientific request is never guessed here: an empty or multi-valued box is refused.
    """
    raw = text.strip()
    if not raw:
        return "", (
            "Enter the target metabolite (e.g. but or ac). "
            "CMIG does not substitute a default target."
        )
    if "," in raw:
        return "", (
            "Multi-target search is CLI-only (`cmig search --targets ac,but`). "
            "Enter a single metabolite here."
        )
    return raw, ""


def _finish_after_artifacts(ctx: Any) -> None:
    """Mark a GUI job complete once its artifacts have been committed to disk.

    Deliberately does NOT re-check cancellation. By this point `main(argv)` (or
    `solve_fixture`) has already written `manifest.json`, the CSVs and the figures. Raising
    `JobCancelled` here made `JobRunner` drop the outcome and record `cancelled` while a
    complete, valid run directory sat on disk — a durable contradiction, and a silent loss
    of a multi-minute solve the user can never get back. A cancel that arrives after the
    work is finished is reported as finished; the pre-run check still short-circuits a job
    that has not started.
    """
    ctx.report_progress(1, 1)


def _search_temp_root() -> Path:
    """Return an OS-managed temp root for GUI search outputs."""
    candidates: list[Path] = []
    qt_temp = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation)
    if qt_temp:
        candidates.append(Path(qt_temp))
    candidates.append(Path(tempfile.gettempdir()))

    last_error: OSError | None = None
    for base in candidates:
        root = base / "cmig"
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            last_error = exc
            continue
        return root
    raise RuntimeError("Unable to create CMIG search temp directory") from last_error


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

    def add_run(self, label: str, path: str | Path | None = None) -> None:
        root = self._roots["runs"]
        path_text = None if path is None else str(path)
        for i in range(root.childCount()):
            child = root.child(i)
            if path_text is not None and child.data(0, Qt.ItemDataRole.UserRole) == path_text:
                child.setText(0, label)
                return
            if path_text is None and child.text(0) == label:
                return
        item = QTreeWidgetItem([label])
        if path is not None:
            item.setData(0, Qt.ItemDataRole.UserRole, str(path))
        root.addChild(item)


class RuntimeJobsPanel(QTableWidget):
    """우측 런타임&작업 패널 — JobRunner job 상태 표시(실 소비)."""

    def __init__(self, tr: dict[str, str]) -> None:
        super().__init__(0, 4)
        self.setHorizontalHeaderLabels(
            [tr["col_job"], tr["col_kind"], tr["col_status"], tr["col_progress"]])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        make_read_only(self)

    def refresh(
        self,
        runner: JobRunner,
        job_ids: list[str],
        cancelling: frozenset[str] | set[str] = frozenset(),
    ) -> None:
        """JobRunner.poll 로 각 job 의 실제 상태를 표에 반영(orphan 아님).

        A job whose cancel has been *requested* but which is still inside a non-interruptible
        solver call is shown as `cancelling (solver still running)` rather than plain
        `running` — the previous label made the cancel look like it had done nothing.
        """
        self.setRowCount(len(job_ids))
        for row, jid in enumerate(job_ids):
            job = runner.poll(jid)
            # GUI jobs only check cancellation at run boundaries, so an in-flight MICOM/Gurobi
            # call keeps burning CPU after cancel(); say so instead of implying it stopped.
            progress = (
                f"{job.progress[0]}/{job.progress[1]}"
                if job.progress and job.progress[1] > 1
                # 0/1 → 1/1 is a two-state placeholder, not measured progress.
                else "—"
            )
            status = job.status.value
            if jid in cancelling and job.status in (JobStatus.PENDING, JobStatus.RUNNING):
                status = "cancelling (solver still running)"
            for col, text in enumerate([job.job_id, job.kind, status, progress]):
                self.setItem(row, col, read_only_item(text))

    def selected_job_id(self) -> str | None:
        row = self.currentRow()
        if row < 0:
            return None
        item = self.item(row, 0)
        return None if item is None else item.text()


class JobsBridge(QObject):
    """JobRunner(Qt 비의존) → Qt 패널 bridge. QTimer 폴링(GUI 비차단)."""

    def __init__(self, runner: JobRunner, panel: RuntimeJobsPanel, interval_ms: int = 500) -> None:
        super().__init__()
        self._runner = runner
        self._panel = panel
        self._job_ids: list[str] = []
        #: jobs for which the user pressed Cancel; the request is cooperative, so a job stays
        #: here until it actually reaches a terminal state.
        self.cancelling: set[str] = set()
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.refresh)

    def track(self, job_id: str) -> None:
        self._job_ids.append(job_id)
        self.refresh()

    def refresh(self) -> None:
        self._panel.refresh(self._runner, self._job_ids, frozenset(self.cancelling))

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()


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
        # Each Search-tab map holds (out_dir, the answer-determining inputs at submit time)
        # so an arriving result can say which request it belongs to.
        self._search_jobs: dict[str, tuple[Path, dict[str, str]]] = {}
        self._host_microbe_jobs: dict[str, Path] = {}
        self._host_search_jobs: dict[str, tuple[Path, dict[str, str]]] = {}
        self._gene_ko_jobs: dict[str, tuple[Path, dict[str, str]]] = {}
        self._strain_growth_jobs: dict[str, tuple[Path, dict[str, str]]] = {}
        self._abundance_impact_jobs: dict[str, tuple[Path, dict[str, str]]] = {}
        self._dfba_jobs: dict[str, Path] = {}
        self._spatial_jobs: dict[str, Path] = {}
        self._community_jobs: dict[str, Path] = {}
        self._sweep_fixture_jobs: dict[str, Path] = {}
        self._medium_growth_jobs: dict[str, Path] = {}
        #: sandbox job id -> (commit?, the bound constraint the result will belong to)
        self._sandbox_jobs: dict[str, tuple[bool, Any]] = {}
        self.current_manifest: dict[str, Any] | None = None
        self.current_graph_payload: dict[str, Any] | None = None
        self.current_model_review: dict[str, Any] | None = None
        self.current_search_dir: Path | None = None
        self.current_host_microbe_dir: Path | None = None

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
        self.host_view = HostImpactView()
        self.dynamics_view = DfbaSpatialView()
        self._primary_tabs = [
            ("Models", self.model_manager),
            ("Search", self.search_view),
            ("Host", self.host_view),
            ("Dynamics", self.dynamics_view),
            ("Profile", self.profile_view),
        ]
        self._advanced_tabs = [
            ("Community", self.community_builder),
            ("Medium", self.medium_editor),
            ("Sweep", self.sweep_view),
            ("Sandbox", self.sandbox_view),
            ("Compare", self.scenario_compare),
        ]
        self._advanced_tabs_visible = False
        for label, widget in self._primary_tabs:
            self.tabs.addTab(widget, label)
        self.tabs.setCurrentWidget(self.search_view)
        self.central_stack.addWidget(self.tabs)
        layout.addWidget(self.central_stack)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        # Without minimum widths the centre widget's size hint squeezed both side panes to
        # 90 px at the shipped 1500x950 default, making Runtime & Jobs unreadable — and it is
        # the only surface from which a job can be selected and cancelled.
        self.explorer.setMinimumWidth(180)
        self.jobs_panel.setMinimumWidth(260)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.explorer)
        splitter.addWidget(center)
        splitter.addWidget(self.jobs_panel)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([200, 600, 250])
        self.setCentralWidget(splitter)
        self.statusBar().showMessage(self.tr_map["ready"])
        self._install_workflow_actions()
        self._connect_view_actions()
        self.explorer.itemDoubleClicked.connect(self._open_explorer_item)
        self._completion_timer = QTimer(self)
        self._completion_timer.setInterval(500)
        self._completion_timer.timeout.connect(self._poll_completed_jobs)
        self._completion_timer.start()
        self.bridge.start()

    def closeEvent(self, event: Any) -> None:
        """Stop the GUI's timers and the job pool so closing the window ends the session.

        The window used to vanish while non-daemon executor threads kept a Gurobi licence
        seat and >1 GB RSS with no UI left to observe or stop them. Cancellation is
        cooperative, so an in-flight solver call still runs to its next checkpoint — queued
        jobs, however, are cancelled outright and never start.
        """
        self._completion_timer.stop()
        self.bridge.stop()
        for jid in list(self.bridge._job_ids):
            if self.runner.poll(jid).status in (JobStatus.PENDING, JobStatus.RUNNING):
                self.runner.cancel(jid)
        self.runner.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)

    def _install_workflow_actions(self) -> None:
        toolbar = self.addToolBar("Workflow")
        self.import_model_action = QAction("Import Model", self)
        self.import_model_action.triggered.connect(self._import_model_dialog)
        self.import_model_action.setShortcut(QKeySequence("Ctrl+I"))
        self.open_run_action = QAction("Open Run", self)
        self.open_run_action.triggered.connect(self._open_run_dialog)
        self.open_run_action.setShortcut(QKeySequence.StandardKey.Open)
        self.run_fixture_action = QAction("Run Fixture", self)
        self.run_fixture_action.triggered.connect(self._run_fixture_dialog)
        self.run_fixture_action.setShortcut(QKeySequence("Ctrl+R"))
        self.cancel_job_action = QAction("Cancel Selected Job", self)
        self.cancel_job_action.triggered.connect(self._cancel_selected_job)
        self.cancel_job_action.setShortcut(QKeySequence("Ctrl+."))
        self.advanced_tools_action = QAction("Show Advanced Tools", self)
        self.advanced_tools_action.setCheckable(True)
        self.advanced_tools_action.toggled.connect(self._set_advanced_tabs_visible)
        toolbar.addAction(self.import_model_action)
        toolbar.addAction(self.open_run_action)
        toolbar.addAction(self.run_fixture_action)
        toolbar.addAction(self.cancel_job_action)
        toolbar.addAction(self.advanced_tools_action)

    def _set_advanced_tabs_visible(self, visible: bool) -> None:
        """Show or hide advanced/preview tools so the default workflow stays focused."""
        if visible == self._advanced_tabs_visible:
            return
        self._advanced_tabs_visible = visible
        self.advanced_tools_action.setText(
            "Hide Advanced Tools" if visible else "Show Advanced Tools"
        )
        if visible:
            for label, widget in self._advanced_tabs:
                if self.tabs.indexOf(widget) == -1:
                    self.tabs.addTab(widget, label)
            return
        for _label, widget in self._advanced_tabs:
            idx = self.tabs.indexOf(widget)
            if idx != -1:
                self.tabs.removeTab(idx)

    def _connect_view_actions(self) -> None:
        self.sandbox_view.preview_btn.clicked.connect(self._run_sandbox_preview)
        self.sandbox_view.commit_btn.clicked.connect(self._run_sandbox_commit)
        self.search_view.browse_pool_btn.clicked.connect(self._browse_search_model_dir)
        self.search_view.run_btn.clicked.connect(self.run_search_fixture)
        self.search_view.run_ko_btn.clicked.connect(self.run_gene_ko_search)
        self.search_view.run_growth_btn.clicked.connect(self.run_strain_growth_report)
        self.search_view.run_abundance_btn.clicked.connect(self.run_abundance_impact)
        self.search_view.export_figure_btn.clicked.connect(self._export_search_figure)
        self.host_view.browse_host_btn.clicked.connect(self._browse_host_model)
        self.host_view.browse_model_dir_btn.clicked.connect(self._browse_host_microbe_model_dir)
        self.host_view.browse_host_medium_btn.clicked.connect(self._browse_host_medium)
        self.host_view.browse_microbe_medium_btn.clicked.connect(self._browse_microbe_medium)
        self.host_view.browse_out_dir_btn.clicked.connect(self._browse_host_microbe_out_dir)
        self.host_view.run_btn.clicked.connect(self.run_host_microbe_bigg)
        self.host_view.run_search_btn.clicked.connect(self.run_host_search_bigg)
        self.host_view.export_figure_btn.clicked.connect(self._export_host_figure)
        self.dynamics_view.browse_model_btn.clicked.connect(self.dynamics_view.browse_model)
        self.dynamics_view.browse_out_btn.clicked.connect(self.dynamics_view.browse_out)
        self.dynamics_view.run_dfba_btn.clicked.connect(self.run_dfba)
        self.dynamics_view.run_spatial_btn.clicked.connect(self.run_spatial_preview)
        self.community_builder.browse_model_dir_btn.clicked.connect(
            self._browse_community_model_dir
        )
        self.community_builder.run_btn.clicked.connect(self.run_community_solve)
        self.sweep_view.run_btn.clicked.connect(self.run_sweep_fixture)
        self.medium_editor.browse_model_btn.clicked.connect(self._browse_medium_model)
        self.medium_editor.check_growth_btn.clicked.connect(self.run_medium_growth_check)
        self.scenario_compare.browse_a_btn.clicked.connect(self._browse_scenario_run_a)
        self.scenario_compare.browse_b_btn.clicked.connect(self._browse_scenario_run_b)
        self.scenario_compare.compare_btn.clicked.connect(self.run_scenario_compare)

    def _cancel_selected_job(self) -> None:
        job_id = self.jobs_panel.selected_job_id()
        if not job_id:
            self.statusBar().showMessage("Select a running job to cancel.")
            return
        job = self.runner.poll(job_id)
        if job.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
            self.statusBar().showMessage(f"Job already {job.status.value}: {job_id}")
            return
        self.runner.cancel(job_id)
        self.bridge.cancelling.add(job_id)
        self.bridge.refresh()
        # Cancellation is cooperative and GUI jobs only check it at run boundaries, so saying
        # just "Cancel requested" let the user believe the solve had stopped when it had not.
        self.statusBar().showMessage(
            f"Cancel requested for {job_id}. The solver cannot be interrupted mid-solve — "
            f"this run keeps using CPU until it reaches its next checkpoint. If it has "
            f"already written its artifacts it will still be reported as complete."
        )

    def _open_explorer_item(self, item: QTreeWidgetItem, _column: int) -> None:
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if not path:
            return
        self.load_run_dir(str(path))

    def _browse_search_model_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Model Pool Folder")
        if path:
            self.search_view.model_dir_input.setText(path)

    def _browse_host_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Host Model", "", "Models (*.xml *.sbml *.xml.gz *.sbml.gz)"
        )
        if path:
            self.host_view.host_path_input.setText(path)

    def _browse_host_microbe_model_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Microbial Model Folder")
        if path:
            self.host_view.model_dir_input.setText(path)

    def _browse_host_medium(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Host Medium", "", "Medium (*.csv *.json);;All Files (*)"
        )
        if path:
            self.host_view.host_medium_input.setText(path)

    def _browse_microbe_medium(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Microbe Medium", "", "Medium (*.csv *.json);;All Files (*)"
        )
        if path:
            self.host_view.microbe_medium_input.setText(path)

    def _browse_host_microbe_out_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Host-Microbe Output Folder")
        if path:
            self.host_view.out_dir_input.setText(path)

    def _browse_community_model_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Community Model Folder")
        if path:
            self.community_builder.model_dir_input.setText(path)

    def _browse_medium_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Model for Growth Check", "", "Models (*.xml *.sbml *.xml.gz *.sbml.gz)"
        )
        if path:
            self.medium_editor.model_path_input.setText(path)

    def _browse_scenario_run_a(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Run A Directory")
        if path:
            self.scenario_compare.run_a_input.setText(path)

    def _browse_scenario_run_b(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Run B Directory")
        if path:
            self.scenario_compare.run_b_input.setText(path)

    def _export_host_figure(self) -> None:
        # Key the export to the run the tables are actually *displaying*. The window-level
        # pointer used to advance on a failed load, so Export Figure could write run B's SVG
        # while every number on screen still belonged to run A.
        run_dir = self.host_view.current_run_dir
        if run_dir is None:
            self.host_view.run_status.setText("No host-microbe result is loaded.")
            return
        artifact = self.host_view.selected_figure_artifact()
        src = run_dir / artifact
        if not src.exists():
            self.host_view.run_status.setText(f"Figure artifact not found: {artifact}")
            return
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Export Host-Microbe Figure",
            artifact,
            "SVG (*.svg);;All Files (*)",
        )
        if not target:
            return
        shutil.copyfile(src, target)
        self.host_view.run_status.setText(f"Exported figure: {target}")

    def _export_search_figure(self) -> None:
        # Same rule as the Host tab: export the run the table is displaying, and nothing else.
        # There is deliberately NO fallback to `current_search_dir`: invalidation clears
        # `current_run_dir` and tells the user the result was discarded, and a fallback would
        # then still export that discarded run and report success (verifier V-1).
        run_dir = self.search_view.current_run_dir
        if run_dir is None:
            self.search_view.status.setText("No search result is loaded.")
            return
        artifact = self.search_view.selected_figure_artifact()
        src = run_dir / artifact
        if not src.exists():
            self.search_view.status.setText(f"Search figure artifact not found: {artifact}")
            return
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Export Search Figure",
            artifact,
            "SVG (*.svg);;All Files (*)",
        )
        if not target:
            return
        shutil.copyfile(src, target)
        self.search_view.status.setText(f"Exported figure: {target}")

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

    def _run_sandbox(self, *, commit: bool) -> str:
        """Submit the sandbox baseline+constrained solve through JobRunner.

        This slot used to call `EngineService().sandbox_fixture()` directly — 2190 ms of a
        completely frozen event loop on the 3-member golden fixture, auto-fired 500 ms after
        any table edit. It is the only solve view that bypassed JobRunner; now it does not.
        """
        from cmig.service import JobContext

        constraints = self.sandbox_view.constraints()
        if self.sandbox_view.invalid_rows:
            rows = ", ".join(str(r) for r in self.sandbox_view.invalid_rows)
            self.sandbox_view.delta_view.setRowCount(0)
            self.sandbox_view.status.setText(
                f"row {rows}: bound is not a number — fix it before previewing."
            )
            return ""
        if not constraints:
            self.sandbox_view.status.setText("Add a bound constraint first.")
            return ""
        if len(constraints) > 1:
            self.sandbox_view.status.setText(
                "Sandbox fixture supports one bound at a time; "
                "remove extra rows before preview or commit."
            )
            return ""
        out_dir = None
        if commit:
            selected = QFileDialog.getExistingDirectory(self, "Select Commit Output Directory")
            if not selected:
                return ""
            out_dir = selected
        # Snapshot the request in the GUI thread; the worker must never read a QWidget.
        c = constraints[0]
        reaction_id, lower, upper = c.reaction_id, c.lower, c.upper

        def _job(ctx: JobContext) -> Any:
            from cmig.service import EngineService

            ctx.raise_if_cancelled()
            return EngineService().sandbox_fixture(
                reaction_id=reaction_id,
                lower=lower,
                upper=upper,
                commit=commit,
                out_dir=out_dir,
            )

        jid = self.submit_job("sandbox_fixture", _job)
        # Remember which bound this result will belong to: the table is still editable while
        # the solve runs, so the delta must be able to name its own request on arrival.
        self._sandbox_jobs[jid] = (commit, c)
        self.sandbox_view.preview_btn.setEnabled(False)
        self.sandbox_view.commit_btn.setEnabled(False)
        self.sandbox_view.status.setText(f"sandbox solve started: {jid}")
        self.statusBar().showMessage(f"Started sandbox solve: {jid}")
        return jid

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

        run_dir = Path(path).resolve()
        if (run_dir / "dfba_summary.json").exists():
            self.load_dfba_dir(run_dir)
            return
        if (run_dir / "spatial_summary.json").exists():
            self.load_spatial_dir(run_dir)
            return
        if (run_dir / "host_microbe_bigg_summary.json").exists():
            self.load_host_microbe_bigg_dir(run_dir)
            return
        try:
            bundle = TidyBundle.read(run_dir)
        except Exception as e:
            # A failed load must not leave the *previous* run's provenance on screen: the
            # run_hash in the status bar and the profile table would still describe run A.
            self.current_manifest = None
            self.current_graph_payload = None
            self.profile_view.load_profile([])
            self.profile_view.load_targets(None)
            self.statusBar().showMessage(f"Run load failed: {e}")
            return
        manifest_path = run_dir / "manifest.json"
        self.current_manifest = (
            json.loads(manifest_path.read_text()) if manifest_path.exists() else None
        )
        self.current_graph_payload = graph_payload(bundle)
        self.profile_view.load_profile(bundle.profile.to_pylist())
        self.explorer.add_run(run_dir.name, run_dir)
        self.tabs.setCurrentWidget(self.profile_view)
        run_hash = None if self.current_manifest is None else self.current_manifest.get("run_hash")
        suffix = "" if run_hash is None else f" (run_hash {str(run_hash)[:12]})"
        self.statusBar().showMessage(f"Loaded run: {run_dir}{suffix}")

    def load_host_microbe_bigg_dir(self, path: str | Path) -> bool:
        """Load `cmig host-microbe-bigg` outputs into the Host tab."""
        from cmig.core.host import InterfaceFlux
        from cmig.core.host_impact import HostImpact

        run_dir = Path(path).resolve()
        # The pointer is only advanced after a successful parse (see the end of this method).
        # Advancing it up front meant Export Figure could write a *different* run's SVG while
        # every table on screen still showed the previously loaded run.
        summary_path = run_dir / "host_microbe_bigg_summary.json"
        if not summary_path.exists():
            self.statusBar().showMessage(f"Host-microbe summary not found: {summary_path}")
            return False
        try:
            payload = json.loads(summary_path.read_text())
            if "microbial_secretion" not in payload:
                secretion_path = run_dir / "microbial_secretion.csv"
                if secretion_path.exists():
                    with open(secretion_path, newline="") as f:
                        payload["microbial_secretion"] = {
                            str(row["metabolite"]): float(row["flux"])
                            for row in csv.DictReader(f)
                        }
            host_payload = payload.get("host", {})
            transfer = {
                str(met): float(value)
                for met, value in dict(payload.get("microbe_to_host", {})).items()
            }
            uptake_rows: list[InterfaceFlux] = []
            uptake_path = run_dir / "host_uptake.csv"
            if uptake_path.exists():
                with open(uptake_path, newline="") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        met = str(row["metabolite"])
                        uptake = float(row["uptake_flux"])
                        uptake_rows.append(InterfaceFlux(
                            exchange_id=f"EX_{met}_e",
                            interface="bigg_external",
                            metabolite=met,
                            flux=-uptake,
                            label="uptake",
                        ))
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
            self.statusBar().showMessage(f"Host-microbe load failed: {e}")
            return False

        if not isinstance(host_payload, dict) or "viable" not in host_payload:
            # Absence of the host block is missing data, not a biological finding. Defaulting
            # to viable=False rendered a red "non-viable — microbiome support insufficient",
            # i.e. a scientific conclusion manufactured from an incomplete file.
            self.statusBar().showMessage(
                f"No `host` block in {summary_path.name}; host viability cannot be reported "
                f"for {run_dir}."
            )
            return False

        host_result = SimpleNamespace(
            viable=bool(host_payload.get("viable", False)),
            status=str(host_payload.get("status", "unknown")),
            biomass=float(host_payload.get("objective_value") or 0.0),
            interface_fluxes=uptake_rows,
            lumen_uptake={
                str(met): float(value)
                for met, value in dict(host_payload.get("lumen_uptake", {})).items()
            },
        )
        impact = HostImpact(
            microbe_to_host=transfer,
            unused_secretion={
                str(met): float(value)
                for met, value in dict(payload.get("unused_secretion", {})).items()
            },
            host_viable=host_result.viable,
            host_biomass=host_result.biomass,
        )
        self.host_view.load_host_result(host_result)
        self.host_view.load_impact(impact)
        self.host_view.show_currency_metabolites = self.host_view.include_currency_check.isChecked()
        self.host_view.load_bigg_summary(payload, run_dir=run_dir)
        self.current_host_microbe_dir = run_dir      # only after a successful parse
        self.explorer.add_run(run_dir.name, run_dir)
        self.tabs.setCurrentWidget(self.host_view)
        self.statusBar().showMessage(
            f"Loaded host-microbe BiGG run: {run_dir} "
            f"({len(transfer)} transferred metabolites)"
        )
        return True

    def load_dfba_dir(self, path: str | Path) -> bool:
        run_dir = Path(path).resolve()
        summary_path = run_dir / "dfba_summary.json"
        if not summary_path.exists():
            self.statusBar().showMessage(f"dFBA summary not found: {summary_path}")
            return False
        try:
            payload = json.loads(summary_path.read_text())
            if not isinstance(payload, dict):
                raise ValueError("dfba_summary.json is not a JSON object")
        except (OSError, ValueError, json.JSONDecodeError) as e:
            self.statusBar().showMessage(f"dFBA load failed: {e}")
            return False
        self.dynamics_view.load_dfba_summary(payload, run_dir=run_dir)
        self.explorer.add_run(run_dir.name, run_dir)
        self.tabs.setCurrentWidget(self.dynamics_view)
        self.statusBar().showMessage(f"Loaded dFBA run: {run_dir}")
        return True

    def load_spatial_dir(self, path: str | Path) -> bool:
        run_dir = Path(path).resolve()
        summary_path = run_dir / "spatial_summary.json"
        if not summary_path.exists():
            self.statusBar().showMessage(f"Spatial summary not found: {summary_path}")
            return False
        try:
            payload = json.loads(summary_path.read_text())
            if not isinstance(payload, dict):
                raise ValueError("spatial_summary.json is not a JSON object")
        except (OSError, ValueError, json.JSONDecodeError) as e:
            self.statusBar().showMessage(f"Spatial load failed: {e}")
            return False
        self.dynamics_view.load_spatial_summary(payload, run_dir=run_dir)
        self.explorer.add_run(run_dir.name, run_dir)
        self.tabs.setCurrentWidget(self.dynamics_view)
        self.statusBar().showMessage(f"Loaded spatial preview: {run_dir}")
        return True

    def run_fixture(self, out_dir: str | Path, *, solver: str = "gurobi") -> str:
        """GUI 버튼용 fixture solve. JobRunner 로 제출해 Qt main thread 를 막지 않는다."""
        from cmig.service import EngineService, JobContext

        run_dir = Path(out_dir)

        def _job(ctx: JobContext) -> Any:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            outcome = EngineService().solve_fixture(solver=solver, out_dir=run_dir)
            _finish_after_artifacts(ctx)
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
        """Run user model-pool search from the Search tab."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        target, target_error = _single_target(self.search_view.targets_input.text())
        if target_error:
            self.search_view.status.setText(target_error)
            return ""
        model_dir = self.search_view.model_dir_input.text().strip()
        strategy = self.search_view.strategy_combo.currentText()
        min_size = str(self.search_view.min_size_spin.value())
        max_size = str(self.search_view.max_size_spin.value())
        top_k = str(self.search_view.top_k_spin.value())
        robustness_fva = self.search_view.robustness_check.isChecked()
        if not model_dir:
            self.search_view.status.setText(
                "Select a model folder before running product search."
            )
            return ""

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            argv = [
                "search",
                "--model-dir", model_dir,
                "--target", target,
                "--strategy", strategy,
                "--min-size", min_size,
                "--max-size", max_size,
                "--top-k", top_k,
            ]
            if robustness_fva:
                argv.append("--robustness-fva")
            argv.extend(["--out", str(out_dir)])
            output_name = "search_summary.json"
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"search failed with rc={rc}")
            _finish_after_artifacts(ctx)
            payload = json.loads((out_dir / output_name).read_text())
            if not isinstance(payload, dict):
                raise RuntimeError("search output is not a JSON object")
            return payload

        out_dir = Path(tempfile.mkdtemp(prefix="cmig-search-", dir=_search_temp_root())).resolve()
        jid = self.submit_job("search_fixture", _job)
        self._search_jobs[jid] = (out_dir, self.search_view.request_fields("search"))
        self.search_view.run_btn.setEnabled(False)
        self.search_view.status.setText(f"search started: {jid}")
        return jid

    def run_host_microbe_bigg(self) -> str:
        """Run BiGG host-microbe analysis from the Host tab."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        request = self.host_view.request()
        host = request["host"]
        model_dir = request["model_dir"]
        out_dir_text = request["out_dir"]
        if not host or not model_dir or not out_dir_text:
            self.host_view.run_status.setText(
                "Host model, microbial model folder, and output folder are required."
            )
            return ""
        if (
            float(request["microbial_biomass_gdw"]) <= 0.0
            or float(request["host_biomass_gdw"]) <= 0.0
            or not request["biomass_basis_kind"]
            or not request["biomass_basis_source"]
        ):
            self.host_view.run_status.setText(
                "Positive biomass gDW values, basis kind, and source are required."
            )
            return ""
        out_dir = Path(out_dir_text)

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            argv = [
                "host-microbe-bigg",
                "--host", str(host),
                "--model-dir", str(model_dir),
                "--tradeoff-f", f"{float(request['tradeoff_f']):.6g}",
                "--microbial-biomass-gdw",
                f"{float(request['microbial_biomass_gdw']):.12g}",
                "--host-biomass-gdw", f"{float(request['host_biomass_gdw']):.12g}",
                "--biomass-basis-kind", str(request["biomass_basis_kind"]),
                "--biomass-basis-source", str(request["biomass_basis_source"]),
                "--out", str(out_dir),
            ]
            if request["recursive"]:
                argv.append("--recursive")
            if request["keep_host_uptake"]:
                argv.append("--keep-host-uptake")
            if request["include_currency_metabolites"]:
                argv.append("--include-currency-metabolites")
            if request["host_medium"]:
                argv.extend(["--host-medium", str(request["host_medium"])])
            if request["microbe_medium"]:
                argv.extend(["--microbe-medium", str(request["microbe_medium"])])
            if request["host_objective"]:
                argv.extend(["--host-objective", str(request["host_objective"])])
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"host-microbe run failed with rc={rc}")
            _finish_after_artifacts(ctx)
            payload = json.loads((out_dir / "host_microbe_bigg_summary.json").read_text())
            if not isinstance(payload, dict):
                raise RuntimeError("host-microbe output is not a JSON object")
            return payload

        jid = self.submit_job("host_microbe_bigg", _job)
        self._host_microbe_jobs[jid] = out_dir
        self.host_view.run_btn.setEnabled(False)
        self.host_view.show_currency_metabolites = bool(request["include_currency_metabolites"])
        self.host_view.set_running(jid)
        self.statusBar().showMessage(f"Started host-microbe run: {jid}")
        return jid

    def run_host_search_bigg(self) -> str:
        """Rank microbial combinations by host objective/target transfer from the Host tab."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        request = self.host_view.request()
        host = request["host"]
        model_dir = request["model_dir"]
        if not host or not model_dir:
            self.host_view.run_status.setText(
                "Host model and microbial model folder are required for ranking."
            )
            return ""
        if (
            float(request["microbial_biomass_gdw"]) <= 0.0
            or float(request["host_biomass_gdw"]) <= 0.0
            or not request["biomass_basis_kind"]
            or not request["biomass_basis_source"]
        ):
            self.host_view.run_status.setText(
                "Positive biomass gDW values, basis kind, and source are required for ranking."
            )
            return ""
        out_dir_text = request["out_dir"]
        out_dir = (
            Path(out_dir_text)
            if out_dir_text
            else Path(tempfile.mkdtemp(prefix="cmig-host-search-", dir=_search_temp_root()))
        ).resolve()

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            argv = [
                "host-search-bigg",
                "--host", str(host),
                "--model-dir", str(model_dir),
                "--target", str(request["search_target"]),
                "--metric", str(request["search_metric"]),
                "--min-size", str(request["min_size"]),
                "--max-size", str(request["max_size"]),
                "--tradeoff-f", f"{float(request['tradeoff_f']):.6g}",
                "--microbial-biomass-gdw",
                f"{float(request['microbial_biomass_gdw']):.12g}",
                "--host-biomass-gdw", f"{float(request['host_biomass_gdw']):.12g}",
                "--biomass-basis-kind", str(request["biomass_basis_kind"]),
                "--biomass-basis-source", str(request["biomass_basis_source"]),
                "--out", str(out_dir),
            ]
            if request["recursive"]:
                argv.append("--recursive")
            if request["keep_host_uptake"]:
                argv.append("--keep-host-uptake")
            if request["include_currency_metabolites"]:
                argv.append("--include-currency-metabolites")
            if request["host_medium"]:
                argv.extend(["--host-medium", str(request["host_medium"])])
            if request["microbe_medium"]:
                argv.extend(["--microbe-medium", str(request["microbe_medium"])])
            if request["host_objective"]:
                argv.extend(["--host-objective", str(request["host_objective"])])
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"host-search run failed with rc={rc}")
            _finish_after_artifacts(ctx)
            payload = json.loads((out_dir / "host_search_summary.json").read_text())
            if not isinstance(payload, dict):
                raise RuntimeError("host-search output is not a JSON object")
            return payload

        jid = self.submit_job("host_search_bigg", _job)
        self._host_search_jobs[jid] = (out_dir, self.search_view.request_fields("host_search"))
        self.host_view.run_search_btn.setEnabled(False)
        self.host_view.run_status.setText(f"host-search started: {jid}")
        self.statusBar().showMessage(f"Started host-search run: {jid}")
        return jid

    def run_gene_ko_search(self) -> str:
        """Run fixed-combination single-gene KO screening from the Search tab."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        model_dir = self.search_view.model_dir_input.text().strip()
        members = self.search_view.ko_members_input.text().strip()
        member = self.search_view.ko_member_input.text().strip()
        genes = self.search_view.ko_genes_input.text().strip()
        target, target_error = _single_target(self.search_view.targets_input.text())
        if target_error:
            self.search_view.status.setText(target_error)
            return ""
        if not model_dir or not members:
            self.search_view.status.setText(
                "Model folder and KO members are required."
            )
            return ""
        if genes and not member:
            self.search_view.status.setText("Gene ids require a specific edited member.")
            return ""
        # Snapshot every answer-determining widget value HERE, on the GUI thread, before the
        # closure is handed to the executor. Reading `.value()` inside `_job` meant a queued
        # run silently executed the parameters the user typed *after* clicking, and read a
        # QWidget from a worker thread (undefined behaviour in Qt). Coordinator CC-8.
        max_genes = str(self.search_view.ko_max_genes_spin.value())
        top_k = str(self.search_view.top_k_spin.value())
        out_dir = Path(
            tempfile.mkdtemp(prefix="cmig-gene-ko-", dir=_search_temp_root())
        ).resolve()

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            argv = [
                "gene-ko-search",
                "--model-dir", model_dir,
                "--members", members,
                "--target", target,
                "--max-genes", max_genes,
                "--top-k", top_k,
                "--out", str(out_dir),
            ]
            if member:
                argv.extend(["--member", member])
            if genes:
                argv.extend(["--genes", genes])
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"gene KO search failed with rc={rc}")
            _finish_after_artifacts(ctx)
            payload = json.loads((out_dir / "gene_ko_summary.json").read_text())
            if not isinstance(payload, dict):
                raise RuntimeError("gene KO output is not a JSON object")
            return payload

        jid = self.submit_job("gene_ko_search", _job)
        self._gene_ko_jobs[jid] = (out_dir, self.search_view.request_fields("gene_ko"))
        self.search_view.run_ko_btn.setEnabled(False)
        self.search_view.status.setText(f"gene KO search started: {jid}")
        self.statusBar().showMessage(f"Started gene KO search: {jid}")
        return jid

    def run_strain_growth_report(self) -> str:
        """Run per-strain single/community growth profiling from the Search tab."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        model_dir = self.search_view.model_dir_input.text().strip()
        if not model_dir:
            self.search_view.status.setText("Select a model folder before strain growth.")
            return ""
        out_dir = Path(
            tempfile.mkdtemp(prefix="cmig-strain-growth-", dir=_search_temp_root())
        ).resolve()

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            argv = [
                "strain-growth",
                "--model-dir", model_dir,
                "--out", str(out_dir),
            ]
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"strain growth failed with rc={rc}")
            _finish_after_artifacts(ctx)
            payload = json.loads((out_dir / "strain_growth_summary.json").read_text())
            if not isinstance(payload, dict):
                raise RuntimeError("strain growth output is not a JSON object")
            return payload

        jid = self.submit_job("strain_growth", _job)
        self._strain_growth_jobs[jid] = (
            out_dir, self.search_view.request_fields("strain_growth")
        )
        self.search_view.run_growth_btn.setEnabled(False)
        self.search_view.status.setText(f"strain growth started: {jid}")
        self.statusBar().showMessage(f"Started strain growth report: {jid}")
        return jid

    def run_abundance_impact(self) -> str:
        """Run one-member abundance sweep from the Search tab."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        model_dir = self.search_view.model_dir_input.text().strip()
        member = self.search_view.growth_member_input.text().strip()
        fractions = self.search_view.abundance_fractions_input.text().strip()
        target, target_error = _single_target(self.search_view.targets_input.text())
        if target_error:
            self.search_view.status.setText(target_error)
            return ""
        if not model_dir or not member:
            self.search_view.status.setText(
                "Model folder and target member are required for ratio impact."
            )
            return ""
        out_dir = Path(
            tempfile.mkdtemp(prefix="cmig-abundance-impact-", dir=_search_temp_root())
        ).resolve()

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            argv = [
                "abundance-impact",
                "--model-dir", model_dir,
                "--member", member,
                "--fractions", fractions or "0.1,0.25,0.5,0.75",
                "--target", target,
                "--out", str(out_dir),
            ]
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"abundance impact failed with rc={rc}")
            _finish_after_artifacts(ctx)
            payload = json.loads((out_dir / "abundance_impact_summary.json").read_text())
            if not isinstance(payload, dict):
                raise RuntimeError("abundance impact output is not a JSON object")
            return payload

        jid = self.submit_job("abundance_impact", _job)
        self._abundance_impact_jobs[jid] = (
            out_dir, self.search_view.request_fields("abundance_impact")
        )
        self.search_view.run_abundance_btn.setEnabled(False)
        self.search_view.status.setText(f"ratio impact started: {jid}")
        self.statusBar().showMessage(f"Started ratio impact sweep: {jid}")
        return jid

    def run_dfba(self) -> str:
        """Run user-model dFBA from the Dynamics tab."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        request = self.dynamics_view.dfba_request()
        model = str(request["model"])
        if not model:
            self.dynamics_view.status.setText("Select a model before running dFBA.")
            return ""
        out_text = str(request["out_dir"])
        out_dir = (
            Path(out_text)
            if out_text
            else Path(tempfile.mkdtemp(prefix="cmig-dfba-", dir=_search_temp_root()))
        ).resolve()

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            argv = [
                "dfba",
                "--model", model,
                "--initial", str(request["initial"]),
                "--t-end", f"{float(request['t_end']):.6g}",
                "--dt", f"{float(request['dt']):.6g}",
                "--initial-biomass", f"{float(request['initial_biomass']):.6g}",
                "--out", str(out_dir),
            ]
            if request.get("close_untracked_uptake"):
                argv.append("--close-untracked-uptake")
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"dFBA failed with rc={rc}")
            _finish_after_artifacts(ctx)
            payload = json.loads((out_dir / "dfba_summary.json").read_text())
            if not isinstance(payload, dict):
                raise RuntimeError("dFBA output is not a JSON object")
            return payload

        jid = self.submit_job("dfba", _job)
        self._dfba_jobs[jid] = out_dir
        self.dynamics_view.run_dfba_btn.setEnabled(False)
        self.dynamics_view.status.setText(f"dFBA started: {jid}")
        self.statusBar().showMessage(f"Started dFBA: {jid}")
        return jid

    def run_spatial_preview(self) -> str:
        """Run COMETS-inspired spatial medium preview from the Dynamics tab."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        request = self.dynamics_view.spatial_request()
        out_text = str(request["out_dir"])
        out_dir = (
            Path(out_text)
            if out_text
            else Path(tempfile.mkdtemp(prefix="cmig-spatial-", dir=_search_temp_root()))
        ).resolve()

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            argv = [
                "spatial-preview",
                "--metabolite", str(request["metabolite"]),
                "--width", str(request["width"]),
                "--height", str(request["height"]),
                "--steps", str(request["steps"]),
                "--dt", f"{float(request['dt']):.6g}",
                "--diffusion", f"{float(request['diffusion']):.6g}",
                "--source-edge", str(request["source_edge"]),
                "--sink-edge", str(request["sink_edge"]),
                "--out", str(out_dir),
            ]
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"spatial preview failed with rc={rc}")
            _finish_after_artifacts(ctx)
            payload = json.loads((out_dir / "spatial_summary.json").read_text())
            if not isinstance(payload, dict):
                raise RuntimeError("spatial output is not a JSON object")
            return payload

        jid = self.submit_job("spatial_preview", _job)
        self._spatial_jobs[jid] = out_dir
        self.dynamics_view.run_spatial_btn.setEnabled(False)
        self.dynamics_view.status.setText(f"spatial preview started: {jid}")
        self.statusBar().showMessage(f"Started spatial preview: {jid}")
        return jid

    def run_community_solve(self) -> str:
        """Run a community solve from the Community Builder tab's members/abundances/tradeoff.

        Scans Model Folder into a taxonomy (id/file/abundance), overrides abundances for
        any member id present in the builder's table, then runs `cmig solve` through the
        JobRunner (same argv+main() pattern as the other product tabs).
        """
        from cmig.cli.main import main
        from cmig.service import JobContext

        model_dir = self.community_builder.model_dir_input.text().strip()
        if not model_dir:
            self.community_builder.status.setText(
                "Select a model folder before running the community."
            )
            return ""
        members = self.community_builder.members()
        if self.community_builder.invalid_rows:
            rows = ", ".join(str(r) for r in self.community_builder.invalid_rows)
            self.community_builder.status.setText(
                f"row {rows}: abundance is not a number — fix it before running."
            )
            return ""
        # `cmig solve` blocks on the namespace gate unless it is given a reviewed decisions
        # file or an explicit BiGG confirmation, and the GUI could set neither — so this tab
        # failed in 0.2 s for every user pool with the real reason on the process's stdout.
        namespace_argv, namespace_error = self.community_builder.namespace_policy()
        if namespace_error:
            self.community_builder.status.setText(namespace_error)
            return ""
        tradeoff_f = self.community_builder.tradeoff_f()
        out_dir = Path(
            tempfile.mkdtemp(prefix="cmig-community-", dir=_search_temp_root())
        ).resolve()

        def _job(ctx: JobContext) -> dict[str, Any]:
            from cmig.core.model_pool import taxonomy_from_model_dir

            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            taxonomy = taxonomy_from_model_dir(model_dir, recursive=False)
            if members:
                taxonomy = taxonomy.copy()
                taxonomy["abundance"] = [
                    members.get(str(mid), taxonomy["abundance"].iloc[i])
                    for i, mid in enumerate(taxonomy["id"])
                ]
            tax_path = out_dir / "taxonomy.csv"
            taxonomy.to_csv(tax_path, index=False)
            argv = [
                "solve",
                "--taxonomy", str(tax_path),
                "--tradeoff-f", f"{tradeoff_f:.6g}",
                "--out", str(out_dir),
                *namespace_argv,
            ]
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"community solve failed with rc={rc}")
            _finish_after_artifacts(ctx)
            manifest_path = out_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
            return {"manifest": manifest}

        jid = self.submit_job("community_solve", _job)
        self._community_jobs[jid] = out_dir
        self.community_builder.run_btn.setEnabled(False)
        self.community_builder.status.setText(f"community solve started: {jid}")
        self.statusBar().showMessage(f"Started community solve: {jid}")
        return jid

    def run_sweep_fixture(self) -> str:
        """Run a fixture tradeoff/solver sweep from the Sweep tab (`cmig sweep-fixture`)."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        tradeoff_fs = self.sweep_view.tradeoff_fs_input.text().strip() or "0.3,0.5"
        solvers = self.sweep_view.solvers_input.text().strip() or "gurobi"
        out_dir = Path(
            tempfile.mkdtemp(prefix="cmig-sweep-", dir=_search_temp_root())
        ).resolve()

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            argv = [
                "sweep-fixture",
                "--tradeoff-fs", tradeoff_fs,
                "--solvers", solvers,
                "--metric", "growth",
                "--out", str(out_dir),
            ]
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"sweep-fixture failed with rc={rc}")
            _finish_after_artifacts(ctx)
            return {"out_dir": str(out_dir)}

        jid = self.submit_job("sweep_fixture", _job)
        self._sweep_fixture_jobs[jid] = out_dir
        self.sweep_view.run_btn.setEnabled(False)
        self.sweep_view.status.setText(f"sweep started: {jid}")
        self.statusBar().showMessage(f"Started sweep: {jid}")
        return jid

    def run_medium_growth_check(self) -> str:
        """Run a single-model growth check from the Medium Editor tab (`cmig strain-growth`).

        The selected model is copied into an isolated model-pool folder (strain-growth needs
        --model-dir/--taxonomy, not a bare file) and the editor's MediumSpec, if non-empty, is
        written out and passed as --medium.
        """
        from cmig.cli.main import main
        from cmig.service import JobContext

        model_path = self.medium_editor.model_path_input.text().strip()
        if not model_path:
            self.medium_editor.growth_label.setText("Select a model before checking growth.")
            return ""
        try:
            spec = self.medium_editor.to_spec()
        except ValueError:
            return ""  # to_spec() already set an explicit status message (no silent failure)

        out_dir = Path(
            tempfile.mkdtemp(prefix="cmig-medium-growth-", dir=_search_temp_root())
        ).resolve()
        uptake = dict(spec.uptake)

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            src = Path(model_path)
            if not src.exists():
                raise RuntimeError(f"model file not found: {src}")
            model_dir = out_dir / "model_pool"
            model_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, model_dir / src.name)
            argv = [
                "strain-growth",
                "--model-dir", str(model_dir),
                "--out", str(out_dir),
            ]
            if uptake:
                medium_path = out_dir / "medium.json"
                medium_path.write_text(json.dumps(uptake))
                argv.extend(["--medium", str(medium_path)])
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"growth check failed with rc={rc}")
            _finish_after_artifacts(ctx)
            payload = json.loads((out_dir / "strain_growth_summary.json").read_text())
            if not isinstance(payload, dict):
                raise RuntimeError("growth check output is not a JSON object")
            return payload

        jid = self.submit_job("medium_growth_check", _job)
        self._medium_growth_jobs[jid] = out_dir
        self.medium_editor.check_growth_btn.setEnabled(False)
        self.medium_editor.growth_label.setText(f"growth check started: {jid}")
        self.statusBar().showMessage(f"Started growth check: {jid}")
        return jid

    def run_scenario_compare(self) -> None:
        """Compare two completed CMIG run directories from the Scenario Compare tab.

        Reads each run's tidy profile.parquet/nodes.parquet directly (fast local IO, matching
        the existing synchronous `load_run_dir`/sandbox-preview pattern — no solver call here,
        so no JobRunner needed) and feeds compute_delta() the fields it actually reads
        (external_exchange/members/status/objective).
        """
        from cmig.core.delta import compute_delta

        dir_a = self.scenario_compare.run_a_input.text().strip()
        dir_b = self.scenario_compare.run_b_input.text().strip()
        if not dir_a or not dir_b:
            self.scenario_compare.status.setText("Select both Run A and Run B directories.")
            return
        path_a, path_b = Path(dir_a), Path(dir_b)
        if not (path_a / "profile.parquet").exists() or not (path_b / "profile.parquet").exists():
            self.scenario_compare.status.setText(
                "Both directories must be completed CMIG runs (profile.parquet missing)."
            )
            return
        try:
            result_a = _solve_result_like_from_run_dir(path_a)
            result_b = _solve_result_like_from_run_dir(path_b)
            # Duck-typed run-dir reconstruction: compute_delta reads only
            # status/objective/external_exchange/members, all present on the namespace.
            delta = compute_delta(result_a, result_b)  # type: ignore[arg-type]
        except Exception as e:
            self.scenario_compare.status.setText(f"Scenario compare failed: {e}")
            return
        self.scenario_compare.load_comparison(delta)
        self.scenario_compare.status.setText(f"compare complete: {dir_a} vs {dir_b}")
        self.statusBar().showMessage("Scenario compare complete")

    def _register_run_output(self, out_dir: Path) -> None:
        """Make a GUI-only run reachable: it is the directory holding manifest.json.

        GUI workflows write to an OS temp dir that never appeared anywhere in the UI, so a
        GUI-only researcher could not find the run_hash a publication needs (and macOS purges
        `/var/folders/**/T` periodically).
        """
        self.explorer.add_run(out_dir.name, out_dir)

    def _poll_completed_jobs(self) -> None:
        for jid, (commit, constraint) in list(self._sandbox_jobs.items()):
            job = self.runner.poll(jid)
            if job.status not in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
                continue
            # Every terminal state releases the buttons — including DONE with a None result,
            # which previously matched no branch and left the job stranded in the dict with
            # Preview and Commit disabled for the rest of the session.
            self._sandbox_jobs.pop(jid, None)
            self.sandbox_view.preview_btn.setEnabled(True)
            self.sandbox_view.commit_btn.setEnabled(True)
            if job.status is not JobStatus.DONE:
                self.sandbox_view.status.setText(
                    f"Sandbox {job.status.value}: {job.error or jid}"
                )
                continue
            result = job.result
            if result is None or getattr(result, "delta", None) is None:
                self.sandbox_view.status.setText(
                    f"Sandbox finished with no result to display: {jid}"
                )
                continue
            run_hash = getattr(result, "run_hash", None)
            if commit and run_hash:
                self.sandbox_view.show_commit(result.delta, run_hash, constraint)
            else:
                self.sandbox_view.show_preview(result.delta, constraint)
            self.runner.release_payload(jid)
        for jid in list(self._fixture_jobs):
            job = self.runner.poll(jid)
            if job.status is JobStatus.DONE:
                self._fixture_jobs.pop(jid, None)
                self.load_completed_fixture(jid)
                # The fixture outcome holds a whole MICOM community; release it once the UI
                # has rendered it so a long session does not grow without bound.
                self.runner.release_payload(jid)
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._fixture_jobs.pop(jid, None)
                self.statusBar().showMessage(f"Fixture job {job.status.value}: {jid}")
        for jid, (out_dir, requested) in list(self._search_jobs.items()):
            job = self.runner.poll(jid)
            if job.status is JobStatus.DONE and isinstance(job.result, dict):
                self._search_jobs.pop(jid, None)
                self.current_search_dir = out_dir
                self.search_view.load_summary(
                    job.result, run_dir=out_dir,
                    request_note=self.search_view.superseded_note(requested, "search"),
                )
                self.search_view.run_btn.setEnabled(True)
                self.tabs.setCurrentWidget(self.search_view)
                self._register_run_output(out_dir)
                self.statusBar().showMessage(f"Search complete: {jid} → {out_dir}")
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._search_jobs.pop(jid, None)
                self.search_view.run_btn.setEnabled(True)
                self.search_view.status.setText(f"search {job.status.value}: {job.error or jid}")
        for jid, out_dir in list(self._host_microbe_jobs.items()):
            job = self.runner.poll(jid)
            if job.status is JobStatus.DONE:
                self._host_microbe_jobs.pop(jid, None)
                self.host_view.run_btn.setEnabled(True)
                self.load_host_microbe_bigg_dir(out_dir)
                self.statusBar().showMessage(f"Host-microbe complete: {jid}")
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._host_microbe_jobs.pop(jid, None)
                self.host_view.run_btn.setEnabled(True)
                self.host_view.run_status.setText(
                    f"host-microbe {job.status.value}: {job.error or jid}"
                )
        for jid, (out_dir, requested) in list(self._host_search_jobs.items()):
            job = self.runner.poll(jid)
            if job.status is JobStatus.DONE and isinstance(job.result, dict):
                self._host_search_jobs.pop(jid, None)
                self.host_view.run_search_btn.setEnabled(True)
                self.current_search_dir = out_dir
                summary = _host_search_summary_for_search_view(job.result)
                self.search_view.figure_mode_combo.setCurrentText("Ranking")
                self.search_view.load_summary(
                    summary, run_dir=out_dir,
                    request_note=self.search_view.superseded_note(requested, "host_search"),
                )
                self.tabs.setCurrentWidget(self.search_view)
                self._register_run_output(out_dir)
                self.statusBar().showMessage(f"Host-search complete: {jid} → {out_dir}")
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._host_search_jobs.pop(jid, None)
                self.host_view.run_search_btn.setEnabled(True)
                self.host_view.run_status.setText(
                    f"host-search {job.status.value}: {job.error or jid}"
                )
        for jid, (out_dir, requested) in list(self._gene_ko_jobs.items()):
            job = self.runner.poll(jid)
            if job.status is JobStatus.DONE and isinstance(job.result, dict):
                self._gene_ko_jobs.pop(jid, None)
                self.search_view.run_ko_btn.setEnabled(True)
                self.current_search_dir = out_dir
                summary = _gene_ko_summary_for_search_view(job.result)
                self.search_view.figure_mode_combo.setCurrentText("Ranking")
                self.search_view.load_summary(
                    summary, run_dir=out_dir,
                    request_note=self.search_view.superseded_note(requested, "gene_ko"),
                )
                self.tabs.setCurrentWidget(self.search_view)
                self._register_run_output(out_dir)
                self.statusBar().showMessage(f"Gene KO search complete: {jid} → {out_dir}")
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._gene_ko_jobs.pop(jid, None)
                self.search_view.run_ko_btn.setEnabled(True)
                self.search_view.status.setText(
                    f"gene KO search {job.status.value}: {job.error or jid}"
                )
        for jid, (out_dir, requested) in list(self._strain_growth_jobs.items()):
            job = self.runner.poll(jid)
            if job.status is JobStatus.DONE and isinstance(job.result, dict):
                self._strain_growth_jobs.pop(jid, None)
                self.search_view.run_growth_btn.setEnabled(True)
                self.current_search_dir = out_dir
                summary = _strain_growth_summary_for_search_view(job.result)
                self.search_view.figure_mode_combo.setCurrentText("Ranking")
                self.search_view.load_summary(
                    summary, run_dir=out_dir,
                    request_note=self.search_view.superseded_note(requested, "strain_growth"),
                )
                self.tabs.setCurrentWidget(self.search_view)
                self._register_run_output(out_dir)
                self.statusBar().showMessage(f"Strain growth complete: {jid} → {out_dir}")
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._strain_growth_jobs.pop(jid, None)
                self.search_view.run_growth_btn.setEnabled(True)
                self.search_view.status.setText(
                    f"strain growth {job.status.value}: {job.error or jid}"
                )
        for jid, (out_dir, requested) in list(self._abundance_impact_jobs.items()):
            job = self.runner.poll(jid)
            if job.status is JobStatus.DONE and isinstance(job.result, dict):
                self._abundance_impact_jobs.pop(jid, None)
                self.search_view.run_abundance_btn.setEnabled(True)
                self.current_search_dir = out_dir
                summary = _abundance_impact_summary_for_search_view(job.result)
                self.search_view.figure_mode_combo.setCurrentText("Ranking")
                self.search_view.load_summary(
                    summary, run_dir=out_dir,
                    request_note=self.search_view.superseded_note(requested, "abundance_impact"),
                )
                self.tabs.setCurrentWidget(self.search_view)
                self._register_run_output(out_dir)
                self.statusBar().showMessage(f"Ratio impact complete: {jid} → {out_dir}")
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._abundance_impact_jobs.pop(jid, None)
                self.search_view.run_abundance_btn.setEnabled(True)
                self.search_view.status.setText(
                    f"ratio impact {job.status.value}: {job.error or jid}"
                )
        for jid, out_dir in list(self._dfba_jobs.items()):
            job = self.runner.poll(jid)
            if job.status is JobStatus.DONE:
                self._dfba_jobs.pop(jid, None)
                self.dynamics_view.run_dfba_btn.setEnabled(True)
                self.load_dfba_dir(out_dir)
                self.statusBar().showMessage(f"dFBA complete: {jid}")
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._dfba_jobs.pop(jid, None)
                self.dynamics_view.run_dfba_btn.setEnabled(True)
                self.dynamics_view.status.setText(f"dFBA {job.status.value}: {job.error or jid}")
        for jid, out_dir in list(self._spatial_jobs.items()):
            job = self.runner.poll(jid)
            if job.status is JobStatus.DONE:
                self._spatial_jobs.pop(jid, None)
                self.dynamics_view.run_spatial_btn.setEnabled(True)
                self.load_spatial_dir(out_dir)
                self.statusBar().showMessage(f"Spatial preview complete: {jid}")
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._spatial_jobs.pop(jid, None)
                self.dynamics_view.run_spatial_btn.setEnabled(True)
                self.dynamics_view.status.setText(
                    f"spatial preview {job.status.value}: {job.error or jid}"
                )
        for jid, out_dir in list(self._community_jobs.items()):
            job = self.runner.poll(jid)
            if job.status is JobStatus.DONE:
                self._community_jobs.pop(jid, None)
                self.community_builder.run_btn.setEnabled(True)
                manifest = (job.result or {}).get("manifest", {}) if isinstance(
                    job.result, dict
                ) else {}
                run_hash = manifest.get("run_hash") if isinstance(manifest, dict) else None
                suffix = f" (run_hash {str(run_hash)[:12]})" if run_hash else ""
                self.community_builder.status.setText(f"community solve complete{suffix}")
                self.load_run_dir(out_dir)
                self.statusBar().showMessage(f"Community solve complete: {jid}")
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._community_jobs.pop(jid, None)
                self.community_builder.run_btn.setEnabled(True)
                self.community_builder.status.setText(
                    f"community solve {job.status.value}: {job.error or jid}"
                )
        for jid, out_dir in list(self._sweep_fixture_jobs.items()):
            job = self.runner.poll(jid)
            if job.status is JobStatus.DONE:
                self._sweep_fixture_jobs.pop(jid, None)
                self.sweep_view.run_btn.setEnabled(True)
                rows = _load_sweep_rows(out_dir / "sweep.parquet")
                self.sweep_view.load_results(rows)
                self.sweep_view.status.setText(f"sweep complete: {len(rows)} runs → {out_dir}")
                self._register_run_output(out_dir)
                self.statusBar().showMessage(f"Sweep complete: {jid} → {out_dir}")
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._sweep_fixture_jobs.pop(jid, None)
                self.sweep_view.run_btn.setEnabled(True)
                self.sweep_view.status.setText(f"sweep {job.status.value}: {job.error or jid}")
        for jid, out_dir in list(self._medium_growth_jobs.items()):
            job = self.runner.poll(jid)
            if job.status is JobStatus.DONE and isinstance(job.result, dict):
                self._medium_growth_jobs.pop(jid, None)
                self.medium_editor.check_growth_btn.setEnabled(True)
                self._register_run_output(out_dir)
                members = job.result.get("members", [])
                if members and isinstance(members[0], dict):
                    growth = members[0].get("single_growth")
                    status = members[0].get(
                        "single_status", members[0].get("community_status", "")
                    )
                    growth_text = "—" if growth is None else f"{growth:.4g}"
                    self.medium_editor.growth_label.setText(
                        f"growth: {growth_text} ({status})"
                    )
                else:
                    self.medium_editor.growth_label.setText(
                        "growth check complete (no result rows)"
                    )
                self.statusBar().showMessage(f"Growth check complete: {jid}")
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._medium_growth_jobs.pop(jid, None)
                self.medium_editor.check_growth_btn.setEnabled(True)
                self.medium_editor.growth_label.setText(
                    f"growth check {job.status.value}: {job.error or jid}"
                )


def _host_search_summary_for_search_view(payload: dict[str, Any]) -> dict[str, Any]:
    """Adapt host-search output to the existing SearchView ranking table contract."""
    target = str(payload.get("target", ""))
    rows: list[dict[str, Any]] = []
    for item in payload.get("top_ranked", []):
        if not isinstance(item, dict):
            continue
        rows.append({
            "members": item.get("members", []),
            "score": item.get("score"),
            "target_flux": item.get("target_transfer"),
            "community_growth": item.get("community_growth"),
            "status": item.get("evaluation_status", item.get("host_status", "")),
            "diagnostic": item.get("diagnostic"),
        })
    return {
        "target": target,
        "strategy": f"host-search/{payload.get('metric', '')}",
        "top_ranked": rows,
        # Forward CLI warnings verbatim — the GUI is not allowed to be quieter than the CLI.
        "warnings": list(payload.get("warnings") or []),
        "column_labels": [
            "Members", "Target", "Score", "Target transfer (mmol gDW⁻¹ h⁻¹)",
            "Community growth (h⁻¹)", "FVA Range", "Status",
        ],
    }


def _gene_ko_summary_for_search_view(payload: dict[str, Any]) -> dict[str, Any]:
    """Adapt gene KO output to the existing SearchView ranking table contract."""
    target = str(payload.get("target", ""))
    rows: list[dict[str, Any]] = []
    for item in payload.get("top_ranked", []):
        if not isinstance(item, dict):
            continue
        rows.append({
            "members": [f"{item.get('member', '')}:{item.get('gene', '')}"],
            # SearchView columns are absolute Score/Flux/Growth; feed the absolute fields (deltas
            # live in the figure + CSV/JSON) so the headers match the values shown.
            "score": item.get("score"),
            "target_flux": item.get("target_flux"),
            "community_growth": item.get("community_growth"),
            "status": item.get("evaluation_status", item.get("status", "")),
            "diagnostic": item.get("diagnostic"),
        })
    return {
        "target": target,
        "strategy": f"{payload.get('ko_level', 'gene')}-ko",
        "top_ranked": rows,
        # Forward CLI warnings (truncation / random selection) so the GUI status bar surfaces
        # them too — never silently drop them (the honesty fix must hold on the GUI path).
        "warnings": list(payload.get("warnings") or []),
        "column_labels": [
            "Member:gene", "Target", "KO score", "Target flux (mmol gDW⁻¹ h⁻¹)",
            "Community growth (h⁻¹)", "FVA Range", "Status",
        ],
    }


def _strain_growth_summary_for_search_view(payload: dict[str, Any]) -> dict[str, Any]:
    """Adapt strain-growth output to the existing SearchView ranking table contract."""
    rows: list[dict[str, Any]] = []
    for item in payload.get("members", []):
        if not isinstance(item, dict):
            continue
        rows.append({
            "members": [item.get("member", "")],
            "score": item.get("community_member_growth"),
            "target_flux": item.get("single_growth"),
            "community_growth": item.get("community_growth"),
            "status": item.get("community_status", item.get("single_status", "")),
            "diagnostic": item.get("diagnostic"),
        })
    return {
        "target": "growth",
        "strategy": "strain-growth",
        "top_ranked": rows,
        "warnings": list(payload.get("warnings") or []),
        # Both quantities here are growth rates in h⁻¹; the default "Flux" header implied
        # mmol gDW⁻¹ h⁻¹ and was the concrete misread risk.
        "column_labels": [
            "Member", "Quantity", "Community member growth (h⁻¹)", "Single growth (h⁻¹)",
            "Community growth (h⁻¹)", "FVA Range", "Status",
        ],
    }


def _abundance_impact_summary_for_search_view(payload: dict[str, Any]) -> dict[str, Any]:
    """Adapt abundance-impact output to the existing SearchView ranking table contract."""
    target = str(payload.get("target", ""))
    target_member = str(payload.get("target_member", ""))
    rows: list[dict[str, Any]] = []
    for item in payload.get("rows", []):
        if not isinstance(item, dict):
            continue
        abundance = item.get("target_abundance")
        label = f"{target_member}@{abundance:.3g}" if isinstance(abundance, (int, float)) else (
            f"{target_member}@{abundance}"
        )
        # The member's own exchange and the community's net exchange can disagree completely
        # (7.14 vs 0.0 on real output). Showing only the member value under a column headed
        # "Flux" next to "Target = ac" made the GUI ranking contradict the community result,
        # so both are surfaced side by side under labels that say which is which.
        community_exchange = item.get("community_target_exchange")
        rows.append({
            "members": [label],
            "score": item.get("target_influence_share"),
            "target_flux": item.get("target_member_exchange"),
            "community_growth": item.get("community_growth"),
            "aux_text": "—" if community_exchange is None else f"{float(community_exchange):.4g}",
            "status": item.get("status", ""),
            "diagnostic": item.get("diagnostic"),
        })
    return {
        "target": target,
        "strategy": "abundance-impact",
        "top_ranked": rows,
        "warnings": list(payload.get("warnings") or []),
        "column_labels": [
            "Member@abundance", "Target", "Influence share (dimensionless)",
            "Member exchange (mmol gDW⁻¹ h⁻¹)", "Community growth (h⁻¹)",
            "Community exchange (mmol gDW⁻¹ h⁻¹)", "Status",
        ],
    }


def _load_sweep_rows(parquet_path: Path) -> list[Any]:
    """Read a sweep.parquet artifact back into SweepRow objects for SweepView.load_results."""
    import pyarrow.parquet as pq

    from cmig.core.sweep import SweepRow

    if not parquet_path.exists():
        return []
    table = pq.read_table(parquet_path)  # type: ignore[no-untyped-call]  # pyarrow has no stubs
    rows: list[Any] = []
    for record in table.to_pylist():
        rows.append(SweepRow(
            condition_id=str(record.get("condition_id", "")),
            axis_values={},
            metric=str(record.get("metric", "")),
            value=record.get("value"),
            run_hash=str(record.get("run_hash", "")),
            status=str(record.get("status", "")),
            diagnostic=record.get("diagnostic"),
            cache_hit=bool(record.get("cache_hit", False)),
        ))
    return rows


def _solve_result_like_from_run_dir(run_dir: Path) -> SimpleNamespace:
    """Reconstruct the fields compute_delta() actually reads from a completed run directory.

    manifest.json only stores run_hash *inputs* (11 hash components), not the solved growth
    objective, so `objective` is reconstructed as the abundance-weighted sum of per-member
    growth from nodes.parquet — this matches how MICOM's cooperative-tradeoff community
    objective is itself built (a convex combination of member biomass reactions weighted by
    abundance), so it is a faithful reconstruction rather than an approximation of a different
    quantity. `status` is "optimal" unless a member is missing growth/abundance (infeasible).
    """
    from cmig.core.tidy import TidyBundle

    bundle = TidyBundle.read(run_dir)
    external_exchange = {
        str(row["metabolite"]): float(row["net_flux"])
        for row in bundle.profile.to_pylist()
    }
    members: list[str] = []
    objective = 0.0
    status = "optimal"
    for row in bundle.nodes.to_pylist():
        if row.get("node_type") != "member":
            continue
        members.append(str(row["node_id"]))
        growth, abundance = row.get("growth"), row.get("abundance")
        if growth is None or abundance is None:
            status = "infeasible"
            continue
        objective += float(growth) * float(abundance)
    return SimpleNamespace(
        external_exchange=external_exchange, members=members, status=status, objective=objective,
    )


def build_main_window(runner: JobRunner | None = None, lang: str = "ko") -> CmigMainWindow:
    """메인 윈도우 팩토리(offscreen 검증·진입점)."""
    return CmigMainWindow(runner=runner, lang=lang)
