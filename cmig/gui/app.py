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
from cmig.gui.host_view import HostImpactView
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

    def refresh(self, runner: JobRunner, job_ids: list[str]) -> None:
        """JobRunner.poll 로 각 job 의 실제 상태를 표에 반영(orphan 아님)."""
        self.setRowCount(len(job_ids))
        for row, jid in enumerate(job_ids):
            job = runner.poll(jid)
            prog = f"{job.progress[0]}/{job.progress[1]}" if job.progress else "—"
            for col, text in enumerate([job.job_id, job.kind, job.status.value, prog]):
                self.setItem(row, col, QTableWidgetItem(text))

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
        self._search_jobs: dict[str, Path] = {}
        self._host_microbe_jobs: dict[str, Path] = {}
        self._host_search_jobs: dict[str, Path] = {}
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
        self._primary_tabs = [
            ("Models", self.model_manager),
            ("Search", self.search_view),
            ("Host", self.host_view),
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
        splitter.addWidget(self.explorer)
        splitter.addWidget(center)
        splitter.addWidget(self.jobs_panel)
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

    def _install_workflow_actions(self) -> None:
        toolbar = self.addToolBar("Workflow")
        self.import_model_action = QAction("Import Model", self)
        self.import_model_action.triggered.connect(self._import_model_dialog)
        self.open_run_action = QAction("Open Run", self)
        self.open_run_action.triggered.connect(self._open_run_dialog)
        self.run_fixture_action = QAction("Run Fixture", self)
        self.run_fixture_action.triggered.connect(self._run_fixture_dialog)
        self.cancel_job_action = QAction("Cancel Selected Job", self)
        self.cancel_job_action.triggered.connect(self._cancel_selected_job)
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
        self.search_view.export_figure_btn.clicked.connect(self._export_search_figure)
        self.host_view.browse_host_btn.clicked.connect(self._browse_host_model)
        self.host_view.browse_model_dir_btn.clicked.connect(self._browse_host_microbe_model_dir)
        self.host_view.browse_host_medium_btn.clicked.connect(self._browse_host_medium)
        self.host_view.browse_microbe_medium_btn.clicked.connect(self._browse_microbe_medium)
        self.host_view.browse_out_dir_btn.clicked.connect(self._browse_host_microbe_out_dir)
        self.host_view.run_btn.clicked.connect(self.run_host_microbe_bigg)
        self.host_view.run_search_btn.clicked.connect(self.run_host_search_bigg)
        self.host_view.export_figure_btn.clicked.connect(self._export_host_figure)

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
        self.statusBar().showMessage(f"Cancel requested: {job_id}")

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

    def _export_host_figure(self) -> None:
        if self.current_host_microbe_dir is None:
            self.host_view.run_status.setText("No host-microbe result is loaded.")
            return
        artifact = self.host_view.selected_figure_artifact()
        src = self.current_host_microbe_dir / artifact
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
        if self.current_search_dir is None:
            self.search_view.status.setText("No search result is loaded.")
            return
        artifact = self.search_view.selected_figure_artifact()
        src = self.current_search_dir / artifact
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
        if len(constraints) > 1:
            self.sandbox_view.status.setText(
                "Sandbox fixture supports one bound at a time; "
                "remove extra rows before preview or commit."
            )
            return
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

        run_dir = Path(path).resolve()
        if (run_dir / "host_microbe_bigg_summary.json").exists():
            self.load_host_microbe_bigg_dir(run_dir)
            return
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
        self.current_host_microbe_dir = run_dir
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
        self.explorer.add_run(run_dir.name, run_dir)
        self.tabs.setCurrentWidget(self.host_view)
        self.statusBar().showMessage(
            f"Loaded host-microbe BiGG run: {run_dir} "
            f"({len(transfer)} transferred metabolites)"
        )
        return True

    def run_fixture(self, out_dir: str | Path, *, solver: str = "gurobi") -> str:
        """GUI 버튼용 fixture solve. JobRunner 로 제출해 Qt main thread 를 막지 않는다."""
        from cmig.service import EngineService, JobContext

        run_dir = Path(out_dir)

        def _job(ctx: JobContext) -> Any:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            outcome = EngineService().solve_fixture(solver=solver, out_dir=run_dir)
            ctx.raise_if_cancelled()
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
        """Run user model-pool search from the Search tab."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        target_text = self.search_view.targets_input.text().strip() or "but"
        target = target_text.split(",", 1)[0].strip() or "but"
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
                "--out", str(out_dir),
            ]
            if robustness_fva:
                argv.insert(-2, "--robustness-fva")
            output_name = "search_summary.json"
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"search failed with rc={rc}")
            ctx.raise_if_cancelled()
            ctx.report_progress(1, 1)
            payload = json.loads((out_dir / output_name).read_text())
            if not isinstance(payload, dict):
                raise RuntimeError("search output is not a JSON object")
            return payload

        out_dir = Path(tempfile.mkdtemp(prefix="cmig-search-", dir=_search_temp_root())).resolve()
        jid = self.submit_job("search_fixture", _job)
        self._search_jobs[jid] = out_dir
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
        out_dir = Path(out_dir_text)

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            argv = [
                "host-microbe-bigg",
                "--host", str(host),
                "--model-dir", str(model_dir),
                "--tradeoff-f", f"{float(request['tradeoff_f']):.6g}",
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
            ctx.raise_if_cancelled()
            ctx.report_progress(1, 1)
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
            ctx.raise_if_cancelled()
            ctx.report_progress(1, 1)
            payload = json.loads((out_dir / "host_search_summary.json").read_text())
            if not isinstance(payload, dict):
                raise RuntimeError("host-search output is not a JSON object")
            return payload

        jid = self.submit_job("host_search_bigg", _job)
        self._host_search_jobs[jid] = out_dir
        self.host_view.run_search_btn.setEnabled(False)
        self.host_view.run_status.setText(f"host-search started: {jid}")
        self.statusBar().showMessage(f"Started host-search run: {jid}")
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
        for jid, out_dir in list(self._search_jobs.items()):
            job = self.runner.poll(jid)
            if job.status is JobStatus.DONE and isinstance(job.result, dict):
                self._search_jobs.pop(jid, None)
                self.current_search_dir = out_dir
                self.search_view.load_summary(job.result, run_dir=out_dir)
                self.search_view.run_btn.setEnabled(True)
                self.tabs.setCurrentWidget(self.search_view)
                self.statusBar().showMessage(f"Search complete: {jid}")
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
        for jid, out_dir in list(self._host_search_jobs.items()):
            job = self.runner.poll(jid)
            if job.status is JobStatus.DONE and isinstance(job.result, dict):
                self._host_search_jobs.pop(jid, None)
                self.host_view.run_search_btn.setEnabled(True)
                self.current_search_dir = out_dir
                summary = _host_search_summary_for_search_view(job.result)
                self.search_view.figure_mode_combo.setCurrentText("Ranking")
                self.search_view.load_summary(summary, run_dir=out_dir)
                self.tabs.setCurrentWidget(self.search_view)
                self.statusBar().showMessage(f"Host-search complete: {jid}")
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._host_search_jobs.pop(jid, None)
                self.host_view.run_search_btn.setEnabled(True)
                self.host_view.run_status.setText(
                    f"host-search {job.status.value}: {job.error or jid}"
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
        "warnings": [],
    }


def build_main_window(runner: JobRunner | None = None, lang: str = "ko") -> CmigMainWindow:
    """메인 윈도우 팩토리(offscreen 검증·진입점)."""
    return CmigMainWindow(runner=runner, lang=lang)
