<!--
Feature: cmig-baseline-hardening
Phase: Design
Created: 2026-06-01
Architecture: Option C — Pragmatic (verification + localized fixes on existing 4-seam headless core)
Plan: docs/01-plan/features/cmig-baseline-hardening.plan.md
-->

# cmig-baseline-hardening Design Document

## Context Anchor

| 축 | 내용 |
|----|------|
| **WHY** | 98.25%가 가린 3대 정직성 격차(미실행 GUI·미증명 통합·미검토 모듈)를 닫아, 지표가 아니라 동작으로 baseline을 신뢰 가능하게 만든다. |
| **WHO** | community 대사 모델링 연구자 + CMIG 유지보수자. |
| **RISK** | offscreen ≠ 시각 QA(명시 경계); 적대적 리뷰 신규 Critical 발굴 시 범위 확대; PySide6 헤드리스 설치 이슈; FVA 비용. |
| **SUCCESS** | SC-H1..H6 (Plan §4). GUI offscreen 실행·산출 검증 / E2E 1-pass / 미검토 모듈 0 Critical 잔존 / 과학영향 Minor 해소 / FVA 실채움. |
| **SCOPE** | baseline(MVP-0~2) 하드닝. PART II out-of-scope. |

## 1. Overview

검증·보강 사이클. 신규 아키텍처 없음 — 기존 `cmig/`(4-seam headless core + EngineService facade + RenderClient)를 **그대로 두고**, 그 위에 (1) 실행 증거 테스트, (2) 통합 테스트, (3) 적대적 리뷰, (4) 국소 수정 + FVA 1급 모듈을 올린다. 변경의 90%는 `tests/`·`fixtures/`이며, 코드 변경은 파일 단위 국소 + 신규 `core/fva.py` 하나.

### 1.1 Architecture (Option C — Pragmatic)
```
cmig/core/fva.py            ← 신규 1급 모듈 (cobra FVA 위임, MICOM-위임 철학 일관)
cmig/core/sign.py           ← eps noise floor 1e-6 정합 (in-place)
cmig/core/metrics.py        ← sign 단일진입점 경유 (in-place)
cmig/core/engine.py         ← status 전파 완성 + FVA 호출 hook (in-place)
cmig/core/namespace.py      ← coverage 분모 정의 명시 (in-place)
cmig/core/tidy.py           ← edge_type/label 분리 + fva_lo/hi 소비 (in-place)
cmig/core/manifest.py       ← flux_report_status 모델링 (in-place)
tests/test_gui_render.py    ← Track A: offscreen 렌더 유틸리티 + 검증
tests/test_e2e_pipeline.py  ← Track B: 전 파이프라인 통합 1-pass
tests/test_fva.py           ← Track D: FVA 실값 검증
tests/test_robustness.py    ← Track D: 2nd golden·infeasible·edge-media
tests/test_review_regressions.py ← Track C: 적대 리뷰 발굴분 회귀
fixtures/community_5_member/ ← Track D: 2nd golden (다른 크기/namespace)
fixtures/infeasible_*/       ← Track D: infeasible 케이스
Workflow (ad-hoc)           ← Track C: 3차원 적대 리뷰(sandbox/sweep/delta/render/medium/metrics)
```

## 2. Track A — GUI 실행 검증 (closes G-7)

### 2.1 설계
- **환경**: `uv sync --extra gui` 로 PySide6 실제 설치. `QT_QPA_PLATFORM=offscreen` (테스트 conftest에서 `os.environ` 설정, import 전).
- **하니스** (`tests/test_gui_render.py` 내 헬퍼 — 별도 패키지화 안 함, Option C):
  1. `QApplication([])` (offscreen).
  2. `graph_data.build_elements(tidy_bundle)` → Cytoscape elements.
  3. `InteractionGraphView` 인스턴스화 → `setGraph(elements)` (graph.html JS bridge 로드 대기).
  4. `widget.grab()` → `QPixmap` → `QImage` → numpy/PNG 저장.
  5. `GateBadge`는 gate 결과 주입 → grab.
- **검증 단언**:
  - 위젯 import·생성·렌더 **예외 0** (가장 큰 가치 — 바인딩/JS bridge 오류 포착).
  - 산출 `QImage` 픽셀 분산 > 0 (non-empty).
  - QWebEngine 렌더는 비동기 → JS bridge가 elements를 수신했는지는 `runJavaScript("cy.nodes().length")` 콜백으로 노드 수 == `tidy.nodes.num_rows` 단언 (DOM 레벨 계약; 픽셀이 비동기로 늦으면 픽셀 대신 DOM count를 1차 게이트로).
  - GateBadge: high→block 색/텍스트, low→warn 표시.

### 2.2 명시 경계 (정직성)
- offscreen 렌더 = **실행+산출 증거**. *human 시각 디자인 QA 아님.* 테스트 docstring·report에 명기. 후자는 **G-7b (별도, 본 사이클 out-of-scope)**.
- QWebEngine이 헤드리스 offscreen에서 GPU/JS 로드 불가 시: **DOM count 게이트(runJavaScript)**를 1차 증거로, 픽셀 검증은 best-effort. 그래도 차단 시 **정직히 "차단"** 보고(가짜 통과 금지).

## 3. Track B — End-to-end 수직 슬라이스

### 3.1 계약 매트릭스 (`tests/test_e2e_pipeline.py`)
실 3-member community 1회 실행으로 전 hop 통과 + 각 경계 계약 단언:

| Hop | 입력→출력 | 계약 단언 |
|-----|----------|----------|
| H1 model→engine | model → `SolveResult` | status∈{optimal,...}, member_growth 전 멤버 키 존재(I-1) |
| H2 engine→tidy | SolveResult → `TidyBundle` | schema_version 존재, run_hash 11구성, sign 규약 |
| H3 tidy→graph | TidyBundle → Cytoscape elements | 노드 보존(nodes.num_rows == elements 노드 수), gate 반영 |
| H4 tidy→render(R) | profile → SVG | bar 방향 ↔ profile.net_flux 부호 일관 |
| H5 graph→GUI(offscreen) | elements → QImage/DOM | Track A 게이트 재사용 |
| **교차** | run_hash | H2의 run_hash가 sweep/manifest 경유와 동일([HASH-SINGLE]) |

### 3.2 핵심 단언
- **부호 일관**: profile.net_flux>0 행 ↔ figure bar(+방향) ↔ graph edge_type 'secretion' 100% 일치.
- **노드 보존**: solve member 수 + environment_pool == tidy.nodes == graph 노드.

## 4. Track C — 적대적 리뷰 확장

### 4.1 범위 (per-slice Check만 받은 모듈)
`sandbox.py` · `sweep.py`(aggregation 경로) · `delta.py` · `render/client.py` · `medium.py` · `metrics.py`.

### 4.2 Workflow 설계 (ad-hoc, Check 단계 실행)
- 3차원 병렬(correctness·contract·quality) × 모듈, 각 finding을 적대적 verify(refute 우선)로 검증 → confirmed만 Gap 등재.
- 표적 패턴 (C-1/C-2/C-3 class): 계약 메타데이터 오염·schema_version 누락·silent drop·단일진입점 우회·비결정 직렬화.
- 산출: Check 단계 analysis에 Gap 등재(severity 분류) → Checkpoint 5에서 수정 범위 합의 → confirmed Critical/Important는 `tests/test_review_regressions.py`로 고정.

## 5. Track D — Minor-6 + FVA + Robustness

### 5.1 Data Contract 변경
| 항목 | 현재 | 변경 | 파급 |
|------|------|------|------|
| sign `eps` | 0.0 | noise floor 1e-6 (|flux|<eps → near_zero, label='exchange_inactive') | metrics·tidy label·golden sign_expected |
| engine status | "optimal" 부분 하드코딩 | `optimal`/`infeasible`/`unbounded`/기타 전파(enum) | SolveResult.status 소비자 |
| metrics 분류 | inline sign 분류 | `sign.classify()` 단일진입 경유 | 분류 drift 제거 |
| namespace coverage | WARNED 분모 제외 | 분모에 WARNED 포함 OR 지표 정의 docstring 명시 | coverage 수치 |
| tidy edge_type | label과 overload(OD-45) | edge_type(구조) ↔ label(부호) 분리 컬럼 | graph_data·golden edges |
| manifest | flux_report_status 미모델 | RunManifest 필드 추가 | manifest 직렬화 |

### 5.2 FVA 설계 (`cmig/core/fva.py` — closes G-3)
- **위임**: cobra `flux_variability_analysis(model, reaction_list=exchanges, loopless=<opt>, fraction_of_optimum=f)`. MICOM community 모델의 exchange에 적용.
- **출력**: `{metabolite: (fva_lo, fva_hi)}` → `tidy.profile.fva_lo/fva_hi` 실채움(현재 컬럼 존재, 미충전).
- **infeasible 진단**: FVA 실패 시 status 전파 + diagnostic 메시지(§5.1 status 연동).
- **불변식**: 모든 exchange에 `fva_lo ≤ net_flux ≤ fva_hi` (테스트 단언).
- **비용**: e_coli_core/3-member 한정, loopless 토글, 가이드 <60s.

### 5.3 Robustness Fixtures
- `fixtures/community_5_member/`: 다른 크기·namespace 혼합 → golden(gurobi hash-exact, OSQP tolerance) 재캡처.
- `fixtures/infeasible_*/`: 충돌 media → engine이 status='infeasible' + 진단(silent NaN 금지).
- edge-media: 극단 abundance(0 근방·dominant) → sign eps 경계 검증.

## 6. Test Plan (§8 대응)

| Level | Track | 테스트 | 게이트 |
|-------|:-----:|--------|--------|
| L-A | A | offscreen 위젯 렌더·DOM count·gate badge | SC-H1 |
| L-B | B | E2E 6-hop 계약 매트릭스 | SC-H2 |
| L-C | C | 적대 리뷰 발굴분 회귀 | SC-H3 |
| L-D1 | D | FVA fva_lo≤net≤fva_hi·infeasible 진단 | SC-H4 |
| L-D2 | D | 2nd golden·infeasible·edge-media | SC-H4 |
| L-reg | all | 기존 95 pytest 무회귀 + ruff/mypy | SC-H5 |

## 7. Risks
Plan §5 동일. 추가: sign eps 변경이 기존 golden sign_expected를 깨뜨릴 수 있음 → golden 재캡처 + 변경 의도 명시(과학적 정정이므로 의도된 diff).

## 8. Implementation Guide

### 8.1 권장 순서
A(실행증거) → B(통합) → C(발굴) → D(보강). A·B가 먼저면 C/D 수정의 회귀를 즉시 통합 레벨에서 검출.

### 8.2 Code Comment Convention
- `# Design Ref: §<n> — <decision>`
- `# Plan SC: SC-H<n>`

### 8.3 Session Guide (Module Map — `/pdca do --scope`)
| scope key | 산출물 | SC |
|-----------|--------|-----|
| `track-A` | tests/test_gui_render.py + conftest offscreen + `gui` extra 설치 | SC-H1 |
| `track-B` | tests/test_e2e_pipeline.py (6-hop 계약) | SC-H2 |
| `track-C` | Workflow 적대 리뷰 + tests/test_review_regressions.py + 발굴 수정 | SC-H3 |
| `track-D` | core/fva.py + Minor 수정(sign/metrics/engine/namespace/tidy/manifest) + fixtures + tests/test_fva.py·test_robustness.py | SC-H4 |

### 8.4 Environment
`uv sync --extra gui --extra engine --extra render`; PySide6 실제 설치 확인; R 4.3.2 + svglite/ragg(기존).

## 9. Next Steps
1. `/pdca do cmig-baseline-hardening --scope track-A` (실행증거 우선)
2. → track-B → track-C → track-D
3. `/pdca analyze` (적대 리뷰 포함) → iterate → report

## Version History
| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-01 | 초안 — Option C(Pragmatic) 선택. 4-track 검증·보강 설계 + Session Guide(track-A~D) + 계약 매트릭스 + FVA 위임 설계 + 정직성 경계(offscreen≠시각QA) 명시. |
