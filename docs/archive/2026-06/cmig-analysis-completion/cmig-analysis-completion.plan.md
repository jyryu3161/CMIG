<!--
Feature: cmig-analysis-completion
Phase: Plan
Created: 2026-06-01
Predecessor: cmig-analysis-foundations (archived 2026-06)
Constraint: HiGHS 제거, solver 의존 기능은 gurobi-only
-->

# cmig-analysis-completion Planning Document

> cmig-analysis-foundations(cycle #3)가 남긴 carried-over 중 **gurobi로 지금 구현 가능한 5개
> foundation 완성 항목**을 닫는다. 사용자 제약: **HiGHS 제거 · solver 의존 기능은 gurobi-only**.
> 대형 데이터 foundation인 **실 AGORA/VMH import는 별도 feature로 분리**(본 plan 밖).

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | foundation cycle가 일부 capability를 미완으로 남겼다 — hybrid flux는 정직 표기만(실 LP 재계산 미수행), FVA는 단일-GEM만(community FVA 없음), SCFA readout은 CLI 미노출, diagnostic은 sweep만 구조화(engine/delta/sandbox legacy 문자열), host schema seed는 코드 미반영. |
| **Solution** | gurobi-only로 5개 완성 — **F1** 실 LP flux 재계산(gurobi) · **F2** community-level FVA(cobra FVA on micom community, gurobi·processes=1) · **F3** CLI `--targets`(SCFA summary 산출) · **F4** diagnostic 전면 구조화(engine/delta/sandbox→Diagnostic) · **F5** C11 host schema-migration(schema_version bump + legacy reader). |
| **Function/UX 효과** | hybrid가 *진짜* LP flux(full)를 gurobi로 산출(또는 정직 폐기), community 전체 exchange의 FVA 범위 산출(fva_lo/hi 실채움), `cmig solve --targets scfa`로 SCFA summary 파일 산출, 모든 diagnostic이 기계판독 JSON, host 확장 schema 자리 코드 반영. |
| **Core Value** | "정직하게 미완으로 남긴 것"을 gurobi로 실제 완성. 단, HiGHS 의존을 버리고 gurobi-only로 단순화·확실화 — 무라이선스 경로(osqp)는 qp_only_approximate로 유지(정직). |

> **확정 결정 (Plan gate, design으로 미루지 않음)**: **F1 = `osqp_growth_highs_flux`(hybrid) 폐기.**
> gurobi=full을 canonical full-flux 경로로, osqp=qp_only_approximate를 무라이선스 정직 경로로 둔다.
> `osqp_growth_gurobi_flux`(OSQP-growth→gurobi-LP recalc) experimental 변형은 **본 cycle 밖**(필요 시 후속).
> 이유: "HiGHS 제거 + gurobi-only 단순화" 목표에 폐기가 가장 부합하고, hybrid가 코드/테스트/fixture
> 9파일+golden 디렉터리에 깊게 박혀 있어 *열어두면 design 작업량이 흔들린다*(외부 리뷰).

## Context Anchor

| 축 | 내용 |
|----|------|
| **WHY** | foundation의 정직한 미완 항목을 gurobi로 실제 완성 — 지표가 아니라 동작으로. |
| **WHO** | gurobi 라이선스 보유 연구자(full flux·community FVA) + 유지보수자(diagnostic·schema). |
| **RISK** | (1) community FVA가 큰 community에서 비용↑(processes=1). (2) C11 schema-migration이 기존 golden 재캡처 유발(validate() exact-match → reader 승격 필요). (3) F1 hybrid 폐기가 9파일+fixture에 흩어져 누락 회귀 위험(SC-C3 grep 게이트). |
| **SUCCESS** | §4 SC-C1~C6. 핵심: 실 LP flux(gurobi)·community FVA fva_lo/hi 실채움·CLI --targets·diagnostic JSON 통일·host schema v1.1 하위호환. |
| **SCOPE** | gurobi-only 5개 완성(F1~F5). **out-of-scope**: 실 AGORA/VMH import(별도 feature)·HiGHS LP 경로·무라이선스 full flux. |

## 1. Overview

### 1.1 Purpose
cmig-analysis-foundations의 carried-over를 닫되, **HiGHS를 제거하고 solver 의존 기능을 gurobi-only로 단순화**한다. gurobi는 QP+LP+MILP+FVA를 모두 지원하므로 cycle #3에서 research-gated였던 항목(실 LP 재계산·community FVA)이 **확실히 구현 가능**(probe 확인).

### 1.2 Background — 제약·feasibility (probe 검증)
- **HiGHS 제거**: hybrid의 HiGHS LP 경로를 버린다. full flux는 gurobi로만.
- **community FVA**: micom `Community`는 cobra `Model` 서브클래스 → `cobra.flux_variability_analysis(community, processes=1)` 동작 확인(병렬 worker는 pickling 실패, 단일 프로세스 성공).
- **LP flux 재계산**: gurobi `cooperative_tradeoff(pfba=True)`가 이미 실 LP pFBA flux 산출 — gurobi=full은 실재.

### 1.3 Related Documents
- 선행: `docs/archive/2026-06/cmig-analysis-foundations/` (plan/design/analysis/report)
- 결정 로그: `docs/decisions/2026-06-01-golden-solver-list.md`
- 명세: `CMIG_명세서_v3.0.md`

## 2. Scope

우선순위 단계(Do 단위):
- **P0 (저위험 완성)**: F3 CLI --targets, F4 diagnostic 전면 구조화.
- **P1 (gurobi solver 기능)**: F1 실 LP flux 재계산, F2 community-level FVA.
- **P2 (schema migration)**: F5 C11 host schema-migration.

### 2.1 In Scope
- **F1 — hybrid 폐기 + gurobi=full canonical (확정)**: `osqp_growth_highs_flux`를 제거한다. **migration 전 표면 정리(9파일+fixture)**:
  - `core/engine.py`: hybrid 분기·`METADATA_ONLY_HYBRID` 상수·관련 docstring 제거(또는 명시적 deprecation 에러).
  - `golden_fixture.py`: `SOLVER_VARIANTS=("gurobi","osqp")` (hybrid 제거).
  - `fixtures/community_3_member/expected/osqp_growth_highs_flux/`: 디렉터리 **삭제**.
  - `cli/main.py`: `solve`·`solve-fixture` `--solver` choices에서 hybrid 제거.
  - `core/solver.py`·`core/diagnostics.py`: hybrid 잔재(DiagnosticCode.METADATA_ONLY_HYBRID 사용처) 정리.
  - 테스트: `test_engine_golden.py`(hybrid parametrize·`test_hybrid_*`·`test_osqp_to_lp_matches_gurobi_profile`)·`test_cli_solve.py`·`test_diagnostics.py`의 hybrid 케이스 제거/갱신.
  - `README.md` hybrid caveat 제거, `docs/decisions/2026-06-01-golden-solver-list.md` golden 목록 = gurobi/osqp로 갱신(결정 로그).
  - 결과: **`full`은 gurobi LP flux일 때만**(이미 동작). osqp=qp_only_approximate 유지.
- **F2 — community-level FVA (gurobi)**: `cobra.flux_variability_analysis(community, processes=1)` 위임. **reaction-id → metabolite 매핑 확정**: community FVA는 reaction id(`EX_*_m`) 기준, profile은 metabolite key(`ac`,`but`) → `_met_from_exchange(col,"_m")` 정규화로 매핑(현 engine 추출 규약 재사용). **scope: `EX_*_m`(환경 exchange)만 profile `fva_lo/fva_hi`에 부착**; member `EX_*_e` readout 확장은 out-of-scope(후속). fraction_of_optimum·infeasible 진단·fva_lo≤net≤fva_hi 불변.
- **F3 — CLI --targets**: `cmig solve [--targets scfa]` → `target_summary.json` 산출(C8 targets wire). manifest artifacts에 추가.
- **F4 — diagnostic 전면 구조화**: engine/delta/sandbox의 자유 문자열 diagnostic → `Diagnostic.to_json()` 통일(DiagnosticCode 사용). 다중 원인(engine diag_parts)은 primary code + detail로 수용. 기존 substring 테스트 호환 유지.
- **F5 — C11 host schema-migration**: tidy schema_version 1.0→1.1. `organism_type{microbe,host}`(default microbe)·`interface{lumen,blood}`(nullable)·`compartment`(nullable) 컬럼. **reader migration API 확정**: writer는 **항상 v1.1** 기록; `validate(version)` 분기(1.0/1.1 schema); `read()`는 `read_legacy_or_upgrade()` 단일 경로 — v1.0 parquet 읽으면 신규 컬럼 default 주입 후 v1.1로 승격(즉시 exact-validate 실패 방지). golden **재캡처**(v1.1, 의도된 diff·결정 로그). **로직은 microbe-only 유지**(host solve는 MVP-3).

### 2.2 Out of Scope
- **실 AGORA/VMH SBML import + namespace mapping** = 별도 대형 feature.
- HiGHS LP 경로 일체 · 무라이선스(osqp) full flux(qp_only_approximate 유지).
- host-microbe solve 로직(HostModel·viability·multi-objective) = MVP-3.

## 3. Requirements

### 3.1 Functional Requirements
| ID | 요구 | P |
|----|------|:-:|
| FR-C1 | hybrid(`osqp_growth_highs_flux`) **폐기** — 9파일+fixture 정리(engine/golden_fixture/cli/solver/diagnostics/3 테스트/README/decision log) + fixture 디렉터리 삭제. `full`=gurobi LP flux 전용 | P1 |
| FR-C2 | community FVA(gurobi·processes=1) — **reaction-id(`EX_*_m`)→metabolite 매핑(`_met_from_exchange`)** 후 profile fva_lo/hi 실채움 + infeasible 진단 + fva_lo≤net≤fva_hi 불변. member `EX_*_e`는 out-of-scope | P1 |
| FR-C3 | `cmig solve --targets scfa` → target_summary.json 산출 + manifest artifacts 반영 | P0 |
| FR-C4 | engine/delta/sandbox diagnostic을 Diagnostic.to_json() 구조화(코드 enum, 다중원인=primary+detail), substring 호환 | P0 |
| FR-C5 | tidy schema v1.1(organism_type·interface·compartment nullable) — **writer 항상 v1.1**·`validate(version)` 분기·`read_legacy_or_upgrade()` 단일 경로(v1.0 default 주입 승격) | P2 |
| FR-C6 | schema v1.1 golden 재캡처(결정 로그) + v1.0 parquet 읽기 하위호환(reader 승격) | P2 |

### 3.2 Non-Functional
- 기존 175 pytest 무회귀(F5 golden 재캡처분 제외) + ruff/mypy strict 유지.
- community FVA는 3-member/synthetic 규모에서 합리적 시간(processes=1).
- gurobi-only 기능은 gurobi 미가용 시 명시적 capability 에러(§2 seam, fail-fast).

## 4. Success Criteria (단계화)
- **SC-C1 (F4, P0)**: engine/delta/sandbox diagnostic이 `{code,message,detail}` JSON(파싱 가능), 기존 테스트 green.
- **SC-C2 (F3, P0)**: `cmig solve --targets scfa`가 target_summary.json 산출(실 profile의 acetate 포함).
- **SC-C3 (F1, P1)**: `osqp_growth_highs_flux` 참조 0(코드·테스트·fixture·문서 전부); golden 변형=gurobi/osqp; `full`=gurobi 전용. 전 테스트 green.
- **SC-C4 (F2, P1)**: community FVA가 `EX_*_m`→metabolite 매핑으로 profile fva_lo/hi 실채움 AND 모든 환경 exchange에 fva_lo≤net≤fva_hi.
- **SC-C5 (F5, P2)**: schema v1.1 — writer 항상 v1.1 + **v1.0 parquet `read_legacy_or_upgrade()`로 읽힘**(default 주입) + golden v1.1 재캡처.
- **SC-C6**: 무회귀 — 전 테스트 green, ruff/mypy clean, gurobi-only 기능 capability fail-fast.

## 5. Risks and Mitigation
| 위험 | 영향 | 완화 |
|------|------|------|
| community FVA 비용/병렬 pickling 실패 | F2 성능 | processes=1 고정(probe 확인), 소규모 fixture 한정 |
| C11 schema v1.1이 기존 golden 전부 깸 | 대량 재캡처 | writer 항상 v1.1 + `read_legacy_or_upgrade()` 단일 경로로 v1.0 읽기 유지; 재캡처 범위 결정 로그 명시 |
| F1 hybrid 폐기가 9파일+fixture 표면에 흩어짐 | 누락 회귀 | FR-C1에 정리 대상 전부 열거; SC-C3="osqp_growth_highs_flux 참조 0" grep 게이트 |
| gurobi-only가 무라이선스 사용자 배제 | 접근성 | osqp 경로 qp_only_approximate 유지(정직), full은 gurobi 명시 |
| F2 reaction-id↔metabolite 매핑 누락 | 잘못된 fva 부착 | `_met_from_exchange` 재사용·EX_*_m 한정 명시(FR-C2) |
| diagnostic 구조화가 engine 다중 diag_parts와 충돌 | F4 | 다중 원인은 primary code + detail로 수용 |

## 6. Impact Analysis
### 6.1 Changed/New
- **F1 폐기(9파일+fixture)**: `core/engine.py`·`core/solver.py`·`core/diagnostics.py`·`golden_fixture.py`·`cli/main.py`·`tests/test_engine_golden.py`·`tests/test_cli_solve.py`·`tests/test_diagnostics.py`·`README.md`·`docs/decisions/2026-06-01-golden-solver-list.md` 수정 + `fixtures/community_3_member/expected/osqp_growth_highs_flux/` **삭제**.
- F2: `core/fva.py`(community_fva 헬퍼·reaction-id 매핑)·`io/solve_output` 또는 build_tidy 경로(fva_lo/hi 부착).
- F3: `cli/main.py`·`io/solve_output.py`(target_summary 산출)·`core/targets` 재사용.
- F4: `core/engine.py`·`core/delta.py`·`core/sandbox.py`(Diagnostic 통일).
- F5: `core/tidy.py`(schema v1.1·validate(version)·read_legacy_or_upgrade)·`golden_fixture.py`(v1.1 재캡처)·golden 디렉터리.
- 신규 테스트: community FVA·target CLI·diagnostic 통일·schema v1.1 legacy 읽기.
### 6.2 Consumers
- F1: hybrid golden·flux_report_status 소비자(hybrid 제거). F5: 모든 tidy 소비자(writer v1.1·reader 승격으로 하위호환).

## 7. Architecture Considerations
- Level: Dynamic 유지. 기존 headless core 위 완성.
- F1·F2: gurobi capability seam 경유(미가용 시 fail-fast). community FVA는 cobra 위임(processes=1).
- F5: schema_version 도입은 신중 — legacy reader로 기존 parquet/golden 무파손 보장.

## 8. Convention Prerequisites
- gurobi-only 기능은 capability_matrix gurobi.supports 확인 후 실행.
- diagnostic 통일은 DiagnosticCode enum(기존). schema v1.1은 default 주입 규약 문서화.

## 9. Next Steps
1. `/pdca design cmig-analysis-completion` — design checkpoint: **P0** F3/F4 그대로 · **P1** F1=hybrid 폐기 확정(설계는 정리 순서만)·F2 community FVA helper 위치(build_tidy 전/후)와 reaction-id 매핑 확정 · **P2** F5 reader migration API(read_legacy_or_upgrade·validate(version))와 golden 재캡처 범위 확정. Session Guide(P0→P1→P2).
2. `/pdca do --scope F4-diag` 등 단계 구현.
3. `/pdca analyze`(+ 신규 모듈 적대 리뷰 고려) → report.

## Version History
| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-01 | foundation carried-over 5개 완성 plan(gurobi-only, HiGHS 제거). AGORA import 분리. probe로 community FVA·LP recalc feasibility 확인. P0(F3·F4)→P1(F1·F2)→P2(F5). |
| 1.1 | 2026-06-01 | 외부 리뷰 4건 반영: (1) **F1=hybrid 폐기 확정**(plan gate, design 미루지 않음) (2) F1 migration 범위 명시(9파일+fixture 삭제·CLI choices·golden verify·README·decision log) (3) F5 reader migration API 구체화(writer 항상 v1.1·validate(version)·read_legacy_or_upgrade) (4) F2 reaction-id→metabolite 매핑(_met_from_exchange·EX_*_m 한정) 명시. SC-C3 grep 게이트 추가. |
