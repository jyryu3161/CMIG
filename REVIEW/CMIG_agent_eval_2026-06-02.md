# CMIG v3.0 — Agent-mode 자율 평가 테스트 캠페인 (2026-06-02)

> Claude Code가 실제 프로그램(CLI + headless facade + offscreen GUI)을 **스스로 구동**하여
> MICOM 모델링 기능 전반을 실제 GEM 3종으로 검증한 결과.
> 실행 산출물: `.run/agent-eval/` · 드라이버: `.run/agent-eval/{single_fba,build_decisions,pair_delta_sandbox,drive_gui}.py`

## 0. 그라운드 트루스 (직접 확인)
- 환경: Python 3.10.9, micom **0.39.0**, Gurobi 12 (academic, ~2026-11-12 만료), PySide6 offscreen
- 실제 GEM 3종 (저장소 최상위):
  - `Recon3D.xml` (28MB) — **human** GEM, host (rxn 10600 / mets 5835 / genes 2248 / exch 1560)
  - `iHN637.xml` (3.9MB) — *Clostridium ljungdahlii* 아세토젠 (rxn 785 / genes 637 / exch 95)
  - `iML1515.xml` (11MB) — *E. coli* K-12 (rxn 2712 / genes 1516 / exch 331)
- **결론: 자율 구동·평가 가능.** EngineService(Qt 비의존) + CLI가 GUI 로직을 전부 헤드리스로 노출, GUI는 offscreen 구동 + `widget.grab()` 스크린샷 가능.

## 1. 요약 (6 Phase, 전부 통과)

| Phase | 내용 | 결과 |
|---|---|---|
| 0 | version/solvers/golden verify + `pytest -q` | ✅ 전 항목 통과, **pytest exit=0 (~386 tests green)** |
| 1 | 실제 3종 model-review + 단일 FBA/pFBA | ✅ 3종 모두 optimal |
| 2 | namespace 게이트 해소 (suggest→resolve) | ✅ blocked True→**False**, coverage 100% |
| 3 | 커뮤니티 매트릭스 (fixture/실제 2종/pair/delta/sweep/sandbox) | ✅ 전부, 실제 2종 solve 성공 |
| 4 | 확장 (dFBA/search/host-Recon3D/stats) | ✅ 8개 서브커맨드 전부 |
| 5 | GUI offscreen 8탭 + 3툴바 + host + KO locale | ✅ **10/10** 뷰, 스크린샷 11장 |

## 2. Phase별 증거

### Phase 1 — 단일 GEM FBA (`single_fba.json`)
| 모델 | FBA growth | load(s) | peak RSS |
|---|---|---|---|
| iHN637 | 0.2245 | 0.62 | 345 MB |
| iML1515 | **0.8770** (교과서 *E.coli* 호기성 glucose 값과 일치) | 1.92 | 532 MB |
| Recon3D | 755.0 (optimal) | 6.08 | 1.13 GB |

### Phase 2 — namespace 게이트
- `namespace-suggest`는 **draft**(전부 `unresolved/high/target_id=null`)를 생성 → 게이트 하드 차단(설계대로).
- 게이트 통과를 위해 **테스트용 BiGG self-map**(`community_decisions.json`, 352 resolved) 생성.
  **(정직: 과학적 큐레이션 아님 — source BiGG id를 동일 id로 self-map.)**
- `evaluate_gate` → `blocked=False, coverage=100%`.

### Phase 3 — 커뮤니티 모델링
- **Fixture solve**: gurobi `run_hash=29844e29…` `flux_report_status=full`; osqp `c491a6a8…` `qp_only_approximate`.
  gurobi 재실행 run_hash **동일**(결정성 ✅).
- **실제 2종 solve (iHN637+iML1515, f=0.5)**: growth **0.7510**, `run_hash=1edaa452…`, full-flux.
  Profile: ac·etoh·co2 secretion / glc·o2 uptake (아세토젠 생리와 정합).
- **Pair**: synthetic = `mutualism` (MRO 0, MIP 1); 실제 2종 = `parasitism`
  (mono iHN637 0.224 / iML1515 0.877 → co 둘 다 ~0.751), MRO 0.5, MIP 13, status ok.
- **Delta**: status ok, growth_delta −0.229, **8 significant**(마스킹 없음).
- **Sweep**(f=0.3/0.5/0.7): growth 0.451 / 0.751 / 1.051 단조 증가. axis_tradeoff_f float64 per-column(TC-2 ✅).
  **cond-0001 run_hash = `1edaa452…` = 독립 실행한 실제 2종 solve와 정확히 일치** → run_hash/cache key 결정성 교차 입증.
- **Sandbox**: preview `run_hash=null`(미기록) / commit `run_hash=4ede5410…`(기록) — SC-8 preview 비오염 ✅.

### Phase 4 — 확장
- **dFBA** (e_coli_core, glucose 10, t=10): timecourse 177행, 고갈 후 solver-status 경고 노출(SC-DF4 정직 처리).
- **Search**: target-max `EX_ac` flux 13.36 optimal; advanced(ac,but) Pareto frontier 3, butyrate는 `missing`(거짓 0-success 아님).
- **Host(Recon3D human)**: host-fixture viable·biomass 35·scope=`synthetic_toy_host_not_human_gem_quantitative`(자기 표기);
  host-generic Recon3D 컴파트먼트 정상 파싱; host-benchmark solve 0.74s.
- **Stats**: stats-demo 2-group(fiber/western) + BH-FDR q=0.0286; stats-sweep gurobi(3)/osqp(3) cliff's delta(두 솔버 ≈동일, ~1e-15 노이즈).

### Phase 5 — GUI offscreen (`gui/*.png`, `gui_report.json`)
**10/10 뷰가 실제 데이터로 채워짐**:
| 뷰 | 데이터 증빙 |
|---|---|
| Models | iML1515 import → Explorer Models +1 |
| Run Fixture | JobRunner job=**done**, Profile 8행 로드 |
| Open Run (실제 2종) | Profile **26행**, graph **3 nodes / 85 edges**, run_hash 1edaa452, 상태바 표기 |
| Community | members {iHN637:0.5, iML1515:0.5}, tradeoff 0.50 |
| Medium | profile uptake 21행 → editor 21행 |
| Sandbox | preview status ok |
| Compare | delta status ok |
| Search | 6행(ac optimal / but **missing** 정직), Pareto 3 |
| HostImpact | viable, biomass 35, interface 4행 + cross-feed 2행 |
| KO locale | 한국어 윈도우 구동 |

`03-openrun-profile.png` / `08-search.png` 육안 확인: 3-pane 셸·색상 라벨(secretion녹/uptake청)·잡 패널·상태바 정상.
**(정직: offscreen = 실행/데이터바인딩 증빙. 사람 눈의 디자인 심미 평가 아님.)**

## 3. 기존 D-시리즈 버그 교차검증 (`CMIG_v3_debug_bughunt_2026-06-02.md` 대조)

| ID | 라이브 구동 관찰 | 판정 |
|---|---|---|
| **D-2** (osqp `full` 오기재) | 내 fixture-osqp manifest = **`qp_only_approximate`** (정상) | **재현 안 됨** — 해당 경로는 해소된 것으로 보임 (커밋 bf69fb4 추정) |
| **D-3** (pair infeasible→neutralism 오분류) | feasible co-culture만 만남(mutualism/parasitism, status ok). infeasible co 미발생 | 미트리거 (latent) |
| **D-7** (GA seed 비결정성) | auto 전략이 exhaustive로 라우팅(소규모), GA 경로 미진입 | 미트리거 (PYTHONHASHSEED 미변동) |
| **D-9/D-10** (host maintenance 누락/완화) | Recon3D는 `solve_generic_host` 경로, maintenance id override 미노출; toy는 ATPM=1.0 | 미트리거 (latent) |
| **D-11** (benchmark가 model.solver 변형) | host-benchmark 후 동일 객체 재solve 미수행 | 미검증 |
| **D-12** (dFBA clamp 질량보존) | dFBA 정상 종료, 고갈 step 균형 미측정 | 미트리거 (latent) |
| **D-4 inf-growth, D-5/D-18 hash NaN/inf, D-6 bounds, D-8 sweep cancel, D-13~D-21** | 정상 입력만 사용, 엣지 미유발 | 미트리거 (대부분 latent — bughunt 문서의 "현재 배선 미트리거" 평가와 일치) |

→ **bughunt 문서의 핵심 주장(대부분 latent/엣지 의존)이 라이브 구동으로 재확인됨**: 정상 경로에서는 silent success/오분류가 나타나지 않았다.

## 4. 본 캠페인에서 새로 관찰한 항목

### AE-1 (Low~Med) — `--fva --solver osqp` 조합이 solver `time_limit`을 "infeasible"로 오표기 → **수정 완료**
- 증거(수정 전): `solve-fixture --solver osqp --fva` → `cobra ... (time_limit)` → `FVAInfeasibleError: community FVA infeasible (fraction=0.5)` + 미처리 traceback(exit 1).
- 루트 원인 2건:
  1. `EngineService.solve_fixture/solve_community`가 `community_fva(...)`에 **요청 solver를 미전달** → gurobi 기본으로 community solver와 불일치(osqp 빌드 community가 time_limit 퇴화).
  2. `community_fva`의 capability 체크가 osqp의 명목 `lp=True`만 보고 통과시킴 — osqp는 §4.2상 QP-only approximate.
- **수정**(프로덕션):
  - `cmig/core/fva.py`: osqp를 **capability 단계에서 사전 거부**(`FVAUnavailableError`, infeasible 아님 — 정직성: capability 부재 ≠ 제약 infeasible). substring 매칭(D-13 안티패턴) 미사용.
  - `cmig/service/engine_service.py`: FVA에 실제 `solver` 전달(부수적으로 "FVA가 요청 solver 무시" 잠복 결함도 해소).
  - `cmig/cli/main.py`: `solve`/`solve-fixture`가 `FVAUnavailableError`를 catch → traceback 대신 **rc=2 + 명시 메시지**.
- **검증**: 신규 회귀 테스트 2개(`tests/test_community_fva.py`): osqp+FVA가 `FVAUnavailableError`로 raise(InfeasibleError 아님), CLI rc=2. 영향 테스트 55개 + **전체 스위트 exit=0**(회귀 없음).
- 수정 후 동작: `cmig solve-fixture --solver osqp --fva` → `FVA 미지원: community FVA 는 osqp 미지원 … --solver gurobi 를 사용하라` (rc=2).

### AE-2 (정보) — fixture sweep growth가 tradeoff_f에 불변
- fixture(e_coli 3-member) sweep은 f=0.3/0.5/0.7에서 growth 동일(sd=0); 실제 2종 sweep은 변동(0.45/0.75/1.05).
- 버그 아님(데이터 의존: fixture 군집 성장이 tradeoff에 포화). stats-sweep의 shapiro "range zero" 경고 원인.

## 5. 후속 작업 (사용자 요청: 전체 진행)

### 5.1 AE-1 수정 — 완료 (위 §4 AE-1 참조)
fva.py / engine_service.py / cli/main.py 3파일 수정 + 회귀 테스트 2개 + 전체 스위트 그린.

### 5.2 큐레이션 namespace 정량 community 분석 (`community-curated/`, `curated_namespace.py`)
- **큐레이션 방식(제품 의도 워크플로)**: iML1515·iHN637은 출판된 BiGG GEM → exchange metabolite id가 정규 BiGG id.
  이를 `known_targets`로 공급 → `suggest_namespace_decisions`가 **exact id match → RESOLVED(`bigg:` namespaced)**로 분류.
  Phase-2의 손수 self-map과 달리 엔진 자체가 "exact id match" 근거로 해소(진짜 큐레이션).
- 결과: per-model 합산 **426 resolved**, 중복 metabolite를 병합한 최종 decision 파일은
  **352 RESOLVED / 0 warned / 0 unresolved**, 게이트 `blocked=False` coverage 100%.
- 정량 solve(gurobi, f=0.5): growth **0.7510**, secretion h2o 31.9·co2 18.6·h⁺ 6.58·**etoh 3.75**·ac 1.14 (아세토젠 생리 정합), SCFA target acetate ui_flux +1.145.
- **Provenance 무결성 입증**: 큐레이션 run_hash `924ec1f9…` ≠ 자기맵 run_hash `1edaa452…`
  (taxonomy·medium·tradeoff·solver 동일, **namespace_decisions만 다름** → run_hash 11-구성요소에 namespace_decisions 포함 확인).
  수치(growth)는 동일 — decisions는 게이트/provenance에 영향, solve 수치엔 무영향(설계대로).
- **FVA 변형 완료**(gurobi, `solve-fva/`): 26/26 profile 행 FVA 실채움, `flux_report_status=full`, 불변식 `fva_lo ≤ net ≤ fva_hi` 전 행 성립(예: h2o net +31.9 ∈ [−15.8,+145.7], o2 net −11.2 ∈ [−50,0]). FVA는 분석 overlay라 run_hash 불변(11-구성요소 외) — no-FVA와 동일 `924ec1f9…`. (community FVA = ~352 exchange × 2 ≈ 704 LP 재최적화로 비용 큼 — 정상.)

### 5.3 D-7 GA 비결정성 재현 시도 → **재현 안 됨 (수정된 것으로 확인)** (`d7-ga/`)
- CLI 경로: `search-advanced-fixture --strategy ga --seed 7`을 PYTHONHASHSEED=1/2/3/42에서 실행 → 출력 **byte-identical**.
- 단위 재현(최악 시나리오): `genetic_search`에 **모든 genome 정확히 동일 fitness(4.0)** 부여, PYTHONHASHSEED=0/1/2/3/42/999 →
  `best_members`가 6회 모두 `["m0","m1"]`로 **결정적**.
- 근거: `search_ga.py:118` `final = sorted(set(pop)|set(cache), key=lambda g: (-fit(g), g))` — fitness 동률을 **genome 튜플로 2차 정렬**하는 전순서 tie-break → set 반복 순서(PYTHONHASHSEED) 무관하게 결정적.
- 판정: bughunt D-7(best_members가 HASHSEED 의존)은 현재 코드에서 **재현 불가 — 전순서 tie-break로 해소됨**(D-2와 함께 커밋 bf69fb4 추정).

## 6. 정직성 고지
- §5.2 큐레이션 decisions = BiGG exact-match(출판 GEM의 정규 id) → Phase-2의 손수 self-map보다 엄밀하나, 여전히 정량 생물학 검증이 아니라 namespace/provenance 워크플로 증빙.
- offscreen GUI = 실행·데이터바인딩 증빙, 디자인 심미 평가 아님.
- OSQP = `qp_only_approximate`, Gurobi = `full`로 구분.
- D-시리즈 "미트리거"는 "버그 없음"이 아니라 "정상 경로에서 미유발"; D-2·D-7은 라이브/단위로 **해소 확인**, AE-1은 본 캠페인에서 **수정**.

## 7. 산출물 인덱스
- `pytest-baseline.log` · `pytest-after-ae1.log`(AE-1 수정 후 전체 그린) · `single_fba.json` · `ns/community_decisions.json`
- `community/{fixture-gurobi,fixture-osqp,real-2member,sweep,sandbox-commit}/` + `pair_delta_sandbox.json`
- `ext/{dfba,search,search-adv,host-fixture,host-generic,host-bench,stats-demo,sweep2,stats-sweep}/`
- `gui/00..10-*.png` (11장) + `gui_report.json`
- **후속**: `community-curated/{known_bigg_targets.txt,curated_decisions.json,solve-nofva/,solve-fva/}` + `curated_namespace.py`
- **후속**: `d7-ga/{hs-1,hs-2,hs-3,hs-42}/` + `d7_unit.py`
- **코드 수정(AE-1)**: `cmig/core/fva.py` · `cmig/service/engine_service.py` · `cmig/cli/main.py` · `tests/test_community_fva.py`(회귀 2건)
