<!--
Feature: cmig-analysis-completion
Phase: Design
Created: 2026-06-01
Architecture: Option C — Pragmatic (기존 headless core 위 localized 완성)
Plan: docs/01-plan/features/cmig-analysis-completion.plan.md
Constraint: HiGHS 제거, gurobi-only
-->

# cmig-analysis-completion Design Document

## Context Anchor

| 축 | 내용 |
|----|------|
| **WHY** | foundation의 정직한 미완 항목을 gurobi로 실제 완성 — 지표가 아니라 동작으로. |
| **WHO** | gurobi 보유 연구자(full flux·community FVA) + 유지보수자(diagnostic·schema). |
| **RISK** | community FVA 비용(processes=1) · F1 폐기 9파일+fixture 누락(SC-C3 grep 게이트) · F5 golden 재캡처(reader 승격). |
| **SUCCESS** | SC-C1~C6 (Plan §4). diagnostic JSON·CLI targets·hybrid 참조 0·community FVA fva_lo/hi·schema v1.1 하위호환. |
| **SCOPE** | gurobi-only 5개(F1~F5). out: 실 AGORA import·HiGHS·host solve·member EX_*_e FVA. |

## 1. Overview
완성 cycle. 신규 아키텍처 없음 — 기존 core/CLI 위 localized 변경 + 1개 폐기(F1). gurobi capability seam 경유(미가용 fail-fast). 단계: **P0**(F3·F4 저위험) → **P1**(F1 폐기·F2 community FVA) → **P2**(F5 schema v1.1).

### 1.1 Module Map (Option C)
```
in-place 수정:
  core/fva.py            F2 — community_fva(community, gurobi, processes=1) + EX_*_m→metabolite 매핑
  core/tidy.py           F5 — SCHEMA_VERSION 1.1·v1.0/v1.1 스키마·validate(version)·read_legacy_or_upgrade
  core/engine.py         F1 폐기(hybrid 분기·METADATA_ONLY_HYBRID 제거) + F4(Diagnostic) + F2(fva 부착 hook)
  core/delta.py          F4 — diagnostic → Diagnostic.to_json()
  core/sandbox.py        F4 — diagnostic → Diagnostic.to_json()
  core/solver.py         F1 — hybrid 잔재 정리
  cli/main.py            F3 — solve [--targets scfa] + F1(--solver choices에서 hybrid 제거)
  io/solve_output.py     F3 — target_summary.json 산출 + artifacts
  golden_fixture.py      F1(SOLVER_VARIANTS) + F5(v1.1 재캡처)
  README.md              F1 caveat 제거
  docs/decisions/2026-06-01-golden-solver-list.md  F1 golden 목록=gurobi/osqp
삭제:
  fixtures/community_3_member/expected/osqp_growth_highs_flux/   F1
테스트:
  test_engine_golden·test_cli_solve·test_diagnostics  F1 hybrid 케이스 제거/갱신
  신규: test_community_fva·test_cli_targets·test_diagnostic_unified·test_schema_migration
```

## 2. F1 — Hybrid 폐기 (P1, 확정)

### 2.1 폐기 순서 (누락 방지 — grep 게이트)
1. `core/engine.py`: `if cmig_solver == "osqp_growth_highs_flux"` 분기 제거 → osqp/gurobi 2분기만. `METADATA_ONLY_HYBRID` 상수 제거.
2. `golden_fixture.py`: `SOLVER_VARIANTS = ("gurobi", "osqp")`. VARIANT_DECIMALS에서 hybrid 제거.
3. `fixtures/community_3_member/expected/osqp_growth_highs_flux/` 디렉터리 삭제.
4. `cli/main.py`: `solve`·`solve-fixture` `--solver` choices = `["gurobi","osqp"]`.
5. `core/solver.py`: hybrid 관련 주석/매핑 정리(SOLVER_MAP은 engine 소관).
6. `core/diagnostics.py`: `DiagnosticCode.METADATA_ONLY_HYBRID` 제거(사용처 0 확인 후).
7. 테스트: `test_engine_golden`(hybrid parametrize·`test_hybrid_not_full_with_diagnostic`·`test_hybrid_is_not_full_despite_same_flux`·`test_osqp_to_lp_matches_gurobi_profile`)·`test_cli_solve`(choices)·`test_diagnostics`(metadata_only_hybrid) 제거/갱신.
8. `README.md` hybrid caveat 제거; `docs/decisions/2026-06-01-golden-solver-list.md`: golden 변형 = gurobi/osqp(hybrid 폐기 결정 append).
9. **게이트**: `grep -rn osqp_growth_highs_flux cmig/ tests/ fixtures/ docs/ README.md` → **0건**(SC-C3).

### 2.2 결과
`full`은 gurobi LP flux 전용(이미 동작). osqp=qp_only_approximate(무라이선스 정직). `osqp_growth_gurobi_flux`(OSQP-growth→gurobi-LP recalc)는 **본 cycle 밖**(필요 시 후속 experimental).

## 3. F2 — Community-level FVA (P1, gurobi)

### 3.1 community_fva (core/fva.py)
- `community_fva(community, *, reactions=None, fraction_of_optimum=1.0, solver="gurobi") -> dict[str, FVARange]`:
  - gurobi LP capability seam 확인(fail-fast). `community.solver = "gurobi"`.
  - `cobra.flux_analysis.flux_variability_analysis(community, reaction_list=..., fraction_of_optimum=..., processes=1)` — **processes=1 고정**(병렬 worker pickling 실패 회피, probe 확인).
  - 기존 `flux_variability`(단일-GEM)와 분리된 함수. 반환은 동일 `FVARange`(lo≤hi 보장).
- **reactions 기본**: community의 `EX_*_m`(환경 exchange) 전체.

### 3.2 EX_*_m → metabolite 매핑 + profile 부착
- 매핑: `_met_from_exchange(reaction_id, "_m")` 재사용(engine의 external profile 추출과 동일 규약) → `EX_ac_m → ac`.
- `attach_community_fva_to_profile(profile_rows, community_fva) -> rows`: reaction FVA를 metabolite로 매핑 후 profile `fva_lo/fva_hi` 채움(매칭 없으면 None). **member `EX_*_e`는 out-of-scope**.
- 부착 위치: **build_tidy 이후 opt-in 헬퍼**(profile 생성 자체는 불변; FVA는 비용↑이므로 명시 호출). CLI/solve에서 `--fva` 옵션 시 community_fva 산출→부착(P1 wiring은 헬퍼+테스트까지, CLI --fva 노출은 선택).

### 3.3 불변식
모든 환경 exchange에 `fva_lo ≤ net_flux ≤ fva_hi`(테스트 단언, SC-C4).

## 4. F3 — CLI --targets (P0)
- `cmig solve [--targets scfa]`·`solve-fixture [--targets scfa]`: `--targets` 지정 시 `core.targets.TARGET_PRESETS[name]`로 `target_summary(profile)` → `out/target_summary.json` 산출.
- `io/solve_output.write_solve_output(..., targets=None)`: targets 제공 시 target_summary.json 기록 + manifest `artifacts`에 추가(AF-1 파생 일관).
- 미지 preset → fail-fast(에러 + rc=2).

## 5. F4 — Diagnostic 전면 구조화 (P0)
- `core/engine.py`: diag_parts(자유문자열 다중) → **primary DiagnosticCode + detail**. 우선순위: infeasible > members_missing. `Diagnostic(code, message, detail={...}).to_json()`. (hybrid 코드는 F1로 제거됨.)
- `core/delta.py`: `_solve_diag` 결과를 `Diagnostic(code=...,...)`로. status='failed' 시 JSON.
- `core/sandbox.py`: constrained 실패 diagnostic을 Diagnostic.to_json()으로.
- **호환**: JSON 문자열이 기존 substring 단언("infeasible" 등) 포함 → 기존 테스트 green. `parse_diagnostic`로 구조 접근.

## 6. F5 — Schema v1.1 Migration (P2)

### 6.1 tidy.py 스키마 버저닝
- `TIDY_SCHEMA_VERSION = "1.1"`. v1.1 = v1.0 + nullable 컬럼 `organism_type`(string, default "microbe")·`interface`(string, nullable)·`compartment`(string, nullable). nodes·profile에 추가(edges는 불변 또는 동일 규약).
- **writer 항상 v1.1**: build_tidy/write는 v1.1 컬럼 포함(organism_type="microbe"·interface=None·compartment=None 기본).
- `validate(table, schema, name, *, version="1.1")`: version별 스키마로 검증. legacy 1.0 검증도 지원.

### 6.2 reader migration (단일 경로)
- `read_legacy_or_upgrade(table) -> table`: 읽은 parquet의 schema_version 확인 → 1.0이면 신규 컬럼 default 주입 후 v1.1로 승격 → v1.1 validate. 1.1이면 그대로.
- `TidyBundle.read()`가 즉시 exact-validate하던 것을 `read_legacy_or_upgrade` 경유로 변경(v1.0 parquet 무파손).

### 6.3 golden 재캡처
- 기존 golden(gurobi/osqp, v1.0)을 v1.1로 재캡처(신규 컬럼 default) — 결정 로그(`docs/decisions/`). 또는 reader 승격으로 v1.0 golden을 읽되 hash는 v1.1 기준 재계산. **설계 확정: golden v1.1 재캡처**(단순·명확). pair_acetate_butyrate golden도 v1.1 재캡처.

### 6.4 로직 불변
organism_type은 항상 "microbe"(host solve 미구현, MVP-3). 컬럼은 *확장 자리*.

## 7. Test Plan
| Level | F | 테스트 | SC |
|-------|:-:|--------|-----|
| L1 | F4 | engine/delta/sandbox diagnostic JSON 구조 + substring 호환 | SC-C1 |
| L2 | F3 | solve --targets scfa → target_summary.json(acetate 포함)·미지 preset fail | SC-C2 |
| L3 | F1 | grep "osqp_growth_highs_flux" 0건·golden 변형 gurobi/osqp·full=gurobi | SC-C3 |
| L4 | F2 | community FVA EX_*_m→metabolite·fva_lo≤net≤fva_hi·profile 부착 | SC-C4 |
| L5 | F5 | v1.1 writer·v1.0 parquet read_legacy_or_upgrade 승격·golden v1.1 | SC-C5 |
| L-reg | all | 무회귀(F1·F5 갱신분 제외) + ruff/mypy | SC-C6 |

## 8. Implementation Guide

### 8.3 Session Guide (`/pdca do --scope`)
| scope key | P | 산출물 | SC |
|-----------|:-:|--------|-----|
| `F4-diag` | P0 | engine/delta/sandbox Diagnostic 통일 + 테스트 | SC-C1 |
| `F3-targets` | P0 | cli --targets + io target_summary + 테스트 | SC-C2 |
| `F1-deprecate` | P1 | hybrid 9파일+fixture 정리 + grep 게이트 + golden/decision/README | SC-C3 |
| `F2-community-fva` | P1 | core/fva community_fva + EX_*_m 매핑 + attach + 테스트 | SC-C4 |
| `F5-schema-v11` | P2 | tidy schema v1.1 + read_legacy_or_upgrade + golden 재캡처 + 테스트 | SC-C5 |

권장 순서: **P0(F4 → F3) → P1(F1 → F2) → P2(F5)**. F1을 F2 앞에 두어 solver 표면을 먼저 단순화.

### 8.4 Conventions
- gurobi-only 기능은 capability seam 확인 후 실행(fail-fast). community FVA processes=1.
- diagnostic은 DiagnosticCode + Diagnostic.to_json(). schema writer 항상 v1.1·reader 승격.

## 9. Risks
Plan §5 동일. 추가: F5 golden 재캡처가 cycle #3 synthetic pair golden도 포함 → 재캡처 목록에 명시(누락 방지).

## 10. Next Steps
1. `/pdca do cmig-analysis-completion --scope F4-diag` (P0)
2. → F3-targets → F1-deprecate → F2-community-fva → F5-schema-v11
3. `/pdca analyze`(+신규 모듈 적대 리뷰) → report.

## Version History
| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-01 | Option C(Pragmatic). F1 폐기 순서(grep 게이트)·F2 community_fva(processes=1·EX_*_m 매핑)·F3 CLI --targets·F4 diagnostic 통일·F5 schema v1.1(writer 항상 v1.1·read_legacy_or_upgrade·golden v1.1 재캡처) + Session Guide(P0→P1→P2). |
