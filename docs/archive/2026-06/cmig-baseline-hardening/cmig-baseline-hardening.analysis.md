# cmig-baseline-hardening — Check (Gap Analysis)

> 하드닝 사이클의 Check 산출물. Track-A/B 는 검증 통과(증거 생성), Track-C 는 적대적 리뷰로
> per-slice Check 가 놓친 결함을 발굴한다. baseline 의 교훈("적대적 정밀도를 받은 모듈만 그
> 정밀도로 검증됨")을 직접 적용 — 미검토 6모듈에 동급 리뷰를 수행했다.

## Context Anchor
| 축 | 내용 |
|----|------|
| WHY | 98.25% 가 가린 정직성 격차를 동작·증거로 전환. |
| SUCCESS | SC-H1(GUI exec)·SC-H2(E2E)·SC-H3(미검토 모듈 0 Critical/Important 잔존)·SC-H4(Minor+FVA+robustness). |

## 1. Track-A / Track-B 결과 (증거 생성, 통과)
| Track | 산출 | 게이트 |
|-------|------|--------|
| A | GUI offscreen 실행 검증(G-7 해소): DOM count·gate DOM·grab·GateBadge. cytoscape CDN→로컬 번들. | 100 pytest, SC-H1 ✅ |
| B | E2E 6-hop 계약 매트릭스(실 solve→tidy→graph→R→GUI), 부호 100% 일관. | 106 pytest, SC-H2 ✅ |

## 2. Track-C — 적대적 리뷰 (미검토 6모듈)

**워크플로**: 3차원(correctness·contract·quality) 리뷰 × 6모듈 → refute-first 적대 검증.
**29 agents · 2.06M tokens · 23 raised → 18 confirmed (10 Important · 8 Minor) · 5 rejected(오탐).**
**Critical 0** — baseline Act #2 가 engine/sweep 핵심 계약을 이미 고정한 효과.

### 2.1 Confirmed Gaps (18)

**🟠 Important (10)**

| # | 모듈 | id | 위치 | 결함 |
|---|------|----|----|------|
| TC-1 | sandbox | infeasible-masked-as-no-significant-change | sandbox.py:83-84 | constrained 재solve infeasible(status/NaN)를 미검사 → `no_significant_change=True` 로 **실패를 '변화 없음'으로 위장**(fail-explicit 위반, design E-1/ERR-NO-SILENT) |
| TC-2 | sweep | axes-single-json-column-vs-schema-6-1 | sweep.py:27-37,150 | 6축을 단일 `axes` JSON 컬럼으로 collapse → schema §6.1 6개 타입 컬럼(axis_tradeoff_f float64 포함)·Resolved OD-30 위반 |
| TC-3 | sweep | axes-noncanonical-serialization-nan-float | sweep.py:150 | `axes` 직렬화가 allow_nan/float 반올림(A17) 없음 → NaN/inf 가 비표준 JSON·비결정 hash(I-6 class) |
| TC-4 | delta | delta-drops-status-diagnostic | delta.py:54-59 | baseline/modified status·diagnostic 무시·미전파 → 실패 solve 를 정상 delta 와 구분 불가 |
| TC-5 | delta | delta-nan-growth-silent | delta.py:58 | objective NaN(infeasible) → growth_delta=NaN 무진단 산출(silent NaN, §4.4) |
| TC-6 | delta | significant-nan-filtered-out | delta.py:38 | `abs(delta)>threshold` 가 NaN→False → NaN delta **조용히 누락** → sandbox no_change 오판(TC-1 근원) |
| TC-7 | client | csv-nondeterministic-float-nan | client.py:116-121 | `_write_csv` float 반올림·NaN/inf 가드 없음 → R read.csv 가 'nan' 오파싱, 정렬·부호색 비결정 |
| TC-8 | medium | infeasible-vs-capability-conflation | medium.py:60-63 | minimal_medium None→infeasible 와 MILP capability 부재를 하나의 에러로 묶음(§4.4 vs §2 별개 개념) |
| TC-9 | medium | solver-seam-bypass | medium.py:50-56 | canonical solver seam(capability_matrix/get_backend) 우회·inline model.solver 직접 설정 → capability gate 미경유(I-5 class) |
| TC-10 | medium | min-medium-invariants-missing | medium.py:41-70 | [MIN-MEDIUM-U]/§4.5 invariant(U 기본 {H₂O,H⁺,Pi}·oxygen_mode·blocked 제외·결정적 tie-break) **전혀 미반영** |

**🟡 Minor (8)**

| # | 모듈 | id | 위치 | 결함 |
|---|------|----|----|------|
| TC-11 | sandbox | commit-without-store-claims-success | sandbox.py:89-94 | store=None+COMMITTED → record_run skip 하면서 committed=True(비기록 commit 미구분, [RUNHASH-COMMIT]) |
| TC-12 | sweep | cache-hit-extra-column-not-in-contract | sweep.py:36,156 | `cache_hit` 컬럼이 §6.1 컬럼셋·AN-SWEEP 튜플에 없음(view 관심사를 store 에 영속) |
| TC-13 | client | fallback-netflux-or-zero-silent-drop | client.py:102,104 | fallback `net_flux or 0.0` → null(failed)을 0.0 으로 강등(가짜 0 막대, fail-explicit) |
| TC-14 | client | sidecar-json-allow-nan | client.py:72-74 | figure_spec sidecar json.dumps allow_nan=True → NaN/inf 주입 시 비표준·비결정(§9 재현) |
| TC-15 | medium | solver-set-swallowed | medium.py:53-56 | bare except 로 solver 설정 실패 삼킴 → 요청과 다른 solver 로 MILP, 무진단(메타 오염) |
| TC-16 | metrics | inline-sign-classification-bypass | metrics.py:30,37,85-90 | uptake/secretion/_sign inline 재구현 → sign.classify 단일진입 우회(§5.1, 분류 drift) |
| TC-17 | metrics | sign-eps-default-drift | metrics.py:27,34,94 | eps 기본 1e-6 이 sign.convert(0.0)과 독립 하드코딩 → noise floor drift surface |
| TC-18 | metrics | amensalism-enum-casing | metrics.py:80 | `AMENSalism` 혼합 케이싱(다른 멤버 UPPER 관례 위반, value 는 정상) |

### 2.2 Rejected (5, 오탐) — 적대 검증이 걸러냄
- `commit-no-status-gate` (코드 사실은 맞으나 인용 계약 위반 아님), `growth-and-memberset-delta-ignored`(계약 준수 동작), `fallback-sign-bypass-inline`(색상 drift 반증), `fallback-format-svg-savefig`(계약 미뒷받침), `min-growth-passthrough-no-validation`(영향근거 반증).

### 2.3 교차 테마 (근본 패턴)
1. **fail-explicit 위반 (silent NaN/infeasible)**: TC-1·4·5·6·13·15 — infeasible/실패가 진단 없이 정상 산출로 위장. *가장 과학적으로 위험* — 성장 불가 커뮤니티가 '변화 없음'·가짜 0 으로 결론 반전.
2. **비-canonical 직렬화 (I-6 class)**: TC-3·7·14 — allow_nan/float 반올림 누락 → 재현성·결정성 훼손.
3. **계약 형상 위반 (C-3 class)**: TC-2·12 — sweep parquet schema §6.1 불일치.
4. **단일진입점 우회 (I-5 class)**: TC-9·16 — solver seam·sign 우회.
5. **누락 invariant**: TC-10 — minimal medium 사양 거동 통째 미구현(가장 큰 기능 격차).

## 3. Track-C 수정 (Checkpoint 5: Important 9 수정, TC-10→Track-D, Minor 8 defer)
Important 9건(TC-1~9) 수정 + `tests/test_review_regressions.py` 9 회귀. 근본 테마=**fail-explicit**.
- TC-1 sandbox infeasible→status=failed·no_change=False · TC-2/3 sweep 6 per-axis 컬럼+canonical float
- TC-4/5/6 delta status 전파·NaN 미위장 · TC-7 client CSV NaN→NA · TC-8/9 medium infeasible↔capability 분리+solver seam gate.

## 4. Track-D — D-full (TC-10 + FVA + 과학 Minor + robustness)
| 항목 | 산출 | 검증 |
|------|------|------|
| **TC-10** | medium [MIN-MEDIUM-U]: U 기본 {H₂O,H⁺,Pi} 항상 포함·oxygen_mode(O₂)·blocked 제외·결정적 tie-break | 3 tests (e_coli_core) |
| **G-3 FVA** | `cmig/core/fva.py` 신규 — cobra `flux_variability_analysis` 위임, fva_lo≤net≤fva_hi 불변, fraction 검증, infeasible↔unavailable 분리, fva_lo/hi 실채움 | 6 tests |
| **TC-16/17** | metrics sign.classify 단일진입 경유 + `NOISE_FLOOR` 공유(eps drift 제거) | — |
| **sign eps** | `convert`/`cross_feeding_weight` 기본 0.0→`NOISE_FLOOR`(1e-6) — 0근방 flux 오분류 방지(과학적 정정) | golden 미파손(near-zero 부재) |
| **robustness** | 4-member community 불변식 + infeasible 파이프라인 통과(silent 금지) + edge-media sign 경계 | 5 tests |

**golden 정직성**: sign eps 변경이 기존 3-member golden 을 깨지 않음(해당 fixture 에 |flux|<1e-6 항목 없음 → 정정 적용·재캡처 불요). 2nd community 는 captured-golden 대신 **불변식 검증**(OD-47 교훈: OSQP cross-process 비결정성으로 captured 취약·불변식은 강건).

## 5. 결론 (하드닝 4-track 완료)
- **A** GUI exec(G-7) ✅ · **B** E2E(SC-H2) ✅ · **C** 적대리뷰+Important 9 수정(SC-H3, Critical 0) ✅ · **D** TC-10+FVA+Minor+robustness(SC-H4) ✅.
- **129 pytest**(95→129, +34) · ruff clean · mypy strict(24) · 0 placeholder.
- **잔여(known issue, defer)**: Track-C Minor 8(TC-11~18) · G-7b(human 시각 디자인 QA).
- 다음: `/pdca analyze`(재Check, match rate) → report.

## 6. Check — SC-H 평가 + Match Rate (4-track 통합)

### 6.1 Success Criteria (SC-H1~H6)
| SC | 기준 | 상태 | 근거 |
|----|------|:----:|------|
| **SC-H1** | GUI offscreen 실행+산출 검증(G-7) | ✅ Met | test_gui_render.py 5 — DOM count·gate DOM·grab·GateBadge |
| **SC-H2** | E2E 1-pass, hop 계약 보존 | ✅ Met | test_e2e_pipeline.py 6 — 실 solve→R→GUI, 부호 100% |
| **SC-H3** | 미검토 모듈 0 Critical·Important 잔존 | ✅ Met | 적대리뷰 18 confirmed(Critical 0), Important 9 전부 수정+9 회귀; Minor 8 defer(결정) |
| **SC-H4** | 과학 Minor + FVA + robustness | ✅ Met | TC-10(3)·FVA(6)·robustness(5)·sign eps 정정·metrics 단일진입 |
| **SC-H5** | 무회귀 | ✅ Met | 129 pytest green, ruff clean, mypy strict(24), 0 placeholder |
| **SC-H6** | 정직성 산출물(잔여 위험 명시) | ✅ Met | offscreen≠시각QA(G-7b)·H4 데이터계약·golden near-zero·OSQP captured 취약 모두 문서화 |

**SC-H 6/6 Met (100%).**

### 6.2 Layer 점수
| Layer | Score | 근거 |
|-------|:-----:|------|
| Structural | 100% | 계획 산출물 전부 존재(fva.py 신규 + 5 신규 테스트 모듈 + 국소 수정) |
| Functional | 98% | 4-track 기능 구현·검증. 잔여 Minor 8(defer, in-scope 결함 아님) |
| Contract | 97% | Track-C Important 9 계약 위반 해소; 잔여 Minor 8(계약경미·defer) |
| Runtime | 100% | 129 pytest green(실 GUI·solve·R·MILP·FVA), ruff/mypy clean |

**Match Rate = 100×0.15 + 98×0.25 + 97×0.25 + 100×0.35 = 98.75%** (runtime 실행 공식).

### 6.3 결론 (Check)
- **SC-H 6/6 Met · Match 98.75% · Critical·Important 0**(Track-C Important 전부 수정).
- baseline 의 3대 정직성 격차 **전부 닫힘**: GUI 실행됨(A) · 통합 증명됨(B) · 미검토 모듈 적대 검증됨(C).
- **잔여(known issue, 사용자 결정 defer)**: Track-C Minor 8(TC-11~18) · G-7b(human 시각 디자인 QA).
- 신규 정직성 발견: golden near-zero 부재로 sign 정정 무파손 · OSQP captured-golden 취약(불변식 검증 채택).
- **report → archive 권장** (Checkpoint 5: Critical·Important 0 → 수정 대상 없음, 잔여는 Minor defer).

## Version History
| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-01 | Track-A/B 통과 + Track-C 적대 리뷰(18 confirmed) 등재. |
| 1.1 | 2026-06-01 | Track-C 수정(Important 9) + Track-D(D-full: TC-10·FVA·과학 Minor·robustness) 등재. 4-track 완료, 129 pytest. |
| 1.2 | 2026-06-01 | Check: SC-H 6/6 Met, Layer 점수, Match Rate 98.75%, Critical·Important 0. |
