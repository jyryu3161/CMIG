# CMIG v3.0 — 코드리뷰 + 명세 갭 분석 (검증 통과본)

- 작성일: 2026-06-01 (코드 재검토 시점)
- 기준 명세(권위): `CMIG_명세서_v3.0.md`
- 이전 리뷰: `REVIEW/CMIG_v3_implementation_review.md`(2026-05-31), `REVIEW/CMIG_v3_update_review_2026-06-01.md`
- 방법: 10개 기능 클러스터별 정밀 분석 → 고위험 발견 **적대적 검증(adversarial verify)** → 핵심 쟁점은 작성자가 직접 코드/데이터로 재확인.
- 비고: 이전 두 리뷰 이후 코드가 크게 진화함(CLI solve 구현, hybrid solver 폐기, host/dfba/search/stats 추가). 이전 R1–R6 / U1–U6 다수가 **해결됨**. 본 문서는 현재 코드 기준의 새 baseline이다.

## 0. 그라운드 트루스 (직접 확인)

| 게이트 | 결과 |
|---|---|
| `uv run pytest` | **green (exit 0)** · 308 test fn / ~313 item (실 MICOM·OSQP·dFBA·host·stats·GUI offscreen 포함) |
| `uv run ruff check .` | All checks passed |
| `uv run mypy cmig` | Success: no issues found in 55 source files (strict) |
| 코드 규모 | `cmig/` 약 6,224 LOC / 약 50 모듈, 49 테스트 파일 |

테스트·린트·타입 게이트가 모두 통과하므로, 아래 "코드리뷰 발견"은 **테스트로는 드러나지 않는** 계약/재현성/정직성/스코프 격차에 집중한다.

---

## 1. 이전 리뷰 대비 해결 현황

| 이전 항목 | 현재 | 근거 |
|---|---|---|
| R1/U1 hybrid가 메타데이터-only LP 위장 | **해결(방식 전환)** | hybrid `osqp_growth_highs_flux` 폐기. `SOLVER_VARIANTS=("gurobi","osqp")` (`golden_fixture.py:25`). 단, OSQP 라벨링이 새 이슈로 전환 → §3 F-1 |
| R3/U2 CLI solve 미구현 | **해결** | `solve_fixture`/`solve_community`가 nodes/edges/profile.parquet + manifest.json(run_hash) 산출 (`service/engine_service.py:45-133`, `io/solve_output.py`) |
| R4/U4 FVA가 sandbox에 미연결 | **부분 해결** | `evaluate_sandbox(fva=...)`가 no-change 시 FVA 동반(`core/sandbox.py:113`). 단 단일-GEM·테스트 경로만 → §3 F-7 |
| R5/U5 자유 문자열 diagnostic | **해결** | `core/diagnostics.py` 폐쇄 enum + canonical JSON(`allow_nan=False`), engine/delta/sandbox/sweep/service 전면 적용 |
| R6/U6 README 불일치 | **해결** | README가 현재 상태(headless core+facade+GUI shell, hybrid 폐기) 반영 |
| R2 golden 목록 불일치 | **부분 해결** | `docs/decisions/2026-06-01-golden-solver-list.md`로 결정 기록. 단 명세 §16 본문 미개정 + CI 부재 → §3 F-2, §4-L |

---

## 2. 잘 구현된 부분 (직접 확인)

- **MICOM 단일 seam·정확 pin**: `core/engine.py`가 public API(`cooperative_tradeoff(fraction, fluxes=True, pfba=True)`)만 경유, `micom==0.39.0` pin, internal API 미사용.
- **§4.8 namespace gate 로직 + 실제 enforce**: `evaluate_gate`/`raise_if_blocked`가 high-confidence unresolved 시 `GateBlockedError`로 solve 차단. **`solve_community`가 solve 전에 실제 호출**(`engine_service.py:101-102`)하고 decision key를 run_hash #10에 배선(`:124`). (이전 분석에이전트의 "gate 미배선" 주장은 검증으로 **기각**.)
- **run_hash 11구성요소**: `core/manifest.py`가 11개 assert·float rounding·비유한 sentinel·canonical JSON(`allow_nan=False`)로 SHA-256. SC-4 충족.
- **sign 단일 진입점 + §4.7 계약**: `core/sign.py` `+`=분비/`−`=흡수 단일 변환, canonical CI 케이스, cross-feeding `weight=min` 회귀 테스트.
- **golden + MICOM-version 회귀 게이트**: float rounding 후 정규화 hash + tolerance 비교, 버전 불일치 시 승격 차단(`golden_fixture.py:125-167`).
- **sandbox preview/commit + fail-explicit**: PREVIEW는 store 비기록, COMMIT만 run_hash 승격; constrained 실패를 `no_significant_change`로 위장하지 않음(`core/sandbox.py:103-131`).
- **AN-SINGLE/AN-PAIR 코어**: FBA/pFBA(성장률 재계산)/FVA/knockout(auto-restore)/interaction typing/MRO/MIP/cross-feeding — 실 Gurobi/cobra 테스트 통과.
- **Stats 5a**: 분포요약·effect size(Cliff δ/Cohen d)·MWU/Welch/Kruskal/ANOVA·statsmodels BH/BY FDR·오용 경고 — 순수함수로 구현·테스트.
- **R 렌더 격리·확장**: profile(ggplot2)/network(ggraph)/chord(circlize)/heatmap(ComplexHeatmap) 각각 격리 Rscript subprocess, `.Rlib` 잠금, SVG(svglite)+TIFF(ragg 600dpi LZW).
- **Interaction Graph Viewer**: 실제 `QWebEngineView` + 로컬 Cytoscape.js 번들, payload 주입 DOM 검증, sign 범례 상시 — GUI 중 가장 완성도 높음.

---

## 3. 코드리뷰 — 검증 통과 발견만 (file:line)

> 적대적 검증에서 **기각된** analyze 주장은 §5에 별도 정리.

### 🔴 High

**F-1. OSQP 경로 라벨은 루트 명세 기준 `qp_only_approximate`가 맞음 (2026-06-02 정정)**
- 위치: `core/engine.py:171-177`
- 정정: 루트 명세(`CMIG_명세서_v3.0.md`)는 OSQP baseline을 `qp_only_approximate`로 명시한다. 따라서 runtime optlang 세부와 별개로 제품 provenance는 `growth_solver=osqp`, `flux_solver=null`, `flux_report_status=qp_only_approximate`가 권위 계약이다.

**F-2. run_hash `bounds` 구성요소가 모든 production assembly에서 `{}` 하드코딩**
- 위치: `io/solve_output.py:51` (`build_run_components`), `golden_fixture.py:77`
- 영향: reaction bound만 다른 두 solve(=sandbox commit, knockout, sweep의 `bounds` 축)가 **동일 run_hash** 산출 → 캐시 충돌·재현성 구멍. 11구성요소가 hash 레이어엔 배선됐지만 #5는 실무에서 절대 변하지 않음.
- 권장: solve 시 community의 실제(편집된) reaction bound를 `RunHashComponents.bounds`에 주입.

**F-3. Baseline GUI(§11)가 통합 애플리케이션으로 미완 — 패널 고아·진입점 부재**
- 위치: `gui/app.py:110-148` (패널이 shell에 docking 안 됨, GUI entry point/event loop 없음)
- 영향: §11 데스크톱 워크플로(Community Builder 라이브 preview·gate UI, Medium Editor, Model Manager, External Profile Viewer 차트, Sweep View, Scenario Compare, **G1 sandbox 인터랙티브 루프**)가 사용 가능한 앱으로 존재하지 않음. 위젯은 offscreen 테스트 36개를 통과하나 "실행 가능한 제품"은 아님. **baseline 최대 격차.**
- 권장: §4-F 로드맵 참조.

### 🟠 Med

**F-4. namespace 정합(reconciliation) producer 부재 → gate가 기본값에서 무력**
- 위치: gate는 enforce되나(`engine_service.py:101`) `solve_community`의 `namespace_decisions` 기본값 `[]` → 차단할 대상이 없음. exchange 대사체를 비교해 `NamespaceDecision`(confidence·status)을 **자동 산출하는 로직이 없음.**
- 영향: §4.8 hard gate의 보호 가치가 기본 경로에서 0. 사용자가 직접 제공한 모델/medium namespace mismatch를 잡으려면 명시적 decision 입력 또는 사전 review가 필요함. (게이트/감사 메커니즘 자체는 완성.)
- 권장: 멤버 exchange 대사체 namespace 정합·confidence·audit trail 생성기 구현(§4.8 핵심·MVP-1a).

**F-5. headless sweep 산출 경로 부재 (AN-SWEEP/G4가 라이브러리에 갇힘)**
- 위치: `core/sweep.py:122-169`에 sweep 로직은 있으나, 축 값 → 11구성 run_hash → `EngineService.solve` → `sweep.parquet`(condition_id, axis, metric, value, run_hash, status, diagnostic)을 쓰는 **production bridge(CLI/facade)가 없음.**
- 권장: `cmig sweep` CLI + facade 메서드 추가(§5 AggregationStore 기록).

**F-6. 영속 manifest.json이 §7 RunManifest 전체 필드 누락**
- 위치: `io/solve_output.py:92-106` payload가 flat(run_hash·components·diagnostic·env_lock·platform·artifacts).
- 누락: `solver.tolerance`/`flux_report_status`(별도 필드), `algorithms`(metric_mode·minimal_medium·seed·normalization), `engine.tradeoff_f`, `sweep`(axes·n_runs), `figure_specs`. 또한 `env_lock`/`platform`은 CLI가 채우지 않음(`engine_service.py:92`).
- 권장: §7 전체 nested 그룹 직렬화.

**F-7. sandbox no-change FVA가 단일-GEM·production 미배선 + facade에 sandbox 메서드 없음**
- 위치: `core/sandbox.py:64-66,113` (단일-GEM FVA 동반, docstring도 "community-level FVA 아님" 명시); `service/engine_service.py:31` docstring은 "sandbox 오케스트레이션"을 광고하나 **sandbox 메서드 없음.**
- 영향: §10 AN-SANDBOX의 "보상 우회 시 FVA 범위" 과학적 의도가 community 차원에서 충족 안 됨. 실제 FVA 주입은 테스트만 수행.
- 권장: facade에 sandbox orchestration 추가 + no-change 시 community FVA 계산·주입.

**F-8. minimal medium MILP — 비결정적 tie-break + U-base 강제추가가 cardinality/essentiality 왜곡**
- 위치: `core/medium.py:104,120-122,131-136,140-145`
- 영향: equicardinal alternate optima 중 결정적 선택 없음(출력 정렬만) → 재현성·골든 안정성 위협. MILP 후 U-base{H₂O,H⁺,Pi}를 강제 추가해 cardinality를 부풀리고 `limiting_nutrients`가 U-base를 essential로 오라벨.
- 권장: 결정적 tie-break(예: lexicographic secondary objective), U-base를 MILP 유도분과 분리.

**F-9. AN-PAIR 배지별 matrix 부재**
- 위치: `core/pair.py` — `analyze_pair`에 medium 파라미터 없음, 다중 배지 iterator/aggregator 없음.
- 권장: 배지 리스트 순회 → condition×metric matrix 조립.

**F-10. R export 격차: 'stress' 레이아웃·PDF/EPS·폰트 임베딩·journal_preset 미적용 + profile 경로 --rlib 누락**
- 위치: `render_r/network.R:41`('fr' 사용, 명세는 결정적 'stress'); `render/client.py:41`(`journal_preset` 기록되나 R에 미전달=dead); profile 경로가 `--rlib` 미전달로 `.Rlib`의 svglite/ragg 도달 불가; `SUPPORTED_FORMATS`에 PDF/EPS 없음·폰트 임베딩 없음.
- 권장: §9 export 워크플로(상태 승계+레이아웃 override+preview+seed) 포함 보강.

**F-11. JobRunner 스레드 안전성/수명 결함**
- 위치: `service/jobrunner.py:144-156` — cancel/result/retry/poll가 lock 밖에서 공유 dict 접근; unknown job_id에 bare `KeyError`; `retry()`가 상태 무관 재제출·job 보존 무한 증가(eviction 없음).

### 🟡 Low (선택)
- `core/engine.py:71-79` `EngineWrapper` Protocol이 §4.1의 documented `pfba` 옵션을 시그니처에 미노출(구현은 사용) — *검증=반박(none)이나 인터페이스 명세 일관성 차원 권장.*
- `core/solver.py:80-91` `OsqpBackend` docstring이 폐기된 HiGHS-LP-recompute 동작을 여전히 서술(F1 이후 stale).
- `core/solver.py:24` CPLEX가 명세 §2 매트릭스엔 있으나 registry 부재(Extension).
- `core/golden.py:21-27` float 정규화가 NaN은 토큰화하나 ±inf는 미정규화(`manifest._round_floats`와 비대칭).
- `core/interactions.py:98-101` cross-feeding secretor/consumer 필터가 sign 단일 진입점 우회(부호 직접 비교).
- `core/metrics.py:65-79` CMIG-MIP를 "donation count"로 계산 — 명세의 "cross-feeding 절감(reduction)"과 의미 차이(SMETANA-호환 옵션 미제공).
- `service/engine_service.py:92` headless solve가 env_lock/platform 미기록(F-6과 동일 축).

---

## 4. 추가 구현 필요 — Baseline (MVP-0~2) 우선

> 명세상 baseline(§10–§11, §16) 완성을 위해 **지금 필요한** 작업. 효율 표기 S/M/L.

| # | 항목 | 명세 | MVP | 효율 | 근거 발견 |
|---|---|---|---|---|---|
| **A** | **namespace exchange 정합 producer**(decision·confidence·audit 자동 산출) — gate에 실제 보호력 부여 | §4.8 | 1a(blocker) | L | F-4 |
| **B** | **OSQP flux 보고 정직화**(`qp_only_approximate` 유지·full은 gurobi 전용) | §4.2 | 1a | M | F-1 |
| **C** | **run_hash `bounds` 실배선**(하드코딩 `{}` 제거) | §5·§7 | 2 | S–M | F-2 |
| **D** | **headless sweep 산출**(`cmig sweep` + facade → `sweep.parquet`·캐시·실패 diagnostic) | §10 G4 | 2 | M | F-5 |
| **E** | **§7 manifest 전체 필드 persist** + env_lock/platform | §7 | 2 | M | F-6 |
| **F** | **Baseline GUI 통합**: shell 조립·진입점 / Community Builder(drag·abundance·objective·live preview·gate UI) / Medium Editor(CSV·preset·Check Growth·minimal medium·before-after) / Model Manager(import·rxn/met/gene 테이블·coverage·validation) / External Profile Viewer 차트 / Sweep View / Scenario Compare / **G1 sandbox 루프(slider→debounce→re-solve→delta overlay→cancel/undo→Apply/Save)** / §11 원칙(command palette·undo-redo·autosave·고대비 테마·KO-EN 토글·검색·provenance tooltip) | §11 | 1b | L(다수) | F-3 |
| **G** | **sandbox 제품경로 완성**: facade sandbox 메서드 + no-change 시 **community** FVA 계산·주입 | §10·§11 | 2 | M | F-7 |
| **H** | **minimal medium 결정성·정확성**: 결정적 tie-break, U-base 분리, optional SMETANA-호환 MIP | §4.5 | 2 | M | F-8 |
| **I** | **AN-PAIR 배지별 matrix** | §10 | 2 | M | F-9 |
| **J** | **AN-SINGLE bound 편집** 오퍼레이션 | §10 | 0 | S | §5 single_model |
| **K** | **R export 보강**: PDF/EPS·폰트 임베딩·'stress' 레이아웃·journal_preset 적용·profile `--rlib`·export workflow(preview/seed) | §9 | 2 | M–L | F-10 |
| **L** | **CI 매트릭스**: solver별 golden regression + MICOM-version gate를 CI 배선(.github 부재) | §16/A17 | 1a | S | F-2 근거 |
| **M** | **JobRunner 스레드 안전성/수명** | §8 | 1a | S | F-11 |

---

## 5. 추가 구현 필요 — Extension (MVP-3~5)

> 명세상 **baseline 아님**. 설계는 확정·일부 구현됨. baseline 일정에 섞지 말 것. 단 사용자 노출 surface(CLI/GUI)에 "PART II Extension" 라벨 부재 → 혼동 방지 라벨 권장.

- **Host-Microbe (§12, MVP-3)** — *구현됨*: 기본정책(host를 community objective 미포함 + ATP-maintenance viability lower-bound constraint, microbe=MICOM cooperative tradeoff 분리), lumen/blood 2-interface 스키마, Recon3D smoke, GUI dashboard. *필요*: ① 실 Human-GEM scale **spike**(10k+ rxn host + 미생물 2 결합 solve 시간·메모리 측정 — 명세상 본착수 선행조건) ② exchange→lumen/blood **mapping wizard** ③ 선택형 host objective{growth, ATP/biomass maintenance, target secretion} ④ non-ATPM host의 maintenance reaction 해소(현재 id 부재 시 silent skip, `core/host.py:197-199`) ⑤ **버그**: `solve_host`가 caller host 모델을 영구 변형(컨텍스트 매니저 없음, `:188-199`) ⑥ **버그(High-in-Extension)**: dFBA emergency-clamp가 질량보존/'소비≤가용' 위반(`core/dfba.py:108-114` — min_dt 오버슈트 시 농도를 0 clamp하나 그 step의 biomass는 full uptake 기반 μ로 이미 증가 → 가짜 기질로 성장) + Δt 수렴/질량보존 acceptance test 필요.
- **Consortium Search (§14, MVP-4)** — *구현됨*: `target_max_solve`(community growth floor), exhaustive `rank_consortia`, `normalize_score`/`weighted_multi_target`/`pareto_frontier`/`mro_mip_prescreen`/GA 헬퍼·단위테스트. *필요(모두 라이브러리→파이프라인 미배선)*: ① **direction semantic preset**(`maximize_secretion`/`minimize_toxic_secretion`/`maximize_uptake_reduction`/`maximize_uptake`) — 현재 enum이 명세 preset 미구현(`search.py:20-24`) ② 목적식에 **member-min-growth·(host viability) 제약**(`:49-88` 누락) ③ **단위 정규화 후 가중합(A13)**을 실제 ranking 경로에 적용(`:91-140` 미적용) ④ targets[]의 `constraint` 필드 + ε-constraint ⑤ Pareto 3-optional/4+-비권장·`pareto_rank`·trade-off 곡선 출력 ⑥ combo 크기별 strategy dispatch(exhaustive/MRO-MIP greedy/GA·Bayesian) ⑦ 출력 계약(per-target yield·abundance·key_crossfeeding·required_medium·limiting/toxic·host_impact·robustness) ⑧ search GUI(target row·top-k·2D Pareto·trade-off).
- **Stats (§15, MVP-5)** — *구현됨*: 5a 전부 + 5b(PCA/KMeans) + 5c 일부(UMAP). *필요*: ① **AN-SWEEP store 연결**(현재 입력이 sweep store와 미연결) ② `StatsConfig{groups,methods,fdr_method,seed,dimred,clustering}` + method/seed **manifest 기록**(dimred/clustering seed 하드코딩·미기록, `stats_embed.py:25,33,44`) ③ 5c volcano·advanced cohort ④ R stats figure export(boxplot/volcano/PCA/clustering heatmap).

---

## 6. 검증으로 기각된 주장 (기록 정리 — false positive)

분석 단계에서 High로 제기되었으나 적대적 검증 + green 테스트로 **반박**됨. 보고서에 포함하지 않음.

| 기각 주장 | 반박 근거 |
|---|---|
| "CLI에 TAB/4-space 혼용 IndentationError로 모듈 import 불가" (`cli/main.py:366`) | 전체 테스트 green·CLI 테스트 통과 → 모듈 정상 import |
| "DiagnosticCode enum 변경으로 stale 테스트 실패" (`test_diagnostics.py:47`) | green suite (테스트 실패 없음) |
| "search MAX/MIN_UPTAKE 목적 방향 반전" (`search.py:80`) | 검증자 재확인 반박 |
| "namespace hard gate가 solve 전에 enforce 안 됨" | `engine_service.py:101-102` `raise_if_blocked()` 직접 확인 |
| "run_hash #10(namespace decisions) 항상 빈값" | `engine_service.py:124` `namespace_decision_keys(decisions)` 배선 확인(단 producer 부재는 F-4로 별도) |
| "'highs' golden 변형 누락이 결함" | F1 결정문서로 정당화·spec amend 권고 사항(결함 아님) |

---

## 7. 권장 우선순위 (baseline 완성 관점)

1. **F-3 / 4-F GUI 통합** — baseline 최대 격차, 제품 사용성의 전제. (L, 다회 PDCA 권장)
2. **A(F-4) namespace 정합 producer** — §4.8 MVP-1a blocker의 실효성. (L)
3. **B(F-1) OSQP 라벨 정직화** — 과학적 재현성 신뢰. (M, 작은 변경·큰 효과)
4. **C(F-2)+D(F-5)+E(F-6) sweep/manifest 재현성 축** — G4·§7 완성, 통계(Extension)의 입력 기반. (M)
5. **H(F-8) minimal medium 결정성** — golden 안정성. (M)
6. **K(F-10) R export + L CI + M JobRunner** — 출판·자동화·안정성. (S–M)
7. Extension(§5)은 baseline 안정화 후 — 단 dFBA mass-balance·host 모델 mutation 버그는 작은 수정이므로 조기 처리 가능.
