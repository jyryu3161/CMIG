<!--
Feature: cmig-baseline-hardening
Phase: Plan
Created: 2026-06-01
Predecessor: cmig-community-core (archived 2026-05-31, baseline MVP-0~2, 98.25%)
Basis: archived adversarial review — docs/archive/2026-05/cmig-community-core/cmig-community-core.analysis.md §11 (Re-Check #6)
-->

# cmig-baseline-hardening Planning Document

> **솔직한 검토 기반 개선 사이클.** cmig-community-core baseline은 "문서↔코드 계약 + 단위 런타임" 98.25%로 닫혔으나, **(1) GUI가 한 번도 실행된 적 없고, (2) 수직 통합이 증명 안 됐으며, (3) 적대적 리뷰를 받은 모듈만 그 정밀도로 검증됨**. 이 plan은 그 정직한 격차를 닫는다.

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | baseline 98.25%는 *계약·단위* 지표일 뿐 *제품 동작* 지표가 아니다. CMIG의 "G"(GUI)는 import조차 안 됐고(G-7), 전 파이프라인을 관통하는 통합 증거가 없으며, per-slice Check가 run_hash를 오염시킨 Critical 3건을 놓쳤다(적대적 리뷰가 사후 포착). 미검토 모듈에 동급 결함이 잠재한다. |
| **Solution** | 4트랙 하드닝: **(A)** GUI를 offscreen QPA로 실제 실행→산출 검증, **(B)** model→solve→tidy→graph→render→R figure end-to-end 통합 테스트, **(C)** 미검토 모듈(sandbox·sweep·delta·render·medium·metrics)에 적대적 리뷰 확장, **(D)** 과학적 영향 있는 Minor-6 수정 + AN-SINGLE FVA 실구현 + robustness fixture 추가. |
| **Function/UX 효과** | "never executed GUI"→"실행+산출 검증"; 결합부 미지수→통합 1-pass 보장; 잠재 계약 버그 발굴·고정; 0근방 flux 라벨 정확성·coverage 지표 정직화·fva_lo/hi 실제 채움. 재현성 비대칭(Gurobi only bit-exact)을 명시 문서화. |
| **Core Value** | baseline을 "통과하는 문서"에서 **"실행으로 증명된 제품"**으로. 정직한 잔여 위험(human 시각 QA, OSQP 근사 재현)을 숨기지 않고 명시적 경계로 전환. |

## Context Anchor

| 축 | 내용 |
|----|------|
| **WHY** | 98.25%가 가린 3대 정직성 격차(미실행 GUI·미증명 통합·미검토 모듈)를 닫아, 지표가 아니라 동작으로 baseline을 신뢰 가능하게 만든다. |
| **WHO** | community 대사 모델링 연구자(직접 사용자) + CMIG 유지보수자(재현성·계약 신뢰 필요). |
| **RISK** | (1) 헤드리스 환경에서 GUI 시각 QA는 여전히 human 필요 — offscreen은 실행 증거지 시각 검증 아님(명시). (2) 적대적 리뷰가 신규 Critical을 더 발굴하면 범위 확대. (3) FVA가 큰 모델에서 비용↑. |
| **SUCCESS** | 아래 §4. 핵심: GUI offscreen 렌더 산출 검증·E2E 1-pass·미검토 모듈 적대 리뷰 0 Critical 잔존·과학영향 Minor 해소·FVA가 fva_lo/hi 실채움. |
| **SCOPE** | baseline(MVP-0~2) 하드닝. PART II(동적 FBA·시계열·multi-condition)는 out-of-scope. |

## 1. Overview

### 1.1 Purpose
cmig-community-core baseline의 **정직한 잔여 위험을 닫는다.** 신규 기능 추가가 아니라, 이미 "완료"로 표기된 산출물이 *실제로 실행되고·통합되고·계약을 지키는지*를 증거로 전환하는 검증·보강 사이클.

### 1.2 Background
- baseline은 2026-05-31 archived (docs/archive/2026-05/cmig-community-core/).
- 최종 적대적 리뷰(Re-Check #6, 24-agent)가 per-slice Check가 놓친 **3 Critical + 6 Important** 계약/정확성 결함을 포착 → Act #2로 해소(98.25%).
- 그러나 적대적 정밀도를 받은 건 engine/sweep/golden/manifest 중심. **GUI는 미실행, 통합은 미증명, 절반의 모듈은 per-slice Check만 받음.**

### 1.3 Related Documents
- 전임 Plan/Design/Report: `docs/archive/2026-05/cmig-community-core/`
- 리뷰 근거: 동 폴더 `cmig-community-core.analysis.md` §11 (Re-Check #6 + Act #2)
- 명세: `CMIG_명세서_v3.0.md`
- 공통 참조: `docs/01-plan/glossary.md`, `docs/01-plan/schema.md`

## 2. Scope

### 2.1 In Scope — 4 Tracks

**Track A — GUI 실행 검증 (closes G-7)**
- `gui` extra(PySide6) 실제 설치, `QT_QPA_PLATFORM=offscreen`으로 헤드리스 실행.
- `InteractionGraphView`/`GateBadge`를 실제 인스턴스화→graph_data elements 주입→오프스크린 렌더→PNG/grab 산출.
- 검증: 위젯이 예외 없이 import·생성·렌더되고, 산출 이미지가 non-empty(픽셀 분산>0), 노드/엣지 수가 입력 tidy와 일치, gate 배지가 정책(high=block/low=warn)대로 표시.
- **명시 경계**: offscreen 렌더는 *실행+산출* 증거이며 *human 시각 디자인 QA가 아니다*. 후자는 별도 G-7b로 분리 유지.

**Track B — End-to-end 수직 슬라이스**
- 단일 통합 테스트: 실 모델 → `MicomEngine.cooperative_tradeoff` → `build_tidy` → `graph_data` → offscreen 렌더 → `RenderClient`(R figure) 전 체인.
- 검증: 각 hop의 계약(schema_version·sign·run_hash·gate)이 결합 상태에서 보존됨. profile→figure 부호 일관성, tidy→graph 노드 보존.

**Track C — 적대적 리뷰 확장**
- per-slice Check만 받은 모듈에 correctness·contract·quality 3차원 적대적 패스: `sandbox.py`·`sweep.py`(aggregation)·`delta.py`·`render/client.py`·`medium.py`·`metrics.py`.
- C-1/C-2급(계약 메타데이터 오염)·C-3급(schema 누락) 패턴 표적. 발굴 결과는 Check 단계 Gap으로 등재.

**Track D — Minor-6 + G-3 FVA + robustness**
- **과학영향 Minor 수정**: sign `eps` noise floor(1e-6) 정합, metrics를 sign 단일진입점 경유, engine status 전파 완성, namespace coverage 분모에 WARNED 포함(또는 지표 정의 명시).
- **표현 Minor**: edge_type/label overload 분리(OD-45), manifest에 flux_report_status 모델링.
- **G-3 AN-SINGLE FVA**: cobra `flux_variability_analysis`(loopless 옵션) 실구현 → `profile.fva_lo/fva_hi` 실채움 + infeasible 진단.
- **Robustness fixture**: 2번째 golden community(다른 크기/namespace) + infeasible 모델 케이스 + edge media.

### 2.2 Out of Scope (PART II)
- 동적/시계열 community FBA, multi-condition 통계 비교, 설치형 패키징(installer), 클라우드 잡 러너, human 시각 디자인 QA의 자동화(본 사이클은 실행 증거까지).

## 3. Requirements

### 3.1 Functional Requirements

| ID | 요구사항 | Track |
|----|---------|:-----:|
| FR-H1 | PySide6 위젯이 offscreen에서 예외 없이 렌더되고 non-empty 산출 생성 | A |
| FR-H2 | 렌더 산출의 노드/엣지 수·gate 표시가 입력 tidy와 일치 | A |
| FR-H3 | model→figure 전 파이프라인 1-pass 통합 테스트 통과 | B |
| FR-H4 | 각 hop 계약(schema_version·sign·run_hash·gate) 결합 상태 보존 검증 | B |
| FR-H5 | 6개 미검토 모듈 적대적 리뷰 완료, 발굴 Gap 등재·분류 | C |
| FR-H6 | 발굴된 Critical/Important 결함 수정 + 회귀 테스트 | C |
| FR-H7 | sign eps noise floor 정합 — 0근방 flux 라벨 정확 | D |
| FR-H8 | metrics가 sign 단일진입점 경유(분류 drift 제거) | D |
| FR-H9 | engine status 전파 완성(optimal/infeasible/기타) | D |
| FR-H10 | AN-SINGLE FVA 실구현 → fva_lo/fva_hi 실값 + infeasible 진단 | D |
| FR-H11 | 2번째 golden + infeasible + edge-media robustness fixture | D |
| FR-H12 | 재현성 비대칭(Gurobi bit-exact ↔ OSQP/HiGHS tolerance) 명시 문서화 | D |

### 3.2 Non-Functional Requirements
- 기존 95 pytest 전부 green 유지(무회귀). 신규 트랙별 테스트 추가.
- ruff clean·mypy strict clean 유지(신규 모듈 포함).
- offscreen 렌더는 CI/헤드리스에서 결정적 재실행 가능(seed·QPA 고정).
- FVA는 e_coli_core/3-member 규모에서 합리적 시간(가이드 <60s) 내.

## 4. Success Criteria

### 4.1 Definition of Done
- **SC-H1 (A)**: GUI 위젯 offscreen 실행+산출 검증 테스트 통과 — G-7 "never executed" 해소.
- **SC-H2 (B)**: end-to-end 통합 테스트 1건 green, 전 hop 계약 보존 단언.
- **SC-H3 (C)**: 6개 모듈 적대적 리뷰 완료, **잔존 Critical·Important 0**(발굴분 수정 후).
- **SC-H4 (D)**: 과학영향 Minor 4건 수정 + FVA가 fva_lo/hi 실채움 + robustness fixture green.
- **SC-H5**: 무회귀 — 전 사이클 테스트 green, ruff/mypy clean, 0 placeholder.
- **SC-H6**: 정직성 산출물 — 잔여 위험(human 시각 QA, OSQP 근사 재현)이 report에 명시적 경계로 기록.

### 4.2 Quality Criteria (측정 가능)
- offscreen 산출 이미지 픽셀 분산 > 0 AND 노드 수 == tidy.nodes.num_rows.
- E2E 테스트: profile sign ↔ figure bar 방향 일관(100%).
- 적대적 리뷰 confirmed Critical 전부 회귀 테스트로 고정.
- FVA: 모든 exchange에 fva_lo ≤ net_flux ≤ fva_hi 성립.

## 5. Risks and Mitigation

| 위험 | 영향 | 완화 |
|------|------|------|
| offscreen ≠ 시각 QA — "검증됨" 오해 | 정직성 훼손 | report·테스트 docstring에 경계 명시, G-7b(human QA) 별도 유지 |
| 적대적 리뷰가 신규 Critical 대량 발굴 | 범위·일정 확대 | Check에서 severity 분류 후 Checkpoint 5로 수정 범위 재합의 |
| PySide6 헤드리스 설치/QPA 이슈 | Track A 차단 | offscreen 우선, 실패 시 `QPainter` 직접 grab fallback, 그래도 불가면 정직히 "차단" 보고 |
| FVA 비용/비결정성 | Track D 지연 | 소규모 fixture 한정, loopless 옵션 토글, tolerance 비교 |
| OSQP 근사 재현이 robustness fixture에서 흔들림 | 신뢰 저하 | 기존 atol 1e-4 정책 재사용, 결정적 solver와 분리 검증 |

## 6. Impact Analysis

### 6.1 Changed/New Resources
- 신규 테스트: `tests/test_gui_render.py`(A), `tests/test_e2e_pipeline.py`(B), 적대 리뷰 발굴분 회귀(C), `tests/test_fva.py`·`tests/test_robustness.py`(D).
- 수정: `cmig/core/sign.py`(eps), `cmig/core/metrics.py`(sign 경유), `cmig/core/engine.py`(status 전파), `cmig/core/namespace.py`(coverage), `cmig/core/tidy.py`(edge_type), `cmig/core/manifest.py`(flux_report_status 모델).
- 신규: `cmig/core/fva.py`(또는 engine 확장) — AN-SINGLE FVA.
- 신규 fixture: `fixtures/community_<2nd>/`, infeasible/edge-media 케이스.
- `pyproject.toml`: `gui` extra 실제 설치 경로 확인.

### 6.2 Current Consumers
- profile fva_lo/hi 소비자: R figure·graph_data → FVA 실값 채움 시 하위 호환(이미 컬럼 존재).
- sign 변경은 metrics·tidy label에 파급 → 회귀 테스트로 고정.

### 6.3 Verification
- 트랙별 테스트 + 기존 95 pytest 무회귀 + ruff/mypy + Check 단계 적대 리뷰.

## 7. Architecture Considerations

### 7.1 Project Level
Dynamic (기존 유지). 신규 아키텍처 도입 없음 — 기존 4-seam(SolverBackend·EngineWrapper·Store·RenderClient)·headless core 위에 검증·보강.

### 7.2 Key Decisions (확정/예정)
- A: offscreen QPA(`QT_QPA_PLATFORM=offscreen`) 우선 — 헤드리스 결정성·CI 친화.
- C: 적대적 리뷰는 Check 단계 workflow로 실행(per-slice가 아닌 cross-module).
- D: FVA는 cobra public API(`flux_variability_analysis`) 위임 — MICOM 위임 철학 일관, 자체 LP 미구현.

### 7.3 Approach
기존 `cmig/` 구조 유지. 변경은 국소(파일 단위), 신규는 `core/fva.py`·`tests/`·`fixtures/`에 한정.

## 8. Convention Prerequisites
- 기존 컨벤션 준수: Design Ref 주석·Plan SC 주석·sign 단일진입·tidy schema_version·[HASH-SINGLE].
- 신규 정의: offscreen 렌더 테스트 결정성 규약(seed·QPA·산출 비교 tolerance).
- 환경: `uv sync --extra gui --extra engine --extra render`; R 4.3.2 + svglite/ragg(기존); PySide6 실제 설치.

## 9. Next Steps
1. `/pdca design cmig-baseline-hardening` — 트랙별 검증 설계(offscreen 렌더 하니스·E2E 계약 매트릭스·적대 리뷰 범위·FVA 경로).
2. `/pdca do --scope track-A …` 순차 구현(권장 순서 A→B→C→D: 실행증거→통합→발굴→보강).
3. `/pdca analyze` 적대 리뷰 포함 Check → iterate → report.

## Version History
| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-01 | 초안 — archived 적대적 리뷰(§11) 기반 정직한 검토 + 4-track 하드닝 plan. 사용자 범위 확정: A·B·C·D 전체. |
