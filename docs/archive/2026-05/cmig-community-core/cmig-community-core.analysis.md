# cmig-community-core — Check (Gap Analysis)

> **Phase**: Check · **Scope**: `module-1a` (Headless community core, 2a+2b) · **Date**: 2026-05-31
> **Method**: 3-layer static (Structural·Functional·Contract) + Runtime (pytest, 과학 라이브러리이므로 web L1/L2/L3 대신 pytest)
> **Upstream**: PRD · Plan(SC-1~9) · Design(Option C) · schema.md · glossary.md

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | community 대사 상호작용 분석이 스크립트 전용에 갇혀 인터랙티브·재현·출판 단절 |
| **RISK** | MICOM drift · namespace/sign silent error · OSQP-LP 정확도 → gate+sign CI+golden |
| **SCOPE(checked)** | module-1a only. module-1b(GUI)·1c(validation)·2(delta/sandbox/sweep)는 **미구현 = 범위 외** |

---

## 1. Strategic Alignment (PRD WHY)

✅ **정렬**. PRD 핵심 문제("스크립트 전용 → 인터랙티브·재현 단절")의 baseline 코어가 구현됨: 스크립트 0줄로 3-member community solve(`cmig`/golden_fixture) + 재현 가능 golden + run_hash. Option C(headless core + 4 seam) 아키텍처 결정 준수.

---

## 2. Plan Success Criteria 평가

| SC | 상태 | Evidence |
|----|:----:|----------|
| **SC-1** solver별 golden | ✅ Met | `tests/test_engine_golden.py::test_golden_regression_per_solver[gurobi/osqp/osqp_growth_highs_flux]` 통과; `fixtures/community_3_member/expected/*` 커밋 |
| **SC-2** sign-test CI | ✅ Met | `test_sign.py` canonical(−10→uptake10/+8→secretion8/−5/+3) + `test_engine_golden.py::test_sign_labels_real_data` |
| **SC-3** namespace gate 차단 | ✅ Met | `test_namespace_gate.py` (unresolved-high→block, low→warn·자동병합 없음, coverage%) |
| **SC-4** run_hash 캐시 | ✅ Met | `test_run_hash.py` (11구성요소·결정성·1개 변경 miss·member_set 순서 불변·float 잡음 흡수·env_lock 제외) |
| **SC-5** MICOM-version golden regression | ⚠️ Partial | run_hash에 `micom_version` 포함 검증(`test_run_hash_includes_micom_version`)·exact pin(0.39.0). **버전 상향 시 차단 게이트 자동화는 미구현(1c)** |
| **SC-6** OSQP→LP 재계산 | ✅ Met | `test_osqp_to_lp_matches_gurobi_profile` (hybrid=OSQP-QP+HiGHS-LP, profile=gurobi tolerance 내) — **단, 메커니즘은 MICOM hybrid 위임(아래 G-1)** |
| **SC-7** 튜토리얼 재현 | ⚠️ Partial | `test_community_solves_nonempty`로 스크립트 0줄 산출 입증. **MICOM 공식 튜토리얼과의 수치 대조는 1c** |
| **SC-9** tidy 계약 | ✅ Met | `test_tidy.py`(스키마·node/edge_type·roundtrip) + 실데이터 build_tidy 검증 |

**요약**: 7/9 Met, 2/9 Partial(SC-5·SC-7 — 둘 다 **1c(validation) 범위**라 module-1a 범위 내 결함 아님).

---

## 3. 3-Layer Static + Runtime

| Layer | Score | 근거 |
|-------|:-----:|------|
| **Structural** | 100% | design §4.2/§4.4 module-1a 컴포넌트 9개 파일 전부 존재(engine·namespace·sign·tidy·interactions·manifest·solver·golden·cli). 13파일 전부 Design Ref 주석 |
| **Functional** | 90% | 코어 로직 실구현·실 MICOM solve. 결함: G-1(SolverBackend.solve_* 미사용 stub), G-2(cross-feeding 경로 미검증) |
| **Contract** | 92% | tidy 컬럼·run_hash 11·sign 규약·gate 규칙·golden 구조가 schema와 일치. 미세: solver seam 계약(solve_lp/qp) 선언했으나 미사용 |
| **Runtime** | 100% | **pytest 41 passed**, ruff clean, mypy strict clean(13 files) |

**Match Rate (runtime-executed formula)** = Structural×0.15 + Functional×0.25 + Contract×0.25 + Runtime×0.35
- Check 시점: 15 + 22.5(F90) + 23(C92) + 35 = **95.5%**
- **Act/Iterate 후(G-1 resolved)**: 15 + 24(F96) + 24(C96) + 35 = **98%** (scope: module-1a)

---

## 4. Gap 목록

### G-1 [Important] ✅ RESOLVED (Act/Iterate, 2026-05-31)
- **발견**(원): `solver.py`의 `solve_lp`/`solve_qp`가 전부 `NotImplementedError`·호출처 0건. 실제 OSQP→LP는 MICOM "hybrid"가 내부 수행.
- **조치**: (a) `SolverBackend`를 **capability 보고 + solver selection seam**으로 정리 — `solve_lp`/`solve_qp` 제거(미사용 stub 0). solver 교체는 `engine.SOLVER_MAP`의 optlang solver 이름 선택으로 실현. (b) design §4.2 SolverBackend Protocol·solve 플로우를 동일하게 동기화("OSQP→LP는 MICOM hybrid 위임" 명시).
- **검증 후**: `grep NotImplementedError cmig` = 0; pytest 41 passed; ruff/mypy clean. 설계-구현 일치.

### G-2 [Minor] cross-feeding 추출 경로 미검증 (homogeneous fixture)
- **발견**: golden fixture가 4×동일 E.coli라 **cross_feeding edge = 0**. `interactions.build_tidy`의 secretor→consumer min-weight 경로가 양성 케이스로 실행되지 않음.
- **영향**: 코드는 존재하나 실 cross-feeding 산출 정확성 미입증(SC-9 일부).
- **권고**: 1c에서 **이종(heterogeneous) 멤버 fixture**(서로 다른 영양형) 추가 → cross_feeding edge 양성 케이스 golden.

### G-3 [Minor] AN-SINGLE FVA·loopless·infeasible diagnostic 미구현
- **발견**: §10 AN-SINGLE의 FVA/loopless/infeasible 진단은 미구현(MVP-0/세부).
- **영향**: module-1a 핵심(community core) 범위 밖. baseline 후속.
- **권고**: MVP-0 보강 또는 1c에서 처리.

---

## 5. Decision Record 검증

| 결정 (PRD→Plan→Design) | 준수? | 비고 |
|---|:---:|---|
| MICOM 위임·public API only | ✅ | `cooperative_tradeoff(fraction,fluxes,pfba)` 단일 wrapper 경유 |
| Gurobi 기본·solver별 golden | ✅ | 기본 gurobi + 3 variant golden. 환경 라이선스 v12에 맞춰 pin 조정 |
| Option C — 4 SC-driven seam | ✅ | (G-1 resolved) SolverBackend = capability+selection seam로 정합화·design 동기화 |
| tidy 단일 계약·pickle 금지 | ✅ | TidyBundle 단일 reader, ruff pickle-ban |
| run_hash 11·env_lock 제외 | ✅ | manifest.py 불변식 + 테스트 |

---

## 6. 결론 (Check #1)

module-1a(2a+2b)는 **Match Rate 95.5%**로 목표(≥90%) 충족. 9개 SC 중 7 Met·2 Partial(둘 다 1c 범위). Critical 결함 없음. **Important 1건(G-1, 설계-구현 편차)**은 기능 정확성 영향 없으나 design 동기화 권장.

---

## 7. Re-Check #2 — module-1a + 1c (validation 후)

> 1c(validation) 구현 + Act(G-1) 반영 후 재평가. Scope: 헤드리스 코어(1a+1c).

### 7.1 SC 재평가
| SC | Check#1 | **Re-Check#2** | Evidence |
|----|:--:|:--:|----------|
| SC-1 golden by solver | ✅ | ✅ | golden 3 variant 회귀 |
| SC-2 sign CI | ✅ | ✅ | canonical + 실데이터 |
| SC-3 gate 차단 | ✅ | ✅ | gate 테스트 |
| SC-4 run_hash 캐시 | ✅ | ✅ | 11구성요소·결정성 |
| **SC-5** version regression | ⚠️ Partial | ✅ **Met** | `verify_golden_versions`+`cmig golden verify`+양/음성 테스트 (1c) |
| SC-6 OSQP→LP | ✅ | ✅ | hybrid≡gurobi profile |
| **SC-7** 튜토리얼 재현 | ⚠️ Partial | ✅ **Met** | `test_engine_reproduces_direct_micom`(비트 동일)+sanity (1c) |
| SC-9 tidy 계약 | ✅ | ✅ | 스키마·실데이터 |
| SC-8 sandbox preview | — | ⬜ module-2 | (범위 외) |

→ **module-1a+1c 범위 SC 8/8 Met** (SC-8은 module-2).

### 7.2 Gap 상태
| Gap | Check#1 | Re-Check#2 |
|-----|:--:|:--:|
| **G-1** SolverBackend stub | Important | ✅ Resolved (Act: seam 정리 + design 동기화) |
| **G-2** cross-feeding 경로 미검증 | Minor | ✅ Closed (1c: 합성 secretor/consumer → weight=min) |
| **G-3** AN-SINGLE FVA/loopless | Minor | ⬜ Open (MVP-0 보강, 범위 외) |

### 7.3 Layer 점수 (Re-Check#2)
| Layer | Score | 근거 |
|-------|:-----:|------|
| Structural | 100% | 1a 9파일 + 1c validation(golden_fixture verify·tests) |
| Functional | 98% | G-1/G-2 해소. 잔여 G-3(범위 외) |
| Contract | 98% | design §4.2 동기화 완료(Act) |
| Runtime | 100% | **pytest 48 passed**, ruff clean, mypy strict clean, 0 placeholder |

**Match Rate** = 100×0.15 + 98×0.25 + 98×0.25 + 100×0.35 = **99%** (scope: 헤드리스 코어 1a+1c)

### 7.4 결론
헤드리스 코어(1a+1c)는 **99% / Critical·Important 0**. SC 8/8 Met. 잔여 G-3는 범위 외(MVP-0/AN-SINGLE FVA). **report 또는 다음 모듈(1b GUI / 2 delta·sandbox·sweep) 진행 가능.**

---

## 8. Re-Check #3 — module-2 headless slice 후 (전체 헤드리스 baseline)

> module-2 headless slice(delta·sandbox·sweep) 구현 후 재평가. Scope: 헤드리스 baseline(1a+1c+2-slice).

### 8.1 SC 재평가 (최종)
| SC | Re-Check#2 | **Re-Check#3** | Evidence |
|----|:--:|:--:|----------|
| SC-1~7,9 | ✅(8) | ✅ | (변동 없음) |
| **SC-8** sandbox preview 비오염 | ⬜ module-2 | ✅ **Met** | `test_sandbox.py`(PREVIEW store write 0·COMMITTED 승격·multiple preview 비오염) |

→ **baseline SC 9/9 전부 Met** (코드+테스트).

### 8.2 신규 구현 (module-2 headless slice)
| 구성 | 파일 | 검증 |
|---|---|---|
| AN-DELTA | `core/delta.py` | `test_delta.py`(profile delta·added/removed·real 2→3 member) |
| G1 Sandbox (SC-8) | `core/sandbox.py` | `test_sandbox.py` 6 tests |
| G4 Sweep (SC-4 ext) | `core/sweep.py` | `test_sweep.py`(cache hit/miss·실패 diagnostic·parquet·run_hash 결정성) |

### 8.3 Gap 상태 (carry-over는 범위 결정)
| Gap | 상태 | 비고 |
|-----|:--:|------|
| G-1 SolverBackend stub | ✅ Resolved | (Act) |
| G-2 cross-feeding 미검증 | ✅ Closed | (1c) |
| G-3 AN-SINGLE FVA/loopless | ⬜ Open | MVP-0 보강, 범위 외 |
| **G-4** R Render (FR-2.5, SVG/TIFF) | ⏸️ Deferred | R 설치 필요 — Checkpoint 4 명시적 defer |
| **G-5** minimal medium MILP·limiting·sensitivity (FR-2.3) | ⏸️ Deferred | MILP·heavier — 후속 슬라이스 |
| **G-6** CMIG-MIP/MRO·interaction typing (FR-2.4) | ⏸️ Deferred | 후속 슬라이스 |
| GUI delta/sandbox 오버레이 (FR-2.6 UI) | ⏸️ Deferred | module-1b 의존 |

> G-4~G-6은 **결함이 아니라 Checkpoint 4에서 합의된 범위 분할(scope split)**이다. baseline 전체 완성도 관점의 carry-over이며 Critical/Important 아님.

### 8.4 Layer 점수 (헤드리스 baseline slice)
| Layer | Score | 근거 |
|-------|:-----:|------|
| Structural | 100% | 12 core 모듈(+delta·sandbox·sweep) |
| Functional | 97% | SC 9/9 로직 구현. 잔여=범위-defer(R/MILP/MIP-MRO/GUI)·G-3 |
| Contract | 98% | tidy·run_hash·sign·gate·sweep schema 일치 |
| Runtime | 100% | **pytest 65 passed**, ruff clean, mypy strict clean(16), 0 placeholder |

**Match Rate** = 100×0.15 + 97×0.25 + 98×0.25 + 100×0.35 = **98.75%** (scope: 헤드리스 baseline slice)

### 8.5 결론
헤드리스 baseline(1a+1c+2-slice)는 **≈99% / Critical·Important 0 / SC 9/9 Met**. carry-over(G-4~G-6 = R Render·MILP·MIP-MRO·GUI)는 명시적 범위 분할로, 후속 슬라이스/모듈에서 진행. **report(헤드리스 baseline 완성) 또는 module-1b(GUI)/R Render 슬라이스 진행 가능.**

---

## 9. Re-Check #4 — module-1b (GUI graph) 후

> module-1b GUI 구현 후 재평가. Scope: baseline(1a+1c+2-slice+1b). headless 환경 제약 명시.

### 9.1 구현 (module-1b)
| 구성 | 검증 | Evidence |
|---|---|---|
| `gui/graph_data.py` (tidy→Cytoscape elements·필터·gate UI·legend) | ✅ Tested | `test_graph_data.py` 7 tests (FR-1b.1/1b.2/1b.3 데이터 계약) |
| `gui/assets/graph.html` (Cytoscape.js + setGraph hook) | △ 구조 검사 | key hooks 존재 |
| `gui/graph_view.py` (PySide6 InteractionGraphView·GateBadge) | ❌ **미검증** | PySide6 미설치·headless → 실행/렌더 검증 불가 |

### 9.2 Gap 갱신
| Gap | 상태 | 비고 |
|-----|:--:|------|
| **G-7** GUI 위젯 렌더링 미검증 | ⚠️ Open (env-limited) | `graph_view.py`는 작성됐으나 **디스플레이+PySide6 환경에서만 검증 가능**. 코드 결함 아님 — 환경 제약. 데이터 계약(graph_data)은 완전 테스트됨 |
| G-3 / G-4 / G-5 / G-6 | (변동 없음) | AN-SINGLE FVA / R Render / MILP / MIP-MRO |

> G-7은 **환경 제약(headless·PySide6 부재)** 이며 코드 수정으로 해소되지 않는다. Option C대로 GUI는 tidy 계약만 소비하므로, 검증 가능한 데이터 브릿지가 핵심이고 그 부분은 green. 실제 렌더는 `uv sync --extra gui` + 디스플레이에서 확인.

### 9.3 Layer 점수 (baseline + 1b)
| Layer | Score | 근거 |
|-------|:-----:|------|
| Structural | 100% | core 12 + gui 3 모듈 |
| Functional | 96% | SC 9/9 로직 + GUI 데이터 계약. 잔여=GUI 렌더 미검증(G-7, env)·carry-over·G-3 |
| Contract | 98% | tidy·run_hash·sign·gate·sweep·graph payload 일치 |
| Runtime | 100% | **pytest 72 passed**, ruff clean, mypy strict clean(19), 0 placeholder (검증 가능 표면) |

**Match Rate** = 100×0.15 + 96×0.25 + 98×0.25 + 100×0.35 = **98.5%** (scope: baseline + 1b 데이터 계약)

### 9.4 결론
baseline(1a+1c+2-slice) + module-1b 데이터 계약 = **≈98.5% / Critical·Important 0 / SC 9/9 Met**. **G-7(GUI 렌더 미검증)** 은 환경 제약(디스플레이·PySide6 부재)으로, 디스플레이 환경에서 별도 검증 필요 — 코드 결함 아님. carry-over(R/MILP/MIP-MRO)는 범위 분할. **report 갱신 또는 R/MILP 슬라이스 진행 가능.**

---

## 10. Re-Check #5 — R Render 슬라이스 (G-4) 후

> R Render(FR-2.5) 구현 후 재평가. Scope: baseline + render. **실제 R 렌더 검증됨**.

### 10.1 구현 (render-slice)
| 구성 | 검증 | Evidence |
|---|---|---|
| `cmig/render/client.py` (RenderClient subprocess·FigureSpec·matplotlib fallback) | ✅ Tested | `test_render.py` (figure_spec·bad format·available 분기) |
| `cmig/render_r/figure.R` (ggplot2 diverging bar) | ✅ **실제 R 실행** | `test_real_r_render_svg`(svglite SVG 8.5KB·`<svg` 헤더)·`test_real_r_render_deterministic` |
| figure_spec sidecar (seed 재현, §9) | ✅ | `test_render_writes_figure_spec_sidecar` |

### 10.2 Gap 갱신
| Gap | Re-Check#4 | **Re-Check#5** | 비고 |
|-----|:--:|:--:|------|
| **G-4** R Render | ⏸️ Deferred | ✅ **Closed** | 실제 R(ggplot2) SVG 렌더 검증·GPL subprocess 격리 |
| G-7 GUI 렌더 | ⚠️ env-limited | ⚠️ (변동 없음) | 디스플레이 환경 필요 |
| G-5 minimal medium MILP / G-6 CMIG-MIP/MRO | ⏸️ carry-over | (변동 없음) | 후속 슬라이스 |
| G-3 AN-SINGLE FVA | ⬜ Open | (변동 없음) | MVP-0 |

### 10.3 Layer 점수 (baseline + render)
| Layer | Score | 근거 |
|-------|:-----:|------|
| Structural | 100% | core 12 + gui 3 + render 2 |
| Functional | 97% | SC 9/9 + R Render(실검증) + GUI 데이터 계약. 잔여=G-7(env)·carry-over G-5/6·G-3 |
| Contract | 98% | tidy·run_hash·sign·gate·sweep·graph·figure_spec 일치 |
| Runtime | 100% | **pytest 78 passed**(실제 MICOM solve + 실제 R 렌더), ruff clean, mypy strict(21), 0 placeholder |

**Match Rate** = 100×0.15 + 97×0.25 + 98×0.25 + 100×0.35 = **98.75%** (scope: baseline + render)

### 10.4 결론
baseline + GUI 데이터 계약 + **R Render(실검증)** = **≈98.75% / Critical·Important 0 / SC 9/9 Met**. **G-4 closed**(실제 출판 그림 렌더). 잔여: G-7(GUI 렌더 env)·G-5/G-6(MILP/MIP-MRO carry-over)·G-3(FVA). **report 갱신 또는 MILP 슬라이스 진행 가능.**

---

## 11. Re-Check #6 — 최종 적대적 코드 리뷰 (baseline 완성 점검)

> baseline 전체(MILP 포함) 완성 후, **3-차원 병렬 리뷰(correctness·contract·quality) + 적대적 검증** 워크플로(24 agents, 1.73M tokens). **21건 제기 → 15건 confirmed**(오탐 6). per-slice Check가 놓친 **교차 모듈 계약 위반**을 포착 — match rate 하향.

### 11.1 Confirmed Gaps (15: 3 Critical · 6 Important · 6 Minor)

**🔴 Critical (3)**
| # | 위치 | 결함 |
|---|---|---|
| **C-1** | `engine.py:146-164` | **pure-OSQP 경로가 flux_solver='osqp'·flux_report_status='full'로 오기록**. OSQP는 QP 전용(LP 불가, solver.py:90)→ `flux_solver=None`·`qp_only_approximate`여야 함(§4.2 [SOLVER-SPLIT]). **run_hash #7에 존재하지 않는 LP solver 주입 → 재현성 정체성 오염** |
| **C-2** | `engine.py:160` | `flux_report_status` 전 경로 `"full"` 하드코딩 → 계약상 `qp_only_approximate`(§4.2·glossary §1.D)를 **영원히 방출 불가** (C-1과 동일 뿌리) |
| **C-3** | `sweep.py:24` | `SWEEP_SCHEMA`에 **`schema_version` 컬럼 누락** — schema §6.1이 AggregationStore 첫 컬럼(nullable=false)으로 명시. tidy 단일-계약 원칙 위반 |

**🟠 Important (6)**
| # | 위치 | 결함 |
|---|---|---|
| I-1 | `engine.py:117-126` | member_growth/abundances가 members_df 미존재 멤버를 **무진단 silent drop** → members ⊋ growth (§4.4 fail-explicit 위반) |
| I-2 | `sweep.py:118-126` | **실패 run 미캐시** → 동일 실패 조건 재sweep마다 재계산(§6.2·A14 캐시 정체성) |
| I-3 | `engine.py:26` | **SOLVER_MAP에 `highs` golden 변형 누락**(`osqp`로 대체). schema §7.4 golden 3종=gurobi/highs/osqp_growth_highs_flux ↔ 구현=gurobi/osqp/hybrid 불일치 |
| I-4 | `engine.py:103` | **tradeoff_f 범위(0<f≤1) 미검증**(§4.2 [TRADEOFF-RANGE]) — MICOM에 직접 전달 |
| I-5 | `golden_fixture.py:104` | run_hash **독자 재구현**(manifest.compute_run_hash 우회) → [HASH-SINGLE] 위반, golden↔runtime 분기 위험 |
| I-6 | `manifest.py:94` | `canonical_json` allow_nan=True → bounds의 ±inf/NaN **비결정적 직렬화**(NaN≠NaN hash) |

**🟡 Minor (6)**: sign `eps` 기본 0.0(noise floor 1e-6 불일치, sign.py:45) · namespace coverage가 WARNED를 분모서 제외(namespace.py:86) · RunManifest에 flux_report_status 미모델(manifest.py:107) · tidy edge_type가 sign label과 overload(tidy.py:54, OD-45) · metrics가 sign 단일진입점 우회 inline 분류(metrics.py:30) · engine status="optimal" 하드코딩·infeasible 미검사(engine.py:159).

### 11.2 Layer 점수 (Re-Check #6)
| Layer | Score | 근거 |
|-------|:-----:|------|
| Structural | 100% | 모든 모듈 존재 |
| Functional | 92% | C-1·I-1·I-2·minor engine status — 실 로직 결함 |
| Contract | 87% | C-1·C-2·C-3·I-3·I-4·I-5·I-6 — schema/design 계약 위반 다수 |
| Runtime | 100% | 88 pytest green — **단, 이 결함들을 커버하지 않음**(리뷰가 보강) |

**Match Rate** = 100×0.15 + 92×0.25 + 87×0.25 + 100×0.35 = **94.75%** (per-slice 98.75 → 교차검토 후 하향)

### 11.3 결론
baseline 기능은 동작하나 **3 Critical + 6 Important 계약/정확성 결함**이 잠재(특히 C-1/C-2 OSQP flux 메타데이터 → run_hash 오염, C-3 sweep schema_version). 모두 **국소 수정 가능**(예외/분기/컬럼 추가)이며 회귀 테스트로 고정 권장. **Act(iterate)로 Critical+Important 수정 후 report 권장.**

### 11.4 Act/Iterate #2 — Critical + Important 해소 (2026-05-31)
Checkpoint 5에서 "Critical+Important 모두 수정" 선택. **9건 전부 수정 + 7 회귀 테스트 추가**(95 pytest, ruff/mypy clean).

| Gap | 조치 | 검증 |
|-----|------|------|
| **C-1·C-2** | `engine.py` flux 분기: osqp→`flux_solver=None`·`qp_only_approximate`; hybrid→`highs`·full; gurobi→full. run_hash #7 LP 오염 제거 | `test_flux_report_metadata_per_solver`(실 solve) |
| **C-3** | `sweep.py` SWEEP_SCHEMA에 `schema_version` 첫 컬럼 + `SWEEP_SCHEMA_VERSION` | `test_schema_version_first_column` |
| I-1 | `engine.py` member_growth/abundances를 모든 member_id로 기록(None=누락) + missing 진단 + infeasible(growth NaN) 가드 | 타입 Optional·diagnostic |
| I-2 | `sweep.py` RunHashCache가 (value,status,diagnostic) 저장 → **실패도 캐시·replay** | `test_failed_run_is_cached` |
| I-3 | golden 변형 `highs`→`osqp` 재조정(MICOM community QP 불가) + design L3-2·SOLVER_MAP 주석 동기화 | design §11.2·engine 주석 |
| I-4 | `engine.py` tradeoff_f 범위(0<f≤1) fail-fast 가드 | `test_tradeoff_f_range_guard` |
| I-5 | `golden_fixture.py` run_hash를 **manifest.compute_run_hash 단일 경유**([HASH-SINGLE]) | config run_hash == canonical (검증) |
| I-6 | `manifest.py` non-finite float→sentinel + `allow_nan=False` | `test_non_finite_floats_deterministic` |

**잔여 Minor 6건**(사용자 결정으로 defer): sign eps 기본·coverage WARNED·manifest flux_report_status 미모델·edge_type/label overload·metrics sign-bypass·engine status(부분 해소: infeasible 가드 추가). → known issues, 후속.

### 11.5 Re-Check 결과 (Act 후)
| Layer | Score |
|-------|:-----:|
| Structural | 100% |
| Functional | 96% (C-1·I-1·I-2 해소; 잔여 minor) |
| Contract | 97% (C-2·C-3·I-3~I-6 해소; 잔여 minor) |
| Runtime | 100% (**95 pytest** +7 회귀, ruff/mypy clean, 0 placeholder) |

**Match Rate = 100×0.15 + 96×0.25 + 97×0.25 + 100×0.35 = 98.25%** (94.75 → **98.25**, Critical·Important 0).

**최종 결론**: baseline 전체(MVP-0~2) 구현·검증 완료, **Critical·Important 0, SC 9/9 Met, 98.25%**. 잔여는 Minor 6(defer)·G-7(GUI env)·G-3(MVP-0 FVA). **report → archive 권장.**
