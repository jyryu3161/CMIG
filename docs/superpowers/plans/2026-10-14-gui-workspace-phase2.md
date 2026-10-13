# GUI 작업 공간 개편 2단계 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 분석 화면을 화면 하나당 분석 하나로 나누고 같은 틀(입력 카드·Advanced·결과 영역)을 씌운다. 그 위에 실행 입력 복원, 모델 브라우저와 Check Growth, 모델별 namespace 확인, 전역 검색(⌘F), 결과 표시 개선, 키보드 선택기를 더한다.

**Architecture:**
- **Qt 없는 층**: `cmig/io/project.py`에 점검의 구조화 값, namespace 확인 기록, 실행 입력 기록(`runs/_inputs/<run>-request.json`), 설정 키 이전을 더한다. 새 `cmig/io/model_index.py`가 `models/.index/<sha256>.json` 색인을 맡는다.
- **GUI 공통 틀**: `cmig/gui/analysis_page.py`의 `AnalysisPage`를 모든 분석 화면이 쓴다. Search 계열 결과 위젯은 `cmig/gui/search_results.py`의 `SearchResultsPanel`로 떼어 내 여러 화면이 하나씩 갖는다.
- **실행 경로는 그대로**: CLI argv → `JobRunner` → `cmig.cli.main.main`. 화면을 옮기기 전에 argv 동일성 테스트를 먼저 고정한다.

**Tech Stack:** Python 3.10–3.12, PySide6(Qt 6), cobra(색인), pytest(offscreen Qt), `uv run --no-sync`.

**Spec:** `docs/superpowers/specs/2026-10-14-gui-workspace-phase2-design.md`

## Global Constraints

- GUI는 과학 계산을 하지 않는다. 모든 분석은 CLI argv → `JobRunner` → `cmig.cli.main.main`으로 실행한다. CLI 옵션, `run_hash`, envelope, manifest, tidy 스키마, golden은 바꾸지 않는다.
- 같은 입력이면 화면을 나누기 전과 똑같은 argv가 나와야 한다. `tests/test_phase2_argv_parity.py`의 `EXPECTED`는 Task 1 이후 어떤 작업도 고치지 않는다. 화면이 바뀌면 `tests/argv_drivers.py`의 입력 설정 방식만 고친다.
- 원본 GEM과 프로젝트 모델 사본은 수정하지 않는다. 프로젝트 폴더 밖에 쓰지 않는다. 파일 쓰기는 `cmig.io.atomic.atomic_write_text`로 한다.
- `cmig/io/project.py`와 `cmig/io/model_index.py`는 `cmig.gui`, `cmig.cli`, `cmig.service`, PySide6를 import하지 않는다.
- 프로젝트 형식은 `format_version: 1`을 유지한다. 새 필드는 모두 기본값이 있는 선택 항목이다. 1단계 프로젝트가 그대로 열려야 한다.
- 실패, 취소, 판독 실패, 성장 없음은 성공이나 0의 성장처럼 보이지 않는다. 다중 항 목적함수 값은 "Growth"로 부르지 않는다. Gurobi는 "Gurobi (full-flux)", OSQP는 "OSQP (QP-only approximate)"로 표기한다.
- namespace 확인은 사용자의 명시적 동작으로만 생긴다. 확인 기록의 `sha256`이 지금 파일과 다르거나 `integrity != "ok"`이면 무효다.
- 새 UI 문구는 영어로만 쓴다. `I18N` 새 키는 `"en"`과 `"ko"`에 같은 영어 문구로 넣는다.
- strict mypy(`graph_view.py` 제외), Ruff(line 100, `E,F,I,B,UP,TID`), pickle 금지
- main window 전체가 1280×800·1500×950을 넘어 강제로 커지면 안 된다.
- GUI 테스트는 `QT_QPA_PLATFORM=offscreen`에서 돌린다. 새 GUI 테스트 파일은 `from gui_project_helpers import _deterministic_qt_teardown`(autouse fixture)를 import한다. `tests/`에는 `__init__.py`가 없으니 `tests.` 접두 없이 import한다.
- 테스트 명령은 `uv run --no-sync pytest …`이다. 전체 pytest는 모든 테스트가 끝난 뒤 macOS에서 종료 코드 139로 끝나는 기존 문제가 있다. 판정은 마지막 요약 줄로 한다.
- 커밋은 기능 브랜치 `gui-workspace-phase2`에만 한다. 메시지 끝에 다음 두 줄을 붙인다:
  ```
  Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX
  ```

## Review Focus

1. 1단계 프로젝트를 열었을 때: 옛 `analysis_settings` 키(`search`, `dynamics`, `host`, `host_model`)의 기억된 선택이 새 화면에 이어지고, 구조화 값이 없는 모델 항목도 점검 이유가 올바르게 보여야 한다. → Task 2 `test_phase1_project_opens_with_migrated_settings`, Task 14 `test_legacy_entry_reason_from_warning_text`
2. 실행 기록(request.json)이 깨졌거나 다른 schema이거나 지금 없는 모델·배지를 가리킬 때: 앱이 멈추지 않고, 그 화면이 열리며, 배너가 이유를 말해야 한다. → Task 13 `test_corrupt_request_opens_page_with_banner`, `test_removed_model_named_in_banner`
3. 색인 파일이 깨졌거나 다른 모델 파일의 것이거나 쓰기 권한이 없을 때: 브라우저는 다시 만들거나 사유와 Retry를 보이고, 분석 입력에는 아무 영향이 없어야 한다. → Task 3 `test_corrupt_or_foreign_index_is_rejected`, Task 14 `test_index_failure_shows_retry_and_keeps_model_selectable`
4. 확인 기록이 있는 모델 파일이 바뀌었을 때: 확인이 무효가 되어 Check Growth가 거부되고, 분석 확인란이 미리 체크되지 않아야 한다. → Task 2 `test_confirmation_void_after_file_change`, Task 15 `test_changed_file_voids_pretick_and_check_growth`
5. 모델이 수백 개인 AGORA2 프로젝트에서 ⌘F 검색: 같은 대사체가 모델마다 반복 저장되지 않고, 묶음별 줄 수가 제한되며, 입력마다 화면이 멈추지 않아야 한다. → Task 16 `test_search_table_dedupes_across_models`, `test_find_caps_rows_and_reports_more`

---

## 파일 구조

| 파일 | 책임 |
|---|---|
| `cmig/io/project.py` | `ModelEntry`/`ModelCheck` 새 필드, `namespace_review_state`, `namespace_confirmed`, `confirm_namespace`, `revoke_namespace`, `confirmation_summary`, `check_reason`, 실행 입력 기록(`write_run_request`, `read_run_request`), `migrate_analysis_settings`, `rename_model` 보정, `add_model_file`의 색인 쓰기 |
| `cmig/io/model_import.py` | `load_and_summarize(path)` — 모델을 한 번 읽어 요약과 cobra 모델을 함께 돌려줌 |
| `cmig/io/model_index.py` (새) | 색인 만들기·쓰기·읽기(`index_from_model`, `write_index`, `load_index`, `build_index_file`, `search_rows`) |
| `cmig/gui/analysis_page.py` (새) | `AnalysisPage`, `AdvancedSection`, `ResultsArea`, `widget_value`, `set_widget_value`, `hide_row_numbers` |
| `cmig/gui/search_results.py` (새) | `SearchResultsPanel` — 순위 표·상세·후보 상세·Pareto·그림 |
| `cmig/gui/pages/__init__.py` (새) | 패키지 |
| `cmig/gui/pages/gene_ko.py`, `strain_growth.py`, `ratio_impact.py`, `host_search.py`, `spatial.py`, `tools.py` (새) | 나눈 분석 화면과 Tools 틀 |
| `cmig/gui/builder.py` | `SearchView`를 `AnalysisPage` 기반 Combination Search로, `CommunityBuilderView`를 멤버 표가 선택기를 따르는 화면으로 |
| `cmig/gui/host_view.py` | `HostImpactView`를 Host–Microbe 전용 화면으로, 공통 숙주 입력 `HostInputs` |
| `cmig/gui/views.py` | `DfbaSpatialView`를 dFBA 전용 화면으로 |
| `cmig/gui/sidebar.py` | `ANALYSIS_GROUPS`(네 묶음) |
| `cmig/gui/pickers.py` | 키보드 조작 |
| `cmig/gui/run_restore.py` (새) | 실행 → 화면 키(`analysis_for_run`), 복원 배너 문구 |
| `cmig/gui/model_browser.py` (새) | 모델 브라우저와 Check Growth 머리글 |
| `cmig/gui/growth.py` (새, Qt 없음) | Check Growth 결과 판독(`read_growth`), 최근 실행 찾기 |
| `cmig/gui/find.py` (새) | 검색 표·맞추기(Qt 없음 함수)와 검색 칸 위젯 |
| `cmig/gui/inspector.py`, `editors.py` | 모델 상세 문구, 선택 없음 요약, 모델 표 Check 이유 |
| `cmig/gui/project_session.py` | namespace 확인 Undo 명령, rename의 설정 스냅샷 |
| `cmig/gui/app.py` | 화면 등록·실행 연결·복원·Check Growth·검색·상태 표시줄 |
| `tests/argv_drivers.py`, `tests/test_phase2_argv_parity.py` (새) | argv 동일성 |
| `tests/test_project_phase2.py`, `tests/test_model_index.py` (새) | Qt 없는 단위 테스트 |
| `tests/test_phase2_*.py` (새) | GUI 테스트 |
| 문서 | `docs/USER_GUIDE.md`, `CHANGELOG.md`, `docs/tracking/status.md`, `docs/tracking/findings.md`, `cmig/gui/AGENTS.md`, `cmig/io/AGENTS.md` |

## 작업 간 공통 이름 (모든 작업이 이 이름을 그대로 쓴다)

- 화면 키(13개): `search`, `gene_ko`, `strain_growth`, `ratio_impact`, `community`, `host`, `host_search`, `dfba`, `spatial`, `medium`, `sweep`, `sandbox`, `compare`. Check Growth 실행의 분석 키는 `check_growth`(화면이 아니라 모델 브라우저).
- 창 속성: `w.search_view`(Combination Search), `w.gene_ko_page`, `w.strain_growth_page`, `w.ratio_impact_page`, `w.community_builder`, `w.host_view`(Host–Microbe), `w.host_search_page`, `w.dynamics_view`(dFBA), `w.spatial_page`, `w.medium_page`, `w.sweep_page`, `w.sandbox_page`, `w.compare_page`(Tools 틀; 안의 기존 위젯 `w.medium_editor`, `w.sweep_view`, `w.sandbox_view`, `w.scenario_compare`는 그대로), `w.model_browser`, `w.find_field`.
- `w.analysis_pages: dict[str, AnalysisPage]` — 키마다 서로 다른 화면.
- 모든 `AnalysisPage`: `run_btn`, `cancel_btn`, `status`(결과 영역 상태 줄과 같은 QLabel), `advanced`, `results`, `banner`, `snapshot()`, `restore(values)`, `show_banner(text)`, `clear_banner()`.
- 실행 폴더 종류 이름은 지금과 같다: `search`, `gene-ko`, `strain-growth`, `abundance-impact`, `community`, `host-microbe`, `host-search`, `dfba`, `spatial`, `medium-growth`, `minimal-medium`, `sweep`. 새로 `check-growth`.

---

### Task 0: 브랜치 준비

- [ ] **Step 1: 기능 브랜치 만들기**

Run:
```bash
cd /Users/jaeyongryu/Projects/CMIG && git status --short && git checkout -b gui-workspace-phase2
```
Expected: 작업 트리가 깨끗하고(`docs/superpowers/` 아래 새 문서 두 개만 untracked) 새 브랜치로 바뀐다.

- [ ] **Step 2: 설계·계획 문서 커밋**

```bash
git add docs/superpowers/specs/2026-10-14-gui-workspace-phase2-design.md docs/superpowers/plans/2026-10-14-gui-workspace-phase2.md
git commit -m "docs: GUI workspace phase 2 design and plan

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 1: argv 동일성 기준 테스트 (지금 코드 기준)

화면을 옮기기 전에 지금 GUI가 만드는 argv를 고정한다. `EXPECTED`는 계획을 쓸 때 지금 main(`d6a1d31`)에서 아래 드라이버로 실제로 뽑은 값이다. Constraint Sandbox는 CLI argv 없이 `EngineService`를 부르므로 대상에서 빠진다.

**Files:**
- Create: `tests/argv_drivers.py`
- Create: `tests/test_phase2_argv_parity.py`

**Interfaces:**
- Produces: `argv_drivers.DRIVERS: dict[str, Callable[[CmigMainWindow], str]]`, `test_phase2_argv_parity.normalize(argv, root)`. 이후 작업은 화면이 옮겨질 때 `DRIVERS`의 함수 본문만 고친다.

- [ ] **Step 1: 드라이버 작성**

`tests/argv_drivers.py`:
```python
"""Set each analysis' inputs through the GUI and start it; the argv parity test records argv.

Only this file changes when a page moves (phase 2): the expected argv in
test_phase2_argv_parity.py must not.
"""

from __future__ import annotations

from typing import Any


def search_default(w: Any) -> str:
    v = w.search_view
    v.model_picker.set_selected(["a", "b"])
    v.medium_picker.set_ref("preset:western_diet")
    return w.run_search_fixture()


def search_advanced(w: Any) -> str:
    v = w.search_view
    v.model_picker.set_selected(["a", "b", "host"])
    v.set_target_rows([["but", "max_secretion", "1", "2"], ["ac", "max_secretion", "2", "3"]])
    v.multi_metric_combo.setCurrentText("raw_sum")
    v.min_size_spin.setValue(1)
    v.max_size_spin.setValue(3)
    v.strategy_combo.setCurrentText("exhaustive")
    v.search_top_k_spin.setValue(5)
    v.seed_spin.setValue(7)
    v.growth_fraction_spin.setValue(0.25)
    v.min_member_growth_spin.setValue(0.01)
    v.validation_top_spin.setValue(2)
    return w.run_search_fixture()


def gene_ko(w: Any) -> str:
    v = w.search_view
    v.model_picker.set_selected(["a", "b", "host"])
    v.medium_picker.set_ref("preset:high_fiber")
    v.set_target_rows([["ac", "min_uptake", "1", ""]])
    v.ko_members_input.setText("a,b")
    v.ko_member_input.setText("a")
    v.ko_max_genes_spin.setValue(10)
    v.ko_top_k_spin.setValue(5)
    v.growth_fraction_spin.setValue(0.3)
    return w.run_gene_ko_search()


def strain_growth(w: Any) -> str:
    v = w.search_view
    v.model_picker.set_selected(["a", "b"])
    v.medium_picker.set_ref("preset:high_fiber")
    v.cooperative_tradeoff_spin.setValue(0.4)
    return w.run_strain_growth_report()


def ratio_impact(w: Any) -> str:
    v = w.search_view
    v.model_picker.set_selected(["a", "b"])
    v.set_target_rows([["but", "max_secretion", "1", ""]])
    v.growth_member_input.setText("b")
    v.abundance_fractions_input.setText("0.2,0.8")
    v.cooperative_tradeoff_spin.setValue(0.6)
    return w.run_abundance_impact()


def community(w: Any) -> str:
    v = w.community_builder
    v.model_picker.set_selected(["a", "b"])
    v.add_member("a", 0.25)
    v.assume_bigg_check.setChecked(True)
    v.f_slider.setValue(30)
    return w.run_community_solve()


def _host_common(v: Any) -> None:
    v.host_picker.set_selected(["host"])
    v.model_picker.set_selected(["a", "b"])
    v.host_medium_picker.set_ref("preset:western_diet")
    v.biomass_basis_kind_combo.setCurrentText("measured")
    v.biomass_basis_source_input.setText("lab record 12")
    v.microbial_biomass_spin.setValue(0.5)
    v.host_biomass_spin.setValue(10.0)
    v.tradeoff_spin.setValue(0.7)
    v.keep_host_uptake_check.setChecked(True)


def host(w: Any) -> str:
    _host_common(w.host_view)
    return w.run_host_microbe_bigg()


def host_search(w: Any) -> str:
    v = w.host_view
    _host_common(v)
    v.search_target_input.setText("but")
    v.search_metric_combo.setCurrentText("objective_value")
    v.min_size_spin.setValue(1)
    v.max_size_spin.setValue(2)
    return w.run_host_search_bigg()


def dfba(w: Any) -> str:
    v = w.dynamics_view
    v.model_picker.set_selected(["a"])
    v.initial_input.setText("EX_glc__D_e=5,EX_o2_e=10")
    v.t_end_spin.setValue(2.0)
    v.dt_spin.setValue(0.05)
    v.biomass_spin.setValue(0.02)
    v.close_untracked_check.setChecked(True)
    return w.run_dfba()


def spatial(w: Any) -> str:
    v = w.dynamics_view
    v.spatial_metabolite_input.setText("EX_ac_e")
    v.grid_size_spin.setValue(16)
    v.steps_spin.setValue(10)
    v.spatial_dt_spin.setValue(0.2)
    v.diffusion_spin.setValue(0.3)
    v.source_combo.setCurrentText("top")
    v.sink_combo.setCurrentText("bottom")
    return w.run_spatial_preview()


def medium_growth(w: Any) -> str:
    v = w.medium_editor
    v.model_picker.set_selected(["a", "b"])
    v.clear_rows()
    v.add_row("EX_glc__D_e", 10.0)
    v.exact_medium_check.setChecked(True)
    v.assume_bigg_check.setChecked(True)
    return w.run_medium_growth_check()


def minimal_medium(w: Any) -> str:
    v = w.medium_editor
    v.single_model_picker.set_selected(["a"])
    v.clear_rows()
    v.add_row("EX_glc__D_e", 10.0)
    v.assume_bigg_check.setChecked(True)
    v.min_growth_spin.setValue(0.1)
    return w.run_minimal_medium()


def sweep(w: Any) -> str:
    v = w.sweep_view
    v.model_picker.set_selected(["a", "b"])
    v.tradeoff_fs_input.setText("0.2,0.4")
    v.assume_bigg_check.setChecked(True)
    v.fva_check.setChecked(True)
    return w.run_sweep()


DRIVERS = {
    "search_default": search_default,
    "search_advanced": search_advanced,
    "gene_ko": gene_ko,
    "strain_growth": strain_growth,
    "ratio_impact": ratio_impact,
    "community": community,
    "host": host,
    "host_search": host_search,
    "dfba": dfba,
    "spatial": spatial,
    "medium_growth": medium_growth,
    "minimal_medium": minimal_medium,
    "sweep": sweep,
}
```

- [ ] **Step 2: 동일성 테스트 작성**

`tests/test_phase2_argv_parity.py`:
```python
"""Phase 2 moves every analysis input to a new page; the CLI argv must not change.

EXPECTED was recorded from main d6a1d31 (before phase 2) with tests/argv_drivers.py.
Never edit EXPECTED: when a page moves, change only the driver.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from argv_drivers import DRIVERS  # noqa: E402
from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.editors import installed_medium_preset_path  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402

APP = QApplication.instance() or QApplication([])
_STAMP = re.compile(r"-\d{8}-\d{6}(?:-\d+)?")


def normalize(argv: list[str], root: Path) -> list[str]:
    presets = str(installed_medium_preset_path("western_diet").parent)
    return [
        _STAMP.sub("-<STAMP>", a.replace(presets, "<PRESETS>").replace(str(root), "<P>"))
        for a in argv
    ]


<EXPECTED 블록: 아래 Step 3에서 붙인다>


@pytest.mark.parametrize("name", sorted(DRIVERS))
def test_argv_unchanged(name: str, tmp_path: Path, monkeypatch) -> None:
    make_project(tmp_path / "p", ["a", "b", "host"])
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(tmp_path / "p")
    calls: list[list[str]] = []

    def recorder(argv: list[str]) -> int:
        calls.append(list(argv))
        return 2

    monkeypatch.setattr("cmig.cli.main.main", recorder)
    try:
        job = DRIVERS[name](w)
        assert job, f"{name}: the page refused to run"
        deadline = time.time() + 10
        while not calls and time.time() < deadline:
            APP.processEvents()
            time.sleep(0.02)
        w._poll_completed_jobs()
        assert calls, f"{name}: no CLI call"
        assert normalize(calls[0], w.session.require().root) == EXPECTED[name]
    finally:
        w.close_project()
```

- [ ] **Step 3: `EXPECTED` 붙이기**

`<EXPECTED 블록…>` 줄을 아래 내용으로 바꾼다(그대로 복사):
```python
EXPECTED: dict[str, list[str]] = {
    "search_default": [
        "search", "--taxonomy", "<P>/runs/_inputs/search-<STAMP>-taxonomy.csv", "--target", "but",
        "--direction", "max_secretion", "--strategy", "auto", "--min-size", "2", "--max-size", "2",
        "--top-k", "10", "--seed", "0", "--workers", "1", "--solver-threads", "1",
        "--growth-fraction", "0.5", "--min-member-growth", "0.0", "--min-community-growth", "0.0",
        "--validate-top", "0", "--exhaustive-max", "100", "--ga-pop-size", "30",
        "--ga-generations", "20", "--ga-mutation-rate", "0.2", "--ga-immigrant-fraction", "0.1",
        "--ga-tournament-k", "3", "--ga-elitism", "2", "--ga-local-search-fraction", "0.0",
        "--medium", "<PRESETS>/western_diet.csv", "--exact-medium", "--out",
        "<P>/runs/search-<STAMP>",
    ],
    "search_advanced": [
        "search", "--taxonomy", "<P>/runs/_inputs/search-<STAMP>-taxonomy.csv", "--targets",
        "but,ac", "--target-directions", "max_secretion,max_secretion", "--target-weights", "1,2",
        "--target-scales", "but=2,ac=3", "--multi-metric", "raw_sum", "--strategy", "exhaustive",
        "--min-size", "1", "--max-size", "3", "--top-k", "5", "--seed", "7", "--workers", "1",
        "--solver-threads", "1", "--growth-fraction", "0.25", "--min-member-growth", "0.01",
        "--min-community-growth", "0.0", "--validate-top", "2", "--out", "<P>/runs/search-<STAMP>",
    ],
    "gene_ko": [
        "gene-ko-search", "--taxonomy", "<P>/runs/_inputs/gene-ko-<STAMP>-taxonomy.csv",
        "--members", "a,b", "--target", "ac", "--max-genes", "10", "--top-k", "5", "--direction",
        "min_uptake", "--growth-fraction", "0.3", "--out", "<P>/runs/gene-ko-<STAMP>", "--medium",
        "<PRESETS>/high_fiber.csv", "--exact-medium", "--member", "a",
    ],
    "strain_growth": [
        "strain-growth", "--taxonomy", "<P>/runs/_inputs/strain-growth-<STAMP>-taxonomy.csv",
        "--tradeoff-f", "0.4", "--single-medium", "community", "--out",
        "<P>/runs/strain-growth-<STAMP>", "--medium", "<PRESETS>/high_fiber.csv", "--exact-medium",
    ],
    "ratio_impact": [
        "abundance-impact", "--taxonomy", "<P>/runs/_inputs/abundance-impact-<STAMP>-taxonomy.csv",
        "--member", "b", "--fractions", "0.2,0.8", "--target", "but", "--tradeoff-f", "0.6",
        "--out", "<P>/runs/abundance-impact-<STAMP>",
    ],
    "community": [
        "solve", "--taxonomy", "<P>/runs/_inputs/community-<STAMP>-taxonomy.csv", "--tradeoff-f",
        "0.3", "--out", "<P>/runs/community-<STAMP>", "--assume-bigg-namespace",
    ],
    "host": [
        "host-microbe-bigg", "--host", "<P>/models/host.xml", "--taxonomy",
        "<P>/runs/_inputs/host-microbe-<STAMP>-taxonomy.csv", "--tradeoff-f", "0.7",
        "--microbial-biomass-gdw", "0.5", "--host-biomass-gdw", "10", "--biomass-basis-kind",
        "measured", "--biomass-basis-source", "lab record 12", "--out",
        "<P>/runs/host-microbe-<STAMP>", "--keep-host-uptake", "--host-medium",
        "<PRESETS>/western_diet.csv",
    ],
    "host_search": [
        "host-search-bigg", "--host", "<P>/models/host.xml", "--taxonomy",
        "<P>/runs/_inputs/host-search-<STAMP>-taxonomy.csv", "--target", "but", "--metric",
        "objective_value", "--min-size", "1", "--max-size", "2", "--tradeoff-f", "0.7",
        "--microbial-biomass-gdw", "0.5", "--host-biomass-gdw", "10", "--biomass-basis-kind",
        "measured", "--biomass-basis-source", "lab record 12", "--out",
        "<P>/runs/host-search-<STAMP>", "--keep-host-uptake", "--host-medium",
        "<PRESETS>/western_diet.csv",
    ],
    "dfba": [
        "dfba", "--model", "<P>/models/a.xml", "--initial", "EX_glc__D_e=5,EX_o2_e=10", "--t-end",
        "2", "--dt", "0.05", "--initial-biomass", "0.02", "--out", "<P>/runs/dfba-<STAMP>",
        "--close-untracked-uptake",
    ],
    "spatial": [
        "spatial-preview", "--metabolite", "EX_ac_e", "--width", "16", "--height", "16", "--steps",
        "10", "--dt", "0.2", "--diffusion", "0.3", "--source-edge", "top", "--sink-edge", "bottom",
        "--out", "<P>/runs/spatial-<STAMP>",
    ],
    "medium_growth": [
        "solve", "--taxonomy", "<P>/runs/_inputs/medium-growth-<STAMP>-taxonomy.csv", "--out",
        "<P>/runs/medium-growth-<STAMP>", "--assume-bigg-namespace", "--medium",
        "<P>/runs/_inputs/medium-growth-<STAMP>-medium.json", "--exact-medium",
    ],
    "minimal_medium": [
        "minimal-medium", "--model", "<P>/models/a.xml", "--min-growth", "0.1", "--oxygen-mode",
        "aerobic", "--out", "<P>/runs/minimal-medium-<STAMP>", "--assume-bigg-namespace",
        "--medium", "<P>/runs/_inputs/minimal-medium-<STAMP>-medium.json",
    ],
    "sweep": [
        "sweep", "--taxonomy", "<P>/runs/_inputs/sweep-<STAMP>-taxonomy.csv", "--tradeoff-fs",
        "0.2,0.4", "--solvers", "gurobi", "--metric", "growth", "--out", "<P>/runs/sweep-<STAMP>",
        "--assume-bigg-namespace", "--fva",
    ],
}
```

- [ ] **Step 4: 지금 코드에서 통과 확인**

Run: `uv run --no-sync pytest tests/test_phase2_argv_parity.py -q`
Expected: 13 passed. 하나라도 다르면 `EXPECTED`를 고치지 말고 드라이버가 계획과 같은지 확인한다(계획의 값은 `d6a1d31`에서 뽑았다). main이 그 사이 바뀌어 차이가 나면 멈추고 보고한다.

- [ ] **Step 5: Commit**

```bash
git add tests/argv_drivers.py tests/test_phase2_argv_parity.py
git commit -m "test(gui): pin the CLI argv of every analysis before the page split

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 2: 프로젝트 형식 확장 — 점검 구조화 값, namespace 확인, 점검 이유, 실행 입력 기록, 설정 키 이전, rename 보정

**Files:**
- Modify: `cmig/io/project.py` (`ModelEntry`, `ModelCheck`, `check_model_file`, `apply_check`, `open_project`, `rename_model`, 새 함수들)
- Modify: `cmig/gui/project_session.py` (`_RenameModel` 설정 스냅샷, `_SetNamespaceConfirmation`, `confirm_namespace`, `revoke_namespace`)
- Modify: `tests/gui_project_helpers.py` (`textbook_sbml`)
- Create: `tests/test_project_phase2.py`
- Modify: `tests/test_workspace_session.py` (확인 Undo, rename 스냅샷 테스트 추가)

**Interfaces:**
- Produces (`cmig.io.project`):
  - `ModelEntry` 새 필드: `namespace_mappings: dict[str, int] | None = None`(`total`, `resolved`, `unresolved_high`, `warned_low`), `objective_warning: str | None = None`, `namespace_confirmed: dict[str, str] | None = None`(`sha256`, `at`)
  - `ModelCheck` 새 필드(모두 기본값): `namespace_mappings`, `objective_warning`, `index: dict[str, Any] | None`(Task 3이 채움, 저장 안 함)
  - `namespace_review_state(entry) -> str` — `"blocked" | "review" | "clear" | "unknown"`
  - `objective_warning_of(entry) -> str | None`
  - `confirmation_state(entry) -> str` — `"confirmed" | "changed" | "none"`
  - `namespace_confirmed(entry) -> bool`
  - `confirm_namespace(project, model_id, *, at: str | None = None) -> None`, `revoke_namespace(project, model_id) -> None`
  - `confirmation_summary(project, ids) -> tuple[bool, list[str]]` — (모두 확인됨, 확인 안 된 id)
  - `check_reasons(entry) -> list[tuple[str, str]]` (나쁜 순), `check_reason(entry) -> tuple[str, str]`
  - `REQUEST_SCHEMA_VERSION = 1`, `run_request_path(run_dir) -> Path`, `write_run_request(run_dir, analysis, values, *, models, media, cmig_version) -> Path`, `read_run_request(run_dir) -> tuple[dict[str, Any] | None, str]`
  - `migrate_analysis_settings(settings) -> dict[str, dict[str, object]]`
- Produces (`ProjectSession`): `confirm_namespace(model_id) -> None`, `revoke_namespace(model_id) -> None` (Undo 가능, 저장 실패 시 되돌림)

- [ ] **Step 1: 테스트 도우미 추가**

`tests/gui_project_helpers.py` 끝에 추가:
```python
def textbook_sbml(path: Path) -> Path:
    """cobra's bundled e_coli_core ("textbook") written as SBML at `path` (no network)."""
    import cobra

    path.parent.mkdir(parents=True, exist_ok=True)
    cobra.io.write_sbml_model(cobra.io.load_model("textbook"), str(path))
    return path
```

- [ ] **Step 2: 실패하는 단위 테스트 작성**

`tests/test_project_phase2.py`:
```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from gui_project_helpers import make_project, textbook_sbml

from cmig.io import project as proj


def test_check_records_structured_namespace_and_objective(tmp_path: Path) -> None:
    check = proj.check_model_file(textbook_sbml(tmp_path / "textbook.xml"))
    assert check.namespace_mappings == {
        "total": 20, "resolved": 0, "unresolved_high": 20, "warned_low": 0,
    }
    assert check.objective_warning is None  # one biomass term


def test_apply_check_copies_structured_values(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    entry = proj.add_model_file(project, textbook_sbml(tmp_path / "src" / "t.xml"))
    assert entry.namespace_mappings is not None and entry.namespace_mappings["total"] == 20
    proj.save_project(project)
    again = proj.open_project(project.root).model(entry.id)
    assert again.namespace_mappings == entry.namespace_mappings
    assert again.objective_warning is None


def _entry(**overrides: object) -> proj.ModelEntry:
    base: dict[str, object] = dict(
        id="m", file="models/m.xml", source_path="/x/m.xml", sha256="abc", format="xml",
        added="t", status="warning", biomass=["BIOMASS_X"],
        warnings=["20 unresolved high-confidence namespace mappings block solve"],
    )
    base.update(overrides)
    return proj.ModelEntry(**base)  # type: ignore[arg-type]


def test_namespace_state_from_structured_values_or_legacy_text() -> None:
    assert proj.namespace_review_state(_entry()) == "blocked"  # legacy: from warning text
    assert proj.namespace_review_state(_entry(warnings=[])) == "clear"
    assert proj.namespace_review_state(
        _entry(namespace_mappings={"total": 3, "resolved": 1, "unresolved_high": 0,
                                   "warned_low": 2})
    ) == "review"
    assert proj.namespace_review_state(_entry(status="failed")) == "unknown"


def test_confirm_and_revoke(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a"])
    entry = project.model("a")
    assert proj.confirmation_state(entry) == "none"
    proj.confirm_namespace(project, "a", at="2026-10-14T00:00:00+00:00")
    assert entry.namespace_confirmed == {"sha256": entry.sha256,
                                         "at": "2026-10-14T00:00:00+00:00"}
    assert proj.namespace_confirmed(entry)
    proj.revoke_namespace(project, "a")
    assert entry.namespace_confirmed is None


def test_confirmation_void_after_file_change(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a", "b"])
    proj.confirm_namespace(project, "a")
    proj.confirm_namespace(project, "b")
    assert proj.confirmation_summary(project, ["a", "b"]) == (True, [])
    (project.root / project.model("b").file).write_text("<sbml id='edited'/>")
    proj.verify_checksums(project)
    assert proj.confirmation_state(project.model("b")) == "changed"
    assert proj.confirmation_summary(project, ["a", "b"]) == (False, ["b"])
    with pytest.raises(proj.ProjectError):
        proj.confirm_namespace(project, "b")  # a changed copy cannot be confirmed


def test_confirmation_summary_of_nothing_is_not_all_confirmed(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a"])
    assert proj.confirmation_summary(project, []) == (False, [])


def test_check_reasons_worst_first() -> None:
    assert proj.check_reason(_entry(status="failed")) == ("✗", "Unreadable")
    assert proj.check_reason(_entry(integrity="changed")) == ("⚠", "File changed")
    assert proj.check_reason(_entry(integrity="missing")) == ("⚠", "File missing")
    assert proj.check_reason(_entry()) == ("⚠", "Namespace not reviewed")
    assert proj.check_reason(_entry(warnings=[], biomass=[])) == ("⚠", "No objective")
    many = [f"R{i}" for i in range(283)]
    assert proj.check_reason(_entry(warnings=[], biomass=many)) == (
        "⚠", "Objective is not growth"
    )
    assert proj.check_reason(_entry(warnings=[])) == ("✓", "Ready")
    confirmed = _entry(namespace_confirmed={"sha256": "abc", "at": "t"})
    assert proj.check_reason(confirmed) == ("✓", "Ready · namespace confirmed")
    both = _entry(biomass=[])
    assert [text for _s, text in proj.check_reasons(both)] == [
        "Namespace not reviewed", "No objective",
    ]


def test_run_request_round_trip(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "search-20261014-101010"
    run_dir.mkdir(parents=True)
    path = proj.write_run_request(
        run_dir, "search", {"min_size": 2, "models": ["a", "b"]},
        models=["a", "b"], media=["preset:western_diet"], cmig_version="0.3.0",
    )
    assert path == tmp_path / "runs" / "_inputs" / "search-20261014-101010-request.json"
    payload, problem = proj.read_run_request(run_dir)
    assert problem == ""
    assert payload is not None
    assert payload["analysis"] == "search" and payload["values"]["min_size"] == 2
    assert payload["schema_version"] == proj.REQUEST_SCHEMA_VERSION
    assert payload["models"] == ["a", "b"] and payload["cmig_version"] == "0.3.0"


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        ("{not json", "could not be read"),
        (json.dumps({"schema_version": 9, "analysis": "search", "values": {}}), "schema 9"),
        (json.dumps({"schema_version": 1, "analysis": 3, "values": {}}), "malformed"),
        (json.dumps([1, 2]), "malformed"),
    ],
)
def test_bad_run_request_is_a_problem_not_an_exception(
    tmp_path: Path, text: str, needle: str
) -> None:
    run_dir = tmp_path / "runs" / "search-1"
    run_dir.mkdir(parents=True)
    proj.run_request_path(run_dir).parent.mkdir(parents=True)
    proj.run_request_path(run_dir).write_text(text)
    payload, problem = proj.read_run_request(run_dir)
    assert payload is None and needle in problem


def test_missing_run_request_is_no_record(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "dfba-1"
    run_dir.mkdir(parents=True)
    assert proj.read_run_request(run_dir) == (None, "")


def test_unserialisable_request_is_refused(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "x-1"
    run_dir.mkdir(parents=True)
    with pytest.raises(proj.ProjectError):
        proj.write_run_request(run_dir, "x", {"bad": object()}, models=[], media=[],
                               cmig_version="0")


def test_migrate_analysis_settings() -> None:
    old = {
        "search": {"models": ["a"], "medium": "preset:western_diet"},
        "dynamics": {"models": ["b"]},
        "host": {"models": ["a"], "host_medium": "preset:high_fiber"},
        "host_model": {"models": ["h"]},
        "growth": {"models": ["c"]},
        "community": {"models": ["a", "b"]},
    }
    new = proj.migrate_analysis_settings(old)
    assert new["gene_ko"] == new["search"] == {"models": ["a"], "medium": "preset:western_diet"}
    assert new["strain_growth"] == {"models": ["a"], "medium": "preset:western_diet"}
    assert new["ratio_impact"] == {"models": ["a"], "medium": "preset:western_diet"}
    assert new["dfba"] == {"models": ["b"]}
    assert new["host_search"] == {"models": ["a"], "host_medium": "preset:high_fiber"}
    assert new["host_search_model"] == {"models": ["h"]}
    assert new["community"] == {"models": ["a", "b"]}
    assert "dynamics" not in new and "growth" not in new
    new["gene_ko"]["models"].append("z")
    assert new["search"]["models"] == ["a"], "copies, not shared lists"


def test_phase1_project_opens_with_migrated_settings(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a", "b"])
    project.analysis_settings = {"search": {"models": ["a"]}, "dynamics": {"models": ["b"]}}
    proj.save_project(project)
    again = proj.open_project(project.root)
    assert again.analysis_settings["gene_ko"] == {"models": ["a"]}
    assert again.analysis_settings["dfba"] == {"models": ["b"]}
    assert "dynamics" not in again.analysis_settings


def test_rename_onto_removed_remembered_id_drops_the_stale_id(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a", "b"])
    project.analysis_settings["search"] = {"models": ["a", "b"]}
    proj.remove_model(project, "a")  # "a" stays remembered, as phase 1 keeps it
    proj.rename_model(project, "b", "a")
    assert project.analysis_settings["search"]["models"] == ["a"]  # the renamed b, once
```

- [ ] **Step 3: 실패 확인**

Run: `uv run --no-sync pytest tests/test_project_phase2.py -q`
Expected: FAIL — `AttributeError`/`TypeError`(새 필드·함수 없음).

- [ ] **Step 4: `cmig/io/project.py` 구현**

1. `ModelEntry` 끝(`integrity` 다음)에 필드 세 개를 더한다:
```python
    namespace_mappings: dict[str, int] | None = None
    objective_warning: str | None = None
    namespace_confirmed: dict[str, str] | None = None
```
2. `ModelCheck`(frozen dataclass) 끝에 더한다:
```python
    namespace_mappings: dict[str, int] | None = None
    objective_warning: str | None = None
    #: the model index built from the same read (Task 3); never saved in the project file
    index: dict[str, Any] | None = field(default=None, repr=False, compare=False)
```
3. `check_model_file`의 성공 경로를 바꾼다(실패 경로는 그대로):
```python
    warnings = [str(w) for w in review.warnings]
    coverage = review.namespace.get("coverage_pct")
    decisions = review.namespace.get("decisions") or []
    mappings = {
        "total": int(review.namespace.get("n_decisions", len(decisions))),
        "resolved": sum(1 for d in decisions if d.get("status") == "resolved"),
        "unresolved_high": int(review.namespace.get("n_unresolved_high", 0)),
        "warned_low": int(review.namespace.get("n_warned_low", 0)),
    }
    objective_warning = review.model.get("objective_warning")
    return ModelCheck(
        status="warning" if warnings else "ok",
        error=None,
        n_reactions=summary.n_reactions,
        n_metabolites=summary.n_metabolites,
        n_genes=summary.n_genes,
        biomass=list(summary.biomass_reactions),
        namespace_coverage_pct=None if coverage is None else float(coverage),
        warnings=warnings,
        namespace_mappings=mappings,
        objective_warning=None if objective_warning is None else str(objective_warning),
    )
```
4. `apply_check` 끝에 더한다:
```python
    entry.namespace_mappings = None if check.namespace_mappings is None else dict(
        check.namespace_mappings
    )
    entry.objective_warning = check.objective_warning
```
5. `rename_model`의 설정 갱신 루프를 바꾼다. `new_id`는 지금 어떤 모델의 id도 아니므로(검증 통과) 기억 목록에 있는 `new_id`는 제거된 모델의 흔적이다:
```python
    entry.id = new_id
    for values in project.analysis_settings.values():
        chosen = values.get("models")
        if isinstance(chosen, list):
            # `new_id` names no current model (checked above): a remembered `new_id` is a
            # removed model's leftover, and must not start meaning the renamed one.
            kept = [item for item in chosen if item != new_id]
            values["models"] = [new_id if item == model_id else item for item in kept]
```
6. `open_project`에서 `analysis_settings=settings`를 `analysis_settings=migrate_analysis_settings(settings)`로 바꾼다.
7. 파일 끝에 새 함수들을 더한다:
```python
# ── namespace review and the user's per-model confirmation ─────────────────────────────────
_NS_BLOCKED_TEXT = "unresolved high-confidence namespace mappings block solve"
_NS_REVIEW_TEXT = "low-confidence normalized candidates require review"


def namespace_review_state(entry: ModelEntry) -> str:
    """"blocked" | "review" | "clear" | "unknown" from the import review of this copy.

    Phase-1 entries carry no structured counts; their state is read once from the warning
    text `cmig.io.model_import.build_import_review` wrote.
    """
    counts = entry.namespace_mappings
    if counts is not None:
        if int(counts.get("unresolved_high", 0)) > 0:
            return "blocked"
        return "review" if int(counts.get("warned_low", 0)) > 0 else "clear"
    if entry.status not in _RUNNABLE_STATUSES:
        return "unknown"
    text = " ".join(entry.warnings)
    if _NS_BLOCKED_TEXT in text:
        return "blocked"
    return "review" if _NS_REVIEW_TEXT in text else "clear"


def objective_warning_of(entry: ModelEntry) -> str | None:
    """Why this model's objective is not a growth rate, or None (also for phase-1 entries)."""
    if entry.objective_warning is not None:
        return entry.objective_warning
    if not entry.biomass:
        return None
    from cmig.io.model_import import objective_structure_warning

    return objective_structure_warning(len(entry.biomass), entry.biomass)


def confirmation_state(entry: ModelEntry) -> str:
    """"confirmed" (this exact file), "changed" (confirmed for another file) or "none"."""
    record = entry.namespace_confirmed
    if not isinstance(record, dict):
        return "none"
    if record.get("sha256") == entry.sha256 and entry.integrity == "ok":
        return "confirmed"
    return "changed"


def namespace_confirmed(entry: ModelEntry) -> bool:
    return confirmation_state(entry) == "confirmed"


def confirm_namespace(project: Project, model_id: str, *, at: str | None = None) -> None:
    """Record the user's confirmation that this copy's exchange ids are BiGG (caller saves)."""
    entry = project.model(model_id)
    state = refresh_integrity(project, entry)
    if state != "ok":
        reason = "changed since it was added" if state == "changed" else "is missing"
        raise ProjectError(f"model {model_id!r} cannot be confirmed: its file {reason}")
    entry.namespace_confirmed = {"sha256": entry.sha256, "at": at or _now()}


def revoke_namespace(project: Project, model_id: str) -> None:
    project.model(model_id).namespace_confirmed = None


def confirmation_summary(project: Project, ids: list[str]) -> tuple[bool, list[str]]:
    """(every id confirmed, the ids that are not). No ids is never "all confirmed"."""
    unconfirmed = [i for i in ids if not namespace_confirmed(project.model(i))]
    return bool(ids) and not unconfirmed, unconfirmed


def check_reasons(entry: ModelEntry) -> list[tuple[str, str]]:
    """Every reason this model is not plainly ready, worst first; ("✓", …) when there is none."""
    if entry.status == "failed":
        return [("✗", "Unreadable")]
    if entry.status == "pending":
        return [("…", "Checking")]
    reasons: list[tuple[str, str]] = []
    if entry.integrity == "changed":
        reasons.append(("⚠", "File changed"))
    elif entry.integrity == "missing":
        reasons.append(("⚠", "File missing"))
    confirmed = namespace_confirmed(entry)
    if namespace_review_state(entry) in ("blocked", "review") and not confirmed:
        reasons.append(("⚠", "Namespace not reviewed"))
    if not entry.biomass:
        reasons.append(("⚠", "No objective"))
    elif objective_warning_of(entry):
        reasons.append(("⚠", "Objective is not growth"))
    if reasons:
        return reasons
    return [("✓", "Ready · namespace confirmed" if confirmed else "Ready")]


def check_reason(entry: ModelEntry) -> tuple[str, str]:
    return check_reasons(entry)[0]


# ── the GUI's record of a run's on-screen inputs (never part of the CLI's run folder) ──────
REQUEST_SCHEMA_VERSION = 1


def run_request_path(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    return run_dir.parent / "_inputs" / f"{run_dir.name}-request.json"


def write_run_request(
    run_dir: Path,
    analysis: str,
    values: dict[str, Any],
    *,
    models: list[str],
    media: list[str],
    cmig_version: str,
) -> Path:
    payload = {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "analysis": analysis,
        "values": values,
        "models": list(models),
        "media": list(media),
        "created": _now(),
        "cmig_version": cmig_version,
    }
    try:
        text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    except (TypeError, ValueError) as exc:
        raise ProjectError(f"cannot record the inputs of {Path(run_dir).name}: {exc}") from exc
    path = run_request_path(run_dir)
    try:
        atomic_write_text(path, text)
    except OSError as exc:
        raise ProjectError(f"cannot write run inputs {path}: {exc}") from exc
    return path


def read_run_request(run_dir: Path) -> tuple[dict[str, Any] | None, str]:
    """(record, "") — or (None, "") when there is none, or (None, why it cannot be used)."""
    path = run_request_path(run_dir)
    if not path.exists():
        return None, ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as exc:
        return None, f"the input record could not be read ({exc})"
    if not isinstance(payload, dict):
        return None, "the input record is malformed"
    version = payload.get("schema_version")
    if version != REQUEST_SCHEMA_VERSION:
        return None, (f"the input record has schema {version}; this CMIG reads "
                      f"{REQUEST_SCHEMA_VERSION}")
    if not isinstance(payload.get("analysis"), str) or not isinstance(payload.get("values"), dict):
        return None, "the input record is malformed"
    return payload, ""


# ── phase-1 analysis settings → the phase-2 pages ───────────────────────────────────────────
#: an old key's remembered choice seeds each page that took over its inputs
_SETTINGS_COPIES: dict[str, tuple[str, ...]] = {
    "search": ("gene_ko", "strain_growth", "ratio_impact"),
    "growth": ("strain_growth", "ratio_impact"),
    "dynamics": ("dfba",),
    "host": ("host_search",),
    "host_model": ("host_search_model",),
}
_SETTINGS_RETIRED = ("growth", "dynamics")


def migrate_analysis_settings(
    settings: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    out = {key: json.loads(json.dumps(values)) for key, values in settings.items()}
    for old, new_keys in _SETTINGS_COPIES.items():
        if old in settings:
            for new in new_keys:
                out.setdefault(new, json.loads(json.dumps(settings[old])))
    for old in _SETTINGS_RETIRED:
        out.pop(old, None)
    return out
```
(`json` 왕복 복사는 설정값이 JSON에서 왔기 때문에 안전하고, 목록을 공유하지 않게 한다.)

- [ ] **Step 5: 단위 테스트 통과 확인**

Run: `uv run --no-sync pytest tests/test_project_phase2.py tests/test_project_io.py -q`
Expected: 모두 통과.

- [ ] **Step 6: 세션 테스트 작성**

`tests/test_workspace_session.py`에 추가(파일 안의 기존 fixture·import 방식을 따른다. 세션을 여는 기존 도우미가 있으면 그것을 쓴다):
```python
def test_confirm_namespace_is_undoable(tmp_path):
    from cmig.gui.project_session import ProjectSession

    make_project(tmp_path / "p", ["a"])
    session = ProjectSession()
    session.open(tmp_path / "p")
    try:
        session.confirm_namespace("a")
        assert proj.namespace_confirmed(session.require().model("a"))
        assert session.undo_stack.undoText() == "Confirm Namespace"
        session.undo_stack.undo()
        assert session.require().model("a").namespace_confirmed is None
        session.undo_stack.redo()
        assert proj.namespace_confirmed(session.require().model("a"))
        session.revoke_namespace("a")
        assert session.require().model("a").namespace_confirmed is None
        reopened = proj.open_project(tmp_path / "p")
        assert reopened.model("a").namespace_confirmed is None  # saved
    finally:
        session.close()


def test_undo_rename_restores_remembered_settings_exactly(tmp_path):
    from cmig.gui.project_session import ProjectSession

    project = make_project(tmp_path / "p", ["a", "b"])
    project.analysis_settings["search"] = {"models": ["a", "b"]}
    proj.save_project(project)
    session = ProjectSession()
    session.open(tmp_path / "p")
    try:
        session.remove_models(["a"])
        session.rename_model("b", "a")
        assert session.settings("search")["models"] == ["a"]
        session.undo_stack.undo()  # undo rename
        assert session.settings("search")["models"] == ["a", "b"]
    finally:
        session.close()
```
(`make_project`, `proj`가 그 파일에 import되어 있지 않으면 `from gui_project_helpers import make_project`, `from cmig.io import project as proj`를 더한다.)

- [ ] **Step 7: 세션 구현**

`cmig/gui/project_session.py`:
1. `import copy`를 더한다.
2. `_RenameModel`을 바꾼다:
```python
class _RenameModel(_Command):
    def __init__(self, session: ProjectSession, old: str, new: str) -> None:
        super().__init__(session, "Rename Model")
        self._old, self._new = old, new
        self._settings: dict[str, dict[str, object]] | None = None

    def apply(self) -> None:
        project = self._session.require()
        self._settings = copy.deepcopy(project.analysis_settings)
        proj.rename_model(project, self._old, self._new)

    def revert(self) -> None:
        project = self._session.require()
        project.model(self._new).id = self._old
        if self._settings is not None:
            project.analysis_settings = copy.deepcopy(self._settings)
```
3. 새 명령과 세션 메서드:
```python
class _SetNamespaceConfirmation(_Command):
    def __init__(self, session: ProjectSession, model_id: str, confirmed: bool) -> None:
        super().__init__(
            session, "Confirm Namespace" if confirmed else "Revoke Namespace Confirmation"
        )
        self._id, self._confirmed = model_id, confirmed
        self._before: dict[str, str] | None = None

    def apply(self) -> None:
        project = self._session.require()
        before = project.model(self._id).namespace_confirmed
        self._before = None if before is None else dict(before)
        if self._confirmed:
            proj.confirm_namespace(project, self._id)
        else:
            proj.revoke_namespace(project, self._id)

    def revert(self) -> None:
        entry = self._session.require().model(self._id)
        entry.namespace_confirmed = None if self._before is None else dict(self._before)
```
`ProjectSession`에 메서드를 더한다:
```python
    def confirm_namespace(self, model_id: str) -> None:
        _SetNamespaceConfirmation(self, model_id, True).execute()

    def revoke_namespace(self, model_id: str) -> None:
        _SetNamespaceConfirmation(self, model_id, False).execute()
```
(`confirm_namespace`가 `ProjectError`를 내면 `execute`의 `apply`에서 나므로 스택은 그대로다.)

- [ ] **Step 8: 테스트 통과 확인**

Run: `uv run --no-sync pytest tests/test_workspace_session.py tests/test_project_phase2.py tests/test_project_io.py tests/test_workspace_analysis_inputs.py -q`
Expected: 모두 통과(기존 `test_renamed_model_stays_selected_where_it_was_remembered` 포함).

- [ ] **Step 9: Commit**

```bash
git add cmig/io/project.py cmig/gui/project_session.py tests/gui_project_helpers.py tests/test_project_phase2.py tests/test_workspace_session.py
git commit -m "feat(io): structured model checks, namespace confirmation, run input records

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 3: 모델 색인 (`cmig/io/model_index.py`)과 한 번 읽기

**Files:**
- Modify: `cmig/io/model_import.py` (`load_and_summarize` 추가, `import_model`은 그것을 부름)
- Create: `cmig/io/model_index.py`
- Modify: `cmig/io/project.py` (`check_model_file`이 같은 읽기로 색인을 만듦, `add_model_file`이 색인을 씀)
- Create: `tests/test_model_index.py`

**Interfaces:**
- Consumes: Task 2의 `ModelCheck.index`
- Produces (`cmig.io.model_index`):
  - `INDEX_SCHEMA_VERSION = 1`
  - `index_path(root: Path, sha256: str) -> Path` — `<root>/models/.index/<sha256>.json`
  - `index_from_model(model) -> dict[str, Any]` — 키 `reactions`, `metabolites`, `genes`, `exchanges`, `objective`
  - `write_index(root, sha256, model_id, body) -> Path`
  - `load_index(root, sha256) -> dict[str, Any] | None` (유효하지 않으면 None)
  - `build_index_file(root, model_file, sha256, model_id) -> Path` (모델을 읽어 만들고 씀; 실패는 예외)
  - `search_rows(index) -> list[tuple[str, str, str]]` — (`"reaction"|"metabolite"|"gene"`, id, name)
- Produces (`cmig.io.model_import`): `load_and_summarize(path) -> tuple[ModelSummary, Any]`

색인 항목 형식:
- reaction: `{"id", "name", "metabolites": {met_id: coef}, "lower": float|None, "upper": float|None, "gpr", "subsystem"}` (무한 bound는 `None`)
- metabolite: `{"id", "name", "formula", "charge": int|None, "compartment"}`
- gene: `{"id", "name", "reactions": [ids]}`
- `exchanges`: 정렬한 반응 id 목록, `objective`: `[{"id", "coef"}]`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_model_index.py`:
```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from gui_project_helpers import textbook_sbml

from cmig.io import model_index as mi
from cmig.io import project as proj


@pytest.fixture(scope="module")
def textbook(tmp_path_factory) -> Path:
    return textbook_sbml(tmp_path_factory.mktemp("src") / "textbook.xml")


def test_index_from_model_content(textbook: Path) -> None:
    from cmig.io.model_import import load_cobra_model

    body = mi.index_from_model(load_cobra_model(textbook))
    reactions = {r["id"]: r for r in body["reactions"]}
    assert len(reactions) == 95
    pgi = reactions["PGI"]
    assert pgi["metabolites"] == {"g6p_c": -1.0, "f6p_c": 1.0}
    assert pgi["lower"] == -1000.0 and pgi["upper"] == 1000.0
    assert "b4025" in pgi["gpr"]
    mets = {m["id"]: m for m in body["metabolites"]}
    assert mets["glc__D_e"]["compartment"] == "e" and mets["glc__D_e"]["formula"] == "C6H12O6"
    genes = {g["id"]: g for g in body["genes"]}
    assert "PGI" in genes["b4025"]["reactions"]
    assert "EX_glc__D_e" in body["exchanges"]
    assert body["objective"] == [{"id": "Biomass_Ecoli_core", "coef": 1.0}]
    json.dumps(body, allow_nan=False)  # strict JSON, no NaN/Infinity


def test_write_and_load_round_trip(tmp_path: Path, textbook: Path) -> None:
    path = mi.build_index_file(tmp_path, textbook, "sha1", "textbook")
    assert path == tmp_path / "models" / ".index" / "sha1.json"
    loaded = mi.load_index(tmp_path, "sha1")
    assert loaded is not None and loaded["model_id"] == "textbook"
    assert loaded["schema_version"] == mi.INDEX_SCHEMA_VERSION


def test_corrupt_or_foreign_index_is_rejected(tmp_path: Path) -> None:
    path = mi.index_path(tmp_path, "abc")
    path.parent.mkdir(parents=True)
    path.write_text("{broken")
    assert mi.load_index(tmp_path, "abc") is None
    path.write_text(json.dumps({"schema_version": 1, "sha256": "other", "model_id": "m",
                                "reactions": [], "metabolites": [], "genes": [],
                                "exchanges": [], "objective": []}))
    assert mi.load_index(tmp_path, "abc") is None  # another file's index
    path.write_text(json.dumps({"schema_version": 99, "sha256": "abc"}))
    assert mi.load_index(tmp_path, "abc") is None
    assert mi.load_index(tmp_path, "missing") is None


def test_search_rows(tmp_path: Path, textbook: Path) -> None:
    mi.build_index_file(tmp_path, textbook, "s", "textbook")
    rows = mi.search_rows(mi.load_index(tmp_path, "s") or {})
    assert ("reaction", "PGI", "glucose-6-phosphate isomerase") in rows
    assert ("metabolite", "glc__D_e", "D-Glucose") in rows
    assert any(kind == "gene" and key == "b4025" for kind, key, _name in rows)


def test_adding_a_model_writes_its_index_from_the_same_read(
    tmp_path: Path, textbook: Path, monkeypatch
) -> None:
    import cmig.io.model_import as model_import

    reads: list[str] = []
    original = model_import.load_cobra_model

    def counting(path):  # type: ignore[no-untyped-def]
        reads.append(str(path))
        return original(path)

    monkeypatch.setattr(model_import, "load_cobra_model", counting)
    project = proj.create_project(tmp_path / "p")
    entry = proj.add_model_file(project, textbook)
    assert len(reads) == 1, "the check and the index share one read"
    loaded = mi.load_index(project.root, entry.sha256)
    assert loaded is not None and loaded["model_id"] == entry.id


def test_index_write_failure_does_not_fail_the_import(
    tmp_path: Path, textbook: Path, monkeypatch
) -> None:
    def refuse(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise OSError("read-only")

    monkeypatch.setattr(mi, "write_index", refuse)
    project = proj.create_project(tmp_path / "p")
    entry = proj.add_model_file(project, textbook)
    assert entry.status in ("ok", "warning")
    assert mi.load_index(project.root, entry.sha256) is None
```

- [ ] **Step 2: 실패 확인**

Run: `uv run --no-sync pytest tests/test_model_index.py -q`
Expected: FAIL — `ModuleNotFoundError: cmig.io.model_index`.

- [ ] **Step 3: `load_and_summarize` 구현**

`cmig/io/model_import.py`에서 `import_model`의 본문을 그대로 `load_and_summarize`로 옮기고, 마지막 `return ModelSummary(...)`를 `return ModelSummary(...), model`로 바꾼다. `import_model`은 다음이 된다:
```python
def load_and_summarize(path: str | Path) -> tuple[ModelSummary, Any]:
    """GEM 파일 → (ModelSummary, loaded cobra model): one read for callers needing both."""
    ...  # 옛 import_model 본문. 반환만 (summary, model)


def import_model(path: str | Path) -> ModelSummary:
    """GEM 파일 → ModelSummary. 포맷 자동 감지 + cobra.io 위임."""
    return load_and_summarize(path)[0]
```
본문 안의 `model = load_cobra_model(p)`는 모듈 전역 이름 `load_cobra_model`을 부르도록 둔다(테스트의 monkeypatch가 그 이름을 바꾼다).

- [ ] **Step 4: `cmig/io/model_index.py` 작성**

```python
"""Per-model browse/search index under ``models/.index/<sha256>.json`` (Qt-free).

A cache for the model browser and project search only — never an analysis input, a taxonomy
row or a CLI argument. A file that cannot be read, has another schema, or belongs to another
model file reads as missing and is rebuilt.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from cmig.io.atomic import atomic_write_text

INDEX_SCHEMA_VERSION = 1
_KEYS = ("reactions", "metabolites", "genes", "exchanges", "objective")


def index_path(root: Path, sha256: str) -> Path:
    return Path(root) / "models" / ".index" / f"{sha256}.json"


def _bound(value: object) -> float | None:
    number = float(value)  # type: ignore[arg-type]
    return number if math.isfinite(number) else None


def _charge(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return int(number) if math.isfinite(number) and number == int(number) else None


def index_from_model(model: Any) -> dict[str, Any]:
    from cobra.util.solver import linear_reaction_coefficients

    reactions = [
        {
            "id": str(r.id),
            "name": str(r.name or ""),
            "metabolites": {str(m.id): float(c) for m, c in r.metabolites.items()},
            "lower": _bound(r.lower_bound),
            "upper": _bound(r.upper_bound),
            "gpr": str(r.gene_reaction_rule or ""),
            "subsystem": str(r.subsystem or ""),
        }
        for r in model.reactions
    ]
    metabolites = [
        {
            "id": str(m.id),
            "name": str(m.name or ""),
            "formula": str(m.formula or ""),
            "charge": _charge(m.charge),
            "compartment": str(m.compartment or ""),
        }
        for m in model.metabolites
    ]
    genes = [
        {"id": str(g.id), "name": str(g.name or ""),
         "reactions": sorted(str(r.id) for r in g.reactions)}
        for g in model.genes
    ]
    objective = [
        {"id": str(r.id), "coef": float(c)}
        for r, c in linear_reaction_coefficients(model).items()
    ]
    return {
        "reactions": reactions,
        "metabolites": metabolites,
        "genes": genes,
        "exchanges": sorted(str(r.id) for r in model.exchanges),
        "objective": sorted(objective, key=lambda item: str(item["id"])),
    }


def write_index(root: Path, sha256: str, model_id: str, body: dict[str, Any]) -> Path:
    payload = {"schema_version": INDEX_SCHEMA_VERSION, "sha256": sha256,
               "model_id": model_id, **body}
    text = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return atomic_write_text(index_path(root, sha256), text)


def load_index(root: Path, sha256: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(index_path(root, sha256).read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != INDEX_SCHEMA_VERSION
        or payload.get("sha256") != sha256
        or not all(isinstance(payload.get(key), list) for key in _KEYS)
    ):
        return None
    return payload


def build_index_file(root: Path, model_file: Path, sha256: str, model_id: str) -> Path:
    """Read one model copy and write its index. Raises on an unreadable model or disk error."""
    from cmig.io.model_import import load_cobra_model

    return write_index(root, sha256, model_id, index_from_model(load_cobra_model(model_file)))


def search_rows(index: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(kind, id, name) for every reaction, metabolite and gene; exchanges are reactions."""
    rows: list[tuple[str, str, str]] = []
    for kind, key in (("reaction", "reactions"), ("metabolite", "metabolites"),
                      ("gene", "genes")):
        for item in index.get(key) or []:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                rows.append((kind, item["id"], str(item.get("name") or "")))
    return rows
```
(`atomic_write_text`가 `Path`를 돌려주는지 확인하고, 아니면 `write_index`에서 경로를 따로 돌려준다.)

- [ ] **Step 5: 점검과 가져오기 연결**

`cmig/io/project.py`:
1. `check_model_file`에서 `from cmig.io.model_import import build_import_review, import_model`를 `from cmig.io.model_import import build_import_review, load_and_summarize`로, `summary = import_model(path)`를 `summary, model = load_and_summarize(path)`로 바꾼다. `review = …` 다음에 색인을 만든다(색인 실패는 점검 결과를 바꾸지 않는다):
```python
    index: dict[str, Any] | None
    try:
        from cmig.io.model_index import index_from_model

        index = index_from_model(model)
    except Exception:  # noqa: BLE001 - the index is a browse cache; the check stands without it
        index = None
```
그리고 `return ModelCheck(...)`에 `index=index`를 더한다.
2. `add_model_file`에서 `apply_check(entry, check(target))`를 다음으로 바꾼다:
```python
    if check is not None:
        result = check(target)
        apply_check(entry, result)
        if result.index is not None:
            from cmig.io import model_index

            with contextlib.suppress(OSError, ValueError):
                model_index.write_index(project.root, sha, entry.id, result.index)
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `uv run --no-sync pytest tests/test_model_index.py tests/test_project_phase2.py tests/test_project_io.py tests/test_workspace_import.py -q`
Expected: 모두 통과.

- [ ] **Step 7: Commit**

```bash
git add cmig/io/model_import.py cmig/io/model_index.py cmig/io/project.py tests/test_model_index.py
git commit -m "feat(io): per-model browse index built from the import read

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 4: 공통 분석 화면 틀 (`cmig/gui/analysis_page.py`)

**Files:**
- Create: `cmig/gui/analysis_page.py`
- Create: `tests/test_phase2_analysis_page.py`

**Interfaces:**
- Produces:
  - `hide_row_numbers(table: QTableWidget) -> QTableWidget`
  - `widget_value(widget) -> Any` — `ModelPicker`→선택 id 목록, `MediumPicker`→ref, `QCheckBox`→bool, `QDoubleSpinBox`→float, `QSpinBox`→int, `QComboBox`→현재 글자, `QLineEdit`→글자
  - `set_widget_value(widget, value) -> str | None` — 복원하지 못하면 이유 문장(배너용), 성공은 None
  - `connect_change(widget, slot) -> None` — 위 종류의 "값이 바뀜" 신호에 연결
  - `AdvancedSection(title="Advanced options")`: `toggle`(QToolButton), `body`, `body_layout`, `add_row(*items) -> QHBoxLayout`, `track(*widgets)`, `changed_count() -> int`, `set_expanded(bool)`
  - `ResultsArea`: `status`(QLabel), `empty_label`, `content`, `add(widget, stretch=0)`, `show_results()`, `show_empty()`, `has_results() -> bool`, `EMPTY_TEXT`
  - `AnalysisPage(title, description, run_text="Run", *, cancel=True)`: `scroll_area`, `title`, `description`, `banner`, `card`, `inputs`(QVBoxLayout), `run_btn`, `cancel_btn`, `advanced`, `results`, `status`(= `results.status`), `add_input_row(*items) -> QHBoxLayout`, `register(name, widget)`, `register_custom(name, getter, setter)`, `snapshot() -> dict[str, Any]`, `restore(values) -> list[str]`, `show_banner(text)`, `clear_banner()`
  - 복원 순서는 등록 순서다. 다른 입력의 선택지를 정하는 입력(모델 선택기)을 먼저 등록한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_phase2_analysis_page.py`:
```python
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown  # noqa: E402,F401
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLineEdit,
    QSpinBox,
    QTableWidget,
)

from cmig.gui.analysis_page import (  # noqa: E402
    AnalysisPage,
    ResultsArea,
    hide_row_numbers,
)
from cmig.gui.pickers import MediumPicker, ModelPicker  # noqa: E402

APP = QApplication.instance() or QApplication([])


def _page() -> tuple[AnalysisPage, dict[str, object]]:
    page = AnalysisPage("Demo", "One line about the demo.")
    models = ModelPicker("Models")
    models.set_choices([("a", True, ""), ("b", True, ""), ("gone", False, "missing")])
    medium = MediumPicker()
    medium.set_choices(["western_diet"], [])
    size = QSpinBox()
    size.setRange(1, 10)
    size.setValue(2)
    fraction = QDoubleSpinBox()
    fraction.setValue(0.5)
    combo = QComboBox()
    combo.addItems(["auto", "exhaustive"])
    check = QCheckBox("FVA")
    text = QLineEdit("but")
    page.add_input_row(models, "Medium", medium)
    page.add_input_row("Size", size)
    page.advanced.add_row("Fraction", fraction, "Strategy", combo, check, text)
    page.advanced.track(fraction, combo, check, text)
    widgets = {"models": models, "medium": medium, "size": size, "fraction": fraction,
               "strategy": combo, "fva": check, "target": text}
    for name, widget in widgets.items():
        page.register(name, widget)  # type: ignore[arg-type]
    return page, widgets


def test_snapshot_and_restore_round_trip() -> None:
    page, w = _page()
    w["models"].set_selected(["b"])  # type: ignore[attr-defined]
    w["medium"].set_ref("preset:western_diet")  # type: ignore[attr-defined]
    w["size"].setValue(3)  # type: ignore[attr-defined]
    w["strategy"].setCurrentText("exhaustive")  # type: ignore[attr-defined]
    saved = page.snapshot()
    assert saved == {"models": ["b"], "medium": "preset:western_diet", "size": 3,
                     "fraction": 0.5, "strategy": "exhaustive", "fva": False, "target": "but"}
    other, _ = _page()
    assert other.restore(saved) == []
    assert other.snapshot() == saved


def test_restore_reports_values_that_cannot_be_chosen_now() -> None:
    page, _w = _page()
    notes = page.restore({"models": ["a", "gone", "never"], "medium": "medium:deleted",
                          "strategy": "ga"})
    assert page.snapshot()["models"] == ["a"]
    assert page.snapshot()["medium"] == ""
    joined = " ".join(notes)
    assert "gone" in joined and "never" in joined
    assert "deleted" in joined and "ga" in joined


def test_advanced_counts_values_changed_from_their_defaults() -> None:
    page, w = _page()
    assert page.advanced.changed_count() == 0
    assert page.advanced.toggle.text() == "Advanced options"
    w["fraction"].setValue(0.25)  # type: ignore[attr-defined]
    w["fva"].setChecked(True)  # type: ignore[attr-defined]
    assert page.advanced.changed_count() == 2
    assert page.advanced.toggle.text() == "Advanced options · 2 changed"
    w["fraction"].setValue(0.5)  # type: ignore[attr-defined]
    assert page.advanced.toggle.text() == "Advanced options · 1 changed"
    assert page.advanced.body.isHidden(), "collapsed by default"
    page.advanced.set_expanded(True)
    assert not page.advanced.body.isHidden()


def test_results_area_starts_empty_and_shows_content() -> None:
    area = ResultsArea()
    table = QTableWidget(0, 2)
    area.add(table)
    assert not area.has_results()
    assert area.empty_label.text() == ResultsArea.EMPTY_TEXT
    assert table.isHidden() or area.content.isHidden()
    area.show_results()
    assert area.has_results() and area.empty_label.isHidden()
    area.show_empty()
    assert not area.has_results()


def test_page_frame_and_banner() -> None:
    page, _w = _page()
    assert page.status is page.results.status
    assert page.banner.isHidden()
    page.show_banner("Inputs restored from search-1")
    assert not page.banner.isHidden() and "search-1" in page.banner.text()
    page.clear_banner()
    assert page.banner.isHidden()
    assert not page.cancel_btn.isEnabled()


def test_hide_row_numbers() -> None:
    table = hide_row_numbers(QTableWidget(2, 2))
    assert table.verticalHeader().isHidden()
```

- [ ] **Step 2: 실패 확인**

Run: `uv run --no-sync pytest tests/test_phase2_analysis_page.py -q`
Expected: FAIL — `ModuleNotFoundError: cmig.gui.analysis_page`.

- [ ] **Step 3: 구현**

`cmig/gui/analysis_page.py`:
```python
"""The frame every analysis page uses: an inputs card with Run, Advanced options, Results.

Pages register their inputs by name; `snapshot()` is what a run records in
`runs/_inputs/<run>-request.json` and `restore()` puts it back when the run is reopened.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from cmig.gui.pickers import MediumPicker, ModelPicker


def hide_row_numbers(table: QTableWidget) -> QTableWidget:
    table.verticalHeader().setVisible(False)
    return table


def widget_value(widget: QWidget) -> Any:
    if isinstance(widget, ModelPicker):
        return widget.selected_ids()
    if isinstance(widget, MediumPicker):  # before QComboBox: it is one
        return widget.current_ref()
    if isinstance(widget, QCheckBox):
        return widget.isChecked()
    if isinstance(widget, QDoubleSpinBox):
        return widget.value()
    if isinstance(widget, QSpinBox):
        return widget.value()
    if isinstance(widget, QComboBox):
        return widget.currentText()
    if isinstance(widget, QLineEdit):
        return widget.text()
    raise TypeError(f"no value for {type(widget).__name__}")


def set_widget_value(widget: QWidget, value: Any) -> str | None:
    """Put a recorded value back; returns why it could not be, or None when it was."""
    try:
        if isinstance(widget, ModelPicker):
            wanted = [str(v) for v in value]
            widget.set_selected(wanted)
            lost = [v for v in wanted if v not in widget.selected_ids()]
            return f"{', '.join(lost)} can no longer be chosen" if lost else None
        if isinstance(widget, MediumPicker):
            try:
                widget.set_ref(str(value))
            except ValueError:
                widget.set_ref("")
                return f"medium {str(value).partition(':')[2] or value} is no longer available"
            return None
        if isinstance(widget, QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, QDoubleSpinBox):
            widget.setValue(float(value))
        elif isinstance(widget, QSpinBox):
            widget.setValue(int(value))
        elif isinstance(widget, QComboBox):
            index = widget.findText(str(value))
            if index < 0:
                return f"{value} is not a choice any more"
            widget.setCurrentIndex(index)
        elif isinstance(widget, QLineEdit):
            widget.setText(str(value))
        else:
            return f"{type(widget).__name__} cannot be restored"
    except (TypeError, ValueError):
        return f"{value!r} could not be restored"
    return None


def connect_change(widget: QWidget, slot: Callable[..., Any]) -> None:
    if isinstance(widget, ModelPicker):
        widget.selection_changed.connect(slot)
    elif isinstance(widget, QComboBox):
        widget.currentIndexChanged.connect(slot)
    elif isinstance(widget, QCheckBox):
        widget.toggled.connect(slot)
    elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
        widget.valueChanged.connect(slot)
    elif isinstance(widget, QLineEdit):
        widget.textChanged.connect(slot)


def _row(items: tuple[QWidget | str, ...]) -> QHBoxLayout:
    row = QHBoxLayout()
    for item in items:
        row.addWidget(QLabel(item) if isinstance(item, str) else item)
    row.addStretch(1)
    return row


class AdvancedSection(QWidget):
    """A disclosure button and its (collapsed) body; the button counts changed settings."""

    def __init__(self, title: str = "Advanced options") -> None:
        super().__init__()
        self._title = title
        self.toggle = QToolButton()
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setAutoRaise(True)
        self.toggle.toggled.connect(self.set_expanded)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(18, 0, 0, 0)
        self.body.setVisible(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toggle)
        layout.addWidget(self.body)
        self._tracked: list[tuple[QWidget, Any]] = []
        self._refresh()

    def add_row(self, *items: QWidget | str) -> QHBoxLayout:
        row = _row(items)
        self.body_layout.addLayout(row)
        return row

    def track(self, *widgets: QWidget) -> None:
        """Count each widget as changed while its value differs from its value now."""
        for widget in widgets:
            self._tracked.append((widget, widget_value(widget)))
            connect_change(widget, lambda *_a: self._refresh())
        self._refresh()

    def changed_count(self) -> int:
        return sum(1 for widget, default in self._tracked if widget_value(widget) != default)

    def set_expanded(self, expanded: bool) -> None:
        if self.toggle.isChecked() != expanded:
            self.toggle.setChecked(expanded)
        self.toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.body.setVisible(expanded)

    def _refresh(self) -> None:
        count = self.changed_count()
        self.toggle.setText(self._title + (f" · {count} changed" if count else ""))


class ResultsArea(QWidget):
    EMPTY_TEXT = "No results yet — set the inputs above and press Run."

    def __init__(self) -> None:
        super().__init__()
        heading = QLabel("Results")
        font = QFont(heading.font())
        font.setBold(True)
        heading.setFont(font)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.empty_label = QLabel(self.EMPTY_TEXT)
        self.empty_label.setEnabled(False)  # secondary text colour in both appearances
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(heading)
        layout.addWidget(self.status)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.content, 1)
        self.show_empty()

    def add(self, widget: QWidget, stretch: int = 0) -> None:
        self.content_layout.addWidget(widget, stretch)

    def show_results(self) -> None:
        self.empty_label.setVisible(False)
        self.content.setVisible(True)

    def show_empty(self) -> None:
        self.content.setVisible(False)
        self.empty_label.setVisible(True)

    def has_results(self) -> bool:
        return not self.content.isHidden()


class AnalysisPage(QWidget):
    def __init__(
        self, title: str, description: str, run_text: str = "Run", *, cancel: bool = True
    ) -> None:
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setMinimumSize(0, 0)
        outer.addWidget(self.scroll_area)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 10, 12, 10)
        self.scroll_area.setWidget(content)
        self.title = QLabel(title)
        title_font = QFont(self.title.font())
        title_font.setBold(True)
        title_font.setPointSizeF(title_font.pointSizeF() * 1.25)
        self.title.setFont(title_font)
        self.description = QLabel(description)
        self.description.setWordWrap(True)
        self.banner = QLabel("")
        self.banner.setWordWrap(True)
        self.banner.setFrameShape(QFrame.Shape.StyledPanel)
        self.banner.setMargin(6)
        self.banner.setVisible(False)
        self.card = QFrame()
        self.card.setFrameShape(QFrame.Shape.StyledPanel)
        card_layout = QVBoxLayout(self.card)
        self.inputs = QVBoxLayout()
        card_layout.addLayout(self.inputs)
        self.run_btn = QPushButton(run_text)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setVisible(cancel)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.run_btn)
        card_layout.addLayout(buttons)
        self.advanced = AdvancedSection()
        self.results = ResultsArea()
        self.status = self.results.status
        layout.addWidget(self.title)
        layout.addWidget(self.description)
        layout.addWidget(self.banner)
        layout.addWidget(self.card)
        layout.addWidget(self.advanced)
        layout.addWidget(self.results, 1)
        self._fields: dict[str, tuple[Callable[[], Any], Callable[[Any], str | None]]] = {}

    def add_input_row(self, *items: QWidget | str) -> QHBoxLayout:
        row = _row(items)
        self.inputs.addLayout(row)
        return row

    def register(self, name: str, widget: QWidget) -> None:
        self._fields[name] = (
            lambda: widget_value(widget), lambda value: set_widget_value(widget, value)
        )

    def register_custom(
        self, name: str, getter: Callable[[], Any], setter: Callable[[Any], str | None]
    ) -> None:
        self._fields[name] = (getter, setter)

    def snapshot(self) -> dict[str, Any]:
        return {name: getter() for name, (getter, _setter) in self._fields.items()}

    def restore(self, values: dict[str, Any]) -> list[str]:
        notes: list[str] = []
        for name, (_getter, setter) in self._fields.items():
            if name in values:
                note = setter(values[name])
                if note:
                    notes.append(note)
        return notes

    def show_banner(self, text: str) -> None:
        self.banner.setText(text)
        self.banner.setVisible(True)

    def clear_banner(self) -> None:
        self.banner.clear()
        self.banner.setVisible(False)
```

- [ ] **Step 4: 통과 확인**

Run: `uv run --no-sync pytest tests/test_phase2_analysis_page.py -q && uv run --no-sync mypy cmig/gui/analysis_page.py`
Expected: 6 passed; mypy 오류 없음.

- [ ] **Step 5: Commit**

```bash
git add cmig/gui/analysis_page.py tests/test_phase2_analysis_page.py
git commit -m "feat(gui): common analysis page frame with Advanced count and restorable inputs

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 5: 키보드로 조작하는 모델 선택기

**Files:**
- Modify: `cmig/gui/pickers.py` (`ModelPicker._build_list`, `eventFilter`, 메뉴 닫힘 처리)
- Modify: `tests/test_workspace_pickers.py`

**Interfaces:**
- Produces: 동작만. 다중 선택기: 필터 칸 ↓/Tab → 목록(처음 보이는 행이 현재 행), 목록 맨 위 ↑ 또는 Shift+Tab → 필터 칸, 목록 Tab → Select All → Tab → Select None → Tab → 필터 칸(반대 방향은 Shift+Tab), Space(목록) → 체크 전환(열린 채), Return/Enter(어디서든) → 닫기, 닫히면 포커스는 선택기 단추. 하나만 고르는 선택기는 Qt 메뉴 기본 동작(↑/↓, Return으로 고르고 닫힘)을 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_workspace_pickers.py`에 추가:
```python
def _open(picker: ModelPicker):
    picker.show()
    menu = picker.menu()
    menu.popup(picker.mapToGlobal(QPoint(0, picker.height())))
    APP.processEvents()
    QTest.qWait(10)  # the filter takes focus on the next event-loop turn
    APP.processEvents()
    return menu


def test_keyboard_reaches_list_buttons_and_back() -> None:
    picker = ModelPicker()
    picker.set_choices([("alpha", True, ""), ("beta", True, ""), ("gamma", True, "")])
    picker.set_selected([])
    menu = _open(picker)
    assert picker.filter_input.hasFocus()
    QTest.keyClick(picker.filter_input, Qt.Key.Key_Down)
    assert picker.choice_list.hasFocus()
    assert picker.choice_list.currentItem().text() == "alpha"
    QTest.keyClick(picker.choice_list, Qt.Key.Key_Space)
    assert picker.selected_ids() == ["alpha"] and menu.isVisible()
    QTest.keyClick(picker.choice_list, Qt.Key.Key_Up)
    assert picker.filter_input.hasFocus(), "Up on the first row goes back to the filter"
    QTest.keyClick(picker.filter_input, Qt.Key.Key_Tab)
    assert picker.choice_list.hasFocus()
    QTest.keyClick(picker.choice_list, Qt.Key.Key_Tab)
    assert picker.select_all_btn.hasFocus()
    QTest.keyClick(picker.select_all_btn, Qt.Key.Key_Space)
    assert picker.selected_ids() == ["alpha", "beta", "gamma"]
    QTest.keyClick(picker.select_all_btn, Qt.Key.Key_Tab)
    assert picker.select_none_btn.hasFocus()
    QTest.keyClick(picker.select_none_btn, Qt.Key.Key_Tab)
    assert picker.filter_input.hasFocus()
    QTest.keyClick(picker.filter_input, Qt.Key.Key_Backtab)
    assert picker.select_none_btn.hasFocus()
    QTest.keyClick(picker.select_none_btn, Qt.Key.Key_Return)
    APP.processEvents()
    assert not menu.isVisible()
    assert picker.hasFocus(), "focus returns to the picker button"
    assert picker.selected_ids() == ["alpha", "beta", "gamma"], "Return closes, it does not act"


def test_filter_then_down_starts_at_first_shown_row() -> None:
    picker = ModelPicker()
    picker.set_choices([("alpha", True, ""), ("beta", True, ""), ("bravo", True, "")])
    picker.set_selected([])
    menu = _open(picker)
    QTest.keyClicks(picker.filter_input, "br")
    QTest.keyClick(picker.filter_input, Qt.Key.Key_Down)
    assert picker.choice_list.currentItem().text() == "bravo"
    QTest.keyClick(picker.choice_list, Qt.Key.Key_Space)
    assert picker.selected_ids() == ["bravo"]
    QTest.keyClick(picker.choice_list, Qt.Key.Key_Escape)
    APP.processEvents()
    assert not menu.isVisible() and picker.hasFocus()


def test_single_picker_return_picks_and_closes() -> None:
    picker = ModelPicker("Model", single=True)
    picker.set_choices([("a", True, ""), ("b", True, "")])
    picker.show()
    menu = picker.menu()
    menu.popup(picker.mapToGlobal(QPoint(0, picker.height())))
    APP.processEvents()
    QTest.keyClick(menu, Qt.Key.Key_Down)
    QTest.keyClick(menu, Qt.Key.Key_Down)
    QTest.keyClick(menu, Qt.Key.Key_Return)
    APP.processEvents()
    assert not menu.isVisible()
    assert picker.selected_ids() == ["b"]
```
(마지막 테스트에서 ↓ 두 번이 "b"에 닿지 않으면, offscreen 메뉴의 첫 ↓가 첫 항목을 고르는지 확인하고 ↓ 횟수를 그에 맞춘다. 단언 `["b"]`는 바꾸지 않는다.)

- [ ] **Step 2: 실패 확인**

Run: `uv run --no-sync pytest tests/test_workspace_pickers.py -q -k "keyboard or first_shown or single_picker_return"`
Expected: FAIL — 필터 칸에서 ↓를 눌러도 목록으로 가지 않는다.

- [ ] **Step 3: 구현**

`cmig/gui/pickers.py`:
1. `_build_list`에서 `self.choice_list.installEventFilter(self)` 옆에 다음을 더한다:
```python
        for widget in (self.filter_input, self.select_all_btn, self.select_none_btn):
            widget.installEventFilter(self)
        menu.aboutToHide.connect(self._return_focus)
```
2. `eventFilter`를 바꾼다:
```python
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt override
        """Keyboard path through the open list: filter ⇄ list ⇄ Select All ⇄ Select None.

        QMenu would otherwise take Tab and the arrows for its own (single) action, so a
        keyboard-only user could never reach the rows or the buttons.
        """
        if event.type() != QEvent.Type.KeyPress or not isinstance(event, QKeyEvent):
            return super().eventFilter(watched, event)
        if getattr(self, "choice_list", None) is None:
            return super().eventFilter(watched, event)
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.menu().close()
            return True
        order: list[QWidget] = [
            self.filter_input, self.choice_list, self.select_all_btn, self.select_none_btn,
        ]
        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab) and watched in order:
            step = -1 if key == Qt.Key.Key_Backtab else 1
            self._focus(order[(order.index(watched) + step) % len(order)])  # type: ignore[arg-type]
            return True
        if watched is self.filter_input and key == Qt.Key.Key_Down:
            self._focus(self.choice_list)
            return True
        if watched is self.choice_list:
            if key == Qt.Key.Key_Space:
                item = self.choice_list.currentItem()
                if item is not None:
                    self._toggle(item)
                return True
            if key == Qt.Key.Key_Up and self.choice_list.currentItem() is self._first_shown():
                self._focus(self.filter_input)
                return True
        return super().eventFilter(watched, event)

    def _first_shown(self) -> QListWidgetItem | None:
        for i in range(self.choice_list.count()):
            item = self.choice_list.item(i)
            if not item.isHidden():
                return item
        return None

    def _focus(self, widget: QWidget) -> None:
        if widget is self.choice_list:
            current = self.choice_list.currentItem()
            if current is None or current.isHidden():
                first = self._first_shown()
                if first is not None:
                    self.choice_list.setCurrentItem(first)
        widget.setFocus(Qt.FocusReason.TabFocusReason)

    def _return_focus(self) -> None:
        QTimer.singleShot(0, lambda: self.setFocus(Qt.FocusReason.PopupFocusReason))
```
3. `QWidget`가 import 목록에 이미 있다. 없으면 더한다.

- [ ] **Step 4: 통과 확인**

Run: `uv run --no-sync pytest tests/test_workspace_pickers.py -q`
Expected: 기존 테스트 포함 모두 통과. `_return_focus`가 다음 이벤트 차례에 실행되므로, 테스트에서 포커스를 확인하기 전에 `APP.processEvents()`가 필요하면 더한다.

- [ ] **Step 5: Commit**

```bash
git add cmig/gui/pickers.py tests/test_workspace_pickers.py
git commit -m "fix(gui): multi-model picker is fully keyboard operable

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 6: Search 결과 위젯을 `SearchResultsPanel`로 떼어 내기 (동작 변화 없음)

Search·Gene KO·Strain Growth·Ratio Impact·Host Search 결과는 모두 지금 `SearchView` 한 곳의 표·상세·그림에 그려진다. 화면을 나누려면 이 결과 위젯이 화면마다 하나씩 있어야 한다. 이 작업은 코드를 옮기기만 하고 동작은 바꾸지 않는다.

**Files:**
- Create: `cmig/gui/search_results.py`
- Modify: `cmig/gui/builder.py` (`SearchView`가 패널을 갖고 옛 이름을 위임)
- Create: `tests/test_phase2_search_results.py`

**Interfaces:**
- Produces: `SearchResultsPanel(request_fields: Callable[[str], dict[str, str]], status: QLabel | None = None)`
  - 위젯: `status`(받은 QLabel 또는 새 것), `details`, `table`, `pareto_label`, `inspector_label`, `inspector`, `figure_mode_combo`, `export_figure_btn`, `figure_view`, `figure_placeholder`, `figure_stack`
  - 상태: `current_run_dir`, `_displayed_kind`, `_displayed_request`, `_executed_request`, `_row_records`, `_inspector_summary`, `_evaluations`, `_evaluations_error`
  - 메서드: `invalidate_results(*args)`, `superseded_note(requested, kind)`, `effective_note(requested, kind)`, `row_record(row)`, `selected_figure_artifact()`, `refresh_figure_mode(mode=None)`, `load_summary(summary, *, run_dir=None, request_note="", workflow_kind="search", executed_request=None, source_summary=None)`
- `SearchView`는 같은 이름의 속성·메서드를 패널에 위임한다(`current_run_dir`, `_displayed_kind`, `_displayed_request`는 읽기·쓰기 property). 기존 코드와 테스트는 그대로 동작한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_phase2_search_results.py`:
```python
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown  # noqa: E402,F401
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from cmig.gui.builder import SearchView  # noqa: E402
from cmig.gui.search_results import SearchResultsPanel  # noqa: E402

APP = QApplication.instance() or QApplication([])

SUMMARY = {
    "status": "ok", "strategy": "exhaustive", "target": "but",
    "top_ranked": [{"members": ["a", "b"], "score": 1.5, "target_flux": 1.5,
                    "community_growth": 0.4, "status": "optimal"}],
}


def test_panel_loads_and_invalidates_on_its_own() -> None:
    request = {"models": "a,b"}
    status = QLabel()
    panel = SearchResultsPanel(lambda kind: dict(request) if kind == "search" else {},
                               status=status)
    assert panel.status is status
    panel.load_summary(SUMMARY)
    assert panel.table.rowCount() == 1
    assert panel.table.item(0, 0).text() == "a+b"
    panel.invalidate_results(True)  # same request: kept
    assert panel.table.rowCount() == 1
    request["models"] = "a"
    panel.invalidate_results(True)
    assert panel.table.rowCount() == 0
    assert "Inputs changed" in status.text()


def test_search_view_delegates_to_its_panel() -> None:
    view = SearchView()
    assert isinstance(view.results_panel, SearchResultsPanel)
    assert view.table is view.results_panel.table
    view.current_run_dir = None
    view._displayed_kind = "search"
    assert view.results_panel._displayed_kind == "search"
    view.load_summary(SUMMARY)
    assert view.results_panel.table.rowCount() == 1
```

- [ ] **Step 2: 실패 확인**

Run: `uv run --no-sync pytest tests/test_phase2_search_results.py -q`
Expected: FAIL — `ModuleNotFoundError: cmig.gui.search_results`.

- [ ] **Step 3: 패널 만들기**

`cmig/gui/search_results.py`를 만든다:
1. 모듈 docstring: `"""Ranked-result view shared by Search, Gene KO, Strain Growth, Ratio Impact and Host Search pages."""`
2. `SearchView.__init__`(`cmig/gui/builder.py` 527행 근처)에서 결과 위젯을 만드는 코드를 그대로 옮겨 `SearchResultsPanel.__init__`을 만든다. 옮길 것:
   - `self.export_figure_btn`, `self.figure_mode_combo`(+ `currentTextChanged.connect(self.refresh_figure_mode)`), `figure_row`
   - `self.status`(인자로 받은 QLabel이 있으면 그것을 쓴다), `self.details`, `self.table`, `self.pareto_label`, `self.inspector_label`, `self.inspector`
   - `_row_records`, `_inspector_summary`, `_evaluations`, `_evaluations_error`, `table.itemSelectionChanged.connect(self._refresh_inspector)`, `current_run_dir`
   - `figure_view`/`figure_placeholder`/`figure_stack`, `_displayed_kind`, `_displayed_request`, `_executed_request`
   - 배치: `figure_row`, `status`(인자로 받았으면 넣지 않음 — 그 QLabel은 이미 다른 곳에 있다), `details`, `table`, `inspector_label`, `inspector`, `pareto_label`, `figure_stack`를 `QVBoxLayout(self)`에 이 순서로 넣는다(여백 0).
3. `SearchView`의 다음 메서드를 본문 그대로 패널로 옮긴다. 본문의 `self.request_fields(`는 `self._request_fields(`로 바꾼다: `superseded_note`, `effective_note`, `invalidate_results`, `_clear_inspector`, `row_record`, `_refresh_inspector`, `_inspector_lines`, `selected_figure_artifact`, `_refresh_figure_choices`, `refresh_figure_mode`, `load_summary`. 이 메서드들이 쓰는 모듈 함수·상수(`_format_recorded`, `_recorded`, `_read_search_evaluations`, `_matching_evaluation`, `_pareto_attempt_lines`, `_optional_float`, `_diagnostic_text`, `_fva_range_text`, `_DIAGNOSTIC_COLOR`, `_NOT_RECORDED`, `_ABSENT`, `_FLUX_BASIS_TEXT`, `SEARCH_COLUMNS`, `medium_mode_text`, `validate_search_summary`, `read_only_item`, `make_read_only`)는 `cmig.gui.builder`에서 import한다. 순환 import가 생기면(`builder`가 `search_results`를 import하므로) 그 함수들을 `search_results.py`로 옮기고 `builder.py`에서 다시 import해 옛 이름을 유지한다.
4. 생성자 서명:
```python
class SearchResultsPanel(QWidget):
    def __init__(
        self,
        request_fields: Callable[[str], dict[str, str]],
        status: QLabel | None = None,
    ) -> None:
        super().__init__()
        self._request_fields = request_fields
        self._own_status = status is None
        self.status = QLabel("") if status is None else status
        if self._own_status:
            self.status.setWordWrap(True)
            self.status.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
        ...  # 옮긴 위젯 생성과 배치
```

- [ ] **Step 4: `SearchView`가 패널에 위임**

`SearchView.__init__`에서 옮긴 위젯 생성 코드를 지우고 다음으로 바꾼다(같은 배치 위치에 패널을 넣는다. `status`는 패널이 만든 것을 쓴다):
```python
        self.results_panel = SearchResultsPanel(self.request_fields)
        panel = self.results_panel
        for name in ("status", "details", "table", "pareto_label", "inspector_label",
                     "inspector", "figure_mode_combo", "export_figure_btn", "figure_view",
                     "figure_placeholder", "figure_stack"):
            setattr(self, name, getattr(panel, name))
```
`layout.addLayout(figure_row)`와 `layout.addWidget(self.status)` … `layout.addWidget(self.figure_stack)` 줄들은 `layout.addWidget(self.results_panel)` 한 줄로 바꾼다. 옮긴 메서드는 `SearchView`에서 지우고 다음 위임을 더한다:
```python
    # ── the ranked result lives in self.results_panel ────────────────────────────────
    @property
    def current_run_dir(self) -> Path | None:
        return self.results_panel.current_run_dir

    @current_run_dir.setter
    def current_run_dir(self, value: Path | None) -> None:
        self.results_panel.current_run_dir = value

    @property
    def _displayed_kind(self) -> str | None:
        return self.results_panel._displayed_kind

    @_displayed_kind.setter
    def _displayed_kind(self, value: str | None) -> None:
        self.results_panel._displayed_kind = value

    @property
    def _displayed_request(self) -> dict[str, str] | None:
        return self.results_panel._displayed_request

    @_displayed_request.setter
    def _displayed_request(self, value: dict[str, str] | None) -> None:
        self.results_panel._displayed_request = value

    def invalidate_results(self, *args: object) -> None:
        self.results_panel.invalidate_results(*args)

    def superseded_note(self, requested: dict[str, str], kind: str) -> str:
        return self.results_panel.superseded_note(requested, kind)

    def effective_note(self, requested: dict[str, str], kind: str) -> str:
        return self.results_panel.effective_note(requested, kind)

    def row_record(self, row: int) -> dict[object, object] | None:
        return self.results_panel.row_record(row)

    def selected_figure_artifact(self) -> str:
        return self.results_panel.selected_figure_artifact()

    def refresh_figure_mode(self, mode: str | None = None) -> None:
        self.results_panel.refresh_figure_mode(mode)

    def load_summary(self, summary: dict[str, object], **kwargs: Any) -> None:
        self.results_panel.load_summary(summary, **kwargs)
```
`SearchView.__init__`에서 `self.current_run_dir = …`, `self._displayed_kind = …`처럼 이 상태를 처음 대입하던 줄은 지운다(패널이 초기화한다). `__init__`이 패널을 만들기 전에 `invalidate_results`가 신호로 불리지 않도록, 신호 연결은 지금처럼 `__init__` 끝에 둔다.

- [ ] **Step 5: 회귀 확인**

Run: `uv run --no-sync pytest tests/test_phase2_search_results.py tests/test_gui_search_output.py tests/test_gui_search_parity.py tests/test_gui_search_inspector.py tests/test_gui_search_cancel.py tests/test_gui_round5_p2.py tests/test_gui_editors_builder.py tests/test_phase2_argv_parity.py -q`
Expected: 모두 통과. 실패가 있으면 위임이 빠진 이름이다. 테스트를 고치지 말고 위임을 더한다.

- [ ] **Step 6: Commit**

```bash
git add cmig/gui/search_results.py cmig/gui/builder.py tests/test_phase2_search_results.py
git commit -m "refactor(gui): ranked results become a reusable SearchResultsPanel

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 7: 화면 목록 13개 — 사이드바·메뉴 묶음과 창의 화면 등록부

이 작업은 화면 키와 묶음만 바꾼다. 아직 나뉘지 않은 키는 지금 화면을 임시로 가리키고, 나누는 작업(8–12)이 하나씩 바꾼다.

**Files:**
- Modify: `cmig/gui/sidebar.py` (`ANALYSIS_GROUPS`, `ANALYSES`, `_fill_analyses`; `ANALYSIS_SEPARATOR_AFTER` 제거)
- Modify: `cmig/gui/app.py` (import, `analysis_pages`, `_run_buttons`, `_DESCRIPTIONS`, Analysis 메뉴, `show_analysis`)
- Modify: `cmig/gui/project_session.py` (`_KIND_LABELS`에 `"check-growth": "Check Growth"`, `"single": "Check Growth"`)
- Modify: `tests/test_app_shell.py`, `tests/test_workspace_sidebar.py`
- Create: `tests/test_phase2_shell.py`

**Interfaces:**
- Produces (`cmig.gui.sidebar`):
```python
ANALYSIS_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Community", [("search", "Combination Search"), ("gene_ko", "Gene Knockout"),
                   ("strain_growth", "Strain Growth"), ("ratio_impact", "Ratio Impact"),
                   ("community", "Community Solve")]),
    ("Host", [("host", "Host–Microbe"), ("host_search", "Host Combination Search")]),
    ("Dynamics", [("dfba", "dFBA"), ("spatial", "Spatial Preview")]),
    ("Tools", [("medium", "Medium Editor"), ("sweep", "Sweep"),
               ("sandbox", "Constraint Sandbox"), ("compare", "Compare Runs")]),
]
ANALYSES: list[tuple[str, str]] = [item for _title, items in ANALYSIS_GROUPS for item in items]
```
- Produces (창): `analysis_pages: dict[str, QWidget]`(키 13개), `_run_buttons() -> dict[str, QAbstractButton]`(실행 버튼이 하나인 화면만), `_DESCRIPTIONS`(키 13개)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_phase2_shell.py`:
```python
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown  # noqa: E402,F401
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.sidebar import ANALYSES, ANALYSIS_GROUPS  # noqa: E402

APP = QApplication.instance() or QApplication([])
KEYS = ["search", "gene_ko", "strain_growth", "ratio_impact", "community", "host",
        "host_search", "dfba", "spatial", "medium", "sweep", "sandbox", "compare"]


def test_thirteen_analyses_in_four_groups() -> None:
    assert [key for key, _label in ANALYSES] == KEYS
    assert [title for title, _items in ANALYSIS_GROUPS] == ["Community", "Host", "Dynamics",
                                                            "Tools"]


def test_sidebar_separates_the_groups() -> None:
    w = build_main_window()
    group = w.sidebar.topLevelItem(2)
    keys = [group.child(i).data(0, Qt.ItemDataRole.UserRole)
            for i in range(group.childCount())]
    assert keys == ["search", "gene_ko", "strain_growth", "ratio_impact", "community", None,
                    "host", "host_search", None, "dfba", "spatial", None,
                    "medium", "sweep", "sandbox", "compare"]


def test_every_key_has_a_page_a_menu_action_and_a_description() -> None:
    w = build_main_window()
    assert list(w.analysis_pages) == KEYS
    assert set(w.analysis_actions) == set(KEYS)
    assert set(w._DESCRIPTIONS) == set(KEYS)
    for key in KEYS:
        w.show_analysis(key)
        assert w.pages.currentWidget() is w.analysis_pages[key]
        assert w.inspector.title_label.text() == dict(ANALYSES)[key]
```

- [ ] **Step 2: 실패 확인**

Run: `uv run --no-sync pytest tests/test_phase2_shell.py -q`
Expected: FAIL — `ImportError: ANALYSIS_GROUPS`.

- [ ] **Step 3: 사이드바**

`cmig/gui/sidebar.py`에서 `ANALYSES`와 `ANALYSIS_SEPARATOR_AFTER` 정의를 위 Interfaces의 두 정의로 바꾸고, `_fill_analyses`를 다음으로 바꾼다:
```python
    def _fill_analyses(self) -> None:
        group = self._groups["analyses"]
        for index, (_title, items) in enumerate(ANALYSIS_GROUPS):
            if index:
                separator = QTreeWidgetItem(["──────────"])
                separator.setFlags(Qt.ItemFlag.NoItemFlags)
                separator.setData(0, _ROLE, None)
                group.addChild(separator)
            for key, label in items:
                item = QTreeWidgetItem([label])
                item.setData(0, _ROLE, key)
                group.addChild(item)
```

- [ ] **Step 4: 창**

`cmig/gui/app.py`:
1. import에서 `ANALYSIS_SEPARATOR_AFTER`를 `ANALYSIS_GROUPS`로 바꾼다.
2. `self.analysis_pages`를 키 13개로 바꾼다. 아직 나뉘지 않은 키는 지금 화면을 가리킨다:
```python
        self.analysis_pages: dict[str, QWidget] = {
            "search": self.search_view,
            "gene_ko": self.search_view,        # Task 8 replaces
            "strain_growth": self.search_view,  # Task 8 replaces
            "ratio_impact": self.search_view,   # Task 8 replaces
            "community": self.community_builder,
            "host": self.host_view,
            "host_search": self.host_view,      # Task 10 replaces
            "dfba": self.dynamics_view,
            "spatial": self.dynamics_view,      # Task 11 replaces
            "medium": self.medium_editor,       # Task 12 wraps
            "sweep": self.sweep_view,           # Task 12 wraps
            "sandbox": self.sandbox_view,       # Task 12 wraps
            "compare": self.scenario_compare,   # Task 12 wraps
        }
```
3. `_run_buttons`:
```python
        return {
            "search": self.search_view.run_btn,
            "gene_ko": self.search_view.run_ko_btn,
            "strain_growth": self.search_view.run_growth_btn,
            "ratio_impact": self.search_view.run_abundance_btn,
            "community": self.community_builder.run_btn,
            "host": self.host_view.run_btn,
            "host_search": self.host_view.run_search_btn,
            "dfba": self.dynamics_view.run_dfba_btn,
            "spatial": self.dynamics_view.run_spatial_btn,
            "medium": self.medium_editor.check_growth_btn,
            "sweep": self.sweep_view.run_btn,
        }
```
4. `_DESCRIPTIONS`:
```python
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
```
5. Analysis 메뉴를 묶음마다 구분선으로 만든다:
```python
        analysis_menu = bar.addMenu("&Analysis")
        for index, (_title, items) in enumerate(ANALYSIS_GROUPS):
            if index:
                analysis_menu.addSeparator()
            for key, _label in items:
                analysis_menu.addAction(self.analysis_actions[key])
        analysis_menu.addSeparator()
        analysis_menu.addActions([self.run_action, self.cancel_job_action])
```
6. `show_analysis`의 스크롤 분기를 새 키로 바꾼다(임시, Task 8이 지운다):
```python
        if key == "gene_ko":
            self.search_view.scroll_area.ensureWidgetVisible(self.search_view.ko_members_input)
        elif key in ("strain_growth", "ratio_impact"):
            self.search_view.scroll_area.ensureWidgetVisible(self.search_view.growth_member_input)
```
7. `_refresh_pickers`·`_model_pickers`의 picker 키 `"dynamics"`를 `"dfba"`로 바꾼다(Task 2의 설정 이전이 옛 `dynamics` 값을 `dfba`로 옮긴다). `_PICKER_LABELS`의 `"dynamics": "Dynamics"`도 `"dfba": "dFBA"`로 바꾼다.

- [ ] **Step 5: 기존 테스트 옮기기**

- `tests/test_app_shell.py`: `ANALYSIS_SEPARATOR_AFTER` import를 지운다. `test_advanced_tools_are_listed_apart_and_open_on_request`는 Tools 묶음을 확인하도록 바꾼다: `advanced = [key for key, _l in dict(ANALYSIS_GROUPS)["Tools"]]`, 기대값 `["medium", "sweep", "sandbox", "compare"]`, 화면 목록 `[w.medium_editor, w.sweep_view, w.sandbox_view, w.scenario_compare]`, 그리고 `w.show_analysis(key)` 후 `w.pages.currentWidget() is w.analysis_pages[key]`. Community Solve 문구 확인은 따로 `w.show_analysis("community")` 뒤에 둔다.
- `tests/test_workspace_sidebar.py`: `keys[:5]` 기대값을 `["search", "gene_ko", "strain_growth", "ratio_impact", "community"]`로 바꾼다.

- [ ] **Step 6: 통과 확인**

Run: `uv run --no-sync pytest tests/test_phase2_shell.py tests/test_app_shell.py tests/test_workspace_sidebar.py tests/test_workspace_shell.py tests/test_workspace_analysis_inputs.py tests/test_phase2_argv_parity.py -q`
Expected: 모두 통과.

- [ ] **Step 7: Commit**

```bash
git add cmig/gui/sidebar.py cmig/gui/app.py cmig/gui/project_session.py tests/test_phase2_shell.py tests/test_app_shell.py tests/test_workspace_sidebar.py
git commit -m "feat(gui): thirteen analyses in four sidebar groups

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 8: Combination Search를 틀에 옮기고 Gene Knockout·Strain Growth·Ratio Impact 화면 분리

**Files:**
- Modify: `cmig/gui/search_results.py` (`area` 인자: 결과가 생기고 사라질 때 `ResultsArea`를 따라 바꿈)
- Modify: `cmig/gui/builder.py` (`SearchView`를 `AnalysisPage` 기반으로; Gene KO·Growth·Ratio 위젯 제거)
- Create: `cmig/gui/pages/__init__.py`, `cmig/gui/pages/gene_ko.py`, `cmig/gui/pages/strain_growth.py`, `cmig/gui/pages/ratio_impact.py`
- Modify: `cmig/gui/app.py` (화면 생성·등록, 선택기 기억 키, `run_gene_ko_search`·`run_strain_growth_report`·`run_abundance_impact`, 완료 처리 통합, `show_analysis` 임시 스크롤 제거)
- Modify: `tests/argv_drivers.py` (`gene_ko`, `strain_growth`, `ratio_impact`)
- Create: `tests/test_phase2_community_pages.py`
- Modify (옮기기): `tests/test_app_shell.py`, `tests/test_gui_round5_p2.py`, `tests/test_workspace_activity_flow.py`, `tests/test_workspace_analysis_inputs.py`, `tests/test_gui_search_parity.py`, `tests/test_gui_search_output.py`

**Interfaces:**
- Consumes: `AnalysisPage`, `connect_change`(Task 4), `SearchResultsPanel`(Task 6)
- Produces:
  - `SearchResultsPanel(request_fields, status=None, area: ResultsArea | None = None)` — `load_summary`가 끝나면 `area.show_results()`, `invalidate_results`가 실제로 결과를 지우면 `area.show_empty()`
  - `SearchView(AnalysisPage)`: 제목 "Combination Search", `run_btn`("Run Search"), `cancel_btn`, `advanced_toggle`(= `advanced.toggle`), `advanced_box`(= `advanced.body`), `REQUEST_FIELDS`는 `"search"`, `"host_search"`만
  - `GeneKoPage(AnalysisPage)`: `model_picker`, `medium_picker`, `members_picker`(ModelPicker "Combination"), `member_combo`(QComboBox, 첫 항목 "All members" 데이터 ""), `target_input`, `direction_combo`, `genes_input`, `max_genes_spin`, `top_k_spin`, `growth_fraction_spin`, `results_panel`, `request_fields(kind) -> dict[str, str]`
  - `StrainGrowthPage(AnalysisPage)`: `model_picker`, `medium_picker`, `cooperative_tradeoff_spin`, `results_panel`, `request_fields(kind)`
  - `RatioImpactPage(AnalysisPage)`: `model_picker`, `medium_picker`, `member_combo`(첫 항목 "choose…" 데이터 ""), `fractions_input`, `target_input`, `cooperative_tradeoff_spin`, `results_panel`, `request_fields(kind)`
  - 창: `gene_ko_page`, `strain_growth_page`, `ratio_impact_page`, `_page_run_inputs(page, kind, medium_ref) -> tuple[Path, Path | None, str | None] | None`, `_ranked_spec(key)`, `_show_ranked(key, payload, out_dir, requested)`, `_finish_ranked_jobs(key, jobs, failure_label)`
  - 선택기 기억 키: 모델 `"gene_ko"`, `"strain_growth"`, `"ratio_impact"`, 배지 `("gene_ko","medium")`, `("strain_growth","medium")`, `("ratio_impact","medium")`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_phase2_community_pages.py`:
```python
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402

APP = QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path: Path, monkeypatch):
    make_project(tmp_path / "p", ["a", "b", "c"])
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(tmp_path / "p")
    calls: list[list[str]] = []
    monkeypatch.setattr("cmig.cli.main.main", lambda argv: (calls.append(list(argv)), 2)[1])
    yield w, calls
    w.close_project()


def test_each_workflow_has_its_own_page(window) -> None:
    w, _calls = window
    assert w.analysis_pages["gene_ko"] is w.gene_ko_page
    assert w.analysis_pages["strain_growth"] is w.strain_growth_page
    assert w.analysis_pages["ratio_impact"] is w.ratio_impact_page
    assert not hasattr(w.search_view, "ko_members_input")
    assert not hasattr(w.search_view, "growth_member_input")
    for page in (w.search_view, w.gene_ko_page, w.strain_growth_page, w.ratio_impact_page):
        assert not page.results.has_results(), "no result until a run"


def test_gene_ko_combination_follows_the_models(window) -> None:
    w, _calls = window
    page = w.gene_ko_page
    page.model_picker.set_selected(["a", "b"])
    assert page.members_picker.choice_ids() == ["a", "b"]
    assert page.members_picker.selected_ids() == [], "no combination is assumed"
    page.members_picker.set_selected(["a", "b"])
    items = [page.member_combo.itemText(i) for i in range(page.member_combo.count())]
    assert items == ["All members", "a", "b"]
    page.member_combo.setCurrentText("b")
    page.model_picker.set_selected(["a"])
    assert page.members_picker.selected_ids() == ["a"]
    assert page.member_combo.currentText() == "All members", "b left the combination"


def test_gene_ko_refuses_without_combination_or_target(window) -> None:
    w, calls = window
    page = w.gene_ko_page
    page.model_picker.set_selected(["a", "b"])
    assert w.run_gene_ko_search() == ""
    assert "KO members are required" in page.status.text()
    page.members_picker.set_selected(["a"])
    page.target_input.setText("")
    assert w.run_gene_ko_search() == ""
    assert "does not substitute a default target" in page.status.text()
    assert calls == []


def test_ratio_member_comes_from_the_models(window) -> None:
    w, calls = window
    page = w.ratio_impact_page
    page.model_picker.set_selected(["b", "c"])
    items = [page.member_combo.itemText(i) for i in range(page.member_combo.count())]
    assert items == ["choose…", "b", "c"]
    assert w.run_abundance_impact() == ""
    assert "Target member is required" in page.status.text()
    assert calls == []


def test_ranked_result_lands_on_its_own_page(window, tmp_path: Path) -> None:
    w, _calls = window
    payload = {"target": "ac", "ko_level": "gene", "warnings": [],
               "top_ranked": [{"member": "a", "gene": "g1", "score": 1.0, "target_flux": 2.0,
                               "community_growth": 0.3, "evaluation_status": "optimal"}]}
    w._show_ranked("gene_ko", payload, tmp_path, w.gene_ko_page.request_fields("gene_ko"))
    assert w.pages.currentWidget() is w.gene_ko_page
    assert w.gene_ko_page.results.has_results()
    assert w.gene_ko_page.results_panel.table.item(0, 0).text() == "a:g1"
    assert w.search_view.results_panel.table.rowCount() == 0, "Search keeps its own result"


def test_search_advanced_counts_changes(window) -> None:
    w, _calls = window
    page = w.search_view
    assert page.advanced.changed_count() == 0
    page.strategy_combo.setCurrentText("exhaustive")
    page.seed_spin.setValue(3)
    assert page.advanced.toggle.text() == "Advanced options · 2 changed"
    assert page.advanced_toggle is page.advanced.toggle


def test_remembered_choice_per_page(window) -> None:
    w, _calls = window
    w.strain_growth_page.model_picker.set_selected(["b"])
    assert w.session.settings("strain_growth")["models"] == ["b"]
    assert w.session.settings("gene_ko").get("models") != ["b"]
```

- [ ] **Step 2: 실패 확인**

Run: `uv run --no-sync pytest tests/test_phase2_community_pages.py -q`
Expected: FAIL — `AttributeError: … has no attribute 'gene_ko_page'`.

- [ ] **Step 3: `SearchResultsPanel`의 `area` 인자**

`cmig/gui/search_results.py`:
- 생성자에 `area: ResultsArea | None = None`을 더하고 `self._area = area`로 둔다(`from cmig.gui.analysis_page import ResultsArea`).
- `load_summary` 끝(`self.refresh_figure_mode()` 다음)에 `if self._area is not None: self._area.show_results()`를 더한다.
- `invalidate_results`에서 결과를 실제로 지우는 경로의 끝(`self.status.setText("Inputs changed — …")` 다음)에 `if self._area is not None: self._area.show_empty()`를 더한다.

- [ ] **Step 4: 화면 세 개 작성**

`cmig/gui/pages/__init__.py`:
```python
"""Analysis pages split out of the old multi-workflow tabs (phase 2)."""
```

`cmig/gui/pages/gene_ko.py`:
```python
"""Gene Knockout: rank single-gene knockouts of one fixed combination."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QLineEdit, QSpinBox

from cmig.gui.analysis_page import AnalysisPage, connect_change
from cmig.gui.builder import TARGET_DIRECTIONS
from cmig.gui.pickers import MediumPicker, ModelPicker
from cmig.gui.search_results import SearchResultsPanel

ALL_MEMBERS = "All members"


class GeneKoPage(AnalysisPage):
    REQUEST_FIELDS = (
        "models", "target", "ko_members", "ko_member", "ko_genes", "max_genes", "ko_top_k",
        "medium", "direction", "growth_fraction",
    )

    def __init__(self) -> None:
        super().__init__(
            "Gene Knockout",
            "Rank single-gene knockouts of one fixed combination. A chosen medium is "
            "applied exactly.",
            run_text="Rank Gene KOs",
            cancel=False,
        )
        self.model_picker = ModelPicker("Models")
        self.medium_picker = MediumPicker()
        self.members_picker = ModelPicker("Combination")
        self.member_combo = QComboBox()
        self.member_combo.addItem(ALL_MEMBERS, "")
        self.target_input = QLineEdit("but")
        self.target_input.setPlaceholderText("Target metabolite, e.g. but")
        self.direction_combo = QComboBox()
        self.direction_combo.addItems(list(TARGET_DIRECTIONS))
        self.genes_input = QLineEdit("")
        self.genes_input.setPlaceholderText("Optional gene ids; blank = auto genes")
        self.max_genes_spin = QSpinBox()
        self.max_genes_spin.setRange(0, 10000)
        self.max_genes_spin.setValue(50)
        self.top_k_spin = QSpinBox()  # gene-ko-search default 20, separate from Search top-k
        self.top_k_spin.setRange(1, 100)
        self.top_k_spin.setValue(20)
        self.growth_fraction_spin = QDoubleSpinBox()
        self.growth_fraction_spin.setRange(0.001, 1.0)
        self.growth_fraction_spin.setDecimals(3)
        self.growth_fraction_spin.setValue(0.5)
        self.add_input_row(self.model_picker, "Medium", self.medium_picker)
        self.add_input_row(self.members_picker, "Edited member", self.member_combo)
        self.add_input_row("Target", self.target_input, "Direction", self.direction_combo)
        self.advanced.add_row("Gene IDs", self.genes_input)
        self.advanced.add_row("Max genes/member", self.max_genes_spin, "KO Top K",
                              self.top_k_spin, "Target growth fraction",
                              self.growth_fraction_spin)
        self.advanced.track(self.genes_input, self.max_genes_spin, self.top_k_spin,
                            self.growth_fraction_spin)
        self.results_panel = SearchResultsPanel(self.request_fields, status=self.status,
                                                area=self.results)
        self.results.add(self.results_panel, 1)
        for name, widget in (
            ("models", self.model_picker), ("medium", self.medium_picker),
            ("members", self.members_picker), ("member", self.member_combo),
            ("target", self.target_input), ("direction", self.direction_combo),
            ("genes", self.genes_input), ("max_genes", self.max_genes_spin),
            ("top_k", self.top_k_spin), ("growth_fraction", self.growth_fraction_spin),
        ):
            self.register(name, widget)
        self.model_picker.selection_changed.connect(self._pool_changed)
        self.members_picker.selection_changed.connect(self._combination_changed)
        for widget in (self.model_picker, self.medium_picker, self.members_picker,
                       self.member_combo, self.target_input, self.direction_combo,
                       self.genes_input, self.max_genes_spin, self.top_k_spin,
                       self.growth_fraction_spin):
            connect_change(widget, lambda *_a: self.results_panel.invalidate_results(True))

    def _pool_changed(self) -> None:
        kept = self.members_picker.selected_ids()
        pool = self.model_picker.selected_ids()
        self.members_picker.set_choices([(model_id, True, "") for model_id in pool])
        self.members_picker.set_selected([m for m in kept if m in pool])

    def _combination_changed(self) -> None:
        current = str(self.member_combo.currentData() or "")
        members = self.members_picker.selected_ids()
        blocked = self.member_combo.blockSignals(True)
        try:
            self.member_combo.clear()
            self.member_combo.addItem(ALL_MEMBERS, "")
            for member in members:
                self.member_combo.addItem(member, member)
            index = self.member_combo.findData(current) if current in members else 0
            self.member_combo.setCurrentIndex(max(index, 0))
        finally:
            self.member_combo.blockSignals(blocked)

    def request_fields(self, kind: str) -> dict[str, str]:
        if kind != "gene_ko":
            return {}
        return {
            "models": ",".join(self.model_picker.selected_ids()),
            "target": self.target_input.text().strip(),
            "ko_members": ",".join(self.members_picker.selected_ids()),
            "ko_member": str(self.member_combo.currentData() or ""),
            "ko_genes": self.genes_input.text().strip(),
            "max_genes": str(self.max_genes_spin.value()),
            "ko_top_k": str(self.top_k_spin.value()),
            "medium": self.medium_picker.current_ref(),
            "direction": self.direction_combo.currentText(),
            "growth_fraction": str(self.growth_fraction_spin.value()),
        }
```
(`set_choices`는 처음 받은 목록을 모두 체크하므로, `_pool_changed`가 이전 선택만 남겨 "조합을 가정하지 않는다"를 지킨다.)

`cmig/gui/pages/strain_growth.py`:
```python
"""Strain Growth: each member's growth alone and inside the community."""

from __future__ import annotations

from PySide6.QtWidgets import QDoubleSpinBox

from cmig.gui.analysis_page import AnalysisPage, connect_change
from cmig.gui.pickers import MediumPicker, ModelPicker
from cmig.gui.search_results import SearchResultsPanel


def tradeoff_spin() -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(0.01, 1.0)
    spin.setDecimals(2)
    spin.setSingleStep(0.05)
    spin.setValue(0.5)
    return spin


class StrainGrowthPage(AnalysisPage):
    REQUEST_FIELDS = ("models", "medium", "cooperative_tradeoff")

    def __init__(self) -> None:
        super().__init__(
            "Strain Growth",
            "Growth of each selected strain alone and in the community. A chosen medium is "
            "applied exactly.",
            run_text="Run Strain Growth",
            cancel=False,
        )
        self.model_picker = ModelPicker("Models")
        self.medium_picker = MediumPicker()
        self.cooperative_tradeoff_spin = tradeoff_spin()
        self.add_input_row(self.model_picker, "Medium", self.medium_picker)
        self.advanced.add_row("Cooperative tradeoff f", self.cooperative_tradeoff_spin)
        self.advanced.track(self.cooperative_tradeoff_spin)
        self.results_panel = SearchResultsPanel(self.request_fields, status=self.status,
                                                area=self.results)
        self.results.add(self.results_panel, 1)
        for name, widget in (("models", self.model_picker), ("medium", self.medium_picker),
                             ("tradeoff", self.cooperative_tradeoff_spin)):
            self.register(name, widget)
            connect_change(widget, lambda *_a: self.results_panel.invalidate_results(True))

    def request_fields(self, kind: str) -> dict[str, str]:
        if kind != "strain_growth":
            return {}
        return {
            "models": ",".join(self.model_picker.selected_ids()),
            "medium": self.medium_picker.current_ref(),
            "cooperative_tradeoff": str(self.cooperative_tradeoff_spin.value()),
        }
```

`cmig/gui/pages/ratio_impact.py`:
```python
"""Ratio Impact: how one member's share of the community changes a target metabolite."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QLineEdit

from cmig.gui.analysis_page import AnalysisPage, connect_change
from cmig.gui.pages.strain_growth import tradeoff_spin
from cmig.gui.pickers import MediumPicker, ModelPicker
from cmig.gui.search_results import SearchResultsPanel

CHOOSE = "choose…"


class RatioImpactPage(AnalysisPage):
    REQUEST_FIELDS = ("models", "target", "growth_member", "fractions", "medium",
                      "cooperative_tradeoff")

    def __init__(self) -> None:
        super().__init__(
            "Ratio Impact",
            "Change one member's share of the community and see how a target metabolite "
            "responds. A chosen medium is applied exactly.",
            run_text="Run Ratio Impact",
            cancel=False,
        )
        self.model_picker = ModelPicker("Models")
        self.medium_picker = MediumPicker()
        self.member_combo = QComboBox()
        self.member_combo.addItem(CHOOSE, "")
        self.fractions_input = QLineEdit("0.1,0.25,0.5,0.75")
        self.fractions_input.setPlaceholderText("Fractions, e.g. 0.1,0.25,0.5,0.75")
        self.target_input = QLineEdit("but")
        self.target_input.setPlaceholderText("Target metabolite, e.g. but")
        self.cooperative_tradeoff_spin = tradeoff_spin()
        self.add_input_row(self.model_picker, "Medium", self.medium_picker)
        self.add_input_row("Member", self.member_combo, "Fractions", self.fractions_input)
        self.add_input_row("Target", self.target_input)
        self.advanced.add_row("Cooperative tradeoff f", self.cooperative_tradeoff_spin)
        self.advanced.track(self.cooperative_tradeoff_spin)
        self.results_panel = SearchResultsPanel(self.request_fields, status=self.status,
                                                area=self.results)
        self.results.add(self.results_panel, 1)
        for name, widget in (("models", self.model_picker), ("medium", self.medium_picker),
                             ("member", self.member_combo), ("fractions", self.fractions_input),
                             ("target", self.target_input),
                             ("tradeoff", self.cooperative_tradeoff_spin)):
            self.register(name, widget)
            connect_change(widget, lambda *_a: self.results_panel.invalidate_results(True))
        self.model_picker.selection_changed.connect(self._pool_changed)

    def _pool_changed(self) -> None:
        current = str(self.member_combo.currentData() or "")
        pool = self.model_picker.selected_ids()
        blocked = self.member_combo.blockSignals(True)
        try:
            self.member_combo.clear()
            self.member_combo.addItem(CHOOSE, "")
            for member in pool:
                self.member_combo.addItem(member, member)
            index = self.member_combo.findData(current) if current in pool else 0
            self.member_combo.setCurrentIndex(max(index, 0))
        finally:
            self.member_combo.blockSignals(blocked)

    def request_fields(self, kind: str) -> dict[str, str]:
        if kind != "abundance_impact":
            return {}
        return {
            "models": ",".join(self.model_picker.selected_ids()),
            "target": self.target_input.text().strip(),
            "growth_member": str(self.member_combo.currentData() or ""),
            "fractions": self.fractions_input.text().strip(),
            "medium": self.medium_picker.current_ref(),
            "cooperative_tradeoff": str(self.cooperative_tradeoff_spin.value()),
        }
```

- [ ] **Step 5: `SearchView`를 Combination Search 화면으로**

`cmig/gui/builder.py`의 `SearchView`:
1. `class SearchView(AnalysisPage)`로 바꾸고, `__init__` 첫 줄을 `super().__init__("Combination Search", "Rank model combinations by a target metabolite.", run_text="Run Search")`로 바꾼다. 자체 `outer`/`scroll_area`/`content`/`layout` 생성, `self.title`, `self.run_btn`, `self.cancel_btn` 생성 줄을 지운다(틀이 만든다. `cancel_btn`은 틀의 "Cancel"이다).
2. 지우는 위젯과 줄: `ko_*` 입력 다섯 개와 `run_ko_btn`, `growth_member_input`, `abundance_fractions_input`, `run_growth_btn`, `run_abundance_btn`, `cooperative_tradeoff_spin`, `ko_row`/`ko_action_row`/`growth_row`/`growth_action_row`/`tradeoff_row`, `workflow_note`. 신호 연결 목록에서도 이 위젯들을 지운다.
3. `target_note` 문구를 `"Each row is a target. Weight and Reference apply when there are two or more rows."`로 바꾼다.
4. 입력 카드(`self.add_input_row` / `self.inputs.addWidget`) 순서: (모델 선택기, "Medium", 배지 선택기) → `medium_mode_summary` → `target_note` → `target_table` → `target_btn_row`(Add·Remove·Fill from preset·"Multi-target metric"·metric 콤보) → `weight_note` → `reference_warning_label` → ("Size", `min_size_spin`, "to", `max_size_spin`).
5. Advanced(`self.advanced.add_row` / `self.advanced.body_layout`) 순서: ("Strategy", `strategy_combo`, "Top K", `search_top_k_spin`, `robustness_check`) → ("Seed", `seed_spin`, "Workers", `workers_spin`) → ("Growth fraction", `growth_fraction_spin`, "Member growth ≥", `min_member_growth_spin`, "Community growth ≥", `min_community_growth_spin`) → ("Validate top (extra solves)", `validation_top_spin`, "Per-solve timeout (s)", `solve_timeout_spin`) → `checkpoint_row`(checkpoint 입력·Browse·Resume; 옛 `cancel_btn`은 빼고 틀의 것을 쓴다) → `_build_advanced_settings()`가 만들던 내용. `_build_advanced_settings`는 자체 `advanced_toggle`/`advanced_box`를 만들지 말고 `box = self.advanced.body_layout`에 줄을 더하도록 바꾸며, `self.advanced_toggle = self.advanced.toggle`, `self.advanced_box = self.advanced.body`로 둔다. `_toggle_advanced`와 `advanced_toggle.toggled.connect(self._toggle_advanced)`는 지운다.
6. `self.advanced.track(...)`에 Advanced의 모든 입력을 넘긴다: `strategy_combo, search_top_k_spin, robustness_check, seed_spin, workers_spin, growth_fraction_spin, min_member_growth_spin, min_community_growth_spin, validation_top_spin, solve_timeout_spin, checkpoint_input, resume_check, exhaustive_max_spin, n_samples_spin, ga_pop_size_spin, ga_generations_spin, ga_mutation_rate_spin, ga_immigrant_fraction_spin, ga_tournament_k_spin, ga_elitism_spin, ga_budget_spin, ga_patience_spin, ga_restart_after_spin, ga_local_search_fraction_spin, ga_preserve_common_check, solver_threads_spin, pareto_resolution_spin, medium_mode_combo, allow_unknown_medium_check`.
7. 결과: `self.results_panel = SearchResultsPanel(self.request_fields, status=self.status, area=self.results)`, `self.results.add(self.results_panel, 1)`. Task 6에서 만든 위임은 그대로 둔다(`status` 별칭은 이제 틀의 `status`와 같은 객체다).
8. `REQUEST_FIELDS`에서 `"gene_ko"`, `"strain_growth"`, `"abundance_impact"` 항목을 지우고, `request_fields`의 snapshot에서 `ko_top_k`, `ko_members`, `ko_member`, `ko_genes`, `max_genes`, `growth_member`, `fractions`, `cooperative_tradeoff`를 지운다.
9. 입력 등록(복원용, 모델 선택기를 먼저):
```python
        self.register("models", self.model_picker)
        self.register("medium", self.medium_picker)
        self.register_custom("targets", lambda: [list(r) for r in self.target_rows()],
                             self._restore_targets)
        for name, widget in (
            ("multi_metric", self.multi_metric_combo), ("min_size", self.min_size_spin),
            ("max_size", self.max_size_spin), ("strategy", self.strategy_combo),
            ("top_k", self.search_top_k_spin), ("fva", self.robustness_check),
            ("seed", self.seed_spin), ("workers", self.workers_spin),
            ("growth_fraction", self.growth_fraction_spin),
            ("min_member_growth", self.min_member_growth_spin),
            ("min_community_growth", self.min_community_growth_spin),
            ("validate_top", self.validation_top_spin), ("timeout", self.solve_timeout_spin),
            ("checkpoint", self.checkpoint_input), ("resume", self.resume_check),
            ("exhaustive_max", self.exhaustive_max_spin), ("n_samples", self.n_samples_spin),
            ("ga_pop_size", self.ga_pop_size_spin), ("ga_generations", self.ga_generations_spin),
            ("ga_mutation_rate", self.ga_mutation_rate_spin),
            ("ga_immigrant_fraction", self.ga_immigrant_fraction_spin),
            ("ga_tournament_k", self.ga_tournament_k_spin), ("ga_elitism", self.ga_elitism_spin),
            ("ga_budget", self.ga_budget_spin), ("ga_patience", self.ga_patience_spin),
            ("ga_restart_after", self.ga_restart_after_spin),
            ("ga_local_search_fraction", self.ga_local_search_fraction_spin),
            ("ga_preserve_common", self.ga_preserve_common_check),
            ("solver_threads", self.solver_threads_spin),
            ("pareto_resolution", self.pareto_resolution_spin),
            ("medium_mode", self.medium_mode_combo),
            ("allow_unknown_medium", self.allow_unknown_medium_check),
        ):
            self.register(name, widget)

    def _restore_targets(self, rows: object) -> str | None:
        try:
            self.set_target_rows([tuple(str(cell) for cell in row) for row in rows])  # type: ignore[union-attr]
        except (TypeError, ValueError) as exc:
            return f"targets could not be restored ({exc})"
        return None
```
10. `_refresh_target_notes` 끝에 Multi-target metric을 2행 이상일 때만 보이게 한다: `self.multi_metric_combo.setVisible(self.target_table.rowCount() >= 2)`와 그 라벨(지역 변수였다면 `self.multi_metric_label`로 만들어)도 같이 숨긴다.

- [ ] **Step 6: 창 연결**

`cmig/gui/app.py`:
1. import: `from cmig.gui.pages.gene_ko import GeneKoPage`, `from cmig.gui.pages.ratio_impact import RatioImpactPage`, `from cmig.gui.pages.strain_growth import StrainGrowthPage`.
2. `self.search_view = SearchView()` 옆에 `self.gene_ko_page = GeneKoPage()`, `self.strain_growth_page = StrainGrowthPage()`, `self.ratio_impact_page = RatioImpactPage()`. `analysis_pages`의 세 키를 이 화면으로 바꾼다.
3. `_run_buttons`의 세 키를 `self.gene_ko_page.run_btn`, `self.strain_growth_page.run_btn`, `self.ratio_impact_page.run_btn`으로 바꾼다.
4. `_connect_view_actions`에서 `search_view.run_ko_btn`/`run_growth_btn`/`run_abundance_btn` 연결을 지우고 다음을 더한다:
```python
        self.gene_ko_page.run_btn.clicked.connect(self.run_gene_ko_search)
        self.strain_growth_page.run_btn.clicked.connect(self.run_strain_growth_report)
        self.ratio_impact_page.run_btn.clicked.connect(self.run_abundance_impact)
        for page in (self.search_view, self.gene_ko_page, self.strain_growth_page,
                     self.ratio_impact_page):
            page.results_panel.export_figure_btn.clicked.connect(
                lambda _c=False, p=page: self._export_ranked_figure(p)
            )
```
그리고 `self.search_view.export_figure_btn.clicked.connect(self._export_search_figure)`를 지운다. `_export_search_figure`를 `_export_ranked_figure(self, page)`로 바꾸고 본문의 `self.search_view`를 `page.results_panel`(상태 문구는 `page.status`)로 바꾼다.
5. `_model_pickers`에 `"gene_ko": self.gene_ko_page.model_picker, "strain_growth": self.strain_growth_page.model_picker, "ratio_impact": self.ratio_impact_page.model_picker`, `_medium_pickers`에 `("gene_ko", "medium")`, `("strain_growth", "medium")`, `("ratio_impact", "medium")` 항목, `_PICKER_LABELS`에 `"gene_ko": "Gene Knockout", "strain_growth": "Strain Growth", "ratio_impact": "Ratio Impact"`을 더한다.
6. `_search_tab_inputs`를 화면을 받도록 바꾼다(이름도 바꾼다):
```python
    def _page_run_inputs(
        self, page: Any, kind: str, medium_ref: str
    ) -> tuple[Path, Path | None, str | None] | None:
        """Claim a run for a page with a model picker: (out, taxonomy, medium file), or None
        after the reason is shown on the page."""
        model_ids = page.model_picker.selected_ids()
        if not model_ids:
            page.status.setText("Select at least one model.")
            return None
        try:
            medium_file = self._medium_arg(medium_ref)
            out_dir, taxonomy = self._prepare_run(kind, model_ids)
        except (ProjectError, ValueError) as exc:
            page.status.setText(str(exc))
            return None
        return out_dir, taxonomy, medium_file
```
7. `run_gene_ko_search`: `self.search_view`를 `page = self.gene_ko_page`로 바꾸고, 대상은 `_single_target([(requested["target"], requested["direction"], "", "")])`로 검사한다. `_search_tab_inputs("gene-ko", …)`는 `_page_run_inputs(page, "gene-ko", …)`로, `run_ko_btn`은 `page.run_btn`으로, 상태 문구는 `page.status`로 바꾼다. argv와 검증 문구는 그대로 둔다.
8. `run_strain_growth_report`와 `run_abundance_impact`도 같은 방식으로 `self.strain_growth_page` / `self.ratio_impact_page`를 쓴다. Ratio Impact의 대상 검사는 `_single_target([(requested["target"], "max_secretion", "", "")])`이다.
9. `_poll_completed_jobs`의 gene KO·strain growth·abundance impact 완료 블록 세 개를 지우고 다음 세 줄로 바꾼다:
```python
        self._finish_ranked_jobs("gene_ko", self._gene_ko_jobs, "gene KO search")
        self._finish_ranked_jobs("strain_growth", self._strain_growth_jobs, "strain growth")
        self._finish_ranked_jobs("ratio_impact", self._abundance_impact_jobs, "ratio impact")
```
그리고 메서드 세 개를 더한다:
```python
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
        }[key]

    def _show_ranked(
        self, key: str, payload: dict[str, Any], out_dir: Path, requested: dict[str, str]
    ) -> None:
        _file, adapter, kind, _label = self._ranked_spec(key)
        page = self.analysis_pages[key]
        panel = page.results_panel  # type: ignore[attr-defined]
        panel.figure_mode_combo.setCurrentText("Ranking")
        panel.load_summary(
            _with_search_conditions(adapter(payload), payload),
            run_dir=out_dir,
            request_note=(panel.effective_note(requested, kind)
                          + panel.superseded_note(requested, kind)),
            workflow_kind=kind,
            executed_request=requested,
            source_summary=payload,
        )
        self._show_page(page)

    def _finish_ranked_jobs(
        self, key: str, jobs: dict[str, tuple[Path, dict[str, str]]], failure_label: str
    ) -> None:
        page = self.analysis_pages[key]
        for jid, (out_dir, requested) in list(jobs.items()):
            job = self.runner.poll(jid)
            if job.status is JobStatus.DONE and isinstance(job.result, dict):
                jobs.pop(jid, None)
                page.run_btn.setEnabled(True)  # type: ignore[attr-defined]
                if self._inspect_gui_run(out_dir) is None:
                    continue
                self.current_search_dir = out_dir
                self._show_ranked(key, job.result, out_dir, requested)
                self._register_run_output(out_dir)
                self._show_status("status_complete_out",
                                  kind=self.tr_map[self._ranked_spec(key)[3]],
                                  job_id=jid, out_dir=out_dir)
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                jobs.pop(jid, None)
                page.run_btn.setEnabled(True)  # type: ignore[attr-defined]
                page.status.setText(  # type: ignore[attr-defined]
                    f"{failure_label} {job.status.value}: {job.error or jid}"
                )
```
(`Callable`이 import되어 있지 않으면 `from collections.abc import Callable`을 더한다.)
10. `show_analysis`의 Task 7 임시 스크롤 분기를 지운다.
11. `_search_with_models`(사이드바 "Search with Selected…")는 그대로 `search_view`를 쓴다.

- [ ] **Step 7: 드라이버 옮기기**

`tests/argv_drivers.py`에서 세 함수의 본문만 바꾼다(`EXPECTED`는 그대로):
```python
def gene_ko(w: Any) -> str:
    v = w.gene_ko_page
    v.model_picker.set_selected(["a", "b", "host"])
    v.medium_picker.set_ref("preset:high_fiber")
    v.target_input.setText("ac")
    v.direction_combo.setCurrentText("min_uptake")
    v.members_picker.set_selected(["a", "b"])
    v.member_combo.setCurrentText("a")
    v.max_genes_spin.setValue(10)
    v.top_k_spin.setValue(5)
    v.growth_fraction_spin.setValue(0.3)
    return w.run_gene_ko_search()


def strain_growth(w: Any) -> str:
    v = w.strain_growth_page
    v.model_picker.set_selected(["a", "b"])
    v.medium_picker.set_ref("preset:high_fiber")
    v.cooperative_tradeoff_spin.setValue(0.4)
    return w.run_strain_growth_report()


def ratio_impact(w: Any) -> str:
    v = w.ratio_impact_page
    v.model_picker.set_selected(["a", "b"])
    v.target_input.setText("but")
    v.member_combo.setCurrentText("b")
    v.fractions_input.setText("0.2,0.8")
    v.cooperative_tradeoff_spin.setValue(0.6)
    return w.run_abundance_impact()
```

- [ ] **Step 8: 기존 테스트 옮기기**

Run: `uv run --no-sync pytest tests/ -q -x -k "gui or workspace or app_shell or phase2" 2>&1 | tail -30`

실패하는 테스트를 같은 의도로 새 화면에 옮긴다. 기준:
- `w.search_view.ko_members_input.setText("a,b")` → `w.gene_ko_page.members_picker.set_selected(["a", "b"])`
- `ko_member_input.setText(x)` → `member_combo.setCurrentText(x)`; `ko_genes_input` → `genes_input`; `ko_max_genes_spin` → `max_genes_spin`; `ko_top_k_spin` → `top_k_spin`
- Gene KO·Ratio의 대상은 `search_view.set_target_rows([...])` 대신 각 화면의 `target_input`(+ Gene KO `direction_combo`)
- `growth_member_input.setText(x)` → `ratio_impact_page.member_combo.setCurrentText(x)`; `abundance_fractions_input` → `ratio_impact_page.fractions_input`
- `cooperative_tradeoff_spin` → 그 화면의 `cooperative_tradeoff_spin`
- 모델 선택은 그 화면의 `model_picker`; 결과 확인은 그 화면의 `results_panel`
- `run_ko_btn`/`run_growth_btn`/`run_abundance_btn` → 그 화면의 `run_btn`
- "Search only"가 들어간 Advanced 제목 단언 → `"Advanced options"`
- 하나의 Search 타깃 표를 Gene KO·Ratio가 함께 쓰는 것을 전제로 한 테스트(예: `test_gui_round5_p2.py`의 빈 Target 테스트)는 "각 화면이 자기 대상을 쓰고, 빈 대상은 거부된다"로 바꾼다. 거부 문구 단언은 유지한다.
- 행동을 바꾸는 수정은 하지 않는다. 옮길 방법이 없는 테스트가 있으면 멈추고 보고한다.

- [ ] **Step 9: 통과 확인**

Run: `uv run --no-sync pytest tests/test_phase2_community_pages.py tests/test_phase2_argv_parity.py tests/test_phase2_shell.py -q && uv run --no-sync pytest tests/ -q -k "gui or workspace or app_shell or phase2" 2>&1 | tail -3`
Expected: 모두 통과.

- [ ] **Step 10: Commit**

```bash
git add cmig/gui tests
git commit -m "feat(gui): Combination Search, Gene Knockout, Strain Growth and Ratio Impact pages

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 9: Community Solve 화면 — 멤버 표가 선택기를 따르고 결과가 화면 안에

**Files:**
- Modify: `cmig/gui/builder.py` (`CommunityBuilderView`)
- Modify: `cmig/gui/app.py` (공동체 결과 위젯을 화면 결과 영역에 둠: `_show_profile(host_key)`, `load_run_dir(..., host_key=...)`, 실행·완료 처리)
- Modify: `tests/argv_drivers.py` (`community`)
- Create: `tests/test_phase2_community_solve.py`
- Modify (옮기기): `tests/test_app_shell.py`, `tests/test_gui_round5_p2.py`, `tests/test_workspace_analysis_inputs.py`, `tests/test_gui_editors_builder.py`

**Interfaces:**
- Produces:
  - `CommunityBuilderView(AnalysisPage)`: 제목 "Community Solve", `run_btn`("Run Community"), `model_picker`("Members"), `assume_bigg_check`, `namespace_decisions_input`, `browse_namespace_decisions_btn`, `namespace_note`(QLabel, Task 15가 씀), `table`(열 Member 읽기 전용·Abundance 편집), `set_abundance(member_id, value)`, `members() -> dict[str, float]`, `invalid_rows`, `f_label`, `f_slider`(Advanced), `tradeoff_f()`, `namespace_policy()`. `add_member`, `remove_member`, `add_member_btn`, `remove_member_btn`는 없어진다.
  - 창: `community_result_page`(QTabWidget, Profile|Graph)는 한 번에 한 화면의 결과 영역에 있다. `_show_profile(host_key: str = "community")`가 그 화면의 결과 영역으로 옮겨 보이고 그 화면을 연다. `load_run_dir(path, host_key: str = "community") -> bool`.
- 규칙: 선택에서 뺐다가 다시 넣은 멤버의 abundance는 1로 돌아간다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_phase2_community_solve.py`:
```python
from __future__ import annotations

import csv
import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402

APP = QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path: Path, monkeypatch):
    make_project(tmp_path / "p", ["a", "b", "c"])
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(tmp_path / "p")
    calls: list[list[str]] = []
    monkeypatch.setattr("cmig.cli.main.main", lambda argv: (calls.append(list(argv)), 2)[1])
    yield w, calls
    w.close_project()


def _rows(view) -> list[tuple[str, str]]:
    return [(view.table.item(r, 0).text(), view.table.item(r, 1).text())
            for r in range(view.table.rowCount())]


def test_member_table_mirrors_the_picker(window) -> None:
    w, _calls = window
    view = w.community_builder
    view.model_picker.set_selected(["a", "b"])
    assert _rows(view) == [("a", "1"), ("b", "1")]
    view.set_abundance("a", 0.25)
    view.model_picker.set_selected(["a", "b", "c"])
    assert _rows(view) == [("a", "0.25"), ("b", "1"), ("c", "1")]
    view.model_picker.set_selected(["b", "c"])
    view.model_picker.set_selected(["a", "b", "c"])
    assert _rows(view)[0] == ("a", "1"), "a re-added member starts at 1 again"
    assert not hasattr(view, "add_member_btn")


def test_member_names_are_read_only(window) -> None:
    from PySide6.QtCore import Qt

    w, _calls = window
    view = w.community_builder
    view.model_picker.set_selected(["a"])
    assert not view.table.item(0, 0).flags() & Qt.ItemFlag.ItemIsEditable
    assert view.table.item(0, 1).flags() & Qt.ItemFlag.ItemIsEditable


def test_bad_abundance_is_refused(window) -> None:
    w, calls = window
    view = w.community_builder
    view.model_picker.set_selected(["a", "b"])
    view.table.item(1, 1).setText("lots")
    view.assume_bigg_check.setChecked(True)
    assert w.run_community_solve() == ""
    assert "row 2" in view.status.text()
    assert calls == []


def test_abundances_reach_the_taxonomy(window) -> None:
    w, calls = window
    view = w.community_builder
    view.model_picker.set_selected(["a", "b"])
    view.set_abundance("b", 3.0)
    view.assume_bigg_check.setChecked(True)
    assert w.run_community_solve()
    deadline = time.time() + 10
    while not calls and time.time() < deadline:
        APP.processEvents()
        time.sleep(0.02)
    path = Path(calls[0][calls[0].index("--taxonomy") + 1])
    rows = {r["id"]: float(r["abundance"]) for r in csv.DictReader(path.open())}
    assert rows == {"a": 1.0, "b": 3.0}


def test_community_result_lives_in_the_page(window) -> None:
    w, _calls = window
    w._show_profile("community")
    assert w.pages.currentWidget() is w.community_builder
    assert w.community_result_page.parent() is not None
    assert w.community_builder.results.has_results()
    assert w.community_result_page.isAncestorOf(w.profile_view)
```

- [ ] **Step 2: 실패 확인**

Run: `uv run --no-sync pytest tests/test_phase2_community_solve.py -q`
Expected: FAIL — `set_abundance` 없음.

- [ ] **Step 3: `CommunityBuilderView` 다시 쓰기**

`cmig/gui/builder.py`의 `CommunityBuilderView`를 다음으로 바꾼다(`namespace_policy`, `_on_f`, `tradeoff_f`는 본문 그대로 둔다):
```python
class CommunityBuilderView(AnalysisPage):
    """Community Solve: the picked members are the table's rows; only abundances are edited."""

    def __init__(self) -> None:
        super().__init__(
            "Community Solve",
            "Community FBA of the selected members. Abundances start at 1; edit them in the "
            "table.",
            run_text="Run Community",
            cancel=False,
        )
        self.model_picker = ModelPicker("Members")
        self.assume_bigg_check = QCheckBox(
            "I reviewed these models and confirm they are already in BiGG namespace"
        )
        self.namespace_decisions_input = QLineEdit("")
        self.namespace_decisions_input.setPlaceholderText(
            "…or a reviewed namespace-decisions JSON file"
        )
        self.browse_namespace_decisions_btn = QPushButton("Decisions")
        self.namespace_note = QLabel("")
        self.namespace_note.setWordWrap(True)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Member", "Abundance"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setMaximumHeight(220)
        #: rows whose abundance could not be parsed on the last members() call
        self.invalid_rows: list[int] = []
        self.add_input_row(self.model_picker)
        self.inputs.addWidget(self.table)
        self.add_input_row(self.assume_bigg_check)
        self.add_input_row(self.namespace_decisions_input, self.browse_namespace_decisions_btn)
        self.inputs.addWidget(self.namespace_note)
        self.f_label = QLabel("tradeoff f: 0.50")
        self.f_slider = QSlider(Qt.Orientation.Horizontal)
        self.f_slider.setRange(1, 100)
        self.f_slider.setValue(50)
        self.f_slider.valueChanged.connect(self._on_f)
        self.advanced.add_row(self.f_label, self.f_slider)
        self.advanced.track(self.f_slider)  # QSlider: see note below
        self.model_picker.selection_changed.connect(self._sync_rows)
        self.register("members", self.model_picker)
        self.register_custom("abundances", self.members_snapshot, self._restore_abundances)
        self.register_custom("tradeoff", lambda: self.f_slider.value(),
                             self._restore_tradeoff)
        self.register("assume_bigg", self.assume_bigg_check)
        self.register("namespace_decisions", self.namespace_decisions_input)
        self._sync_rows()

    def _sync_rows(self) -> None:
        kept = {}
        for row in range(self.table.rowCount()):
            member, value = self.table.item(row, 0), self.table.item(row, 1)
            if member is not None and value is not None:
                kept[member.text()] = value.text()
        chosen = self.model_picker.selected_ids()
        self.table.setRowCount(len(chosen))
        for row, member_id in enumerate(chosen):
            name = read_only_item(member_id)
            self.table.setItem(row, 0, name)
            self.table.setItem(row, 1, QTableWidgetItem(kept.get(member_id, "1")))

    def set_abundance(self, member_id: str, value: float) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.text() == member_id:
                self.table.setItem(row, 1, QTableWidgetItem(f"{value:g}"))
                return
        raise KeyError(f"{member_id!r} is not a selected member")

    def members(self) -> dict[str, float]:
        """Return member→abundance for every row. Unparseable rows are recorded, never skipped.

        Silently dropping a row the user typed would run a *different* community than the
        one on screen, so `invalid_rows` is populated and the caller must refuse to run.
        """
        out: dict[str, float] = {}
        self.invalid_rows = []
        for r in range(self.table.rowCount()):
            mid = self.table.item(r, 0)
            ab = self.table.item(r, 1)
            if mid is None:
                continue
            try:
                out[mid.text()] = float(ab.text()) if ab else 1.0
            except ValueError:
                self.invalid_rows.append(r + 1)
        return out

    def members_snapshot(self) -> dict[str, str]:
        return {
            self.table.item(r, 0).text(): self.table.item(r, 1).text()
            for r in range(self.table.rowCount())
            if self.table.item(r, 0) is not None and self.table.item(r, 1) is not None
        }

    def _restore_abundances(self, values: object) -> str | None:
        if not isinstance(values, dict):
            return "abundances could not be restored"
        for row in range(self.table.rowCount()):
            member = self.table.item(row, 0)
            if member is not None and member.text() in values:
                self.table.setItem(row, 1, QTableWidgetItem(str(values[member.text()])))
        return None

    def _restore_tradeoff(self, value: object) -> str | None:
        try:
            self.f_slider.setValue(int(value))  # type: ignore[call-overload]
        except (TypeError, ValueError):
            return "tradeoff f could not be restored"
        return None
```
`AdvancedSection.track`/`widget_value`/`connect_change`가 `QSlider`를 다루도록 `cmig/gui/analysis_page.py`에 한 줄씩 더한다: `widget_value`에 `if isinstance(widget, QSlider): return widget.value()`, `set_widget_value`에 `elif isinstance(widget, QSlider): widget.setValue(int(value))`, `connect_change`에 `elif isinstance(widget, QSlider): widget.valueChanged.connect(slot)`(`QSlider` import 추가). 이 셋에 대한 테스트 한 줄을 `tests/test_phase2_analysis_page.py`의 `test_advanced_counts_values_changed_from_their_defaults` 끝에 더한다:
```python
    from PySide6.QtWidgets import QSlider

    slider = QSlider()
    page.advanced.track(slider)
    slider.setValue(slider.value() + 1)
    assert page.advanced.changed_count() == 2
```
(이 줄 직전 값은 1이다. 숫자가 맞지 않으면 앞 단언 순서를 확인한다.)

- [ ] **Step 4: 창**

`cmig/gui/app.py`:
1. `_show_profile`를 바꾼다:
```python
    def _show_profile(self, host_key: str = "community") -> None:
        """Show the community result (Profile | Graph) inside `host_key`'s results area."""
        page = self.analysis_pages[host_key]
        previous = self._community_result_host
        if previous is not None and previous != host_key:
            self.analysis_pages[previous].results.show_empty()  # type: ignore[attr-defined]
        if self._community_result_host != host_key:
            page.results.add(self.community_result_page, 1)  # type: ignore[attr-defined]
            self._community_result_host = host_key
        page.results.show_results()  # type: ignore[attr-defined]
        self.community_result_page.setCurrentWidget(self.profile_view)
        self._show_page(page)
```
`__init__`에서 `self._community_result_host: str | None = None`을 두고, `self.pages.addWidget(self.community_result_page)`(페이지 목록에 넣던 줄)에서 `community_result_page`를 뺀다. `analysis_pages`를 만든 뒤 `self._show_profile`을 부르지 말고, 대신 `self.community_builder.results.add(self.community_result_page, 1)`과 `self._community_result_host = "community"`로 처음 자리를 정한다(결과 영역은 비어 있음 상태로 시작).
2. `load_run_dir(self, path, host_key: str = "community")`로 바꾸고 안의 `self._show_profile()`를 `self._show_profile(host_key)`로 바꾼다.
3. `_show_page(self.community_result_page)`를 부르는 곳이 있으면 `_show_profile(...)`로 바꾼다. Sandbox와 Compare가 `_show_profile()`를 부르는 곳(`run_scenario_compare`, sandbox 완료 처리)은 Task 12에서 `"compare"`/`"sandbox"`로 바꾼다. 이 작업에서는 그대로 둔다(기본값 `"community"`).
4. `run_community_solve`: 동작은 그대로. 멤버 표가 선택기를 따르므로 "선택하지 않은 모델의 abundance" 검사는 남겨 두되 일어나지 않는다.
5. `_connect_view_actions`에 `browse_namespace_decisions_btn` 연결이 있으면 그대로 둔다.

- [ ] **Step 5: 드라이버와 기존 테스트**

`tests/argv_drivers.py`의 `community`:
```python
def community(w: Any) -> str:
    v = w.community_builder
    v.model_picker.set_selected(["a", "b"])
    v.set_abundance("a", 0.25)
    v.assume_bigg_check.setChecked(True)
    v.f_slider.setValue(30)
    return w.run_community_solve()
```
기존 테스트에서 `add_member(x, v)` → `set_abundance(x, v)`(먼저 그 모델을 선택), `remove_member`/`add_member_btn` 사용 → 선택기에서 빼기로 옮긴다. `"Pick members" in w.community_builder.status.text()` 단언은 `"Abundances start at 1" in w.community_builder.description.text()`로 바꾼다. 선택하지 않은 모델의 abundance 행을 만드는 테스트(`test_refused_community_abundance_keeps_runs_clean` 등)는 표가 선택기를 따르므로 그런 행을 만들 수 없다. 이 테스트는 "선택하지 않은 모델에는 행이 없다"를 확인하도록 바꾼다.

- [ ] **Step 6: 통과 확인**

Run: `uv run --no-sync pytest tests/test_phase2_community_solve.py tests/test_phase2_argv_parity.py tests/test_phase2_analysis_page.py -q && uv run --no-sync pytest tests/ -q -k "gui or workspace or app_shell or phase2 or round7 or round9" 2>&1 | tail -3`
Expected: 모두 통과.

- [ ] **Step 7: Commit**

```bash
git add cmig/gui tests
git commit -m "feat(gui): Community Solve rows follow the member picker; results stay on the page

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 10: Host–Microbe와 Host Combination Search 분리

**Files:**
- Modify: `cmig/gui/host_view.py` (`HostInputs`, `HostImpactView`를 Host–Microbe 전용 `AnalysisPage`로, 표 머리글)
- Create: `cmig/gui/pages/host_search.py` (`HostSearchPage`)
- Modify: `cmig/gui/app.py` (`host_search_page`, `_host_inputs`, 실행·완료, 선택기 키, `_host_model_changed`)
- Modify: `tests/argv_drivers.py` (`host`, `host_search`)
- Create: `tests/test_phase2_host_pages.py`
- Modify (옮기기): Host 관련 기존 테스트

**Interfaces:**
- Produces:
  - `HostInputs` (일반 클래스): `host_picker`, `model_picker`, `host_medium_picker`, `microbe_medium_picker`, `host_objective_input`, `tradeoff_spin`, `microbial_biomass_spin`, `host_biomass_spin`, `biomass_basis_kind_combo`, `biomass_basis_source_input`, `keep_host_uptake_check`, `include_currency_check`, `allow_unknown_medium_check`; `attach(page: AnalysisPage) -> None`(카드·Advanced에 배치하고 등록), `request() -> dict[str, Any]`(옛 `HostImpactView.request()`의 숙주 공통 키), `widgets() -> list[QWidget]`
  - `HostImpactView(AnalysisPage)`: 제목 "Host–Microbe", `run_btn`("Run Host-Microbe"), `run_status`(= `status`), 위 `HostInputs`의 위젯 이름을 같은 이름의 속성으로도 가진다, 결과 위젯(`figure_mode_combo`, `export_figure_btn`, `viability_label`, `iface_table`, `cross_label`, `cross_table`, `network_view`, `static_figure_view`, `figure_stack`)과 기존 메서드(`invalidate_results`, `request`, `set_running`, `selected_figure_artifact`, `refresh_figure_mode`, `load_host_result`, `load_impact`, `load_bigg_summary`). `run_search_btn`, `search_target_input`, `search_metric_combo`, `min_size_spin`, `max_size_spin`는 없어진다.
  - `HostSearchPage(AnalysisPage)`: 제목 "Host Combination Search", `run_btn`("Rank Combinations"), `HostInputs` 위젯 같은 이름 속성, `target_input`(기본 "ac"), `metric_combo`(`target_transfer`, `objective_value`), `min_size_spin`, `max_size_spin`(1–20, 기본 2), `results_panel`, `request() -> dict[str, Any]`(숙주 공통 키 + `search_target`, `search_metric`, `min_size`, `max_size`), `request_fields(kind) -> dict[str, str]`(kind `"host_search"`일 때 `request()` 값을 글자로)
  - 선택기 기억 키: `"host_search_model"`(숙주), `"host_search"`(미생물), 배지 `("host_search","host_medium")`, `("host_search","microbe_medium")`
  - Host 표 머리글: `iface_table` = `["Interface", "Metabolite", "Flux", "Direction"]`(Flux 머리글 도움말 "mmol gDW⁻¹ h⁻¹"), `cross_table` = `["Metabolite", "Lumen transfer"]`(도움말 "mmol gDW⁻¹ h⁻¹")

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_phase2_host_pages.py`:
```python
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402

APP = QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path: Path):
    make_project(tmp_path / "p", ["a", "b", "host"])
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(tmp_path / "p")
    yield w
    w.close_project()


def test_two_host_pages(window) -> None:
    w = window
    assert w.analysis_pages["host"] is w.host_view
    assert w.analysis_pages["host_search"] is w.host_search_page
    assert not hasattr(w.host_view, "run_search_btn")
    assert w.host_search_page.target_input.text() == "ac"


def test_host_search_has_its_own_host_choice(window) -> None:
    w = window
    w.host_search_page.host_picker.set_selected(["host"])
    assert "host" not in w.host_search_page.model_picker.selected_ids()
    assert w.session.settings("host_search_model")["models"] == ["host"]


def test_host_search_result_goes_to_its_page(window, tmp_path: Path) -> None:
    w = window
    payload = {"target": "ac", "metric": "target_transfer", "status": "ok", "warnings": [],
               "top_ranked": [{"members": ["a"], "score": 1.0, "target_transfer": 0.5,
                               "community_growth": 0.2, "evaluation_status": "optimal",
                               "target_identifiability": "identified"}]}
    w._show_ranked("host_search", payload, tmp_path,
                   w.host_search_page.request_fields("host_search"))
    assert w.pages.currentWidget() is w.host_search_page
    assert w.host_search_page.results_panel.table.rowCount() == 1


def test_host_table_headers_fit_and_keep_units(window) -> None:
    view = window.host_view
    headers = [view.iface_table.horizontalHeaderItem(i).text() for i in range(4)]
    assert headers == ["Interface", "Metabolite", "Flux", "Direction"]
    assert "mmol gDW" in view.iface_table.horizontalHeaderItem(2).toolTip()
    assert view.cross_table.horizontalHeaderItem(1).text() == "Lumen transfer"
    assert "mmol gDW" in view.cross_table.horizontalHeaderItem(1).toolTip()


def test_host_pages_start_without_result_tables(window) -> None:
    assert not window.host_view.results.has_results()
    assert not window.host_search_page.results.has_results()
```

- [ ] **Step 2: 실패 확인**

Run: `uv run --no-sync pytest tests/test_phase2_host_pages.py -q`
Expected: FAIL — `host_search_page` 없음.

- [ ] **Step 3: `HostInputs`와 `HostImpactView`**

`cmig/gui/host_view.py`:
1. `HostImpactView.__init__`에서 숙주 공통 위젯을 만드는 코드(host/microbe 선택기, 배지 선택기 두 개, host objective, tradeoff, biomass 두 개, basis 콤보·출처, 체크 세 개)를 그대로 `HostInputs.__init__`으로 옮긴다. `HostInputs`는 `QObject`가 아닌 일반 클래스다.
2. `HostInputs.attach(page)`:
```python
    def attach(self, page: AnalysisPage) -> None:
        page.add_input_row(self.host_picker, self.model_picker)
        page.add_input_row("Host medium", self.host_medium_picker,
                           "Microbe medium", self.microbe_medium_picker)
        page.add_input_row("Biomass basis", self.biomass_basis_kind_combo,
                           self.biomass_basis_source_input)
        page.add_input_row("Microbe gDW", self.microbial_biomass_spin,
                           "Host gDW", self.host_biomass_spin)
        page.advanced.add_row("Host objective", self.host_objective_input)
        page.advanced.add_row("tradeoff f", self.tradeoff_spin)
        page.advanced.add_row(self.keep_host_uptake_check, self.include_currency_check,
                              self.allow_unknown_medium_check)
        page.advanced.track(self.host_objective_input, self.tradeoff_spin,
                            self.keep_host_uptake_check, self.include_currency_check,
                            self.allow_unknown_medium_check)
        for name, widget in (
            ("host", self.host_picker), ("microbes", self.model_picker),
            ("host_medium", self.host_medium_picker),
            ("microbe_medium", self.microbe_medium_picker),
            ("basis_kind", self.biomass_basis_kind_combo),
            ("basis_source", self.biomass_basis_source_input),
            ("microbe_gdw", self.microbial_biomass_spin), ("host_gdw", self.host_biomass_spin),
            ("host_objective", self.host_objective_input), ("tradeoff", self.tradeoff_spin),
            ("keep_host_uptake", self.keep_host_uptake_check),
            ("currency", self.include_currency_check),
            ("allow_unknown_medium", self.allow_unknown_medium_check),
        ):
            page.register(name, widget)
            setattr(page, _ATTRIBUTE_NAMES[name], widget)
```
여기서 `_ATTRIBUTE_NAMES`는 등록 이름 → 옛 속성 이름이다(`"host": "host_picker"`, `"microbes": "model_picker"`, `"host_medium": "host_medium_picker"`, `"microbe_medium": "microbe_medium_picker"`, `"basis_kind": "biomass_basis_kind_combo"`, `"basis_source": "biomass_basis_source_input"`, `"microbe_gdw": "microbial_biomass_spin"`, `"host_gdw": "host_biomass_spin"`, `"host_objective": "host_objective_input"`, `"tradeoff": "tradeoff_spin"`, `"keep_host_uptake": "keep_host_uptake_check"`, `"currency": "include_currency_check"`, `"allow_unknown_medium": "allow_unknown_medium_check"`).
3. `HostInputs.request()`는 옛 `request()`에서 `search_*`, `min_size`, `max_size`를 뺀 키를 돌려준다. `widgets()`는 위 13개 위젯 목록.
4. `HostImpactView(AnalysisPage)`: `super().__init__("Host–Microbe", "Couple one host model with microbial models and read what crosses between them.", run_text="Run Host-Microbe", cancel=False)`. `self.host_inputs = HostInputs(); self.host_inputs.attach(self)`. `self.run_status = self.status`. 결과 위젯(figure 줄, `viability_label`, 표 두 개, `cross_label`, 그래프, splitter)은 지금처럼 만들어 `self.results.add(<figure 줄을 담은 QWidget>)`, `self.results.add(splitter, 1)`로 넣는다. `search_*`·`min/max_size`·`run_search_btn` 생성과 연결을 지운다. 옛 자체 `scroll_area`/`title`/`run_btn` 생성을 지운다.
5. `request()`는 `self.host_inputs.request()`를 돌려준다.
6. 무효화 연결은 `for widget in self.host_inputs.widgets(): connect_change(widget, lambda *_a: self.invalidate_results())`로 바꾼다. `invalidate_results`가 실제로 결과를 지울 때 끝에 `self.results.show_empty()`를 더하고, `load_host_result`/`load_bigg_summary`가 결과를 그릴 때 `self.results.show_results()`를 더한다.
7. 머리글:
```python
        self.iface_table.setHorizontalHeaderLabels(["Interface", "Metabolite", "Flux",
                                                    "Direction"])
        self.iface_table.horizontalHeaderItem(2).setToolTip("Flux, mmol gDW⁻¹ h⁻¹")
        ...
        self.cross_table.setHorizontalHeaderLabels(["Metabolite", "Lumen transfer"])
        self.cross_table.horizontalHeaderItem(1).setToolTip(
            "Lumen transfer, mmol gDW⁻¹ h⁻¹"
        )
```

- [ ] **Step 4: `HostSearchPage`**

`cmig/gui/pages/host_search.py`:
```python
"""Host Combination Search: rank microbial combinations for one host."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QComboBox, QLineEdit, QSpinBox

from cmig.gui.analysis_page import AnalysisPage, connect_change
from cmig.gui.host_view import HostInputs
from cmig.gui.search_results import SearchResultsPanel


def _size_spin() -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(1, 20)
    spin.setValue(2)
    return spin


class HostSearchPage(AnalysisPage):
    def __init__(self) -> None:
        super().__init__(
            "Host Combination Search",
            "Rank microbial combinations by what they transfer to the host or by the host "
            "objective.",
            run_text="Rank Combinations",
            cancel=False,
        )
        self.host_inputs = HostInputs()
        self.host_inputs.attach(self)
        self.target_input = QLineEdit("ac")
        self.target_input.setPlaceholderText("Target transferred metabolite")
        self.metric_combo = QComboBox()
        self.metric_combo.addItems(["target_transfer", "objective_value"])
        self.min_size_spin = _size_spin()
        self.max_size_spin = _size_spin()
        self.add_input_row("Target", self.target_input, "Metric", self.metric_combo,
                           "Size", self.min_size_spin, "to", self.max_size_spin)
        for name, widget in (("target", self.target_input), ("metric", self.metric_combo),
                             ("min_size", self.min_size_spin),
                             ("max_size", self.max_size_spin)):
            self.register(name, widget)
        self.results_panel = SearchResultsPanel(self.request_fields, status=self.status,
                                                area=self.results)
        self.results.add(self.results_panel, 1)
        for widget in [*self.host_inputs.widgets(), self.target_input, self.metric_combo,
                       self.min_size_spin, self.max_size_spin]:
            connect_change(widget, lambda *_a: self.results_panel.invalidate_results(True))

    def request(self) -> dict[str, Any]:
        return {
            **self.host_inputs.request(),
            "search_target": self.target_input.text().strip() or "ac",
            "search_metric": self.metric_combo.currentText(),
            "min_size": self.min_size_spin.value(),
            "max_size": self.max_size_spin.value(),
        }

    def request_fields(self, kind: str) -> dict[str, str]:
        if kind != "host_search":
            return {}
        return {
            key: ",".join(value) if isinstance(value, list) else str(value)
            for key, value in self.request().items()
        }
```

- [ ] **Step 5: 창**

`cmig/gui/app.py`:
1. `self.host_search_page = HostSearchPage()`; `analysis_pages["host_search"] = self.host_search_page`; `_run_buttons["host_search"] = self.host_search_page.run_btn`.
2. `_host_inputs(self, kind, request, biomass_error)` → `_host_inputs(self, page, kind, request, biomass_error)`로 바꾸고, 본문의 `self.host_view.run_status`를 `page.status`로 바꾼다. `run_host_microbe_bigg`는 `page = self.host_view`, `run_host_search_bigg`는 `page = self.host_search_page`와 `request = page.request()`를 쓴다. `run_host_search_bigg`의 `self.host_view.run_search_btn`은 `page.run_btn`, 시작 문구는 `page.status`, `self._host_search_jobs[jid] = (out_dir, page.request_fields("host_search"))`. argv는 그대로.
3. `_ranked_spec`에 `"host_search": ("host_search_summary.json", _host_search_summary_for_search_view, "host_search", "kind_host_search")`을 더하고, `_poll_completed_jobs`의 host-search 블록을 `self._finish_ranked_jobs("host_search", self._host_search_jobs, "host-search")`로 바꾼다.
4. `_connect_view_actions`: `self.host_view.run_search_btn` 연결을 지우고 `self.host_search_page.run_btn.clicked.connect(self.run_host_search_bigg)`와 `host_search_page.results_panel.export_figure_btn` → `_export_ranked_figure(self.host_search_page)` 연결을 더한다. `self.host_search_page.host_picker.selection_changed.connect(...)`로 Host 화면과 같은 "숙주를 미생물에서 빼기" 동작을 연결한다.
5. `_host_model_changed`를 화면을 받도록 바꾼다:
```python
    def _host_model_changed(self, page: Any) -> None:
        """A newly chosen host model is unticked from Microbes; re-ticking it is refused at run."""
        if self._refreshing_pickers:
            return
        host = page.host_picker.selected_ids()
        microbes = page.model_picker.selected_ids()
        if host and host[0] in microbes:
            page.model_picker.set_selected([m for m in microbes if m != host[0]])
```
연결은 `lambda p=self.host_view: self._host_model_changed(p)`, `lambda p=self.host_search_page: self._host_model_changed(p)`.
6. `_model_pickers`: `"host_model"`, `"host"` 다음에 `"host_search_model": self.host_search_page.host_picker`, `"host_search": self.host_search_page.model_picker`(숙주가 미생물보다 먼저). `_medium_pickers`에 `("host_search", "host_medium")`, `("host_search", "microbe_medium")`. `_PICKER_LABELS`에 `"host_search_model": "Host search host"`, `"host_search": "Host search microbes"`.
7. `_refresh_pickers`의 기본 선택 줄 `host = self.host_view.host_picker.selected_ids() if key == "host" else []`를 두 화면 모두에 맞게 바꾼다:
```python
                    host_pickers = {"host": self.host_view.host_picker,
                                    "host_search": self.host_search_page.host_picker}
                    host = host_pickers[key].selected_ids() if key in host_pickers else []
```

- [ ] **Step 6: 드라이버**

`tests/argv_drivers.py`:
```python
def host_search(w: Any) -> str:
    v = w.host_search_page
    _host_common(v)
    v.target_input.setText("but")
    v.metric_combo.setCurrentText("objective_value")
    v.min_size_spin.setValue(1)
    v.max_size_spin.setValue(2)
    return w.run_host_search_bigg()
```
(`host`와 `_host_common`은 그대로 둔다. 속성 이름이 같기 때문이다.)

- [ ] **Step 7: 기존 테스트 옮기기와 통과 확인**

Host Search 관련 기존 테스트(`run_search_btn`, `search_target_input`, `search_metric_combo`, Host Search 결과를 `w.search_view`에서 찾는 단언)는 `w.host_search_page`로 옮긴다.

Run: `uv run --no-sync pytest tests/test_phase2_host_pages.py tests/test_phase2_argv_parity.py -q && uv run --no-sync pytest tests/ -q -k "gui or workspace or app_shell or phase2 or host" 2>&1 | tail -3`
Expected: 모두 통과.

- [ ] **Step 8: Commit**

```bash
git add cmig/gui tests
git commit -m "feat(gui): Host–Microbe and Host Combination Search pages

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 11: dFBA와 Spatial Preview 분리

**Files:**
- Modify: `cmig/gui/views.py` (`DfbaSpatialView` → `DfbaView(AnalysisPage)`, 결과 공통 `DynamicsResults`)
- Create: `cmig/gui/pages/spatial.py` (`SpatialPage`)
- Modify: `cmig/gui/app.py` (`spatial_page`, `run_spatial_preview`, `load_spatial_dir`, 완료 처리)
- Modify: `tests/argv_drivers.py` (`spatial`)
- Create: `tests/test_phase2_dynamics_pages.py`
- Modify (옮기기): `DfbaSpatialView`나 `dynamics_view`의 spatial 위젯을 쓰는 기존 테스트

**Interfaces:**
- Produces:
  - `DynamicsResults` (mixin): `_build_dynamics_results()`가 `warning_label`, `table`(열 Run·Status·Final time (h)·Readout), `figure_label`을 만들어 `self.results`에 넣는다. 메서드 `_show_warnings`, `_set_single_row`, `_load_figure`, `_clear_dynamics(text)`.
  - `DfbaView(AnalysisPage, DynamicsResults)`: 제목 "dFBA", `run_btn`("Run dFBA"), `run_dfba_btn`(= `run_btn`), `model_picker`, `initial_input`, `t_end_spin`(카드), `dt_spin`, `biomass_spin`, `close_untracked_check`(Advanced), `dfba_request()`, `load_dfba_summary()`, `invalidate_results()`
  - `SpatialPage(AnalysisPage, DynamicsResults)`: 제목 "Spatial Preview", `run_btn`("Preview Spatial Medium"), `run_spatial_btn`(= `run_btn`), `spatial_metabolite_input`, `grid_size_spin`, `steps_spin`(카드), `spatial_dt_spin`, `diffusion_spin`, `source_combo`, `sink_combo`(Advanced), `spatial_request()`, `load_spatial_summary()`, `invalidate_results()`
  - 창: `dynamics_view`는 `DfbaView`, `spatial_page`는 `SpatialPage`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_phase2_dynamics_pages.py`:
```python
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown  # noqa: E402,F401
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402

APP = QApplication.instance() or QApplication([])


def test_two_dynamics_pages() -> None:
    w = build_main_window()
    assert w.analysis_pages["dfba"] is w.dynamics_view
    assert w.analysis_pages["spatial"] is w.spatial_page
    assert not hasattr(w.dynamics_view, "spatial_metabolite_input")
    assert w.dynamics_view.run_dfba_btn is w.dynamics_view.run_btn
    assert w.spatial_page.run_spatial_btn is w.spatial_page.run_btn


def test_spatial_result_loads_on_its_page(tmp_path) -> None:
    w = build_main_window()
    w.spatial_page.load_spatial_summary(
        {"status": "ok", "final_t": 1.0, "final_min": 0.0, "final_max": 2.0, "warnings": []},
        run_dir=tmp_path,
    )
    assert w.spatial_page.results.has_results()
    assert w.spatial_page.table.item(0, 0).text() == "Spatial"
    assert w.dynamics_view.table.rowCount() == 0


def test_dfba_advanced_counts_changes() -> None:
    w = build_main_window()
    page = w.dynamics_view
    page.close_untracked_check.setChecked(True)
    assert page.advanced.changed_count() == 1
```

- [ ] **Step 2: 실패 확인**

Run: `uv run --no-sync pytest tests/test_phase2_dynamics_pages.py -q`
Expected: FAIL — `spatial_page` 없음.

- [ ] **Step 3: 구현**

`cmig/gui/views.py`:
1. `DynamicsResults` mixin을 만든다. `DfbaSpatialView`의 `_show_warnings`, `_set_single_row`, `_load_figure`를 본문 그대로 옮기고, 결과 위젯 생성 코드(`warning_label`, `table`, `figure_label`)를 `_build_dynamics_results(self)`로 옮긴 뒤 `self.results.add(self.warning_label)`, `self.results.add(self.table)`, `self.results.add(self.figure_label, 1)`로 넣는다. `_set_single_row` 끝에 `self.results.show_results()`를 더한다. `_clear_dynamics(self, text)`는 옛 `invalidate_results`의 본문(표 비우기, 경고 숨기기, 그림 지우기, 두 문구)을 담고 끝에 `self.results.show_empty()`를 부른다.
2. `DfbaView(AnalysisPage, DynamicsResults)`: `super().__init__("dFBA", "Well-mixed dynamic FBA of one model.", run_text="Run dFBA", cancel=False)`. 카드: (`model_picker`) → ("Initial (mmol L⁻¹)", `initial_input`) → ("T end", `t_end_spin`). Advanced: ("dt", `dt_spin`, "Initial biomass", `biomass_spin`) → (`close_untracked_check`), `track` 세 개. 등록 이름: `model`, `initial`, `t_end`, `dt`, `biomass`, `close_untracked`. `self.run_dfba_btn = self.run_btn`. `invalidate_results`는 `if self.table.rowCount() == 0: return` 뒤 `self._clear_dynamics("Inputs changed — previous result cleared; re-run to update.")`. dFBA 입력의 변화 신호만 연결한다. `dfba_request`, `load_dfba_summary`는 그대로.
3. `cmig/gui/pages/spatial.py`의 `SpatialPage(AnalysisPage, DynamicsResults)`: `super().__init__("Spatial Preview", "Preview how one metabolite spreads across a grid (no growth).", run_text="Preview Spatial Medium", cancel=False)`. `DfbaSpatialView`의 spatial 위젯 생성 코드를 옮긴다. 카드: ("Metabolite", `spatial_metabolite_input`, "Grid", `grid_size_spin`, "Steps", `steps_spin`). Advanced: ("dt", `spatial_dt_spin`, "Diffusion", `diffusion_spin`) → ("Source", `source_combo`, "Sink", `sink_combo`), `track` 네 개. 등록 이름: `metabolite`, `grid`, `steps`, `dt`, `diffusion`, `source`, `sink`. `self.run_spatial_btn = self.run_btn`. `spatial_request`, `load_spatial_summary`를 옮기고, `invalidate_results`는 dFBA와 같은 방식이다.
4. `DfbaSpatialView` 이름을 쓰는 곳(`app.py` import, 테스트)을 `DfbaView`로 바꾼다.

`cmig/gui/app.py`:
- `self.dynamics_view = DfbaView()`, `self.spatial_page = SpatialPage()`, `analysis_pages["spatial"] = self.spatial_page`, `_run_buttons["spatial"] = self.spatial_page.run_btn`.
- `run_spatial_preview`, `load_spatial_dir`, spatial 완료 처리의 `self.dynamics_view`를 `self.spatial_page`로 바꾼다(`_show_page(self.spatial_page)` 포함). `_connect_view_actions`의 `run_spatial_btn` 연결을 `self.spatial_page.run_btn`으로 바꾼다.

`tests/argv_drivers.py`의 `spatial`에서 `v = w.dynamics_view`를 `v = w.spatial_page`로 바꾼다.

- [ ] **Step 4: 통과 확인**

Run: `uv run --no-sync pytest tests/test_phase2_dynamics_pages.py tests/test_phase2_argv_parity.py -q && uv run --no-sync pytest tests/ -q -k "gui or workspace or app_shell or phase2 or dfba or dynamics or spatial" 2>&1 | tail -3`
Expected: 모두 통과(옮긴 테스트 포함).

- [ ] **Step 5: Commit**

```bash
git add cmig/gui tests
git commit -m "feat(gui): dFBA and Spatial Preview pages

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 12: Tools 화면 틀(Medium Editor·Sweep·Constraint Sandbox·Compare Runs)과 행 번호 숨김

**Files:**
- Create: `cmig/gui/pages/tools.py` (`ToolPage`)
- Modify: `cmig/gui/app.py` (Tools 화면 생성·등록, `_show_page(<도구 위젯>)` 호출 교체, 공동체 결과를 Medium/Sandbox/Compare 화면에 보이기, 창 전체 표 행 번호 숨김)
- Modify: `cmig/gui/editors.py` (`ModelManagerPanel` 표 행 번호)
- Create: `tests/test_phase2_tool_pages.py`
- Modify (옮기기): `w.pages.currentWidget() is w.medium_editor` 같은 단언

**Interfaces:**
- Produces:
  - `ToolPage(AnalysisPage)`: `ToolPage(title, description, content, *, results: bool)` — `content`(기존 위젯)를 카드에 넣고, 틀의 `run_btn`·`cancel_btn`·`advanced`는 숨긴다(도구는 자기 단추를 쓴다). `results=False`면 결과 영역도 숨긴다. `content` 속성.
  - 창: `medium_page`, `sweep_page`, `sandbox_page`, `compare_page`. `analysis_pages`의 Tools 키는 이 틀을 가리킨다. 공동체 결과를 보이는 곳: Medium 성장 확인 → `"medium"`, Sandbox → `"sandbox"`, Compare → `"compare"`.
  - `medium_page`와 `sweep_page`는 실행 입력을 기록·복원하도록 입력을 등록한다(Task 13이 씀):
    - medium: `models`(`medium_editor.model_picker`), `model`(`single_model_picker`), `rows`(사용자 정의: `[[exchange, limit, role], …]`; 복원은 `clear_rows()` 후 `add_row(exchange, float(limit), role, notify=False)`, 끝에 `medium_changed` 한 번), `exact`, `allow_unknown`, `assume_bigg`, `namespace_decisions`, `min_growth`, `oxygen_mode`
    - sweep: `models`, `mediums`, `abundance_variants`, `member_sets`, `bounds_variants`, `tradeoff_fs`, `solvers`, `assume_bigg`, `namespace_decisions`, `fva`, `fva_metabolites`, `exact_medium`, `allow_unknown_medium` — `sweep_view`의 같은 이름 `*_input`/`*_check` 위젯
- 창의 모든 `QTableWidget`의 행 번호를 숨긴다(`__init__` 끝에서 `for table in self.findChildren(QTableWidget): hide_row_numbers(table)`). 이후 만드는 표(모델 브라우저 등)는 각자 숨긴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_phase2_tool_pages.py`:
```python
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown  # noqa: E402,F401
from PySide6.QtWidgets import QApplication, QTableWidget  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402

APP = QApplication.instance() or QApplication([])


def test_tools_are_framed_pages() -> None:
    w = build_main_window()
    pairs = {"medium": w.medium_editor, "sweep": w.sweep_view, "sandbox": w.sandbox_view,
             "compare": w.scenario_compare}
    for key, content in pairs.items():
        page = w.analysis_pages[key]
        assert page.content is content
        assert page.isAncestorOf(content)
        assert page.run_btn.isHidden() and page.advanced.isHidden()
    assert w.sweep_page.results.isHidden(), "Sweep shows its own results"


def test_no_row_numbers_anywhere() -> None:
    w = build_main_window()
    tables = w.findChildren(QTableWidget)
    assert tables
    assert all(table.verticalHeader().isHidden() for table in tables)


def test_sandbox_result_shows_on_the_sandbox_page() -> None:
    w = build_main_window()
    w._show_profile("sandbox")
    assert w.pages.currentWidget() is w.sandbox_page
    assert w.sandbox_page.isAncestorOf(w.profile_view)
    w._show_profile("community")
    assert not w.sandbox_page.results.has_results()


def test_medium_inputs_round_trip() -> None:
    w = build_main_window()
    editor = w.medium_editor
    editor.clear_rows()
    editor.add_row("EX_glc__D_e", 10.0)
    editor.exact_medium_check.setChecked(True)
    saved = w.medium_page.snapshot()
    editor.clear_rows()
    editor.exact_medium_check.setChecked(False)
    assert w.medium_page.restore(saved) == []
    assert w.medium_page.snapshot() == saved
```

- [ ] **Step 2: 실패 확인**

Run: `uv run --no-sync pytest tests/test_phase2_tool_pages.py -q`
Expected: FAIL — `medium_page` 없음.

- [ ] **Step 3: `ToolPage`**

`cmig/gui/pages/tools.py`:
```python
"""Tools (Medium Editor, Sweep, Constraint Sandbox, Compare Runs) in the common page frame.

The tools keep their own controls and buttons; the frame gives them the same title, place
and results area as every analysis page.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from cmig.gui.analysis_page import AnalysisPage


class ToolPage(AnalysisPage):
    def __init__(self, title: str, description: str, content: QWidget, *,
                 results: bool) -> None:
        super().__init__(title, description, cancel=False)
        self.content = content
        self.inputs.addWidget(content)
        self.run_btn.setVisible(False)
        self.advanced.setVisible(False)
        self.results.setVisible(results)
```

- [ ] **Step 4: 창**

`cmig/gui/app.py`:
1. 도구 위젯을 만든 뒤:
```python
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
```
`analysis_pages`의 `medium`/`sweep`/`sandbox`/`compare`를 이 네 틀로 바꾼다.
2. 앱 코드 안의 `self._show_page(self.medium_editor)`, `self._show_page(self.sweep_view)`, `self._show_page(self.sandbox_view)`, `self._show_page(self.scenario_compare)`를 각각 `self.medium_page`, `self.sweep_page`, `self.sandbox_page`, `self.compare_page`로 바꾼다(`grep -n "_show_page(self\.\(medium_editor\|sweep_view\|sandbox_view\|scenario_compare\))" cmig/gui/app.py`로 찾는다).
3. 공동체 결과를 보이는 곳:
   - Medium 성장 확인 완료 처리의 `self.load_run_dir(out_dir)`를 `self.load_run_dir(out_dir, host_key="medium")`로
   - `run_scenario_compare`의 `self._show_profile()`를 `self._show_profile("compare")`로
   - Sandbox 완료 처리의 `self._show_profile()`를 `self._show_profile("sandbox")`로
4. Medium·Sweep 입력 등록(복원용)을 `__init__`에서 한다:
```python
        editor = self.medium_editor
        self.medium_page.register("models", editor.model_picker)
        self.medium_page.register("model", editor.single_model_picker)
        self.medium_page.register_custom("rows", self._medium_rows, self._restore_medium_rows)
        for name, widget in (("exact", editor.exact_medium_check),
                             ("allow_unknown", editor.allow_unknown_check),
                             ("assume_bigg", editor.assume_bigg_check),
                             ("namespace_decisions", editor.namespace_decisions_input),
                             ("min_growth", editor.min_growth_spin),
                             ("oxygen_mode", editor.oxygen_mode_combo)):
            self.medium_page.register(name, widget)
        sweep = self.sweep_view
        self.sweep_page.register("models", sweep.model_picker)
        for name in ("mediums", "abundance_variants", "member_sets", "bounds_variants",
                     "tradeoff_fs", "solvers", "namespace_decisions", "fva_metabolites"):
            self.sweep_page.register(name, getattr(sweep, f"{name}_input"))
        for name in ("assume_bigg", "fva", "exact_medium", "allow_unknown_medium"):
            self.sweep_page.register(name, getattr(sweep, f"{name}_check"))
```
그리고 메서드 두 개:
```python
    def _medium_rows(self) -> list[list[str]]:
        table = self.medium_editor.table
        rows = []
        for r in range(table.rowCount()):
            cells = [table.item(r, c) for c in range(3)]
            rows.append(["" if cell is None else cell.text() for cell in cells])
        return rows

    def _restore_medium_rows(self, rows: object) -> str | None:
        editor = self.medium_editor
        try:
            parsed = [(str(e), float(v), str(role)) for e, v, role in rows]  # type: ignore[union-attr]
        except (TypeError, ValueError):
            return "medium rows could not be restored"
        editor.clear_rows()
        for exchange, limit, role in parsed:
            editor.add_row(exchange, limit, role, notify=False)
        editor.medium_changed.emit()
        return None
```
(`sweep_view`의 위젯 이름이 위 규칙과 다르면 실제 이름으로 맞추고 등록 이름은 그대로 둔다. `editor.clear_rows()`가 신호를 보내는지 확인하고, 보낸다면 그대로 둔다.)
5. `__init__` 끝(모든 화면을 만든 뒤)에 `for table in self.findChildren(QTableWidget): hide_row_numbers(table)`. `QTableWidget`과 `hide_row_numbers` import를 더한다.
6. `cmig/gui/editors.py`의 `ModelManagerPanel.__init__`에 `self.exchange_table.verticalHeader().setVisible(False)`를 더한다.

- [ ] **Step 5: 기존 테스트 옮기기와 통과 확인**

`w.pages.currentWidget() is w.medium_editor`(또는 `sweep_view`, `sandbox_view`, `scenario_compare`) 단언은 `… is w.medium_page`(해당 틀)로 바꾼다. 결과가 `community_result_page`에 보이는지 확인하던 Sandbox/Compare/Medium 테스트는 해당 틀 안에 `profile_view`가 있는지로 바꾼다. `test_app_shell.py`의 "Advanced editor"·"Advanced result view" 같은 상태 문구 단언은 위젯 자체 문구라 그대로 둔다.

Run: `uv run --no-sync pytest tests/test_phase2_tool_pages.py -q && uv run --no-sync pytest tests/ -q -k "gui or workspace or app_shell or phase2 or round7 or round8 or round9" 2>&1 | tail -3`
Expected: 모두 통과.

- [ ] **Step 6: Commit**

```bash
git add cmig/gui tests
git commit -m "feat(gui): tools in the page frame; no row numbers in tables

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 13: 실행 입력 기록과 RUNS에서 열 때 입력 복원

**Files:**
- Create: `cmig/gui/run_restore.py` (Qt 없음)
- Modify: `cmig/gui/app.py` (`_prepare_run(..., analysis=…)`, 모든 실행이 기록, `_open_run_entry`, 결과 불러오기 `_load_run_into_page`, `load_ranked_dir`)
- Create: `tests/test_phase2_run_restore.py`

**Interfaces:**
- Consumes: `write_run_request`, `read_run_request`(Task 2), 각 화면의 `snapshot()`/`restore()`/`show_banner()`/`clear_banner()`(Tasks 4–12), `_show_ranked`(Task 8)
- Produces (`cmig.gui.run_restore`):
  - `analysis_for_run(run_dir: Path) -> tuple[str | None, dict[str, Any] | None, str]` — (화면 키, 기록, 기록을 못 쓴 이유). 순서: 기록 → manifest `workflow_kind` → 요약 파일 → `nodes.parquet` → 폴더 이름 앞부분.
  - `banner_text(run_name: str, record: dict | None, problem: str, notes: list[str]) -> str`
  - `request_models_and_media(values: dict[str, Any]) -> tuple[list[str], list[str]]`
- Produces (창): `_prepare_run(kind, model_ids, *, abundances=None, analysis: str | None = None)` — `analysis`가 있으면 그 화면 입력을 기록하고, 기록에 실패하면 실행 폴더와 입력 파일을 지우고 `ProjectError`. `load_ranked_dir(key, run_dir) -> bool`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_phase2_run_restore.py`:
```python
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui import run_restore  # noqa: E402
from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402
from cmig.io import project as proj  # noqa: E402

APP = QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path: Path, monkeypatch):
    make_project(tmp_path / "p", ["a", "b", "c"])
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(tmp_path / "p")
    calls: list[list[str]] = []
    monkeypatch.setattr("cmig.cli.main.main", lambda argv: (calls.append(list(argv)), 2)[1])
    yield w, calls
    w.close_project()


def _out(argv: list[str]) -> Path:
    return Path(argv[argv.index("--out") + 1])


def _wait(calls: list[list[str]], n: int = 1) -> list[str]:
    deadline = time.time() + 10
    while len(calls) < n and time.time() < deadline:
        APP.processEvents()
        time.sleep(0.02)
    assert len(calls) >= n
    return calls[-1]


def test_every_run_records_its_inputs(window) -> None:
    w, calls = window
    w.search_view.model_picker.set_selected(["a", "b"])
    w.search_view.min_size_spin.setValue(1)
    assert w.run_search_fixture()
    record, problem = proj.read_run_request(_out(_wait(calls)))
    assert problem == "" and record is not None
    assert record["analysis"] == "search"
    assert record["values"]["models"] == ["a", "b"]
    assert record["values"]["min_size"] == 1
    assert record["models"] == ["a", "b"]


def test_reopening_a_run_restores_its_page_and_inputs(window) -> None:
    w, calls = window
    page = w.gene_ko_page
    page.model_picker.set_selected(["a", "b"])
    page.members_picker.set_selected(["a"])
    page.target_input.setText("ac")
    assert w.run_gene_ko_search()
    run_dir = _out(_wait(calls))
    w.show_analysis("search")
    page.target_input.setText("but")
    page.model_picker.set_selected(["c"])
    w._open_run_entry(run_dir)
    assert w.pages.currentWidget() is page
    assert page.model_picker.selected_ids() == ["a", "b"]
    assert page.members_picker.selected_ids() == ["a"]
    assert page.target_input.text() == "ac"
    assert "Inputs restored from" in page.banner.text()


def test_removed_model_named_in_banner(window) -> None:
    w, calls = window
    w.strain_growth_page.model_picker.set_selected(["a", "b"])
    assert w.run_strain_growth_report()
    run_dir = _out(_wait(calls))
    w.session.remove_models(["b"])
    w._open_run_entry(run_dir)
    page = w.strain_growth_page
    assert page.model_picker.selected_ids() == ["a"]
    assert "b can no longer be chosen" in page.banner.text()


def test_corrupt_request_opens_page_with_banner(window) -> None:
    w, _calls = window
    project = w.session.require()
    run_dir = project.runs_dir / "gene-ko-20261014-101010"
    run_dir.mkdir()
    proj.run_request_path(run_dir).write_text("{oops")
    w._open_run_entry(run_dir)
    assert w.pages.currentWidget() is w.gene_ko_page
    assert "cannot be restored" in w.gene_ko_page.banner.text()
    assert "could not be read" in w.gene_ko_page.banner.text()


def test_run_without_record_keeps_inputs(window) -> None:
    w, _calls = window
    project = w.session.require()
    run_dir = project.runs_dir / "dfba-20261014-101010"
    run_dir.mkdir()
    w.dynamics_view.initial_input.setText("EX_glc__D_e=3")
    w._open_run_entry(run_dir)
    assert w.pages.currentWidget() is w.dynamics_view
    assert w.dynamics_view.initial_input.text() == "EX_glc__D_e=3"
    assert "Inputs for dfba-20261014-101010 cannot be restored" in w.dynamics_view.banner.text()


def test_record_failure_refuses_the_run_and_leaves_nothing(window, monkeypatch) -> None:
    w, calls = window

    def refuse(*_a, **_k):  # type: ignore[no-untyped-def]
        raise proj.ProjectError("disk full")

    monkeypatch.setattr(proj, "write_run_request", refuse)
    before = sorted(p.name for p in w.session.require().runs_dir.iterdir())
    w.strain_growth_page.model_picker.set_selected(["a"])
    assert w.run_strain_growth_report() == ""
    assert "disk full" in w.strain_growth_page.status.text()
    assert sorted(p.name for p in w.session.require().runs_dir.iterdir()) == before
    assert calls == []


def test_restored_ranked_result_is_not_marked_superseded(window, monkeypatch) -> None:
    w, calls = window
    page = w.gene_ko_page
    page.model_picker.set_selected(["a", "b"])
    page.members_picker.set_selected(["a"])
    assert w.run_gene_ko_search()
    run_dir = _out(_wait(calls))
    run_dir.mkdir(exist_ok=True)
    (run_dir / "gene_ko_summary.json").write_text(json.dumps({
        "target": "but", "ko_level": "gene", "warnings": [],
        "top_ranked": [{"member": "a", "gene": "g1", "score": 1.0, "target_flux": 2.0,
                        "community_growth": 0.3, "evaluation_status": "optimal"}],
    }))
    monkeypatch.setattr(w, "_inspect_gui_run", lambda _d: {"artifact_integrity": "verified"})
    page.target_input.setText("ac")
    w._open_run_entry(run_dir)
    assert page.results.has_results()
    assert "superseded" not in page.status.text()


def test_analysis_for_run_falls_back_to_the_folder_name(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "host-search-20261014-101010"
    run_dir.mkdir(parents=True)
    assert run_restore.analysis_for_run(run_dir) == ("host_search", None, "")
    (run_dir / "manifest.json").write_text(json.dumps({"workflow_kind": "strain_growth"}))
    assert run_restore.analysis_for_run(run_dir)[0] == "strain_growth"
```

- [ ] **Step 2: 실패 확인**

Run: `uv run --no-sync pytest tests/test_phase2_run_restore.py -q`
Expected: FAIL — `cmig.gui.run_restore` 없음.

- [ ] **Step 3: `cmig/gui/run_restore.py`**

```python
"""Which page a run belongs to, and the banner shown when it is reopened (Qt-free)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from cmig.io import project as proj

#: manifest `workflow_kind` -> page key
_WORKFLOW_PAGES = {
    "model_pool_search": "search",
    "multi_target_model_pool_search": "search",
    "gene_ko_search": "gene_ko",
    "strain_growth": "strain_growth",
    "abundance_impact": "ratio_impact",
    "host_microbe_bigg": "host",
    "host_search_bigg": "host_search",
    "dfba": "dfba",
    "spatial_preview": "spatial",
    "sweep": "sweep",
    "minimal_medium": "medium",
    "single": "check_growth",
}
#: summary file -> page key, for runs whose manifest names no workflow kind
_SUMMARY_PAGES = {
    "search_summary.json": "search",
    "spatial_summary.json": "spatial",
    "dfba_summary.json": "dfba",
}
#: run folder kind (the GUI names folders `<kind>-YYYYMMDD-HHMMSS[-N]`) -> page key
_FOLDER_PAGES = {
    "search": "search", "gene-ko": "gene_ko", "strain-growth": "strain_growth",
    "abundance-impact": "ratio_impact", "community": "community", "host-microbe": "host",
    "host-search": "host_search", "dfba": "dfba", "spatial": "spatial",
    "medium-growth": "medium", "minimal-medium": "medium", "sweep": "sweep",
    "check-growth": "check_growth",
}
_STAMP = re.compile(r"-\d{8}-\d{6}(?:-\d+)?$")


def _manifest_kind(run_dir: Path) -> str | None:
    try:
        manifest = json.loads((run_dir / "manifest.json").read_text())
    except (OSError, ValueError, RecursionError):
        return None
    kind = manifest.get("workflow_kind") if isinstance(manifest, dict) else None
    return kind if isinstance(kind, str) else None


def analysis_for_run(run_dir: Path) -> tuple[str | None, dict[str, Any] | None, str]:
    run_dir = Path(run_dir)
    record, problem = proj.read_run_request(run_dir)
    if record is not None:
        return str(record["analysis"]), record, ""
    kind = _manifest_kind(run_dir)
    if kind in _WORKFLOW_PAGES:
        return _WORKFLOW_PAGES[kind], None, problem
    for name, key in _SUMMARY_PAGES.items():
        if (run_dir / name).exists():
            return key, None, problem
    if (run_dir / "nodes.parquet").exists():
        return "community", None, problem
    match = _STAMP.search(run_dir.name)
    prefix = run_dir.name[: match.start()] if match else ""
    return _FOLDER_PAGES.get(prefix), None, problem


def banner_text(run_name: str, record: dict[str, Any] | None, problem: str,
                notes: list[str]) -> str:
    if record is None:
        return (f"Inputs for {run_name} cannot be restored"
                + (f": {problem}." if problem else "; the inputs on screen are unchanged."))
    text = f"Inputs restored from {run_name}."
    if notes:
        text += " Not restored: " + "; ".join(notes) + "."
    return text


def request_models_and_media(values: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Model ids (picker lists) and medium refs (`preset:`/`medium:`) named in a snapshot."""
    models: list[str] = []
    media: list[str] = []
    for value in values.values():
        if isinstance(value, list) and all(isinstance(v, str) for v in value):
            models.extend(v for v in value if v not in models)
        elif isinstance(value, str) and value.startswith(("preset:", "medium:")):
            media.append(value)
    return models, media
```

- [ ] **Step 4: 실행이 입력을 기록**

`cmig/gui/app.py`:
1. `_prepare_run`:
```python
    def _prepare_run(
        self, kind: str, model_ids: list[str], *, abundances: dict[str, float] | None = None,
        analysis: str | None = None,
    ) -> tuple[Path, Path | None]:
        """Claim a new `runs/<kind>-…` folder, write its `runs/_inputs` taxonomy and, for an
        analysis page, the page's inputs (`<run>-request.json`, for reopening the run).

        Returns (run folder, taxonomy or None when `model_ids` is empty). A model that cannot
        run, or inputs that cannot be recorded, raise `ProjectError`; the claimed folder and
        its inputs are removed again, so a refused run leaves nothing in RUNS.
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
        from cmig import __version__
        from cmig.gui.run_restore import request_models_and_media

        page = self.analysis_pages[analysis]
        values = page.snapshot()  # type: ignore[attr-defined]
        page.clear_banner()  # type: ignore[attr-defined]
        models, media = request_models_and_media(values)
        proj.write_run_request(run_dir, analysis, values, models=models, media=media,
                               cmig_version=__version__)
```
2. 모든 분석 실행이 `analysis=`를 넘긴다:
   - `run_search_fixture`: `self._prepare_run("search", model_ids, analysis="search")`
   - `_page_run_inputs(page, kind, medium_ref)`: 화면의 키를 찾아 넘긴다 — `analysis = next(k for k, p in self.analysis_pages.items() if p is page)`, `self._prepare_run(kind, model_ids, analysis=analysis)`
   - `run_community_solve`: `analysis="community"`
   - `_host_inputs(page, kind, …)`: 위와 같은 방식으로 화면의 키
   - `run_dfba`: `self._prepare_run("dfba", [], analysis="dfba")`
   - `run_spatial_preview`: `self._prepare_run("spatial", [], analysis="spatial")`
   - `run_medium_growth_check`: `self._prepare_run("medium-growth", model_ids, analysis="medium")`
   - `run_minimal_medium`: `self._prepare_run("minimal-medium", [], analysis="medium")`
   - `run_sweep`: `self._prepare_run("sweep", model_ids, analysis="sweep")`
3. `_discard_run`에 `runs/_inputs/<run>-request.json`도 지우게 한다:
```python
    @staticmethod
    def _discard_run(run_dir: Path, *inputs: Path | None) -> None:
        """Remove a claimed run folder (still empty) and its inputs when the GUI refuses it."""
        for path in (*inputs, proj.run_request_path(run_dir)):
            if path is not None:
                with suppress(OSError):
                    path.unlink()
        with suppress(OSError):
            run_dir.rmdir()
```

- [ ] **Step 5: 열 때 복원**

`cmig/gui/app.py`:
```python
    def _open_run_entry(self, run_dir: Path) -> None:
        from cmig.gui.run_restore import analysis_for_run, banner_text

        run_dir = Path(run_dir).resolve()
        key, record, problem = analysis_for_run(run_dir)
        page = self.analysis_pages.get(key or "")
        if page is None:
            self._inspector_run = None
            self.load_run_dir(run_dir)
            if self._inspector_run != str(run_dir):  # e.g. a run kind without a viewer
                self._show_run_in_inspector(run_dir)
            return
        assert key is not None
        self.show_analysis(key)
        notes = page.restore(record["values"]) if record is not None else []  # type: ignore[attr-defined]
        self._load_run_into_page(key, run_dir)
        page.show_banner(banner_text(run_dir.name, record, problem, notes))  # type: ignore[attr-defined]
        self._show_run_in_inspector(run_dir)

    def _load_run_into_page(self, key: str, run_dir: Path) -> bool:
        """Show a run's result on its page; inputs are restored first, so it is not stale."""
        if key == "search":
            return self.load_search_dir(run_dir)
        if key in ("gene_ko", "strain_growth", "ratio_impact", "host_search"):
            return self.load_ranked_dir(key, run_dir)
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
            self.sweep_view.load_results(_load_sweep_rows(run_dir / "sweep.parquet"))
            self._show_page(self.sweep_page)
            return True
        return False

    def load_ranked_dir(self, key: str, run_dir: Path) -> bool:
        summary_name, _adapter, kind, _label = self._ranked_spec(key)
        page = self.analysis_pages[key]
        if self._inspect_gui_run(run_dir) is None:
            return False
        try:
            payload = json.loads((run_dir / summary_name).read_text())
            if not isinstance(payload, dict):
                raise ValueError(f"{summary_name} is not a JSON object")
            self._show_ranked(key, payload, run_dir,
                              page.request_fields(kind))  # type: ignore[attr-defined]
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self._reject_gui_summary(run_dir, exc)
            page.status.setText(f"Readback invalid/unreadable: {exc}")  # type: ignore[attr-defined]
            return False
        self._register_run_output(run_dir)
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
            self.medium_editor.minimal_status.setText(f"Readback invalid/unreadable: {exc}")
            return False
        self._show_page(self.medium_page)
        return True
```
`_ranked_spec`의 Ratio Impact `kind`는 `"abundance_impact"`이고 `RatioImpactPage.request_fields("abundance_impact")`가 그 키를 받는다(Task 8). `show_analysis` 시작에서 화면의 배너를 지운다: `getattr(page, "clear_banner", lambda: None)()`.

Check Growth 실행(`check_growth`)은 화면 키가 아니므로 Task 15 전까지는 옛 방식으로 열린다(`analysis_pages`에 없다).

- [ ] **Step 6: 통과 확인**

Run: `uv run --no-sync pytest tests/test_phase2_run_restore.py tests/test_phase2_argv_parity.py -q && uv run --no-sync pytest tests/ -q -k "gui or workspace or app_shell or phase2" 2>&1 | tail -3`
Expected: 모두 통과. 기존 RUNS 열기 테스트가 화면 이동 때문에 실패하면, 그 실행 종류의 화면으로 가는 것이 맞는지 확인하고 단언을 새 화면으로 옮긴다.

- [ ] **Step 7: Commit**

```bash
git add cmig/gui/run_restore.py cmig/gui/app.py tests/test_phase2_run_restore.py
git commit -m "feat(gui): runs record their page inputs; reopening restores page, inputs and result

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 14: 모델 표의 점검 이유, 모델 브라우저, 상세 패널 문구, 색인 백그라운드 작업

**Files:**
- Create: `cmig/gui/model_browser.py`
- Modify: `cmig/gui/editors.py` (`ModelManagerPanel.show_project_models`: Check 이유, 두 번 클릭 신호)
- Modify: `cmig/gui/inspector.py` (`show_model` 문구, exchange 목록 제거, `show_project_summary`)
- Modify: `cmig/gui/app.py` (브라우저 화면, 모델 선택 → 브라우저, 색인 작업·캐시·실패, inspector exchange 조회 기계 제거, 선택 없음 요약)
- Modify: `cmig/gui/activity.py` (작업 이름 `"index_models": "Index Models"`, `"check_growth": "Check Growth"`)
- Modify: `tests/gui_project_helpers.py` (`make_project`가 가짜 모델에 빈 색인을 씀)
- Create: `tests/test_phase2_model_browser.py`
- Modify (옮기기): inspector exchange 목록을 확인하던 테스트 → 브라우저 Exchanges 탭

**Interfaces:**
- Consumes: Task 2의 `check_reasons`, `check_reason`, `confirmation_state`, `namespace_review_state`, `objective_warning_of`; Task 3의 `model_index`
- Produces (`cmig.gui.model_browser`):
  - `ModelBrowser(QWidget)` 신호 `confirm_requested(str)`, `revoke_requested(str)`, `check_growth_requested(str)`, `retry_index_requested(str)`
  - 위젯: `title_label`, `namespace_label`, `confirm_btn`, `revoke_btn`, `objective_label`, `objective_toggle`, `objective_terms`, `growth_label`, `medium_picker`, `skip_unknown_check`, `check_growth_btn`, `contents_label`, `retry_btn`, `tabs`, `reactions_tab`, `metabolites_tab`, `genes_tab`, `exchanges_tab`(각각 `filter_input`, `table`, `detail`)
  - 메서드: `show_model(entry: ModelEntry, index: dict | None, problem: str = "") -> None`, `set_growth(text: str) -> None`, `select(kind: str, item_id: str) -> bool`(kind: `"reaction" | "metabolite" | "gene" | "exchange"`), `model_id() -> str | None`, `snapshot() -> dict[str, Any]`(`model`, `sha256`, `medium`, `skip_unknown`), `clear_banner() -> None`(아무것도 안 함; 실행 기록 공통 처리용)
- Produces (`InspectorPanel`): `show_project_summary(project: Project, runs: list[RunEntry]) -> None`
- Produces (`ModelManagerPanel`): 신호 `model_activated(str)`
- Produces (창): `model_browser`, `_show_model(entry)`, `_ensure_indexes()`, `_index_failures: dict[str, str]`(sha256 → 이유), `_load_index(entry) -> dict | None`
- `make_project(root, names, *, statuses=None, index=True)`: `index=True`면 가짜 모델마다 빈 색인(`reactions`…`objective` 모두 빈 목록)을 쓴다. 색인 작업이 가짜 SBML을 읽으려다 실패하지 않게 한다.

- [ ] **Step 1: 테스트 도우미**

`tests/gui_project_helpers.py`의 `make_project`에 `index: bool = True` 키워드를 더하고, 각 모델을 추가한 뒤 다음을 실행한다:
```python
        if index:
            from cmig.io import model_index

            model_index.write_index(project.root, entry.sha256, entry.id,
                                    {"reactions": [], "metabolites": [], "genes": [],
                                     "exchanges": [], "objective": []})
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_phase2_model_browser.py`:
```python
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import (  # noqa: E402
    _deterministic_qt_teardown,  # noqa: F401
    make_project,
    textbook_sbml,
)
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402
from cmig.io import project as proj  # noqa: E402

APP = QApplication.instance() or QApplication([])


def _open(w, root: Path, tmp_path: Path) -> None:
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(root)


@pytest.fixture
def textbook_window(tmp_path: Path):
    project = proj.create_project(tmp_path / "p")
    proj.add_model_file(project, textbook_sbml(tmp_path / "src" / "e_coli_core.xml"))
    proj.save_project(project)
    w = build_main_window()
    _open(w, project.root, tmp_path)
    yield w
    w.close_project()


def _visible_ids(tab) -> list[str]:
    return [tab.table.item(r, 0).text() for r in range(tab.table.rowCount())
            if not tab.table.isRowHidden(r)]


def test_selecting_a_model_opens_its_browser(textbook_window) -> None:
    w = textbook_window
    w.sidebar.select("models", "e_coli_core")
    assert w.pages.currentWidget() is w.model_browser
    b = w.model_browser
    assert b.title_label.text().startswith("e_coli_core · 95 reactions · 72 metabolites")
    assert b.reactions_tab.table.rowCount() == 95
    assert b.exchanges_tab.table.rowCount() == 20
    assert b.objective_label.text() == "Objective: Biomass_Ecoli_core (biomass)"
    assert "Namespace not reviewed" in b.namespace_label.text()
    assert "0 of 20 reviewed" in b.namespace_label.text()
    assert not b.confirm_btn.isHidden() and b.revoke_btn.isHidden()


def test_filter_and_detail_navigation(textbook_window) -> None:
    w = textbook_window
    w.sidebar.select("models", "e_coli_core")
    b = w.model_browser
    b.reactions_tab.filter_input.setText("glc")
    assert set(_visible_ids(b.reactions_tab)) >= {"EX_glc__D_e", "GLCpts"}
    assert "PGI" not in _visible_ids(b.reactions_tab)
    assert b.select("reaction", "GLCpts")
    detail = b.reactions_tab.detail.toHtml()
    assert "D-Glucose" in detail and "met:glc__D_e" in detail
    b._navigate("met:glc__D_e")
    assert b.tabs.currentWidget() is b.metabolites_tab
    assert b.metabolites_tab.current_id() == "glc__D_e"
    assert "C6H12O6" in b.metabolites_tab.detail.toHtml()


def test_multi_term_objective_is_not_called_biomass(tmp_path: Path) -> None:
    from cmig.gui.model_browser import ModelBrowser

    entry = proj.ModelEntry(
        id="iAF987", file="models/iAF987.xml", source_path="x", sha256="s", format="xml",
        added="t", status="warning", biomass=[f"R{i}" for i in range(283)],
    )
    browser = ModelBrowser()
    browser.show_model(entry, None, "")
    assert browser.objective_label.text().startswith("Objective: 283 terms")
    assert "biomass)" not in browser.objective_label.text()
    assert browser.objective_terms.isHidden()
    browser.objective_toggle.setChecked(True)
    assert not browser.objective_terms.isHidden()


def test_missing_index_is_built_in_the_background(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a"], index=False)
    real = textbook_sbml(tmp_path / "src" / "real.xml")
    (project.root / project.model("a").file).write_bytes(real.read_bytes())
    entry = project.model("a")
    entry.sha256 = proj._sha256(project.root / entry.file)
    proj.save_project(project)
    w = build_main_window()
    _open(w, project.root, tmp_path)
    try:
        w.sidebar.select("models", "a")
        deadline = time.time() + 30
        while w.model_browser.reactions_tab.table.rowCount() == 0 and time.time() < deadline:
            APP.processEvents()
            time.sleep(0.05)
            w._poll_completed_jobs()
        assert w.model_browser.reactions_tab.table.rowCount() == 95
    finally:
        w.close_project()


def test_index_failure_shows_retry_and_keeps_model_selectable(
    tmp_path: Path, monkeypatch
) -> None:
    from cmig.io import model_index

    def boom(*_a, **_k):  # type: ignore[no-untyped-def]
        raise ValueError("boom")

    monkeypatch.setattr(model_index, "build_index_file", boom)
    make_project(tmp_path / "p", ["a", "b"], index=False)
    w = build_main_window()
    _open(w, tmp_path / "p", tmp_path)
    try:
        w.sidebar.select("models", "a")
        deadline = time.time() + 10
        while "boom" not in w.model_browser.contents_label.text() and time.time() < deadline:
            APP.processEvents()
            time.sleep(0.05)
            w._poll_completed_jobs()
        assert "Model contents unavailable: boom" in w.model_browser.contents_label.text()
        assert not w.model_browser.retry_btn.isHidden()
        assert "a" in w.search_view.model_picker.selected_ids()
    finally:
        w.close_project()


def test_model_table_shows_reasons(tmp_path: Path) -> None:
    make_project(tmp_path / "p", ["a", "bad"], statuses={"bad": "failed"})
    project = proj.open_project(tmp_path / "p")
    project.model("a").warnings = ["20 unresolved high-confidence namespace mappings block solve"]
    proj.save_project(project)
    w = build_main_window()
    _open(w, tmp_path / "p", tmp_path)
    try:
        table = w.model_manager.exchange_table
        checks = {table.item(r, 0).text(): table.item(r, 1).text()
                  for r in range(table.rowCount())}
        assert checks == {"a": "⚠ Namespace not reviewed", "bad": "✗ Unreadable"}
    finally:
        w.close_project()


def test_legacy_entry_reason_from_warning_text(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a"])
    entry = project.model("a")
    entry.namespace_mappings = None
    entry.warnings = ["3 low-confidence normalized candidates require review"]
    assert proj.check_reason(entry) == ("⚠", "Namespace not reviewed")


def test_inspector_wording(textbook_window) -> None:
    w = textbook_window
    w.sidebar.select("models", "e_coli_core")
    text = w.inspector.details.toPlainText()
    assert "Namespace mappings: 0 of 20 reviewed" in text
    assert "BiGG namespace coverage" not in text
    assert "Biomass:" not in text
    assert w.inspector.exchange_list.isHidden() if hasattr(w.inspector, "exchange_list") else True


def test_nothing_selected_shows_project_summary(textbook_window) -> None:
    w = textbook_window
    w._show_project_summary()
    assert w.inspector.title_label.text().startswith("Project · ")
    assert "Models: 1" in w.inspector.details.toPlainText()
```
(`test_missing_index_is_built_in_the_background`는 `proj._sha256`을 쓴다. 이름이 다르면 `cmig/io/project.py`의 sha256 계산 함수 이름으로 바꾼다.)

- [ ] **Step 3: 실패 확인**

Run: `uv run --no-sync pytest tests/test_phase2_model_browser.py -q`
Expected: FAIL — `model_browser` 없음.

- [ ] **Step 4: `cmig/gui/model_browser.py` 작성**

```python
"""Read-only browser of one model copy: reactions, metabolites, genes and exchanges, with the
model's namespace confirmation and Check Growth in its header.

Contents come from the model's index (`models/.index/<sha256>.json`); nothing here edits a
model or feeds an analysis.
"""

from __future__ import annotations

import html
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from cmig.gui.analysis_page import hide_row_numbers
from cmig.gui.builder import make_read_only, read_only_item
from cmig.gui.pickers import MediumPicker
from cmig.io import project as proj
from cmig.io.project import ModelEntry


def _bound(value: object) -> str:
    return "unbounded" if value is None else f"{float(value):g}"  # type: ignore[arg-type]


def _bounds_text(item: dict[str, Any]) -> str:
    return f"[{_bound(item.get('lower'))}, {_bound(item.get('upper'))}]"


def _arrow(item: dict[str, Any]) -> str:
    lower = item.get("lower")
    upper = item.get("upper")
    low = float("-inf") if lower is None else float(lower)
    high = float("inf") if upper is None else float(upper)
    if low < 0 < high:
        return "⇌"
    return "←" if high <= 0 else "→"


def _side(terms: list[tuple[str, float]], label: Callable[[str], str]) -> str:
    parts = []
    for met, coef in terms:
        amount = abs(coef)
        prefix = "" if amount == 1 else f"{amount:g} "
        parts.append(prefix + label(met))
    return " + ".join(parts) or "∅"


def equation(item: dict[str, Any], label: Callable[[str], str]) -> str:
    mets = item.get("metabolites") or {}
    left = [(m, float(c)) for m, c in mets.items() if float(c) < 0]
    right = [(m, float(c)) for m, c in mets.items() if float(c) > 0]
    return f"{_side(left, label)} {_arrow(item)} {_side(right, label)}"


class _EntityTab(QWidget):
    def __init__(self, headers: list[str], detail: Callable[[str], str]) -> None:
        super().__init__()
        self._detail = detail
        self._haystack: list[str] = []
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter by id or name")
        self.filter_input.setClearButtonEnabled(True)
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        make_read_only(self.table)
        hide_row_numbers(self.table)
        self.detail = QTextBrowser()
        self.detail.setOpenLinks(False)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.detail)
        splitter.setSizes([400, 180])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.addWidget(self.filter_input)
        layout.addWidget(splitter, 1)
        self.filter_input.textChanged.connect(self._apply_filter)
        self.table.itemSelectionChanged.connect(self._show_detail)

    def set_rows(self, rows: list[list[str]], haystack: list[str]) -> None:
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, text in enumerate(row):
                self.table.setItem(r, c, read_only_item(text))
        self._haystack = [h.lower() for h in haystack]
        self.detail.clear()
        self._apply_filter(self.filter_input.text())

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for r, hay in enumerate(self._haystack):
            self.table.setRowHidden(r, bool(needle) and needle not in hay)

    def current_id(self) -> str | None:
        row = self.table.currentRow()
        item = None if row < 0 else self.table.item(row, 0)
        return None if item is None else item.text()

    def select_id(self, item_id: str) -> bool:
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item is not None and item.text() == item_id:
                if self.table.isRowHidden(r):
                    self.filter_input.clear()
                self.table.setCurrentCell(r, 0)
                self.table.scrollToItem(item)
                self._show_detail()
                return True
        return False

    def _show_detail(self) -> None:
        item_id = self.current_id()
        self.detail.setHtml("" if item_id is None else self._detail(item_id))


class ModelBrowser(QWidget):
    confirm_requested = Signal(str)
    revoke_requested = Signal(str)
    check_growth_requested = Signal(str)
    retry_index_requested = Signal(str)

    _KINDS = ("reaction", "metabolite", "gene", "exchange")

    def __init__(self) -> None:
        super().__init__()
        self._entry: ModelEntry | None = None
        self._reactions: dict[str, dict[str, Any]] = {}
        self._metabolites: dict[str, dict[str, Any]] = {}
        self._genes: dict[str, dict[str, Any]] = {}
        self._met_reactions: dict[str, list[str]] = {}
        self.title_label = QLabel("")
        font = QFont(self.title_label.font())
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() * 1.2)
        self.title_label.setFont(font)
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        self.medium_picker = MediumPicker()
        self.skip_unknown_check = QCheckBox("Skip medium metabolites this model lacks")
        self.check_growth_btn = QPushButton("Check Growth")
        self.namespace_label = QLabel("")
        self.namespace_label.setWordWrap(True)
        self.confirm_btn = QPushButton("Confirm…")
        self.revoke_btn = QPushButton("Revoke")
        self.objective_label = QLabel("")
        self.objective_label.setWordWrap(True)
        self.objective_toggle = QToolButton()
        self.objective_toggle.setText("Show terms")
        self.objective_toggle.setCheckable(True)
        self.objective_terms = QLabel("")
        self.objective_terms.setWordWrap(True)
        self.objective_terms.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.objective_terms.setVisible(False)
        self.objective_toggle.toggled.connect(self.objective_terms.setVisible)
        self.growth_label = QLabel("Growth: not checked yet")
        self.growth_label.setWordWrap(True)
        self.growth_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.contents_label = QLabel("")
        self.contents_label.setWordWrap(True)
        self.retry_btn = QPushButton("Retry")
        self.retry_btn.setVisible(False)
        self.reactions_tab = _EntityTab(["ID", "Name", "Bounds", "Subsystem"],
                                        self._reaction_detail)
        self.metabolites_tab = _EntityTab(["ID", "Name", "Formula", "Compartment"],
                                          self._metabolite_detail)
        self.genes_tab = _EntityTab(["ID", "Name", "Reactions"], self._gene_detail)
        self.exchanges_tab = _EntityTab(["ID", "Name", "Bounds"], self._reaction_detail)
        self.tabs = QTabWidget()
        for tab, title in ((self.reactions_tab, "Reactions"),
                           (self.metabolites_tab, "Metabolites"),
                           (self.genes_tab, "Genes"), (self.exchanges_tab, "Exchanges")):
            self.tabs.addTab(tab, title)
            tab.detail.anchorClicked.connect(lambda url: self._navigate(url.toString()))
        header = QHBoxLayout()
        header.addWidget(self.title_label, 1)
        header.addWidget(self.medium_picker)
        header.addWidget(self.check_growth_btn)
        namespace_row = QHBoxLayout()
        namespace_row.addWidget(self.namespace_label, 1)
        namespace_row.addWidget(self.confirm_btn)
        namespace_row.addWidget(self.revoke_btn)
        objective_row = QHBoxLayout()
        objective_row.addWidget(self.objective_label, 1)
        objective_row.addWidget(self.objective_toggle)
        contents_row = QHBoxLayout()
        contents_row.addWidget(self.contents_label, 1)
        contents_row.addWidget(self.retry_btn)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.addLayout(header)
        layout.addWidget(self.skip_unknown_check, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(namespace_row)
        layout.addLayout(objective_row)
        layout.addWidget(self.objective_terms)
        layout.addWidget(self.growth_label)
        layout.addLayout(contents_row)
        layout.addWidget(self.tabs, 1)
        self.confirm_btn.clicked.connect(lambda: self._emit(self.confirm_requested))
        self.revoke_btn.clicked.connect(lambda: self._emit(self.revoke_requested))
        self.check_growth_btn.clicked.connect(lambda: self._emit(self.check_growth_requested))
        self.retry_btn.clicked.connect(lambda: self._emit(self.retry_index_requested))

    def _emit(self, signal: Any) -> None:
        if self._entry is not None:
            signal.emit(self._entry.id)

    def model_id(self) -> str | None:
        return None if self._entry is None else self._entry.id

    def clear_banner(self) -> None:
        """The run-recording path clears a page banner; the browser has none."""

    def snapshot(self) -> dict[str, Any]:
        entry = self._entry
        return {
            "model": None if entry is None else entry.id,
            "sha256": None if entry is None else entry.sha256,
            "medium": self.medium_picker.current_ref(),
            "skip_unknown": self.skip_unknown_check.isChecked(),
        }

    def set_growth(self, text: str) -> None:
        self.growth_label.setText(text)

    # ── header ───────────────────────────────────────────────────────────────────────
    def show_model(self, entry: ModelEntry, index: dict[str, Any] | None,
                   problem: str = "") -> None:
        self._entry = entry
        counts = (f"{entry.n_reactions} reactions · {entry.n_metabolites} metabolites · "
                  f"{entry.n_genes} genes" if entry.n_reactions is not None
                  else "size not recorded")
        self.title_label.setText(f"{entry.id} · {counts}")
        self._show_namespace(entry)
        self._show_objective(entry)
        self.growth_label.setText("Growth: not checked yet")
        runnable = entry.status in ("ok", "warning") and entry.integrity == "ok"
        confirmed = proj.namespace_confirmed(entry)
        self.check_growth_btn.setEnabled(runnable and confirmed)
        self.check_growth_btn.setToolTip(
            "" if runnable and confirmed else
            ("Confirm this model's namespace first" if runnable
             else "This model cannot be run: " + proj.check_reason(entry)[1])
        )
        self._show_contents(index, problem)

    def _show_namespace(self, entry: ModelEntry) -> None:
        state = proj.confirmation_state(entry)
        counts = entry.namespace_mappings
        mapping = ("" if counts is None else
                   f" · mappings: {counts.get('resolved', 0)} of {counts.get('total', 0)} "
                   "reviewed")
        if state == "confirmed":
            when = str((entry.namespace_confirmed or {}).get("at", ""))[:10]
            text = f"✓ Namespace confirmed by you · {when}"
        elif state == "changed":
            text = "⚠ Changed since confirmed — confirm again before running it"
        elif proj.namespace_review_state(entry) in ("blocked", "review"):
            text = "⚠ Namespace not reviewed — needed before community analyses"
        else:
            text = "Namespace not confirmed — needed before community analyses"
        self.namespace_label.setText(text + mapping)
        self.confirm_btn.setVisible(state != "confirmed")
        self.revoke_btn.setVisible(state == "confirmed")

    def _show_objective(self, entry: ModelEntry) -> None:
        terms = list(entry.biomass)
        warning = proj.objective_warning_of(entry)
        self.objective_toggle.setChecked(False)
        if not terms:
            self.objective_label.setText("⚠ No objective")
            self.objective_toggle.setVisible(False)
        elif len(terms) == 1 and warning is None:
            self.objective_label.setText(f"Objective: {terms[0]} (biomass)")
            self.objective_toggle.setVisible(False)
        else:
            self.objective_label.setText(
                f"Objective: {len(terms)} {'term' if len(terms) == 1 else 'terms'} — "
                f"{warning or 'not a single biomass reaction'}"
            )
            self.objective_toggle.setVisible(True)
        self.objective_terms.setText(", ".join(terms))

    # ── contents ─────────────────────────────────────────────────────────────────────
    def _show_contents(self, index: dict[str, Any] | None, problem: str) -> None:
        if index is None:
            self.tabs.setVisible(False)
            self.contents_label.setVisible(True)
            self.contents_label.setText(
                f"Model contents unavailable: {problem}" if problem
                else "Building model contents…"
            )
            self.retry_btn.setVisible(bool(problem))
            return
        self.contents_label.setVisible(False)
        self.retry_btn.setVisible(False)
        self.tabs.setVisible(True)
        self._reactions = {r["id"]: r for r in index.get("reactions", [])}
        self._metabolites = {m["id"]: m for m in index.get("metabolites", [])}
        self._genes = {g["id"]: g for g in index.get("genes", [])}
        self._met_reactions = {}
        for rid, reaction in self._reactions.items():
            for met in reaction.get("metabolites") or {}:
                self._met_reactions.setdefault(met, []).append(rid)

        def ids(item: dict[str, Any]) -> str:
            return equation(item, lambda m: m)

        reactions = list(self._reactions.values())
        self.reactions_tab.set_rows(
            [[r["id"], r.get("name", ""), _bounds_text(r), r.get("subsystem", "")]
             for r in reactions],
            [f"{r['id']} {r.get('name', '')} {ids(r)}" for r in reactions],
        )
        metabolites = list(self._metabolites.values())
        self.metabolites_tab.set_rows(
            [[m["id"], m.get("name", ""), m.get("formula", ""), m.get("compartment", "")]
             for m in metabolites],
            [f"{m['id']} {m.get('name', '')}" for m in metabolites],
        )
        genes = list(self._genes.values())
        self.genes_tab.set_rows(
            [[g["id"], g.get("name", ""), str(len(g.get("reactions") or []))] for g in genes],
            [f"{g['id']} {g.get('name', '')}" for g in genes],
        )
        exchanges = [self._reactions[e] for e in index.get("exchanges", [])
                     if e in self._reactions]
        self.exchanges_tab.set_rows(
            [[r["id"], r.get("name", ""), _bounds_text(r)] for r in exchanges],
            [f"{r['id']} {r.get('name', '')} {ids(r)}" for r in exchanges],
        )

    def _met_link(self, met: str) -> str:
        name = self._metabolites.get(met, {}).get("name") or met
        return f'<a href="met:{html.escape(met)}">{html.escape(str(name))}</a>'

    def _reaction_detail(self, rid: str) -> str:
        r = self._reactions.get(rid)
        if r is None:
            return ""
        genes = [g for g in self._genes if g in str(r.get("gpr", "")).replace("(", " ")
                 .replace(")", " ").split()]
        gene_links = ", ".join(f'<a href="gene:{html.escape(g)}">{html.escape(g)}</a>'
                               for g in genes)
        return (
            f"<b>{html.escape(rid)}</b> — {html.escape(str(r.get('name', '')))}<br>"
            f"{equation(r, self._met_link)}<br>"
            f"<small>{html.escape(equation(r, lambda m: m))}</small><br>"
            f"<b>Bounds</b>: {_bounds_text(r)}<br>"
            f"<b>GPR</b>: {html.escape(str(r.get('gpr') or 'none'))}"
            + (f" ({gene_links})" if gene_links else "") + "<br>"
            f"<b>Subsystem</b>: {html.escape(str(r.get('subsystem') or 'not recorded'))}"
        )

    def _metabolite_detail(self, met: str) -> str:
        m = self._metabolites.get(met)
        if m is None:
            return ""
        links = ", ".join(f'<a href="rxn:{html.escape(r)}">{html.escape(r)}</a>'
                          for r in self._met_reactions.get(met, []))
        charge = m.get("charge")
        return (
            f"<b>{html.escape(met)}</b> — {html.escape(str(m.get('name', '')))}<br>"
            f"<b>Formula</b>: {html.escape(str(m.get('formula') or 'not recorded'))}<br>"
            f"<b>Charge</b>: {'not recorded' if charge is None else charge}<br>"
            f"<b>Compartment</b>: {html.escape(str(m.get('compartment') or 'not recorded'))}"
            f"<br><b>Reactions</b>: {links or 'none'}"
        )

    def _gene_detail(self, gid: str) -> str:
        g = self._genes.get(gid)
        if g is None:
            return ""
        links = ", ".join(f'<a href="rxn:{html.escape(r)}">{html.escape(r)}</a>'
                          for r in g.get("reactions") or [])
        return (f"<b>{html.escape(gid)}</b> — {html.escape(str(g.get('name', '')))}<br>"
                f"<b>Reactions</b>: {links or 'none'}")

    def _navigate(self, link: str) -> None:
        kind, _, item_id = link.partition(":")
        target = {"rxn": "reaction", "met": "metabolite", "gene": "gene"}.get(kind)
        if target is not None:
            self.select(target, item_id)

    def select(self, kind: str, item_id: str) -> bool:
        tab = {"reaction": self.reactions_tab, "metabolite": self.metabolites_tab,
               "gene": self.genes_tab, "exchange": self.exchanges_tab}.get(kind)
        if tab is None:
            return False
        self.tabs.setCurrentWidget(tab)
        return tab.select_id(item_id)
```
(`QUrl` import는 `anchorClicked`의 인자 타입을 위해 남긴다. Ruff가 쓰이지 않는다고 하면 지운다.)

- [ ] **Step 5: 모델 표와 상세 패널**

`cmig/gui/editors.py`의 `ModelManagerPanel`:
- 클래스에 `model_activated = Signal(str)`을 더하고, `__init__`에서 `self.exchange_table.cellDoubleClicked.connect(lambda row, _col: self._activate(row))`.
```python
    def _activate(self, row: int) -> None:
        item = self.exchange_table.item(row, 0)
        if item is not None and self.exchange_table.columnCount() == 4:
            self.model_activated.emit(item.text())
```
- `show_project_models`의 `values`를 다음으로 바꾼다:
```python
        from cmig.io.project import check_reasons

        for row, entry in enumerate(models):
            reasons = check_reasons(entry)
            symbol, text = reasons[0]
            values = [entry.id, f"{symbol} {text}",
                      "—" if entry.n_reactions is None else str(entry.n_reactions), entry.file]
            for col, value in enumerate(values):
                item = read_only_item(value)
                if col == 1:
                    item.setToolTip("\n".join([f"{s} {t}" for s, t in reasons] + entry.warnings))
                self.exchange_table.setItem(row, col, item)
        self.biomass_label.setText("Double-click a model, or select it in the sidebar, to "
                                   "browse it.")
```
(`Signal` import를 더한다.)

`cmig/gui/inspector.py`:
- exchange 목록 위젯(`exchange_filter`, `exchange_list`, `_set_exchanges`, `_filter_exchanges`)을 지운다. `show_model(self, project, entry)` 서명에서 `exchanges` 인자를 지운다.
- `show_model`의 body를 바꾼다:
```python
        counts_ns = entry.namespace_mappings
        mappings = (None if counts_ns is None else
                    f"{counts_ns.get('resolved', 0)} of {counts_ns.get('total', 0)} reviewed")
        state = confirmation_state(entry)
        namespace = {
            "confirmed": "confirmed by you",
            "changed": "changed since confirmed",
        }.get(state, "not confirmed")
        terms = list(entry.biomass)
        warning = objective_warning_of(entry)
        objective = (None if not terms else
                     f"{terms[0]} (biomass)" if len(terms) == 1 and warning is None
                     else f"{len(terms)} terms — {warning or 'not a single biomass reaction'}")
        checked = entry.status in ("ok", "warning")
        body = (
            _row("Check", " · ".join(f"{s} {t}" for s, t in check_reasons(entry)))
            + _row("Warnings", "; ".join(entry.warnings) or ("none" if checked else None))
            + _row("Error", entry.error or ("none" if checked else None))
            + _row("Size", counts)
            + _row("Objective", objective)
            + _row("Namespace", namespace)
            + _row("Namespace mappings", mappings)
            + _row("File", integrity)
            + _row("SHA-256", entry.sha256[:12] + "…" if entry.sha256 else None)
            + _row("Original", entry.source_path)
            + _row("Format", entry.format)
        )
```
(`check_reasons`, `confirmation_state`, `objective_warning_of`를 `cmig.io.project`에서 import한다. `_row`가 "Namespace mappings: 0 of 20 reviewed" 형태를 만든다.)
- 새 메서드:
```python
    def show_project_summary(self, project: Project, runs: list[RunEntry]) -> None:
        ready = sum(1 for m in project.models if check_reason(m)[0] == "✓")
        last = max(runs, key=lambda r: r.mtime, default=None)
        self.title_label.setText(f"Project · {project.name}")
        self.details.setHtml(
            _row("Models", f"{len(project.models)} ({ready} ready)")
            + _row("Project media", str(len(project.media)))
            + _row("Runs", str(len(runs)))
            + _row("Last run", None if last is None else f"{last.label} · {last.status}")
        )
        self._set_actions("", project.root)
```

- [ ] **Step 6: 창**

`cmig/gui/app.py`:
1. `self.model_browser = ModelBrowser()`를 만들고 `self.pages.addWidget(self.model_browser)`. `self._index_failures: dict[str, str] = {}`, `self._index_job: str | None = None`, `self._index_cache: dict[str, dict[str, Any]] = {}`.
2. inspector exchange 조회 기계를 지운다: `_exchange_cache`, `_exchange_jobs`, `_stale_exchange_jobs`, `_cancel_stale_exchange_jobs`, `_exchange_placeholder`, `_finish_exchange_jobs`와 이들을 부르는 줄(`_poll_completed_jobs` 첫 부분, `closeEvent`, `_close_session` 등). `_inspect_model`은 `self.inspector.show_model(project, entry)` 한 줄과 `_inspector_run`, `_inspected_model` 갱신만 남긴다.
3. 모델 선택:
```python
    def _show_model(self, entry: ModelEntry) -> None:
        self._inspect_model(entry)
        self.current_analysis = None
        index = self._load_index(entry)
        self.model_browser.show_model(entry, index, self._index_failures.get(entry.sha256, ""))
        self._show_page(self.model_browser)
        if index is None and entry.sha256 not in self._index_failures:
            self._ensure_indexes()
```
`_on_sidebar_selection`의 `group == "models"` 분기를 `self._show_model(project.model(key))`로 바꾼다. `self.model_manager.model_activated.connect(lambda mid: self.sidebar.select("models", mid))`를 연결한다.
4. 색인:
```python
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
        """Build missing model indexes in one background job (listed in Activity)."""
        from cmig.io import model_index

        project = self.session.project
        if project is None or self._index_job is not None:
            return
        wanted = [
            (m.id, m.sha256, proj.model_path(project, m)) for m in project.models
            if m.status in ("ok", "warning") and m.integrity == "ok"
            and m.sha256 not in self._index_failures
            and not model_index.index_path(project.root, m.sha256).exists()
        ]
        if not wanted:
            return
        root = project.root

        def _job(ctx: Any) -> dict[str, Any]:
            failures: dict[str, str] = {}
            for i, (model_id, sha, path) in enumerate(wanted):
                if ctx.cancelled:
                    break
                ctx.report_progress(i, len(wanted))
                try:
                    model_index.build_index_file(root, path, sha, model_id)
                except Exception as exc:  # noqa: BLE001 - one bad model must not stop the rest
                    failures[sha] = str(exc) or type(exc).__name__
            ctx.report_progress(len(wanted), len(wanted))
            return {"failures": failures, "root": str(root)}

        self._index_job = self.runner.submit("index_models", _job)
        self.bridge.track(self._index_job)
        self._job_commands[self._index_job] = f"Index {len(wanted)} model(s)"

    def _finish_index_job(self) -> None:
        jid = self._index_job
        if jid is None:
            return
        job = self.runner.poll(jid)
        if job.status not in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
            return
        self._index_job = None
        project = self.session.project
        result = job.result if isinstance(job.result, dict) else {}
        if project is not None and result.get("root") == str(project.root):
            self._index_failures.update(result.get("failures", {}))
        if self.pages.currentWidget() is self.model_browser and project is not None:
            model_id = self.model_browser.model_id()
            if model_id is not None:
                entry = project.model(model_id)
                self.model_browser.show_model(entry, self._load_index(entry),
                                              self._index_failures.get(entry.sha256, ""))
        self._index_changed()

    def _index_changed(self) -> None:
        """Hook for the project search table (Task 16)."""
```
`_poll_completed_jobs` 시작 부분에 `self._finish_index_job()`. 프로젝트를 열거나 바꿀 때(`refresh_workspace`의 `switched` 분기)와 가져오기가 끝났을 때(`_finish_import` 끝) `self._ensure_indexes()`를 부른다. 프로젝트를 바꾸면 `_index_failures`와 `_index_cache`를 비운다. `self.model_browser.retry_index_requested.connect(self._retry_index)`:
```python
    def _retry_index(self, model_id: str) -> None:
        project = self.session.require()
        entry = project.model(model_id)
        self._index_failures.pop(entry.sha256, None)
        self.model_browser.show_model(entry, None, "")
        self._ensure_indexes()
```
5. 선택 없음 요약:
```python
    def _show_project_summary(self) -> None:
        project = self.session.project
        if project is None:
            self.inspector.clear()
        else:
            self.inspector.show_project_summary(project, self._display_runs(self.session.runs()))
```
`refresh_workspace`의 `switched` 분기에서 `self.inspector.clear()`를 `self._show_project_summary()`로 바꾼다.

`cmig/gui/activity.py`의 작업 이름표에 `"index_models": "Index Models"`, `"check_growth": "Check Growth"`를 더한다.

- [ ] **Step 7: 기존 테스트 옮기기와 통과 확인**

inspector의 exchange 목록(`exchange_list`, `exchange_filter`, "Loading exchanges…")을 확인하던 테스트는 브라우저 Exchanges 탭(`w.model_browser.exchanges_tab`)으로 옮긴다. 이 테스트들은 가짜 모델을 쓰므로, 색인이 실제 내용을 가져야 하는 테스트는 `textbook_sbml`로 만든 모델을 쓴다. `show_model(project, entry, exchanges)` 호출은 인자 두 개로 바꾼다.

Run: `uv run --no-sync pytest tests/test_phase2_model_browser.py -q && uv run --no-sync pytest tests/ -q -k "gui or workspace or app_shell or phase2 or inspector" 2>&1 | tail -3`
Expected: 모두 통과.

- [ ] **Step 8: Commit**

```bash
git add cmig/gui tests
git commit -m "feat(gui): model browser with reasons, objective and namespace wording, background index

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 15: Check Growth와 모델별 namespace 확인

**Files:**
- Create: `cmig/gui/growth.py` (Qt 없음)
- Modify: `cmig/gui/app.py` (확인·해제 처리, `run_check_growth`, 완료 처리, 최근 결과 표시, 분석 확인란 기본값, RUNS에서 Check Growth 열기)
- Modify: `cmig/gui/editors.py` (`MediumEditor.namespace_note`)
- Create: `tests/test_phase2_check_growth.py`, `tests/test_growth_reading.py`

**Interfaces:**
- Consumes: `ProjectSession.confirm_namespace`/`revoke_namespace`(Task 2), `confirmation_summary`, `namespace_confirmed`, `objective_warning_of`; `ModelBrowser`(Task 14); `_prepare_run(..., analysis="check_growth")`(Task 13); `run_restore.analysis_for_run`가 `single` → `"check_growth"`(Task 13)
- Produces (`cmig.gui.growth`):
  - `GrowthReading(symbol: str, text: str)` (frozen dataclass)
  - `solver_text(name: object) -> str` — `"gurobi"` → `"Gurobi (full-flux)"`, `"osqp"` → `"OSQP (QP-only approximate)"`, 그 밖 → `"solver not recorded"`
  - `medium_text(ref: str) -> str` — `""` → `"model default"`, `"preset:x"`/`"medium:x"` → `"x (exact)"`
  - `read_growth(run_dir: Path, *, objective_warning: str | None, medium: str, finished: str) -> GrowthReading`
  - `run_clock(run_name: str) -> str` — `check-growth-20261014-103100` → `"10:31"`
  - `latest_check_growth(root: Path, model_id: str, sha256: str) -> Path | None`
- Produces (창): `run_check_growth(model_id: str | None = None) -> str`, `_check_growth_jobs: dict[str, tuple[Path, str, str]]`(job → run, 모델 id, sha256), `_confirm_namespace(model_id)`, `_revoke_namespace(model_id)`, `_apply_namespace_defaults()`
- 확인란 규칙: Community와 Medium Editor는 고른 모델이 모두 확인됐을 때만 확인란을 체크한 채 시작하고, 옆 `namespace_note`에 "All N models confirmed in this project" 또는 "<ids> not confirmed"를 적는다. 사용자가 직접 누른 상태(`clicked`)는 그 화면의 모델 선택이 바뀔 때까지 유지한다.

- [ ] **Step 1: 판독 테스트 (Qt 없음)**

`tests/test_growth_reading.py`:
```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cmig.gui.growth import (
    latest_check_growth,
    medium_text,
    read_growth,
    run_clock,
    solver_text,
)
from cmig.io import project as proj


def _summary(tmp_path: Path, **overrides: object) -> Path:
    payload: dict[str, object] = {
        "status": "ok", "solver": "gurobi", "growth_feasible": True, "growth_threshold": 1e-6,
        "warnings": [], "methods": {"FBA": {"status": "optimal", "objective": 0.8739}},
    }
    payload.update(overrides)
    run = tmp_path / "check-growth-20261014-103100"
    run.mkdir(exist_ok=True)
    (run / "single_summary.json").write_text(json.dumps(payload))
    return run


def _read(run: Path, warning: str | None = None):
    return read_growth(run, objective_warning=warning, medium="western_diet (exact)",
                       finished="10:31")


def test_growth_ok(tmp_path: Path) -> None:
    reading = _read(_summary(tmp_path))
    assert reading.symbol == "✓"
    assert reading.text == ("Growth 0.8739 h⁻¹ · Gurobi (full-flux) · western_diet (exact) · "
                            "10:31")


def test_osqp_is_labelled_approximate(tmp_path: Path) -> None:
    assert "OSQP (QP-only approximate)" in _read(_summary(tmp_path, solver="osqp")).text


def test_no_growth_is_a_failure_not_zero(tmp_path: Path) -> None:
    run = _summary(tmp_path, growth_feasible=False,
                   methods={"FBA": {"status": "optimal", "objective": 0.0}})
    reading = _read(run)
    assert reading.symbol == "✗"
    assert reading.text.startswith("No growth (below 1e-06)")


def test_infeasible(tmp_path: Path) -> None:
    run = _summary(tmp_path, methods={"FBA": {"status": "infeasible", "objective": None}})
    assert _read(run).text.startswith("✗ Infeasible") is False  # symbol is separate
    assert _read(run).symbol == "✗" and _read(run).text.startswith("Infeasible")


def test_objective_that_is_not_growth_is_never_called_growth(tmp_path: Path) -> None:
    reading = _read(_summary(tmp_path), warning="283 objective terms")
    assert reading.symbol == "⚠"
    assert reading.text.startswith("Objective value 0.8739 — 283 objective terms")
    assert "Growth" not in reading.text


def test_degraded_is_flagged_with_its_warnings(tmp_path: Path) -> None:
    run = _summary(tmp_path, status="degraded", warnings=["dropped EX_x_e"])
    reading = _read(run)
    assert reading.symbol == "⚠" and "dropped EX_x_e" in reading.text


def test_unreadable_summary(tmp_path: Path) -> None:
    run = tmp_path / "check-growth-1"
    run.mkdir()
    reading = _read(run)
    assert reading.symbol == "✗" and reading.text.startswith("Failed:")


@pytest.mark.parametrize(("ref", "text"), [("", "model default"),
                                           ("preset:western_diet", "western_diet (exact)"),
                                           ("medium:mine", "mine (exact)")])
def test_medium_text(ref: str, text: str) -> None:
    assert medium_text(ref) == text


def test_solver_and_clock() -> None:
    assert solver_text("gurobi") == "Gurobi (full-flux)"
    assert solver_text(None) == "solver not recorded"
    assert run_clock("check-growth-20261014-103100") == "10:31"
    assert run_clock("odd") == ""


def test_latest_check_growth_matches_model_and_file(tmp_path: Path) -> None:
    root = tmp_path
    runs = root / "runs"
    for name, model, sha in (("check-growth-20261014-090000", "a", "s1"),
                             ("check-growth-20261014-100000", "a", "s1"),
                             ("check-growth-20261014-110000", "a", "OLD"),
                             ("check-growth-20261014-120000", "b", "s2")):
        run = runs / name
        run.mkdir(parents=True)
        proj.write_run_request(run, "check_growth", {"model": model, "sha256": sha},
                               models=[model], media=[], cmig_version="0")
    found = latest_check_growth(root, "a", "s1")
    assert found is not None and found.name == "check-growth-20261014-100000"
    assert latest_check_growth(root, "c", "x") is None
```

- [ ] **Step 2: 실패 확인**

Run: `uv run --no-sync pytest tests/test_growth_reading.py -q`
Expected: FAIL — `cmig.gui.growth` 없음.

- [ ] **Step 3: `cmig/gui/growth.py`**

```python
"""Reading a Check Growth run (`cmig single --fba`) for the model browser header (Qt-free).

Never reports a failed, infeasible or zero-growth run as growth, and never calls the value of
an objective that is not a growth rate "Growth".
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from cmig.io import project as proj

_CLOCK = re.compile(r"-(\d{8})-(\d{2})(\d{2})(\d{2})(?:-\d+)?$")


@dataclass(frozen=True)
class GrowthReading:
    symbol: str
    text: str


def solver_text(name: object) -> str:
    return {"gurobi": "Gurobi (full-flux)", "osqp": "OSQP (QP-only approximate)"}.get(
        str(name) if isinstance(name, str) else "", "solver not recorded"
    )


def medium_text(ref: str) -> str:
    if not ref:
        return "model default"
    return f"{ref.partition(':')[2] or ref} (exact)"


def run_clock(run_name: str) -> str:
    match = _CLOCK.search(run_name)
    return "" if match is None else f"{match.group(2)}:{match.group(3)}"


def read_growth(run_dir: Path, *, objective_warning: str | None, medium: str,
                finished: str) -> GrowthReading:
    try:
        summary = json.loads((Path(run_dir) / "single_summary.json").read_text())
        fba = summary["methods"]["FBA"]
        if not isinstance(summary, dict) or not isinstance(fba, dict):
            raise ValueError("unexpected summary shape")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return GrowthReading("✗", f"Failed: the result could not be read ({exc})")
    tail = " · ".join(part for part in (solver_text(summary.get("solver")), medium, finished)
                      if part)
    run_status = str(summary.get("status", "unknown"))
    if run_status == "failed":
        diagnostic = fba.get("diagnostic") or "the run failed"
        return GrowthReading("✗", f"Failed: {diagnostic}")
    status = str(fba.get("status", "unknown"))
    if status != "optimal":
        return GrowthReading("✗", f"{status.replace('_', ' ').capitalize()} · {tail}")
    value = fba.get("objective")
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return GrowthReading("✗", f"No objective value recorded · {tail}")
    warnings = [str(w) for w in summary.get("warnings") or []]
    note = f" · {'; '.join(warnings)}" if run_status == "degraded" and warnings else ""
    if objective_warning is not None:
        return GrowthReading(
            "⚠", f"Objective value {float(value):.4g} — {objective_warning} · {tail}{note}"
        )
    if not summary.get("growth_feasible"):
        threshold = summary.get("growth_threshold")
        below = f" (below {float(threshold):g})" if isinstance(threshold, (int, float)) else ""
        return GrowthReading("✗", f"No growth{below} · {tail}")
    symbol = "⚠" if run_status == "degraded" else "✓"
    return GrowthReading(symbol, f"Growth {float(value):.4g} h⁻¹ · {tail}{note}")


def latest_check_growth(root: Path, model_id: str, sha256: str) -> Path | None:
    """The newest Check Growth run recorded for exactly this model file, or None."""
    inputs = Path(root) / "runs" / "_inputs"
    found: list[Path] = []
    for path in inputs.glob("check-growth-*-request.json"):
        run_dir = Path(root) / "runs" / path.name.removesuffix("-request.json")
        record, _problem = proj.read_run_request(run_dir)
        if (record is not None and record.get("analysis") == "check_growth"
                and record["values"].get("model") == model_id
                and record["values"].get("sha256") == sha256 and run_dir.is_dir()):
            found.append(run_dir)
    return max(found, key=lambda p: p.name, default=None)
```
`test_infeasible`의 첫 단언은 `text`에 기호가 들어가지 않음을 확인한다(기호는 `symbol`에 따로 있다).

- [ ] **Step 4: GUI 테스트 작성**

`tests/test_phase2_check_growth.py`:
```python
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402
from cmig.io import project as proj  # noqa: E402

APP = QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path: Path, monkeypatch):
    make_project(tmp_path / "p", ["a", "b"])
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(tmp_path / "p")
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    calls: list[list[str]] = []

    def fake_single(argv: list[str]) -> int:
        calls.append(list(argv))
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "single_summary.json").write_text(json.dumps({
            "status": "ok", "solver": "gurobi", "growth_feasible": True,
            "growth_threshold": 1e-6, "warnings": [],
            "methods": {"FBA": {"status": "optimal", "objective": 0.5}},
        }))
        return 0

    monkeypatch.setattr("cmig.cli.main.main", fake_single)
    monkeypatch.setattr(w, "_inspect_gui_run", lambda _d: {"artifact_integrity": "verified"})
    yield w, calls
    w.close_project()


def _wait_text(w, needle: str) -> None:
    deadline = time.time() + 10
    while needle not in w.model_browser.growth_label.text() and time.time() < deadline:
        APP.processEvents()
        time.sleep(0.02)
        w._poll_completed_jobs()


def test_unconfirmed_model_is_refused(window) -> None:
    w, calls = window
    w.sidebar.select("models", "a")
    assert not w.model_browser.check_growth_btn.isEnabled()
    assert w.run_check_growth("a") == ""
    assert "Confirm" in w.model_browser.growth_label.text()
    assert calls == []


def test_confirm_then_check_growth(window) -> None:
    w, calls = window
    w.sidebar.select("models", "a")
    w.model_browser.confirm_btn.click()
    assert proj.namespace_confirmed(w.session.require().model("a"))
    assert w.model_browser.check_growth_btn.isEnabled()
    w.model_browser.medium_picker.set_ref("preset:western_diet")
    assert w.run_check_growth("a")
    _wait_text(w, "Growth 0.5")
    argv = calls[0]
    assert argv[:2] == ["single", "--model"]
    assert argv[argv.index("--medium") + 1].endswith("western_diet.csv")
    assert "--exact-medium" in argv and "--assume-bigg-namespace" in argv
    assert "--allow-unknown-medium" not in argv
    assert Path(argv[argv.index("--out") + 1]).name.startswith("check-growth-")
    assert "western_diet (exact)" in w.model_browser.growth_label.text()


def test_last_result_comes_back_after_reselect(window) -> None:
    w, _calls = window
    w.sidebar.select("models", "a")
    w.model_browser.confirm_btn.click()
    assert w.run_check_growth("a")
    _wait_text(w, "Growth 0.5")
    w.sidebar.select("models", "b")
    assert "not checked yet" in w.model_browser.growth_label.text()
    w.sidebar.select("models", "a")
    assert "Growth 0.5" in w.model_browser.growth_label.text()


def test_refusal_for_unknown_medium_suggests_the_option(window, monkeypatch) -> None:
    w, _calls = window

    def refuse(argv: list[str]) -> int:
        import sys

        print("medium exchange has no counterpart in the target model (matched on "
              "metabolite): ['EX_x_e']", file=sys.stderr)
        return 2

    monkeypatch.setattr("cmig.cli.main.main", refuse)
    w.sidebar.select("models", "a")
    w.model_browser.confirm_btn.click()
    assert w.run_check_growth("a")
    _wait_text(w, "Failed")
    text = w.model_browser.growth_label.text()
    assert text.startswith("✗ Failed")
    assert "Skip medium metabolites this model lacks" in text


def test_changed_file_voids_pretick_and_check_growth(window) -> None:
    w, _calls = window
    project = w.session.require()
    w.session.confirm_namespace("a")
    w.session.confirm_namespace("b")
    w.community_builder.model_picker.set_selected(["a", "b"])
    assert w.community_builder.assume_bigg_check.isChecked()
    assert "All 2 models confirmed" in w.community_builder.namespace_note.text()
    (project.root / project.model("b").file).write_text("<sbml id='edited'/>")
    proj.verify_checksums(project)
    w.refresh_workspace()
    assert proj.confirmation_state(project.model("b")) == "changed"
    assert "b" not in w.community_builder.model_picker.selected_ids(), "a changed copy drops out"
    assert w.community_builder.namespace_note.text() == "a is confirmed in this project"
    w.sidebar.select("models", "b")
    assert not w.model_browser.check_growth_btn.isEnabled()
    assert "Changed since confirmed" in w.model_browser.namespace_label.text()


def test_user_choice_holds_until_the_selection_changes(window) -> None:
    w, _calls = window
    w.session.confirm_namespace("a")
    view = w.community_builder
    view.model_picker.set_selected(["a"])
    assert view.assume_bigg_check.isChecked()
    view.assume_bigg_check.click()  # the user unticks it
    w.refresh_workspace()
    assert not view.assume_bigg_check.isChecked()
    view.model_picker.set_selected(["a", "b"])
    view.model_picker.set_selected(["a"])
    assert view.assume_bigg_check.isChecked(), "a new selection recomputes the default"


def test_medium_editor_pretick(window) -> None:
    w, _calls = window
    w.session.confirm_namespace("a")
    editor = w.medium_editor
    editor.model_picker.set_selected(["a"])
    editor.single_model_picker.set_selected(["a"])
    assert editor.assume_bigg_check.isChecked()
    editor.model_picker.set_selected(["a", "b"])
    assert not editor.assume_bigg_check.isChecked()
    assert "b not confirmed" in editor.namespace_note.text()


def test_revoke_is_undoable(window) -> None:
    w, _calls = window
    w.sidebar.select("models", "a")
    w.model_browser.confirm_btn.click()
    w.model_browser.revoke_btn.click()
    assert not proj.namespace_confirmed(w.session.require().model("a"))
    w.session.undo_stack.undo()
    assert proj.namespace_confirmed(w.session.require().model("a"))
```

- [ ] **Step 5: 실패 확인**

Run: `uv run --no-sync pytest tests/test_phase2_check_growth.py -q`
Expected: FAIL — `run_check_growth` 없음.

- [ ] **Step 6: 창 구현**

`cmig/gui/editors.py`의 `MediumEditor.__init__`에서 `namespace_row`를 배치하는 줄 바로 다음에 다음을 더한다:
```python
        self.namespace_note = QLabel("")
        self.namespace_note.setWordWrap(True)
        layout.addWidget(self.namespace_note)  # 그 함수의 실제 레이아웃 변수 이름을 쓴다
```

`cmig/gui/app.py`:
1. 연결:
```python
        self.model_browser.confirm_requested.connect(self._confirm_namespace)
        self.model_browser.revoke_requested.connect(self._revoke_namespace)
        self.model_browser.check_growth_requested.connect(self.run_check_growth)
        self._namespace_user_set: dict[str, bool] = {"community": False, "medium": False}
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
```
2. 확인·해제:
```python
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
        self._refresh_browser(model_id)

    def _revoke_namespace(self, model_id: str) -> None:
        try:
            self.session.revoke_namespace(model_id)
        except ProjectError as exc:
            self.statusBar().showMessage(str(exc), 8000)
        self._refresh_browser(model_id)

    def _refresh_browser(self, model_id: str) -> None:
        project = self.session.project
        if project is None or self.model_browser.model_id() != model_id:
            return
        entry = project.model(model_id)
        self.model_browser.show_model(entry, self._load_index(entry),
                                      self._index_failures.get(entry.sha256, ""))
        self._show_latest_growth(entry)
```
(테스트는 `QMessageBox.question`을 바꿔치기하므로 이 호출을 그대로 쓴다.)
3. 확인란 기본값:
```python
    def _namespace_selection_changed(self, key: str) -> None:
        self._namespace_user_set[key] = False
        self._apply_namespace_defaults()

    def _apply_namespace_defaults(self) -> None:
        project = self.session.project
        targets = {
            "community": (self.community_builder.assume_bigg_check,
                          self.community_builder.namespace_note,
                          self.community_builder.model_picker.selected_ids()),
            "medium": (self.medium_editor.assume_bigg_check, self.medium_editor.namespace_note,
                       list(dict.fromkeys(self.medium_editor.model_picker.selected_ids()
                                          + self.medium_editor.single_model_picker
                                          .selected_ids()))),
        }
        for key, (check, note, ids) in targets.items():
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
            if not self._namespace_user_set.get(key, False):
                blocked = check.blockSignals(True)
                try:
                    check.setChecked(confirmed_all)
                finally:
                    check.blockSignals(blocked)
                if key == "medium":
                    self._medium_context_changed()
```
`refresh_workspace` 끝(`_refresh_pickers` 뒤)에서 `self._apply_namespace_defaults()`를 부른다. 확인란의 `toggled`가 다른 동작(예: Medium의 `_medium_context_changed`)에 연결되어 있으므로, 신호를 막은 경우 Medium만 위처럼 직접 부른다.
4. Check Growth 실행:
```python
    def run_check_growth(self, model_id: str | None = None) -> str:
        from cmig.cli.main import main
        from cmig.service import JobContext

        project = self.session.require()
        model_id = model_id or self.model_browser.model_id()
        if model_id is None:
            return ""
        entry = project.model(model_id)
        proj.refresh_integrity(project, entry)
        if not proj.namespace_confirmed(entry):
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
```
`_record_request`는 `analysis == "check_growth"`일 때 `self.model_browser`를 쓰도록 바꾼다:
```python
        page = self.model_browser if analysis == "check_growth" else self.analysis_pages[analysis]
```
`__init__`에 `self._check_growth_jobs: dict[str, tuple[Path, str, str]] = {}`.
5. 완료 처리(`_poll_completed_jobs`에 더한다):
```python
        for jid, (out_dir, model_id, sha) in list(self._check_growth_jobs.items()):
            job = self.runner.poll(jid)
            if job.status not in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
                continue
            self._check_growth_jobs.pop(jid, None)
            self.model_browser.check_growth_btn.setEnabled(True)
            text = self._growth_text(out_dir, model_id, job)
            if self.model_browser.model_id() == model_id:
                self.model_browser.set_growth(text)
            self.refresh_workspace()
```
```python
    def _growth_text(self, out_dir: Path, model_id: str, job: Job | None) -> str:
        from cmig.gui.growth import medium_text, read_growth, run_clock

        if job is not None and job.status is JobStatus.CANCELLED:
            return "⊘ Cancelled"
        if job is not None and job.status is JobStatus.FAILED:
            reason = (job.error or "the run failed").splitlines()[-1]
            hint = (" — tick “Skip medium metabolites this model lacks” to run without them"
                    if "no counterpart" in reason else "")
            return f"✗ Failed: {reason}{hint}"
        state = proj.read_run_state(out_dir)
        if state is not None:
            return {"cancelled": "⊘ Cancelled"}.get(state, f"✗ Failed ({state}) — see the run")
        if self._inspect_gui_run(out_dir) is None:
            return "✗ Failed: the result could not be read back — see the inspector"
        record, _problem = proj.read_run_request(out_dir)
        medium = medium_text(str((record or {}).get("values", {}).get("medium", "")))
        entry = self.session.require().model(model_id)
        reading = read_growth(out_dir, objective_warning=proj.objective_warning_of(entry),
                              medium=medium, finished=run_clock(out_dir.name))
        return f"{reading.symbol} {reading.text}"

    def _show_latest_growth(self, entry: ModelEntry) -> None:
        from cmig.gui.growth import latest_check_growth

        project = self.session.require()
        run_dir = latest_check_growth(project.root, entry.id, entry.sha256)
        if run_dir is not None:
            self.model_browser.set_growth(self._growth_text(run_dir, entry.id, None))
```
`_show_model` 끝에서 `self._show_latest_growth(entry)`를 부른다. `job.error`가 `RuntimeError` 메시지를 담는지 확인한다(JobRunner가 예외 문자열을 `error`에 넣는다). 담지 않으면 job의 실제 오류 필드를 쓴다.
6. RUNS 표시: `cmig/gui/project_session.py`의 `_summary_hint(inspected, run_dir)` 끝에서, 요약에 대상이 없을 때 `proj.read_run_request(run_dir)`의 `values["model"]`을 쓰게 한다(Check Growth 실행이 "Check Growth · iAF987 · 10:31"로 보인다). 테스트를 `tests/test_phase2_check_growth.py`에 더한다:
```python
def test_runs_label_names_the_model(window) -> None:
    w, _calls = window
    w.sidebar.select("models", "a")
    w.model_browser.confirm_btn.click()
    assert w.run_check_growth("a")
    _wait_text(w, "Growth 0.5")
    labels = [e.label for e in w.session.runs()]
    assert any(label.startswith("Check Growth · a · ") for label in labels)
```
7. RUNS에서 Check Growth 실행 열기: `_open_run_entry`에서 `key == "check_growth"`이면, 기록의 `values["model"]` 모델이 프로젝트에 있으면 `self.sidebar.select("models", model_id)` 후 `self.model_browser.set_growth(self._growth_text(run_dir, model_id, None))`와 `self._show_run_in_inspector(run_dir)`; 없으면 지금처럼 결과·상세 패널만 보인다.

- [ ] **Step 7: 통과 확인**

Run: `uv run --no-sync pytest tests/test_growth_reading.py tests/test_phase2_check_growth.py tests/test_phase2_model_browser.py tests/test_phase2_argv_parity.py -q && uv run --no-sync pytest tests/ -q -k "gui or workspace or app_shell or phase2 or medium" 2>&1 | tail -3`
Expected: 모두 통과. 기존 Community/Medium 테스트가 확인란 기본값 때문에 실패하면(예: 확인란이 꺼져 있다고 가정), 그 테스트의 모델이 확인되지 않은 상태인지 확인한다. 확인 기록이 없으면 기본값은 꺼짐이라 기존 동작과 같아야 한다.

- [ ] **Step 8: Commit**

```bash
git add cmig/gui tests
git commit -m "feat(gui): Check Growth from the model browser; per-model namespace confirmation

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 16: 전역 검색 (⌘F)

**Files:**
- Create: `cmig/gui/find.py`
- Modify: `cmig/gui/app.py` (검색 칸, Edit > Find…, 검색 표 만들기·갱신, 결과 열기)
- Create: `tests/test_find.py` (Qt 없음 부분), `tests/test_phase2_find_field.py`

**Interfaces:**
- Consumes: `model_index.search_rows`, `load_index`(Task 3), `_index_changed` 훅(Task 14), `_open_run_entry`(Task 13), `ModelBrowser.select`(Task 14)
- Produces (`cmig.gui.find`):
  - `GROUPS = (("model","Models"), ("reaction","Reactions"), ("metabolite","Metabolites"), ("gene","Genes"), ("medium","Media"), ("run","Runs"))`
  - `FindRow(kind, key, text, model=None)`, `FindGroup(kind, title, rows: tuple[FindRow, ...], more: int)` (frozen dataclass)
  - `SearchTable(models, entities, media, runs, indexing, unreadable)` — `entities: dict[(kind, id), (name, [model ids])]`
  - `build_table(models, rows_by_model, media, runs, *, indexing=0, unreadable=0) -> SearchTable`
  - `find(table, query, per_group=8) -> list[FindGroup]` — 2글자 미만은 `[]`; 순위 id 완전 일치 → 앞부분 → 그 밖 부분 일치(id·이름·배지 exchange·실행 표시); 같은 순위는 정렬 키 순
  - `footer_lines(table) -> list[str]` — `"2 models still indexing"`, `"1 model could not be searched"`
  - `FindField(QLineEdit)`: 신호 `activated(str, str, object)`(kind, key, model id 또는 None), `popup`(QListWidget), `FindField(source: Callable[[], SearchTable], host: QWidget)`
- Produces (창): `find_field`, `find_action`(Edit > Find…, `QKeySequence.StandardKey.Find`), `_search_table() -> SearchTable`, `_search_rows: dict[str, list[tuple[str, str, str]]]`(sha256 → 행), `_refresh_search_rows()`, `_find_activated(kind, key, model)`

- [ ] **Step 1: Qt 없는 테스트**

`tests/test_find.py`:
```python
from __future__ import annotations

from cmig.gui.find import FindRow, build_table, find, footer_lines

ROWS = {
    "a": [("metabolite", "glc__D_e", "D-Glucose"), ("reaction", "GLCpts", "glucose transport"),
          ("reaction", "EX_glc__D_e", "D-Glucose exchange"), ("gene", "b2417", "crr")],
    "b": [("metabolite", "glc__D_e", "D-Glucose"), ("reaction", "PGI", "isomerase")],
}


def _table(**kw):  # type: ignore[no-untyped-def]
    return build_table(
        [("a", "a.xml"), ("glc_model", "glc_model.xml")], ROWS,
        [("preset:western_diet", "western_diet", ["EX_glc__D_m", "EX_fru_m"])],
        [("/p/runs/search-1", "search-1", "Search · glc__D_e · 10:31 · ok")], **kw,
    )


def test_short_queries_find_nothing() -> None:
    assert find(_table(), "g") == []


def test_groups_in_order_with_rank() -> None:
    groups = find(_table(), "glc__d_e")
    assert [g.title for g in groups] == ["Metabolites", "Reactions", "Runs"]
    metabolites = groups[0]
    assert [r.text for r in metabolites.rows] == ["glc__D_e · a — D-Glucose",
                                                  "glc__D_e · b — D-Glucose"]
    assert metabolites.rows[0] == FindRow("metabolite", "glc__D_e",
                                          "glc__D_e · a — D-Glucose", "a")
    reactions = groups[1]
    assert reactions.rows[0].key == "EX_glc__D_e"


def test_exact_then_prefix_then_substring() -> None:
    rows = {"m": [("reaction", "GLC", ""), ("reaction", "GLCpts", ""),
                  ("reaction", "EX_GLC", "")]}
    groups = find(build_table([], rows, [], []), "glc")
    assert [r.key for r in groups[0].rows] == ["GLC", "GLCpts", "EX_GLC"]


def test_models_media_and_runs() -> None:
    groups = {g.kind: g for g in find(_table(), "glc")}
    assert [r.key for r in groups["model"].rows] == ["glc_model"]
    assert groups["medium"].rows[0].key == "preset:western_diet"  # found by its exchange id
    assert groups["run"].rows[0].key == "/p/runs/search-1"


def test_find_caps_rows_and_reports_more() -> None:
    rows = {f"m{i:03d}": [("metabolite", "ac_e", "Acetate")] for i in range(20)}
    (group,) = find(build_table([], rows, [], []), "ac_e")
    assert len(group.rows) == 8 and group.more == 12


def test_search_table_dedupes_across_models() -> None:
    shared = [("metabolite", f"m{i}", f"name {i}") for i in range(1000)]
    table = build_table([], {f"model{j}": shared for j in range(300)}, [], [])
    assert len(table.entities) == 1000
    assert len(table.entities[("metabolite", "m5")][1]) == 300


def test_footer() -> None:
    assert footer_lines(_table(indexing=2, unreadable=1)) == [
        "2 models still indexing", "1 model could not be searched",
    ]
    assert footer_lines(_table()) == []
```

- [ ] **Step 2: 실패 확인**

Run: `uv run --no-sync pytest tests/test_find.py -q`
Expected: FAIL — `cmig.gui.find` 없음.

- [ ] **Step 3: `cmig/gui/find.py`**

```python
"""Project search (⌘F): the search table, ranking, and the toolbar search field."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import QLineEdit, QListWidget, QListWidgetItem, QWidget

GROUPS = (("model", "Models"), ("reaction", "Reactions"), ("metabolite", "Metabolites"),
          ("gene", "Genes"), ("medium", "Media"), ("run", "Runs"))


@dataclass(frozen=True)
class FindRow:
    kind: str
    key: str
    text: str
    model: str | None = None


@dataclass(frozen=True)
class FindGroup:
    kind: str
    title: str
    rows: tuple[FindRow, ...]
    more: int


@dataclass
class SearchTable:
    models: list[tuple[str, str]] = field(default_factory=list)
    #: (kind, id) -> (name, ids of the models that have it): one entry, however many models
    entities: dict[tuple[str, str], tuple[str, list[str]]] = field(default_factory=dict)
    media: list[tuple[str, str, list[str]]] = field(default_factory=list)
    runs: list[tuple[str, str, str]] = field(default_factory=list)
    indexing: int = 0
    unreadable: int = 0


def build_table(
    models: list[tuple[str, str]],
    rows_by_model: dict[str, list[tuple[str, str, str]]],
    media: list[tuple[str, str, list[str]]],
    runs: list[tuple[str, str, str]],
    *,
    indexing: int = 0,
    unreadable: int = 0,
) -> SearchTable:
    table = SearchTable(models=list(models), media=list(media), runs=list(runs),
                        indexing=indexing, unreadable=unreadable)
    for model_id, rows in rows_by_model.items():
        for kind, key, name in rows:
            slot = table.entities.get((kind, key))
            if slot is None:
                table.entities[(kind, key)] = (name, [model_id])
            else:
                slot[1].append(model_id)
    return table


def _rank(query: str, key: str, *texts: str) -> int | None:
    lowered = key.lower()
    if lowered == query:
        return 0
    if lowered.startswith(query):
        return 1
    if query in lowered or any(query in text.lower() for text in texts):
        return 2
    return None


def find(table: SearchTable, query: str, per_group: int = 8) -> list[FindGroup]:
    q = query.strip().lower()
    if len(q) < 2:
        return []
    found: dict[str, list[tuple[int, str, FindRow]]] = {kind: [] for kind, _t in GROUPS}
    for model_id, file_name in table.models:
        rank = _rank(q, model_id, file_name)
        if rank is not None:
            found["model"].append(
                (rank, model_id, FindRow("model", model_id, f"{model_id} · {file_name}",
                                         model_id))
            )
    for (kind, key), (name, model_ids) in table.entities.items():
        rank = _rank(q, key, name)
        if rank is None or kind not in found:
            continue
        for model_id in model_ids:
            text = f"{key} · {model_id}" + (f" — {name}" if name else "")
            found[kind].append((rank, f"{key}\0{model_id}",
                                FindRow(kind, key, text, model_id)))
    for ref, label, exchanges in table.media:
        rank = _rank(q, label, *exchanges)
        if rank is not None:
            found["medium"].append((rank, label, FindRow("medium", ref, label)))
    for path, name, label in table.runs:
        rank = _rank(q, name, label)
        if rank is not None:
            found["run"].append((rank, name, FindRow("run", path, label)))
    groups: list[FindGroup] = []
    for kind, title in GROUPS:
        hits = sorted(found[kind], key=lambda hit: (hit[0], hit[1]))
        if hits:
            groups.append(FindGroup(kind, title, tuple(h[2] for h in hits[:per_group]),
                                    max(0, len(hits) - per_group)))
    return groups


def footer_lines(table: SearchTable) -> list[str]:
    lines = []
    if table.indexing:
        lines.append(f"{table.indexing} model{'' if table.indexing == 1 else 's'} "
                     "still indexing")
    if table.unreadable:
        lines.append(f"{table.unreadable} model{'' if table.unreadable == 1 else 's'} "
                     "could not be searched")
    return lines


class FindField(QLineEdit):
    """The toolbar search field and its result list (shown under it, inside the window)."""

    activated = Signal(str, str, object)

    def __init__(self, source: Callable[[], SearchTable], host: QWidget) -> None:
        super().__init__()
        self._source = source
        self._host = host
        self.setPlaceholderText("Search project")
        self.setClearButtonEnabled(True)
        self.setMaximumWidth(260)
        self.popup = QListWidget(host)
        self.popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.popup.setVisible(False)
        self.popup.itemClicked.connect(self._activate_item)
        self.textChanged.connect(self._refresh)
        self.installEventFilter(self)

    def _selectable(self) -> list[int]:
        return [i for i in range(self.popup.count())
                if self.popup.item(i).data(Qt.ItemDataRole.UserRole) is not None]

    def _refresh(self, text: str) -> None:
        self.popup.clear()
        table = self._source()
        groups = find(table, text)
        if not groups and len(text.strip()) < 2:
            self.popup.setVisible(False)
            return
        bold = QFont(self.popup.font())
        bold.setBold(True)
        for group in groups:
            header = QListWidgetItem(group.title)
            header.setFont(bold)
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            self.popup.addItem(header)
            for row in group.rows:
                item = QListWidgetItem("   " + row.text)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.popup.addItem(item)
            if group.more:
                more = QListWidgetItem(f"   +{group.more} more — refine the search")
                more.setFlags(Qt.ItemFlag.NoItemFlags)
                self.popup.addItem(more)
        if not groups:
            none = QListWidgetItem("No matches")
            none.setFlags(Qt.ItemFlag.NoItemFlags)
            self.popup.addItem(none)
        for line in footer_lines(table):
            note = QListWidgetItem(line)
            note.setFlags(Qt.ItemFlag.NoItemFlags)
            self.popup.addItem(note)
        selectable = self._selectable()
        if selectable:
            self.popup.setCurrentRow(selectable[0])
        corner = self.mapTo(self._host, QPoint(0, self.height()))
        width = max(self.width(), 420)
        x = min(corner.x(), max(0, self._host.width() - width))
        height = min(max(self.popup.sizeHintForRow(0), 18) * self.popup.count() + 6, 420)
        self.popup.setGeometry(x, corner.y(), width, height)
        self.popup.setVisible(True)
        self.popup.raise_()

    def _move(self, step: int) -> None:
        selectable = self._selectable()
        if not selectable:
            return
        current = self.popup.currentRow()
        later = [i for i in selectable if (i > current if step > 0 else i < current)]
        target = (later[0] if step > 0 else later[-1]) if later else current
        self.popup.setCurrentRow(target)

    def _activate_item(self, item: QListWidgetItem | None) -> None:
        row = None if item is None else item.data(Qt.ItemDataRole.UserRole)
        if isinstance(row, FindRow):
            self.popup.setVisible(False)
            self.activated.emit(row.kind, row.key, row.model)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt override
        if watched is self and event.type() == QEvent.Type.KeyPress and isinstance(
            event, QKeyEvent
        ):
            key = event.key()
            if key == Qt.Key.Key_Down and self.popup.isVisible():
                self._move(1)
                return True
            if key == Qt.Key.Key_Up and self.popup.isVisible():
                self._move(-1)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.popup.isVisible():
                self._activate_item(self.popup.currentItem())
                return True
            if key == Qt.Key.Key_Escape:
                if self.popup.isVisible():
                    self.popup.setVisible(False)
                else:
                    self.clear()
                return True
        return super().eventFilter(watched, event)
```

- [ ] **Step 4: GUI 테스트**

`tests/test_phase2_find_field.py`:
```python
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown, textbook_sbml  # noqa: E402,F401
from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtGui import QKeySequence  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402
from cmig.io import project as proj  # noqa: E402

APP = QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path: Path):
    project = proj.create_project(tmp_path / "p")
    proj.add_model_file(project, textbook_sbml(tmp_path / "src" / "e_coli_core.xml"))
    proj.save_project(project)
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(project.root)
    w.show()
    deadline = time.time() + 20
    while not w._search_rows and time.time() < deadline:
        APP.processEvents()
        time.sleep(0.05)
        w._poll_completed_jobs()
    yield w
    w.close_project()


def test_cmd_f_focuses_the_field(window) -> None:
    window.find_action.trigger()
    APP.processEvents()
    assert window.find_field.hasFocus()
    assert window.find_action.shortcut() == QKeySequence(QKeySequence.StandardKey.Find)


def test_typing_lists_groups_and_return_opens_the_item(window) -> None:
    field = window.find_field
    field.setFocus()
    QTest.keyClicks(field, "pgi")
    assert field.popup.isVisible()
    texts = [field.popup.item(i).text() for i in range(field.popup.count())]
    assert "Reactions" in texts
    assert any("PGI · e_coli_core" in t for t in texts)
    QTest.keyClick(field, Qt.Key.Key_Return)
    APP.processEvents()
    assert window.pages.currentWidget() is window.model_browser
    assert window.model_browser.reactions_tab.current_id() == "PGI"


def test_escape_closes_then_clears(window) -> None:
    field = window.find_field
    field.setFocus()
    QTest.keyClicks(field, "glc")
    QTest.keyClick(field, Qt.Key.Key_Escape)
    assert not field.popup.isVisible() and field.text() == "glc"
    QTest.keyClick(field, Qt.Key.Key_Escape)
    assert field.text() == ""


def test_media_are_found(window) -> None:
    field = window.find_field
    QTest.keyClicks(field, "western")
    texts = [field.popup.item(i).text() for i in range(field.popup.count())]
    assert "Media" in texts
    assert any(t.strip() == "western_diet" for t in texts)
```

- [ ] **Step 5: 창 연결**

`cmig/gui/app.py`:
1. `__init__`: `self._search_rows: dict[str, list[tuple[str, str, str]]] = {}`, `self._search_unreadable: set[str] = set()`, `self._search_rows_job: str | None = None`, `self.find_field = FindField(self._search_table, self)`, `self.find_field.activated.connect(self._find_activated)`.
2. 툴바: 오른쪽 spacer 다음, Inspector 토글 앞에 `toolbar.addWidget(self.find_field)`.
3. Edit 메뉴에 Find…:
```python
        self.find_action = self._action("Find…", self._focus_find, QKeySequence.StandardKey.Find)
        edit_menu.addSeparator()
        edit_menu.addAction(self.find_action)
```
```python
    def _focus_find(self) -> None:
        self.find_field.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.find_field.selectAll()
```
4. 검색 행 불러오기(활동 창에 넣지 않는 조회 작업):
```python
    def _refresh_search_rows(self) -> None:
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

        self._search_rows_job = self.runner.submit("search_rows", _job)

    def _finish_search_rows_job(self) -> None:
        jid = self._search_rows_job
        if jid is None:
            return
        job = self.runner.poll(jid)
        if job.status not in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
            return
        self._search_rows_job = None
        project = self.session.project
        result = job.result if isinstance(job.result, dict) else {}
        if project is not None and result.get("root") == str(project.root):
            self._search_rows.update(result.get("rows", {}))
            self._search_unreadable.update(result.get("bad", []))
        self.runner.release_payload(jid)
        self._refresh_search_rows()  # an index built meanwhile

    def _search_table(self) -> SearchTable:
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
```
`__init__`에 `self._medium_exchange_cache: dict[str, list[str]] = {}`. 프로젝트를 바꾸면(`refresh_workspace`의 `switched`) `_search_rows`, `_search_unreadable`, `_medium_exchange_cache`를 비우고 `_refresh_search_rows()`를 부른다. Task 14의 `_index_changed`가 `self._refresh_search_rows()`를 부르게 한다. `_poll_completed_jobs`에 `self._finish_search_rows_job()`을 더한다. 활동 창 작업 이름표에 `"search_rows"`를 넣지 않는다(목록에 보이지 않는 조회).
5. 결과 열기:
```python
    def _find_activated(self, kind: str, key: str, model: object) -> None:
        project = self.session.project
        if project is None:
            return
        if kind == "run":
            self._open_run_entry(Path(key))
        elif kind == "medium":
            self.sidebar.select("media", key)
        else:
            model_id = key if kind == "model" else str(model)
            self.sidebar.select("models", model_id)
            if self.model_browser.model_id() != model_id or (
                self.pages.currentWidget() is not self.model_browser
            ):
                self._show_model(project.model(model_id))
            if kind != "model":
                self.model_browser.select(kind, key)
```

- [ ] **Step 6: 통과 확인**

Run: `uv run --no-sync pytest tests/test_find.py tests/test_phase2_find_field.py -q && uv run --no-sync pytest tests/ -q -k "gui or workspace or app_shell or phase2" 2>&1 | tail -3`
Expected: 모두 통과. (offscreen에서 포커스가 잡히지 않으면 테스트에서 `window.activateWindow()`를 먼저 부른다.)

- [ ] **Step 7: Commit**

```bash
git add cmig/gui/find.py cmig/gui/app.py tests/test_find.py tests/test_phase2_find_field.py
git commit -m "feat(gui): project search (⌘F) over models, contents, media and runs

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 17: 결과 표시 — 상태 표시줄의 마지막 실행, 계산값 강조, flux 범례

**Files:**
- Modify: `cmig/gui/analysis_page.py` (`mark_computed_headers`, `paint_computed`, `is_failed_status`, `FLUX_LEGEND`)
- Modify: `cmig/gui/search_results.py`, `cmig/gui/host_view.py`, `cmig/gui/views.py`(`ExternalProfileView`, `DynamicsResults`), `cmig/gui/builder.py`(`DeltaTable`)
- Modify: `cmig/gui/app.py` (`last_run_button`, `_settle_run_jobs`가 끝난 실행을 모음, `_show_last_run`)
- Create: `tests/test_phase2_results_display.py`

**Interfaces:**
- Produces (`cmig.gui.analysis_page`):
  - `COMPUTED_TIP = "Computed by CMIG"`, `FLUX_LEGEND = "+ secretion / − uptake (mmol gDW⁻¹ h⁻¹)"`
  - `is_failed_status(text: str) -> bool` — "failed", "error", "infeasible", "cancel", "non-viable", "non_viable", "timeout", "unknown", "unreadable" 중 하나를 (대소문자 무시) 포함하면 참
  - `mark_computed_headers(table, columns: Iterable[int]) -> None` — 머리글 도움말에 `COMPUTED_TIP`를 더함(기존 도움말이 있으면 줄을 바꿔 덧붙임)
  - `paint_computed(table, columns, *, status_column: int | None = None) -> None` — 강조색(`QPalette.ColorRole.Accent`)으로 칠한다. 칠하지 않는 것: 이미 글자색이 정해진 칸, 값이 아닌 칸(빈칸, "—", "unknown…", "not recorded…"), `status_column`의 글자가 `is_failed_status`인 행
- Produces (창): `last_run_button`(QToolButton, 상태 표시줄 왼쪽), `_show_last_run(run_dir: Path, error: str = "") -> None`

계산값 열:
| 표 | 열 |
|---|---|
| `SearchResultsPanel.table` | 2, 3, 4, 5 (status 열 6) |
| `HostImpactView.iface_table` | 2 |
| `HostImpactView.cross_table` | 1 |
| `ExternalProfileView.table` | 1, 3 |
| `DynamicsResults.table` | 2, 3 (status 열 1) |
| `DeltaTable` | 1, 2, 3 |

범례(`FLUX_LEGEND` 라벨)는 `ExternalProfileView.table`과 `HostImpactView.iface_table` 바로 위에 둔다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_phase2_results_display.py`:
```python
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401
from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtGui import QColor, QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QTableWidget  # noqa: E402

from cmig.gui.analysis_page import (  # noqa: E402
    FLUX_LEGEND,
    is_failed_status,
    mark_computed_headers,
    paint_computed,
)
from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.builder import read_only_item  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402

APP = QApplication.instance() or QApplication([])


def _accent() -> QColor:
    return QApplication.palette().color(QPalette.ColorRole.Accent)


def _fg(table: QTableWidget, row: int, col: int):  # type: ignore[no-untyped-def]
    return table.item(row, col).data(Qt.ItemDataRole.ForegroundRole)


def test_paint_computed_rules() -> None:
    table = QTableWidget(3, 3)
    table.setHorizontalHeaderLabels(["Name", "Flux", "Status"])
    rows = [("a", "1.5", "optimal"), ("b", "—", "optimal"), ("c", "2.0", "failed")]
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            table.setItem(r, c, read_only_item(text))
    fixed = read_only_item("9.9")
    fixed.setForeground(QColor("#d62728"))
    table.setItem(0, 0, fixed)
    mark_computed_headers(table, [1])
    paint_computed(table, [0, 1], status_column=2)
    assert _fg(table, 0, 1).color() == _accent()
    assert _fg(table, 0, 0).color() == QColor("#d62728"), "an explicit colour is kept"
    assert _fg(table, 1, 1) is None, "a missing value is not painted as a value"
    assert _fg(table, 2, 1) is None, "a failed row is never painted"
    assert "Computed by CMIG" in table.horizontalHeaderItem(1).toolTip()


@pytest.mark.parametrize(("text", "failed"), [("failed", True), ("Infeasible", True),
                                              ("non-viable", True), ("optimal", False),
                                              ("ok", False), ("timeout", True)])
def test_is_failed_status(text: str, failed: bool) -> None:
    assert is_failed_status(text) is failed


def test_search_results_paint_computed_columns() -> None:
    w = build_main_window()
    panel = w.search_view.results_panel
    panel.load_summary({"status": "ok", "strategy": "exhaustive", "target": "but",
                        "top_ranked": [{"members": ["a"], "score": 1.0, "target_flux": 2.0,
                                        "community_growth": 0.4, "status": "optimal"}]})
    assert _fg(panel.table, 0, 2).color() == _accent()
    assert _fg(panel.table, 0, 0) is None
    assert "Computed by CMIG" in panel.table.horizontalHeaderItem(3).toolTip()


def test_flux_legend_next_to_flux_tables() -> None:
    w = build_main_window()
    for widget in (w.profile_view, w.host_view):
        labels = [label.text() for label in widget.findChildren(QLabel)]
        assert FLUX_LEGEND in labels


def test_status_bar_names_the_last_finished_run(tmp_path: Path, monkeypatch) -> None:
    make_project(tmp_path / "p", ["a", "b"])
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(tmp_path / "p")
    try:
        monkeypatch.setattr("cmig.cli.main.main", lambda argv: 2)
        w.strain_growth_page.model_picker.set_selected(["a"])
        assert w.run_strain_growth_report()
        deadline = time.time() + 10
        while not w.last_run_button.text() and time.time() < deadline:
            APP.processEvents()
            time.sleep(0.02)
            w._poll_completed_jobs()
        text = w.last_run_button.text()
        assert text.startswith("✗ Strain Growth · strain-growth-")
        assert "rc=2" in text
        w.show_analysis("search")
        w.last_run_button.click()
        assert w.pages.currentWidget() is w.strain_growth_page
    finally:
        w.close_project()
```

- [ ] **Step 2: 실패 확인**

Run: `uv run --no-sync pytest tests/test_phase2_results_display.py -q`
Expected: FAIL — `FLUX_LEGEND` import 실패.

- [ ] **Step 3: 도우미**

`cmig/gui/analysis_page.py`에 더한다:
```python
COMPUTED_TIP = "Computed by CMIG"
FLUX_LEGEND = "+ secretion / − uptake (mmol gDW⁻¹ h⁻¹)"
_FAILED_WORDS = ("failed", "error", "infeasible", "cancel", "non-viable", "non_viable",
                 "timeout", "unknown", "unreadable")
_NOT_VALUES = ("—", "unknown", "not recorded")


def is_failed_status(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in _FAILED_WORDS)


def mark_computed_headers(table: QTableWidget, columns: Iterable[int]) -> None:
    for column in columns:
        item = table.horizontalHeaderItem(column)
        if item is None:
            continue
        tip = item.toolTip()
        if COMPUTED_TIP not in tip:
            item.setToolTip(f"{tip}\n{COMPUTED_TIP}" if tip else COMPUTED_TIP)


def paint_computed(
    table: QTableWidget, columns: Iterable[int], *, status_column: int | None = None
) -> None:
    """Show computed values in the system accent colour; inputs keep the default colour.

    A cell that already has its own colour (a diagnostic, a significance mark) keeps it; a
    missing value and every cell of a failed or unevaluated row are never painted as values.
    """
    accent = QApplication.palette().color(QPalette.ColorRole.Accent)
    wanted = list(columns)
    for row in range(table.rowCount()):
        if status_column is not None:
            status = table.item(row, status_column)
            if status is not None and is_failed_status(status.text()):
                continue
        for column in wanted:
            item = table.item(row, column)
            if item is None or item.data(Qt.ItemDataRole.ForegroundRole) is not None:
                continue
            text = item.text().strip()
            if not text or text.startswith(_NOT_VALUES):
                continue
            item.setForeground(accent)
```
(`Iterable`은 `collections.abc`에서, `QApplication`은 `PySide6.QtWidgets`에서, `QPalette`는 `PySide6.QtGui`에서 import한다.)

- [ ] **Step 4: 표에 적용**

- `SearchResultsPanel.__init__`: `mark_computed_headers(self.table, [2, 3, 4, 5])`. `load_summary`에서 `setHorizontalHeaderLabels`를 다시 부르면 도움말이 사라지므로 그 뒤에 `mark_computed_headers(self.table, [2, 3, 4, 5])`를 다시 부른다. 행을 다 채운 뒤 `paint_computed(self.table, [2, 3, 4, 5], status_column=6)`.
- `HostImpactView`: 머리글을 정한 뒤 `mark_computed_headers(self.iface_table, [2])`, `mark_computed_headers(self.cross_table, [1])`. `load_host_result` 끝에 `paint_computed(self.iface_table, [2])`, `load_impact` 끝에 `paint_computed(self.cross_table, [1])`. `iface_table` 바로 위에 `QLabel(FLUX_LEGEND)`를 넣는다.
- `ExternalProfileView`: `mark_computed_headers(self.table, [1, 3])`, `load_profile` 끝에 `paint_computed(self.table, [1, 3])`, `self.table` 바로 위에 `QLabel(FLUX_LEGEND)`.
- `DynamicsResults`: `_build_dynamics_results`에서 `mark_computed_headers(self.table, [2, 3])`, `_set_single_row` 끝에 `paint_computed(self.table, [2, 3], status_column=1)`.
- `DeltaTable`: `__init__`에서 `mark_computed_headers(self, [1, 2, 3])`, `load_delta` 끝에 `paint_computed(self, [1, 2, 3])`(유의 행의 빨강은 이미 정해진 색이라 유지된다).

- [ ] **Step 5: 상태 표시줄의 마지막 실행**

`cmig/gui/app.py`:
1. `__init__`(상태 표시줄을 만든 곳):
```python
        self.last_run_button = QToolButton()
        self.last_run_button.setAutoRaise(True)
        self.last_run_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.last_run_button.clicked.connect(self._open_last_run)
        self.statusBar().addWidget(self.last_run_button)
        self._last_run_dir: Path | None = None
        #: run folders whose job ended since the last poll: (folder, error text)
        self._just_finished: list[tuple[Path, str]] = []
```
2. `_settle_run_jobs`에서 끝난 job마다(DONE 포함, `del self._job_runs[job_id]` 다음) `self._just_finished.append((run_dir, "" if job.status is JobStatus.DONE else (job.error or "")))`를 더한다(DONE의 `continue`보다 앞에).
3. `_poll_completed_jobs` 맨 끝에:
```python
        if self._just_finished:
            run_dir, error = self._just_finished[-1]
            self._just_finished.clear()
            self._show_last_run(run_dir, error)
```
(각 종류의 완료 처리가 판독 실패를 기록한 뒤에 부르기 위해 끝에 둔다.)
4. 메서드:
```python
    _STATUS_SYMBOLS = {"ok": "✓", "degraded": "⚠", "warning": "⚠", "cancelled": "⊘"}

    def _show_last_run(self, run_dir: Path, error: str = "") -> None:
        from cmig.gui.inspector import _solver_label
        from cmig.gui.run_restore import analysis_for_run

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
        if symbol == "✗":
            reason = error.strip().splitlines()[0] if error.strip() else entry.status
            parts.append(reason)
        self.last_run_button.setText(" · ".join(parts))
        self.last_run_button.setToolTip(str(entry.path))
        self._last_run_dir = entry.path

    def _open_last_run(self) -> None:
        if self._last_run_dir is not None:
            self._open_run_entry(self._last_run_dir)
```
`ANALYSES` import(사이드바)가 이미 있다. `_solver_label`은 inspector의 모듈 함수다. 실패 이유 첫 줄은 job 오류 문구(예: `strain growth failed with rc=2`)다.

- [ ] **Step 6: 통과 확인**

Run: `uv run --no-sync pytest tests/test_phase2_results_display.py -q && uv run --no-sync pytest tests/ -q -k "gui or workspace or app_shell or phase2 or round7 or round8" 2>&1 | tail -3`
Expected: 모두 통과. 글자색을 확인하던 기존 테스트(예: 진단 행 색)가 실패하면, 이미 정해진 색은 유지되는지 확인한다.

- [ ] **Step 7: Commit**

```bash
git add cmig/gui tests/test_phase2_results_display.py
git commit -m "feat(gui): last run in the status bar; computed values in the accent colour

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 18: 1단계 보류 항목 — 실행 기록 해시와 AGORA2 카탈로그 조회를 화면 스레드 밖으로

**Files:**
- Modify: `cmig/gui/app.py` (`_run_off_thread`, `_inspect_gui_run`, `_show_run_in_inspector`, `_ThreadStderrRouter` 일반화, `_agora2_list`)
- Create: `tests/test_phase2_off_thread.py`

**Interfaces:**
- Produces: `CmigMainWindow._run_off_thread(fn: Callable[..., T], *args) -> T` — 작업 스레드에서 `fn(*args)`를 실행하고, 끝날 때까지 작은 이벤트 루프로 화면을 살려 둔다. 예외는 그대로 다시 낸다.
- Produces: `_install_stdout_router()`, `_captured_thread_stdout() -> Iterator[list[str]]` — `_ThreadStderrRouter`와 같은 방식으로 *지금 스레드*가 stdout에 쓴 것만 모은다.
- 행동: `_inspect_run_dir`는 크기와 상관없이 항상 작업 스레드에서 돈다. `agora2-list` CLI 호출도 작업 스레드에서 돈다(CLI를 그대로 부르는 방식은 유지).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_phase2_off_thread.py`:
```python
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402

APP = QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path: Path):
    make_project(tmp_path / "p", ["a"])
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(tmp_path / "p")
    yield w
    w.close_project()


def test_run_inspection_never_runs_on_the_gui_thread(window, monkeypatch) -> None:
    seen: list[bool] = []

    def fake_inspect(run_dir):  # type: ignore[no-untyped-def]
        seen.append(threading.current_thread() is threading.main_thread())
        return {"artifact_integrity": "verified", "kind": "search", "status": "ok"}

    monkeypatch.setattr("cmig.cli.main._inspect_run_dir", fake_inspect)
    run_dir = window.session.require().runs_dir / "search-20261014-101010"
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text(json.dumps({}))
    window._inspect_gui_run(run_dir)
    assert seen and not any(seen)


def test_agora2_list_runs_the_cli_off_the_gui_thread(window, monkeypatch) -> None:
    seen: list[bool] = []

    def fake_main(argv):  # type: ignore[no-untyped-def]
        seen.append(threading.current_thread() is threading.main_thread())
        print(json.dumps({"models": [{"id": "Roseburia_x", "published_size": "1M"}]}))
        return 0

    monkeypatch.setattr("cmig.cli.main.main", fake_main)
    found = window._agora2_list("Roseburia")
    assert [str(s) for s in found] == ["Roseburia_x"]
    assert seen == [False]


def test_off_thread_errors_propagate(window) -> None:
    def boom() -> None:
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        window._run_off_thread(boom)
```

- [ ] **Step 2: 실패 확인**

Run: `uv run --no-sync pytest tests/test_phase2_off_thread.py -q`
Expected: FAIL — `_run_off_thread` 없음, 작은 실행은 GUI 스레드에서 검사됨.

- [ ] **Step 3: 구현**

1. `_run_off_thread`:
```python
    def _run_off_thread(self, fn: Callable[..., T], *args: Any) -> T:
        """Run `fn` on a worker thread; keep the window responsive until it is done."""
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(fn, *args)
            loop = QEventLoop(self)
            timer = QTimer(self)
            timer.setInterval(20)
            timer.timeout.connect(lambda: loop.quit() if future.done() else None)
            timer.start()
            while not future.done():
                loop.exec()
            timer.stop()
            return future.result()
```
(`T = TypeVar("T")`를 모듈에 둔다.)
2. `_inspect_gui_run`의 `large` 계산과 두 갈래를 `inspected = self._run_off_thread(_inspect_run_dir, run_dir)` 한 줄로 바꾼다. `_show_run_in_inspector`의 `_inspect_run_dir(run_dir)` 호출도 `self._run_off_thread(_inspect_run_dir, run_dir)`로 바꾼다. 둘 다 `from cmig.cli.main import _inspect_run_dir`를 함수 안에서 그대로 import한다(테스트가 그 이름을 바꿔치기한다).
3. `_ThreadStderrRouter`는 어떤 스트림에도 쓸 수 있다. stdout용 설치·수집 함수를 더한다:
```python
def _install_stdout_router() -> None:
    """Install the pass-through router on stdout (GUI thread only; idempotent)."""
    if not isinstance(sys.stdout, _ThreadStderrRouter):
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
```
4. `_agora2_list`에서 `redirect_stdout`를 쓰던 부분을 바꾼다(검증·argv는 그대로):
```python
        _install_stderr_router()
        _install_stdout_router()

        def _call() -> tuple[int, str, str]:
            with _captured_thread_stdout() as out, _captured_job_stderr() as err:
                try:
                    rc = main(argv)
                except SystemExit as exc:  # argparse rejected the query
                    rc = exc.code if isinstance(exc.code, int) else 2
            return rc, "".join(out), "".join(err)

        rc, printed, errors = self._run_off_thread(_call)
        if rc != 0:
            lines = errors.strip().splitlines()
            raise RuntimeError(lines[-1].strip() if lines else f"agora2-list exited {rc}")
        return _parse_catalogue(printed)
```
docstring의 "Runs on the GUI thread …" 문장을 "Runs the CLI on a worker thread; only that thread's stdout is captured."로 바꾼다. `contextlib`/`io` import가 쓰이지 않게 되면 지운다. `main`은 함수 안에서 `from cmig.cli.main import main`으로 import한 이름을 쓴다(테스트가 `cmig.cli.main.main`을 바꿔치기하므로 호출 시점에 모듈 속성을 읽도록 `import cmig.cli.main as cli_main`, `cli_main.main(argv)`로 부른다).

- [ ] **Step 4: 통과 확인**

Run: `uv run --no-sync pytest tests/test_phase2_off_thread.py tests/test_workspace_agora2.py tests/test_workspace_activity_flow.py -q && uv run --no-sync pytest tests/ -q -k "gui or workspace or app_shell or phase2" 2>&1 | tail -3`
Expected: 모두 통과.

- [ ] **Step 5: Commit**

```bash
git add cmig/gui/app.py tests/test_phase2_off_thread.py
git commit -m "fix(gui): run readback hashing and the AGORA2 lookup off the GUI thread

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 19: 문서, 화면 확인(offscreen·REA, 밝은/어두운 모드), 전체 검증

**Files:**
- Modify: `docs/USER_GUIDE.md`(Desktop GUI 절), `CHANGELOG.md`, `docs/tracking/status.md`, `docs/tracking/findings.md`, `cmig/gui/AGENTS.md`, `cmig/io/AGENTS.md`
- Create (git에 넣지 않음): 화면 캡처 스크립트와 결과 — scratchpad

- [ ] **Step 1: 문서**

- `docs/USER_GUIDE.md` Desktop GUI 절: 사이드바 네 묶음(13개 화면), 공통 화면 구조(입력 카드·Advanced·결과), RUNS에서 열면 입력이 돌아온다는 것, 모델 브라우저·Check Growth·namespace 확인, ⌘F 검색, 상태 표시줄의 마지막 실행, 계산값 강조. Check Growth는 `cmig single --fba`를 부르며, 배지를 고르면 exact로 적용되고, 목적함수가 성장이 아니면 "Objective value"로 보인다는 것을 적는다.
- `CHANGELOG.md` Unreleased에 2단계 변경을 적는다. CLI·`run_hash`·manifest·tidy 스키마는 바뀌지 않았다고 명시한다.
- `docs/tracking/status.md`: 남은 작업 1(GUI 2단계)을 완료로 옮기고 검증 증거(전체 테스트 요약 줄, golden 결과)를 적는다. 3단계가 다음 항목이다.
- `docs/tracking/findings.md`에 다음을 더한다:
  - "AXPress(접근성 '누름')로 사이드바 QTreeWidget 항목이 선택되지 않음 — REA 자동 조작에서 확인(2026-10-13). 마우스·키보드는 정상. Qt 항목 뷰의 접근성 동작이라 이번 범위에서 고치지 않음."
- `cmig/gui/AGENTS.md`:
  - 화면 키 13개와 `AnalysisPage` 규칙(새 화면은 틀을 쓰고 입력을 `register`한다)
  - `tests/argv_drivers.py`의 `EXPECTED`는 고치지 않는다는 규칙
  - 공동체 결과 위젯은 `_show_profile(host_key)`로 화면을 옮겨 다닌다
  - 색인은 보기·검색용 캐시다
- `cmig/io/AGENTS.md`: `model_index.py`(분석 입력이 아님), `project.py`의 새 필드·함수(namespace 확인, 실행 입력 기록, 설정 키 이전).

- [ ] **Step 2: offscreen 화면 캡처**

scratchpad에 스크립트를 만들어 1280×800과 1500×950에서 다음을 PNG로 캡처한다:
- 13개 분석 화면(결과 없음 상태)
- Advanced를 펼친 Combination Search
- 실행 기록을 연 화면 하나(배너 포함)
- 모델 표, 모델 브라우저(textbook), 검색 결과 목록이 열린 상태, 선택 없음 상세 패널

잘림·겹침·빈 공간을 눈으로 확인하고, 문제가 있으면 고친 뒤 다시 캡처한다. 고친 것은 별도 커밋으로 남긴다.

- [ ] **Step 3: REA로 실제 창 확인 (밝은 모드와 어두운 모드)**

memory `gui-workspace-phase1.md`의 REA 절차를 따른다:
1. CMIG를 작은 `.app` 묶음으로 띄운다. QSettings는 scratchpad의 ini를 쓰게 하고, 프로젝트도 scratchpad에 만든다.
2. 실제 python 경로, `--pid`, `--window-id`로 `observe-native-ui`를 실행한다.
3. 화면 이동은 접근성 '누름'으로 안 되므로, 실행 스크립트가 읽는 명령 파일로 사이드바를 선택한다.

캡처 대상은 Combination Search, Community Solve, Host–Microbe, 모델 브라우저, 검색 결과 목록이다. 시스템 모양을 어두운 모드와 밝은 모드로 바꿔 각각 캡처한다. 시스템 설정을 바꾸기 전에 사용자에게 묻는다. 묻기 어려우면 `QApplication.setPalette`로 밝은 팔레트를 강제한 캡처로 대신하고, 그렇게 했다고 보고한다.

계산값 강조색과 범례가 두 모드 모두에서 읽히는지 확인한다.

- [ ] **Step 4: 전체 검증**

```bash
uv run --no-sync python scripts/harness_checks.py --tier quality
uv run --no-sync pytest -q 2>&1 | tail -5
uv run --no-sync cmig golden verify
uv run --no-sync cmig golden verify-envelope
```
Expected:
- quality 통과
- pytest 마지막 요약 줄에 failed 0. 종료 코드 139는 기존 macOS 종료 문제이고, 요약 줄로 판정한다.
- golden과 envelope는 바뀌지 않는다.

harness 검사가 시간 초과로 실패하면 세 harness 테스트 파일을 따로 실행해 확인한다(memory 참고).

- [ ] **Step 5: Commit**

```bash
git add docs CHANGELOG.md cmig/gui/AGENTS.md cmig/io/AGENTS.md
git commit -m "docs: GUI workspace phase 2 (pages, model browser, search, run restore)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

- [ ] **Step 6: 사용자 확인 요청**

실제 macOS 화면에서 다음 흐름을 확인해 달라고 요청한다:
- 모델 추가 → 브라우저 → Confirm → Check Growth
- Combination Search 실행 → RUNS에서 다시 열기
- ⌘F 검색
- Community Solve abundance 편집

---

## 계획에서 정한 것 (설계 문서에 없던 세부)

1. **Cancel 단추**: 화면 안의 Cancel은 지금처럼 Combination Search에만 둔다. 다른 분석은 작업 창(Activity)의 Cancel로 취소한다. 지금 동작과 같고, 실행 중 단추가 꺼지는 규칙도 그대로다.
2. **Gene Knockout 조합 기본값**: 조합 선택기는 아무것도 고르지 않은 채 시작한다. 모델 선택기가 처음 목록을 모두 체크하는 동작을 조합에는 쓰지 않는다. 조합을 가정하지 않기 위해서다.
3. **Constraint Sandbox**: CLI argv 없이 `EngineService`를 부르므로 argv 동일성 테스트에서 빠지고, 실행 기록도 남기지 않는다(`runs/`에 쓰지 않음).
4. **실행 폴더 이름만으로 화면 찾기**: 실행 기록과 manifest가 모두 없으면 폴더 이름 앞부분으로 화면을 고른다. 기록이 깨진 실행도 그 화면이 열리게 하기 위해서다.
5. **상태 표시줄의 솔버 문구**: 상세 패널과 같은 `_solver_label` 문구를 쓴다("Gurobi full-flux"). Check Growth 머리글은 설계 문서대로 "Gurobi (full-flux)"다.
6. **가짜 모델 테스트**: `make_project`가 빈 색인을 기본으로 쓴다. 기존 GUI 테스트가 색인 작업 실패 때문에 흔들리지 않게 하기 위해서다.
7. **검색 행 불러오기**: 색인 파일을 읽어 검색 행을 만드는 일은 작업 창에 보이지 않는 조회 작업으로 돌린다. 모델 색인을 만드는 작업("Index Models")만 작업 창에 보인다.
8. **확인란 문구**: 고른 모델이 하나이고 확인되어 있으면 "<id> is confirmed in this project"라고 적는다.
