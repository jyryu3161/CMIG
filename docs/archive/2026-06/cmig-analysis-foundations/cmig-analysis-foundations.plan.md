<!--
Feature: cmig-analysis-foundations
Phase: Plan
Created: 2026-06-01
Basis: REVIEW/CMIG_v3_update_review_2026-06-01.md + CMIG_v3_implementation_review.md
Predecessors: cmig-community-core (2026-05), cmig-baseline-hardening (2026-06) — both archived
-->

# cmig-analysis-foundations Planning Document

> **질문 재정의(사용자)**: "특정 시나리오 6개를 구현하라"가 아니라 — *"저런 종류의 분석을 할 수 있는
> **기능 기반(capability foundations)**이 구현돼 있는가"*. 이 plan은 그 capability 지도를 그리고,
> 빠진 기반을 짓는다. 시나리오(S1~S6)는 capability 요구를 드러내는 **예시**이지 목표 자체가 아니다.

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 외부 리뷰(2026-06-01)가 확인: 분석의 *원자 연산*(상호작용·섭동·재현성)은 구현됐으나, 그것을 **실제 분석으로 바꾸는 기능 기반**(실모델 수집·배지 입력·사용자 산출 경로·표적 readout)이 없고, hybrid solver는 QP flux를 `full(LP)`로 **거짓 표기**한다. 결과적으로 분석을 *라이브러리/테스트 fixture 경로로는 실행할 수 있으나, **사용자-facing CLI/GUI 산출 경로로는 실행할 수 없다***. |
| **Solution** | capability foundation을 짓는다 — **C9** hybrid 정직화(`qp_only_approximate` + diagnostic code `metadata_only_hybrid`, 새 enum 미도입), **C7** CLI 산출(P0 solve-fixture → P1 solve), **C6** medium 입력/preset(+ run_hash 반영), **C8** SCFA target readout, **C3** sandbox 단일-GEM FVA 연결, **C5** synthetic cross-feeding fixture. S3(acetate→butyrate)를 synthetic golden으로 정성 검증. |
| **Function/UX 효과** | "라이브러리 함수만 있고 사용자가 못 돌림"→**CLI로 parquet+manifest 산출**, medium/diet 입력으로 외부 profile 비교, SCFA target summary 자동 생성, hybrid 결과가 더 이상 `full`로 위장 안 됨(diagnostic으로 한계 명시). |
| **Core Value** | CMIG를 "검증된 원자 연산 모음"에서 **"사용자가 실제 community 분석을 실행·재현·비교할 수 있는 기반"**으로. 정직성(hybrid)·실행성(CLI)을 동시에 확보. host schema seed는 별도 schema-migration feature로 분리. |

## Context Anchor

| 축 | 내용 |
|----|------|
| **WHY** | 분석 원자 연산은 있으나 *실행 기반*이 없어 capability가 사용자에게 닿지 않음. 외부 리뷰가 이 격차 + hybrid 거짓 표기를 확인. |
| **WHO** | gut microbiome/host-microbe 대사 모델링 연구자(실 분석 실행) + 유지보수자(정직성·재현성). |
| **RISK** | (1) C9 실 HiGHS 재계산 미구현 — diagnostic 강등으로 우회(후속 feature). (2) C5 실모델 import는 대형 공사 → **synthetic** fixture로 제한. (3) C11 host schema seed는 `validate()` exact-match 파급 때문에 **별도 schema-migration feature로 분리**(본 plan 코드 미반영). |
| **SUCCESS** | §4. 핵심: hybrid `full` 미표기 + diagnostic·CLI parquet 산출(P0 fixture)·medium 입력(+run_hash)·SCFA readout·단일-GEM FVA 연결·synthetic S3 golden. |
| **SCOPE** | capability foundation(C3 단일-GEM·C5 synthetic·C6·C7·C8·C9) + 정직성(R2·R5·R6) + S3 검증. host MVP-3(C11 full)·**C11 schema seed 코드 반영**·실 AGORA import(C5 full)·community-level FVA·cohort 통계는 out-of-scope. |

## 1. Overview

### 1.1 Purpose
community/host-microbe 대사 분석 클래스를 **실제 실행 가능**하게 만드는 **기능 기반**을 짓는다. 신규 분석 알고리즘이 아니라, 이미 검증된 원자 연산(C1·C2·C4)을 사용자 분석 흐름으로 잇는 **수집(C5)·입력(C6)·산출(C7)·readout(C8)·정직성(C9)** 기반.

### 1.2 Background — 외부 리뷰 확인 사항 (검증 완료)
- **C9/U1·R1 (검증됨)**: `engine.py`는 `cooperative_tradeoff` 1회 호출 후 hybrid일 때 라벨만 `highs/full`로 변경 — **실 HiGHS LP 재계산 코드 부재**. golden `osqp`↔`osqp_growth_highs_flux` tidy_hash **바이트 동일**. cycle #2 적대 리뷰는 pure-osqp만 정직화(`qp_only_approximate`)했고 hybrid 거짓은 잔존.
- **C7/R3 (검증됨)**: `cmig solve`는 stub(`return 2`).
- **C5·C6·C8·C11**: 부재 확인.

### 1.3 Capability Foundation Map (이 plan의 중심 — 사용자 질문의 직접 답)
| # | capability | 현재 | 본 plan |
|---|-----------|:---:|:------:|
| C1 상호작용 추출 | ✅ | 유지 |
| C2 섭동/sweep | ✅ | 유지 |
| C3 FVA | ⚠️ 미연결 | **단일-GEM/sandbox 연결**(community-level FVA는 후속) |
| C4 재현성/manifest | ✅ | 유지 |
| C5 실모델 수집 | ❌ | **synthetic fixture seed**(실 AGORA import는 후속) |
| C6 배지 입력/preset | ❌ | **구축**(+ medium checksum → run_hash) |
| C7 사용자 산출(CLI) | ❌ | **구축**(P0 solve-fixture → P1 solve) |
| C8 표적 readout(SCFA) | ❌ | **구축** |
| C9 solver 정직성 | ❌ 거짓 | **정직화**(qp_only_approximate + diagnostic, 새 enum X) |
| C10 실모델 namespace workflow | ⚠️ gate만 | seed(synthetic 범위) |
| C11 host-microbe | ❌ | **out-of-scope** — schema seed도 별도 schema-migration feature |

### 1.4 Related Documents
- 리뷰: `REVIEW/CMIG_v3_update_review_2026-06-01.md`, `REVIEW/CMIG_v3_implementation_review.md`
- 명세: `CMIG_명세서_v3.0.md` (§4.2 solver·§12 host spike·§16 MVP)
- 선행 아카이브: `docs/archive/2026-05·2026-06/`

## 2. Scope

우선순위 단계(Do 단위) — P0 먼저, P3는 본 plan 밖:
- **P0 정직성/실행성**: C9 hybrid 정직화, C7 solve-fixture, R5 diagnostic JSON helper, R6 README.
- **P1 분석 입력/readout**: C6 medium spec/preset(+run_hash), C8 SCFA target summary, C7 `solve --taxonomy --medium`.
- **P2 검증 fixture**: C5 synthetic acetate-producer/butyrate-consumer pair golden(S3), C3 sandbox 단일-GEM FVA.
- **P3(분리)**: C11 host schema seed = 별도 **schema-migration feature**(schema_version bump·legacy reader 포함).

### 2.1 In Scope (P0~P2)
- **C9 정직화**: hybrid가 `flux_report_status='full'` 미표기 → **`qp_only_approximate` 유지 + diagnostic code `metadata_only_hybrid`**(새 FluxReportStatus enum 미도입 — 작고 안전). golden config 라벨 갱신.
- **C7 CLI 산출**: **P0** `cmig solve-fixture --solver --tradeoff-f --out`(nodes/edges/profile.parquet + manifest) → **P1** `cmig solve --taxonomy --medium --solver`(입력 검증). 성공 기준 단계화.
- **C6 medium 입력**: medium spec 로더(csv/yaml) + `medium_presets/`(diet preset seed) + **MICOM public API로 medium 설정 경로 명시** + **medium checksum이 run_hash(§4.2 11구성요소)에 반영**.
- **C8 표적 readout**: `TargetMetaboliteSet`(SCFA: acetate/propionate/butyrate/lactate/succinate) + profile/delta target-only summary(sign 단일진입 경유).
- **C3 FVA 연결**: **sandbox affected single-GEM/reaction FVA만** — `evaluate_sandbox(..., fva=None)`로 no-change 시 FVA range 동반. **community-level(MICOM) FVA는 out-of-scope(후속 조사)**.
- **C5 synthetic seed**: `fixtures/pair_acetate_butyrate/` **synthetic_acetate_producer / synthetic_butyrate_consumer** toy GEM 2종(종명 미부여, "문헌 대표 관계 모사 synthetic fixture") + golden(cross-feeding·sign 정성 고정) = **S3 정성 검증**.
- **정직성 부수**: R5 diagnostic `{code,message,detail}` 구조화 · R2 golden solver 목록 공식 결정 로그 · R6 README 갱신.

### 2.2 Out of Scope
- **C11 schema seed(코드 반영)** = 별도 schema-migration feature(schema_version bump·legacy reader·golden 재캡처). 본 plan은 문서/adapter 설계 노트까지만.
- C11 full(HostModel·viability constraint·multi-objective host solve) = MVP-3.
- C5 full(실 AGORA2/VMH SBML import·대규모 namespace mapping) = 별도 foundation feature.
- C9 실 HiGHS LP pFBA 재계산(정직화로 갈음) = 후속.
- **community-level FVA**(MICOM) · cohort 통계 · diet preset 대량 큐레이션 · drug biotransformation(S6).

## 3. Requirements

### 3.1 Functional Requirements
| ID | 요구 | P | capability |
|----|------|:-:|:----------:|
| FR-F1 | hybrid가 `full` 미표기 — `qp_only_approximate` 유지 + diagnostic code `metadata_only_hybrid`(새 enum X). golden 라벨 갱신 | P0 | C9 |
| FR-F2 | 정직성 검증 테스트: "hybrid is not full despite same flux" — 동일 flux는 *현재 한계 설명*(guard)이지 성공 조건 아님 | P0 | C9 |
| FR-F3 | `cmig solve-fixture`가 nodes/edges/profile.parquet + manifest(run_hash) 산출, run_hash==라이브러리 | P0 | C7 |
| FR-F4 | `cmig solve --taxonomy --medium --solver`가 동일 산출(입력 검증 포함) | P1 | C7 |
| FR-F5 | medium spec 로더(csv/yaml) + `medium_presets/` seed + **MICOM API medium 설정 경로** + **medium checksum → run_hash 반영** | P1 | C6 |
| FR-F6 | `TargetMetaboliteSet`(SCFA) + profile/delta target-only summary(sign 단일진입) | P1 | C8 |
| FR-F7 | sandbox no-change 시 **단일-GEM/reaction FVA range** 동반(SandboxDiagnostics). community FVA는 범위 밖 | P2 | C3 |
| FR-F8 | `fixtures/pair_acetate_butyrate` **synthetic** golden — cross-feeding/sign 정성 검증(S3) | P2 | C5 |
| FR-F9 | sweep/solve/sandbox diagnostic `{code,message,detail}` 구조화 | P0 | R5 |
| FR-F10 | golden solver 목록 결정(명세 highs vs 구현 osqp) 공식 로그 + README 현행화 | P0 | R2·R6 |
| FR-F11 | (분리) C11 host schema seed = 별도 schema-migration feature 설계 노트만(코드 미반영) | — | C11 |

### 3.2 Non-Functional
- 기존 129 pytest 무회귀 + ruff/mypy strict 유지. CLI 산출은 결정적(run_hash 일치).
- **tidy schema 미변경**(C11 seed 코드 제외) → 기존 parquet/golden·`TidyBundle.validate()` exact-match 미파손.
- synthetic GEM은 라이선스-clean·소형(빠른 solve)·종명 미부여.

## 4. Success Criteria (단계화)
- **SC-F1 (C9, P0)**: hybrid의 `flux_report_status`가 **`full`이 아님** + diagnostic code=`metadata_only_hybrid` 존재. (성공=정직 표기. *osqp↔hybrid 동일 flux는 현재 한계를 설명하는 guard 테스트일 뿐 성공 조건 아님.*)
- **SC-F2 (C7, P0)**: `cmig solve-fixture`가 parquet+manifest 산출, **run_hash == 라이브러리 경로**([HASH-SINGLE]).
- **SC-F3 (C7, P1)**: `cmig solve --taxonomy --medium`가 입력 검증 후 동일 산출.
- **SC-F4 (C6, P1)**: medium preset A vs B로 external profile이 달라짐 AND medium checksum 차이가 run_hash에 반영.
- **SC-F5 (C8, P1)**: SCFA target summary가 profile/delta에서 자동 산출.
- **SC-F6 (C3, P2)**: sandbox no-change 케이스에 **단일-GEM** FVA range 동반.
- **SC-F7 (C5/S3, P2)**: synthetic acetate-producer→butyrate-consumer golden이 acetate cross-feeding edge·butyrate secretion·sign 규약을 정성 고정.
- **SC-F8**: 무회귀 — 전 테스트 green, ruff/mypy clean, README 현행화, golden 결정 로그(R2).

### 4.1 Quality Criteria
- FR-F8 synthetic golden: producer→consumer acetate cross-feeding edge 존재 AND consumer butyrate secretion>0 AND sign 규약 일치.
- CLI 산출 parquet의 run_hash == 라이브러리 경로 run_hash([HASH-SINGLE]).
- C9: hybrid의 flux_report_status ≠ `full` AND diagnostic code = `metadata_only_hybrid`.

## 5. Risks and Mitigation
| 위험 | 영향 | 완화 |
|------|------|------|
| C9 정직화가 "기능 후퇴"로 보임 | 사용자 혼란 | 정직화=거짓 제거; `qp_only_approximate`+diagnostic으로 한계 명시; 실 HiGHS는 후속 |
| synthetic GEM이 과학적으로 비현실적 | S3 신뢰도 | 종명 미부여·"정성적 cross-feeding 검증용 synthetic" 명시; 실 AGORA는 C5 full(후속) |
| C11 schema seed 코드 반영이 golden/`validate()` 파손 | 회귀 | **본 plan에서 코드 반영 제외** → 별도 schema-migration feature(schema_version bump·legacy reader) |
| CLI 입력 다양성(medium 포맷) | 범위 확대 | P0 solve-fixture(고정 입력) → P1 solve 점진 |
| medium이 run_hash에 미반영 시 재현성 훼손 | 재현성 | medium checksum을 run_hash 11구성요소(§4.2)에 반영(FR-F5) |
| golden 목록 결정이 명세 위반 | 거버넌스 | REVIEW 결정 로그로 공식화(R2) |

## 6. Impact Analysis
### 6.1 Changed/New
- 수정: `cmig/core/engine.py`(C9 hybrid diagnostic), `cmig/cli/main.py`(C7 solve), `cmig/core/sweep.py`·`sandbox.py`(R5 diagnostic·C3 FVA), `golden_fixture.py`(C9 라벨), `README.md`(R6). **tidy.py는 미변경(C11 seed 코드 제외)**.
- 신규: `cmig/core/medium_spec.py`(C6), `cmig/core/targets.py`(C8), `cmig/core/diagnostics.py`(R5), `cmig/io/solve_output.py`(C7), `medium_presets/*.yaml`, `fixtures/pair_acetate_butyrate/`(C5/S3 synthetic), 대응 테스트.
### 6.2 Consumers
- C9 변경은 hybrid golden config 라벨·flux_report_status 소비자 파급 → golden config·테스트 재정렬(flux 값 자체는 불변).
- C6 medium checksum 반영은 run_hash에 영향 → medium 없는 경로는 default checksum로 하위호환.

## 7. Architecture Considerations
- Level: Dynamic 유지. 기존 4-seam + headless core 위에 capability 모듈 추가.
- C7 CLI는 라이브러리(engine·tidy·manifest) 재사용 — 신규 solve 로직 없음(단일 경로, [HASH-SINGLE]).
- C9: MICOM이 fixed-growth 후 LP pFBA 재계산 API를 제공하는지는 후속 조사 — 본 plan은 *정직 표기(diagnostic)*까지.
- C6: MICOM public API의 medium 설정 경로(community.medium 또는 build 시 주입)를 design에서 단일 방식으로 고정 + medium checksum→run_hash.
- C3: **단일-GEM/sandbox reaction FVA만**(cmig/core/fva.py는 cobra 단일 모델용). community-level(MICOM) FVA는 별도 조사.
- C11: 본 plan은 schema seed *설계 노트*까지 — 코드(tidy 컬럼)는 별도 feature.

## 8. Convention Prerequisites
- 단일 경로: CLI는 라이브러리 경유(자체 solve 금지). run_hash 단일 canonical.
- diagnostic code enum: `{infeasible, solver_error, capability_missing, gate_blocked, metadata_only_hybrid, members_missing}`.
- synthetic GEM·preset 라이선스·종명 미부여 명시.

## 9. Next Steps
1. `/pdca design cmig-analysis-foundations` — (완료, 피드백 반영) capability 모듈 경계 + Session Guide(C9→C7→C6→C8→C3→C5).
2. `/pdca do --scope C9-honesty` 부터(P0) → C7 → C6 → C8 → C3 → C5.
3. `/pdca analyze` → report.

## Version History
| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-01 | 외부 리뷰 기반 — capability foundation 지도 + 빠진 기반 구축 plan. 사용자 재정의 반영. |
| 1.1 | 2026-06-01 | 리뷰 피드백 8건 반영: (1) "사용자 실행 불가"→"CLI/GUI 산출 경로 불가"(라이브러리 가능) (2) hybrid=qp_only_approximate+diagnostic(새 enum X) (3) C11 schema seed 코드 반영 제외→별도 feature (4) synthetic 명명(종명 X) (5) P0~P2 단계화 (6) medium checksum→run_hash (7) 단일-GEM FVA만(community FVA 후속) (8) "동일 flux=성공" 제거→정직성 guard. |
