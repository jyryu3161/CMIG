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
from cmig.gui.graph_view import GateBadge, InteractionGraphView
from cmig.gui.host_view import HostImpactView
from cmig.gui.views import (
    CONTRIBUTION_BASIS_NOTE,
    DfbaSpatialView,
    ExternalProfileView,
    SweepView,
)
from cmig.service import JobRunner, JobStatus

I18N: dict[str, dict[str, str]] = {
    "ko": {
        "title": "CMIG — 군집 대사 상호작용",
        "explorer": "프로젝트 탐색기",
        "models": "모델",
        "scenarios": "시나리오",
        "runs": "실행 기록",
        "jobs": "런타임 및 작업",
        "welcome": "프로젝트를 열거나 모델을 가져오세요.",
        "col_job": "작업",
        "col_kind": "종류",
        "col_status": "상태",
        "col_progress": "진행률",
        "tab_models": "모델",
        "tab_search": "탐색",
        "tab_host": "숙주",
        "tab_dynamics": "동역학",
        "tab_graph": "그래프",
        "tab_profile": "외부 프로필",
        "tab_community": "군집",
        "tab_medium": "배지",
        "tab_sweep": "스윕",
        "tab_sandbox": "샌드박스",
        "tab_compare": "비교",
        "toolbar_workflow": "워크플로",
        "action_import_model": "모델 가져오기",
        "action_open_run": "실행 열기",
        "action_run_fixture": "예제 실행",
        "action_cancel_job": "선택한 작업 취소",
        "action_show_advanced": "고급 도구 표시",
        "action_hide_advanced": "고급 도구 숨기기",
        "kind_sandbox_solve": "샌드박스 계산",
        "kind_fixture_run": "예제 실행",
        "kind_host_microbe": "숙주-미생물 실행",
        "kind_host_search": "숙주 탐색",
        "kind_gene_ko_search": "유전자 KO 탐색",
        "kind_strain_growth": "균주 성장 보고서",
        "kind_ratio_impact": "비율 영향 스윕",
        "kind_dfba": "dFBA",
        "kind_spatial": "공간 미리보기",
        "kind_community_solve": "군집 계산",
        "kind_sweep": "스윕",
        "kind_growth_check": "성장 확인",
        "kind_search": "탐색",
        "ready": "준비됨",
        "status_select_job": "취소할 실행 중 작업을 선택하세요.",
        "status_job_already": "작업이 이미 {status} 상태입니다: {job_id}",
        "status_cancel_requested": (
            "{job_id} 취소를 요청했습니다. 실행 중인 solver는 중간에 중단할 수 없어 다음 "
            "체크포인트까지 CPU를 계속 사용합니다. 산출물을 이미 기록했다면 완료로 보고됩니다."
        ),
        "status_started": "{kind} 시작: {job_id}",
        "status_complete": "{kind} 완료: {job_id}",
        "status_complete_out": "{kind} 완료: {job_id} → {out_dir}",
        "status_model_import_failed": "모델 가져오기 실패: {error}",
        "status_imported_model": "{model_id} 가져옴; namespace 범위 {coverage:.0f}%",
        "status_run_load_failed": "실행 불러오기 실패: {error}",
        "status_loaded_run": "실행 불러옴: {run_dir}{suffix}",
        "status_summary_missing": "{kind} 요약 파일 없음: {path}",
        "status_load_failed": "{kind} 불러오기 실패: {error}",
        "status_host_block_missing": (
            "{summary}에 `host` 블록이 없어 {run_dir}의 숙주 생존성을 보고할 수 없습니다."
        ),
        "status_loaded_host": ("숙주-미생물 BiGG 실행 불러옴: {run_dir} (전달 대사체 {count}개)"),
        "status_loaded_dfba": "dFBA 실행 불러옴: {run_dir}",
        "status_loaded_spatial": "공간 미리보기 불러옴: {run_dir}",
        "status_fixture_incomplete": "예제 작업 미완료: {job_id}",
        "status_fixture_failed": "예제 실행 실패: {diagnostic}",
        "status_fixture_job": "예제 작업 {status}: {job_id}",
        "status_compare_complete": "시나리오 비교 완료",
        "sweep_title": "매개변수 스윕",
        "sweep_status_ready": (
            "고급 결과 보기: taxonomy 또는 모델 폴더를 선택하고 축을 설정한 다음 "
            "실행하세요."
        ),
        "sweep_taxonomy_placeholder": "Taxonomy CSV",
        "sweep_browse_taxonomy": "Taxonomy…",
        "sweep_model_dir_placeholder": "또는 사용자가 준비한 미생물 모델 폴더",
        "sweep_browse_models": "모델 폴더…",
        "sweep_taxonomy_label": "Taxonomy",
        "sweep_model_dir_label": "모델 소스",
        "sweep_mediums_placeholder": (
            "쉼표로 구분한 배지 CSV/JSON 파일(비우면 모델 기본값)"
        ),
        "sweep_abundance_placeholder": "쉼표로 구분한 abundance CSV/JSON 파일",
        "sweep_member_sets_placeholder": "세미콜론 구분 집합, 예: A+B;A+C",
        "sweep_bounds_placeholder": "쉼표로 구분한 bounds JSON 파일",
        "sweep_tradeoffs_placeholder": "쉼표로 구분한 tradeoff f 값",
        "sweep_solvers_placeholder": "쉼표로 구분한 solver",
        "sweep_browse_files": "파일…",
        "sweep_mediums_label": "배지",
        "sweep_abundance_label": "Abundance 변형",
        "sweep_member_sets_label": "멤버 집합",
        "sweep_bounds_label": "Bounds 변형",
        "sweep_tradeoffs_label": "Tradeoff f",
        "sweep_solvers_label": "Solver",
        "sweep_assume_bigg": "모델을 검토했고 BiGG namespace임을 확인합니다",
        "sweep_namespace_placeholder": "또는 검토된 namespace-decisions JSON 파일",
        "sweep_namespace_button": "판정 파일…",
        "sweep_fva": "FVA",
        "sweep_fva_metabolites_placeholder": "선택: 쉼표로 구분한 FVA 대사체",
        "sweep_exact_medium": "엄밀한 배지",
        "sweep_allow_unknown_medium": "알 수 없는 배지 ID 허용",
        "sweep_fixture_smoke": "내장 fixture 스모크 스윕 사용",
        "sweep_run": "스윕 실행",
        "sweep_col_condition": "조건",
        "sweep_col_value": "값",
        "sweep_col_status": "상태",
        "sweep_col_cache": "캐시",
        "sweep_col_medium": "배지",
        "sweep_col_abundance": "Abundance",
        "sweep_col_members": "멤버",
        "sweep_col_bounds": "Bounds",
        "sweep_col_tradeoff": "Tradeoff f",
        "sweep_col_solver": "Solver",
        "sweep_col_diagnostic": "진단",
        "sweep_select_source": (
            "실제 스윕을 실행하려면 taxonomy CSV 또는 모델 폴더를 선택하세요."
        ),
        "sweep_one_source": "Taxonomy CSV와 모델 폴더 중 하나만 선택하세요.",
        "sweep_namespace_choice": (
            "Namespace 정책은 검토 파일과 BiGG 확인 중 하나만 선택하세요."
        ),
        "sweep_namespace_required": (
            "Namespace 검토가 필요합니다. 검토된 판정 파일을 선택하거나 BiGG 확인을 체크하세요."
        ),
        "sweep_started_real": "실제 스윕 시작: {job_id}",
        "sweep_started_fixture": "Fixture 스모크 스윕 시작: {job_id}",
        "sweep_complete_detail": "{mode} 스윕 완료: {count}개 실행 → {out_dir}{warnings}",
        "sweep_failed_detail": "{mode} 스윕 {status}: {error}{artifact_note}",
        "sweep_failed_artifacts": " 산출물의 {count}개 조건을 표시합니다.",
        "sweep_mode_real": "실제",
        "sweep_mode_fixture": "fixture",
        "sweep_dialog_taxonomy": "Sweep taxonomy CSV 선택",
        "sweep_dialog_models": "Sweep 모델 폴더 선택",
        "sweep_dialog_mediums": "배지 변형 선택",
        "sweep_dialog_abundances": "Abundance 변형 선택",
        "sweep_dialog_bounds": "Bounds 변형 선택",
        "sweep_dialog_namespace": "Namespace 판정 파일 선택",
        "sweep_filter_csv": "CSV (*.csv);;모든 파일 (*)",
        "sweep_filter_medium": "배지 파일 (*.csv *.json);;모든 파일 (*)",
        "sweep_filter_abundance": "Abundance 파일 (*.csv *.json);;모든 파일 (*)",
        "sweep_filter_bounds": "Bounds 파일 (*.json);;모든 파일 (*)",
        "sweep_filter_json": "JSON (*.json);;모든 파일 (*)",
        "sweep_cli_failed": "sweep 명령 실패(rc={rc})",
        "profile_net_chart_title": "외부 순 플럭스(+ 분비 / − 흡수)",
        "profile_delta_overlay_title": "기준 / 변형 오버레이",
        "profile_no_fluxes": "측정된 프로필 플럭스 없음",
        "profile_delta_legend": "연한 색 = {baseline}; 진한 색 = {variant}",
        "profile_member_chart_title": "멤버별 기여(직접 플럭스 × abundance)",
        "profile_no_member_contributions": "Abundance 기준 멤버 기여 없음",
        "profile_heatmap_title": "플럭스 히트맵(+ 분비 / − 흡수)",
        "profile_heatmap_blank_note": "빈 칸 = 플럭스 미기록(0으로 채우지 않음).",
        "profile_heatmap_empty": "플럭스 행렬 없음",
        "profile_current_scenario": "현재",
        "profile_charts_tab": "플럭스 차트",
        "profile_heatmap_tab": "히트맵",
        "profile_chart_note": (
            "크기가 큰 대사체를 최대 {count}개까지 표시합니다. "
            "FVA whisker는 두 경계가 모두 기록된 경우에만 표시됩니다."
        ),
        "profile_contribution_basis": (
            "멤버 기준: 군집 가중 직접 멤버↔풀 edge 플럭스 (tidy ≥1.3); "
            "할당된 cross-feeding edge 제외."
        ),
        "profile_clear_delta": "비교 오버레이 지우기",
        "profile_load_complete_run": "완전한 tidy 실행을 불러오면 이 차트가 채워집니다.",
        "profile_omitted_prefix": "제외됨: {warnings}",
        "profile_delta_member_unavailable": (
            "DeltaResult는 외부 플럭스만 기록하므로 멤버 기여는 빈 상태입니다."
        ),
        "profile_delta_active": "비교 오버레이 활성: {baseline}(연함) vs {variant}(진함).",
        "profile_delta_failed": "비교 상태 실패: {diagnostic}",
        "profile_overlay_available": "외부 프로필 탭에 비교 오버레이가 활성화됨",
        "profile_scenario_baseline": "기준: {name}",
        "profile_scenario_variant": "변형: {name}",
        "profile_sandbox_baseline": "Fixture 기준",
        "profile_sandbox_preview": "샌드박스 미리보기",
        "profile_sandbox_commit": "샌드박스 적용",
    },
    "en": {
        "title": "CMIG — Community Metabolic Interaction",
        "explorer": "Project Explorer",
        "models": "Models",
        "scenarios": "Scenarios",
        "runs": "Runs",
        "jobs": "Runtime & Jobs",
        "welcome": "Open a project or import a model.",
        "col_job": "Job",
        "col_kind": "Kind",
        "col_status": "Status",
        "col_progress": "Progress",
        "tab_models": "Models",
        "tab_search": "Search",
        "tab_host": "Host",
        "tab_dynamics": "Dynamics",
        "tab_graph": "Graph",
        "tab_profile": "Profile",
        "tab_community": "Community",
        "tab_medium": "Medium",
        "tab_sweep": "Sweep",
        "tab_sandbox": "Sandbox",
        "tab_compare": "Compare",
        "toolbar_workflow": "Workflow",
        "action_import_model": "Import Model",
        "action_open_run": "Open Run",
        "action_run_fixture": "Run Fixture",
        "action_cancel_job": "Cancel Selected Job",
        "action_show_advanced": "Show Advanced Tools",
        "action_hide_advanced": "Hide Advanced Tools",
        "kind_sandbox_solve": "sandbox solve",
        "kind_fixture_run": "fixture run",
        "kind_host_microbe": "Host-microbe",
        "kind_host_search": "Host-search",
        "kind_gene_ko_search": "Gene KO search",
        "kind_strain_growth": "Strain growth report",
        "kind_ratio_impact": "Ratio impact sweep",
        "kind_dfba": "dFBA",
        "kind_spatial": "Spatial preview",
        "kind_community_solve": "Community solve",
        "kind_sweep": "Sweep",
        "kind_growth_check": "Growth check",
        "kind_search": "Search",
        "ready": "Ready",
        "status_select_job": "Select a running job to cancel.",
        "status_job_already": "Job already {status}: {job_id}",
        "status_cancel_requested": (
            "Cancel requested for {job_id}. The solver cannot be interrupted mid-solve — "
            "this run keeps using CPU until it reaches its next checkpoint. If it has "
            "already written its artifacts it will still be reported as complete."
        ),
        "status_started": "Started {kind}: {job_id}",
        "status_complete": "{kind} complete: {job_id}",
        "status_complete_out": "{kind} complete: {job_id} → {out_dir}",
        "status_model_import_failed": "Model import failed: {error}",
        "status_imported_model": "Imported {model_id}; namespace coverage {coverage:.0f}%",
        "status_run_load_failed": "Run load failed: {error}",
        "status_loaded_run": "Loaded run: {run_dir}{suffix}",
        "status_summary_missing": "{kind} summary not found: {path}",
        "status_load_failed": "{kind} load failed: {error}",
        "status_host_block_missing": (
            "No `host` block in {summary}; host viability cannot be reported for {run_dir}."
        ),
        "status_loaded_host": (
            "Loaded host-microbe BiGG run: {run_dir} ({count} transferred metabolites)"
        ),
        "status_loaded_dfba": "Loaded dFBA run: {run_dir}",
        "status_loaded_spatial": "Loaded spatial preview: {run_dir}",
        "status_fixture_incomplete": "Fixture job not complete: {job_id}",
        "status_fixture_failed": "Fixture failed: {diagnostic}",
        "status_fixture_job": "Fixture job {status}: {job_id}",
        "status_compare_complete": "Scenario compare complete",
        "sweep_title": "Parameter Sweep",
        "sweep_status_ready": (
            "Advanced result view: choose a taxonomy or model folder, configure axes, then run."
        ),
        "sweep_taxonomy_placeholder": "Taxonomy CSV",
        "sweep_browse_taxonomy": "Taxonomy…",
        "sweep_model_dir_placeholder": "Or a folder of user-prepared microbial models",
        "sweep_browse_models": "Model folder…",
        "sweep_taxonomy_label": "Taxonomy",
        "sweep_model_dir_label": "Model source",
        "sweep_mediums_placeholder": (
            "Comma-separated medium CSV/JSON files (blank = model defaults)"
        ),
        "sweep_abundance_placeholder": "Comma-separated abundance CSV/JSON files",
        "sweep_member_sets_placeholder": "Semicolon-separated sets, e.g. A+B;A+C",
        "sweep_bounds_placeholder": "Comma-separated bounds JSON files",
        "sweep_tradeoffs_placeholder": "Comma-separated tradeoff f values",
        "sweep_solvers_placeholder": "Comma-separated solvers",
        "sweep_browse_files": "Files…",
        "sweep_mediums_label": "Mediums",
        "sweep_abundance_label": "Abundance variants",
        "sweep_member_sets_label": "Member sets",
        "sweep_bounds_label": "Bounds variants",
        "sweep_tradeoffs_label": "Tradeoff f",
        "sweep_solvers_label": "Solvers",
        "sweep_assume_bigg": "I reviewed the models and confirm BiGG namespace",
        "sweep_namespace_placeholder": "Or a reviewed namespace-decisions JSON file",
        "sweep_namespace_button": "Decisions…",
        "sweep_fva": "FVA",
        "sweep_fva_metabolites_placeholder": "Optional comma-separated FVA metabolites",
        "sweep_exact_medium": "Exact medium",
        "sweep_allow_unknown_medium": "Allow unknown medium IDs",
        "sweep_fixture_smoke": "Use built-in fixture smoke sweep",
        "sweep_run": "Run Sweep",
        "sweep_col_condition": "Condition",
        "sweep_col_value": "Value",
        "sweep_col_status": "Status",
        "sweep_col_cache": "Cache",
        "sweep_col_medium": "Medium",
        "sweep_col_abundance": "Abundance",
        "sweep_col_members": "Members",
        "sweep_col_bounds": "Bounds",
        "sweep_col_tradeoff": "Tradeoff f",
        "sweep_col_solver": "Solver",
        "sweep_col_diagnostic": "Diagnostic",
        "sweep_select_source": (
            "Select a taxonomy CSV or model folder before running a real sweep."
        ),
        "sweep_one_source": "Choose only one model source: taxonomy CSV or model folder.",
        "sweep_namespace_choice": (
            "Choose one namespace policy: reviewed decisions file or BiGG confirmation."
        ),
        "sweep_namespace_required": (
            "Namespace review required: choose a reviewed decisions file or confirm BiGG."
        ),
        "sweep_started_real": "real sweep started: {job_id}",
        "sweep_started_fixture": "fixture smoke sweep started: {job_id}",
        "sweep_complete_detail": (
            "{mode} sweep complete: {count} runs → {out_dir}{warnings}"
        ),
        "sweep_failed_detail": "{mode} sweep {status}: {error}{artifact_note}",
        "sweep_failed_artifacts": " Displaying {count} recorded conditions from its artifacts.",
        "sweep_mode_real": "real",
        "sweep_mode_fixture": "fixture",
        "sweep_dialog_taxonomy": "Select Sweep Taxonomy CSV",
        "sweep_dialog_models": "Select Sweep Model Folder",
        "sweep_dialog_mediums": "Select Medium Variants",
        "sweep_dialog_abundances": "Select Abundance Variants",
        "sweep_dialog_bounds": "Select Bounds Variants",
        "sweep_dialog_namespace": "Select Namespace Decisions",
        "sweep_filter_csv": "CSV (*.csv);;All files (*)",
        "sweep_filter_medium": "Medium files (*.csv *.json);;All files (*)",
        "sweep_filter_abundance": "Abundance files (*.csv *.json);;All files (*)",
        "sweep_filter_bounds": "Bounds files (*.json);;All files (*)",
        "sweep_filter_json": "JSON (*.json);;All files (*)",
        "sweep_cli_failed": "sweep command failed with rc={rc}",
        "profile_net_chart_title": "Net exchange flux (+ secretion / − uptake)",
        "profile_delta_overlay_title": "baseline / variant overlay",
        "profile_no_fluxes": "No measured profile fluxes",
        "profile_delta_legend": "light = {baseline}; solid = {variant}",
        "profile_member_chart_title": "Per-member contribution (direct flux × abundance)",
        "profile_no_member_contributions": "No abundance-weighted member contributions",
        "profile_heatmap_title": "Flux heatmap (+ secretion / − uptake)",
        "profile_heatmap_blank_note": "Blank = flux not recorded (never zero-filled).",
        "profile_heatmap_empty": "No flux matrix available",
        "profile_current_scenario": "Current",
        "profile_charts_tab": "Flux charts",
        "profile_heatmap_tab": "Heatmap",
        "profile_chart_note": (
            "Charts show up to {count} metabolites by magnitude. "
            "FVA whiskers appear only when both bounds are recorded."
        ),
        "profile_contribution_basis": CONTRIBUTION_BASIS_NOTE,
        "profile_clear_delta": "Clear comparison overlay",
        "profile_load_complete_run": "Load a complete tidy run to populate this chart.",
        "profile_omitted_prefix": "Omitted: {warnings}",
        "profile_delta_member_unavailable": (
            "Member contributions are blank because DeltaResult records external flux only."
        ),
        "profile_delta_active": (
            "Comparison overlay active: {baseline} (light) vs {variant} (solid)."
        ),
        "profile_delta_failed": "Comparison status is failed: {diagnostic}",
        "profile_overlay_available": "comparison overlay active in External Profile",
        "profile_scenario_baseline": "Baseline: {name}",
        "profile_scenario_variant": "Variant: {name}",
        "profile_sandbox_baseline": "Fixture baseline",
        "profile_sandbox_preview": "Sandbox preview",
        "profile_sandbox_commit": "Sandbox commit",
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
            [tr["col_job"], tr["col_kind"], tr["col_status"], tr["col_progress"]]
        )
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

    def __init__(self, runner: JobRunner | None = None, lang: str = "en") -> None:
        super().__init__()
        self.lang = lang if lang in I18N else "en"
        self.tr_map = I18N[self.lang]
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
        #: sweep job id -> (artifact directory, "real" | "fixture")
        self._sweep_jobs: dict[str, tuple[Path, str]] = {}
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
        self.profile_view = ExternalProfileView(strings=self.tr_map)
        self.graph_view = InteractionGraphView()
        self.graph_gate_badge = GateBadge(lang=self.lang)
        self.graph_tab = QWidget()
        graph_layout = QVBoxLayout(self.graph_tab)
        graph_layout.setContentsMargins(0, 0, 0, 0)
        graph_layout.addWidget(self.graph_gate_badge)
        graph_layout.addWidget(self.graph_view)
        self.sweep_view = SweepView(runner=self.runner, strings=self.tr_map)
        self.sandbox_view = ConstraintSandboxView()
        self.scenario_compare = ScenarioCompareView()
        self.search_view = SearchView()
        self.host_view = HostImpactView()
        self.dynamics_view = DfbaSpatialView()
        self._primary_tabs = [
            (self.tr_map["tab_models"], self.model_manager),
            (self.tr_map["tab_search"], self.search_view),
            (self.tr_map["tab_host"], self.host_view),
            (self.tr_map["tab_dynamics"], self.dynamics_view),
            (self.tr_map["tab_graph"], self.graph_tab),
            (self.tr_map["tab_profile"], self.profile_view),
        ]
        self._advanced_tabs = [
            (self.tr_map["tab_community"], self.community_builder),
            (self.tr_map["tab_medium"], self.medium_editor),
            (self.tr_map["tab_sweep"], self.sweep_view),
            (self.tr_map["tab_sandbox"], self.sandbox_view),
            (self.tr_map["tab_compare"], self.scenario_compare),
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

    def _message(self, key: str, **values: Any) -> str:
        """Format one localized UI message from the active language catalogue."""
        return self.tr_map[key].format(**values)

    def _show_status(self, key: str, **values: Any) -> None:
        self.statusBar().showMessage(self._message(key, **values))

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
        toolbar = self.addToolBar(self.tr_map["toolbar_workflow"])
        self.import_model_action = QAction(self.tr_map["action_import_model"], self)
        self.import_model_action.triggered.connect(self._import_model_dialog)
        self.import_model_action.setShortcut(QKeySequence("Ctrl+I"))
        self.open_run_action = QAction(self.tr_map["action_open_run"], self)
        self.open_run_action.triggered.connect(self._open_run_dialog)
        self.open_run_action.setShortcut(QKeySequence.StandardKey.Open)
        self.run_fixture_action = QAction(self.tr_map["action_run_fixture"], self)
        self.run_fixture_action.triggered.connect(self._run_fixture_dialog)
        self.run_fixture_action.setShortcut(QKeySequence("Ctrl+R"))
        self.cancel_job_action = QAction(self.tr_map["action_cancel_job"], self)
        self.cancel_job_action.triggered.connect(self._cancel_selected_job)
        self.cancel_job_action.setShortcut(QKeySequence("Ctrl+."))
        self.advanced_tools_action = QAction(self.tr_map["action_show_advanced"], self)
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
            self.tr_map["action_hide_advanced"] if visible else self.tr_map["action_show_advanced"]
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
        self.sweep_view.browse_taxonomy_btn.clicked.connect(self._browse_sweep_taxonomy)
        self.sweep_view.browse_model_dir_btn.clicked.connect(self._browse_sweep_model_dir)
        self.sweep_view.browse_mediums_btn.clicked.connect(self._browse_sweep_mediums)
        self.sweep_view.browse_abundance_btn.clicked.connect(self._browse_sweep_abundances)
        self.sweep_view.browse_bounds_btn.clicked.connect(self._browse_sweep_bounds)
        self.sweep_view.browse_namespace_btn.clicked.connect(self._browse_sweep_namespace)
        self.sweep_view.run_btn.clicked.connect(self.run_sweep_from_view)
        self.medium_editor.browse_model_btn.clicked.connect(self._browse_medium_model)
        self.medium_editor.check_growth_btn.clicked.connect(self.run_medium_growth_check)
        self.scenario_compare.browse_a_btn.clicked.connect(self._browse_scenario_run_a)
        self.scenario_compare.browse_b_btn.clicked.connect(self._browse_scenario_run_b)
        self.scenario_compare.compare_btn.clicked.connect(self.run_scenario_compare)

    def _cancel_selected_job(self) -> None:
        job_id = self.jobs_panel.selected_job_id()
        if not job_id:
            self._show_status("status_select_job")
            return
        job = self.runner.poll(job_id)
        if job.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
            self._show_status("status_job_already", status=job.status.value, job_id=job_id)
            return
        self.runner.cancel(job_id)
        self.bridge.cancelling.add(job_id)
        self.bridge.refresh()
        # Cancellation is cooperative and GUI jobs only check it at run boundaries, so saying
        # just "Cancel requested" let the user believe the solve had stopped when it had not.
        self._show_status("status_cancel_requested", job_id=job_id)

    def _open_explorer_item(self, item: QTreeWidgetItem, _column: int) -> None:
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if not path:
            return
        self.load_run_dir(str(path))

    def _browse_search_model_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Model Pool Folder")
        if path:
            self.search_view.model_dir_input.setText(path)

    def _browse_sweep_taxonomy(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr_map["sweep_dialog_taxonomy"],
            "",
            self.tr_map["sweep_filter_csv"],
        )
        if path:
            self.sweep_view.taxonomy_input.setText(path)

    def _browse_sweep_model_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, self.tr_map["sweep_dialog_models"])
        if path:
            self.sweep_view.model_dir_input.setText(path)

    def _browse_sweep_files(self, editor: Any, title_key: str, file_filter: str) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            self.tr_map[title_key],
            "",
            file_filter,
        )
        if paths:
            editor.setText(",".join(paths))

    def _browse_sweep_mediums(self) -> None:
        self._browse_sweep_files(
            self.sweep_view.mediums_input,
            "sweep_dialog_mediums",
            self.tr_map["sweep_filter_medium"],
        )

    def _browse_sweep_abundances(self) -> None:
        self._browse_sweep_files(
            self.sweep_view.abundance_variants_input,
            "sweep_dialog_abundances",
            self.tr_map["sweep_filter_abundance"],
        )

    def _browse_sweep_bounds(self) -> None:
        self._browse_sweep_files(
            self.sweep_view.bounds_variants_input,
            "sweep_dialog_bounds",
            self.tr_map["sweep_filter_bounds"],
        )

    def _browse_sweep_namespace(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr_map["sweep_dialog_namespace"],
            "",
            self.tr_map["sweep_filter_json"],
        )
        if path:
            self.sweep_view.namespace_decisions_input.setText(path)

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
        self._show_status("status_started", kind=self.tr_map["kind_sandbox_solve"], job_id=jid)
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
            self._show_status("status_model_import_failed", error=e)
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
        self._show_status(
            "status_imported_model",
            model_id=summary.model_id,
            coverage=ns["coverage_pct"],
        )
        return True

    def load_run_dir(self, path: str | Path) -> None:
        """Load a tidy community run into both first-class Graph and Profile tabs."""
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
            self.graph_view.clear()
            self.graph_gate_badge.set_unavailable()
            self.profile_view.load_profile([])
            self.profile_view.load_targets(None)
            self._show_status("status_run_load_failed", error=e)
            return
        manifest_path = run_dir / "manifest.json"
        self.current_manifest = (
            json.loads(manifest_path.read_text()) if manifest_path.exists() else None
        )
        self.current_graph_payload = graph_payload(bundle)
        self.graph_view.set_bundle(bundle)
        provenance = (
            self.current_manifest.get("provenance", {})
            if isinstance(self.current_manifest, dict)
            else {}
        )
        namespace = provenance.get("namespace", {}) if isinstance(provenance, dict) else {}
        policy = namespace.get("policy") if isinstance(namespace, dict) else None
        self.graph_gate_badge.set_recorded_policy(None if policy is None else str(policy))
        self.profile_view.load_bundle(bundle)
        self.explorer.add_run(run_dir.name, run_dir)
        self.tabs.setCurrentWidget(self.profile_view)
        run_hash = None if self.current_manifest is None else self.current_manifest.get("run_hash")
        suffix = "" if run_hash is None else f" (run_hash {str(run_hash)[:12]})"
        self._show_status("status_loaded_run", run_dir=run_dir, suffix=suffix)

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
            self._show_status(
                "status_summary_missing",
                kind=self.tr_map["kind_host_microbe"],
                path=summary_path,
            )
            return False
        try:
            payload = json.loads(summary_path.read_text())
            if "microbial_secretion" not in payload:
                secretion_path = run_dir / "microbial_secretion.csv"
                if secretion_path.exists():
                    with open(secretion_path, newline="") as f:
                        payload["microbial_secretion"] = {
                            str(row["metabolite"]): float(row["flux"]) for row in csv.DictReader(f)
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
                        uptake_rows.append(
                            InterfaceFlux(
                                exchange_id=f"EX_{met}_e",
                                interface="bigg_external",
                                metabolite=met,
                                flux=-uptake,
                                label="uptake",
                            )
                        )
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
            self._show_status("status_load_failed", kind=self.tr_map["kind_host_microbe"], error=e)
            return False

        if not isinstance(host_payload, dict) or "viable" not in host_payload:
            # Absence of the host block is missing data, not a biological finding. Defaulting
            # to viable=False rendered a red "non-viable — microbiome support insufficient",
            # i.e. a scientific conclusion manufactured from an incomplete file.
            self._show_status(
                "status_host_block_missing",
                summary=summary_path.name,
                run_dir=run_dir,
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
        self.current_host_microbe_dir = run_dir  # only after a successful parse
        self.explorer.add_run(run_dir.name, run_dir)
        self.tabs.setCurrentWidget(self.host_view)
        self._show_status("status_loaded_host", run_dir=run_dir, count=len(transfer))
        return True

    def load_dfba_dir(self, path: str | Path) -> bool:
        run_dir = Path(path).resolve()
        summary_path = run_dir / "dfba_summary.json"
        if not summary_path.exists():
            self._show_status(
                "status_summary_missing", kind=self.tr_map["kind_dfba"], path=summary_path
            )
            return False
        try:
            payload = json.loads(summary_path.read_text())
            if not isinstance(payload, dict):
                raise ValueError("dfba_summary.json is not a JSON object")
        except (OSError, ValueError, json.JSONDecodeError) as e:
            self._show_status("status_load_failed", kind=self.tr_map["kind_dfba"], error=e)
            return False
        self.dynamics_view.load_dfba_summary(payload, run_dir=run_dir)
        self.explorer.add_run(run_dir.name, run_dir)
        self.tabs.setCurrentWidget(self.dynamics_view)
        self._show_status("status_loaded_dfba", run_dir=run_dir)
        return True

    def load_spatial_dir(self, path: str | Path) -> bool:
        run_dir = Path(path).resolve()
        summary_path = run_dir / "spatial_summary.json"
        if not summary_path.exists():
            self._show_status(
                "status_summary_missing", kind=self.tr_map["kind_spatial"], path=summary_path
            )
            return False
        try:
            payload = json.loads(summary_path.read_text())
            if not isinstance(payload, dict):
                raise ValueError("spatial_summary.json is not a JSON object")
        except (OSError, ValueError, json.JSONDecodeError) as e:
            self._show_status("status_load_failed", kind=self.tr_map["kind_spatial"], error=e)
            return False
        self.dynamics_view.load_spatial_summary(payload, run_dir=run_dir)
        self.explorer.add_run(run_dir.name, run_dir)
        self.tabs.setCurrentWidget(self.dynamics_view)
        self._show_status("status_loaded_spatial", run_dir=run_dir)
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
        self._show_status("status_started", kind=self.tr_map["kind_fixture_run"], job_id=jid)
        return jid

    def load_completed_fixture(self, job_id: str) -> bool:
        """완료된 fixture job 산출물을 Profile 탭으로 로드한다."""
        job = self.runner.poll(job_id)
        if job.status is not JobStatus.DONE or job.result is None:
            self._show_status("status_fixture_incomplete", job_id=job_id)
            return False
        outcome = job.result
        if outcome.status == "ok" and outcome.manifest_path is not None:
            self.load_run_dir(outcome.manifest_path.parent)
            return True
        self._show_status("status_fixture_failed", diagnostic=outcome.diagnostic)
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
            self.search_view.status.setText("Select a model folder before running product search.")
            return ""

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            argv = [
                "search",
                "--model-dir",
                model_dir,
                "--target",
                target,
                "--strategy",
                strategy,
                "--min-size",
                min_size,
                "--max-size",
                max_size,
                "--top-k",
                top_k,
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
                "--host",
                str(host),
                "--model-dir",
                str(model_dir),
                "--tradeoff-f",
                f"{float(request['tradeoff_f']):.6g}",
                "--microbial-biomass-gdw",
                f"{float(request['microbial_biomass_gdw']):.12g}",
                "--host-biomass-gdw",
                f"{float(request['host_biomass_gdw']):.12g}",
                "--biomass-basis-kind",
                str(request["biomass_basis_kind"]),
                "--biomass-basis-source",
                str(request["biomass_basis_source"]),
                "--out",
                str(out_dir),
            ]
            if request["recursive"]:
                argv.append("--recursive")
            if request["keep_host_uptake"]:
                argv.append("--keep-host-uptake")
            if request["include_currency_metabolites"]:
                argv.append("--include-currency-metabolites")
            if request["allow_unknown_medium"]:
                argv.append("--allow-unknown-medium")
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
        self._show_status("status_started", kind=self.tr_map["kind_host_microbe"], job_id=jid)
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
                "--host",
                str(host),
                "--model-dir",
                str(model_dir),
                "--target",
                str(request["search_target"]),
                "--metric",
                str(request["search_metric"]),
                "--min-size",
                str(request["min_size"]),
                "--max-size",
                str(request["max_size"]),
                "--tradeoff-f",
                f"{float(request['tradeoff_f']):.6g}",
                "--microbial-biomass-gdw",
                f"{float(request['microbial_biomass_gdw']):.12g}",
                "--host-biomass-gdw",
                f"{float(request['host_biomass_gdw']):.12g}",
                "--biomass-basis-kind",
                str(request["biomass_basis_kind"]),
                "--biomass-basis-source",
                str(request["biomass_basis_source"]),
                "--out",
                str(out_dir),
            ]
            if request["recursive"]:
                argv.append("--recursive")
            if request["keep_host_uptake"]:
                argv.append("--keep-host-uptake")
            if request["include_currency_metabolites"]:
                argv.append("--include-currency-metabolites")
            if request["allow_unknown_medium"]:
                argv.append("--allow-unknown-medium")
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
        self._show_status("status_started", kind=self.tr_map["kind_host_search"], job_id=jid)
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
            self.search_view.status.setText("Model folder and KO members are required.")
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
        out_dir = Path(tempfile.mkdtemp(prefix="cmig-gene-ko-", dir=_search_temp_root())).resolve()

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            argv = [
                "gene-ko-search",
                "--model-dir",
                model_dir,
                "--members",
                members,
                "--target",
                target,
                "--max-genes",
                max_genes,
                "--top-k",
                top_k,
                "--out",
                str(out_dir),
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
        self._show_status("status_started", kind=self.tr_map["kind_gene_ko_search"], job_id=jid)
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
                "--model-dir",
                model_dir,
                "--out",
                str(out_dir),
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
        self._strain_growth_jobs[jid] = (out_dir, self.search_view.request_fields("strain_growth"))
        self.search_view.run_growth_btn.setEnabled(False)
        self.search_view.status.setText(f"strain growth started: {jid}")
        self._show_status("status_started", kind=self.tr_map["kind_strain_growth"], job_id=jid)
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
                "--model-dir",
                model_dir,
                "--member",
                member,
                "--fractions",
                fractions or "0.1,0.25,0.5,0.75",
                "--target",
                target,
                "--out",
                str(out_dir),
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
            out_dir,
            self.search_view.request_fields("abundance_impact"),
        )
        self.search_view.run_abundance_btn.setEnabled(False)
        self.search_view.status.setText(f"ratio impact started: {jid}")
        self._show_status("status_started", kind=self.tr_map["kind_ratio_impact"], job_id=jid)
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
                "--model",
                model,
                "--initial",
                str(request["initial"]),
                "--t-end",
                f"{float(request['t_end']):.6g}",
                "--dt",
                f"{float(request['dt']):.6g}",
                "--initial-biomass",
                f"{float(request['initial_biomass']):.6g}",
                "--out",
                str(out_dir),
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
        self._show_status("status_started", kind=self.tr_map["kind_dfba"], job_id=jid)
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
                "--metabolite",
                str(request["metabolite"]),
                "--width",
                str(request["width"]),
                "--height",
                str(request["height"]),
                "--steps",
                str(request["steps"]),
                "--dt",
                f"{float(request['dt']):.6g}",
                "--diffusion",
                f"{float(request['diffusion']):.6g}",
                "--source-edge",
                str(request["source_edge"]),
                "--sink-edge",
                str(request["sink_edge"]),
                "--out",
                str(out_dir),
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
        self._show_status("status_started", kind=self.tr_map["kind_spatial"], job_id=jid)
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
                "--taxonomy",
                str(tax_path),
                "--tradeoff-f",
                f"{tradeoff_f:.6g}",
                "--out",
                str(out_dir),
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
        self._show_status("status_started", kind=self.tr_map["kind_community_solve"], job_id=jid)
        return jid

    def run_sweep_from_view(self) -> str:
        """Dispatch the default real workflow or the explicitly selected fixture smoke path."""
        if self.sweep_view.fixture_check.isChecked():
            return self.run_sweep_fixture()
        return self.run_sweep()

    def run_sweep(self) -> str:
        """Run the user ``cmig sweep`` workflow through the in-process CLI job pattern."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        request = self.sweep_view.request()
        taxonomy = str(request["taxonomy"])
        model_dir = str(request["model_dir"])
        if not taxonomy and not model_dir:
            self.sweep_view.status.setText(self.tr_map["sweep_select_source"])
            return ""
        if taxonomy and model_dir:
            self.sweep_view.status.setText(self.tr_map["sweep_one_source"])
            return ""
        decisions = str(request["namespace_decisions"])
        assumed = bool(request["assume_bigg"])
        if decisions and assumed:
            self.sweep_view.status.setText(self.tr_map["sweep_namespace_choice"])
            return ""
        if not decisions and not assumed:
            self.sweep_view.status.setText(self.tr_map["sweep_namespace_required"])
            return ""

        out_dir = Path(tempfile.mkdtemp(prefix="cmig-sweep-", dir=_search_temp_root())).resolve()

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            taxonomy_path = Path(taxonomy) if taxonomy else out_dir / "taxonomy.csv"
            if model_dir:
                from cmig.core.model_pool import taxonomy_from_model_dir

                discovered = taxonomy_from_model_dir(model_dir, recursive=False)
                discovered.to_csv(taxonomy_path, index=False)
            argv = [
                "sweep",
                "--taxonomy",
                str(taxonomy_path),
                "--tradeoff-fs",
                str(request["tradeoff_fs"] or "0.3,0.5"),
                "--solvers",
                str(request["solvers"] or "gurobi"),
                "--metric",
                "growth",
                "--out",
                str(out_dir),
            ]
            for key, flag in (
                ("mediums", "--mediums"),
                ("abundance_variants", "--abundance-variants"),
                ("member_sets", "--member-sets"),
                ("bounds_variants", "--bounds-variants"),
                ("fva_metabolites", "--fva-metabolites"),
            ):
                if request[key]:
                    argv.extend([flag, str(request[key])])
            if assumed:
                argv.append("--assume-bigg-namespace")
            else:
                argv.extend(["--namespace-decisions", decisions])
            if request["fva"]:
                argv.append("--fva")
            if request["exact_medium"]:
                argv.append("--exact-medium")
            if request["allow_unknown_medium"]:
                argv.append("--allow-unknown-medium")
            rc = main(argv)
            if rc != 0:
                # A scientific failure deliberately exits 3 after writing diagnostic-bearing
                # sweep artifacts. The Job remains failed, while the poller still loads those
                # rows so the GUI is not quieter than the CLI.
                raise RuntimeError(self._message("sweep_cli_failed", rc=rc))
            _finish_after_artifacts(ctx)
            summary_path = out_dir / "sweep_summary.json"
            summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
            return {"out_dir": str(out_dir), "summary": summary}

        jid = self.submit_job("sweep", _job)
        self._sweep_jobs[jid] = (out_dir, "real")
        self.sweep_view.run_btn.setEnabled(False)
        self.sweep_view.status.setText(self._message("sweep_started_real", job_id=jid))
        self._show_status("status_started", kind=self.tr_map["kind_sweep"], job_id=jid)
        return jid

    def run_sweep_fixture(self) -> str:
        """Preserved fixture-only tradeoff/solver smoke path (`cmig sweep-fixture`)."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        tradeoff_fs = self.sweep_view.tradeoff_fs_input.text().strip() or "0.3,0.5"
        solvers = self.sweep_view.solvers_input.text().strip() or "gurobi"
        out_dir = Path(tempfile.mkdtemp(prefix="cmig-sweep-", dir=_search_temp_root())).resolve()

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            argv = [
                "sweep-fixture",
                "--tradeoff-fs",
                tradeoff_fs,
                "--solvers",
                solvers,
                "--metric",
                "growth",
                "--out",
                str(out_dir),
            ]
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"sweep-fixture failed with rc={rc}")
            _finish_after_artifacts(ctx)
            return {"out_dir": str(out_dir)}

        jid = self.submit_job("sweep_fixture", _job)
        self._sweep_jobs[jid] = (out_dir, "fixture")
        self.sweep_view.run_btn.setEnabled(False)
        self.sweep_view.status.setText(self._message("sweep_started_fixture", job_id=jid))
        self._show_status("status_started", kind=self.tr_map["kind_sweep"], job_id=jid)
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
                "--model-dir",
                str(model_dir),
                "--out",
                str(out_dir),
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
        self._show_status("status_started", kind=self.tr_map["kind_growth_check"], job_id=jid)
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
        self.profile_view.show_delta_overlay(
            delta,
            baseline_label=self._message("profile_scenario_baseline", name=path_a.name),
            variant_label=self._message("profile_scenario_variant", name=path_b.name),
        )
        self.scenario_compare.status.setText(
            f"compare complete: {dir_a} vs {dir_b} · {self.tr_map['profile_overlay_available']}"
        )
        self._show_status("status_compare_complete")

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
                self.sandbox_view.status.setText(f"Sandbox {job.status.value}: {job.error or jid}")
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
                variant_label = self.tr_map["profile_sandbox_commit"]
            else:
                self.sandbox_view.show_preview(result.delta, constraint)
                variant_label = self.tr_map["profile_sandbox_preview"]
            self.profile_view.show_delta_overlay(
                result.delta,
                baseline_label=self.tr_map["profile_sandbox_baseline"],
                variant_label=variant_label,
            )
            self.sandbox_view.status.setText(
                f"{self.sandbox_view.status.text()} · {self.tr_map['profile_overlay_available']}"
            )
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
                self._show_status("status_fixture_job", status=job.status.value, job_id=jid)
        for jid, (out_dir, requested) in list(self._search_jobs.items()):
            job = self.runner.poll(jid)
            if job.status is JobStatus.DONE and isinstance(job.result, dict):
                self._search_jobs.pop(jid, None)
                self.current_search_dir = out_dir
                self.search_view.load_summary(
                    job.result,
                    run_dir=out_dir,
                    request_note=self.search_view.superseded_note(requested, "search"),
                )
                self.search_view.run_btn.setEnabled(True)
                self.tabs.setCurrentWidget(self.search_view)
                self._register_run_output(out_dir)
                self._show_status(
                    "status_complete_out",
                    kind=self.tr_map["kind_search"],
                    job_id=jid,
                    out_dir=out_dir,
                )
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
                self._show_status(
                    "status_complete", kind=self.tr_map["kind_host_microbe"], job_id=jid
                )
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
                    summary,
                    run_dir=out_dir,
                    request_note=self.search_view.superseded_note(requested, "host_search"),
                )
                self.tabs.setCurrentWidget(self.search_view)
                self._register_run_output(out_dir)
                self._show_status(
                    "status_complete_out",
                    kind=self.tr_map["kind_host_search"],
                    job_id=jid,
                    out_dir=out_dir,
                )
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
                    summary,
                    run_dir=out_dir,
                    request_note=self.search_view.superseded_note(requested, "gene_ko"),
                )
                self.tabs.setCurrentWidget(self.search_view)
                self._register_run_output(out_dir)
                self._show_status(
                    "status_complete_out",
                    kind=self.tr_map["kind_gene_ko_search"],
                    job_id=jid,
                    out_dir=out_dir,
                )
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
                    summary,
                    run_dir=out_dir,
                    request_note=self.search_view.superseded_note(requested, "strain_growth"),
                )
                self.tabs.setCurrentWidget(self.search_view)
                self._register_run_output(out_dir)
                self._show_status(
                    "status_complete_out",
                    kind=self.tr_map["kind_strain_growth"],
                    job_id=jid,
                    out_dir=out_dir,
                )
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
                    summary,
                    run_dir=out_dir,
                    request_note=self.search_view.superseded_note(requested, "abundance_impact"),
                )
                self.tabs.setCurrentWidget(self.search_view)
                self._register_run_output(out_dir)
                self._show_status(
                    "status_complete_out",
                    kind=self.tr_map["kind_ratio_impact"],
                    job_id=jid,
                    out_dir=out_dir,
                )
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
                self._show_status("status_complete", kind=self.tr_map["kind_dfba"], job_id=jid)
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
                self._show_status("status_complete", kind=self.tr_map["kind_spatial"], job_id=jid)
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
                manifest = (
                    (job.result or {}).get("manifest", {}) if isinstance(job.result, dict) else {}
                )
                run_hash = manifest.get("run_hash") if isinstance(manifest, dict) else None
                suffix = f" (run_hash {str(run_hash)[:12]})" if run_hash else ""
                self.community_builder.status.setText(f"community solve complete{suffix}")
                self.load_run_dir(out_dir)
                self._show_status(
                    "status_complete",
                    kind=self.tr_map["kind_community_solve"],
                    job_id=jid,
                )
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._community_jobs.pop(jid, None)
                self.community_builder.run_btn.setEnabled(True)
                self.community_builder.status.setText(
                    f"community solve {job.status.value}: {job.error or jid}"
                )
        for jid, (out_dir, mode) in list(self._sweep_jobs.items()):
            job = self.runner.poll(jid)
            if job.status is JobStatus.DONE:
                self._sweep_jobs.pop(jid, None)
                self.sweep_view.run_btn.setEnabled(True)
                rows = _load_sweep_rows(out_dir / "sweep.parquet")
                self.sweep_view.load_results(rows)
                summary_path = out_dir / "sweep_summary.json"
                summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
                warnings = summary.get("warnings", []) if isinstance(summary, dict) else []
                warning_note = ""
                if warnings:
                    warning_note = " · " + "; ".join(str(warning) for warning in warnings)
                self.sweep_view.status.setText(
                    self._message(
                        "sweep_complete_detail",
                        mode=self.tr_map[f"sweep_mode_{mode}"],
                        count=len(rows),
                        out_dir=out_dir,
                        warnings=warning_note,
                    )
                )
                self._register_run_output(out_dir)
                self._show_status(
                    "status_complete_out",
                    kind=self.tr_map["kind_sweep"],
                    job_id=jid,
                    out_dir=out_dir,
                )
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._sweep_jobs.pop(jid, None)
                self.sweep_view.run_btn.setEnabled(True)
                rows = _load_sweep_rows(out_dir / "sweep.parquet")
                if rows:
                    self.sweep_view.load_results(rows)
                    self._register_run_output(out_dir)
                artifact_note = (
                    self._message("sweep_failed_artifacts", count=len(rows)) if rows else ""
                )
                self.sweep_view.status.setText(
                    self._message(
                        "sweep_failed_detail",
                        mode=self.tr_map[f"sweep_mode_{mode}"],
                        status=job.status.value,
                        error=job.error or jid,
                        artifact_note=artifact_note,
                    )
                )
        for jid, out_dir in list(self._medium_growth_jobs.items()):
            job = self.runner.poll(jid)
            if job.status is JobStatus.DONE and isinstance(job.result, dict):
                self._medium_growth_jobs.pop(jid, None)
                self.medium_editor.check_growth_btn.setEnabled(True)
                self._register_run_output(out_dir)
                members = job.result.get("members", [])
                if members and isinstance(members[0], dict):
                    growth = members[0].get("single_growth")
                    status = members[0].get("single_status", members[0].get("community_status", ""))
                    growth_text = "—" if growth is None else f"{growth:.4g}"
                    self.medium_editor.growth_label.setText(f"growth: {growth_text} ({status})")
                else:
                    self.medium_editor.growth_label.setText(
                        "growth check complete (no result rows)"
                    )
                self._show_status(
                    "status_complete", kind=self.tr_map["kind_growth_check"], job_id=jid
                )
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
        rows.append(
            {
                "members": item.get("members", []),
                "score": item.get("score"),
                "target_flux": item.get("target_transfer"),
                "community_growth": item.get("community_growth"),
                "status": item.get("evaluation_status", item.get("host_status", "")),
                "diagnostic": item.get("diagnostic"),
            }
        )
    return {
        "target": target,
        "strategy": f"host-search/{payload.get('metric', '')}",
        "top_ranked": rows,
        # Forward CLI warnings verbatim — the GUI is not allowed to be quieter than the CLI.
        "warnings": list(payload.get("warnings") or []),
        "column_labels": [
            "Members",
            "Target",
            "Score",
            "Target transfer (mmol gDW⁻¹ h⁻¹)",
            "Community growth (h⁻¹)",
            "FVA Range",
            "Status",
        ],
    }


def _gene_ko_summary_for_search_view(payload: dict[str, Any]) -> dict[str, Any]:
    """Adapt gene KO output to the existing SearchView ranking table contract."""
    target = str(payload.get("target", ""))
    rows: list[dict[str, Any]] = []
    for item in payload.get("top_ranked", []):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "members": [f"{item.get('member', '')}:{item.get('gene', '')}"],
                # SearchView columns are absolute Score/Flux/Growth; feed the absolute fields
                # (deltas live in the figure + CSV/JSON) so the headers match the values shown.
                "score": item.get("score"),
                "target_flux": item.get("target_flux"),
                "community_growth": item.get("community_growth"),
                "status": item.get("evaluation_status", item.get("status", "")),
                "diagnostic": item.get("diagnostic"),
            }
        )
    return {
        "target": target,
        "strategy": f"{payload.get('ko_level', 'gene')}-ko",
        "top_ranked": rows,
        # Forward CLI warnings (truncation / random selection) so the GUI status bar surfaces
        # them too — never silently drop them (the honesty fix must hold on the GUI path).
        "warnings": list(payload.get("warnings") or []),
        "column_labels": [
            "Member:gene",
            "Target",
            "KO score",
            "Target flux (mmol gDW⁻¹ h⁻¹)",
            "Community growth (h⁻¹)",
            "FVA Range",
            "Status",
        ],
    }


def _strain_growth_summary_for_search_view(payload: dict[str, Any]) -> dict[str, Any]:
    """Adapt strain-growth output to the existing SearchView ranking table contract."""
    rows: list[dict[str, Any]] = []
    for item in payload.get("members", []):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "members": [item.get("member", "")],
                "score": item.get("community_member_growth"),
                "target_flux": item.get("single_growth"),
                "community_growth": item.get("community_growth"),
                "status": item.get("community_status", item.get("single_status", "")),
                "diagnostic": item.get("diagnostic"),
            }
        )
    return {
        "target": "growth",
        "strategy": "strain-growth",
        "top_ranked": rows,
        "warnings": list(payload.get("warnings") or []),
        # Both quantities here are growth rates in h⁻¹; the default "Flux" header implied
        # mmol gDW⁻¹ h⁻¹ and was the concrete misread risk.
        "column_labels": [
            "Member",
            "Quantity",
            "Community member growth (h⁻¹)",
            "Single growth (h⁻¹)",
            "Community growth (h⁻¹)",
            "FVA Range",
            "Status",
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
        label = (
            f"{target_member}@{abundance:.3g}"
            if isinstance(abundance, (int, float))
            else (f"{target_member}@{abundance}")
        )
        # The member's own exchange and the community's net exchange can disagree completely
        # (7.14 vs 0.0 on real output). Showing only the member value under a column headed
        # "Flux" next to "Target = ac" made the GUI ranking contradict the community result,
        # so both are surfaced side by side under labels that say which is which.
        community_exchange = item.get("community_target_exchange")
        rows.append(
            {
                "members": [label],
                "score": item.get("target_influence_share"),
                "target_flux": item.get("target_member_exchange"),
                "community_growth": item.get("community_growth"),
                "aux_text": "—"
                if community_exchange is None
                else f"{float(community_exchange):.4g}",
                "status": item.get("status", ""),
                "diagnostic": item.get("diagnostic"),
            }
        )
    return {
        "target": target,
        "strategy": "abundance-impact",
        "top_ranked": rows,
        "warnings": list(payload.get("warnings") or []),
        "column_labels": [
            "Member@abundance",
            "Target",
            "Influence share (dimensionless)",
            "Member exchange (mmol gDW⁻¹ h⁻¹)",
            "Community growth (h⁻¹)",
            "Community exchange (mmol gDW⁻¹ h⁻¹)",
            "Status",
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
        axis_values = {
            "medium_variant": record.get("axis_medium_variant"),
            "abundance": record.get("axis_abundance"),
            "member_set": record.get("axis_member_set"),
            "bounds": record.get("axis_bounds"),
            "tradeoff_f": record.get("axis_tradeoff_f"),
            "solver": record.get("axis_solver"),
        }
        rows.append(
            SweepRow(
                condition_id=str(record.get("condition_id", "")),
                axis_values=axis_values,
                metric=str(record.get("metric", "")),
                value=record.get("value"),
                run_hash=str(record.get("run_hash", "")),
                status=str(record.get("status", "")),
                diagnostic=record.get("diagnostic"),
                cache_hit=bool(record.get("cache_hit", False)),
            )
        )
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
        str(row["metabolite"]): float(row["net_flux"]) for row in bundle.profile.to_pylist()
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
        external_exchange=external_exchange,
        members=members,
        status=status,
        objective=objective,
    )


def build_main_window(runner: JobRunner | None = None, lang: str = "en") -> CmigMainWindow:
    """메인 윈도우 팩토리(offscreen 검증·진입점)."""
    return CmigMainWindow(runner=runner, lang=lang)
