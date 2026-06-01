<!--
Feature: cmig-analysis-foundations
Phase: Design
Created: 2026-06-01
Architecture: Option C — Pragmatic (capability 모듈 소수 신규 + 기존 core/CLI 재사용)
Plan: docs/01-plan/features/cmig-analysis-foundations.plan.md
-->

# cmig-analysis-foundations Design Document

## Context Anchor

| 축 | 내용 |
|----|------|
| **WHY** | 분석 원자 연산은 있으나 *실행 기반*(모델수집·배지·산출·readout·정직성)이 없어 capability가 사용자에게 닿지 않음. |
| **WHO** | gut/host-microbe 대사 모델링 연구자 + 유지보수자. |
| **RISK** | C9 실 HiGHS 미구현(정직 강등으로 우회) · C5 실모델 import 대형(toy seed로 제한) · C11 host=MVP-3 범위 밖. |
| **SUCCESS** | SC-F1~F7 (Plan §4): hybrid 정직·CLI parquet 산출·medium 입력·SCFA readout·FVA 연결·S3 golden. |
| **SCOPE** | C3·C5seed·C6·C7·C8·C9 + R2/R5/R6 + S3. host MVP-3·실 AGORA·cohort out-of-scope. |

## 1. Overview
신규 알고리즘이 아니라, 검증된 원자 연산(engine·tidy·manifest·delta·sweep·fva)을 **사용자 실행 흐름**으로 잇는 capability 모듈. Option C: 초점 신규 모듈 소수 + 기존 in-place 수정. CLI는 라이브러리 경유(자체 solve 금지, [HASH-SINGLE]).

### 1.1 Module Map (Option C)
```
신규:
  cmig/core/medium_spec.py    C6 — MediumSpec(uptake_limit≥0)·로더·apply·medium_checksum
  cmig/core/targets.py        C8 — TargetMetaboliteSet(SCFA)·profile/delta target summary
  cmig/core/diagnostics.py    R5 — Diagnostic(code,message,detail) + DiagnosticCode enum
  cmig/io/solve_output.py     C7 — SolveResult/TidyBundle → parquet + manifest 산출
  medium_presets/*.yaml       C6 — diet preset seed (western/high_fiber/...)
  fixtures/pair_acetate_butyrate/  C5/S3 — synthetic GEM 2종(종명 X) + golden
in-place:
  cmig/core/engine.py         C9 — hybrid: full 금지 → qp_only_approximate + diagnostic(metadata_only_hybrid)
  cmig/cli/main.py            C7 — solve-fixture(P0) / solve(P1) subcommand (라이브러리 경유)
  cmig/core/sandbox.py        C3 — SandboxDiagnostics(no-change 시 단일-GEM FVA range)
  cmig/core/sweep.py          R5 — diagnostic 구조화 적용
  cmig/golden_fixture.py      C9 — hybrid golden config 라벨 갱신
  README.md                   R6 — 현행화
제외(별도 feature):
  cmig/core/tidy.py           C11 schema seed — validate() exact-match 파급 → schema-migration feature(§8)
```

## 2. C9 — Hybrid Solver 정직화 (SC-F1)

### 2.1 결정 (확정 — 새 enum 미도입)
- **문제**: `engine.py`가 `cooperative_tradeoff` 1회 후 hybrid일 때 `flux_solver,flux_report='highs','full'` 라벨만 부여 — 실 HiGHS LP 재계산 없음. golden osqp↔hybrid tidy_hash 바이트 동일.
- **결정 (작고 안전)**: 새 `FluxReportStatus` 값 도입 **안 함**(현재 `full | qp_only_approximate` 2값 유지 — SolveResult·FLUX_REPORT_LABEL·manifest·golden·UI label 파급 회피). 대신:
  ```
  osqp_growth_highs_flux → growth='osqp', flux=None,
                           flux_report_status='qp_only_approximate',
                           diagnostic=Diagnostic(code='metadata_only_hybrid', ...)
  ```
  즉 **`full` 금지 + qp_only_approximate 유지 + diagnostic code `metadata_only_hybrid`**로 한계 명시.
- **diagnostic**: `Diagnostic(code='metadata_only_hybrid', message="growth=OSQP-QP; flux=LP 재계산 미수행(QP-only)", detail={'growth_solver':'osqp','flux_recalc':False})`.
- **golden**: hybrid config의 flux_report_status를 `qp_only_approximate`로 갱신 + diagnostic 기록.

### 2.2 테스트 (SC-F1 — 정직성 검증)
- **성공 조건**: hybrid의 flux_report_status가 `full`이 **아님** AND diagnostic code=`metadata_only_hybrid` 존재.
- **한계 설명 guard(성공 조건 아님)**: `test_hybrid_is_not_full_despite_same_flux` — osqp↔hybrid가 동일 flux임을 *현재 한계의 증거*로 문서화(이름·docstring에 "현재 LP 재계산 부재" 명시). 동일 flux는 *버그/한계*이지 목표가 아니다.

## 3. C7 — CLI 산출 경로 (SC-F2)

### 3.1 설계 (solve-fixture → solve)
- `cmig solve-fixture --solver gurobi --tradeoff-f 0.5 --out out/`:
  - golden_fixture.solve(solver) 재사용 → io/solve_output.write(bundle, result, out/).
  - 산출: `out/{nodes,edges,profile}.parquet` + `out/manifest.json`(run_hash 11구성).
- `cmig solve --taxonomy taxonomy.csv --medium medium.yaml --solver gurobi --tradeoff-f 0.5 --out out/` (P1):
  - **medium 적용 경로 확정(단일 방식)**: `community = engine.build_community(taxonomy, cmig_solver)` (현재 시그니처 유지) → `medium_spec.apply_medium(community, spec)` → `cooperative_tradeoff` → build_tidy → io.write. (build_community 인자로 medium을 넣지 **않음** — 기존 시그니처 불변, medium은 명시적 apply 단계.)
  - 입력 검증(taxonomy 컬럼·medium 스키마·tradeoff_f 범위) fail-fast.
- **단일 경로 불변**: CLI는 engine/tidy/manifest 라이브러리만 호출 — 자체 solve/hash 금지. 산출 run_hash == 라이브러리 run_hash([HASH-SINGLE]).
- **단계화**: **P0 = solve-fixture만**(고정 입력, 성공 기준 SC-F2). **P1 = solve --taxonomy --medium**(SC-F3). 두 난이도를 분리해 P0를 먼저 통과시킨다.

### 3.2 io/solve_output.py
- `write_solve_output(bundle: TidyBundle, run_hash_components, out_dir) -> manifest_path`.
- parquet은 tidy.write_parquet 재사용; manifest는 manifest.compute_run_hash + 메타.

## 4. C6 — Medium 입력/preset (SC-F3)

### 4.1 medium_spec.py (계약 고정)
- `MediumSpec`: `{exchange_id: uptake_limit}` where **`uptake_limit >= 0`** (흡수 허용량 magnitude, 부호 없음). 음수 입력은 fail-fast.
- **변환 계약**: cobra/MICOM 적용 시 `reaction.lower_bound = -uptake_limit` (uptake 방향 = 음의 lower bound). magnitude↔bound 변환을 apply_medium 한 곳에만 둔다(혼동 방지).
- `load_medium(path)`: csv(`exchange_id,uptake_limit`) / yaml 로더 + 검증(uptake_limit<0·중복·미지 컬럼 fail-fast).
- `apply_medium(community, spec) -> dict`: community medium 설정 + 원래 bound 반환(undo). **MICOM medium 설정 경로**: `community.medium`(MICOM CommunityModel medium dict) 또는 exchange reaction bound 직접 — design 확정: `apply_medium`이 community의 medium exchange bound를 `-uptake_limit`로 설정.
- `medium_checksum(spec) -> str`: 결정적 해시(정렬·rounding) → **run_hash의 medium_checksum 구성요소(§4.2)에 주입**(FR-F5). medium 미지정 경로는 기존 default checksum 유지(하위호환).
- `medium_presets/`: western_diet.yaml·high_fiber.yaml·... (seed, 소수).

### 4.2 검증 (diet 비교 가능 입증)
- 동일 community를 medium A vs B로 apply→solve → external_profile이 달라짐 AND medium_checksum 차이 → run_hash 상이(SC-F4). preset이 sweep medium_variant 축과 연결.

## 5. C8 — SCFA Target Readout (SC-F4)

### 5.1 targets.py
- `TargetMetaboliteSet`: 이름 + metabolite id 집합. `SCFA = {acetate, propionate, butyrate, lactate, succinate}`(기본).
- `target_summary(profile, target_set) -> list[rows]`: profile에서 target만 추출(net_flux·ui_flux·label).
- `target_delta_summary(delta, target_set)`: delta.profile에서 target만(baseline·modified·delta).
- pure 함수(엔진 비의존, sign 단일진입 경유).

## 6. C3 — 단일-GEM FVA ↔ sandbox 연결 (SC-F6)

### 6.1 범위 명확화 (중요)
- **이번 scope = sandbox affected single-GEM/reaction FVA만**. `cmig/core/fva.py`는 cobra **단일 모델** FVA(`flux_variability_analysis`)이며, **MICOM community-level FVA와 직접 연결되지 않는다**.
- **community-level(MICOM) FVA는 out-of-scope** — 별도 조사 대상(MICOM이 community FVA API를 제공하는지·비용). 본 plan은 community profile fva_lo/hi를 community FVA로 채우지 **않는다**.

### 6.2 SandboxDiagnostics
- `evaluate_sandbox(..., fva: dict[str,FVARange]|None=None)`: no_significant_change=True인데 fva 제공 시 SandboxResult에 affected reaction의 (단일-GEM) FVA range 동반.
- `SandboxResult.fva_ranges: dict|None` 추가 — no-change일 때 "허용 변동 범위" 제공(R4). fva는 호출자가 단일-GEM FVA로 산출해 주입(opt-in).

## 7. C5/S3 — Synthetic Cross-feeding Golden (SC-F7)

### 7.1 fixtures/pair_acetate_butyrate/ (synthetic)
- **synthetic toy GEM 2종(종명 미부여, 라이선스-clean)**: `synthetic_acetate_producer`(glucose→acetate 분비), `synthetic_butyrate_consumer`(acetate 흡수→butyrate 분비). **실제 AGORA/VMH 모델이 아님** — "문헌의 대표 acetate→butyrate cross-feeding 관계를 모사한 **정성 검증용 synthetic fixture**".
- community solve → 검증: (a) acetate cross_feeding edge producer→consumer 존재, (b) consumer butyrate secretion>0, (c) sign 규약(+분비/−흡수), (d) external profile에 acetate·butyrate.
- golden: nodes/edges/profile 고정(gurobi hash-exact). **S3 정성 검증** = sign/cross-feeding 과학적 의미 확보(정량 주장 아님).

## 8. C11 seed — 별도 feature로 분리 (FR-F11)
- **본 Do에서 코드 반영 제외**. 이유: `TidyBundle.validate()`가 컬럼 **exact match** → nullable 컬럼 추가만으로 기존 golden/parquet이 **깨진다**(자동 하위호환 아님).
- 본 plan 산출 = **설계 노트만**: host 확장 시 `organism_type{microbe,host}`·`interface{lumen,blood}`·`compartment` 컬럼을 **schema_version bump + legacy read adapter + golden 재캡처**와 함께 도입하는 별도 **schema-migration feature**로 처리(아래 §8.1).

### 8.1 schema-migration 설계 노트 (후속 feature 인계)
- 전략: schema_version `1.0→1.1` bump → `validate()`에 version 분기(legacy 1.0 reader = 신규 컬럼 default 주입) → golden 재캡처(decision 로그). organism_type default='microbe', interface/compartment nullable.

## 9. R5 — Diagnostic 구조화 (FR-F9)
- `Diagnostic(code: DiagnosticCode, message: str, detail: dict|None)` → canonical JSON 문자열.
- `DiagnosticCode` enum: infeasible·solver_error·capability_missing·gate_blocked·metadata_only_hybrid·members_missing.
- sweep/solve/sandbox의 자유 문자열 diagnostic → Diagnostic.to_json()으로 통일. 비유한/NaN allow_nan=False(I-6 일관).

## 10. Test Plan
| Level | capability | 테스트 | SC | P |
|-------|:----------:|--------|-----|:-:|
| L1 | C9 | hybrid flux_report ≠ full + diagnostic=metadata_only_hybrid; guard: not-full-despite-same-flux | SC-F1 | P0 |
| L2 | C7 | solve-fixture parquet+manifest·run_hash==라이브러리 | SC-F2 | P0 |
| L3 | C7 | solve --taxonomy --medium 입력 검증·산출 | SC-F3 | P1 |
| L4 | C6 | medium A vs B → external_profile 상이 + medium_checksum→run_hash 상이 | SC-F4 | P1 |
| L5 | C8 | SCFA target summary(profile·delta) | SC-F5 | P1 |
| L6 | C3 | sandbox no-change + **단일-GEM** FVA range 동반 | SC-F6 | P2 |
| L7 | C5/S3 | synthetic producer/consumer golden(cross-feeding·butyrate·sign) | SC-F7 | P2 |
| L8 | R5 | Diagnostic JSON 구조화(allow_nan=False) | SC-F8 | P0 |
| L-reg | all | 기존 129 무회귀 + ruff/mypy + tidy schema 미변경 확인 | SC-F8 | all |

## 11. Implementation Guide

### 11.3 Session Guide (`/pdca do --scope`)
| scope key | P | 산출물 | SC |
|-----------|:-:|--------|-----|
| `C9-honesty` | P0 | engine.py hybrid→qp_only_approximate+diagnostic + golden config 라벨 + 정직성 테스트(not-full) | SC-F1 |
| `C7-cli` | P0 | io/solve_output.py + cli solve-fixture + 산출 테스트(run_hash==lib) | SC-F2 |
| `R5-diag` | P0 | core/diagnostics.py(Diagnostic·DiagnosticCode) + sweep/sandbox 적용 + README(R6)·golden 결정 로그(R2) | SC-F8 |
| `C6-medium` | P1 | core/medium_spec.py(uptake_limit≥0·apply·checksum→run_hash) + medium_presets/ + cli solve --taxonomy --medium | SC-F3·F4 |
| `C8-targets` | P1 | core/targets.py + SCFA summary 테스트 | SC-F5 |
| `C3-fva` | P2 | sandbox SandboxDiagnostics(단일-GEM FVA) + 테스트 | SC-F6 |
| `C5-s3` | P2 | fixtures/pair_acetate_butyrate(synthetic GEM) + golden 테스트 | SC-F7 |

권장 순서: **P0(C9 → C7 → R5-diag) → P1(C6 → C8) → P2(C3 → C5)**. C11 schema seed는 본 feature 밖(별도 schema-migration, §8).

### 11.4 Conventions
- CLI는 라이브러리 경유(자체 solve/hash 금지). run_hash 단일 canonical.
- **tidy schema 미변경**(C11 seed 코드 제외). Diagnostic allow_nan=False.
- MediumSpec: uptake_limit≥0, bound 변환은 apply_medium 한 곳. synthetic GEM/preset 라이선스·종명 미부여 주석.

## 12. 확정 결정 (Do 전 — 리뷰 피드백 반영)
1. **hybrid**: 새 FluxReportStatus enum **미도입** → `qp_only_approximate` 유지 + diagnostic code `metadata_only_hybrid`. (§2)
2. **tidy schema seed(C11)**: 본 Do **코드 반영 제외** → 별도 schema-migration feature(설계 노트 §8.1만). 따라서 **기존 golden 재캡처 불요**(tidy 미변경).
3. **toy pair**: **synthetic** 명명(synthetic_acetate_producer/consumer), 종명 미부여. (§7)
4. **FVA**: 단일-GEM/sandbox만, community-level FVA 후속. (§6.1)
5. **medium 적용**: build_community 시그니처 불변 + 명시적 `apply_medium` 단계. medium_checksum→run_hash. (§3·§4)
6. **CLI 단계화**: P0 solve-fixture / P1 solve. (§3)

## 13. Risks
- C9 diagnostic 누락 회귀 → 정직성 테스트로 고정. 실 HiGHS 재계산은 후속 feature.
- synthetic GEM이 정량 해석으로 오용 → docstring·fixture README에 "정성 검증용" 명시.
- medium_checksum 도입이 기존 run_hash 회귀 → medium 미지정 경로 default checksum로 하위호환.

## 14. Next Steps
1. `/pdca do cmig-analysis-foundations --scope C9-honesty` (P0 정직성 먼저)
2. → C7-cli → R5-diag (P0) → C6-medium → C8-targets (P1) → C3-fva → C5-s3 (P2)
3. `/pdca analyze` → report.

## Version History
| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-01 | Option C(Pragmatic). capability 모듈 설계 + Session Guide(7 scope) + Test Plan. |
| 1.1 | 2026-06-01 | 리뷰 피드백 반영(8건): hybrid=qp_only_approximate+diagnostic(새 enum X)·정직성 guard(동일 flux=한계 설명)·build_community 시그니처 불변+apply_medium·MediumSpec uptake_limit≥0·단일-GEM FVA만·synthetic 명명·C11 코드 반영 제외(별도 schema-migration)·확정 결정 §12. P0~P2 단계화. |
