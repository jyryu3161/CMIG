# cmig-analysis-foundations — Check (Gap Analysis)

> 외부 리뷰(REVIEW/)가 지적한 capability 격차를 닫는 foundation cycle의 Check.
> 7개 scope(C9·C7·R5·C6·C8·C3·C5)를 SC-F1~F8 기준으로 평가한다.

## Context Anchor
| 축 | 내용 |
|----|------|
| WHY | 분석 원자 연산은 있으나 실행 기반(모델수집·배지·산출·readout·정직성)이 없어 capability가 사용자에게 닿지 않음. |
| SUCCESS | SC-F1~F8 — hybrid 정직·CLI 산출·medium 입력·SCFA·단일-GEM FVA·synthetic cross-feeding. |

## 1. Success Criteria (SC-F1~F8)
| SC | 기준 | P | 상태 | 근거 |
|----|------|:-:|:----:|------|
| SC-F1 | hybrid `full` 미표기 + diagnostic | P0 | ✅ Met | engine 분기·test_hybrid_not_full_with_diagnostic. golden hybrid run_hash==osqp(정직) |
| SC-F2 | solve-fixture parquet+manifest, run_hash==lib | P0 | ✅ Met | test_cli_solve.py — [HASH-SINGLE] |
| SC-F3 | solve --taxonomy --medium 산출 | P1 | ✅ Met | test_cli_solve_medium.py |
| SC-F4 | medium A vs B → profile·run_hash 상이 | P1 | ✅ Met | medium_checksum→run_hash; default 0.437 vs western 0.895 |
| SC-F5 | SCFA target summary | P1 | ✅ Met | targets.py + 실 profile acetate 추출 |
| SC-F6 | sandbox no-change 단일-GEM FVA | P2 | ✅ Met | SandboxResult.fva_ranges + 실 textbook FVA 통합 |
| SC-F7 | synthetic cross-feeding golden | P2 | ✅ Met | producer→consumer ac cross_feeding + butyrate secretion + hash-exact |
| SC-F8 | 무회귀 + R5/R6/R2 | all | ✅ Met | 168 pytest, ruff/mypy clean(30), README 현행화, golden 결정 로그 |

**SC-F 8/8 Met (100%).**

## 2. 외부 리뷰 항목 해소 매트릭스
| 리뷰 항목 | 이전 | 현재 |
|-----------|------|------|
| R1/U1 hybrid 거짓 `full` | 미해결 | ✅ C9 — qp_only_approximate + diagnostic metadata_only_hybrid |
| R3/U2 CLI solve stub | 미해결 | ✅ C7 — solve-fixture + solve --taxonomy --medium |
| R5/U5 자유문자열 diagnostic | 부분 | ✅ R5 — Diagnostic{code,message,detail} (sweep 적용) |
| R6 README 불일치 | 미해결 | ✅ R6 — 현행화 + hybrid caveat |
| R2 golden solver 목록 | 미해결 | ✅ R2 — docs/decisions 공식 결정(Accepted) |
| R4 sandbox FVA 미연결 | 부분 | ✅ C3 — 단일-GEM FVA 동반(SandboxResult.fva_ranges) |
| U3 host-microbe 간극 | — | ⏸ C11 schema seed = 별도 schema-migration feature(의도적 분리) |
| S1~S4 microbe 시나리오 기반 | 부재 | ✅ medium 입력·SCFA·delta·cross-feeding fixture로 분석 기반 확보 |

## 3. Layer 점수
| Layer | Score | 근거 |
|-------|:-----:|------|
| Structural | 100% | 계획 산출물 전부 존재(신규 5 모듈·presets·fixtures·decisions doc) |
| Functional | 99% | 7 capability 전부 end-to-end 동작(실 MICOM·cobra·CLI). 잔여 후속(community FVA·실 AGORA)은 out-of-scope |
| Contract | 98% | run_hash [HASH-SINGLE]·diagnostic 구조화·medium_checksum 반영. C11 deferred=문서화 결정(gap 아님) |
| Runtime | 100% | 168 pytest green(실 MICOM·cobra FVA·CLI·synthetic community), ruff/mypy clean |

**Match Rate = 100×0.15 + 99×0.25 + 98×0.25 + 100×0.35 = 99.25%** (runtime 실행 공식).

## 4. 정직한 방법론 노트 (cycle #2 교훈 적용)
- **신규 모듈(medium_spec·targets·diagnostics·solve_output·synthetic_pair·CLI solve)은 per-slice Check + 표적 테스트만 받았다 — 전용 적대적 cross-module 리뷰는 미수행.** cycle #2의 교훈("per-slice Check가 cross-module 계약 위반을 놓침")이 여기에도 적용 가능 — 잠재 계약 결함이 있을 수 있다(선택적 후속: 적대 리뷰 확장).
- 외부 리뷰 피드백 16건을 plan/design에 반영 후 구현했으므로 *상위 설계 결함*은 사전 차단됨. 다만 *구현 레벨* cross-module 검증은 적대 패스 미수행.

## 5. 잔여 (out-of-scope / 후속, gap 아님)
- 실 HiGHS LP pFBA 재계산(hybrid) · 실 AGORA/VMH 모델 import · C11 host schema seed(schema-migration feature) · community-level FVA · CLI --targets · sandbox/delta diagnostic 전면 구조화.

## 5.1 신규 모듈 적대적 리뷰 (Checkpoint 5 선택 — 실행됨)
**Workflow 16 agents · 1.19M tokens — 10 raised → 5 confirmed(전부 Minor) · 5 rejected.** **Critical·Important 0** (설계단계 피드백 16건이 고severity 차단). 최고위험(solve_output run_hash [HASH-SINGLE] 단일-canonical) **반증됨** — run_hash 경로 정직성 확인.

| # | 모듈 | id | 위치 | 결함(Minor) |
|---|------|----|----|------|
| AF-1 | solve_output | F1 | :88 | manifest `artifacts` 하드코딩 → bundle.matrix 산출 시 누락(현재 latent: matrix 산출 경로 0개) |
| AF-2 | medium_spec | MS-1 | :46 | JSON 경로가 중복 exchange_id fail-fast 안 함(CSV는 함, 비대칭) |
| AF-3 | medium_spec | MS-4 | :46 | bool→float silent 강제(float(True)=1.0, 형 검증 우회) |
| AF-4 | targets | F1 | :29 | SCFA preset에 `for`(formate) 포함 — 문서화된 5종 set 초과(미승인) |
| AF-5 | cli/main | F1 | :76 | solve가 taxonomy 컬럼 검증 없이 solve(입력 fail-fast 계약 미흡) |

**Rejected(5, 오탐)**: SP-1(synthetic [HASH-SINGLE] 위반=반증), apply_medium 미지키 silent(설계 명시 동작), targets KeyError 등.

### 5.2 Act — Minor 5 전부 수정 (2026-06-01)
Checkpoint 5에서 "5건 모두 수정" 선택. 7 회귀 테스트 추가(175 pytest, ruff/mypy clean).
| AF | 조치 |
|----|------|
| AF-1 | solve_output artifacts를 bundle 산출에서 파생(matrix 있으면 포함) |
| AF-2 | medium JSON object_pairs_hook로 중복 키 fail-fast(CSV와 대칭) |
| AF-3 | bool→float silent 강제 차단(isinstance bool → ValueError) |
| AF-4 | SCFA에서 formate('for') 제거 — 문서화된 5종과 정확히 일치 |
| AF-5 | cli solve가 taxonomy 필수 컬럼(id·file) 검증 후 solve(fail-fast) |

**Re-Check 후**: Critical·Important·Minor 잔존 0(발굴분 전부 수정). Match Rate 99.25 유지(Minor는 match에 미반영, 수정으로 품질↑). 175 pytest.

## 6. 결론 (Check)
- **SC-F 8/8 Met · Match 99.25% · Critical·Important 0.**
- 외부 리뷰의 capability 격차(R1~R6·U1~U5) 해소: hybrid 정직화·CLI 산출·diagnostic 구조화·medium 입력·SCFA·FVA·synthetic cross-feeding.
- 정직성: C11 host는 의도적 분리, hybrid 실 재계산은 후속, 신규 모듈 적대 리뷰는 미수행(선택적).
- **Checkpoint 5: Critical·Important 0 → report 권장**(또는 신규 모듈 적대 리뷰 확장 선택).

## Version History
| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-01 | Check: SC-F 8/8 Met, Match 99.25%, Critical·Important 0. 외부 리뷰 해소 매트릭스 + 방법론 노트(신규 모듈 적대 리뷰 미수행). |
