"""CMIG App Shell — PySide6 작업 공간 데스크톱 셸.

Design Ref: docs/superpowers/specs/2026-10-13-gui-workspace-phase1-design.md §5.
Plan SC: SC-AP1~AP6.

QMainWindow 작업 공간(사이드바 | 가운데 화면 | 상세 패널, 아래 작업 창) + 표준 메뉴·툴바 +
JobRunner→Qt bridge(jobs_bridge) + i18n 카탈로그 + 상태바. service(Qt 비의존) 소비. offscreen
실행 검증(QT_QPA_PLATFORM=offscreen) — *실행 증거*지 human 시각 QA(G-7b) 아님(별도, 정직 표기).

[정직성] 본 셸은 service facade/JobRunner 를 실제로 소비(orphan UI 아님): RuntimeJobsPanel 이
JobRunner.poll 로 실 job 상태를 표시.
"""

from __future__ import annotations

import csv
import json
import math
import re
import shutil
import sys
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, suppress
from dataclasses import replace
from datetime import datetime
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Any, TextIO, TypeVar, cast

from PySide6.QtCore import (
    QEvent,
    QEventLoop,
    QItemSelectionModel,
    QMetaObject,
    QModelIndex,
    QObject,
    Qt,
    QTimer,
)
from PySide6.QtGui import QAction, QCursor, QKeySequence
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStyle,
    QTableWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from cmig.core.diagnostics import parse_diagnostic
from cmig.gui.activity import ActivityPane, RuntimeJobsPanel, command_line
from cmig.gui.agora2_dialog import (
    CONFIRM_BYTES,
    SEARCH_LIMIT,
    Agora2Dialog,
    Agora2Strain,
    download_estimate,
)
from cmig.gui.analysis_page import AnalysisPage, RankedPage, hide_row_numbers
from cmig.gui.builder import (
    WEIGHTED_METRICS,
    CommunityBuilderView,
    ConstraintSandboxView,
    ScenarioCompareView,
    SearchView,
    medium_mode_text,
    validate_search_summary,
)
from cmig.gui.editors import (
    MediumEditor,
    ModelManagerPanel,
    installed_medium_preset_path,
    installed_medium_presets,
)
from cmig.gui.find import FindField, SearchTable, build_table
from cmig.gui.graph_view import GateBadge, InteractionGraphView
from cmig.gui.host_view import HostImpactView, HostInputWidgets
from cmig.gui.inspector import InspectorPanel
from cmig.gui.model_browser import ModelBrowser
from cmig.gui.pages.gene_ko import GeneKoPage
from cmig.gui.pages.host_search import HostSearchPage
from cmig.gui.pages.ratio_impact import RatioImpactPage
from cmig.gui.pages.spatial import SpatialPage
from cmig.gui.pages.strain_growth import StrainGrowthPage
from cmig.gui.pages.tools import ToolPage
from cmig.gui.pickers import MediumPicker, ModelPicker
from cmig.gui.project_session import (
    ProjectSession,
    RecentProjects,
    RunEntry,
    inspect_run,
    merge_run_status,
)
from cmig.gui.sidebar import (
    ANALYSES,
    ANALYSIS_GROUPS,
    WorkspaceSidebar,
    droppable_paths,
)
from cmig.gui.views import (
    CONTRIBUTION_BASIS_NOTE,
    DfbaView,
    ExternalProfileView,
    SweepView,
)
from cmig.io import project as proj
from cmig.io.agora2 import CATALOGUE_FILENAME, human_bytes, read_manifest
from cmig.io.atomic import atomic_write_text
from cmig.io.project import ModelEntry, ProjectError
from cmig.service import Job, JobRunner, JobStatus

I18N: dict[str, dict[str, str]] = {
    "ko": {
        "col_job": "작업",
        "col_kind": "종류",
        "col_status": "상태",
        "col_progress": "진행률",
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
        "kind_minimal_medium": "최소 배지",
        "kind_search": "탐색",
        "medium_title": "배지 편집기",
        "medium_preset": "프리셋",
        "medium_choose_preset": "프리셋 선택…",
        "medium_load_preset": "프리셋 불러오기",
        "medium_nutrients_only": "영양소만 보기",
        "medium_pool_closure_warning": (
            "pool_closure 행은 번들 모델 풀을 위한 장부 기록 행입니다. 이를 제거하는 것은 "
            "엄밀한 배지 모드(다른 풀에서 사용할 때도 포함)에서만 안전합니다. 영양소만 남긴 "
            "배지를 병합 모드에서 사용하지 마세요."
        ),
        "medium_col_exchange": "Exchange",
        "medium_col_uptake": "흡수 한도(mmol gDW⁻¹ h⁻¹; 양의 크기)",
        "medium_col_row_role": "행 역할",
        "medium_add_row": "행 추가",
        "medium_remove_selected": "선택 행 제거",
        "medium_clear_all": "모두 지우기",
        "medium_paste_csv": "CSV 붙여넣기",
        "medium_status_ready": (
            "고급 편집기: 배지를 불러오거나 붙여넣거나 편집한 뒤 CLI 기반 검사를 실행하세요."
        ),
        "medium_assume_bigg": "모델을 검토했고 BiGG namespace임을 확인합니다",
        "medium_namespace_placeholder": "또는 검토된 namespace-decisions JSON 파일",
        "medium_namespace_button": "판정 파일…",
        "medium_exact_mode": "엄밀한 배지(해제 시 기본 배지에 병합)",
        "medium_allow_unknown": "알 수 없는 ID를 허용하고 누락된 ID를 모두 보고",
        "medium_check_growth": "성장 확인",
        "medium_min_growth": "최소 성장률",
        "medium_oxygen_aerobic": "호기성",
        "medium_oxygen_anaerobic": "혐기성",
        "medium_run_minimal": "최소 배지 찾기",
        "medium_minimal_uptake": "후보 흡수량",
        "medium_limiting": "제한 영양소(하나씩 제외)",
        "medium_yes": "예",
        "medium_no": "아니요",
        "medium_select_preset": "불러올 프리셋을 선택하세요.",
        "medium_preset_failed": "프리셋 검증 실패: {error}",
        "medium_preset_loaded": "{name} 불러옴: 검증된 행 {count}개.",
        "medium_paste_empty": "클립보드의 CSV가 비어 있습니다.",
        "medium_paste_parse_failed": "CSV 붙여넣기를 해석할 수 없습니다: {error}",
        "medium_paste_bad_header": (
            "CSV 붙여넣기 {row}행: 헤더는 exchange_id,uptake_limit[,row_role]이어야 합니다."
        ),
        "medium_paste_bad_column_count": (
            "CSV 붙여넣기 {row}행: 열은 2개 또는 3개여야 하지만 {count}개입니다."
        ),
        "medium_paste_bad_columns": (
            "CSV 붙여넣기 {row}행: 열 {expected}개가 필요하지만 {count}개입니다."
        ),
        "medium_paste_blank_exchange": "CSV 붙여넣기 {row}행: exchange_id가 비어 있습니다.",
        "medium_paste_duplicate": (
            "CSV 붙여넣기 {row}행({exchange})이 {first}행과 중복됩니다."
        ),
        "medium_paste_bad_role": (
            "CSV 붙여넣기 {row}행({exchange}): row_role은 nutrient 또는 "
            "pool_closure여야 합니다."
        ),
        "medium_paste_validation_failed": (
            "CSV 붙여넣기 검증 실패; 데이터 행 {rows}: {error}"
        ),
        "medium_paste_loaded": "검증된 CSV 행 {count}개를 붙여넣었습니다.",
        "medium_nutrients_merge_unsafe": (
            "영양소만 필터링한 배지는 병합 모드에서 실행할 수 없습니다. 엄밀한 배지를 "
            "선택하세요. 병합 모드는 명시하지 않은 모델 기본 공급원을 다시 엽니다."
        ),
        "medium_namespace_choice": (
            "Namespace 정책은 검토 파일과 BiGG 확인 중 하나만 선택하세요."
        ),
        "medium_namespace_required": (
            "Namespace 검토가 필요합니다. 검토된 판정 파일을 선택하거나 BiGG임을 확인하세요."
        ),
        "medium_table_duplicate": (
            "exchange_id {exchange} 중복: {first}행과 {row}행."
        ),
        "medium_invalid_uptake": "잘못된 uptake_limit({row}행: {exchange})",
        "medium_validation_failed": (
            "{error} — mmol gDW⁻¹ h⁻¹ 단위의 양의 흡수 크기를 입력하세요(예: -10이 "
            "아닌 10). CMIG가 내부적으로 흡수 부호를 적용합니다."
        ),
        "medium_valid_exchanges": "유효한 exchange {count}개",
        "medium_minimal_result": (
            "최소 배지 상태: {status}; 성분 {count}개; 달성 성장률: {growth}; 제한 영양소 "
            "{limiting}개{warnings}"
        ),
        "medium_dialog_namespace": "Namespace 판정 파일 선택",
        "medium_select_taxonomy_growth": "Select at least one model before checking growth.",
        "medium_select_model_minimal": "Choose a model before finding a minimal medium.",
        "medium_growth_started": "성장 확인 시작: {job_id}",
        "medium_growth_result": "성장률: {growth} · 상태: {status} · 모드: {mode}",
        "medium_mode_exact": "엄밀한 배지",
        "medium_mode_merge": "기본 배지에 병합",
        "medium_dropped_none": "누락된 배지 ID: 없음",
        "medium_dropped_ids": "누락된 배지 ID({count}개): {ids}",
        "medium_diagnostic": "진단: {diagnostic}",
        "medium_profile_delta_active": (
            "이전 배지 검사와 현재 검사의 외부 프로필 차이를 외부 프로필 탭에 표시했습니다."
        ),
        "medium_profile_delta_cleared": (
            "배지가 다시 변경되어 외부 프로필 비교를 지웠습니다. 다시 성장 확인을 실행하세요."
        ),
        "medium_profile_delta_ineligible": (
            "이전 검사와 taxonomy 또는 배지 적용 모드가 달라 프로필을 비교하지 않았습니다."
        ),
        "medium_growth_failed": "성장 확인 {status}: {error}",
        "medium_minimal_started": "최소 배지 계산 시작: {job_id}",
        "medium_minimal_failed": "최소 배지 계산 {status}: {error}",
        "medium_profile_baseline": "이전 배지 검사",
        "medium_profile_variant": "현재 배지 검사",
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
        "status_run_load_failed": "실행 불러오기 실패: {error}",
        "status_run_no_viewer": (
            "이 실행 종류({kind})는 GUI 뷰어가 없습니다: {run_dir} — "
            "`cmig inspect-run --run-dir` 로 확인하세요"
        ),
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
        "sweep_status_ready": "Advanced result view: pick models, configure the axes, then run.",
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
        "sweep_select_source": "Select at least one model.",
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
        "sweep_dialog_mediums": "배지 변형 선택",
        "sweep_dialog_abundances": "Abundance 변형 선택",
        "sweep_dialog_bounds": "Bounds 변형 선택",
        "sweep_dialog_namespace": "Namespace 판정 파일 선택",
        "sweep_filter_medium": "배지 파일 (*.csv *.json);;모든 파일 (*)",
        "sweep_filter_abundance": "Abundance 파일 (*.csv *.json);;모든 파일 (*)",
        "sweep_filter_bounds": "Bounds 파일 (*.json);;모든 파일 (*)",
        "sweep_filter_json": "JSON (*.json);;모든 파일 (*)",
        "sweep_cli_failed": "sweep 명령 실패(rc={rc})",
        "profile_net_chart_title": "외부 순 플럭스(+ 분비 / − 흡수)",
        "profile_delta_overlay_title": "기준 / 변형 오버레이",
        "profile_no_fluxes": "측정된 프로필 플럭스 없음",
        "profile_delta_legend": "연한 색 = {baseline}; 진한 색 = {variant}",
        "profile_member_chart_title": "멤버별 기여(군집 가중 플럭스, tidy ≥1.3)",
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
        "col_job": "Job",
        "col_kind": "Kind",
        "col_status": "Status",
        "col_progress": "Progress",
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
        "kind_minimal_medium": "Minimal medium",
        "kind_search": "Search",
        "medium_title": "Medium Editor",
        "medium_preset": "Preset",
        "medium_choose_preset": "Choose a preset…",
        "medium_load_preset": "Load preset",
        "medium_nutrients_only": "Nutrients only",
        "medium_pool_closure_warning": (
            "Pool-closure rows are bookkeeping for the bundled model pool. Removing them is "
            "safe only with exact-medium semantics (including use with another pool); never "
            "use a nutrients-only file in merge mode."
        ),
        "medium_col_exchange": "Exchange",
        "medium_col_uptake": "Uptake limit (mmol gDW⁻¹ h⁻¹; positive magnitude)",
        "medium_col_row_role": "Row role",
        "medium_add_row": "Add row",
        "medium_remove_selected": "Remove selected",
        "medium_clear_all": "Clear all",
        "medium_paste_csv": "Paste CSV",
        "medium_status_ready": (
            "Advanced editor: load, paste, or edit a medium, then run a CLI-backed check."
        ),
        "medium_assume_bigg": "I reviewed the models and confirm BiGG namespace",
        "medium_namespace_placeholder": "Or a reviewed namespace-decisions JSON file",
        "medium_namespace_button": "Decisions…",
        "medium_exact_mode": "Exact medium (unchecked = merge overlay)",
        "medium_allow_unknown": "Allow unknown IDs and report every dropped ID",
        "medium_check_growth": "Check Growth",
        "medium_min_growth": "Minimum growth",
        "medium_oxygen_aerobic": "Aerobic",
        "medium_oxygen_anaerobic": "Anaerobic",
        "medium_run_minimal": "Find Minimal Medium",
        "medium_minimal_uptake": "Candidate uptake",
        "medium_limiting": "Limiting (leave-one-out)",
        "medium_yes": "Yes",
        "medium_no": "No",
        "medium_select_preset": "Choose a preset before loading it.",
        "medium_preset_failed": "Preset failed validation: {error}",
        "medium_preset_loaded": "Loaded {name}: {count} validated rows.",
        "medium_paste_empty": "Clipboard CSV is empty.",
        "medium_paste_parse_failed": "CSV paste could not be parsed: {error}",
        "medium_paste_bad_header": (
            "CSV paste row {row}: header must be exchange_id,uptake_limit[,row_role]."
        ),
        "medium_paste_bad_column_count": (
            "CSV paste row {row}: expected 2 or 3 columns, got {count}."
        ),
        "medium_paste_bad_columns": (
            "CSV paste row {row}: expected {expected} columns, got {count}."
        ),
        "medium_paste_blank_exchange": "CSV paste row {row}: exchange_id is blank.",
        "medium_paste_duplicate": (
            "CSV paste row {row} ({exchange}) duplicates row {first}."
        ),
        "medium_paste_bad_role": (
            "CSV paste row {row} ({exchange}): row_role must be nutrient or pool_closure."
        ),
        "medium_paste_validation_failed": (
            "CSV paste validation failed; data rows {rows}: {error}"
        ),
        "medium_paste_loaded": "Pasted {count} validated CSV rows.",
        "medium_nutrients_merge_unsafe": (
            "Nutrients-only filtering cannot run in merge mode; choose Exact medium. Merge "
            "would reopen undeclared model defaults."
        ),
        "medium_namespace_choice": (
            "Choose only one namespace policy: reviewed decisions or BiGG confirmation."
        ),
        "medium_namespace_required": (
            "Namespace review is required: choose reviewed decisions or confirm BiGG namespace."
        ),
        "medium_table_duplicate": (
            "Duplicate exchange_id {exchange}: rows {first} and {row}."
        ),
        "medium_invalid_uptake": "Invalid uptake_limit (row {row}: {exchange})",
        "medium_validation_failed": (
            "{error} — enter a POSITIVE uptake magnitude in mmol gDW⁻¹ h⁻¹ (e.g. 10, not "
            "-10); CMIG applies the uptake sign internally."
        ),
        "medium_valid_exchanges": "{count} valid exchanges",
        "medium_minimal_result": (
            "Minimal-medium status: {status}; {count} components; achieved growth: {growth}; "
            "{limiting} limiting nutrients{warnings}"
        ),
        "medium_dialog_namespace": "Select Namespace Decisions",
        "medium_select_taxonomy_growth": "Select at least one model before checking growth.",
        "medium_select_model_minimal": "Choose a model before finding a minimal medium.",
        "medium_growth_started": "growth check started: {job_id}",
        "medium_growth_result": "growth: {growth} · status: {status} · mode: {mode}",
        "medium_mode_exact": "exact medium",
        "medium_mode_merge": "merge onto model default",
        "medium_dropped_none": "Dropped medium IDs: none",
        "medium_dropped_ids": "Dropped medium IDs ({count}): {ids}",
        "medium_diagnostic": "Diagnostic: {diagnostic}",
        "medium_profile_delta_active": (
            "External-profile delta versus the previous medium check is active in Profile."
        ),
        "medium_profile_delta_cleared": (
            "The medium changed again, so the external-profile comparison was cleared. Run "
            "Check Growth again."
        ),
        "medium_profile_delta_ineligible": (
            "The previous check used a different taxonomy or application mode, so profiles "
            "were not compared."
        ),
        "medium_growth_failed": "growth check {status}: {error}",
        "medium_minimal_started": "minimal-medium started: {job_id}",
        "medium_minimal_failed": "minimal-medium {status}: {error}",
        "medium_profile_baseline": "Previous medium check",
        "medium_profile_variant": "Current medium check",
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
        "status_run_load_failed": "Run load failed: {error}",
        "status_run_no_viewer": (
            "No GUI viewer for this run kind ({kind}): {run_dir} — "
            "inspect it with `cmig inspect-run --run-dir`"
        ),
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
        "sweep_status_ready": "Advanced result view: pick models, configure the axes, then run.",
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
        "sweep_select_source": "Select at least one model.",
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
        "sweep_dialog_mediums": "Select Medium Variants",
        "sweep_dialog_abundances": "Select Abundance Variants",
        "sweep_dialog_bounds": "Select Bounds Variants",
        "sweep_dialog_namespace": "Select Namespace Decisions",
        "sweep_filter_medium": "Medium files (*.csv *.json);;All files (*)",
        "sweep_filter_abundance": "Abundance files (*.csv *.json);;All files (*)",
        "sweep_filter_bounds": "Bounds files (*.json);;All files (*)",
        "sweep_filter_json": "JSON (*.json);;All files (*)",
        "sweep_cli_failed": "sweep command failed with rc={rc}",
        "profile_net_chart_title": "Net exchange flux (+ secretion / − uptake)",
        "profile_delta_overlay_title": "baseline / variant overlay",
        "profile_no_fluxes": "No measured profile fluxes",
        "profile_delta_legend": "light = {baseline}; solid = {variant}",
        "profile_member_chart_title": (
            "Per-member contribution (community-weighted flux, tidy ≥1.3)"
        ),
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


ONE_TARGET_ROW_REQUIRED = "Gene KO and Ratio Impact need exactly one target row."


def _single_target(rows: list[tuple[str, str, str, str]]) -> tuple[str, str, str]:
    """Return (target, direction, error) from the target table without guessing.

    Gene KO and Ratio Impact answer for one metabolite: an empty table/row is refused
    (CMIG never substitutes a default target) and so is a table with more than one row.
    """
    if len(rows) > 1:
        return "", "", ONE_TARGET_ROW_REQUIRED
    raw = rows[0][0].strip() if rows else ""
    if not raw:
        return "", "", (
            "Enter the target metabolite (e.g. but or ac). "
            "CMIG does not substitute a default target."
        )
    if "," in raw:
        return "", "", "Enter a single metabolite id in the target row."
    return raw, rows[0][1], ""


def _finite_number(text: str) -> float | None:
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _search_target_argv(
    rows: list[tuple[str, str, str, str]], metric: str, pareto_resolution: str
) -> tuple[list[str], str]:
    """Translate the target table into `cmig search` target flags, or a refusal.

    One row → `--target/--direction` (Weight and Reference unused). Two or more rows →
    `--targets`, `--target-directions` (row order), `--target-weights` when the metric
    uses weights, `--target-scales` when References are given. Nothing is defaulted:
    empty, duplicate or non-numeric cells are refused with the reason.
    """
    if not rows:
        return [], "Add at least one target row. CMIG does not substitute a default target."
    targets = [row[0] for row in rows]
    for number, target in enumerate(targets, 1):
        if not target:
            return [], (f"Target row {number} is empty. "
                        "CMIG does not substitute a default target.")
        if any(ch in target for ch in ",=") or any(ch.isspace() for ch in target):
            return [], f"Target row {number} ({target!r}) must be a single metabolite id."
    duplicates = sorted({target for target in targets if targets.count(target) > 1})
    if duplicates:
        return [], f"Duplicate target rows: {', '.join(duplicates)}. Each target once."
    if len(rows) == 1:
        return ["--target", targets[0], "--direction", rows[0][1]], ""
    argv = ["--targets", ",".join(targets),
            "--target-directions", ",".join(row[1] for row in rows)]
    if metric in WEIGHTED_METRICS:
        for target, _direction, weight, _reference in rows:
            if _finite_number(weight) is None:
                return [], f"Weight for {target} must be a finite number; got {weight!r}."
        argv.extend(["--target-weights", ",".join(row[2] for row in rows)])
    references = [row[3] for row in rows]
    if any(references):
        if not all(references):
            return [], ("References must be entered for every target row, or left empty "
                        "for all rows.")
        for target, reference in zip(targets, references, strict=True):
            value = _finite_number(reference)
            if value is None or value <= 0:
                return [], (f"Reference for {target} must be a finite positive number; "
                            f"got {reference!r}.")
        argv.extend(["--target-scales", ",".join(
            f"{target}={reference}" for target, reference in zip(targets, references,
                                                                 strict=True))])
    argv.extend(["--multi-metric", metric])
    if metric == "pareto":
        argv.extend(["--pareto-resolution", pareto_resolution])
    return argv, ""


def _search_argv(
    requested: dict[str, str], rows: list[tuple[str, str, str, str]]
) -> tuple[list[str], str]:
    """Build the `cmig search` argv from a GUI-thread snapshot, without the model input
    (`--taxonomy`, which the caller inserts right after "search") and without `--out`.

    `requested["medium"]` is the medium file path (not the picker's ref). An option whose
    applicability condition does not hold is left out, so the argv never carries a setting
    the run would ignore.
    """
    argv = ["search"]
    target_argv, error = _search_target_argv(
        rows, requested["multi_metric"], requested["pareto_resolution"]
    )
    if error:
        return [], error
    argv.extend(target_argv)
    strategy = requested["strategy"]
    argv.extend([
        "--strategy", strategy,
        "--min-size", requested["min_size"],
        "--max-size", requested["max_size"],
        "--top-k", requested["top_k"],
        "--seed", requested["seed"],
        "--workers", requested["workers"],
        "--solver-threads", requested["solver_threads"],
        "--growth-fraction", requested["growth_fraction"],
        "--min-member-growth", requested["min_member_growth"],
        "--min-community-growth", requested["min_community_growth"],
        "--validate-top", requested["validate_top"],
    ])
    if requested["fva"] == "True" and len(rows) == 1:  # FVA is single-target only
        argv.append("--robustness-fva")
    if strategy == "auto":
        argv.extend(["--exhaustive-max", requested["exhaustive_max"]])
    if strategy == "random":
        argv.extend(["--n-samples", requested["n_samples"]])
    if strategy in ("auto", "ga"):
        argv.extend([
            "--ga-pop-size", requested["ga_pop_size"],
            "--ga-generations", requested["ga_generations"],
            "--ga-mutation-rate", requested["ga_mutation_rate"],
            "--ga-immigrant-fraction", requested["ga_immigrant_fraction"],
            "--ga-tournament-k", requested["ga_tournament_k"],
            "--ga-elitism", requested["ga_elitism"],
            "--ga-local-search-fraction", requested["ga_local_search_fraction"],
        ])
        for key, flag in (("ga_budget", "--ga-max-evaluations"),
                          ("ga_patience", "--ga-patience"),
                          ("ga_restart_after", "--ga-restart-after")):
            if int(requested[key]):  # 0 is the "off" special value
                argv.extend([flag, requested[key]])
        if requested["ga_preserve_common"] == "True":
            argv.append("--ga-preserve-common")
    if requested["medium"]:
        argv.extend(["--medium", requested["medium"]])
        if requested["medium_mode"] == "exact":
            argv.append("--exact-medium")
        if requested["allow_unknown_medium"] == "True":
            argv.append("--allow-unknown-medium")
    if int(requested["timeout"]):
        argv.extend(["--solve-timeout", requested["timeout"]])
    if requested["checkpoint"]:
        argv.extend(["--checkpoint", requested["checkpoint"]])
    if requested["resume"] == "True":
        argv.append("--resume")
    return argv, ""


T = TypeVar("T")


class _ThreadStderrRouter:
    """Pass-through `sys.stderr` that also copies writes made by a *registered* thread.

    The GUI runs the CLI in-process on a job thread, and the CLI reports request errors
    with `print(..., file=sys.stderr)`. Redirecting the global stream from the job thread
    would capture every other thread's output too (and hide it from the terminal). This
    router is installed once from the GUI thread; each job thread registers its own buffer,
    so a job only ever sees what its own thread wrote. Output still reaches the terminal.
    """

    def __init__(self, underlying: TextIO) -> None:
        self._underlying = underlying
        self._local = threading.local()

    def write(self, text: str) -> int:
        buffer = getattr(self._local, "buffer", None)
        if buffer is not None:
            buffer.append(text)
        return self._underlying.write(text)

    def flush(self) -> None:
        self._underlying.flush()

    def attach(self, buffer: list[str]) -> None:
        self._local.buffer = buffer

    def detach(self) -> None:
        self._local.buffer = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._underlying, name)


def _install_stderr_router() -> None:
    """Install the pass-through router (GUI thread only; idempotent)."""
    if not isinstance(sys.stderr, _ThreadStderrRouter):
        sys.stderr = cast(TextIO, _ThreadStderrRouter(sys.stderr))


def _install_stdout_router() -> None:
    """Install the pass-through router on stdout (GUI thread only; idempotent)."""
    if sys.stdout is not None and not isinstance(sys.stdout, _ThreadStderrRouter):
        sys.stdout = cast(TextIO, _ThreadStderrRouter(sys.stdout))


@contextmanager
def _captured_thread_stdout() -> Iterator[list[str]]:
    """Collect what the *current* thread prints (other threads' output is untouched)."""
    chunks: list[str] = []
    router = sys.stdout if isinstance(sys.stdout, _ThreadStderrRouter) else None
    if router is not None:
        router.attach(chunks)
    try:
        yield chunks
    finally:
        if router is not None:
            router.detach()


@contextmanager
def _captured_job_stderr() -> Iterator[list[str]]:
    """Collect what the *current* thread writes to stderr (display only, never an artifact)."""
    chunks: list[str] = []
    router = sys.stderr if isinstance(sys.stderr, _ThreadStderrRouter) else None
    if router is not None:
        router.attach(chunks)
    try:
        yield chunks
    finally:
        if router is not None:
            router.detach()


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


def _failed_search_artifacts(out_dir: Path, rc: int) -> dict[str, Any]:
    """Keep a CLI failure's scientific ledger and directory with the failed job."""
    summary_path = out_dir / "search_summary.json"
    summary: dict[str, Any] = {}
    if summary_path.is_file():
        try:
            loaded = json.loads(summary_path.read_text())
            if isinstance(loaded, dict):
                summary = loaded
        except (OSError, ValueError):
            pass
    # A nonzero CLI outcome cannot become a scientific success even if a partial
    # summary was written before the command failed.
    summary["status"] = "failed"
    summary.setdefault("top_ranked", [])
    summary["cli_exit_code"] = rc
    summary["output_dir"] = str(out_dir)
    if rc == 2 and not summary.get("warnings"):
        summary["warnings"] = [
            "Invalid Search request (CLI exit 2). Check the model pool, target, medium "
            "file, membership bounds and selected options; the exact output directory "
            "is shown below."
        ]
    return summary


def _search_input_diagnostic(medium: str) -> str | None:
    """Keep known CLI input errors when a failed transaction publishes no artifacts."""
    if medium and not Path(medium).is_file():
        return f"medium file not found: {medium}"
    return None


_SEARCH_CONDITION_KEYS = (
    "solution_semantics", "metric", "directions", "weights",
    "normalization_ranges", "ga_metadata", "effective_request", "effective_conditions",
    "growth_fraction", "min_member_growth", "min_community_growth", "seed",
    "target_scales", "ga_max_evaluations",
)


def _with_search_conditions(summary: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    return {**summary, **{key: source[key] for key in _SEARCH_CONDITION_KEYS if key in source}}


CHECKPOINT_EXISTS = "checkpoint exists; enable Resume or choose a new path"
#: a job's final states
_ENDED = (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED)
_UNREADABLE_RESULT = (
    "{kind} finished, but its result could not be read back — see the inspector ({out_dir})"
)
SEARCH_CANCEL_PENDING = "Cancellation requested — the solve in progress will finish first."


def _not_runnable(entry: ModelEntry) -> str:
    """Why a project model cannot be part of a run ("" when it can)."""
    if entry.integrity == "changed":
        return "its file changed since it was added"
    if entry.integrity == "missing":
        return "its file is missing"
    if entry.status not in ("ok", "warning"):
        detail = f": {entry.error}" if entry.error else ""
        return f"its check status is {entry.status!r}{detail}"
    return ""


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
        #: job id -> text shown in the Activity status column instead of the runner's status
        self.status_labels: dict[str, str] = {}
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.refresh)

    def track(self, job_id: str) -> None:
        self._job_ids.append(job_id)
        self.refresh()

    def refresh(self) -> None:
        self._panel.refresh(
            self._runner, self._job_ids, frozenset(self.cancelling), self.status_labels
        )

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()


def _read_target_summary(run_dir: Path) -> list[dict[str, Any]] | None:
    """`target_summary.json` beside a tidy bundle (written by `--targets`), or None."""
    path = run_dir / "target_summary.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, list) else None


#: WorkspaceSidebar's top-level groups, in row order.
_SIDEBAR_GROUPS = ("models", "media", "analyses", "runs")


def _run_key(run_dir: Path) -> str:
    return str(Path(run_dir).resolve())


def _same_folder(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.expanduser().resolve()
    except (OSError, RuntimeError):
        return False


def _parse_catalogue(text: str) -> list[Agora2Strain]:
    """Strains from the JSON `agora2-list --format json` prints, each with its published size.

    The strains are under `models` (a list of objects with an `id` and a `published_size`); a
    bare list of strings or objects is accepted too (a string has no size). An output with no
    strain list, or an entry without an id, is an error: it must not read as "no strain
    matched".
    """
    payload = json.loads(text)
    items = payload.get("models") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ValueError("agora2-list printed no list of strains")
    strains: list[Agora2Strain] = []
    for item in items:
        strain = item.get("id") if isinstance(item, dict) else item
        if not isinstance(strain, str) or not strain:
            raise ValueError(f"agora2-list printed an entry without a strain id: {item!r}")
        size = item.get("published_size") if isinstance(item, dict) else None
        strains.append(Agora2Strain(strain, size if isinstance(size, str) else ""))
    return strains


def _claim_agora2_batch_dir(parent: Path) -> Path:
    """Create and return a new `<YYYYMMDD-HHMMSS>[-N]` folder under `parent`, reusing none."""
    base = datetime.now().strftime("%Y%m%d-%H%M%S")
    n = 1
    while True:
        candidate = parent / (base if n == 1 else f"{base}-{n}")
        try:
            candidate.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            n += 1
            continue
        return candidate


def _manifest_downloads(batch_dir: Path, strains: list[str]) -> dict[str, str]:
    """The files a batch's own manifest records as fetched, each with the URL it came from.

    `agora2-fetch` writes a manifest beside its output that lists only the strains that arrived
    (or were already there), so a strain that failed is absent from it. Only a bare file name
    is followed; it must exist in the batch folder.
    """
    wanted = set(strains)
    found: dict[str, str] = {}
    for record in read_manifest(batch_dir).get("models") or []:
        if not isinstance(record, dict) or record.get("id") not in wanted:
            continue
        name = record.get("file")
        if not isinstance(name, str) or Path(name).name != name:
            continue
        path = batch_dir / name
        if path.is_file():
            found[str(path)] = str(record.get("source_url") or "")
    return found


def _integrity_text(inspected: dict[str, Any]) -> object:
    """Inspector integrity row: the digest state plus which artifacts differ or why none."""
    state = inspected.get("artifact_integrity")
    if state == "mismatch":
        digest = inspected.get("result_digest")
        digest = digest if isinstance(digest, dict) else {}
        changed = ", ".join(digest.get("changed_artifacts") or []) or "none"
        missing = ", ".join(digest.get("missing_artifacts") or []) or "none"
        return f"mismatch — changed: {changed}; missing: {missing}"
    if state == "not_recorded" and inspected.get("result_digest_absent_reason"):
        return f"not_recorded ({inspected['result_digest_absent_reason']})"
    return state


class CmigMainWindow(QMainWindow):
    """Workspace window: sidebar | centre page | inspector, activity pane below. Consumes
    the service layer (JobRunner); every analysis runs the CLI."""

    def __init__(self, runner: JobRunner | None = None, lang: str = "en") -> None:
        super().__init__()
        self.lang = lang if lang in I18N else "en"
        self.tr_map = I18N[self.lang]
        self.runner = runner if runner is not None else JobRunner(max_workers=2)

        self.session = ProjectSession(self)
        self.recent = RecentProjects()
        self.sidebar = WorkspaceSidebar()
        # Long preset names share prefixes (…_low_carb vs …_low_carb_x100): keep both ends.
        self.sidebar.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.inspector = InspectorPanel()
        self.activity = ActivityPane(self.tr_map)
        self.jobs_panel = self.activity.jobs
        self._external_runs: list[RunEntry] = []
        #: import job id -> the files and folders it was given; at most one import runs at a
        #: time (two would race for the same models/ file names)
        self._import_jobs: dict[str, list[Path]] = {}
        #: import job id -> filled by the job with the model files its folder search found
        self._import_found: dict[str, list[list[Path]]] = {}
        #: import job id -> root of the project it imports into
        self._import_roots: dict[str, Path] = {}
        #: AGORA2 download job id -> (project root, folder it downloads into). A download holds
        #: the same one-at-a-time gate as an import, from the fetch until its files are
        #: handed to `add_model_paths` in `_finish_agora2`.
        self._agora2_jobs: dict[str, tuple[Path, Path]] = {}
        #: file names shown as placeholder rows in MODELS while an import runs
        self._pending_imports: list[str] = []
        #: job id -> equivalent command / log text shown in Activity for that job
        self._job_commands: dict[str, str] = {}
        self._job_logs: dict[str, str] = {}
        #: run folder -> the equivalent `cmig` command (the inspector's Copy Command)
        self._run_commands: dict[str, str] = {}
        #: True while _refresh_pickers rebuilds the pickers: those changes are not user choices
        self._refreshing_pickers = False
        #: picker key -> remembered models already reported as no longer runnable
        self._reported_unrunnable: dict[str, set[str]] = {}
        #: root of the project the centre page was last laid out for (see refresh_workspace)
        self._shown_root: Path | None = None
        #: True while a sidebar selection drives the centre page (see _show_page)
        self._following_sidebar = False
        #: run folder -> (status, detail) of the GUI's last failed readback of that run
        self._readback_failures: dict[str, tuple[str, str]] = {}
        #: run folder -> "failed" | "cancelled": how the job that wrote it ended. A folder a
        #: failed or cancelled job left behind must never read as a result in RUNS. The same is
        #: written to a marker beside the run's inputs so it survives a restart; this copy
        #: covers a marker that could not be written.
        self._run_states: dict[str, str] = {}
        #: job id -> the run folder it writes, until the job reaches a terminal state
        self._job_runs: dict[str, Path] = {}
        #: (run folder, inspect-run payload) from the last _inspect_gui_run, for the inspector
        self._last_inspected: tuple[str, dict[str, Any]] | None = None
        #: what the inspector shows: a run folder, or a model's (id, sha256)
        self._inspector_run: str | None = None
        self._inspected_model: tuple[str, str] | None = None
        #: model sha256 -> why its browse index could not be built (this project only)
        self._index_failures: dict[str, str] = {}
        #: the one index job ("check": an unlisted read of the index files; "build": the
        #: Activity job that rebuilds the unusable ones), and the project root it is for
        self._index_job: str | None = None
        self._index_job_kind = "check"
        self._index_job_root: Path | None = None
        #: model sha256 -> loaded browse index (a few recent ones)
        self._index_cache: dict[str, dict[str, Any]] = {}
        #: model sha256s an index job found usable or rebuilt (this project only)
        self._index_checked: set[str] = set()
        #: model sha256 -> its (kind, id, name) search rows, read from its index by an
        #: unlisted job (this project only); sha256s whose index that job could not read
        self._search_rows: dict[str, list[tuple[str, str, str]]] = {}
        self._search_unreadable: set[str] = set()
        self._search_rows_job: str | None = None
        #: the shas that job reads and the project root it reads them for
        self._search_rows_wanted: tuple[Path, list[str]] | None = None
        #: the search table, built on the first search after anything in it changed
        self._search_cache: SearchTable | None = None
        self._search_building = False
        #: medium ref -> its exchange ids, for the project search
        self._medium_exchange_cache: dict[str, list[str]] = {}
        self.find_field = FindField(self._search_table, self)
        self.find_field.activated.connect(self._find_activated)
        self.bridge = JobsBridge(self.runner, self.jobs_panel)
        self._fixture_jobs: dict[str, Path] = {}
        # Each Search-tab map holds (out_dir, the answer-determining inputs at submit time)
        # so an arriving result can say which request it belongs to.
        self._search_jobs: dict[str, tuple[Path, dict[str, str]]] = {}
        #: Search jobs whose cancel was requested but which have not reached a terminal state.
        self._search_cancel_pending: set[str] = set()
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
        #: growth job id -> (artifact directory, answer-determining request snapshot)
        self._medium_growth_jobs: dict[str, tuple[Path, dict[str, Any]]] = {}
        self._minimal_medium_jobs: dict[str, Path] = {}
        #: Check Growth job id -> (run folder, model id, model sha256)
        self._check_growth_jobs: dict[str, tuple[Path, str, str]] = {}
        #: whether the user ticked/unticked the namespace box since that page's models changed
        self._namespace_user_set: dict[str, bool] = {"community": False, "medium": False}
        #: the box state the last default set (None: none since that page's models changed);
        #: a box that no longer matches it was set since (restored inputs, a script) and stays
        self._namespace_defaults: dict[str, bool | None] = {"community": None, "medium": None}
        #: (model id, sha256, confirmation state, status, integrity) the browser header shows
        self._browser_shown: tuple[str, str, str, str, str] | None = None
        #: The most recent completed Check Growth is the baseline for a later medium edit.
        self._last_medium_growth_check: tuple[Path, dict[str, Any]] | None = None
        self._medium_delta_active = False
        #: sandbox job id -> (commit?, the bound constraint the result will belong to,
        #: automatic preview after a bound edit?)
        self._sandbox_jobs: dict[str, tuple[bool, Any, bool]] = {}
        self.current_manifest: dict[str, Any] | None = None
        self.current_graph_payload: dict[str, Any] | None = None
        self.current_search_dir: Path | None = None
        self.current_host_microbe_dir: Path | None = None

        self.model_manager = ModelManagerPanel()
        self.model_browser = ModelBrowser()
        self.community_builder = CommunityBuilderView()
        self.medium_editor = MediumEditor(strings=self.tr_map)
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
        self.gene_ko_page = GeneKoPage()
        self.strain_growth_page = StrainGrowthPage()
        self.ratio_impact_page = RatioImpactPage()
        self.host_view = HostImpactView()
        self.host_search_page = HostSearchPage()
        self.dynamics_view = DfbaView()
        self.spatial_page = SpatialPage()
        self.medium_page = ToolPage(
            "Medium Editor",
            "Edit a medium, check whether the selected models grow on it, or find a minimal "
            "medium.", self.medium_editor, results=True)
        self.sweep_page = ToolPage(
            "Sweep", "Run the community across media, abundances and solvers.",
            self.sweep_view, results=False)
        self.sandbox_page = ToolPage(
            "Constraint Sandbox", "Preview one bound change before committing it.",
            self.sandbox_view, results=True)
        self.compare_page = ToolPage(
            "Compare Runs", "Compare two completed runs.", self.scenario_compare,
            results=True)
        editor = self.medium_editor
        self.medium_page.register("models", editor.model_picker)
        self.medium_page.register("model", editor.single_model_picker)
        for name, widget in (("exact", editor.exact_medium_check),
                             ("allow_unknown", editor.allow_unknown_check),
                             ("assume_bigg", editor.assume_bigg_check),
                             ("namespace_decisions", editor.namespace_decisions_input),
                             ("min_growth", editor.min_growth_spin),
                             ("oxygen_mode", editor.oxygen_mode_combo)):
            self.medium_page.register(name, widget)
        # After "exact": the nutrients-only view it restores is judged against the exact mode.
        self.medium_page.register_custom("rows", self._medium_rows, self._restore_medium_rows)
        # "Already BiGG" is restored only for models confirmed now (it keeps its place, after
        # the models it covers).
        for key, namespace_page, check in (
            ("community", self.community_builder, self.community_builder.assume_bigg_check),
            ("medium", self.medium_page, editor.assume_bigg_check),
        ):
            namespace_page.register_custom(
                "assume_bigg", check.isChecked, partial(self._restore_assume_bigg, key)
            )
        sweep = self.sweep_view
        self.sweep_page.register("models", sweep.model_picker)
        for name in ("mediums", "abundance_variants", "member_sets", "bounds_variants",
                     "tradeoff_fs", "solvers", "namespace_decisions", "fva_metabolites"):
            self.sweep_page.register(name, getattr(sweep, f"{name}_input"))
        for name in ("assume_bigg", "fva", "exact_medium", "allow_unknown_medium"):
            self.sweep_page.register(name, getattr(sweep, f"{name}_check"))
        self.central_stack = QStackedWidget()  # kept: set_central() still docks extra views
        self.pages = self.central_stack
        self.welcome_page = self._build_welcome_page()
        self.empty_models_page = self._build_empty_models_page()
        self.community_result_page = QTabWidget()
        self.community_result_page.addTab(self.profile_view, "Profile")
        self.community_result_page.addTab(self.graph_tab, "Graph")
        self.analysis_pages: dict[str, AnalysisPage] = {
            "search": self.search_view,
            "gene_ko": self.gene_ko_page,
            "strain_growth": self.strain_growth_page,
            "ratio_impact": self.ratio_impact_page,
            "community": self.community_builder,
            "host": self.host_view,
            "host_search": self.host_search_page,
            "dfba": self.dynamics_view,
            "spatial": self.spatial_page,
            "medium": self.medium_page,
            "sweep": self.sweep_page,
            "sandbox": self.sandbox_page,
            "compare": self.compare_page,
        }
        for page in [self.welcome_page, self.empty_models_page, self.model_manager,
                     self.model_browser, *dict.fromkeys(self.analysis_pages.values())]:
            self.pages.addWidget(page)
        # The community result (Profile | Graph) sits in one page's results area at a time;
        # it starts on Community Solve, whose results area stays empty until a run shows.
        self.community_builder.results.add(self.community_result_page, 1)
        self._community_result_host: str | None = "community"
        self.current_analysis: str | None = None

        vertical = QSplitter(Qt.Orientation.Vertical)
        horizontal = QSplitter(Qt.Orientation.Horizontal)
        horizontal.setChildrenCollapsible(False)
        horizontal.addWidget(self.sidebar)
        horizontal.addWidget(self.pages)
        horizontal.addWidget(self.inspector)
        horizontal.setStretchFactor(1, 1)
        horizontal.setSizes([220, 760, 280])
        vertical.addWidget(horizontal)
        vertical.addWidget(self.activity)
        vertical.setStretchFactor(0, 1)
        vertical.setSizes([640, 160])
        self.activity.setVisible(False)
        self.setCentralWidget(vertical)
        self.setAcceptDrops(True)
        self.statusBar().showMessage(self.tr_map["ready"])
        #: Digest state of the last loaded run ("Integrity: verified", "Readback: …").
        self._last_integrity = "Integrity: no run loaded"
        self._integrity_detail = "No run loaded."
        # A permanent widget: ordinary status-bar widgets are hidden while a message shows,
        # and the window keeps one ("Ready") on screen.
        self.last_run_button = QToolButton()
        self.last_run_button.setAutoRaise(True)
        self.last_run_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.last_run_button.clicked.connect(self._open_last_run)
        self.statusBar().addPermanentWidget(self.last_run_button)
        self.last_run_button.setVisible(False)  # empty, it draws as a bare box on macOS
        self._last_run_dir: Path | None = None
        #: run folders whose job ended since the last poll: (folder, error text)
        self._just_finished: list[tuple[Path, str]] = []
        #: runs/ folders of projects closed in this window (see `_from_closed_project`)
        self._closed_runs_dirs: list[Path] = []
        self.solver_label = QLabel("")
        self.statusBar().addPermanentWidget(self.solver_label)
        self._refresh_solver_label()
        self._install_workflow_actions()
        self._connect_view_actions()
        for button in self._run_buttons().values():
            button.installEventFilter(self)
        self.sidebar.selection_changed.connect(self._on_sidebar_selection)
        self.model_manager.model_activated.connect(
            lambda mid: self.sidebar.select("models", mid)
        )
        self.model_browser.retry_index_requested.connect(self._retry_index)
        self.model_browser.confirm_requested.connect(self._confirm_namespace)
        self.model_browser.revoke_requested.connect(self._revoke_namespace)
        self.model_browser.check_growth_requested.connect(self.run_check_growth)
        self.community_builder.assume_bigg_check.clicked.connect(
            lambda _c=False: self._namespace_user_set.__setitem__("community", True))
        self.medium_editor.assume_bigg_check.clicked.connect(
            lambda _c=False: self._namespace_user_set.__setitem__("medium", True))
        for key, pickers in (("community", (self.community_builder.model_picker,)),
                             ("medium", (self.medium_editor.model_picker,
                                         self.medium_editor.single_model_picker))):
            for picker in pickers:
                picker.selection_changed.connect(
                    lambda k=key: self._namespace_selection_changed(k))
        self.sidebar.files_dropped.connect(self.add_model_paths)
        self.sidebar.context_requested.connect(self._show_sidebar_menu)
        self.sidebar.itemSelectionChanged.connect(self._update_model_actions)
        self.activity.cancel_requested.connect(self._cancel_job_id)
        self.jobs_panel.itemSelectionChanged.connect(self._show_selected_job_detail)
        self.session.opened.connect(self.refresh_workspace)
        self.session.closed.connect(self.refresh_workspace)
        self.session.models_changed.connect(self.refresh_workspace)
        # After the refresh: an undo/redo of a confirmation redraws the browsed model's header.
        self.session.models_changed.connect(self._browser_models_changed)
        self.session.media_changed.connect(self.refresh_workspace)
        self.session.runs_changed.connect(self.refresh_workspace)
        # An undo/redo whose save failed was rolled back. Report it without a modal dialog:
        # a nested event loop inside the undo stack's own call can crash QUndoStack.
        self.session.save_failed.connect(
            lambda message: self.statusBar().showMessage(
                f"Could not save the project, so that undo/redo was rolled back: {message}",
                15000,
            )
        )
        self.refresh_workspace()
        self._polling = False
        self._completion_timer = QTimer(self)
        self._completion_timer.setInterval(500)
        self._completion_timer.timeout.connect(self._poll_completed_jobs)
        self._completion_timer.start()
        self.bridge.start()
        for table in self.findChildren(QTableWidget):
            hide_row_numbers(table)

    def _medium_rows(self) -> dict[str, Any]:
        """The medium table as typed (each cell's text) and its Nutrients-only view."""
        editor = self.medium_editor
        table = editor.table
        rows = []
        for r in range(table.rowCount()):
            cells = [table.item(r, c) for c in range(3)]
            rows.append(["" if cell is None else cell.text() for cell in cells])
        return {"rows": rows, "nutrients_only": editor.nutrients_only_check.isChecked()}

    def _restore_medium_rows(self, value: Any) -> str | None:
        editor = self.medium_editor
        try:
            parsed = [(str(e), str(limit), str(role)) for e, limit, role in value["rows"]]
            nutrients_only = value["nutrients_only"]
        except (TypeError, ValueError, KeyError):
            return "medium rows could not be restored"
        if not isinstance(nutrients_only, bool):
            return "medium rows could not be restored"
        editor.clear_rows()
        table = editor.table
        blocked = table.blockSignals(True)
        try:
            for exchange, limit, role in parsed:
                editor.add_row(exchange, 0.0, role, notify=False)
                limit_item = table.item(table.rowCount() - 1, 1)
                if limit_item is not None:  # add_row always sets it
                    limit_item.setText(limit)  # verbatim: "10" stays "10", blank stays blank
        finally:
            table.blockSignals(blocked)
        editor._update_role_presentation()  # add_row(notify=False) leaves the role column as is
        check_blocked = editor.nutrients_only_check.blockSignals(True)
        editor.nutrients_only_check.setChecked(nutrients_only)
        editor.nutrients_only_check.blockSignals(check_blocked)
        editor._apply_role_view(nutrients_only, notify=False)
        editor.medium_changed.emit()
        return None

    def _message(self, key: str, **values: Any) -> str:
        """Format one localized UI message from the active language catalogue."""
        return self.tr_map[key].format(**values)

    def _show_status(self, key: str, **values: Any) -> None:
        self.statusBar().showMessage(self._message(key, **values))

    def _run_off_thread(self, fn: Callable[..., T], *args: Any) -> T:
        """Run `fn` on a worker thread; keep the window repainting until it is done.

        User input is queued until the worker ends (a click or key press in the nested loop
        would re-enter a run loader half way); timers and repaints continue. The loop and
        timer have no parent, so nothing accumulates on the window.
        """
        loop = QEventLoop()
        timer = QTimer()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(fn, *args)
            # The worker thread posts the quit, so the loop ends the moment `fn` returns.
            future.add_done_callback(
                lambda _f: QMetaObject.invokeMethod(
                    loop, "quit", Qt.ConnectionType.QueuedConnection
                )
            )
            # Safety net only: the done callback is the normal way out of the loop.
            timer.setInterval(50)
            timer.timeout.connect(lambda: loop.quit() if future.done() else None)
            timer.start()
            try:
                while not future.done():
                    loop.exec(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            finally:
                timer.stop()
                timer.timeout.disconnect()
        return future.result()

    def _inspect_gui_run(self, run_dir: Path) -> dict[str, Any] | None:
        """Strict manifest preflight around the CLI's shared digest inspector."""
        from cmig.cli.main import _inspect_run_dir

        manifest_path = run_dir / "manifest.json"
        # A failure below re-records it; one that no longer holds must leave RUNS as well.
        cleared = self._readback_failures.pop(_run_key(run_dir), None) is not None
        cleared = self._clear_readback_marker(run_dir) or cleared
        try:
            manifest: dict[str, Any] = {}
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text())
                if not isinstance(manifest, dict):
                    raise ValueError("manifest.json is not a JSON object")
                if "provenance" in manifest and not isinstance(manifest["provenance"], dict):
                    raise ValueError("manifest provenance must be an object")
                if "manifest_scope" in manifest and not isinstance(
                    manifest["manifest_scope"], str
                ):
                    raise ValueError("manifest_scope must be a string")
                if manifest.get("manifest_scope") == "workflow":
                    version = manifest.get("manifest_schema_version")
                    if version is not None and not isinstance(version, str):
                        raise ValueError("workflow manifest schema version must be a string")
                    if ("manifest_schema_version" in manifest
                            and not isinstance(manifest.get("workflow_kind"), str)):
                        raise ValueError("workflow manifest has no workflow_kind")
                    artifacts = manifest.get("artifacts")
                    if ("manifest_schema_version" in manifest and (
                        not isinstance(artifacts, list)
                        or not all(isinstance(name, str) for name in artifacts)
                    )):
                        raise ValueError("workflow manifest artifacts must be a list of names")
                    digest = manifest.get("result_digest")
                    if version is not None:
                        parts = version.split(".")
                        if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
                            raise ValueError("workflow manifest schema version is malformed")
                        if (int(parts[0]), int(parts[1])) >= (1, 2) and digest is None:
                            raise ValueError("modern workflow manifest has no result_digest")
                    if digest is not None and (
                        not isinstance(digest, dict)
                        or not isinstance(digest.get("digest"), str)
                        or not isinstance(digest.get("artifacts"), dict)
                    ):
                        raise ValueError("workflow manifest result_digest is malformed")
            # Digests are I/O bound: a worker hashes the files while a nested event loop
            # keeps repaint, cancellation and window input live.
            inspected = self._run_off_thread(_inspect_run_dir, run_dir)
            state = inspected["artifact_integrity"]
            detail = ""
            if state == "mismatch":
                digest = inspected.get("result_digest") or {}
                detail = "; changed=" + ", ".join(digest.get("changed_artifacts") or [])
                detail += "; missing=" + ", ".join(digest.get("missing_artifacts") or [])
            elif state == "not_recorded":
                detail = f" ({inspected.get('result_digest_absent_reason')})"
            self._last_integrity = f"Integrity: {state}"
            self._integrity_detail = f"Run: {run_dir}\nState: {state}{detail}"
            self._last_inspected = (_run_key(run_dir), inspected)
            if cleared:
                self.refresh_workspace()
            return inspected
        except Exception as exc:
            self._last_integrity = "Integrity: invalid/unreadable"
            self._integrity_detail = f"Run: {run_dir}\nInvalid or unreadable: {exc}"
            self._show_status("status_run_load_failed", error=exc)
            self._readback_failed(run_dir, "invalid/unreadable", self._integrity_detail)
            return None

    def _reject_gui_summary(self, run_dir: Path, error: Exception | str) -> None:
        """Report unreadable readback separately from the recorded byte digest."""
        digest_state = self._last_integrity.removeprefix("Integrity: ")
        self._last_integrity = "Readback: invalid/unreadable"
        self._integrity_detail = (
            f"Run: {run_dir}\nReadback: invalid/unreadable ({error})\n"
            f"Artifact digest: {digest_state}"
        )
        self._readback_failed(run_dir, "readback invalid/unreadable", self._integrity_detail)

    def _summary_missing(self, run_dir: Path, summary_path: Path) -> None:
        self._readback_failed(
            run_dir, "readback invalid/unreadable",
            f"Run: {run_dir}\nReadback: invalid/unreadable ({summary_path.name} not found)",
        )

    def _readback_failed(self, run_dir: Path, status: str, detail: str) -> None:
        """Remember why this run could not be shown; the inspector and RUNS both say so.

        A project run also gets an `unreadable` marker beside its inputs, so RUNS still shows
        ✗ after a restart; a failed or cancelled job's own marker is kept as it is.
        """
        self._readback_failures[_run_key(run_dir)] = (status, detail)
        if self._in_project_runs(run_dir) and proj.read_run_state(run_dir) is None:
            try:
                proj.write_run_state(run_dir, "unreadable", "gui_readback")
            except ProjectError as exc:
                self.statusBar().showMessage(str(exc), 8000)
        self.refresh_workspace()  # RUNS shows the run as unreadable, never as its folder says
        self._show_run_in_inspector(run_dir)

    def _in_project_runs(self, run_dir: Path) -> bool:
        """A run folder directly under the open project's runs/ (never an outside run)."""
        project = self.session.project
        return project is not None and _same_folder(project.runs_dir, Path(run_dir).parent)

    def _from_closed_project(self, run_dir: Path) -> bool:
        """A job's run folder belongs to a project this window has closed since (and not to
        the open one): its result is never drawn, shown or listed here. Its run state is
        still recorded (`_settle_run_jobs`) and its page's buttons are released."""
        if self._in_project_runs(run_dir):
            return False
        parent = Path(run_dir).parent
        return any(_same_folder(runs, parent) for runs in self._closed_runs_dirs)

    def _clear_readback_marker(self, run_dir: Path) -> bool:
        """Drop a project run's `unreadable` marker before it is read back again."""
        if not self._in_project_runs(run_dir):
            return False
        try:
            return proj.clear_run_state(run_dir, "unreadable")
        except ProjectError as exc:
            self.statusBar().showMessage(str(exc), 8000)
            return False

    def _show_run_in_inspector(self, run_dir: Path) -> None:
        """Show a run as RUNS selection does; a failed GUI readback overrides its rows."""
        from cmig.cli.main import _inspect_run_dir

        run_dir = Path(run_dir).resolve()
        key = str(run_dir)
        cached, self._last_inspected = self._last_inspected, None
        inspected: dict[str, Any]
        try:
            fresh = cached[1] if cached is not None and cached[0] == key else None
            if fresh is None:
                fresh = self._run_off_thread(_inspect_run_dir, run_dir)
            inspected = dict(fresh)
            inspected["artifact_integrity"] = _integrity_text(inspected)
        except Exception as exc:  # noqa: BLE001 - an unreadable run is shown as unreadable
            inspected = {"artifact_integrity": f"unreadable ({exc})"}
        failure = self._readback_failures.get(key)
        if failure is not None:
            status, detail = failure
            inspected["status"] = status
            # The first detail line names the run folder, which the Folder row already shows.
            inspected["artifact_integrity"] = "; ".join(detail.splitlines()[1:]) or detail
        entry = self._run_entry(run_dir)
        if failure is None and entry.status in proj.RUN_STATE_STATUSES:
            # A failed or cancelled job's folder, whatever its own summary claims.
            inspected["status"] = merge_run_status(
                str(inspected.get("status", entry.status)), entry.status
            )
        command = self._run_commands.get(key, "")
        self.inspector.show_run(entry, inspected, command)
        self._inspector_run, self._inspected_model = key, None

    def _run_entry(self, run_dir: Path) -> RunEntry:
        for entry in self._display_runs([*self.session.runs(), *self._external_runs]):
            if entry.path == run_dir:
                return entry
        return self._display_runs([inspect_run(run_dir)])[0]

    def _display_runs(self, entries: list[RunEntry]) -> list[RunEntry]:
        """RUNS rows with the GUI's own verdict laid over what the folder says.

        A summary the GUI rejected reads as unreadable, and a folder left by a job that failed
        or was cancelled reads as failed or cancelled: neither may look like a result, whatever
        status a half-written summary in the folder claims.
        """
        shown: list[RunEntry] = []
        for entry in entries:
            key = _run_key(entry.path)
            status = (
                "unreadable" if key in self._readback_failures
                else merge_run_status(entry.status, self._run_states.get(key))
            )
            shown.append(entry if status == entry.status else replace(entry, status=status))
        return shown

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
        self._cancel_unlisted_jobs()
        self.runner.shutdown(wait=False, cancel_futures=True)
        self._close_session()
        super().closeEvent(event)

    # ── pages ────────────────────────────────────────────────────────────────────────────
    def _build_welcome_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addStretch(1)
        title = QLabel("<h2>CMIG</h2>Community metabolic interaction analysis")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_message = QLabel("")
        self.welcome_message.setWordWrap(True)
        self.welcome_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # The reason names user folders and files; never render it as markup.
        self.welcome_message.setTextFormat(Qt.TextFormat.PlainText)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        new_btn = QPushButton("New Project…")
        new_btn.clicked.connect(self._new_project_dialog)
        open_btn = QPushButton("Open Project…")
        open_btn.clicked.connect(self._open_project_dialog)
        run_btn = QPushButton("Open Run…")
        run_btn.clicked.connect(self._open_run_dialog)
        for button in (new_btn, open_btn, run_btn):
            buttons.addWidget(button)
        buttons.addStretch(1)
        self.welcome_recent = QListWidget()
        self.welcome_recent.setMaximumWidth(420)
        self.welcome_recent.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.welcome_recent.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.welcome_recent.itemActivated.connect(
            lambda item: self.open_project(Path(item.data(Qt.ItemDataRole.UserRole)))
        )
        recent_row = QHBoxLayout()
        recent_row.addStretch(1)
        recent_row.addWidget(self.welcome_recent)
        recent_row.addStretch(1)
        layout.addWidget(title)
        layout.addLayout(buttons)
        layout.addWidget(self.welcome_message)
        layout.addLayout(recent_row)
        layout.addStretch(2)
        return page

    def _build_empty_models_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addStretch(1)
        hint = QLabel("Drop SBML, JSON or MAT files or folders here")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        add_btn = QPushButton("Add Models…")
        add_btn.clicked.connect(self._add_models_dialog)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(add_btn)
        row.addStretch(1)
        layout.addWidget(hint)
        layout.addLayout(row)
        layout.addStretch(2)
        return page

    def _show_page(self, widget: QWidget) -> None:
        changed = self.pages.currentWidget() is not widget
        if self.pages.indexOf(widget) == -1:
            self.pages.addWidget(widget)
        self.pages.setCurrentWidget(widget)
        current = None if self._following_sidebar else self._sidebar_current()
        if current is not None and (changed or current[0] == "runs"):
            # The centre no longer shows the sidebar's current item (a run row names one
            # result, so any other show replaces it): drop it, keeping the selection, so
            # clicking that item again opens it.
            self.sidebar.selectionModel().setCurrentIndex(
                QModelIndex(), QItemSelectionModel.SelectionFlag.NoUpdate
            )
        self._update_run_action()

    def _show_profile(self, host_key: str = "community") -> None:
        """Show the community result (Profile | Graph) inside `host_key`'s results area."""
        self._show_page(self._host_community_result(host_key))

    def _host_community_result(self, host_key: str) -> QWidget:
        """Put the community result in `host_key`'s results area without changing the page."""
        page = self.analysis_pages[host_key]
        previous = self._community_result_host
        if previous is not None and previous != host_key:
            self.analysis_pages[previous].results.show_empty()
        if self._community_result_host != host_key:
            page.results.add(self.community_result_page, 1)
            self._community_result_host = host_key
        page.results.show_results()
        self.community_result_page.setCurrentWidget(self.profile_view)
        return page

    def _blank_base_for_overlay(self) -> None:
        """A Compare or Sandbox overlay is not about the loaded run: drop that run's table,
        targets, graph and badge so neither the page nor "Clear comparison overlay" shows them."""
        self._clear_community_result()
        if self._medium_delta_active:  # the overlay on show is no longer the medium's
            self._medium_delta_active = False
            self.medium_editor.profile_delta_label.clear()

    def _compare_failed(self) -> None:
        """A failed Compare leaves no earlier comparison on show (its status says why)."""
        self._empty_community_result_on("compare")
        self.scenario_compare.delta_view.setRowCount(0)
        self.scenario_compare.growth_label.clear()

    def _empty_community_result_on(self, host_key: str) -> None:
        """A failed run on `host_key` must not leave that page's previous result on show."""
        if self._community_result_host == host_key:
            self.analysis_pages[host_key].results.show_empty()

    def _clear_community_result(self) -> None:
        """Drop the shown community run (profile, graph, badge, manifest) and empty its page."""
        self.current_manifest = None
        self.current_graph_payload = None
        self.graph_view.clear()
        self.graph_gate_badge.set_unavailable()
        self.profile_view.load_profile([])
        self.profile_view.load_targets(None)
        host = self._community_result_host
        if host is not None:
            self.analysis_pages[host].results.show_empty()

    def _show_models_overview(self) -> None:
        project = self.session.project
        if project is None:
            self._show_page(self.welcome_page)
        elif not project.models:
            self._show_page(self.empty_models_page)
        else:
            self._show_page(self.model_manager)

    # ── actions & menus ──────────────────────────────────────────────────────────────────
    def _action(self, text: str, slot: Any, shortcut: Any = None) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        return action

    def _install_workflow_actions(self) -> None:
        self.new_project_action = self._action("New Project…", self._new_project_dialog,
                                               QKeySequence.StandardKey.New)
        self.open_project_action = self._action("Open Project…", self._open_project_dialog,
                                                QKeySequence.StandardKey.Open)
        self.recent_menu = QMenu("Open Recent", self)
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        self.close_project_action = self._action("Close Project", self._close_project_command,
                                                 QKeySequence.StandardKey.Close)
        self.add_models_action = self._action("Add Models…", self._add_models_dialog,
                                              "Ctrl+Shift+A")
        self.add_models_folder_action = self._action("Add Models from Folder…",
                                                     self._add_models_folder_dialog)
        self.add_agora2_action = self._action("Add Models from AGORA2…", self._agora2_dialog)
        self.add_medium_action = self._action("Add Medium…", self._add_medium_dialog)
        self.open_run_action = self._action("Open Run…", self._open_run_dialog, "Ctrl+Shift+O")
        self.show_project_action = self._action("Show Project in Finder", self._reveal_project)
        self.undo_action = self.session.undo_stack.createUndoAction(self, "Undo")
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.redo_action = self.session.undo_stack.createRedoAction(self, "Redo")
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.rename_action = self._action("Rename…", self._rename_selected_model)
        self.remove_action = self._action("Remove from Project", self._remove_selected_models,
                                          QKeySequence.StandardKey.Delete)
        # Delete removes the sidebar's selected models, so it must only fire while the sidebar
        # has focus — not when Delete is pressed in a table or editor elsewhere in the window.
        self.remove_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.find_action = self._action("Find…", self._focus_find, QKeySequence.StandardKey.Find)
        self.sidebar.addAction(self.remove_action)
        self.toggle_sidebar_action = self._action("Hide Sidebar",
                                                  lambda: self._toggle(self.sidebar, "Sidebar"),
                                                  "Ctrl+Meta+S")
        self.toggle_inspector_action = self._action(
            "Hide Inspector", lambda: self._toggle(self.inspector, "Inspector"), "Ctrl+Alt+I")
        self.toggle_activity_action = self._action(
            "Show Activity", lambda: self._toggle(self.activity, "Activity"), "Ctrl+Shift+Y")
        self.analysis_actions = {
            key: self._action(label, lambda _=False, k=key: self.show_analysis(k))
            for key, label in ANALYSES
        }
        self.run_action = self._action("Run", self._run_current_analysis, "Ctrl+R")
        self.cancel_job_action = self._action("Cancel", self._cancel_selected_job, "Ctrl+.")
        self.demo_run_action = self._action("Try Demo Run", self._run_fixture_dialog)
        guide = self._action("CMIG User Guide", self._open_user_guide)

        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        file_menu.addActions([self.new_project_action, self.open_project_action])
        file_menu.addMenu(self.recent_menu)
        file_menu.addAction(self.close_project_action)
        file_menu.addSeparator()
        file_menu.addActions([self.add_models_action, self.add_models_folder_action,
                              self.add_agora2_action, self.add_medium_action])
        file_menu.addSeparator()
        file_menu.addActions([self.open_run_action, self.show_project_action])
        edit_menu = bar.addMenu("&Edit")
        edit_menu.addActions([self.undo_action, self.redo_action])
        edit_menu.addSeparator()
        edit_menu.addActions([self.rename_action, self.remove_action])
        edit_menu.addSeparator()
        edit_menu.addAction(self.find_action)
        view_menu = bar.addMenu("&View")
        view_menu.addActions([self.toggle_sidebar_action, self.toggle_inspector_action,
                              self.toggle_activity_action])
        analysis_menu = bar.addMenu("&Analysis")
        for index, (_title, items) in enumerate(ANALYSIS_GROUPS):
            if index:
                analysis_menu.addSeparator()
            for key, _label in items:
                analysis_menu.addAction(self.analysis_actions[key])
        analysis_menu.addSeparator()
        analysis_menu.addActions([self.run_action, self.cancel_job_action])
        window_menu = bar.addMenu("&Window")
        window_menu.addAction(self._action("Minimize", self.showMinimized, "Ctrl+M"))
        window_menu.addAction(self._action("Zoom", self._zoom))
        help_menu = bar.addMenu("&Help")
        help_menu.addActions([guide, self.demo_run_action])

        toolbar = self.addToolBar("Workspace")
        toolbar.setObjectName("workspace_toolbar")
        toolbar.setMovable(False)
        self.workspace_toolbar = toolbar
        toolbar.addAction(self.toggle_sidebar_action)
        self.project_title = QLabel("No Project")
        toolbar.addWidget(self.project_title)
        toolbar.addSeparator()
        toolbar.addAction(self.add_models_action)
        new_analysis = QToolButton()
        new_analysis.setText("New Analysis")
        new_analysis.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        new_analysis.setMenu(analysis_menu)
        # QToolButton draws its menu arrow over the text's last letters; leave room for it.
        arrow = new_analysis.style().pixelMetric(
            QStyle.PixelMetric.PM_MenuButtonIndicator, None, new_analysis
        )
        new_analysis.setMinimumWidth(new_analysis.sizeHint().width() + 2 * arrow)
        toolbar.addWidget(new_analysis)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        toolbar.addWidget(self.find_field)
        toolbar.addAction(self.toggle_inspector_action)
        toolbar.addAction(self.run_action)

    def _focus_find(self) -> None:
        self.find_field.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.find_field.selectAll()

    def _toggle(self, widget: QWidget, name: str) -> None:
        # isHidden() is the pane's own state; isVisible() is also False while the window is.
        widget.setVisible(widget.isHidden())
        verb = "Show" if widget.isHidden() else "Hide"
        action = {"Sidebar": self.toggle_sidebar_action, "Inspector": self.toggle_inspector_action,
                  "Activity": self.toggle_activity_action}[name]
        action.setText(f"{verb} {name}")

    def _zoom(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _open_user_guide(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl("https://github.com/jyryu3161/CMIG/blob/main/docs/USER_GUIDE.md"))

    def _fill_recent_menu(self) -> None:
        self.recent_menu.clear()
        for path in self.recent.paths():
            action = self.recent_menu.addAction(path.name)
            action.setToolTip(str(path))
            action.triggered.connect(lambda _=False, p=path: self.open_project(p))
        self.recent_menu.addSeparator()
        clear = self.recent_menu.addAction("Clear Menu")
        clear.triggered.connect(self._clear_recent)

    def _clear_recent(self) -> None:
        self.recent.clear()
        self.refresh_workspace()

    # ── project lifecycle ────────────────────────────────────────────────────────────────
    def open_project(self, path: Path) -> bool:
        target = Path(path)
        current = self.session.project
        if current is not None and _same_folder(current.root, target):
            # Already open in this window; locking it again would report "already open in
            # another window".
            self.recent.add(current.root)
            self.refresh_workspace()
            return True
        # The target is locked and read first: a stale recent entry, a locked or damaged
        # project must not cost the open project or its running jobs anything.
        try:
            if not target.is_dir():
                raise ProjectError(f"folder not found: {target}")
            project, lock = ProjectSession.lock_and_open(target)
        except (ProjectError, OSError) as exc:
            self._project_refused(f"Could not open {target.name}: {exc}")
            return False
        if not self._switch_to(project, lock, f"{project.name} was not opened"):
            return False
        self.recent.add(target)
        return True

    def create_project(self, path: Path, name: str | None = None) -> bool:
        target = Path(path)
        try:
            project, lock = ProjectSession.create_and_lock(target, name)
        except ProjectError as exc:
            self._project_refused(f"Could not create the project: {exc}")
            return False
        declined = f"{project.name} was created at {project.root} but not opened"
        if not self._switch_to(project, lock, declined):
            return False
        self.recent.add(target)
        return True

    def _project_refused(self, message: str) -> None:
        """Report a project that could not be opened or created; the open one stays as it is."""
        if self.session.project is None:
            self.welcome_message.setText(message)
            self._show_page(self.welcome_page)
        self.statusBar().showMessage(message, 15000)

    def _switch_to(self, project: proj.Project, lock: proj.ProjectLock, declined: str) -> bool:
        """Make an already locked and read project current, closing the open one first.

        Asks before cancelling running jobs; a No gives the new project's lock back, leaves
        everything as it was and says `declined` in the status bar.
        """
        if self.session.project is not None:
            if not self._confirm_closing_with_jobs():
                with suppress(OSError):
                    lock.release()
                self.statusBar().showMessage(
                    f"{declined}; the current project and its jobs were kept.", 15000
                )
                return False
            self._cancel_project_jobs()
            self._close_session()
        try:
            self.session.attach(project, lock)
        except (ProjectError, OSError) as exc:
            self._project_refused(f"Could not open {project.name}: {exc}")
            return False
        self.welcome_message.setText("")
        return True

    def _active_job_ids(self) -> list[str]:
        """Queued or running jobs that closing the project would cancel (not yet cancelling)."""
        return [
            job_id for job_id in self.bridge._job_ids
            if job_id not in self.bridge.cancelling
            and self.runner.poll(job_id).status in (JobStatus.PENDING, JobStatus.RUNNING)
        ]

    def _confirm_closing_with_jobs(self) -> bool:
        """True when nothing runs, or the user agrees to cancel what does (default No)."""
        count = len(self._active_job_ids())
        if not count:
            return True
        running = "1 job is running" if count == 1 else f"{count} jobs are running"
        answer = QMessageBox.question(
            self, "Close Project",
            f"{running} — close the project anyway?\n\nQueued jobs are cancelled; a solve "
            "that is already running stops at its next checkpoint.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _cancel_project_jobs(self) -> None:
        for job_id in list(self.bridge._job_ids):
            if self.runner.poll(job_id).status in (JobStatus.PENDING, JobStatus.RUNNING):
                self._cancel_job_id(job_id)
        self._cancel_unlisted_jobs()

    def _cancel_unlisted_jobs(self) -> None:
        """Cancel this project's jobs that Activity does not list (index check, search rows)."""
        if self._index_job is not None and self._index_job_kind == "check":
            self.runner.cancel(self._index_job)
        if self._search_rows_job is not None:
            self.runner.cancel(self._search_rows_job)

    def _close_project_command(self) -> None:
        """File > Close Project: asks first when jobs are running."""
        if self.session.project is not None and self._confirm_closing_with_jobs():
            self.close_project()

    def close_project(self) -> None:
        """Cancel queued/running jobs (cooperative; an in-flight solve finishes) and unlock."""
        if self.session.project is None:
            return
        self._cancel_project_jobs()
        self._close_session()

    def _close_session(self) -> None:
        """Close the project; a failed final save is reported here, never raised into Qt."""
        self._clear_last_run()
        if self.session.project is not None:
            self._closed_runs_dirs.append(self.session.project.runs_dir)
        try:
            self.session.close()
        except ProjectError as exc:
            self.statusBar().showMessage(
                f"The project was closed, but its final save failed: {exc}", 15000
            )

    def _new_project_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "New Project", "", "CMIG project folder")
        if path:
            self.create_project(Path(path))

    def _open_project_dialog(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open Project")
        if path:
            self.open_project(Path(path))

    def _reveal_project(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        if self.session.project is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.session.project.root)))

    def refresh_workspace(self) -> None:
        project = self.session.project
        has_project = project is not None
        for action in (self.add_models_action, self.add_models_folder_action,
                       self.add_agora2_action, self.add_medium_action, self.close_project_action,
                       self.show_project_action):
            action.setEnabled(has_project)
        for action in self.analysis_actions.values():
            action.setEnabled(has_project)
        self.setWindowTitle("CMIG" if project is None else f"{project.name} — CMIG")
        self.project_title.setText("No Project" if project is None else project.name)
        root = None if project is None else project.root
        switched = root != self._shown_root
        if switched:
            self._pending_imports = []  # placeholders belong to the project they were queued in
            self._reported_unrunnable = {}
            self._clear_community_result()  # the shown run belongs to the previous project
            # A growth check of the previous project is no baseline for this one's medium delta.
            self._last_medium_growth_check = None
            self._medium_delta_active = False
            # Tool results belong to the previous project too.
            self.scenario_compare.delta_view.setRowCount(0)
            self.scenario_compare.growth_label.clear()
            self.sandbox_view.delta_view.setRowCount(0)
            self.sweep_view.table.setRowCount(0)
            editor = self.medium_editor
            for label in (editor.growth_label, editor.dropped_ids_label,
                          editor.profile_delta_label, editor.minimal_status):
                label.clear()
            editor.minimal_table.setRowCount(0)
            self.host_view.clear_result()
            self.host_view.status.clear()
            for ranked in (self.search_view, self.gene_ko_page, self.strain_growth_page,
                           self.ratio_impact_page, self.host_search_page):
                self._clear_ranked(ranked)
                ranked.status.clear()
            for dynamics in (self.dynamics_view, self.spatial_page):
                dynamics._clear_dynamics("")
            # Browse indexes, their failures and the browsed model belong to that project too.
            self._index_failures = {}
            self._index_cache = {}
            self._index_checked = set()
            self.model_browser.clear()
            self._browser_shown = None
            # So do its search rows and media; the open result list is the previous project's.
            self._search_rows = {}
            self._search_unreadable = set()
            self._medium_exchange_cache = {}
            self.find_field.popup.setVisible(False)
            # A namespace choice made for the previous project's models is not one for these.
            self._namespace_user_set = dict.fromkeys(self._namespace_user_set, False)
            self._namespace_defaults = dict.fromkeys(self._namespace_defaults, None)
        # Rebuilding a group drops its rows' selection; put it back unless the project changed.
        current = None if switched else self._sidebar_current()
        selected_models = [] if switched else self.sidebar.selected_keys("models")
        self.sidebar.set_models([] if project is None else project.models,
                                list(self._pending_imports))
        self.sidebar.set_media(installed_medium_presets(), [] if project is None else project.media)
        self.sidebar.set_runs(
            self._display_runs(self.session.runs()), self._display_runs(self._external_runs)
        )
        self._restore_sidebar_selection(current, selected_models)
        self._update_model_actions()
        self.welcome_recent.clear()
        for path in self.recent.paths():
            item = QListWidgetItem(f"{path.name}  —  {path.parent}")
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            self.welcome_recent.addItem(item)
        self.welcome_recent.setVisible(self.welcome_recent.count() > 0)
        self._refresh_pickers()
        self._apply_namespace_defaults()
        if switched:
            # Opened, switched or closed: lay the centre out for the new state.
            self._shown_root = root
            self.current_analysis = None
            self._show_project_summary()
            self._inspector_run, self._inspected_model = None, None
            self._show_models_overview()
            self._ensure_indexes()
            self._refresh_search_rows()
        elif project is not None and self.pages.currentWidget() in (
            self.welcome_page, self.empty_models_page, self.model_manager
        ):
            self._show_models_overview()
        elif (project is not None and self.pages.currentWidget() is self.model_browser
              and self.model_browser.model_id() not in {m.id for m in project.models}):
            # The browsed model was removed or renamed: never keep showing it as current.
            self.model_browser.clear()
            self._browser_shown = None
            self._show_models_overview()
        self.model_manager.show_project_models([] if project is None else project.models)
        self._update_run_action()
        self._search_changed()  # models, media or runs may have changed

    def _update_model_actions(self) -> None:
        """Rename… needs exactly one selected model; Remove from Project at least one."""
        keys = self.sidebar.selected_keys("models") if self.session.project is not None else []
        self.rename_action.setEnabled(len(keys) == 1)
        self.remove_action.setEnabled(bool(keys))

    def _sidebar_current(self) -> tuple[str, str] | None:
        item = self.sidebar.currentItem()
        parent = None if item is None else item.parent()
        key = None if item is None else item.data(0, Qt.ItemDataRole.UserRole)
        if parent is None or not isinstance(key, str):
            return None
        return _SIDEBAR_GROUPS[self.sidebar.indexOfTopLevelItem(parent)], key

    def _restore_sidebar_selection(
        self, current: tuple[str, str] | None, selected_models: list[str]
    ) -> None:
        """Re-select rows after a rebuild without re-running their selection handlers."""
        blocked = self.sidebar.blockSignals(True)
        try:
            if current is None:
                self.sidebar.selectionModel().clear()
            else:
                self.sidebar.select(*current)
            models = self.sidebar.topLevelItem(_SIDEBAR_GROUPS.index("models"))
            if models is not None:
                for i in range(models.childCount()):
                    child = models.child(i)
                    if child.data(0, Qt.ItemDataRole.UserRole) in selected_models:
                        child.setSelected(True)
        finally:
            self.sidebar.blockSignals(blocked)

    #: what each model picker is called in status messages
    _PICKER_LABELS = {
        "search": "Search", "community": "Community", "host_model": "Host model",
        "host": "Host microbes", "dfba": "dFBA", "sweep": "Sweep",
        "medium": "Medium growth check", "medium_single": "Minimal medium",
        "gene_ko": "Gene Knockout", "strain_growth": "Strain Growth",
        "ratio_impact": "Ratio Impact", "host_search_model": "Host search host",
        "host_search": "Host search microbes",
    }

    def _model_pickers(self) -> dict[str, ModelPicker]:
        """Every model picker, keyed by the analysis setting that remembers its choice.

        The host model comes before the microbes: the microbes' default leaves it out.
        """
        return {
            "search": self.search_view.model_picker,
            "gene_ko": self.gene_ko_page.model_picker,
            "strain_growth": self.strain_growth_page.model_picker,
            "ratio_impact": self.ratio_impact_page.model_picker,
            "community": self.community_builder.model_picker,
            "host_model": self.host_view.host_picker,
            "host": self.host_view.model_picker,
            "host_search_model": self.host_search_page.host_picker,
            "host_search": self.host_search_page.model_picker,
            "dfba": self.dynamics_view.model_picker,
            "sweep": self.sweep_view.model_picker,
            "medium": self.medium_editor.model_picker,
            "medium_single": self.medium_editor.single_model_picker,
        }

    def _medium_pickers(self) -> dict[tuple[str, str], MediumPicker]:
        """Every medium picker, keyed by (analysis setting, field) that remembers its choice."""
        return {
            ("search", "medium"): self.search_view.medium_picker,
            ("gene_ko", "medium"): self.gene_ko_page.medium_picker,
            ("strain_growth", "medium"): self.strain_growth_page.medium_picker,
            ("ratio_impact", "medium"): self.ratio_impact_page.medium_picker,
            ("host", "host_medium"): self.host_view.host_medium_picker,
            ("host", "microbe_medium"): self.host_view.microbe_medium_picker,
            ("host_search", "host_medium"): self.host_search_page.host_medium_picker,
            ("host_search", "microbe_medium"): self.host_search_page.microbe_medium_picker,
            ("check_growth", "medium"): self.model_browser.medium_picker,
        }

    def _refresh_pickers(self) -> None:
        """Offer the project's models and media; restore each analysis' remembered choice.

        Without a remembered choice a multi-model picker selects every runnable model (the
        Host microbes leave out the chosen host model), so a model added later is included
        until the user picks for themselves. A remembered model that can no longer run is left
        out and named in the status bar, once.
        """
        project = self.session.project
        models = [] if project is None else project.models
        choices = [(m.id, not _not_runnable(m), _not_runnable(m)) for m in models]
        runnable = [model_id for model_id, ok, _reason in choices if ok]
        known = {m.id for m in models}
        presets = installed_medium_presets()
        media = [] if project is None else [(m.id, m.integrity == "ok") for m in project.media]
        missing: list[str] = []
        left_out: list[str] = []
        self._refreshing_pickers = True
        try:
            for key, picker in self._model_pickers().items():
                picker.set_choices(choices)
                saved = self.session.settings(key).get("models")
                if isinstance(saved, list):
                    wanted = [str(x) for x in saved]
                    picker.set_selected(wanted)
                    lost = {m for m in wanted if m in known and m not in runnable}
                    new = sorted(lost - self._reported_unrunnable.get(key, set()))
                    left_out += [f"{m} ({self._PICKER_LABELS[key]})" for m in new]
                    self._reported_unrunnable[key] = lost
                elif not picker.single:
                    host_pickers = {"host": self.host_view.host_picker,
                                    "host_search": self.host_search_page.host_picker}
                    host = host_pickers[key].selected_ids() if key in host_pickers else []
                    picker.set_selected([m for m in runnable if m not in host])
            for (key, field), medium_picker in self._medium_pickers().items():
                medium_picker.set_choices(presets, media)
                ref = self.session.settings(key).get(field)
                if isinstance(ref, str) and ref != medium_picker.current_ref():
                    try:
                        medium_picker.set_ref(ref)
                    except ValueError:
                        missing.append(ref.partition(":")[2])
        finally:
            self._refreshing_pickers = False
        notes = []
        if left_out:
            notes.append(f"Remembered models that cannot run were left out: {', '.join(left_out)}")
        if missing:
            notes.append(f"Remembered medium no longer available: {', '.join(sorted(set(missing)))}"
                         "; the model default is selected instead")
        if notes:
            self.statusBar().showMessage("; ".join(notes) + ".", 15000)

    def _host_model_changed(self, page: HostInputWidgets) -> None:
        """A newly chosen host model is unticked from Microbes; re-ticking it is refused at run."""
        if self._refreshing_pickers:
            return
        host = page.host_picker.selected_ids()
        microbes = page.model_picker.selected_ids()
        if host and host[0] in microbes:
            page.model_picker.set_selected([m for m in microbes if m != host[0]])

    def _store_settings(self, key: str, values: dict[str, object]) -> None:
        try:
            self.session.store_settings(key, values)
        except ProjectError as exc:
            self.statusBar().showMessage(f"Could not save the analysis settings: {exc}", 8000)

    def _remember(self, key: str, picker: ModelPicker) -> None:
        """Keep a picker's choice in the project (a failed save is reported, never raised)."""
        if self._refreshing_pickers or self.session.project is None:
            return
        values = self.session.settings(key)
        values["models"] = picker.selected_ids()
        self._store_settings(key, values)

    def _remember_medium(self, key: str, field: str, picker: MediumPicker) -> None:
        if self._refreshing_pickers or self.session.project is None:
            return
        values = self.session.settings(key)
        values[field] = picker.current_ref()
        self._store_settings(key, values)

    def _prepare_run(
        self, kind: str, model_ids: list[str], *, abundances: dict[str, float] | None = None,
        analysis: str | None = None,
    ) -> tuple[Path, Path | None]:
        """Claim a new `runs/<kind>-…` folder, write its `runs/_inputs` taxonomy and, for an
        analysis page, the page's inputs (`<run>-request.json`, for reopening the run).

        Returns (run folder, taxonomy or None when `model_ids` is empty). A model that cannot
        run, or inputs that cannot be recorded, raise `ProjectError`; the claimed folder and
        its inputs are removed again, so a refused run leaves nothing in RUNS, and the sidebar
        and pickers show the model's new state.
        """
        project = self.session.require()
        run_dir = proj.new_run_dir(project, kind)
        try:
            taxonomy = (
                proj.write_run_taxonomy(project, run_dir, model_ids, abundances)
                if model_ids else None
            )
        except ProjectError:
            with suppress(OSError):
                run_dir.rmdir()
            self.refresh_workspace()  # a copy found changed or missing is shown and dropped
            raise
        if analysis is not None:
            try:
                self._record_request(analysis, run_dir)
            except ProjectError:
                self._discard_run(run_dir, taxonomy)
                raise
        return run_dir.resolve(), taxonomy

    def _record_request(self, analysis: str, run_dir: Path) -> None:
        """Write the page's inputs as the run's `runs/_inputs/<run>-request.json`."""
        from cmig import __version__
        from cmig.gui.run_restore import request_models_and_media

        page: AnalysisPage | ModelBrowser = (
            self.model_browser if analysis == "check_growth" else self.analysis_pages[analysis]
        )
        values = page.snapshot()
        page.clear_banner()
        models, media = request_models_and_media(values)
        if analysis == "check_growth" and isinstance(values.get("model"), str):
            models = [values["model"]]  # the browser names one model, not a picker list
        proj.write_run_request(run_dir, analysis, values, models=models, media=media,
                               cmig_version=__version__)

    def _page_key(self, page: QWidget) -> str:
        return next(key for key, shown in self.analysis_pages.items() if shown is page)

    @staticmethod
    def _discard_run(run_dir: Path, *inputs: Path | None) -> None:
        """Remove a claimed run folder (still empty) and its inputs when the GUI refuses it."""
        for path in (*inputs, proj.run_request_path(run_dir)):
            if path is not None:
                with suppress(OSError):
                    path.unlink()
        with suppress(OSError):
            run_dir.rmdir()

    def _medium_arg(self, ref: str) -> str | None:
        """The `--medium` path for a medium picker ref ("" = model default → None).

        A project medium is re-hashed first: a copy that changed or went missing since it was
        added is refused, never passed to the CLI.
        """
        if not ref:
            return None
        kind, _, name = ref.partition(":")
        if kind == "preset":
            return str(installed_medium_preset_path(name))
        if kind != "medium":
            raise ValueError(f"unknown medium choice {ref!r}")
        project = self.session.require()
        entry = project.medium(name)
        state = proj.refresh_integrity(project, entry)
        if state != "ok":
            self.refresh_workspace()
            reason = "changed since it was added" if state == "changed" else "is missing"
            raise ProjectError(f"medium {name!r} cannot be used: its file {reason}")
        return str(proj.medium_path(project, entry))

    def _model_file(self, model_id: str) -> Path:
        """The project copy of one model passed as `--host`/`--model`, checked like a
        taxonomy row (re-hashed; a changed, missing or failed model is refused)."""
        project = self.session.require()
        entry = project.model(model_id)
        proj.refresh_integrity(project, entry)
        reason = _not_runnable(entry)
        if reason:
            self.refresh_workspace()
            raise ProjectError(f"model {model_id!r} is not selectable: {reason}")
        return proj.model_path(project, entry).resolve()

    def _record_command(self, job_id: str, out_dir: Path, argv: list[str]) -> None:
        """Keep the equivalent `cmig` command for Activity and the run's Copy Command, and
        which run folder the job writes (see `_settle_run_jobs`)."""
        command = command_line(argv)
        self._job_commands[job_id] = command
        self._run_commands[str(out_dir)] = command
        self._job_runs[job_id] = out_dir

    # ── selection → page + inspector ─────────────────────────────────────────────────────
    def _run_buttons(self) -> dict[str, QAbstractButton]:
        """The page button Run (⌘R) presses for each analysis with one main run.

        Run goes through the button so the page's own guards hold: a page disables its button
        while its job runs or its cancel is pending, and Run is disabled with it.
        """
        return {
            "search": self.search_view.run_btn,
            "gene_ko": self.gene_ko_page.run_btn,
            "strain_growth": self.strain_growth_page.run_btn,
            "ratio_impact": self.ratio_impact_page.run_btn,
            "community": self.community_builder.run_btn,
            "host": self.host_view.run_btn,
            "host_search": self.host_search_page.run_btn,
            "dfba": self.dynamics_view.run_dfba_btn,
            "spatial": self.spatial_page.run_btn,
            "medium": self.medium_editor.check_growth_btn,
            "sweep": self.sweep_view.run_btn,
        }

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt override
        if event.type() == QEvent.Type.EnabledChange and any(
            watched is button for button in self._run_buttons().values()
        ):
            self._update_run_action()  # a page Run button changed: Run follows it
        return super().eventFilter(watched, event)

    _DESCRIPTIONS = {
        "search": ("Rank model combinations by a target metabolite.", "cmig search"),
        "gene_ko": ("Rank single-gene knockouts of a fixed combination.", "cmig gene-ko-search"),
        "strain_growth": ("Growth of each strain alone and in the community.",
                          "cmig strain-growth"),
        "ratio_impact": ("How one member's share changes a target metabolite.",
                         "cmig abundance-impact"),
        "community": ("Community FBA of selected members.", "cmig solve"),
        "host": ("Couple a host model with microbial models.", "cmig host-microbe-bigg"),
        "host_search": ("Rank microbial combinations for a host.", "cmig host-search-bigg"),
        "dfba": ("Well-mixed dynamic FBA of one model.", "cmig dfba"),
        "spatial": ("Preview how one metabolite spreads on a grid.", "cmig spatial-preview"),
        "medium": ("Edit a medium, check growth, find a minimal medium.",
                   "cmig solve / minimal-medium"),
        "sweep": ("Parameter sweep across media, abundances and solvers.", "cmig sweep"),
        "sandbox": ("Preview one bound change before committing it.", "cmig sandbox-fixture"),
        "compare": ("Compare two completed runs.", "cmig inspect-run"),
    }

    def show_analysis(self, key: str, *, select: bool = True) -> None:
        """Show `key`'s page; `select=False` leaves the sidebar's row (an opened run) as is."""
        page = self.analysis_pages[key]
        getattr(page, "clear_banner", lambda: None)()  # a banner is about one reopened run
        self.current_analysis = key
        self._show_page(page)
        if select:
            blocked = self.sidebar.blockSignals(True)
            try:
                self.sidebar.select("analyses", key)  # a menu choice shows in the sidebar too
            finally:
                self.sidebar.blockSignals(blocked)
        title = dict(ANALYSES)[key]
        description, cli = self._DESCRIPTIONS[key]
        self.inspector.show_analysis(title, description, cli)
        self._inspector_run, self._inspected_model = None, None
        self._update_run_action()

    def _current_run_button(self) -> QAbstractButton | None:
        """The current analysis page's Run button, when that page is on show."""
        key = self.current_analysis
        if key is None or self.pages.currentWidget() is not self.analysis_pages.get(key):
            return None
        return self._run_buttons().get(key)

    def _update_run_action(self) -> None:
        key = self.current_analysis
        on_page = key is not None and self.pages.currentWidget() is self.analysis_pages.get(key)
        button = self._current_run_button()
        busy = button is not None and not button.isEnabled()
        enabled = self.session.project is not None and button is not None and not busy
        self.run_action.setEnabled(enabled)
        if enabled:
            tip = "Run this analysis (⌘R)"
        elif self.session.project is None:
            tip = "Open a project to run an analysis"
        elif busy:
            tip = "This analysis is already running"
        elif on_page:
            tip = "Use the buttons on this page"
        else:
            tip = "Choose an analysis to run"
        self.run_action.setToolTip(tip)

    def _run_current_analysis(self) -> None:
        """Press the page's own Run button; nothing happens while that button is disabled."""
        button = self._current_run_button()
        if self.session.project is not None and button is not None and button.isEnabled():
            button.click()

    def _on_sidebar_selection(self, group: str, key: str) -> None:
        self._following_sidebar = True
        try:
            project = self.session.project
            if group == "analyses":
                self.show_analysis(key)
            elif group == "models" and project is not None:
                self._show_model(project.model(key))
            elif group == "media":
                self._inspect_medium(key)
            elif group == "runs":
                self.current_analysis = None
                self._open_run_entry(Path(key))
        finally:
            self._following_sidebar = False

    def _inspect_model(self, entry: ModelEntry) -> None:
        project = self.session.require()
        self.inspector.show_model(project, entry)
        self._inspector_run, self._inspected_model = None, (entry.id, entry.sha256)

    def _show_model(self, entry: ModelEntry) -> None:
        self._inspect_model(entry)
        self.current_analysis = None
        index = self._load_index(entry)
        self.model_browser.show_model(entry, index, self._index_problem(entry))
        self._browser_shown = self._browser_state(entry)
        self._show_page(self.model_browser)
        if index is None and entry.sha256 not in self._index_failures:
            self._index_checked.discard(entry.sha256)  # unusable now, whatever a job found
            self._ensure_indexes()
        self._show_latest_growth(entry)

    def _index_problem(self, entry: ModelEntry, unfinished: str = "") -> str:
        """Why `entry` has no browse index, or "" while one is (or will be) built."""
        if entry.sha256 in self._index_failures:
            return self._index_failures[entry.sha256]
        if entry.status not in ("ok", "warning") or entry.integrity != "ok":
            return proj.check_reason(entry)[1].lower()  # never indexed: not "being built"
        return unfinished

    def _load_index(self, entry: ModelEntry) -> dict[str, Any] | None:
        from cmig.io import model_index

        project = self.session.require()
        cached = self._index_cache.get(entry.sha256)
        if cached is not None:
            return cached
        index = model_index.load_index(project.root, entry.sha256)
        if index is not None:
            if len(self._index_cache) >= 4:
                self._index_cache.pop(next(iter(self._index_cache)))
            self._index_cache[entry.sha256] = index
        return index

    def _ensure_indexes(self) -> None:
        """Check the model indexes not yet checked, in the background.

        Nothing is read on the GUI thread: an unlisted job opens the index files, and only
        when some cannot be used (missing, corrupt, older schema, another model's) does an
        "Index Models" job in Activity rebuild them.
        """
        from cmig.io import model_index

        project = self.session.project
        if project is None or self._index_job is not None:
            return
        wanted = [
            (m.id, m.sha256, proj.model_path(project, m)) for m in project.models
            if m.status in ("ok", "warning") and m.integrity == "ok"
            and m.sha256 not in self._index_failures
            and m.sha256 not in self._index_cache
            and m.sha256 not in self._index_checked
        ]
        if not wanted:
            return
        root = project.root

        def _job(ctx: Any) -> dict[str, Any]:
            valid: list[str] = []
            needed: list[tuple[str, str, Path]] = []
            for model_id, sha, path in wanted:
                if ctx.cancelled:
                    break
                if model_index.load_index(root, sha) is None:
                    needed.append((model_id, sha, path))
                else:
                    valid.append(sha)
            return {"valid": valid, "needed": needed, "root": str(root),
                    "cancelled": ctx.cancelled}

        # A read of small files, not a user job: kept out of Activity.
        self._index_job = self.runner.submit("index_check", _job)
        self._index_job_kind, self._index_job_root = "check", root

    def _build_indexes(self, wanted: list[tuple[str, str, Path]], root: Path) -> None:
        """Rebuild the given model indexes in one background job (listed in Activity)."""
        from cmig.io import model_index

        def _job(ctx: Any) -> dict[str, Any]:
            rebuilt: list[str] = []
            failures: dict[str, str] = {}
            for i, (model_id, sha, path) in enumerate(wanted):
                if ctx.cancelled:
                    break
                ctx.report_progress(i, len(wanted))
                try:
                    model_index.build_index_file(root, path, sha, model_id)
                    rebuilt.append(sha)
                except Exception as exc:  # noqa: BLE001 - one bad model must not stop the rest
                    failures[sha] = str(exc) or type(exc).__name__
            ctx.report_progress(len(wanted), len(wanted))
            return {"rebuilt": rebuilt, "failures": failures, "root": str(root),
                    "cancelled": ctx.cancelled}

        self._index_job = self.runner.submit("index_models", _job)
        self._index_job_kind, self._index_job_root = "build", root
        self.bridge.track(self._index_job)
        self._job_commands[self._index_job] = f"Index {len(wanted)} model(s)"

    def _finish_index_job(self) -> None:
        jid = self._index_job
        if jid is None:
            return
        job = self.runner.poll(jid)
        if job.status not in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
            return
        kind, job_root = self._index_job_kind, self._index_job_root
        self._index_job, self._index_job_root = None, None
        project = self.session.project
        result = job.result if isinstance(job.result, dict) else {}
        self.runner.release_payload(jid)
        if project is None:
            return
        if job_root is None or not _same_folder(project.root, job_root):
            self._ensure_indexes()  # it was the previous project's job: start this project's
            return
        cancelled = job.status is JobStatus.CANCELLED or bool(result.get("cancelled"))
        finished = job.status is JobStatus.DONE and not cancelled
        if kind == "check":
            self._index_checked.update(result.get("valid", []))
            needed = [item for item in result.get("needed", [])
                      if item[1] not in self._index_failures]
            if finished and needed:
                self._build_indexes(needed, job_root)
            elif finished:
                self._ensure_indexes()  # models added or retried while it ran
        else:
            self._index_failures.update(result.get("failures", {}))
            self._index_checked.update(result.get("rebuilt", []))
            if finished:
                self._ensure_indexes()  # models added or retried while this job ran
        # Contents still missing after a cancelled or failed job are not "being built".
        unfinished = (
            "indexing was cancelled" if cancelled
            else "" if job.status is JobStatus.DONE else f"indexing failed: {job.error or jid}"
        )
        # Only a browsed model still waiting for its contents is redrawn, and only its
        # contents: the header (namespace, Check Growth result) and a shown index stay as they are.
        model_id = self.model_browser.model_id()
        if model_id is not None and not self.model_browser.has_index():
            try:
                entry = project.model(model_id)
            except ProjectError:
                entry = None
            if entry is not None:
                self.model_browser.set_contents(
                    self._load_index(entry), self._index_problem(entry, unfinished)
                )
        self._index_changed()

    def _index_changed(self) -> None:
        """An index job finished: read the search rows of the indexes now usable."""
        # A rebuilt index may be one the search job could not read before.
        self._search_unreadable -= self._index_checked
        self._search_changed()  # the footer counts depend on the index state
        self._refresh_search_rows()

    def _search_changed(self) -> None:
        """Drop the cached search table; an open result list is redrawn from a new one."""
        self._search_cache = None
        if not self._search_building:  # a medium check inside the build may refresh the window
            self.find_field.refresh()

    # ── project search (⌘F) ──────────────────────────────────────────────────────────────
    def _refresh_search_rows(self) -> None:
        """Read the search rows of indexed models not read yet, in an unlisted job."""
        from cmig.io import model_index

        project = self.session.project
        if project is None or self._search_rows_job is not None:
            return
        wanted = [m.sha256 for m in project.models
                  if m.sha256 not in self._search_rows and m.sha256 not in self._search_unreadable
                  and model_index.index_path(project.root, m.sha256).exists()]
        if not wanted:
            return
        root = project.root

        def _job(ctx: Any) -> dict[str, Any]:
            rows: dict[str, list[tuple[str, str, str]]] = {}
            bad: list[str] = []
            for sha in wanted:
                if ctx.cancelled:
                    break
                index = model_index.load_index(root, sha)
                if index is None:
                    bad.append(sha)
                else:
                    rows[sha] = model_index.search_rows(index)
            return {"root": str(root), "rows": rows, "bad": bad}

        # A read of small files, not a user job: kept out of Activity.
        self._search_rows_job = self.runner.submit("search_rows", _job)
        self._search_rows_wanted = (root, wanted)

    def _finish_search_rows_job(self) -> None:
        jid = self._search_rows_job
        if jid is None:
            return
        job = self.runner.poll(jid)
        if job.status not in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
            return
        wanted = self._search_rows_wanted
        self._search_rows_job, self._search_rows_wanted = None, None
        project = self.session.project
        result = job.result if isinstance(job.result, dict) else {}
        # Rows read for a previous project (closed or switched while it ran) are dropped.
        if project is not None and result.get("root") == str(project.root):
            self._search_rows.update(result.get("rows", {}))
            self._search_unreadable.update(result.get("bad", []))
        elif (job.status is JobStatus.FAILED and project is not None and wanted is not None
              and wanted[0] == project.root):
            # Not searchable, rather than read again (and fail again) at every poll.
            self._search_unreadable.update(wanted[1])
        self.runner.release_payload(jid)
        self._search_changed()
        self._refresh_search_rows()  # an index built meanwhile, or the new project's rows

    def _search_table(self) -> SearchTable:
        if self._search_cache is None:
            self._search_building = True
            try:
                self._search_cache = self._build_search_table()
            finally:
                self._search_building = False
        return self._search_cache

    def _build_search_table(self) -> SearchTable:
        project = self.session.project
        if project is None:
            return SearchTable()
        by_model = {m.id: self._search_rows[m.sha256] for m in project.models
                    if m.sha256 in self._search_rows}
        indexing = sum(1 for m in project.models
                       if m.sha256 not in self._search_rows
                       and m.sha256 not in self._search_unreadable
                       and m.sha256 not in self._index_failures
                       and m.status in ("ok", "warning") and m.integrity == "ok")
        unreadable = sum(1 for m in project.models
                         if m.sha256 in self._search_unreadable
                         or m.sha256 in self._index_failures)
        media = [(f"preset:{name}", name, self._medium_exchanges(f"preset:{name}"))
                 for name in installed_medium_presets()]
        media += [(f"medium:{m.id}", m.id, self._medium_exchanges(f"medium:{m.id}"))
                  for m in project.media]
        runs = [(str(e.path), e.name, f"{e.label} · {e.status}")
                for e in self._display_runs(self.session.runs())]
        return build_table([(m.id, Path(m.file).name) for m in project.models], by_model,
                           media, runs, indexing=indexing, unreadable=unreadable)

    def _medium_exchanges(self, ref: str) -> list[str]:
        cached = self._medium_exchange_cache.get(ref)
        if cached is not None:
            return cached
        from cmig.core.medium_spec import load_medium

        try:
            path = self._medium_arg(ref)
            ids = sorted(load_medium(path).uptake) if path else []
        except Exception:  # noqa: BLE001 - an unreadable medium is simply not searchable
            ids = []
        self._medium_exchange_cache[ref] = ids
        return ids

    def _find_activated(self, kind: str, key: str, model: object) -> None:
        project = self.session.project
        if project is None:
            return
        if kind == "run":
            before = self._sidebar_current()
            self.sidebar.select("runs", key)  # selecting a new RUNS row opens the run
            if self._sidebar_current() == before:  # already selected, or not listed in RUNS
                self._open_run_entry(Path(key))
        elif kind == "medium":
            self.sidebar.select("media", key)
        else:
            model_id = key if kind == "model" else str(model)
            try:
                entry = project.model(model_id)
            except ProjectError:
                return  # removed or renamed since the result list was drawn
            self.sidebar.select("models", model_id)
            if self.model_browser.model_id() != model_id or (
                self.pages.currentWidget() is not self.model_browser
            ):
                self._show_model(entry)
            if kind != "model":
                self.model_browser.select(kind, key)

    def _retry_index(self, model_id: str) -> None:
        project = self.session.require()
        entry = project.model(model_id)
        self._index_failures.pop(entry.sha256, None)
        self._index_cache.pop(entry.sha256, None)
        self._index_checked.discard(entry.sha256)
        self.model_browser.set_contents(None, "")
        self._search_changed()  # no longer "could not be searched": being indexed again
        self._ensure_indexes()

    # ── namespace confirmation and Check Growth (model browser) ──────────────────────────
    @staticmethod
    def _browser_state(entry: ModelEntry) -> tuple[str, str, str, str, str]:
        return (entry.id, entry.sha256, proj.confirmation_state(entry), entry.status,
                entry.integrity)

    def _confirm_namespace(self, model_id: str) -> None:
        answer = QMessageBox.question(
            self, "Confirm Namespace",
            f"I reviewed {model_id}; its exchange ids already use the BiGG namespace.\n\n"
            "CMIG will pass --assume-bigg-namespace for runs whose models are all confirmed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.session.confirm_namespace(model_id)
        except ProjectError as exc:
            self.statusBar().showMessage(str(exc), 8000)
            self.refresh_workspace()  # e.g. its file was found changed: the sidebar says so
        self._refresh_browser(model_id)

    def _revoke_namespace(self, model_id: str) -> None:
        try:
            self.session.revoke_namespace(model_id)
        except ProjectError as exc:
            self.statusBar().showMessage(str(exc), 8000)
        self._refresh_browser(model_id)

    def _refresh_browser(self, model_id: str) -> None:
        """Redraw the browsed model when its state differs from what the browser shows."""
        project = self.session.project
        if project is None or self.model_browser.model_id() != model_id:
            return
        entry = next((m for m in project.models if m.id == model_id), None)
        if entry is None or self._browser_state(entry) == self._browser_shown:
            return
        self.model_browser.show_model(entry, self._load_index(entry),
                                      self._index_problem(entry))
        self._browser_shown = self._browser_state(entry)
        self._show_latest_growth(entry)

    def _browser_models_changed(self) -> None:
        model_id = self.model_browser.model_id()
        if model_id is not None:
            self._refresh_browser(model_id)

    def _namespace_selection_changed(self, key: str) -> None:
        self._namespace_user_set[key] = False
        self._namespace_defaults[key] = None
        self._apply_namespace_defaults()

    def _namespace_targets(self) -> dict[str, tuple[QCheckBox, QLabel, list[str]]]:
        """Community's and Medium's "already BiGG" box, its note and the models it covers."""
        return {
            "community": (self.community_builder.assume_bigg_check,
                          self.community_builder.namespace_note,
                          self.community_builder.model_picker.selected_ids()),
            "medium": (self.medium_editor.assume_bigg_check, self.medium_editor.namespace_note,
                       list(dict.fromkeys(self.medium_editor.model_picker.selected_ids()
                                          + self.medium_editor.single_model_picker
                                          .selected_ids()))),
        }

    def _restore_assume_bigg(self, key: str, value: Any) -> str | None:
        """Put a run's "already BiGG" tick back only while every model it covers is confirmed
        in this project now; a confirmation revoked or gone stale since is never restored."""
        check, _note, ids = self._namespace_targets()[key]
        project = self.session.project
        if value is not True:
            check.setChecked(False)
            return None
        known = [] if project is None else [i for i in ids
                                            if any(m.id == i for m in project.models)]
        confirmed_all, missing = (
            (False, []) if project is None else proj.confirmation_summary(project, known)
        )
        if confirmed_all:
            check.setChecked(True)
            return None
        check.setChecked(False)
        return ("namespace confirmation not restored: "
                + (f"{', '.join(missing)} not confirmed" if missing else "no model is chosen"))

    def _apply_namespace_defaults(self) -> None:
        """Tick "already BiGG" on Community and Medium only when every chosen model is
        confirmed in this project (a box the user set stays until that page's models change)."""
        project = self.session.project
        for key, (check, note, ids) in self._namespace_targets().items():
            if project is None or not ids:
                note.setText("")
                continue
            known = [i for i in ids if any(m.id == i for m in project.models)]
            confirmed_all, missing = proj.confirmation_summary(project, known)
            if not confirmed_all:
                note.setText(f"{', '.join(missing)} not confirmed")
            elif len(known) == 1:
                note.setText(f"{known[0]} is confirmed in this project")
            else:
                note.setText(f"All {len(known)} models confirmed in this project")
            last = self._namespace_defaults[key]
            if not self._namespace_user_set[key] and (last is None or check.isChecked() == last):
                self._namespace_defaults[key] = confirmed_all
                if check.isChecked() == confirmed_all:
                    continue
                blocked = check.blockSignals(True)
                try:
                    check.setChecked(confirmed_all)
                finally:
                    check.blockSignals(blocked)
                if key == "medium":
                    self._medium_context_changed()  # its toggled handler, blocked above

    def _growth_running(self, entry: ModelEntry) -> bool:
        return any(model_id == entry.id and sha == entry.sha256
                   for _run, model_id, sha in self._check_growth_jobs.values())

    def run_check_growth(self, model_id: str | None = None) -> str:
        """`cmig single --fba` of the browsed model; returns the job id, or "" when refused."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        project = self.session.require()
        model_id = model_id or self.model_browser.model_id()
        if model_id is None:
            return ""
        if model_id != self.model_browser.model_id():
            # The browser's medium and options are the run's inputs: never another model's.
            self.statusBar().showMessage(
                f"Check Growth runs on the model shown in the browser; select {model_id} first",
                8000,
            )
            return ""
        entry = project.model(model_id)
        if proj.refresh_integrity(project, entry) != "ok":
            self.refresh_workspace()  # a changed or missing file is shown as such
        if not proj.namespace_confirmed(entry):
            self._refresh_browser(model_id)  # e.g. "Changed since confirmed"
            self.model_browser.set_growth(
                "✗ Not run: confirm this model's namespace first (Confirm…). `cmig single` "
                "refuses to run without a namespace decision."
            )
            return ""
        values = self.model_browser.snapshot()
        try:
            model_file = self._model_file(model_id)
            medium_file = self._medium_arg(str(values["medium"]))
            out_dir, _ = self._prepare_run("check-growth", [], analysis="check_growth")
        except (ProjectError, ValueError) as exc:
            self.model_browser.set_growth(f"✗ Not run: {exc}")
            return ""
        argv = ["single", "--model", str(model_file), "--fba", "--out", str(out_dir)]
        if medium_file:
            argv.extend(["--medium", medium_file, "--exact-medium"])
        if values["skip_unknown"]:
            argv.append("--allow-unknown-medium")
        argv.append("--assume-bigg-namespace")
        _install_stderr_router()

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            with _captured_job_stderr() as stderr_chunks:
                rc = main(argv)
            if rc != 0:
                lines = "".join(stderr_chunks).strip().splitlines()
                raise RuntimeError(lines[-1] if lines else f"cmig single exited {rc}")
            _finish_after_artifacts(ctx)
            return {"rc": rc}

        jid = self.submit_job("check_growth", _job)
        self._record_command(jid, out_dir, argv)
        self._check_growth_jobs[jid] = (out_dir, entry.id, entry.sha256)
        self.model_browser.check_growth_btn.setEnabled(False)
        self.model_browser.set_growth("Checking growth…")
        return jid

    def _finish_check_growth_jobs(self) -> None:
        for jid, (out_dir, model_id, sha) in list(self._check_growth_jobs.items()):
            job = self.runner.poll(jid)
            if job.status not in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
                continue
            self._check_growth_jobs.pop(jid, None)
            project = self.session.project
            entry = (None if project is None or not self._in_project_runs(out_dir)
                     else next((m for m in project.models if m.id == model_id), None))
            # Only the same model file, in the project the run was made in, shows this result.
            if (entry is not None and entry.sha256 == sha
                    and self.model_browser.model_id() == model_id
                    and self.model_browser.snapshot()["sha256"] == sha):
                self.model_browser.set_growth(self._growth_text(out_dir, model_id, job))
                self.model_browser.check_growth_btn.setEnabled(
                    entry.status in ("ok", "warning") and entry.integrity == "ok"
                    and proj.namespace_confirmed(entry) and not self._growth_running(entry)
                )
            self.refresh_workspace()

    def _growth_text(self, out_dir: Path, model_id: str, job: Job | None) -> str:
        """The browser's growth line for one Check Growth run (a failure never reads as growth)."""
        from cmig.gui.growth import failed_summary, medium_text, read_growth, run_clock

        def reading_text() -> str:
            record, _problem = proj.read_run_request(out_dir)
            values = (record or {}).get("values", {})
            medium = medium_text(str(values.get("medium") or ""),
                                 skip_unknown=values.get("skip_unknown") is True)
            entry = self.session.require().model(model_id)
            reading = read_growth(out_dir, objective_warning=proj.objective_warning_of(entry),
                                  medium=medium, finished=run_clock(out_dir.name))
            return f"{reading.symbol} {reading.text}"

        if job is not None and job.status is JobStatus.CANCELLED:
            return "⊘ Cancelled"
        state = proj.read_run_state(out_dir)
        failed = (job is not None and job.status is JobStatus.FAILED) or state == "failed"
        if failed and failed_summary(out_dir):
            return reading_text()  # a solve that failed (e.g. infeasible), told by its summary
        if job is not None and job.status is JobStatus.FAILED:
            message = str((parse_diagnostic(job.error) or {}).get("message") or "")
            lines = message.removeprefix("RuntimeError: ").strip().splitlines()
            reason = lines[-1] if lines else "the run failed"
            hint = (" — tick “Skip medium metabolites this model lacks” to run without them"
                    if "no counterpart" in reason else "")
            return f"✗ Failed: {reason}{hint}"
        if state is not None:
            return {"cancelled": "⊘ Cancelled"}.get(state, f"✗ Failed ({state}) — see the run")
        inspected = self._inspect_gui_run(out_dir)
        if inspected is None:
            return "✗ Failed: the result could not be read back — see the inspector"
        if inspected.get("artifact_integrity") == "mismatch":
            return "✗ Result changed since the run — see the inspector"
        return reading_text()

    def _show_latest_growth(self, entry: ModelEntry) -> None:
        """The browsed model's running or newest Check Growth, for exactly this model file."""
        from cmig.gui.growth import latest_check_growth

        if self._growth_running(entry):
            self.model_browser.check_growth_btn.setEnabled(False)
            self.model_browser.set_growth("Checking growth…")
            return
        project = self.session.require()
        run_dir = latest_check_growth(project.root, entry.id, entry.sha256)
        if run_dir is not None:
            self.model_browser.set_growth(self._growth_text(run_dir, entry.id, None))

    def _show_project_summary(self) -> None:
        project = self.session.project
        if project is None:
            self.inspector.clear()
        else:
            self.inspector.show_project_summary(project, self._display_runs(self.session.runs()))

    def _inspect_medium(self, key: str) -> None:
        from cmig.io.project import medium_path

        project = self.session.project
        kind, _, name = key.partition(":")
        rows: list[tuple[str, str]] = []
        try:
            if kind == "preset":
                path, title = installed_medium_preset_path(name), name
            elif project is not None:
                entry = project.medium(name)
                path, title = medium_path(project, entry), entry.id
            else:
                return
            if path.suffix.lower() == ".csv":
                with path.open(newline="") as handle:
                    for record in csv.reader(handle):
                        if len(record) >= 2 and record[0] and not record[0].startswith("#"):
                            rows.append((record[0], record[1]))
        except (OSError, UnicodeDecodeError, csv.Error, ValueError, ProjectError) as exc:
            self.statusBar().showMessage(f"Cannot read medium {name}: {exc}", 8000)
            return
        self.inspector.show_medium(title, rows[1:] if rows else rows, str(path))
        self._inspector_run, self._inspected_model = None, None

    def _open_run_entry(self, run_dir: Path) -> None:
        """Open a run on its analysis page: its recorded inputs first, then its result.

        A run of no page (or of no known kind) opens in its viewer as before. A run whose
        result cannot be shown leaves its page empty, with the reason in the page's status:
        never another run's result under this run's inputs.
        """
        from cmig.gui.run_restore import analysis_for_run, banner_text

        run_dir = Path(run_dir).resolve()
        key, record, problem = analysis_for_run(run_dir,
                                                in_project=self._in_project_runs(run_dir))
        if key == "check_growth" and self._open_check_growth_run(run_dir, record):
            return
        page = self.analysis_pages.get(key or "")
        if page is None:
            self._inspector_run = None
            self.load_run_dir(run_dir)
            if self._inspector_run != str(run_dir):  # e.g. a run kind without a viewer
                self._show_run_in_inspector(run_dir)
            return
        assert key is not None
        self.show_analysis(key, select=False)  # the opened run stays selected in RUNS
        notes = page.restore(record["values"]) if record is not None else []
        self._empty_run_result(key)  # inputs changed above; nothing older stays on show
        inputs_known = record is not None and not notes
        if not self._load_run_into_page(key, run_dir, inputs_known=inputs_known):
            self._empty_run_result(key, keep_status=True)
            status = self._run_status_label(key)
            if not status.text():  # the loader gave no reason of its own
                failure = self._readback_failures.get(_run_key(run_dir))
                state = (proj.read_run_state(run_dir) if self._in_project_runs(run_dir)
                         else None)
                if failure is not None:
                    reason = "; ".join(failure[1].splitlines()[1:]) or failure[0]
                elif state is not None:
                    reason = f"the run {state}"
                else:
                    reason = "it has no result this page can show"
                status.setText(f"No result shown for {run_dir.name}: {reason}")
        page.show_banner(banner_text(run_dir.name, record, problem, notes))
        self._show_run_in_inspector(run_dir)

    def _open_check_growth_run(self, run_dir: Path, record: dict[str, Any] | None) -> bool:
        """Show a Check Growth run in its model's browser header; False when that model file
        is no longer in the project (the run then opens like a run of no page)."""
        project = self.session.project
        values = {} if record is None else record["values"]
        model_id, sha = values.get("model"), values.get("sha256")
        entry = (None if project is None or not self._in_project_runs(run_dir)
                 else next((m for m in project.models if m.id == model_id), None))
        if entry is None or entry.sha256 != sha:
            return False
        self.sidebar.select("models", entry.id)  # shows the model, as a click on its row does
        if (self.model_browser.model_id() != entry.id
                or self.pages.currentWidget() is not self.model_browser):
            self._show_model(entry)
        self.model_browser.set_growth(self._growth_text(run_dir, entry.id, None))
        self._show_run_in_inspector(run_dir)
        return True

    def _run_status_label(self, key: str) -> QLabel:
        """The status line under `key`'s results (Sweep's frame has no results area)."""
        if key == "sweep":
            return self.sweep_view.status
        return self.analysis_pages[key].status

    def _empty_run_result(self, key: str, *, keep_status: bool = False) -> None:
        """Empty `key`'s shown result (and, unless `keep_status`, its status line)."""
        if key in ("search", "gene_ko", "strain_growth", "ratio_impact", "host_search"):
            self._clear_ranked(self._ranked_page(key))
            if key == "search":
                self.current_search_dir = None
        elif key in ("community", "medium"):
            self._empty_community_result_on(key)
            if key == "medium":
                editor = self.medium_editor
                for label in (editor.growth_label, editor.dropped_ids_label,
                              editor.profile_delta_label, editor.minimal_status):
                    label.clear()
                editor.minimal_table.setRowCount(0)
                self._medium_delta_active = False
        elif key == "host":
            self.host_view.clear_result()
            self.current_host_microbe_dir = None
        elif key in ("dfba", "spatial"):
            (self.dynamics_view if key == "dfba" else self.spatial_page)._clear_dynamics("")
        elif key == "sweep":
            self.sweep_view.load_results([])
        if not keep_status:
            self._run_status_label(key).clear()

    def _load_run_into_page(self, key: str, run_dir: Path, *, inputs_known: bool) -> bool:
        """Show a run's result on its page; inputs are restored first, so it is not stale.

        `inputs_known`: the run's recorded inputs are all back on screen, so they may label
        the result as its executed request.
        """
        if key == "search":
            return self.load_search_dir(run_dir)
        if key in ("gene_ko", "strain_growth", "ratio_impact", "host_search"):
            return self.load_ranked_dir(key, run_dir, inputs_known=inputs_known)
        if key in ("community", "medium") and (run_dir / "nodes.parquet").exists():
            return self.load_run_dir(run_dir, host_key=key)
        if key == "medium" and (run_dir / "minimal_medium_summary.json").exists():
            return self._load_minimal_medium_dir(run_dir)
        if key == "host":
            return self.load_host_microbe_bigg_dir(run_dir)
        if key == "dfba":
            return self.load_dfba_dir(run_dir)
        if key == "spatial":
            return self.load_spatial_dir(run_dir)
        if key == "sweep" and (run_dir / "sweep.parquet").exists():
            return self._load_sweep_dir(run_dir)
        return False

    def load_ranked_dir(self, key: str, run_dir: Path, *, inputs_known: bool = False) -> bool:
        """Show a Gene KO / Strain Growth / Ratio Impact / Host Search run on its page.

        Only with `inputs_known` (the run's record restored in full) are the inputs on screen
        shown as the run's executed request.
        """
        summary_name, _adapter, kind, _label = self._ranked_spec(key)
        page = self._ranked_page(key)
        if self._inspect_gui_run(run_dir) is None:
            self._clear_ranked(page)
            page.status.setText(f"Readback invalid/unreadable: {run_dir}")
            return False
        try:
            payload = json.loads((run_dir / summary_name).read_text())
            if not isinstance(payload, dict):
                raise ValueError(f"{summary_name} is not a JSON object")
            requested = page.request_fields(kind) if inputs_known else None
            self._show_ranked(key, payload, run_dir, requested)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self._reject_gui_summary(run_dir, exc)
            self._clear_ranked(page)
            page.status.setText(f"Readback invalid/unreadable: {exc}")
            return False
        if not inputs_known:
            status = page.status
            status.setText(
                f"Inputs for {run_dir.name} are not known — labels show only what the run "
                f"recorded. {status.text()}"
            )
        self._register_run_output(run_dir)
        return True

    def _load_sweep_dir(self, run_dir: Path) -> bool:
        """Show a sweep run's rows, with the run's own status: a failed or cancelled job's
        rows are labelled partial, never shown as a complete sweep."""
        view = self.sweep_view
        if self._inspect_gui_run(run_dir) is None:
            view.load_results([])
            view.status.setText(f"Readback invalid/unreadable: {run_dir}")
            return False
        summary_path = run_dir / "sweep_summary.json"
        try:
            rows = _load_sweep_rows(run_dir / "sweep.parquet")
            summary = json.loads(summary_path.read_text()) if summary_path.exists() else None
            if summary is not None and not isinstance(summary, dict):
                raise ValueError("sweep_summary.json is not a JSON object")
        except Exception as exc:  # pyarrow raises its own error types for a damaged file
            self._reject_gui_summary(run_dir, exc)
            view.load_results([])
            view.status.setText(f"Readback invalid/unreadable: {exc}")
            return False
        view.load_results(rows)
        job_state = proj.read_run_state(run_dir) if self._in_project_runs(run_dir) else None
        if job_state in ("failed", "cancelled"):
            text = (f"Sweep {run_dir.name} {job_state}: showing {len(rows)} condition(s) it "
                    "recorded before it stopped — partial, not a complete sweep.")
        elif summary is None:
            text = (f"Sweep {run_dir.name}: no sweep_summary.json — showing {len(rows)} "
                    "recorded condition(s); the sweep may be partial.")
        else:
            warnings = summary.get("warnings") or []
            text = (f"Sweep {run_dir.name}: status {summary.get('status', 'unknown')} · "
                    f"{len(rows)} condition(s)")
            if isinstance(warnings, list) and warnings:
                text += " · " + "; ".join(str(warning) for warning in warnings)
        view.status.setText(text)
        self._register_run_output(run_dir)
        self._show_page(self.sweep_page)
        return True

    def _load_minimal_medium_dir(self, run_dir: Path) -> bool:
        if self._inspect_gui_run(run_dir) is None:
            return False
        try:
            payload = json.loads((run_dir / "minimal_medium_summary.json").read_text())
            if not isinstance(payload, dict):
                raise ValueError("minimal_medium_summary.json is not a JSON object")
            self.medium_editor.load_minimal_result(payload)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self._reject_gui_summary(run_dir, exc)
            self.medium_editor.minimal_table.setRowCount(0)
            self.medium_editor.minimal_status.setText(f"Readback invalid/unreadable: {exc}")
            return False
        self._show_page(self.medium_page)
        return True

    def _show_sidebar_menu(self, group: str, keys: list[str]) -> None:
        if group != "models" or not keys:
            return
        menu = QMenu(self)
        search = menu.addAction("Search with Selected…")
        search.triggered.connect(lambda: self._search_with_models(keys))
        menu.addSeparator()
        menu.addAction(self.rename_action)
        menu.addAction(self.remove_action)
        menu.addSeparator()
        reveal = menu.addAction("Show in Finder")
        reveal.triggered.connect(self.inspector._reveal)
        menu.exec(QCursor.pos())

    def _search_with_models(self, keys: list[str]) -> None:
        """Select these models in Search (sidebar "Search with Selected…"), then show it."""
        picker = self.search_view.model_picker
        picker.set_selected(keys)
        self.show_analysis("search")
        left_out = [key for key in keys if key not in picker.selected_ids()]
        if left_out:
            self.statusBar().showMessage(
                f"Not runnable, left out of Search: {', '.join(left_out)}", 8000
            )

    def _remove_selected_models(self) -> None:
        try:
            self.session.remove_models(self.sidebar.selected_keys("models"))
        except ProjectError as exc:
            self.statusBar().showMessage(str(exc), 8000)

    def _rename_selected_model(self) -> None:
        keys = self.sidebar.selected_keys("models")
        if len(keys) != 1:
            return
        new_id, ok = QInputDialog.getText(self, "Rename Model", "New model id:", text=keys[0])
        if ok and new_id and new_id != keys[0]:
            try:
                self.session.rename_model(keys[0], new_id.strip())
            except ProjectError as exc:
                self.statusBar().showMessage(str(exc), 8000)

    def _cancel_job_id(self, job_id: str) -> None:
        job = self.runner.poll(job_id)
        if job.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
            self._show_status("status_job_already", status=job.status.value, job_id=job_id)
            return
        if job_id in self._search_jobs:
            self.cancel_search()
            return
        self.runner.cancel(job_id)
        self.bridge.cancelling.add(job_id)
        if job_id in self._import_jobs:
            # An import is file copying, not a solver call: the solver wording would be wrong.
            self.bridge.status_labels[job_id] = "cancelling (finishing the current file)"
            self.bridge.refresh()
            self.statusBar().showMessage(
                "Cancelling import — the file being copied will finish first.", 8000
            )
            return
        if job_id in self._agora2_jobs:
            # The download is one in-process CLI call with no cancel checks inside it.
            self.bridge.status_labels[job_id] = "cancelling (download cannot be interrupted)"
            self.bridge.refresh()
            self.statusBar().showMessage(
                "Cancelling the AGORA2 download — it cannot be interrupted; it will finish and "
                "its files will not be added to the project.", 8000,
            )
            return
        self.bridge.refresh()
        # Cancellation is cooperative and GUI jobs only check it at run boundaries, so saying
        # just "Cancel requested" let the user believe the solve had stopped when it had not.
        self._show_status("status_cancel_requested", job_id=job_id)

    def _show_selected_job_detail(self) -> None:
        job_id = self.jobs_panel.selected_job_id()
        if not job_id:
            return
        job = self.runner.poll(job_id)
        log = job.error or ""
        if isinstance(job.result, dict):
            log = str(job.result.get("cli_error") or job.result.get("input_diagnostic") or log)
        self.activity.set_job_detail(self._job_logs.get(job_id) or log,
                                     self._job_commands.get(job_id, ""))

    def _refresh_solver_label(self) -> None:
        try:
            import gurobipy  # noqa: F401

            self.solver_label.setText("Solver: Gurobi (full-flux)")
        except ImportError:
            self.solver_label.setText("Solver: Gurobi not available")

    # ── drag & drop on the whole window ─────────────────────────────────────────────────
    def dragEnterEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        files, _ = droppable_paths(list(event.mimeData().urls()))
        if files and self.session.project is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        local = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if local and self.session.project is not None:
            self.add_model_paths(local)
            event.acceptProposedAction()

    def _import_gate_busy(self) -> str:
        """Why no model import or AGORA2 download may start now, or "" when one may.

        Two writers into `models/` at once would race for the same file names, so an import
        and a download take turns.
        """
        if self._import_jobs:
            return "A model import is already running; wait for it or cancel it in Activity."
        if self._agora2_jobs:
            return "An AGORA2 download is already running; wait for it or cancel it in Activity."
        return ""

    def add_model_paths(
        self,
        paths: list[Path],
        *,
        recursive: bool = True,
        source_overrides: dict[Path, str] | None = None,
    ) -> str:
        """Copy model files, and the models under folders, into the project in the background.

        Returns the import job's id, or "" when nothing was started (the status bar says why).
        The worker only copies and checks files against a private snapshot of the project; the
        entries it produces are added through the session on the GUI thread when it is done.
        `source_overrides` maps a file to the origin to record as its `source_path` instead of
        its local path (an AGORA2 download records the URL it came from).
        """
        from cmig.service import JobContext

        project = self.session.project
        if project is None:
            self.statusBar().showMessage("Open or create a project before adding models.", 8000)
            return ""
        busy = self._import_gate_busy()
        if busy:
            self.statusBar().showMessage(busy, 8000)
            return ""
        # Only names are checked here: listing a folder or parsing a JSON model can take
        # seconds, so the job searches the folders and skips what is not a model.
        given, skipped_here = proj.model_import_candidates([Path(p) for p in paths])
        if not given:
            self.statusBar().showMessage(
                f"No SBML, JSON or MAT model files found ({skipped_here} skipped).", 8000
            )
            return ""
        working = proj.Project(project.root, project.name, project.created,
                               list(project.models), list(project.media),
                               dict(project.analysis_settings))
        origins = {Path(path): origin for path, origin in (source_overrides or {}).items()}
        found_box: list[list[Path]] = []

        def _job(ctx: JobContext) -> dict[str, Any]:
            from cmig.service.jobrunner import ArtifactJobFailure

            try:
                files, skipped = proj.supported_model_paths(given, recursive=recursive)
            except ProjectError as exc:  # e.g. a folder that cannot be read
                raise ArtifactJobFailure(str(exc), {"scan_error": str(exc)}) from exc
            skipped += skipped_here
            found_box.append(files)  # the GUI swaps its placeholder rows for these names
            added: list[ModelEntry] = []
            failed: list[tuple[str, str]] = []
            duplicates: list[tuple[str, str]] = []
            total = len(files)
            for index, path in enumerate(files):
                if ctx.cancelled:
                    return {"added": added, "failed": failed, "duplicates": duplicates,
                            "skipped": skipped, "cancelled_remaining": total - index,
                            "total": total}
                ctx.report_progress(index, total)
                try:
                    entry = proj.add_model_file(working, path, check=proj.check_model_file)
                    if path in origins:
                        entry.source_path = origins[path]
                    added.append(entry)
                except proj.DuplicateModelError as exc:
                    duplicates.append((path.name, exc.existing_id))
                except proj.ProjectError as exc:
                    failed.append((path.name, str(exc)))
                except Exception as exc:  # one odd file must not lose the models already copied
                    failed.append((path.name, f"{type(exc).__name__}: {exc}"))
            ctx.report_progress(total, total)
            return {"added": added, "failed": failed, "duplicates": duplicates,
                    "skipped": skipped, "cancelled_remaining": 0, "total": total}

        job_id = self.submit_job("import_models", _job)
        self._import_jobs[job_id] = given
        self._import_found[job_id] = found_box
        self._import_roots[job_id] = project.root
        self._pending_imports.extend(path.name for path in given)
        self._job_commands[job_id] = (
            f"Add models from {len(given)} file(s) or folder(s) to {project.name}"
        )
        self.refresh_workspace()
        return job_id

    def _take_import_scan(self, job_id: str) -> bool:
        """Once the job has searched its folders, show one placeholder row per model file.

        Only in the project the job imports into: after a switch, its rows are not shown.
        """
        box = self._import_found.get(job_id)
        if not box:
            return False
        files = box.pop()
        self._job_commands[job_id] = f"Add {len(files)} model file(s)"
        project, root = self.session.project, self._import_roots.get(job_id)
        if project is None or root is None or not _same_folder(project.root, root):
            return False
        self._pending_imports = [path.name for path in files]
        self._job_commands[job_id] += f" to {project.name}"
        return True

    def _finish_import(
        self, job_id: str, result: dict[str, Any] | None, status: str, reason: str = ""
    ) -> None:
        """Add what an import job produced to the project it was started for."""
        self._take_import_scan(job_id)
        self._import_jobs.pop(job_id, None)
        self._import_found.pop(job_id, None)
        root = self._import_roots.pop(job_id, None)
        self.bridge.cancelling.discard(job_id)
        self._pending_imports = []  # imports run one at a time: every placeholder was this job's
        remaining = 0 if result is None else int(result["cancelled_remaining"])
        total = 0 if result is None else int(result["total"])
        if remaining:
            # The worker returns normally after a cancel, so the runner calls the job `done`.
            self.bridge.status_labels[job_id] = (
                f"cancelled ({remaining} of {total} not imported)"
            )
            self._job_logs[job_id] = f"Cancelled: {remaining} of {total} files not imported"
        else:
            self.bridge.status_labels.pop(job_id, None)
        project = self.session.project
        if result is None:
            detail = f": {reason}" if reason else ""
            self.statusBar().showMessage(
                f"Model import {status}; nothing was added{detail}", 15000
            )
            if reason:
                self._job_logs[job_id] = reason
        elif not total:
            self.statusBar().showMessage(
                f"No SBML, JSON or MAT model files found ({result['skipped']} skipped).", 8000
            )
        elif project is None or root is None or not _same_folder(project.root, root):
            self.statusBar().showMessage(
                f"The project was closed during the import; {len(result['added'])} copied "
                "model(s) were not added.", 15000,
            )
        else:
            self._add_imported(job_id, project, result)
        if job_id in self._job_logs:
            self._show_job_in_activity(job_id)
        self.runner.release_payload(job_id)
        self.refresh_workspace()
        self._ensure_indexes()

    def _add_imported(self, job_id: str, project: proj.Project, result: dict[str, Any]) -> None:
        # The project may have changed (a rename, an undo) since the worker took its snapshot.
        # An id taken meanwhile would make the project file unreadable, so that model is
        # reported instead of added; its copy stays in models/.
        taken = {m.id for m in project.models}
        added: list[ModelEntry] = []
        failed: list[tuple[str, str]] = list(result["failed"])
        for entry in result["added"]:
            if entry.id in taken:
                reason = f"id {entry.id!r} was taken during the import"
                failed.append((Path(entry.file).name, reason))
            else:
                taken.add(entry.id)
                added.append(entry)
        details = [f"{name}: {reason}" for name, reason in failed]
        details += [f"{name}: already in the project as {eid}"
                    for name, eid in result["duplicates"]]
        if details:
            earlier = self._job_logs.get(job_id)  # the "Cancelled: ..." line, if any
            self._job_logs[job_id] = "\n".join(([earlier] if earlier else []) + details)
        try:
            self.session.add_entries(added)
        except ProjectError as exc:
            self.statusBar().showMessage(
                f"Could not save the project, so {len(added)} imported model(s) were not added: "
                f"{exc}", 15000,
            )
            return
        n_failed = sum(1 for e in added if e.status == "failed") + len(failed)
        duplicates = len(result["duplicates"])
        parts = [f"{len(added)} added"]
        if duplicates:
            parts.append(f"{duplicates} duplicate" + ("" if duplicates == 1 else "s"))
        if n_failed:
            parts.append(f"{n_failed} failed")
        if result["skipped"]:
            parts.append(f"{result['skipped']} skipped")
        if result["cancelled_remaining"]:
            parts.append(f"cancelled with {result['cancelled_remaining']} not imported")
        self.statusBar().showMessage("Models: " + ", ".join(parts), 15000)

    def _show_job_in_activity(self, job_id: str) -> None:
        """Select the job's row in Activity so its log and command are on show."""
        self.bridge.refresh()
        for row in range(self.jobs_panel.rowCount()):
            item = self.jobs_panel.item(row, 0)
            if item is not None and item.text() == job_id:
                self.jobs_panel.selectRow(row)
                break
        self._show_selected_job_detail()

    def _add_models_dialog(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Models", "", "Models (*.xml *.sbml *.xml.gz *.sbml.gz *.json *.mat)"
        )
        if paths:
            self.add_model_paths([Path(p) for p in paths])

    def _add_models_folder_dialog(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Add Models from Folder")
        if path:
            include = QMessageBox.question(
                self, "Add Models from Folder", "Include subfolders?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes
            self.add_model_paths([Path(path)], recursive=include)

    def _add_medium_dialog(self) -> None:
        project = self.session.project
        if project is None:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Add Medium", "", "Media (*.csv *.json)")
        errors: list[str] = []
        for path in paths:
            try:
                self.session.add_medium(proj.add_medium_file(project, Path(path)))
            except ProjectError as exc:
                errors.append(f"{Path(path).name}: {exc}")
        if errors:
            self.statusBar().showMessage("; ".join(errors), 15000)

    def _agora2_dialog(self) -> None:
        if self.session.project is None:
            return
        busy = self._import_gate_busy()
        if busy:  # the pick would be refused at the end, after the user had made it
            self.statusBar().showMessage(busy, 8000)
            return
        dialog = Agora2Dialog(self._agora2_list)
        if not dialog.exec() or not dialog.selected_strains():
            return
        if not self._confirm_agora2_download(dialog.selected_entries()):
            self.statusBar().showMessage("AGORA2 download not started.", 8000)
            return
        self._agora2_fetch(dialog.selected_strains())

    def _confirm_agora2_download(self, strains: list[Agora2Strain]) -> bool:
        """Ask before a download of more than 1 GB, or of a size the catalogue does not give.

        `_agora2_fetch` passes `--yes` to the CLI, so this question is the confirmation the CLI
        asks for from 8 GB up; it defaults to No.
        """
        from cmig.cli.main import AGORA2_LARGE_FETCH_BYTES

        known, unknown = download_estimate(strains)
        if not unknown and known <= CONFIRM_BYTES:
            return True
        if unknown:
            text = (f"{unknown} of the {len(strains)} selected strains have no published size, "
                    "so the download cannot be estimated"
                    + (f" (at least {human_bytes(known)} for the others)." if known else "."))
        else:
            text = (f"{len(strains)} strains, about {human_bytes(known)}, will be downloaded "
                    "from vmh.life.")
        if known >= AGORA2_LARGE_FETCH_BYTES:
            text += (f" That is a very large download "
                     f"({human_bytes(AGORA2_LARGE_FETCH_BYTES)} or more).")
        answer = QMessageBox.question(
            self, "Download from AGORA2", text + "\n\nDownload them into the project?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return bool(answer == QMessageBox.StandardButton.Yes)

    def _agora2_list(self, query: str) -> list[Agora2Strain]:
        """Strains matching `query`, from `cmig agora2-list` run in this process.

        Runs the CLI on a worker thread; only that thread's stdout is captured. The catalogue
        cache is the project's, never the package data folder. A first lookup downloads the
        index.
        """
        import cmig.cli.main as cli_main

        project = self.session.require()
        argv = ["agora2-list", "--format", "json", "--limit", str(SEARCH_LIMIT),
                "--catalogue", str(project.models_dir / "agora2" / CATALOGUE_FILENAME)]
        # An id match, not a genus match: ids read Genus_species_strain, so a partial genus
        # ("Roseb") and "Genus species" both work. The CLI matches case-insensitively.
        words = query.split()
        if not words:
            raise ValueError("Enter part of a genus or strain name.")
        argv += ["--match", re.escape("_".join(words))]
        _install_stderr_router()
        # The router is only needed for this lookup; leave sys.stdout as it was found.
        original_stdout = sys.stdout
        _install_stdout_router()
        router = sys.stdout

        def _call() -> tuple[int, str, str]:
            with _captured_thread_stdout() as out, _captured_job_stderr() as err:
                try:
                    rc = cli_main.main(argv)
                except SystemExit as exc:  # argparse rejected the query
                    rc = exc.code if isinstance(exc.code, int) else 2
            return rc, "".join(out), "".join(err)

        try:
            rc, printed, errors = self._run_off_thread(_call)
        finally:
            if sys.stdout is router:
                sys.stdout = original_stdout
        if rc != 0:
            lines = errors.strip().splitlines()
            raise RuntimeError(lines[-1].strip() if lines else f"agora2-list exited {rc}")
        return _parse_catalogue(printed)

    def _agora2_fetch(self, strains: list[str]) -> str:
        """Download `strains` into a new batch folder of `models/agora2/`, then add them.

        Returns the job id, or "" when nothing was started (the status bar says why). Each call
        gets its own `models/agora2/<YYYYMMDD-HHMMSS>[-N]/` folder, because `agora2-fetch`
        rewrites the manifest beside its output on every call: one folder per call keeps every
        download's provenance. The download holds the import gate; `_finish_agora2` passes the
        files the batch manifest records on to `add_model_paths` in the same GUI-thread step
        that releases it. Callers confirm a large download first (`_confirm_agora2_download`).
        """
        from cmig.cli.main import main
        from cmig.service import JobContext
        from cmig.service.jobrunner import ArtifactJobFailure

        project = self.session.project
        if project is None:
            self.statusBar().showMessage("Open or create a project before adding models.", 8000)
            return ""
        busy = self._import_gate_busy()
        if busy:
            self.statusBar().showMessage(busy, 8000)
            return ""
        if not strains:
            self.statusBar().showMessage("Choose at least one AGORA2 strain.", 8000)
            return ""
        parent = project.models_dir / "agora2"
        try:
            batch_dir = _claim_agora2_batch_dir(parent)
        except OSError as exc:
            self.statusBar().showMessage(f"Cannot create a download folder in {parent}: {exc}",
                                         15000)
            return ""
        argv = ["agora2-fetch", "--strain", ",".join(strains), "--out", str(batch_dir),
                "--catalogue", str(parent / CATALOGUE_FILENAME), "--format", "json", "--yes"]
        _install_stderr_router()

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            error = ""
            rc = 0
            with _captured_job_stderr() as stderr_chunks:
                try:
                    rc = main(argv)
                except SystemExit as exc:
                    rc = exc.code if isinstance(exc.code, int) else 2
                except Exception as exc:  # reported as this job's failure, not raised into Qt
                    rc, error = 1, f"{type(exc).__name__}: {exc}"
            # A cancel during the call cannot stop it; it discards the result instead.
            ctx.raise_if_cancelled()
            stderr = "".join(stderr_chunks).strip()
            # Exit 1 is a partial fetch: the strains the manifest records are real, the rest are
            # named on stderr. Anything else says nothing trustworthy about the files on disk.
            sources = {} if error or rc not in (0, 1) else _manifest_downloads(batch_dir, strains)
            if rc == 0 and len(sources) == len(set(strains)):
                ctx.report_progress(1, 1)
                return {"files": list(sources), "sources": sources}
            if not error:
                if rc != 0:
                    error = f"agora2-fetch exited {rc}"
                    if stderr:
                        error += f": {stderr.splitlines()[-1].strip()}"
                elif sources:
                    error = (f"agora2-fetch finished but its manifest records only {len(sources)} "
                             f"of {len(set(strains))} strains in {batch_dir}")
                else:
                    error = f"agora2-fetch finished but recorded no model file in {batch_dir}"
            message = "\n".join(part for part in (error, stderr) if part)
            raise ArtifactJobFailure(message, {
                "files": list(sources), "sources": sources, "message": message,
                "headline": error,
            })

        job_id = self.submit_job("agora2_fetch", _job)
        self._agora2_jobs[job_id] = (project.root, batch_dir)
        self._job_commands[job_id] = command_line(argv)
        self.statusBar().showMessage(
            f"Downloading {len(strains)} AGORA2 strain(s) into {batch_dir}…", 8000
        )
        return job_id

    def _finish_agora2(self, job_id: str, job: Job) -> None:
        """Register a finished download's files, or say why there are none."""
        root, out_dir = self._agora2_jobs.pop(job_id)  # the gate opens; nothing yields below
        self.bridge.cancelling.discard(job_id)
        self.bridge.status_labels.pop(job_id, None)
        result = job.result if isinstance(job.result, dict) else {}
        files = [Path(f) for f in result.get("files", []) if Path(f).is_file()]
        origins = {Path(f): url for f, url in (result.get("sources") or {}).items() if url}
        project = self.session.project
        problem = ""
        if job.status is JobStatus.CANCELLED:
            files, problem = [], "AGORA2 download cancelled; nothing was added to the project"
            self._job_logs[job_id] = (
                f"Cancelled; nothing was added. Anything already downloaded is in {out_dir}"
            )
        elif job.status is JobStatus.FAILED:
            reason = str(result.get("message") or (parse_diagnostic(job.error) or {}).get(
                "message") or "unknown error")
            self._job_logs[job_id] = reason
            headline = str(result.get("headline") or reason.splitlines()[0])
            problem = f"AGORA2 download failed: {headline}"
        if files and (project is None or not _same_folder(project.root, root)):
            problem = (f"The project was closed during the AGORA2 download; {len(files)} "
                       f"downloaded file(s) were not added (they are in {out_dir})")
            files = []
        if files:
            # Takes the gate on the spot: _agora2_jobs is empty now and nothing yields before it.
            self.add_model_paths(files, source_overrides=origins)
        else:
            with suppress(OSError):
                out_dir.rmdir()  # a download that left nothing leaves no folder (empty only)
        if problem:
            self.statusBar().showMessage(problem, 15000)
            self._show_job_in_activity(job_id)

    def _connect_view_actions(self) -> None:
        self.sandbox_view.preview_btn.clicked.connect(self._run_sandbox_preview)
        self.sandbox_view.commit_btn.clicked.connect(self._run_sandbox_commit)
        self.sandbox_view.auto_preview_requested.connect(self._run_sandbox_auto_preview)
        self.search_view.browse_checkpoint_btn.clicked.connect(self._browse_search_checkpoint)
        self.search_view.run_btn.clicked.connect(self.run_search_fixture)
        self.search_view.cancel_btn.clicked.connect(self.cancel_search)
        self.gene_ko_page.run_btn.clicked.connect(self.run_gene_ko_search)
        self.strain_growth_page.run_btn.clicked.connect(self.run_strain_growth_report)
        self.ratio_impact_page.run_btn.clicked.connect(self.run_abundance_impact)
        for page in (self.search_view, self.gene_ko_page, self.strain_growth_page,
                     self.ratio_impact_page):
            page.results_panel.export_figure_btn.clicked.connect(
                lambda _c=False, p=page: self._export_ranked_figure(p)
            )
        self.host_view.run_btn.clicked.connect(self.run_host_microbe_bigg)
        self.host_view.export_figure_btn.clicked.connect(self._export_host_figure)
        self.host_search_page.run_btn.clicked.connect(self.run_host_search_bigg)
        self.host_search_page.results_panel.export_figure_btn.clicked.connect(
            lambda _c=False: self._export_ranked_figure(self.host_search_page)
        )
        self.dynamics_view.run_dfba_btn.clicked.connect(self.run_dfba)
        self.spatial_page.run_btn.clicked.connect(self.run_spatial_preview)
        self.community_builder.run_btn.clicked.connect(self.run_community_solve)
        self.sweep_view.browse_mediums_btn.clicked.connect(self._browse_sweep_mediums)
        self.sweep_view.browse_abundance_btn.clicked.connect(self._browse_sweep_abundances)
        self.sweep_view.browse_bounds_btn.clicked.connect(self._browse_sweep_bounds)
        self.sweep_view.browse_namespace_btn.clicked.connect(self._browse_sweep_namespace)
        self.sweep_view.run_btn.clicked.connect(self.run_sweep_from_view)
        self.medium_editor.browse_namespace_btn.clicked.connect(self._browse_medium_namespace)
        self.medium_editor.check_growth_btn.clicked.connect(self.run_medium_growth_check)
        self.medium_editor.minimal_medium_btn.clicked.connect(self.run_minimal_medium)
        self.medium_editor.medium_changed.connect(self._medium_context_changed)
        self.medium_editor.model_picker.selection_changed.connect(self._medium_context_changed)
        self.medium_editor.namespace_decisions_input.textChanged.connect(
            self._medium_context_changed
        )
        self.medium_editor.assume_bigg_check.toggled.connect(self._medium_context_changed)
        self.scenario_compare.browse_a_btn.clicked.connect(self._browse_scenario_run_a)
        self.scenario_compare.browse_b_btn.clicked.connect(self._browse_scenario_run_b)
        self.scenario_compare.compare_btn.clicked.connect(self.run_scenario_compare)
        for key, picker in self._model_pickers().items():
            picker.selection_changed.connect(lambda k=key, p=picker: self._remember(k, p))
        self.host_view.host_picker.selection_changed.connect(
            lambda p=self.host_view: self._host_model_changed(p)
        )
        self.host_search_page.host_picker.selection_changed.connect(
            lambda p=self.host_search_page: self._host_model_changed(p)
        )
        for (key, field), medium_picker in self._medium_pickers().items():
            medium_picker.currentIndexChanged.connect(
                lambda _index, k=key, f=field, p=medium_picker: self._remember_medium(k, f, p)
            )

    def _cancel_selected_job(self) -> None:
        job_id = self.jobs_panel.selected_job_id()
        if not job_id:
            self._show_status("status_select_job")
            return
        self._cancel_job_id(job_id)

    def _browse_search_checkpoint(self) -> None:
        # A save dialog: the path may be new (fresh run) or existing (Resume), so the
        # overwrite prompt is off; the run-time pre-check refuses an existing file without
        # Resume instead.
        path, _ = QFileDialog.getSaveFileName(
            self, "Select Checkpoint JSON", "", "Checkpoint (*.json)",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if path:
            self.search_view.checkpoint_input.setText(path)

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

    def _browse_medium_namespace(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr_map["medium_dialog_namespace"],
            "",
            self.tr_map["sweep_filter_json"],
        )
        if path:
            self.medium_editor.namespace_decisions_input.setText(path)

    def _medium_context_changed(self, *_args: Any) -> None:
        """Clear only a medium-owned overlay when its displayed request becomes stale."""
        if not self._medium_delta_active:
            return
        self.profile_view.clear_delta_overlay()
        self._medium_delta_active = False
        self.medium_editor.profile_delta_label.setText(
            self.tr_map["medium_profile_delta_cleared"]
        )

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

    def _export_ranked_figure(self, page: RankedPage) -> None:
        # Same rule as the Host tab: export the run the table is displaying, and nothing else.
        # There is deliberately NO fallback to `current_search_dir`: invalidation clears
        # `current_run_dir` and tells the user the result was discarded, and a fallback would
        # then still export that discarded run and report success (verifier V-1).
        panel = page.results_panel
        run_dir = panel.current_run_dir
        if run_dir is None:
            page.status.setText("No search result is loaded.")
            return
        artifact = panel.selected_figure_artifact()
        src = run_dir / artifact
        if not src.exists():
            panel.refresh_figure_mode()
            page.status.setText(f"Search figure artifact not found: {artifact}")
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
        page.status.setText(f"Exported figure: {target}")

    def _open_run_dialog(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open CMIG Run")
        if path:
            self._open_run_entry(Path(path))

    def _run_fixture_dialog(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if path:
            self.run_fixture(path)

    def _run_sandbox_preview(self) -> None:
        self._run_sandbox(commit=False)

    def _run_sandbox_commit(self) -> None:
        self._run_sandbox(commit=True)

    def _run_sandbox_auto_preview(self) -> None:
        """The debounced preview after a bound edit; its result stays on the sandbox page.

        Nothing starts while a sandbox solve is in flight: another edit would otherwise queue a
        second solve whose result lands on the wrong bound. The preview is re-armed instead.
        """
        if self._sandbox_jobs or not self.sandbox_view.preview_btn.isEnabled():
            if self._sandbox_jobs:
                # Not dropped, only postponed: once the solve ends the preview follows the
                # latest bound, still one job at a time.
                self.sandbox_view._debounce.start()
            return
        self._run_sandbox(commit=False, auto=True)

    def _run_sandbox(self, *, commit: bool, auto: bool = False) -> str:
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
        self._sandbox_jobs[jid] = (commit, c, auto)
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
        """facade 작업을 JobRunner 로 제출 + bridge 추적(실 소비). Opens the Activity pane."""
        jid = self.runner.submit(kind, fn)
        self.bridge.track(jid)
        self.activity.expand()
        self.toggle_activity_action.setText("Hide Activity")
        return jid

    def load_run_dir(self, path: str | Path, host_key: str = "community") -> bool:
        """Show a run in its viewer; a tidy community run goes to Profile and Graph.

        Returns True only when the run is now on screen. A failed readback (reported in the
        status bar and the inspector) and a kind without a viewer give False.
        """
        from cmig.core.tidy import TidyBundle
        from cmig.gui.graph_data import graph_payload

        run_dir = Path(path).resolve()
        if (run_dir / "dfba_summary.json").exists():
            return self.load_dfba_dir(run_dir)
        if (run_dir / "spatial_summary.json").exists():
            return self.load_spatial_dir(run_dir)
        if (run_dir / "host_microbe_bigg_summary.json").exists():
            return self.load_host_microbe_bigg_dir(run_dir)
        if (run_dir / "search_summary.json").exists():
            return self.load_search_dir(run_dir)
        manifest_path = run_dir / "manifest.json"
        if manifest_path.exists() and not (run_dir / "nodes.parquet").exists():
            # A *complete* run of a kind with no viewer here (search / sweep / strain-growth /
            # gene-KO / minimal-medium are registered in the Project Explorer without a tidy
            # bundle). Falling through to TidyBundle.read raised, and the failure branch below
            # then cleared the run that *was* on screen — double-clicking a Search entry wiped
            # the community run. A directory without a manifest is still a failed load.
            kind = "unknown"
            inspected = self._inspect_gui_run(run_dir)
            if inspected is None:
                return False
            kind = str(inspected.get("kind") or kind)
            legacy_manifest = json.loads(manifest_path.read_text())
            # inspect-run reads any manifest that names no workflow_kind as a community solve;
            # only one outside workflow scope really is one (and then needs its tidy bundle).
            if kind == "unknown" or (
                kind == "community_solve" and legacy_manifest.get("manifest_scope") == "workflow"
            ):
                kind = str(legacy_manifest.get("kind") or "unknown")
            if kind in ("tidy", "community", "solve", "fixture", "community_solve"):
                self._reject_gui_summary(run_dir, "missing essential nodes.parquet")
                self._clear_community_result()
                self._show_status("status_run_load_failed", error="missing essential nodes.parquet")
                return False
            self._show_status("status_run_no_viewer", kind=kind, run_dir=run_dir)
            return False
        inspected = self._inspect_gui_run(run_dir)
        if inspected is None:
            self._clear_community_result()
            return False
        try:
            bundle = TidyBundle.read(run_dir)
            manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
            payload = graph_payload(bundle)
        except Exception as e:
            self._reject_gui_summary(run_dir, e)
            # A failed load must not leave the *previous* run's provenance on screen: the
            # run_hash in the status bar and the profile table would still describe run A.
            self._clear_community_result()
            self._show_status("status_run_load_failed", error=e)
            return False
        self.current_manifest = manifest
        self.current_graph_payload = payload
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
        self.profile_view.load_targets(_read_target_summary(run_dir))
        self._register_run_output(run_dir)
        self._show_profile(host_key)
        run_hash = None if self.current_manifest is None else self.current_manifest.get("run_hash")
        suffix = "" if run_hash is None else f" (run_hash {str(run_hash)[:12]})"
        self._show_status("status_loaded_run", run_dir=run_dir, suffix=suffix)
        return True

    def load_search_dir(self, path: str | Path) -> bool:
        run_dir = Path(path).resolve()
        summary_path = run_dir / "search_summary.json"
        inspected = self._inspect_gui_run(run_dir)
        if inspected is None:
            self.search_view.invalidate_results()
            self.search_view.status.setText(f"Readback invalid/unreadable: {run_dir}")
            self.current_search_dir = None
            return False
        try:
            summary = json.loads(summary_path.read_text())
            if not isinstance(summary, dict):
                raise ValueError("search_summary.json is not a JSON object")
            validate_search_summary(summary)
        except (OSError, ValueError, TypeError) as exc:
            self._reject_gui_summary(run_dir, exc)
            self.search_view.invalidate_results()
            self.search_view.status.setText(f"Readback invalid/unreadable: {exc}")
            self.current_search_dir = None
            self._show_status("status_run_load_failed", error=exc)
            return False
        try:
            self.search_view.load_summary(summary, run_dir=run_dir)
        except (TypeError, ValueError, KeyError) as exc:
            self._reject_gui_summary(run_dir, exc)
            self.search_view.invalidate_results()
            self.search_view.status.setText(f"Readback invalid/unreadable: {exc}")
            self.current_search_dir = None
            self._show_status("status_run_load_failed", error=exc)
            return False
        self.current_search_dir = run_dir
        self._register_run_output(run_dir)
        self._show_page(self.search_view)
        self.search_view.status.setText(
            f"{summary.get('status', 'unknown')} Search run: {run_dir} · "
            f"integrity {inspected['artifact_integrity']}; see details"
        )
        return True

    def load_host_microbe_bigg_dir(self, path: str | Path) -> bool:
        """Load `cmig host-microbe-bigg` outputs into the Host tab."""
        from cmig.core.host import InterfaceFlux
        from cmig.gui.host_view import host_microbe_network_payload

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
            self._summary_missing(run_dir, summary_path)
            return False
        previous_integrity = self._last_integrity
        previous_detail = self._integrity_detail
        if self._inspect_gui_run(run_dir) is None:
            self._last_integrity = previous_integrity
            self._integrity_detail = previous_detail
            return False
        try:
            payload = json.loads(summary_path.read_text())
            if not isinstance(payload, dict):
                raise ValueError("host summary is not a JSON object")
            if "microbial_secretion" not in payload:
                secretion_path = run_dir / "microbial_secretion.csv"
                if secretion_path.exists():
                    with open(secretion_path, newline="") as f:
                        payload["microbial_secretion"] = {
                            str(row["metabolite"]): float(row["flux"]) for row in csv.DictReader(f)
                        }
            host_payload = payload.get("host", {})
            if not isinstance(host_payload, dict):
                raise ValueError("host summary host block is not an object")
            if not isinstance(host_payload.get("viable"), bool):
                raise ValueError("host summary viable must be a boolean")
            objective = host_payload.get("objective_value")
            biomass = None if objective is None else float(objective)
            for field in ("lumen_uptake", "unused_secretion", "microbial_secretion"):
                values = (
                    host_payload.get(field, {})
                    if field == "lumen_uptake" else payload.get(field, {})
                )
                if not isinstance(values, dict):
                    raise ValueError(f"{field} must be an object")
            transfers = payload.get("microbe_to_host", {})
            if not isinstance(transfers, dict):
                raise ValueError("microbe_to_host must be an object")
            transfer = {
                str(met): None if value is None else float(value)
                for met, value in transfers.items()
            }
            transfer_ranges = payload.get("microbe_to_host_ranges", {})
            if not isinstance(transfer_ranges, dict):
                raise ValueError("microbe_to_host_ranges must be an object")
            for interval in transfer_ranges.values():
                if not isinstance(interval, list) or len(interval) != 2:
                    raise ValueError("transfer range must contain two bounds")
                low, high = float(interval[0]), float(interval[1])
                if not (math.isfinite(low) and math.isfinite(high) and low <= high):
                    raise ValueError("transfer range must be finite and ordered")
            ambiguous = payload.get("ambiguous_metabolites", [])
            if not isinstance(ambiguous, list) or not all(
                isinstance(met, str) for met in ambiguous
            ):
                raise ValueError("ambiguous_metabolites must be a list of names")
            lumen_uptake = {
                str(met): None if value is None else float(value)
                for met, value in host_payload.get("lumen_uptake", {}).items()
            }
            uptake_rows: list[InterfaceFlux] = []
            uptake_path = run_dir / "host_uptake.csv"
            if uptake_path.exists():
                with open(uptake_path, newline="") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        met = str(row["metabolite"])
                        raw_uptake = row["uptake_flux"]
                        if raw_uptake is None or not raw_uptake.strip():
                            continue  # FVA range only: no point flux exists to display.
                        uptake = float(raw_uptake)
                        uptake_rows.append(
                            InterfaceFlux(
                                exchange_id=f"EX_{met}_e",
                                interface="bigg_external",
                                metabolite=met,
                                flux=-uptake,
                                label="uptake",
                            )
                        )
            host_microbe_network_payload(payload)
        except (OSError, ValueError, TypeError, KeyError) as e:
            self._last_integrity = previous_integrity
            self._integrity_detail = previous_detail
            self._readback_failed(
                run_dir, "readback invalid/unreadable",
                f"Run: {run_dir}\nReadback: invalid/unreadable ({e})",
            )
            self._show_status(
                "status_load_failed", kind=self.tr_map["kind_host_microbe"],
                error=f"{run_dir}: {e}",
            )
            return False

        if not isinstance(host_payload, dict) or "viable" not in host_payload:
            # Absence of the host block is missing data, not a biological finding. Defaulting
            # to viable=False rendered a red "non-viable — microbiome support insufficient",
            # i.e. a scientific conclusion manufactured from an incomplete file.
            self._readback_failed(
                run_dir, "readback invalid/unreadable",
                f"Run: {run_dir}\nReadback: invalid/unreadable (no host block in "
                f"{summary_path.name})",
            )
            self._show_status(
                "status_host_block_missing",
                summary=summary_path.name,
                run_dir=run_dir,
            )
            return False

        host_result = SimpleNamespace(
            viable=bool(host_payload.get("viable", False)),
            status=str(host_payload.get("status", "unknown")),
            biomass=biomass,
            interface_fluxes=uptake_rows,
            lumen_uptake=lumen_uptake,
        )
        # This is a readback view: retain nullable transfers from the serialized host
        # result instead of coercing an unavailable value to a scientific zero.
        impact = SimpleNamespace(
            microbe_to_host=transfer, microbe_to_host_ranges=transfer_ranges,
            ambiguous_metabolites=ambiguous,
        )
        community_payload = payload.get("community")
        community_status = (
            community_payload.get("status") if isinstance(community_payload, dict) else None
        )
        host_status = host_payload.get("status")
        transfer_solved = (
            None if host_status is None or community_status is None else
            host_status == "optimal" and community_status == "optimal"
            and biomass is not None and math.isfinite(biomass)
        )
        self.host_view.load_host_result(host_result)
        self.host_view.load_impact(impact, solved=transfer_solved)
        self.host_view.show_currency_metabolites = self.host_view.include_currency_check.isChecked()
        self.host_view.load_bigg_summary(payload, run_dir=run_dir)
        self.host_view.run_status.setText(
            self.host_view.run_status.text()
            + f" · integrity {self._last_integrity.removeprefix('Integrity: ')}"
        )
        self.current_host_microbe_dir = run_dir  # only after a successful parse
        self._register_run_output(run_dir)
        self._show_page(self.host_view)
        self._show_status("status_loaded_host", run_dir=run_dir, count=len(transfer))
        return True

    def load_dfba_dir(self, path: str | Path) -> bool:
        run_dir = Path(path).resolve()
        summary_path = run_dir / "dfba_summary.json"
        if not summary_path.exists():
            self._show_status(
                "status_summary_missing", kind=self.tr_map["kind_dfba"], path=summary_path
            )
            self._summary_missing(run_dir, summary_path)
            self.dynamics_view._clear_dynamics(
                f"Readback invalid/unreadable: {summary_path.name} not found"
            )
            return False
        inspected = self._inspect_gui_run(run_dir)
        if inspected is None:
            self.dynamics_view._clear_dynamics(f"Readback invalid/unreadable: {run_dir}")
            return False
        try:
            payload = json.loads(summary_path.read_text())
            if not isinstance(payload, dict):
                raise ValueError("dfba_summary.json is not a JSON object")
            required = {"status", "final_t", "final_biomass", "final_concentrations"}
            missing = required - payload.keys()
            if missing:
                raise ValueError(f"dfba summary missing required fields: {sorted(missing)}")
            if not isinstance(payload["status"], str):
                raise ValueError("dfba status must be a string")
            if not isinstance(payload.get("final_concentrations", {}), dict):
                raise ValueError("final_concentrations is not an object")
            if not isinstance(payload.get("warnings", []), list):
                raise ValueError("warnings is not a list")
            for key in ("final_t", "final_biomass"):
                if key in payload and payload[key] is not None:
                    float(payload[key])
            for value in payload.get("final_concentrations", {}).values():
                if value is not None:
                    float(value)
        except (OSError, ValueError, TypeError) as e:
            self._reject_gui_summary(run_dir, e)
            self.dynamics_view._clear_dynamics(f"Readback invalid/unreadable: {e}")
            self._show_status("status_load_failed", kind=self.tr_map["kind_dfba"], error=e)
            return False
        self.dynamics_view.load_dfba_summary(payload, run_dir=run_dir)
        self.dynamics_view.status.setText(
            self.dynamics_view.status.text()
            + f" · integrity {inspected['artifact_integrity']}"
        )
        self._register_run_output(run_dir)
        self._show_page(self.dynamics_view)
        self._show_status("status_loaded_dfba", run_dir=run_dir)
        return True

    def load_spatial_dir(self, path: str | Path) -> bool:
        run_dir = Path(path).resolve()
        summary_path = run_dir / "spatial_summary.json"
        if not summary_path.exists():
            self._show_status(
                "status_summary_missing", kind=self.tr_map["kind_spatial"], path=summary_path
            )
            self._summary_missing(run_dir, summary_path)
            self.spatial_page._clear_dynamics(
                f"Readback invalid/unreadable: {summary_path.name} not found"
            )
            return False
        inspected = self._inspect_gui_run(run_dir)
        if inspected is None:
            self.spatial_page._clear_dynamics(f"Readback invalid/unreadable: {run_dir}")
            return False
        try:
            payload = json.loads(summary_path.read_text())
            if not isinstance(payload, dict):
                raise ValueError("spatial_summary.json is not a JSON object")
            missing = {"status", "final_t", "final_min", "final_max"} - payload.keys()
            if missing:
                raise ValueError(f"spatial summary missing required fields: {sorted(missing)}")
            if not isinstance(payload["status"], str):
                raise ValueError("spatial status must be a string")
            if not isinstance(payload.get("warnings", []), list):
                raise ValueError("warnings is not a list")
            for key in ("final_t", "final_min", "final_max"):
                if key in payload and payload[key] is not None:
                    float(payload[key])
        except (OSError, ValueError, TypeError) as e:
            self._reject_gui_summary(run_dir, e)
            self.spatial_page._clear_dynamics(f"Readback invalid/unreadable: {e}")
            self._show_status("status_load_failed", kind=self.tr_map["kind_spatial"], error=e)
            return False
        self.spatial_page.load_spatial_summary(payload, run_dir=run_dir)
        self.spatial_page.status.setText(
            self.spatial_page.status.text()
            + f" · integrity {inspected['artifact_integrity']}"
        )
        self._register_run_output(run_dir)
        self._show_page(self.spatial_page)
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
            return self.load_run_dir(outcome.manifest_path.parent)
        self._show_status("status_fixture_failed", diagnostic=outcome.diagnostic)
        return False

    def cancel_search(self) -> None:
        for job_id in self._search_jobs:
            self.runner.cancel(job_id)
            self.bridge.cancelling.add(job_id)
            self._search_cancel_pending.add(job_id)
        self.bridge.refresh()
        self._show_search_cancel_pending()

    def _show_search_cancel_pending(self) -> None:
        """Keep the Search tab saying a cancel is pending until the job actually ends.

        The in-flight solve cannot be interrupted, so the job stays RUNNING for a while
        after Cancel; other Search-tab workflows share this status label and may write it
        meanwhile, so every poll tick puts the pending notice back.
        """
        if not self._search_cancel_pending & self._search_jobs.keys():
            return
        self.search_view.cancel_btn.setEnabled(False)
        self.search_view.run_btn.setEnabled(False)
        self.search_view.status.setText(SEARCH_CANCEL_PENDING)

    def run_search_fixture(self) -> str:
        """Run user model-pool search from the Search tab."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        requested = self.search_view.request_fields("search")
        model_ids = self.search_view.model_picker.selected_ids()
        if not model_ids:
            self.search_view.status.setText("Select at least one model.")
            return ""
        try:
            medium_file = self._medium_arg(requested["medium"])
        except (ProjectError, ValueError) as exc:
            self.search_view.status.setText(str(exc))
            return ""
        base_argv, error = _search_argv(
            {**requested, "medium": medium_file or ""}, self.search_view.target_rows()
        )
        if error:
            self.search_view.status.setText(error)
            return ""
        checkpoint = (
            Path(requested["checkpoint"]).resolve()
            if requested["checkpoint"] else None
        )
        if checkpoint is not None and checkpoint.exists() and requested["resume"] != "True":
            self.search_view.status.setText(f"{CHECKPOINT_EXISTS}: {checkpoint}")
            return ""
        try:
            out_dir, taxonomy = self._prepare_run("search", model_ids, analysis="search")
        except ProjectError as exc:
            self.search_view.status.setText(str(exc))
            return ""
        if checkpoint is not None and checkpoint.is_relative_to(out_dir):
            # The CLI publishes by replacing --out; a checkpoint inside it would be lost.
            # The folder was created empty just above, so removing it touches nothing else.
            self._discard_run(out_dir, taxonomy)
            self.search_view.status.setText(
                f"Checkpoint is inside this run's output folder ({out_dir}); "
                "choose a checkpoint path outside it."
            )
            return ""
        argv = ["search", "--taxonomy", str(taxonomy), *base_argv[1:], "--out", str(out_dir)]
        warning = self.search_view.reference_warning()
        _install_stderr_router()

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            output_name = "search_summary.json"
            from cmig.core.search_execution import SearchControl
            from cmig.service.search_service import search_control

            # The control's values win over the argv inside the CLI, so every value the
            # argv carries for it must match — otherwise the run would execute N workers or
            # threads while its provenance recorded a different number.
            control = SearchControl(
                checkpoint=Path(requested["checkpoint"]).resolve()
                if requested["checkpoint"] else None,
                resume=requested["resume"] == "True", workers=int(requested["workers"]),
                solver_threads=int(requested["solver_threads"]),
                cancelled=lambda: ctx.cancelled, progress=ctx.report_progress,
                solve_timeout=float(requested["timeout"]) or None,
            )
            with search_control(control), _captured_job_stderr() as stderr_chunks:
                rc = main(argv)
            if rc == 130:
                ctx.raise_if_cancelled()
            if rc != 0:
                from cmig.service.jobrunner import ArtifactJobFailure

                artifacts = _failed_search_artifacts(out_dir, rc)
                cli_error = "".join(stderr_chunks).strip()
                if cli_error:
                    artifacts["cli_error"] = cli_error
                    artifacts.setdefault("warnings", []).insert(0, f"CLI error: {cli_error}")
                cause = _search_input_diagnostic(medium_file or "") if rc == 2 else None
                if cause:
                    artifacts.setdefault("warnings", []).append(cause)
                    artifacts["input_diagnostic"] = cause
                reason = "; ".join(
                    part for part in (cli_error, cause) if part
                ) or "see diagnostics"
                raise ArtifactJobFailure(
                    f"search failed with rc={rc}; {reason}; outputs: {out_dir}",
                    artifacts,
                )
            _finish_after_artifacts(ctx)
            payload = json.loads((out_dir / output_name).read_text())
            if not isinstance(payload, dict):
                raise RuntimeError("search output is not a JSON object")
            return payload

        jid = self.submit_job("search_fixture", _job)
        self._record_command(jid, out_dir, argv)
        self._search_jobs[jid] = (out_dir, requested)
        self.search_view.run_btn.setEnabled(False)
        self.search_view.cancel_btn.setEnabled(True)
        self.search_view.status.setText(
            f"search started: {jid} · "
            + medium_mode_text(requested["medium"], requested["medium_mode"])
            + f" · output: {out_dir}"
            + (f" · Warning: {warning}" if warning else "")
        )
        return jid

    def _host_inputs(
        self, page: AnalysisPage, kind: str, request: dict[str, Any], biomass_error: str
    ) -> tuple[Path, Path | None, str, str | None, str | None] | None:
        """Check the Host page's choices and claim a run: (out, taxonomy, host, media), or
        None after the reason is shown on the page."""
        message = ""
        if not request["host_id"]:
            message = "Choose a host model."
        elif not request["models"]:
            message = "Select at least one microbial model."
        elif request["host_id"] in request["models"]:
            message = (
                f"{request['host_id']} is also selected as a microbe; pick it only as the host."
            )
        elif (
            float(request["microbial_biomass_gdw"]) <= 0.0
            or float(request["host_biomass_gdw"]) <= 0.0
            or not request["biomass_basis_kind"]
            or not request["biomass_basis_source"]
        ):
            message = biomass_error
        if message:
            page.status.setText(message)
            return None
        try:
            host = str(self._model_file(request["host_id"]))
            host_medium = self._medium_arg(request["host_medium"])
            microbe_medium = self._medium_arg(request["microbe_medium"])
            out_dir, taxonomy = self._prepare_run(
                kind, list(request["models"]), analysis=self._page_key(page)
            )
        except (ProjectError, ValueError) as exc:
            page.status.setText(str(exc))
            return None
        return out_dir, taxonomy, host, host_medium, microbe_medium

    def run_host_microbe_bigg(self) -> str:
        """Run BiGG host-microbe analysis from the Host tab."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        page = self.host_view
        request = page.request()
        inputs = self._host_inputs(
            page, "host-microbe", request,
            "Positive biomass gDW values, basis kind, and source are required.",
        )
        if inputs is None:
            return ""
        out_dir, taxonomy, host, host_medium, microbe_medium = inputs
        argv = [
            "host-microbe-bigg",
            "--host",
            host,
            "--taxonomy",
            str(taxonomy),
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
        if request["keep_host_uptake"]:
            argv.append("--keep-host-uptake")
        if request["include_currency_metabolites"]:
            argv.append("--include-currency-metabolites")
        if request["allow_unknown_medium"]:
            argv.append("--allow-unknown-medium")
        if host_medium:
            argv.extend(["--host-medium", host_medium])
        if microbe_medium:
            argv.extend(["--microbe-medium", microbe_medium])
        if request["host_objective"]:
            argv.extend(["--host-objective", str(request["host_objective"])])

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"host-microbe run failed with rc={rc}")
            _finish_after_artifacts(ctx)
            payload = json.loads((out_dir / "host_microbe_bigg_summary.json").read_text())
            if not isinstance(payload, dict):
                raise RuntimeError("host-microbe output is not a JSON object")
            return payload

        jid = self.submit_job("host_microbe_bigg", _job)
        self._record_command(jid, out_dir, argv)
        self._host_microbe_jobs[jid] = out_dir
        self.host_view.run_btn.setEnabled(False)
        self.host_view.show_currency_metabolites = bool(request["include_currency_metabolites"])
        self.host_view.set_running(jid)
        self._show_status("status_started", kind=self.tr_map["kind_host_microbe"], job_id=jid)
        return jid

    def run_host_search_bigg(self) -> str:
        """Rank microbial combinations by host objective/target transfer for one host."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        page = self.host_search_page
        request = page.request()
        inputs = self._host_inputs(
            page, "host-search", request,
            "Positive biomass gDW values, basis kind, and source are required for ranking.",
        )
        if inputs is None:
            return ""
        out_dir, taxonomy, host, host_medium, microbe_medium = inputs
        argv = [
            "host-search-bigg",
            "--host",
            host,
            "--taxonomy",
            str(taxonomy),
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
        if request["keep_host_uptake"]:
            argv.append("--keep-host-uptake")
        if request["include_currency_metabolites"]:
            argv.append("--include-currency-metabolites")
        if request["allow_unknown_medium"]:
            argv.append("--allow-unknown-medium")
        if host_medium:
            argv.extend(["--host-medium", host_medium])
        if microbe_medium:
            argv.extend(["--microbe-medium", microbe_medium])
        if request["host_objective"]:
            argv.extend(["--host-objective", str(request["host_objective"])])

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"host-search run failed with rc={rc}")
            _finish_after_artifacts(ctx)
            payload = json.loads((out_dir / "host_search_summary.json").read_text())
            if not isinstance(payload, dict):
                raise RuntimeError("host-search output is not a JSON object")
            return payload

        jid = self.submit_job("host_search_bigg", _job)
        self._record_command(jid, out_dir, argv)
        self._host_search_jobs[jid] = (out_dir, page.request_fields("host_search"))
        page.run_btn.setEnabled(False)
        page.status.setText(f"host-search started: {jid}")
        self._show_status("status_started", kind=self.tr_map["kind_host_search"], job_id=jid)
        return jid

    def _page_run_inputs(
        self, page: GeneKoPage | StrainGrowthPage | RatioImpactPage, kind: str, medium_ref: str
    ) -> tuple[Path, Path | None, str | None] | None:
        """Claim a run for a page with a model picker: (out, taxonomy, medium file), or None
        after the reason is shown on the page."""
        model_ids = page.model_picker.selected_ids()
        if not model_ids:
            page.status.setText("Select at least one model.")
            return None
        try:
            medium_file = self._medium_arg(medium_ref)
            out_dir, taxonomy = self._prepare_run(kind, model_ids, analysis=self._page_key(page))
        except (ProjectError, ValueError) as exc:
            page.status.setText(str(exc))
            return None
        return out_dir, taxonomy, medium_file

    def run_gene_ko_search(self) -> str:
        """Run fixed-combination single-gene KO screening from the Gene Knockout page."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        page = self.gene_ko_page
        requested = page.request_fields("gene_ko")
        members = requested["ko_members"]
        member = requested["ko_member"]
        genes = requested["ko_genes"]
        target, direction, target_error = _single_target(
            [(requested["target"], requested["direction"], "", "")]
        )
        if target_error:
            page.status.setText(target_error)
            return ""
        if not members:
            page.status.setText("KO members are required.")
            return ""
        if genes and not member:
            page.status.setText("Gene ids require a specific edited member.")
            return ""
        # Snapshot every answer-determining widget value HERE, on the GUI thread, before the
        # closure is handed to the executor. Reading `.value()` inside `_job` meant a queued
        # run silently executed the parameters the user typed *after* clicking, and read a
        # QWidget from a worker thread (undefined behaviour in Qt). Coordinator CC-8.
        max_genes = requested["max_genes"]
        top_k = requested["ko_top_k"]
        inputs = self._page_run_inputs(page, "gene-ko", requested["medium"])
        if inputs is None:
            return ""
        out_dir, taxonomy, medium_file = inputs
        argv = [
            "gene-ko-search",
            "--taxonomy",
            str(taxonomy),
            "--members",
            members,
            "--target",
            target,
            "--max-genes",
            max_genes,
            "--top-k",
            top_k,
            "--direction",
            direction,
            "--growth-fraction",
            requested["growth_fraction"],
            "--out",
            str(out_dir),
        ]
        if medium_file:
            argv.extend(["--medium", medium_file, "--exact-medium"])
        if member:
            argv.extend(["--member", member])
        if genes:
            argv.extend(["--genes", genes])

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"gene KO search failed with rc={rc}")
            _finish_after_artifacts(ctx)
            payload = json.loads((out_dir / "gene_ko_summary.json").read_text())
            if not isinstance(payload, dict):
                raise RuntimeError("gene KO output is not a JSON object")
            return payload

        jid = self.submit_job("gene_ko_search", _job)
        self._record_command(jid, out_dir, argv)
        self._gene_ko_jobs[jid] = (out_dir, requested)
        page.run_btn.setEnabled(False)
        page.status.setText(f"gene KO search started: {jid}")
        self._show_status("status_started", kind=self.tr_map["kind_gene_ko_search"], job_id=jid)
        return jid

    def run_strain_growth_report(self) -> str:
        """Run per-strain single/community growth profiling from the Strain Growth page."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        page = self.strain_growth_page
        requested = page.request_fields("strain_growth")
        inputs = self._page_run_inputs(page, "strain-growth", requested["medium"])
        if inputs is None:
            return ""
        out_dir, taxonomy, medium_file = inputs
        argv = [
            "strain-growth",
            "--taxonomy",
            str(taxonomy),
            "--tradeoff-f",
            requested["cooperative_tradeoff"],
            "--single-medium",
            "community",
            "--out",
            str(out_dir),
        ]
        if medium_file:
            argv.extend(["--medium", medium_file, "--exact-medium"])

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"strain growth failed with rc={rc}")
            _finish_after_artifacts(ctx)
            payload = json.loads((out_dir / "strain_growth_summary.json").read_text())
            if not isinstance(payload, dict):
                raise RuntimeError("strain growth output is not a JSON object")
            return payload

        jid = self.submit_job("strain_growth", _job)
        self._record_command(jid, out_dir, argv)
        self._strain_growth_jobs[jid] = (out_dir, requested)
        page.run_btn.setEnabled(False)
        page.status.setText(f"strain growth started: {jid}")
        self._show_status("status_started", kind=self.tr_map["kind_strain_growth"], job_id=jid)
        return jid

    def run_abundance_impact(self) -> str:
        """Run one-member abundance sweep from the Ratio Impact page."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        page = self.ratio_impact_page
        requested = page.request_fields("abundance_impact")
        member = requested["growth_member"]
        fractions = requested["fractions"]
        target, _direction, target_error = _single_target(
            [(requested["target"], "max_secretion", "", "")]
        )
        if target_error:
            page.status.setText(target_error)
            return ""
        if not member:
            page.status.setText("Target member is required for ratio impact.")
            return ""
        inputs = self._page_run_inputs(page, "abundance-impact", requested["medium"])
        if inputs is None:
            return ""
        out_dir, taxonomy, medium_file = inputs
        argv = [
            "abundance-impact",
            "--taxonomy",
            str(taxonomy),
            "--member",
            member,
            "--fractions",
            fractions or "0.1,0.25,0.5,0.75",
            "--target",
            target,
            "--tradeoff-f",
            requested["cooperative_tradeoff"],
            "--out",
            str(out_dir),
        ]
        if medium_file:
            argv.extend(["--medium", medium_file, "--exact-medium"])

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"abundance impact failed with rc={rc}")
            _finish_after_artifacts(ctx)
            payload = json.loads((out_dir / "abundance_impact_summary.json").read_text())
            if not isinstance(payload, dict):
                raise RuntimeError("abundance impact output is not a JSON object")
            return payload

        jid = self.submit_job("abundance_impact", _job)
        self._record_command(jid, out_dir, argv)
        self._abundance_impact_jobs[jid] = (
            out_dir,
            requested,
        )
        page.run_btn.setEnabled(False)
        page.status.setText(f"ratio impact started: {jid}")
        self._show_status("status_started", kind=self.tr_map["kind_ratio_impact"], job_id=jid)
        return jid

    def run_dfba(self) -> str:
        """Run user-model dFBA from the Dynamics tab."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        request = self.dynamics_view.dfba_request()
        if not request["model"]:
            self.dynamics_view.status.setText("Choose a model.")
            return ""
        try:
            model = str(self._model_file(str(request["model"])))
            out_dir, _ = self._prepare_run("dfba", [], analysis="dfba")
        except (ProjectError, ValueError) as exc:
            self.dynamics_view.status.setText(str(exc))
            return ""
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

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"dFBA failed with rc={rc}")
            _finish_after_artifacts(ctx)
            payload = json.loads((out_dir / "dfba_summary.json").read_text())
            if not isinstance(payload, dict):
                raise RuntimeError("dFBA output is not a JSON object")
            return payload

        jid = self.submit_job("dfba", _job)
        self._record_command(jid, out_dir, argv)
        self._dfba_jobs[jid] = out_dir
        self.dynamics_view.run_dfba_btn.setEnabled(False)
        self.dynamics_view.status.setText(f"dFBA started: {jid}")
        self._show_status("status_started", kind=self.tr_map["kind_dfba"], job_id=jid)
        return jid

    def run_spatial_preview(self) -> str:
        """Run COMETS-inspired spatial medium preview from the Spatial Preview page."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        request = self.spatial_page.spatial_request()
        try:
            out_dir, _ = self._prepare_run("spatial", [], analysis="spatial")
        except ProjectError as exc:
            self.spatial_page.status.setText(str(exc))
            return ""
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

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"spatial preview failed with rc={rc}")
            _finish_after_artifacts(ctx)
            payload = json.loads((out_dir / "spatial_summary.json").read_text())
            if not isinstance(payload, dict):
                raise RuntimeError("spatial output is not a JSON object")
            return payload

        jid = self.submit_job("spatial_preview", _job)
        self._record_command(jid, out_dir, argv)
        self._spatial_jobs[jid] = out_dir
        self.spatial_page.run_btn.setEnabled(False)
        self.spatial_page.status.setText(f"spatial preview started: {jid}")
        self._show_status("status_started", kind=self.tr_map["kind_spatial"], job_id=jid)
        return jid

    def run_community_solve(self) -> str:
        """Run a community solve from the Community Builder tab's members/abundances/tradeoff.

        The picked members become the run's `runs/_inputs` taxonomy (abundance 1 unless the
        builder's table gives one), then `cmig solve` runs through the JobRunner (same
        argv+main() pattern as the other product tabs).
        """
        from cmig.cli.main import main
        from cmig.service import JobContext

        model_ids = self.community_builder.model_picker.selected_ids()
        if not model_ids:
            self.community_builder.status.setText("Select at least one member model.")
            return ""
        members = self.community_builder.members()
        if self.community_builder.invalid_rows:
            rows = ", ".join(str(r) for r in self.community_builder.invalid_rows)
            self.community_builder.status.setText(
                f"row {rows}: abundance is not a number — fix it before running."
            )
            return ""
        # An abundance row for a model that is not picked used to be dropped silently, so the
        # community that ran differed from the table on screen.
        unknown = sorted(set(members) - set(model_ids))
        if unknown:
            self.community_builder.status.setText(
                f"abundance rows for unselected models: {unknown}; select them or remove the rows"
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
        try:
            out_dir, tax_path = self._prepare_run(
                "community", model_ids, abundances=members, analysis="community"
            )
        except ProjectError as exc:
            self.community_builder.status.setText(str(exc))
            return ""
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

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"community solve failed with rc={rc}")
            _finish_after_artifacts(ctx)
            manifest_path = out_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
            return {"manifest": manifest}

        jid = self.submit_job("community_solve", _job)
        self._record_command(jid, out_dir, argv)
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
        model_ids = list(request["models"])
        if not model_ids:
            self.sweep_view.status.setText(self.tr_map["sweep_select_source"])
            return ""
        decisions = str(request["namespace_decisions"])
        assumed = bool(request["assume_bigg"])
        if decisions and assumed:
            self.sweep_view.status.setText(self.tr_map["sweep_namespace_choice"])
            return ""
        if not decisions and not assumed:
            self.sweep_view.status.setText(self.tr_map["sweep_namespace_required"])
            return ""
        try:
            out_dir, taxonomy = self._prepare_run("sweep", model_ids, analysis="sweep")
        except ProjectError as exc:
            self.sweep_view.status.setText(str(exc))
            return ""
        argv = [
            "sweep",
            "--taxonomy",
            str(taxonomy),
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

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
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
        self._record_command(jid, out_dir, argv)
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
        try:
            out_dir, _ = self._prepare_run("sweep", [])
        except ProjectError as exc:
            self.sweep_view.status.setText(str(exc))
            return ""
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

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"sweep-fixture failed with rc={rc}")
            _finish_after_artifacts(ctx)
            return {"out_dir": str(out_dir)}

        jid = self.submit_job("sweep_fixture", _job)
        self._record_command(jid, out_dir, argv)
        self._sweep_jobs[jid] = (out_dir, "fixture")
        self.sweep_view.run_btn.setEnabled(False)
        self.sweep_view.status.setText(self._message("sweep_started_fixture", job_id=jid))
        self._show_status("status_started", kind=self.tr_map["kind_sweep"], job_id=jid)
        return jid

    def _medium_input_file(self, out_dir: Path, uptake: dict[str, float]) -> Path:
        """Write the editor's medium as `runs/_inputs/<run>-medium.json` (never inside the
        run folder, which the CLI publishes as a whole)."""
        path = self.session.require().inputs_dir / f"{out_dir.name}-medium.json"
        try:
            atomic_write_text(path, json.dumps(uptake))
        except OSError as exc:
            raise ProjectError(f"cannot write run inputs {path}: {exc}") from exc
        return path

    def run_medium_growth_check(self) -> str:
        """Run the editor request through the real ``cmig solve`` CLI workflow."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        model_ids = self.medium_editor.model_picker.selected_ids()
        if not model_ids:
            self.medium_editor.growth_label.setText(
                self.tr_map["medium_select_taxonomy_growth"]
            )
            return ""
        namespace_argv, namespace_error = self.medium_editor.namespace_policy()
        if namespace_error:
            self.medium_editor.growth_label.setText(namespace_error)
            return ""
        mode_error = self.medium_editor.medium_mode_error()
        if mode_error:
            self.medium_editor.growth_label.setText(mode_error)
            return ""
        try:
            spec = self.medium_editor.to_spec()
        except ValueError:
            return ""  # to_spec() already set an explicit status message (no silent failure)

        uptake = dict(spec.uptake)
        exact = self.medium_editor.exact_medium_check.isChecked()
        allow_unknown = self.medium_editor.allow_unknown_check.isChecked()
        medium_file: Path | None = None
        try:
            out_dir, taxonomy = self._prepare_run("medium-growth", model_ids, analysis="medium")
            if uptake:
                try:
                    medium_file = self._medium_input_file(out_dir, uptake)
                except ProjectError:
                    self._discard_run(out_dir, taxonomy)
                    raise
        except ProjectError as exc:
            self.medium_editor.growth_label.setText(str(exc))
            return ""
        request: dict[str, Any] = {
            "models": tuple(model_ids),
            "medium": tuple(sorted((exchange, float(limit)) for exchange, limit in uptake.items())),
            "exact": exact,
            "namespace": tuple(namespace_argv),
        }
        argv = [
            "solve",
            "--taxonomy",
            str(taxonomy),
            "--out",
            str(out_dir),
            *namespace_argv,
        ]
        if medium_file is not None:
            argv.extend(["--medium", str(medium_file)])
        if exact:
            argv.append("--exact-medium")
        if allow_unknown:
            argv.append("--allow-unknown-medium")
        self._medium_context_changed()
        self.medium_editor.profile_delta_label.clear()
        self.medium_editor.dropped_ids_label.clear()

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            rc = main(argv)
            manifest_path = out_dir / "manifest.json"
            if not manifest_path.exists() or not (out_dir / "profile.parquet").exists():
                raise RuntimeError(f"growth check failed with rc={rc}")
            _finish_after_artifacts(ctx)
            manifest = json.loads(manifest_path.read_text())
            if not isinstance(manifest, dict):
                raise RuntimeError("growth check manifest is not a JSON object")
            result = _solve_result_like_from_run_dir(out_dir)
            return {
                "manifest": manifest,
                "growth": result.objective if result.status == "optimal" else None,
                "status": result.status,
                "dropped_ids": _medium_dropped_ids(manifest),
                "diagnostic": manifest.get("diagnostic"),
                "cli_rc": rc,
            }

        jid = self.submit_job("medium_growth_check", _job)
        self._record_command(jid, out_dir, argv)
        self._medium_growth_jobs[jid] = (out_dir, request)
        self.medium_editor.check_growth_btn.setEnabled(False)
        self.medium_editor.growth_label.setText(
            self._message("medium_growth_started", job_id=jid)
        )
        self._show_status("status_started", kind=self.tr_map["kind_growth_check"], job_id=jid)
        return jid

    def run_minimal_medium(self) -> str:
        """Launch ``cmig minimal-medium`` for the selected model and current medium."""
        from cmig.cli.main import main
        from cmig.service import JobContext

        chosen = self.medium_editor.single_model_picker.selected_ids()
        if not chosen:
            self.medium_editor.minimal_status.setText(
                self.tr_map["medium_select_model_minimal"]
            )
            return ""
        namespace_argv, namespace_error = self.medium_editor.namespace_policy()
        if namespace_error:
            self.medium_editor.minimal_status.setText(namespace_error)
            return ""
        mode_error = self.medium_editor.medium_mode_error()
        if mode_error:
            self.medium_editor.minimal_status.setText(mode_error)
            return ""
        try:
            spec = self.medium_editor.to_spec()
        except ValueError:
            return ""

        uptake = dict(spec.uptake)
        exact = self.medium_editor.exact_medium_check.isChecked()
        allow_unknown = self.medium_editor.allow_unknown_check.isChecked()
        min_growth = self.medium_editor.min_growth_spin.value()
        oxygen_mode = str(self.medium_editor.oxygen_mode_combo.currentData())
        medium_file: Path | None = None
        try:
            model = self._model_file(chosen[0])
            out_dir, _ = self._prepare_run("minimal-medium", [], analysis="medium")
            if uptake:
                try:
                    medium_file = self._medium_input_file(out_dir, uptake)
                except ProjectError:
                    self._discard_run(out_dir)
                    raise
        except ProjectError as exc:
            self.medium_editor.minimal_status.setText(str(exc))
            return ""
        argv = [
            "minimal-medium",
            "--model",
            str(model),
            "--min-growth",
            f"{min_growth:.12g}",
            "--oxygen-mode",
            oxygen_mode,
            "--out",
            str(out_dir),
            *namespace_argv,
        ]
        if medium_file is not None:
            argv.extend(["--medium", str(medium_file)])
        if exact:
            argv.append("--exact-medium")
        if allow_unknown:
            argv.append("--allow-unknown-medium")

        def _job(ctx: JobContext) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            ctx.raise_if_cancelled()
            rc = main(argv)
            summary_path = out_dir / "minimal_medium_summary.json"
            if not summary_path.exists():
                raise RuntimeError(f"minimal-medium failed with rc={rc}")
            _finish_after_artifacts(ctx)
            payload = json.loads(summary_path.read_text())
            if not isinstance(payload, dict):
                raise RuntimeError("minimal-medium output is not a JSON object")
            payload["cli_rc"] = rc
            return payload

        jid = self.submit_job("minimal_medium", _job)
        self._record_command(jid, out_dir, argv)
        self._minimal_medium_jobs[jid] = out_dir
        self.medium_editor.minimal_medium_btn.setEnabled(False)
        self.medium_editor.minimal_status.setText(
            self._message("medium_minimal_started", job_id=jid)
        )
        self._show_status("status_started", kind=self.tr_map["kind_minimal_medium"], job_id=jid)
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
            self._compare_failed()
            self.scenario_compare.status.setText("Select both Run A and Run B directories.")
            return
        path_a, path_b = Path(dir_a), Path(dir_b)
        if not (path_a / "profile.parquet").exists() or not (path_b / "profile.parquet").exists():
            self._compare_failed()
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
            self._compare_failed()
            self.scenario_compare.status.setText(f"Scenario compare failed: {e}")
            return
        self.scenario_compare.load_comparison(delta)
        self._blank_base_for_overlay()
        self.profile_view.show_delta_overlay(
            delta,
            baseline_label=self._message("profile_scenario_baseline", name=path_a.name),
            variant_label=self._message("profile_scenario_variant", name=path_b.name),
        )
        self._show_profile("compare")
        self.scenario_compare.status.setText(
            f"compare complete: {dir_a} vs {dir_b} · {self.tr_map['profile_overlay_available']}"
        )
        self._show_status("status_compare_complete")

    def _register_run_output(self, out_dir: Path) -> None:
        """A completed run inside the project appears in RUNS; an outside run is listed as opened.

        A run outside the project (e.g. a fixture run written to a chosen folder) would
        otherwise never appear anywhere in the UI, so a GUI-only researcher could not find the
        run_hash a publication needs.
        """
        out_dir = Path(out_dir).resolve()
        project = self.session.project
        if project is not None and out_dir.parent == project.runs_dir.resolve():
            self.session.refresh_runs()
        else:
            if all(entry.path != out_dir for entry in self._external_runs):
                self._external_runs.append(inspect_run(out_dir))
            self.refresh_workspace()
        self._show_run_in_inspector(out_dir)  # status and integrity, as RUNS selection shows

    def _settle_run_jobs(self) -> bool:
        """Record how each ended job left its run folder. True when RUNS needs a refresh.

        A failed job's folder is listed as failed and a cancelled job's as cancelled, whether
        or not it holds anything: the CLI discards its staged output when it is cancelled, and
        the empty folder is still the record that the run was tried. The state is also written
        beside the run's inputs (never into the CLI's folder) so a restart lists it the same.
        """
        changed = False
        for job_id, run_dir in list(self._job_runs.items()):
            job = self.runner.poll(job_id)
            if job.status not in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
                continue
            del self._job_runs[job_id]
            if self._in_project_runs(run_dir):  # a closed project's run is not shown here
                self._just_finished.append(
                    (run_dir, "" if job.status is JobStatus.DONE else (job.error or ""))
                )
            if job.status is JobStatus.DONE:
                continue  # a finished run is judged by what it holds
            changed = True
            self._run_states[_run_key(run_dir)] = job.status.value
            try:
                proj.write_run_state(run_dir, job.status.value, job.kind)
            except ProjectError as exc:
                self.statusBar().showMessage(str(exc), 8000)
        return changed

    _STATUS_SYMBOLS = {"ok": "✓", "degraded": "⚠", "warning": "⚠", "cancelled": "⊘"}

    def _show_last_run(self, run_dir: Path, error: str = "") -> None:
        """Name the last finished run in the status bar; clicking it opens that run."""
        from cmig.gui.inspector import _solver_label
        from cmig.gui.run_restore import analysis_for_run

        if not self._in_project_runs(run_dir):
            return
        entry = self._run_entry(Path(run_dir).resolve())
        key, _record, _problem = analysis_for_run(entry.path)
        title = (dict(ANALYSES).get(key or "") or ("Check Growth" if key == "check_growth"
                 else entry.label.split(" · ")[0]))
        symbol = self._STATUS_SYMBOLS.get(entry.status, "✗")
        parts = [f"{symbol} {title}", entry.name]
        try:
            manifest = json.loads((entry.path / "manifest.json").read_text())
        except (OSError, ValueError):
            manifest = None
        solver = _solver_label(manifest)
        if solver and symbol != "✗":
            parts.append(solver)
        full_reason = self._failure_reason(error, first_line_only=False)
        tip = [str(entry.path)]
        if symbol == "✗":
            parts.append(self._failure_reason(error) or entry.status)
            tip.insert(0, full_reason or f"Status: {entry.status}")
        elif symbol == "⚠":
            tip.insert(0, f"Status: {entry.status}")
        # A long reason is cut at the bar's edge; the tooltip carries all of it.
        self.last_run_button.setText(self.last_run_button.fontMetrics().elidedText(
            " · ".join(parts), Qt.TextElideMode.ElideRight, 640))
        self.last_run_button.setToolTip("\n".join(tip))
        self.last_run_button.setVisible(True)
        self._last_run_dir = entry.path

    @staticmethod
    def _failure_reason(error: str, *, first_line_only: bool = True) -> str:
        """A job's error as readable text (a serialized Diagnostic or plain text)."""
        message = str((parse_diagnostic(error) or {}).get("message") or error)
        text = message.removeprefix("RuntimeError: ").strip()
        lines = text.splitlines()
        if not lines:
            return ""
        return lines[0] if first_line_only else text

    def _open_last_run(self) -> None:
        if self._last_run_dir is not None:
            self._open_run_entry(self._last_run_dir)

    def _clear_last_run(self) -> None:
        """Forget the last run: a previous project's run is neither shown nor opened."""
        self._last_run_dir = None
        self._just_finished.clear()
        self.last_run_button.setText("")
        self.last_run_button.setToolTip("")
        self.last_run_button.setVisible(False)

    def _poll_completed_jobs(self) -> None:
        # A readback hash runs in a nested event loop (`_run_off_thread`), which lets this
        # 500 ms timer fire again before the first pass is done. Skip; the next tick retries.
        if self._polling:
            return
        self._polling = True
        try:
            self._poll_completed_jobs_pass()
        finally:
            self._polling = False

    def _poll_completed_jobs_pass(self) -> None:
        settled = self._settle_run_jobs()
        self._finish_index_job()
        self._finish_search_rows_job()
        self._finish_check_growth_jobs()
        for jid in list(self._import_jobs):
            job = self.runner.poll(jid)
            if job.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
                done = job.status is JobStatus.DONE and isinstance(job.result, dict)
                reason = (
                    str(job.result.get("scan_error") or "")
                    if job.status is JobStatus.FAILED and isinstance(job.result, dict) else ""
                )
                self._finish_import(jid, job.result if done else None, job.status.value, reason)
            elif self._take_import_scan(jid):
                self.refresh_workspace()
        for jid in list(self._agora2_jobs):
            job = self.runner.poll(jid)
            if job.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
                self._finish_agora2(jid, job)
        for jid, (commit, constraint, auto) in list(self._sandbox_jobs.items()):
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
                self._empty_community_result_on("sandbox")
                self.sandbox_view.delta_view.setRowCount(0)
                self.sandbox_view.status.setText(f"Sandbox {job.status.value}: {job.error or jid}")
                continue
            result = job.result
            if result is None or getattr(result, "delta", None) is None:
                self._empty_community_result_on("sandbox")
                self.sandbox_view.delta_view.setRowCount(0)
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
            self._blank_base_for_overlay()
            self.profile_view.show_delta_overlay(
                result.delta,
                baseline_label=self.tr_map["profile_sandbox_baseline"],
                variant_label=variant_label,
            )
            # Only an explicit Preview / Commit moves the centre to Profile. A debounced preview
            # fires while the user is still typing bounds, and leaving the page would hide the
            # delta table and its "table has changed" warning — and commit a half-typed cell.
            # Either way the overlay belongs to the Sandbox page, never to another page's run.
            editing = (
                self.pages.currentWidget() is self.sandbox_page
                and self.sandbox_view.bound_table.state()
                == QAbstractItemView.State.EditingState
            )
            if not auto and not editing:
                self._show_profile("sandbox")
            else:
                self._host_community_result("sandbox")
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
            was_cancel_pending = jid in self._search_cancel_pending
            if job.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
                self._search_cancel_pending.discard(jid)
                self.bridge.cancelling.discard(jid)
                if self._from_closed_project(out_dir):
                    self._search_jobs.pop(jid, None)
                    self.search_view.run_btn.setEnabled(True)
                    self.search_view.cancel_btn.setEnabled(False)
                    continue
            if job.status is JobStatus.DONE and isinstance(job.result, dict):
                self._search_jobs.pop(jid, None)
                self.search_view.run_btn.setEnabled(True)
                self.search_view.cancel_btn.setEnabled(False)
                if self._inspect_gui_run(out_dir) is None:
                    self.search_view.invalidate_results()
                    self.search_view.status.setText(f"Readback invalid/unreadable: {out_dir}")
                    self.current_search_dir = None
                    continue
                try:
                    validate_search_summary(job.result)
                    self.search_view.load_summary(
                        job.result,
                        run_dir=out_dir,
                        request_note=self.search_view.superseded_note(requested, "search"),
                        workflow_kind="search",
                        executed_request=requested,
                    )
                except (TypeError, ValueError, KeyError) as exc:
                    self._reject_gui_summary(out_dir, exc)
                    self.search_view.invalidate_results()
                    self.search_view.status.setText(f"Readback invalid/unreadable: {exc}")
                    self.current_search_dir = None
                    self._show_status("status_run_load_failed", error=exc)
                    continue
                self.current_search_dir = out_dir
                self._show_page(self.search_view)
                self._register_run_output(out_dir)
                self._show_status(
                    "status_complete_out",
                    kind=self.tr_map["kind_search"],
                    job_id=jid,
                    out_dir=out_dir,
                )
            elif job.status is JobStatus.DONE:
                self._search_jobs.pop(jid, None)
                self.search_view.run_btn.setEnabled(True)
                self.search_view.cancel_btn.setEnabled(False)
                if self._inspect_gui_run(out_dir) is not None:
                    self._reject_gui_summary(out_dir, "completed Search result is not an object")
                self.search_view.invalidate_results()
                self.search_view.status.setText(f"Readback invalid/unreadable: {out_dir}")
                self.current_search_dir = None
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._search_jobs.pop(jid, None)
                self.search_view.run_btn.setEnabled(True)
                self.search_view.cancel_btn.setEnabled(False)
                if job.status is JobStatus.FAILED and isinstance(job.result, dict):
                    if self._inspect_gui_run(out_dir) is None:
                        self.search_view.invalidate_results()
                        self.search_view.status.setText(
                            f"Readback invalid/unreadable: {out_dir}"
                        )
                        self.current_search_dir = None
                        continue
                    if not (out_dir / "manifest.json").exists() and (
                        job.result.get("cli_exit_code") != 2
                    ):
                        self._reject_gui_summary(out_dir, "failed run has no manifest")
                        self.search_view.invalidate_results()
                        self.search_view.status.setText(
                            f"Readback invalid/unreadable: {out_dir}"
                        )
                        self.current_search_dir = None
                        continue
                    try:
                        validate_search_summary(job.result)
                        self.search_view.load_summary(
                            job.result,
                            run_dir=out_dir,
                            request_note=self.search_view.superseded_note(requested, "search"),
                            workflow_kind="search",
                            executed_request=requested,
                        )
                    except (TypeError, ValueError, KeyError) as exc:
                        self._reject_gui_summary(out_dir, exc)
                        self.search_view.invalidate_results()
                        self.search_view.status.setText(f"Readback invalid/unreadable: {exc}")
                        self.current_search_dir = None
                        self._show_status("status_run_load_failed", error=exc)
                        continue
                    self.current_search_dir = out_dir
                    cause = job.result.get("cli_error") or job.result.get(
                        "input_diagnostic"
                    )
                    self.search_view.status.setText(
                        f"search failed (rc={job.result.get('cli_exit_code', '?')})"
                        + (f": {cause}" if cause else "")
                        + "; diagnostics and artifact path are in details"
                    )
                    self._show_page(self.search_view)
                    self._register_run_output(out_dir)
                else:
                    # No replacement summary was published. Keep every part of the
                    # displayed run (including its badge and export pointer) together.
                    self.statusBar().showMessage(
                        f"search {job.status.value}: {job.error or jid}"
                    )
                    if was_cancel_pending:
                        # The pending notice must not outlive the job it describes.
                        self.search_view.status.setText(
                            f"search {job.status.value}: {job.error or jid}"
                        )
        for jid, out_dir in list(self._host_microbe_jobs.items()):
            job = self.runner.poll(jid)
            if job.status in _ENDED and self._from_closed_project(out_dir):
                self._host_microbe_jobs.pop(jid, None)
                self.host_view.run_btn.setEnabled(True)
            elif job.status is JobStatus.DONE:
                self._host_microbe_jobs.pop(jid, None)
                self.host_view.run_btn.setEnabled(True)
                # A completion message must not cover a failed readback (status bar + inspector).
                if self.load_host_microbe_bigg_dir(out_dir):
                    self._show_status(
                        "status_complete", kind=self.tr_map["kind_host_microbe"], job_id=jid
                    )
                else:
                    # The earlier run must not stay drawn under this run's failure message.
                    self.host_view.clear_result()
                    self.host_view.run_status.setText(_UNREADABLE_RESULT.format(
                        kind="host-microbe", out_dir=out_dir))
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._host_microbe_jobs.pop(jid, None)
                self.host_view.run_btn.setEnabled(True)
                self.host_view.clear_result()
                self.host_view.run_status.setText(
                    f"host-microbe {job.status.value}: {job.error or jid}"
                )
        self._finish_ranked_jobs("host_search", self._host_search_jobs, "host-search")
        self._finish_ranked_jobs("gene_ko", self._gene_ko_jobs, "gene KO search")
        self._finish_ranked_jobs("strain_growth", self._strain_growth_jobs, "strain growth")
        self._finish_ranked_jobs("ratio_impact", self._abundance_impact_jobs, "ratio impact")
        for jid, out_dir in list(self._dfba_jobs.items()):
            job = self.runner.poll(jid)
            if job.status in _ENDED and self._from_closed_project(out_dir):
                self._dfba_jobs.pop(jid, None)
                self.dynamics_view.run_dfba_btn.setEnabled(True)
            elif job.status is JobStatus.DONE:
                self._dfba_jobs.pop(jid, None)
                self.dynamics_view.run_dfba_btn.setEnabled(True)
                if self.load_dfba_dir(out_dir):
                    self._show_status("status_complete", kind=self.tr_map["kind_dfba"], job_id=jid)
                else:
                    self.dynamics_view._clear_dynamics(_UNREADABLE_RESULT.format(
                        kind="dFBA", out_dir=out_dir))
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._dfba_jobs.pop(jid, None)
                self.dynamics_view.run_dfba_btn.setEnabled(True)
                # A failed rerun must not leave the previous timecourse drawn under its message.
                self.dynamics_view._clear_dynamics(
                    f"dFBA {job.status.value}: {job.error or jid}"
                )
        for jid, out_dir in list(self._spatial_jobs.items()):
            job = self.runner.poll(jid)
            if job.status in _ENDED and self._from_closed_project(out_dir):
                self._spatial_jobs.pop(jid, None)
                self.spatial_page.run_btn.setEnabled(True)
            elif job.status is JobStatus.DONE:
                self._spatial_jobs.pop(jid, None)
                self.spatial_page.run_btn.setEnabled(True)
                if self.load_spatial_dir(out_dir):
                    self._show_status(
                        "status_complete", kind=self.tr_map["kind_spatial"], job_id=jid
                    )
                else:
                    self.spatial_page._clear_dynamics(_UNREADABLE_RESULT.format(
                        kind="spatial preview", out_dir=out_dir))
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._spatial_jobs.pop(jid, None)
                self.spatial_page.run_btn.setEnabled(True)
                self.spatial_page._clear_dynamics(
                    f"spatial preview {job.status.value}: {job.error or jid}"
                )
        for jid, out_dir in list(self._community_jobs.items()):
            job = self.runner.poll(jid)
            if job.status in _ENDED and self._from_closed_project(out_dir):
                self._community_jobs.pop(jid, None)
                self.community_builder.run_btn.setEnabled(True)
            elif job.status is JobStatus.DONE:
                self._community_jobs.pop(jid, None)
                self.community_builder.run_btn.setEnabled(True)
                manifest = (
                    (job.result or {}).get("manifest", {}) if isinstance(job.result, dict) else {}
                )
                run_hash = manifest.get("run_hash") if isinstance(manifest, dict) else None
                suffix = f" (run_hash {str(run_hash)[:12]})" if run_hash else ""
                if self.load_run_dir(out_dir):
                    self.community_builder.status.setText(f"community solve complete{suffix}")
                    self._show_status(
                        "status_complete",
                        kind=self.tr_map["kind_community_solve"],
                        job_id=jid,
                    )
                else:
                    self.community_builder.status.setText(_UNREADABLE_RESULT.format(
                        kind="community solve", out_dir=out_dir))
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._community_jobs.pop(jid, None)
                self.community_builder.run_btn.setEnabled(True)
                # A failed rerun must not leave the previous run drawn under its message.
                self.community_builder.results.show_empty()
                self.community_builder.status.setText(
                    f"community solve {job.status.value}: {job.error or jid}"
                )
        for jid, (out_dir, mode) in list(self._sweep_jobs.items()):
            job = self.runner.poll(jid)
            if job.status in _ENDED and self._from_closed_project(out_dir):
                self._sweep_jobs.pop(jid, None)
                self.sweep_view.run_btn.setEnabled(True)
            elif job.status is JobStatus.DONE:
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
                # Rows it wrote before failing are shown; none leaves no earlier sweep on show.
                self.sweep_view.load_results(rows)
                if rows:
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
        for jid, (out_dir, request) in list(self._medium_growth_jobs.items()):
            job = self.runner.poll(jid)
            if job.status in _ENDED and self._from_closed_project(out_dir):
                self._medium_growth_jobs.pop(jid, None)
                self.medium_editor.check_growth_btn.setEnabled(True)
            elif job.status is JobStatus.DONE and isinstance(job.result, dict):
                self._medium_growth_jobs.pop(jid, None)
                self.medium_editor.check_growth_btn.setEnabled(True)
                self._register_run_output(out_dir)
                growth = job.result.get("growth")
                status = str(job.result.get("status", "unknown"))
                mode_key = (
                    "medium_mode_exact" if request.get("exact") else "medium_mode_merge"
                )
                growth_text = "—" if growth is None else f"{float(growth):.6g}"
                self.medium_editor.growth_label.setText(
                    self._message(
                        "medium_growth_result",
                        growth=growth_text,
                        status=status,
                        mode=self.tr_map[mode_key],
                    )
                )
                dropped = [str(item) for item in job.result.get("dropped_ids", [])]
                self.medium_editor.dropped_ids_label.setText(
                    self.tr_map["medium_dropped_none"]
                    if not dropped
                    else self._message(
                        "medium_dropped_ids",
                        count=len(dropped),
                        ids=", ".join(dropped),
                    )
                )
                diagnostic = job.result.get("diagnostic")
                if diagnostic and not dropped:
                    self.medium_editor.dropped_ids_label.setText(
                        self._message("medium_diagnostic", diagnostic=diagnostic)
                    )

                previous = self._last_medium_growth_check
                if not self.load_run_dir(out_dir, host_key="medium"):
                    # The growth figure came from files the GUI could not read back: do not
                    # present it, and keep the failure in the status bar and the inspector.
                    self.medium_editor.growth_label.setText(_UNREADABLE_RESULT.format(
                        kind="growth check", out_dir=out_dir))
                    continue
                cli_succeeded = int(job.result.get("cli_rc", 1)) == 0 and status == "optimal"
                if cli_succeeded and previous is not None:
                    previous_dir, previous_request = previous
                    same_context = (
                        previous_request.get("models") == request.get("models")
                        and previous_request.get("exact") == request.get("exact")
                        and previous_request.get("namespace") == request.get("namespace")
                    )
                    medium_modified = previous_request.get("medium") != request.get("medium")
                    if same_context and medium_modified:
                        from cmig.core.delta import compute_delta

                        baseline = _solve_result_like_from_run_dir(previous_dir)
                        variant = _solve_result_like_from_run_dir(out_dir)
                        delta = compute_delta(baseline, variant)  # type: ignore[arg-type]
                        self.profile_view.show_delta_overlay(
                            delta,
                            baseline_label=self.tr_map["medium_profile_baseline"],
                            variant_label=self.tr_map["medium_profile_variant"],
                        )
                        self._medium_delta_active = True
                        self.medium_editor.profile_delta_label.setText(
                            self.tr_map["medium_profile_delta_active"]
                        )
                    elif not same_context:
                        self.medium_editor.profile_delta_label.setText(
                            self.tr_map["medium_profile_delta_ineligible"]
                        )
                if cli_succeeded:
                    self._last_medium_growth_check = (out_dir, request)
                    self._show_status(
                        "status_complete", kind=self.tr_map["kind_growth_check"], job_id=jid
                    )
                else:
                    self._show_status(
                        "medium_growth_failed",
                        status=status,
                        error=f"CLI rc={job.result.get('cli_rc')}; artifacts retained",
                    )
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._medium_growth_jobs.pop(jid, None)
                self.medium_editor.check_growth_btn.setEnabled(True)
                self._empty_community_result_on("medium")
                self.medium_editor.growth_label.setText(
                    self._message(
                        "medium_growth_failed",
                        status=job.status.value,
                        error=job.error or jid,
                    )
                )
        for jid, out_dir in list(self._minimal_medium_jobs.items()):
            job = self.runner.poll(jid)
            if job.status in _ENDED and self._from_closed_project(out_dir):
                self._minimal_medium_jobs.pop(jid, None)
                self.medium_editor.minimal_medium_btn.setEnabled(True)
            elif job.status is JobStatus.DONE and isinstance(job.result, dict):
                self._minimal_medium_jobs.pop(jid, None)
                self.medium_editor.minimal_medium_btn.setEnabled(True)
                self.medium_editor.load_minimal_result(job.result)
                self._register_run_output(out_dir)
                if int(job.result.get("cli_rc", 1)) == 0 and job.result.get("status") != "failed":
                    self._show_status(
                        "status_complete", kind=self.tr_map["kind_minimal_medium"], job_id=jid
                    )
                else:
                    self._show_status(
                        "medium_minimal_failed",
                        status=job.result.get("status", "failed"),
                        error=f"CLI rc={job.result.get('cli_rc')}; artifacts retained",
                    )
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._minimal_medium_jobs.pop(jid, None)
                self.medium_editor.minimal_medium_btn.setEnabled(True)
                self.medium_editor.minimal_status.setText(
                    self._message(
                        "medium_minimal_failed",
                        status=job.status.value,
                        error=job.error or jid,
                    )
                )
        self._show_search_cancel_pending()
        for jid in list(self.bridge.cancelling):
            if self.runner.poll(jid).status not in (JobStatus.PENDING, JobStatus.RUNNING):
                self.bridge.cancelling.discard(jid)
        if settled:
            self.session.refresh_runs()
        if self._just_finished:
            run_dir, error = self._just_finished[-1]
            self._just_finished.clear()
            self._show_last_run(run_dir, error)

    def _ranked_page(self, key: str) -> RankedPage:
        pages: dict[str, RankedPage] = {
            "search": self.search_view, "gene_ko": self.gene_ko_page,
            "strain_growth": self.strain_growth_page, "ratio_impact": self.ratio_impact_page,
            "host_search": self.host_search_page,
        }
        return pages[key]

    def _ranked_spec(self, key: str) -> tuple[str, Callable[[dict[str, Any]], dict[str, Any]],
                                              str, str]:
        """(summary file, adapter to the ranked table, workflow kind, status label key)."""
        return {
            "gene_ko": ("gene_ko_summary.json", _gene_ko_summary_for_search_view,
                        "gene_ko", "kind_gene_ko_search"),
            "strain_growth": ("strain_growth_summary.json",
                              _strain_growth_summary_for_search_view, "strain_growth",
                              "kind_strain_growth"),
            "ratio_impact": ("abundance_impact_summary.json",
                             _abundance_impact_summary_for_search_view, "abundance_impact",
                             "kind_ratio_impact"),
            "host_search": ("host_search_summary.json", _host_search_summary_for_search_view,
                            "host_search", "kind_host_search"),
        }[key]

    def _show_ranked(
        self, key: str, payload: dict[str, Any], out_dir: Path,
        requested: dict[str, str] | None,
    ) -> None:
        """Show a ranked result; `requested` None = the run's inputs are not known, so nothing
        is labelled as executed (the screen's inputs may belong to another run)."""
        _file, adapter, kind, _label = self._ranked_spec(key)
        page = self._ranked_page(key)
        panel = page.results_panel
        panel.figure_mode_combo.setCurrentText("Ranking")
        panel.load_summary(
            _with_search_conditions(adapter(payload), payload),
            run_dir=out_dir,
            request_note="" if requested is None else (
                panel.effective_note(requested, kind) + panel.superseded_note(requested, kind)
            ),
            workflow_kind=kind,
            executed_request=requested,
            source_summary=payload,
        )
        self._show_page(self.analysis_pages[key])

    def _finish_ranked_jobs(
        self, key: str, jobs: dict[str, tuple[Path, dict[str, str]]], failure_label: str
    ) -> None:
        page = self._ranked_page(key)
        for jid, (out_dir, requested) in list(jobs.items()):
            job = self.runner.poll(jid)
            if job.status in _ENDED and self._from_closed_project(out_dir):
                jobs.pop(jid, None)
                page.run_btn.setEnabled(True)
            elif job.status is JobStatus.DONE and isinstance(job.result, dict):
                jobs.pop(jid, None)
                page.run_btn.setEnabled(True)
                if self._inspect_gui_run(out_dir) is None:
                    self._clear_ranked(page)
                    page.status.setText(
                        _UNREADABLE_RESULT.format(kind=failure_label, out_dir=out_dir)
                    )
                    continue
                self.current_search_dir = out_dir
                self._show_ranked(key, job.result, out_dir, requested)
                self._register_run_output(out_dir)
                self._show_status("status_complete_out",
                                  kind=self.tr_map[self._ranked_spec(key)[3]],
                                  job_id=jid, out_dir=out_dir)
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                jobs.pop(jid, None)
                page.run_btn.setEnabled(True)
                # A failed rerun must not leave the previous ranking drawn under its message.
                self._clear_ranked(page)
                page.status.setText(
                    f"{failure_label} {job.status.value}: {job.error or jid}"
                )

    @staticmethod
    def _clear_ranked(page: RankedPage) -> None:
        """Drop a ranked page's shown result and empty its results area."""
        page.results_panel.invalidate_results()
        page.results.show_empty()


def _host_search_summary_for_search_view(payload: dict[str, Any]) -> dict[str, Any]:
    """Adapt host-search output to the existing SearchView ranking table contract."""
    target = str(payload.get("target", ""))
    rows: list[dict[str, Any]] = []
    for item in payload.get("top_ranked", []):
        if not isinstance(item, dict):
            continue
        interval = item.get("target_transfer_range")
        lo = hi = None
        if isinstance(interval, (list, tuple)) and len(interval) == 2:
            lo, hi = interval
        identifiability = str(item.get("target_identifiability", "unknown"))
        rows.append(
            {
                "members": item.get("members", []),
                "score": item.get("score"),
                "target_flux": item.get("target_transfer"),
                "community_growth": item.get("community_growth"),
                "status": (str(item.get("evaluation_status", item.get("host_status", "")))
                           + f" · transfer {identifiability}"),
                "diagnostic": item.get("diagnostic") or item.get("target_reason"),
                "robustness_fva_lo": lo,
                "robustness_fva_hi": hi,
            }
        )
    return {
        "target": target,
        "strategy": f"host-search/{payload.get('metric', '')}",
        "top_ranked": rows,
        # Forward CLI warnings verbatim — the GUI is not allowed to be quieter than the CLI.
        "warnings": list(payload.get("warnings") or []),
        "status": payload.get("status", "unknown"),
        "column_labels": [
            "Members",
            "Target",
            "Score",
            "Target transfer (mmol gDW⁻¹ h⁻¹)",
            "Community growth (h⁻¹)",
            "Transfer range",
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


def _medium_dropped_ids(manifest: dict[str, Any]) -> list[str]:
    """Extract every CLI-recorded ``medium_unapplied`` id from a solve manifest."""
    found: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (TypeError, ValueError):
                return
            visit(parsed)
            return
        if isinstance(value, dict):
            if value.get("code") == "medium_unapplied":
                detail = value.get("detail")
                if isinstance(detail, dict):
                    exchange_ids = detail.get("exchange_ids")
                    if isinstance(exchange_ids, list):
                        found.update(str(item) for item in exchange_ids)
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(manifest.get("diagnostic"))
    return sorted(found)


def build_main_window(runner: JobRunner | None = None, lang: str = "en") -> CmigMainWindow:
    """메인 윈도우 팩토리(offscreen 검증·진입점)."""
    return CmigMainWindow(runner=runner, lang=lang)
