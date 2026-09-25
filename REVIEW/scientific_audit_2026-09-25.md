# 과학 코어 감사 — 2026-09-25

검토자: GPT-6 Astra · 범위: `cmig/core`, 특히 균주 조합 검색과 연결된 과학적 의미 · 검토 기준 HEAD: `c45c836f0c12da04404a712f61f53bec0b346675`.

현재 검색은 **지정 배지·고정 상대 abundance·성장 제약에서 순분비/흡수 flux가 좋은 균주 집합을 찾는 문제**를 실제 community LP로 푼다. 단독 균주 점수나 pairwise MIP를 더해서 조합 성능을 대신하지 않는다. 최근 검색 수정의 핵심인 구성원 검증, 방향별 domain, 공동 feasible 다중 타깃 해, affine 점수, 재개·예산·worker 순서 보존은 소스와 아래 재현에서 확인했다. 반면 host 전달의 미식별 값을 0으로 바꾸는 문제, 동역학의 경계 공급 누락, 반대 방향 exchange의 부호 처리, 비표준 반응 이름의 flux 누락은 잘못된 과학 결과를 정상 결과로 낼 수 있다.

**확정 결함 8건: P1 3건, P2 5건.** P1은 지원 입력에서 과학 수치·해석을 잘못 보고하는 문제, P2는 일부 분석/라이브러리 경로의 정확성·진단·사용 가능성을 해치는 문제다. 수정은 구현하지 않았다. 이 보고서 외 저장소 파일을 수정하지 않았고 commit/push도 하지 않았다.

## 검증 기준과 증거

- 작업 중 생성된 루트 `AGENTS.md`/`CLAUDE.md`도 확인했다. 이 보고서는 지정 review 파일 소유권을 지키며, 재현 명령은 동기화된 환경에서 `uv run --no-sync`를 사용한다.
- 최신 `docs/USER_GUIDE.md`의 검색·FVA·배지·prescreen·Pareto 설명, `CMIG_명세서_v3.0.md` §4/§10/§12–15, `CHANGELOG.md` Unreleased 및 관련 수정 내역, `REVIEW/CMIG_search_implementation_2026-09-05.md`를 대조했다. 이전 리뷰는 현재 결함의 증거로 사용하지 않았다.
- Python 3.12.11, macOS 15.6 arm64, CMIG 0.3.0, COBRA 0.31.1, MICOM 0.39.0, optlang 1.9.0, gurobipy 12.0.3, OSQP 1.1.1. Gurobi 실제 LP/QP와 OSQP hybrid LP를 실행했다. HiGHS는 설치되어 있으나 별도의 adapter 문제를 SC-08에서 구분했다.
- 새 재현은 `/tmp`의 작은 합성 COBRA/MICOM 모델을 사용했다. 이들은 **제약·부호·전달 계약을 확인하는 수치 fixture**이며 화학적으로 검증된 생물학적 GEM이나 생물학적 효능 실험이 아니다.
- 코디네이터의 전체 baseline: **1,537 passed, 1 failed, 18 skipped, 총 1,556개**. 보존 로그: `.run/audit-20260925/baseline-pytest.log` 및 `/tmp/cmig-baseline-pytest-20260925.log`. 실패는 `tests/test_agora2.py::test_fetch_model_refuses_a_url_outside_the_publisher`이며 URL 거부 대신 SBML parse 오류가 발생했다. 이번 과학 코어 범위의 실패는 아니므로 전체 suite를 중복 실행하지 않았다.
- 이번 작업의 추가 pytest는 **9개 통과**: 네 방향 epsilon domain, 혼합 방향 bound, affine 목적식/점수 일치, non-viable gate, minimization Pareto 내부 slice, 실제 MICOM member-growth 하한/복원. `/tmp/cmig-scientific-targeted-pytest-20260925.log`. 아래 명령의 `-k`는 모든 지정 파일에 적용되어 execution/benchmark 파일의 테스트를 추가 실행한 것으로 세지 않았다.

```bash
uv run --no-sync pytest tests/test_search_policy_v2.py \
  -k 'epsilon_direction_domain or epsilon_mixed or reported_normalized or nonviable_gate or minimisation_pareto or member_growth_constraints' \
  tests/test_search_execution.py tests/test_search_benchmark.py -q
uv run --no-sync python /tmp/cmig_scientific_probes_20260925.py
uv run --no-sync python /tmp/cmig_search_probes_20260925.py
uv run --no-sync python /tmp/cmig_host_ambiguity_probe_20260925.py
```

각 스크립트 본문은 이 보고서 마지막 부록에 보존했다. 새 환경에서는 부록 본문을 해당 `/tmp` 경로에 저장하고 위 순서로 실행한다. 로그는 각각 동일 basename의 `.log`; environment는 `/tmp/cmig_scientific_environment_20260925.json`이다. 아래 행 번호는 검토한 HEAD 기준이다.

## 확정 결함

### SC-01 · P1 — 미식별 host 전달 구간이 0이라는 점 추정으로 바뀌어 KO 효과를 만든다

**위치:** `cmig/core/host_ko_impact.py:155`, `:109–122`; 같은 소비 패턴은 `cmig/cli/main.py:2288`의 host-search에도 있다. 올바른 upstream 구간 처리는 `cmig/core/host_impact.py:71–90`이다.

**유발 입력:** host가 acetate 또는 butyrate 중 어느 것으로도 같은 최대 objective 5를 달성하고, 두 미생물 공급 한도가 각각 5인 경우. baseline acetate uptake FVA는 `[0,5]`, butyrate 공급을 제거한 arm은 `[5,5]`이다. 모든 LP는 optimal이다.

**기대/실제:** baseline acetate 전달은 점으로 식별되지 않으므로 point와 point delta는 null이어야 한다. 실제 `host_impact`는 구간과 `ambiguous_metabolites`를 정확히 만들지만 `arm_from_coupling`의 `.get(target, 0.0)`가 이를 `target_transfer=0`으로 바꾼다. 실제 재현에서 `delta_target_transfer=5`, `delta_microbe_to_host={"ac":5}`, `comparable=true`, 양쪽 `run_status=ok`가 나왔다. 가능한 변화는 이 독립 구간 기준 `[0,5]`이며 정확히 +5라고 정해지지 않는다. 경고 문자열이 있어도 잘못된 finite 수치가 정당화되지 않는다.

**증거:** `uv run --no-sync python /tmp/cmig_host_ambiguity_probe_20260925.py`의 `PROBE baseline`, `no_but`, `delta`. 실제 host LP/FVA를 사용했고, community coupling result의 외곽 자료형만 `SimpleNamespace`로 구성해 core 변환 경계를 독립 재현했다. host-search CLI의 동일 패턴은 정적 확인이며 해당 CLI end-to-end 실행을 했다는 주장은 아니다.

**수정 방향:** 전달 point, interval, identifiable 상태를 `HostArm`까지 보존한다. objective 비교 가능성과 target-transfer 비교 가능성을 분리하고, 미식별 target의 point ranking/delta는 제외하거나 명시적인 interval/lower-bound 정책으로 처리한다. 서로 다른 arm의 interval 차이는 보수적 범위라는 의미를 표시한다.

**누락 회귀:** baseline `[0,5]` → arm `[5,5]`, 그 역방향, 양쪽 ambiguous, 실제 `[0,0]`의 구분. host-search target-transfer/weighted metric과 KO CSV/JSON까지 null 및 interval 보존을 확인해야 한다.

### SC-02 · P1 — community dFBA가 내부 sink의 미추적 공급을 놓치고 interpretable로 승인한다

**위치:** `cmig/core/dfba_community.py:431–436`의 `community.exchanges`만 닫는 loop, `:535–544`의 환경 exchange만 보는 미추적 uptake 진단, `:227–264`의 acceptance.

**유발 입력:** 한 멤버의 `SK_glc__D_c`가 음의 flux로 intracellular glucose를 공급하도록 `(-10,1000)` bound를 가진다. tracked `EX_glc__D_m` 농도는 0, 초기 biomass 0.1, `dt=t_end=0.1`, `close_untracked_uptake=True`.

**기대/실제:** 선언하지 않은 실제 물질 공급을 닫거나 명시적으로 추적하지 못한 경계 공급으로 판정해야 한다. 실제는 biomass **0.1 → 0.2**, tracked glucose **0 → 0**, `untracked_uptake={}`, `warnings=[]`, `acceptance.interpretable=true`였다. sink를 제거한 대조는 t=0에서 stalled다. 공통 `boundary.py`가 이미 sink/demand를 다루지만 이 경로가 사용하지 않는다.

**증거:** `/tmp/cmig_scientific_probes_20260925.py`의 `PROBE community_hidden_sink=True/False`. 실제 MICOM community와 pFBA 사용.

**수정 방향:** member 내부 sink/demand까지 포함한 전체 boundary에 공통 방향 인식 isolation을 적용하고, integrated solution에서 해당 공급량도 검사한다. formula-X pseudo-supply 예외는 현재 공통 정책을 유지해야 한다. 환경 exchange만 닫았다는 사실로 전체 경계가 격리됐다고 판단하면 안 된다.

**누락 회귀:** negative sink 및 positive demand 공급, pseudo-X 예외, forced supply, close 옵션 on/off를 포함한 community dFBA 테스트. off에서는 미추적 공급 경고·해석 불가, on에서는 미선언 mass supply 0을 확인한다.

### SC-03 · P1 — 반대 방향 exchange를 받아들이면서 동역학과 host readout은 raw 부호를 고정 해석한다

**위치:** `cmig/core/dfba.py:318`, `:342`, `:353–364`; `cmig/core/host_types.py:602–604`; `cmig/core/host_coupling.py:428–429`. 공급 bound 설정은 `boundary.set_supply_limit`이 방향을 인식하므로 같은 host solve 내부에서도 해석이 갈린다.

**유발 입력:** canonical metabolite ID `glc__D_e`를 가지되 exchange가 `--> glc__D_e`로 쓰여 **양의 flux가 흡수**인 합법적인 COBRA 경계 반응. single dFBA는 `S0=1`, `X0=0.1`, `vmax=10`, `Km=0.01`, `dt=t_end=0.1`; host는 microbial availability 5.

**기대/실제:** (a) dFBA에서 흡수는 농도를 감소시키고 Michaelis–Menten cap을 적용해야 한다. 실제 역방향 입력은 biomass 0.1→0.2, glucose **1→1.1**, `completed`, 경고 없음이다. 통상 방향 대조는 glucose 1→0.900990099, 성장률 9.900990099다. 코드는 uptake에 관계없는 lower bound를 바꾸고 raw +10을 환경 생산으로 적분했다. (b) host LP는 bound를 올바르게 열어 objective=5를 달성했지만 실제 흡수 +5를 `label=secretion`, `lumen_uptake={}`, FVA `[0,0]`로 보고했다. 통상 방향 대조는 uptake 5와 `[5,5]`다.

**증거:** 같은 과학 probe의 `single_dfba_reverse` 및 `host_reverse` 대조. 단순 예외나 solver 실패가 아니라 실제 optimal 해의 판독 오류다.

**수정 방향:** reaction orientation/stoichiometric coefficient에서 물리적 공급·외부농도 변화를 계산하는 공통 adapter를 사용한다. FVA의 두 endpoint도 그 좌표계로 변환한 후 순서를 정한다. 지원하지 않을 입력이라면 solve 전 명시 거부해야 한다. 부호 문자열을 통일하는 `sign.convert`만으로 raw reaction 좌표를 정규화할 수는 없다.

**누락 회귀:** 정방향/역방향 동등 uptake-cap 입력의 농도 감소·고갈·host 전달 불변성, non-unit stoichiometry, 양방향 exchange의 FVA. `host_impact` 산출물에서 흡수를 unused secretion으로 바꾸지 않는지까지 확인한다.

### SC-04 · P2 — 실제 대사체 대신 exchange 반응 이름으로 member flux를 집계한다

**위치:** `cmig/core/engine.py:286–293`; 관련 medium namespace 가정은 `cmig/core/medium_spec.py:255–263`의 `model_exchange_index`에도 있다.

**유발 입력:** 실제 exchange metabolite는 `glc__D_e` 그대로 두고 반응 ID만 `EX_carbon_e` 또는 `carbon_exchange`로 변경한다. MICOM은 이 모델을 실제 glucose pool에 연결하고 동일하게 solve한다.

**기대/실제:** 반응 이름 변경은 물질 정체성을 바꾸지 않아야 한다. 대조는 external/member 모두 `glc__D=-5`. `EX_carbon_e`에서는 external은 `glc__D=-5`지만 member와 tidy edge는 존재하지 않는 **carbon=-5**가 된다. `carbon_exchange`에서는 glucose member exchange/edge가 통째로 사라진다. 모두 `status=optimal`이며 full-flux 경로다. 같은 모델에 glucose medium을 적용하면 medium resolver도 "no counterpart … matched on metabolite"라며 실제 존재하는 glucose exchange를 찾지 못한다.

**증거:** 과학 probe의 `exchange_name=…`, `medium_name=…`. 모델 파일·실제 MICOM 해·`build_tidy`까지 실행했다. 이 증거는 canonical exchange 이름만 쓰는 모든 번들 모델에서 문제가 발생한다는 주장이 아니다. custom/noncanonical 모델을 받아들이는 core 경로의 결함이다.

**수정 방향:** community 구조가 연결한 pool metabolite 및 각 반응의 실제 metabolite를 권위 있는 mapping으로 사용한다. 이름 기반 inference가 불가피하면 사전 검증과 missing-flux 진단으로 fail closed한다. medium, engine, pool diagnostics가 서로 다른 문자열 parser를 사용하지 않도록 통합한다.

**누락 회귀:** 동일 metabolite의 exchange 이름 변경 전후 external/member/tidy 대사체 집합과 abundance-weighted 질량수지 불변성. donor/consumer 한쪽 이름만 다른 경우 cross-feeding이 사라지지 않는지 확인한다. 기존 dFBA `global_id` 수정은 해당 dFBA lookup을 고쳤지만 engine 전체의 대사체 의미를 고치지는 않았다.

### SC-05 · P2 — Pareto slice의 timeout/solver 실패가 ledger와 경고에서 사라진다

**위치:** `cmig/core/search_product.py:1244–1245`; `search_multi.py:253–271`, `:366–394`에서 성공 point 목록만 결과로 남는다.

**유발 입력:** 한 조합의 weighted slice는 optimal이고 후속 objective extremes/epsilon slices는 `time_limit` 또는 `solver_no_solution`이다. `_pareto_points_for_members`는 모든 non-optimal status를 expected infeasible slice와 동일하게 `continue`한다.

**기대/실제:** 수학적으로 불가능한 epsilon과 계산을 끝내지 못한 slice를 구별하고, 시도한 정책·solver status·진단을 보존해야 한다. 실제 failure-injection probe에서 16회 중 첫 회만 optimal, 나머지 15회는 `time_limit`이었지만 `ranks=1`, `unevaluated=0`, evaluation ledger에는 `optimal` 한 행만 남고 timeout 경고가 없다. 일반적인 "sampled approximation" 문구는 요청한 극점 계산이 실패했다는 사실을 전달하지 못한다.

**증거:** `/tmp/cmig_search_probes_20260925.py`, `PROBE pareto_partial_timeout`. 최초 해는 실제 LP이며 후속 status는 재현 가능한 mock 주입이다. 실제 wall-time timeout을 유발한 실험으로 표현하지 않는다. 정상 대조는 동일 모델에서 7개 frontier vector를 얻었다.

**수정 방향:** slice별 attempt ledger를 성공 point archive와 분리하고, infeasible/timeout/error 및 부분 완료를 명시한다. 성공 feasible point는 유지하되 후보 또는 run을 degraded로 표시하고 checkpoint에도 실패 시도를 보존한다.

**누락 회귀:** 일부 slice만 timeout, 모두 timeout, 실제 infeasible slice만 존재, optimal 뒤 exception. resume 후도 요청·완료 slice 수와 진단이 보존되어야 한다.

### SC-06 · P2 — 구형 `rank_consortia` API는 최신 구성원 검증을 우회한다

**위치:** `cmig/core/search.py:513–530`, 특히 `:525–528`.

**유발 입력:** 2개 member abundance `[1,1e-8]`, `sizes=(2,)`. MICOM이 작은 두 번째 member를 필터링한다.

**기대/실제:** 실제 한 member만 계산한 해를 2-member 결과로 표시하지 않아야 한다. 새 `search_model_pool`은 요청/effective mismatch로 순위 제외한다. 같은 입력의 `rank_consortia`는 `members=('s0','s1')`, score=10, `status=optimal`로 순위를 준다.

**증거:** 검색 probe `PROBE legacy_rank_filtered`의 두 API 대조. 실제 MICOM filtering을 사용했다. **현재 SearchService/CLI의 F1 수정이 실패한다는 주장이 아니라 남아 있는 공개 core API의 불일치**다.

**수정 방향:** 기존 함수를 안전한 product 평가에 위임하거나 동일 taxonomy/effective-members gate를 사용한다. 계속 유지할 이유가 없다면 명시적으로 deprecated/차단한다.

**누락 회귀:** 두 API에 동일한 tiny/zero/negative/NaN abundance 입력을 주고 rejection/mismatch 의미가 동일한지 검증. 결과에 requested/effective taxa를 보존한다.

### SC-07 · P2 — 분산이 0인 서로 다른 그룹의 Cohen's d를 효과 없음(0)으로 보고한다

**위치:** `cmig/core/stats.py:307–312`, `:329–332`.

**유발 입력:** `two_group_test([1,1,1], [10,10,10], parametric=True)`.

**기대/실제:** pooled SD가 0이므로 표준화 효과는 유한하게 정의되지 않는다. 미정의 진단/null 등을 사용해야 한다. 실제 결과는 `pvalue=0.0`, `statistic=-inf`, **`effect_size=0.0`, `effect_name='cohens_d'`**다. 평균 차이가 명확히 있는데 0 효과라고 표기한다. 표본 수가 부족한 직접 core 호출도 0으로 채운다.

**증거:** 과학 probe `PROBE constant_distinct_groups`; scipy precision-loss warning도 로그에 남는다. CLI의 독립 replicate 확인 gate와 별개이며, 독립성 확인이 zero-variance 정의 문제를 해결하지 않는다.

**수정 방향:** zero variance와 부족한 표본 수를 explicit unavailable effect로 표현하고 p/statistic 비유한성도 결과 상태에 반영한다. raw mean difference나 비모수 effect를 제공한다면 이름과 단위를 분리한다.

**누락 회귀:** 동일 상수 두 그룹, 서로 다른 상수 두 그룹, 한 그룹만 상수, n<2, 정상 분산. JSON/volcano 소비 경로에서 미정의를 0으로 바꾸지 않는지도 확인한다.

### SC-08 · P2 — HiGHS 설치를 사용 가능한 COBRA LP adapter로 오인한다

**위치:** `cmig/core/solver.py:72–82`, `cmig/core/single_model.py:38–66`.

**유발 입력:** 현재 환경처럼 `highspy`는 설치되어 있으나 optlang에 `highs` interface는 없고 `hybrid`/`osqp`가 존재하는 환경에서 `solve_single_model(model, solver='highs')`.

**기대/실제:** capability와 실제 solver 선택이 일치해야 한다. `capability_matrix()['highs']`는 `available=True, lp=True, milp=True`로 보고하고 `_require_lp`도 통과시킨다. 실제는 `model.solver='highs'`에서 `SolverNotFound`로 실패한다. 동일 toy의 `solver='osqp'`는 optimal, objective 10이다. **라이선스나 패키지 미설치 제약이 아니라 integration/capability 계약 결함**이다.

**증거:** `/tmp/cmig_solver_probe_20260925.log`; 재현 코드는 부록 D. MICOM community가 gurobi/osqp만 지원하는 문서화된 제한과 구별한다. 이 항목은 standalone core LP 선택 경로다.

**수정 방향:** 실제 optlang interface 및 해당 문제군 지원을 probe해 capability를 보고하거나 올바른 adapter를 구현한다. HiGHS의 native MILP 가능성을 이름이 다른 hybrid adapter의 MILP 가능성과 동일시하지 않는다.

**누락 회귀:** native package 설치와 adapter 존재를 분리한 capability matrix, 보고된 LP/MILP 경로의 최소 solve, 미지원 시 명시적인 capability 오류.

## 검색의 과학적 질문과 한계

현재 구현이 답하는 목적은 대략 `max Σ w_t u_t(v)/scale_t`, `Sv=0`, 모델/배지 bounds, `μcommunity ≥ max(f·μ*, absolute_floor)`, 선택적 `μmember ≥ member_floor`다. `μ*`는 해당 조합·배지·member floor에서 다시 계산된다. 방향은 secretion에 `v≥0`, uptake에 `v≤0`를 주고 최대화 utility로 변환한다. 따라서 toxin secretion을 줄이기 위한 `min_secretion`은 target uptake를 허용해 해독하는 목적과 같지 않다. 0이 가능하면 0이 정상 최적값이다.

| 질문/정책 | 실제 지원 및 해석 |
| --- | --- |
| 큰 pool 중 정확히 k개 선택 | 전체 조합을 계산하는 exhaustive 또는 budgeted GA/random. product 경로는 effective taxa mismatch를 배제한다. exact k는 k종 모두의 양의 성장·안정 공존을 뜻하지 않는다. |
| 세 종 이상의 metabolic complementarity | 후보 전체 MICOM LP가 직접 반영할 수 있다. pairwise 점수 가산으로 축약하지 않는다. 다만 탐색이 해당 조합을 방문해야 한다. |
| true synergy 자체 최대화 | 별도 synergy/null-model score가 없다. 큰 flux는 강한 단독 producer나 abundance 재정규화로도 얻는다. 사후 monoculture/leave-one-out 차이는 변화 조건의 민감도이지 인과적 기여·상호작용 차수 추정이 아니다. |
| abundance 동시 최적화 | 미구현 계획 범위. GA genome은 member set이며 abundance는 입력값을 선택 집합 내 재정규화한다. 사후 0.5×/2× 한 member perturbation은 국소 샘플이다. |
| 비용/제조 난도/균주 수 penalty | 비용 목적식·joint discrete/continuous abundance search는 없다. min/max size는 허용 집합만 정한다. 다른 크기끼리 abundance가 재정규화되어 단순 추가 기여로 비교할 수 없다. |
| 타깃별 임계·host viability 동시 제약 | core epsilon solver는 signed bound를 받지만 일반 SearchConfig/GUI의 사용자별 target threshold나 host-coupled fitness는 별도 구현되지 않았다. spec §14의 계획과 현재 제품 기능을 구분해야 한다. |
| prescreen/greedy/Bayesian | 자동 prescreen/greedy/Bayesian은 제품 검색 경로에 없다. `search_advanced.mro_mip_prescreen`의 pair 전용 helper와 enum은 실행 전략 증거가 아니다. 가이드의 2단계 수동 singleton prescreen은 donor 제거 위험을 명시한다. |
| Pareto | 실제 공동 feasible 벡터의 sampled frontier. objective extremes, 독립 slice와 balanced slice를 사용한다. 전체 연속 frontier·NSGA-II 동등성·전역 최적성 보장은 없다. 3+ 축에서는 독립 1축 slice가 모든 복합 trade-off를 다 채우지 못한다. |
| robustness FVA | 단일 target의 성장 허용 영역에서 가능한 flux 범위다. target 최적 생산량의 신뢰구간이나 실험 재현성 확률이 아니다. 방향 target LP와 달리 growth-only FVA는 반대 부호 영역도 포함할 수 있다. multi-target FVA 옵션은 CLI에서 명시 거부한다. |
| 배지·생존성 | custom medium의 exact/merge 선택이 질문을 바꾼다. default MICOM 배지는 생산 능력을 넓게 허용할 수 있다. positive objective가 실제 생물학적 성장임은 GEM objective 품질에 의존한다. |
| MIP/MRO·cross-feeding | MIP/MRO는 선택된 flux 해의 공발생/겹침 지표다. proportional shared-pool allocation은 abundance를 반영해 공급·수요를 보존하지만 donor→recipient의 실제 전달이나 인과적 synergy를 식별하지 않는다. |

고정 reference 또는 capability-range affine 점수는 LP에서 최적화한 점수와 일치한다. observed range는 pool-dependent이며 zero-width는 scale 1, fixed reference는 offset 0이다. carbon-equivalent는 탄소량 기반 flux 점수이고 yield, 농도, 누적 생산량과 다르다. 수치 단위가 같아도 배지·성장 fraction·abundance·GEM이 달라지면 질문이 달라지므로 조건을 함께 비교해야 한다.

## 이번에 직접 확인한 검색 품질·실행 특성

**실제 소형 MICOM 검색:** 같은 toy 4개에서 exactly 2개를 선택하는 6조합, exact glucose medium, `GrowthPolicy(0.1,0.2)`에서 worker 1과 2의 모든 평가 행·점수가 일치했다. GA는 seed 7, population 3, unique-consortium budget 5를 정확히 지켰다. 3개 평가 뒤 취소한 checkpoint를 재개한 결과는 uninterrupted 실행의 평가 순서/점수와 generation history가 일치했다. top 1 사후 검증은 별도 **11개 scenario 평가**를 기록했고 FVA도 재개 결과에 남았다. 별도 검증 횟수가 GA unique budget에 섞이지 않았다.

**다중 LP 검증:** `2a+b≤20` 실제 LP에서 top-k=1이어도 archive에는 7개 vector가 남았고 `(10,0)`, `(0,20)` 양극점 및 내부점이 모두 해당 제약을 만족했다. 독립 target maxima `(10,20)`를 공동 결과처럼 조합하지 않았다. 이는 검증한 fixture의 feasible-vector 보장이지 모든 수치 conditioning·solver backend의 검증이 아니다.

**새 동일 예산 benchmark:** 현재 `search_benchmark.py`를 실행했다. pool 12, exactly 3, oracle 220조합, unique budget 25, seed 0–4. 모든 method/seed가 budget을 채웠다. 아래는 최적값 도달 횟수/5이며 과거 구현 보고서의 숫자를 재사용하지 않았다.

| 합성 목적 지형 | Random | GA | Restart | Local swap |
| --- | ---: | ---: | ---: | ---: |
| additive | 0/5 | 2/5 | 2/5 | 2/5 |
| hidden synergy | 1/5 | 0/5 | 0/5 | 0/5 |
| sparse synergy | 1/5 | 0/5 | 0/5 | 1/5 |

증거: `/tmp/cmig_search_benchmark_probe_20260925.json`. 이 결과는 GA의 일반적 우월성을 지지하지 않는다. hidden synergy를 놓치는 현상은 명시적으로 근사 탐색인 현재 알고리즘의 **한계**이며 그 자체를 구현 버그로 분류하지 않았다. benchmark는 oracle replay로 알고리즘 품질을 비교하므로 실제 GEM 처리량·병렬 메모리 측정으로 해석할 수 없다.

```bash
uv run --no-sync python - <<'PY'
from cmig.core.search_benchmark import benchmark_search, synthetic_landscapes
ids = [f's{i:02}' for i in range(12)]
landscapes = synthetic_landscapes(ids)
for name in ('additive', 'hidden_synergy', 'sparse_synergy'):
    report = benchmark_search(ids, landscapes[name], min_size=3, max_size=3,
                              budget=25, seeds=range(5))
    print(name, report['summary'])
PY
```

실행 제어의 정적 확인: unique 조합 평가 실패도 budget에 포함하고, solver-call 수와 조합 수를 구별한다. 병렬 worker는 process를 분리하며 submission 순서로 수집한다. 취소는 candidate/batch 경계에서 협조적으로 수행하고 실행 중 solver를 즉시 kill하지 않는다고 문서화되어 있다. checkpoint는 JSON으로 config/model bytes/taxonomy metadata/배지 모드/runtime version/solver 설정 identity를 검증한다. seed만으로 서로 다른 solver 버전의 alternate optimum을 동일하게 만들지는 못한다. 큰 population/많은 Pareto point에 대한 archive 정렬의 시간·메모리 한계는 별도 scale benchmark가 필요하다.

## 모듈별 범위와 미검증 영역

표의 **동적**은 이번 작업에서 실제 실행한 범위, **정적**은 소스에서 검토한 계약, **인터페이스만**은 전체 동작을 검증하지 않았음을 뜻한다. 전체 baseline 통과를 모든 과학적 의미가 증명됐다는 뜻으로 쓰지 않는다.

| 모듈군 | 이번 검토/검증 | 잔여 제한 |
| --- | --- | --- |
| `search.py`, `search_constraints.py`, `search_product.py`, `search_multi.py` | 목적·방향·member/growth gate·joint/scalar/Pareto 정적 검토 + 실제 LP/MICOM probe·9개 회귀 | 모든 target 조합/conditioning/solver 비교는 미실행; SC-05/06 존재 |
| `search_ga.py`, `search_benchmark.py` | set 연산·cache·tie·budget·restart·local mutation·front/crowding 정적 검토 + 3지형×5seed×4method benchmark | 실제 대형 GEM pool 탐색 품질/최적성 미검증; GA size-uniform initialization과 random combination-uniform 차이는 가이드에 공개됨 |
| `search_execution.py`, `search_profile.py`, 연결 `service/search_service.py` | identity/lock/복구/취소/worker/timing 검토 + 실제 1/2 worker·취소/재개·budget | 강제 process kill, active solver timeout, 장시간 licence 소진은 이번에 재주입하지 않음 |
| `search_validation.py`, `search_advanced.py`, `fva.py` | 성장 policy/FVA·사후 perturbation의 고정 척도 검토 + 11-scenario 검증·FVA 기록 | real-community multi-target validation 전체 행렬, loopless genome-scale FVA 미실행 |
| `model_pool.py`, `engine.py`, `single_model.py`, `solver.py` | 파일 탐색·abundance·canonical cache 호출·status/readout·capability 검토 + 이름변경/구성원필터/solver probe | 모든 import 형식은 baseline에 의존; objective가 생물학적 biomass인지 자동 보증하지 않음; SC-04/08 |
| `boundary.py`, `medium_spec.py`, `medium.py`, `namespace.py` | exact/merge·sink/demand·pseudo-X·forced supply·alias 충돌·stereo 보존·gate·gap MILP 검토 + medium/exchange 방향 probe | 대형 AGORA2/Recon 전체 경계 재감사·medium-gap 최적성 별도 재실행 안 함 |
| `dfba.py`, `dfba_community.py`, `spatial.py` | bound/적분/고갈/acceptance 검토 + canonical/reverse/hidden-sink 대조 | 실제 장시간 community dt-convergence, spatial 렌더 미검증; spatial은 diffusion preview로 명시되어 full spatial dFBA가 아님 |
| `host.py`, `host_coupling.py`, `host_types.py`, `host_impact.py`, `host_ko_impact.py` | viability·biomass basis·interface·objective-fixed FVA·attribution·delta 검토 + 실제 작은 host FVA/역방향/미식별 probe | Recon3D/RECON1 대형 coupling·host-search CLI end-to-end 이번 미실행; SC-01/03 |
| `host_map.py`, `host_map_probe.py` | matching/normalization/admission 및 probe interface 정적 검토 | 큰 실제 GEM map의 생화학 identity·compartment 정답 외부 검증 없음 |
| `interactions.py`, `metrics.py`, `pair.py`, `matrix.py` | abundance 단위·보존 allocation·공발생 지표·mono/co 배지 비교 검토 + 실제 tidy edge probe | pair growth label은 mono 최대성장과 co tradeoff allocation의 비교이므로 특정 flux 정책 의존; 인과적 상호작용 증명 아님 |
| `stats.py`, `stats_embed.py` | replicate gate·aggregation·FDR·effect·PCA/UMAP/KMeans 입력 검토 + zero-variance probe | 반복측정/paired 설계·실험 독립성은 사용자 설계에 의존; 생물학적 cohort 추론 검증 아님 |
| `delta.py`, `sandbox.py`, `sweep.py`, `diagnostics.py` | 실패 전파·finite 검사·cache·bound preview/restore의 주요 계약 정적 검토 | 모든 bound rollback/취소·cache 조합 동적 재실행 없음 |
| `model_quality.py`, `tidy.py`, `manifest.py`, `golden.py`, `workflow_manifest.py`, `run_store.py` | objective 경고·질량검사 범위·schema·basis·hash 의미·store 계약 정적 검토 | artifact 전면 audit는 다른 검토 범위; MEMOTE/생화학적 타당성을 대체하지 않음 |
| `interaction_figures.py`, `workflow_envelope_golden.py`, `workflow_envelope_golden.json`, `__init__.py` | scientific-output/fixture/패키지 연결 interface 확인 | 렌더 구현·모든 envelope verifier 분기는 이번 과학 audit에서 전면 검증하지 않음; 코디네이터의 baseline/별도 감사에 위임 |

구조적으로 개선할 점은 exchange identity/orientation adapter의 통합, legacy 검색 API의 단일 경로화, `measured point / feasible interval / unevaluable`를 자료형에서 분리하는 것이다. 이번 SC-01/03/04/05가 서로 다른 계층에서 같은 정보 손실 양상을 보인다. 이는 코드를 고치지 않은 설계 권고이며 확인된 개별 결함과 구별한다.

배지·abundance·growth-floor 변화, 목표함수 변화, alternate optimum이 실제 생물학적 안정성·효능을 보증하지 않는다. 모델 예측을 실험적 synergy나 host 건강 개선으로 해석할 근거는 이번 감사에서 확보하지 않았다.

## 부록 — 재현 스크립트 원문

### A. boundary/sign/engine/statistics

저장 경로: `/tmp/cmig_scientific_probes_20260925.py`

```python
import json
from pathlib import Path
from dataclasses import asdict
import cobra
import pandas as pd
from cmig.core.engine import MicomEngine
from cmig.core.dfba import DfbaConfig, simulate_dfba
from cmig.core.dfba_community import CommunityDfbaConfig, run_community_dfba
from cmig.core.interactions import build_tidy

ROOT=Path('/tmp/cmig_scientific_fixtures_20260925'); ROOT.mkdir(exist_ok=True)

def toy(name='toy', *, sink=False, reverse=False, ex_name='EX_glc__D_e'):
    model=cobra.Model(name)
    e=cobra.Metabolite('glc__D_e', compartment='e', formula='C6H12O6')
    c=cobra.Metabolite('glc__D_c', compartment='c', formula='C6H12O6')
    ac=cobra.Metabolite('ac_e', compartment='e', formula='C2H3O2')
    for rid,stoich,bounds in [(ex_name,{e:1 if reverse else -1},(0,10) if reverse else (-10,1000)),('GLCt',{e:-1,c:1},(0,1000)),('BIOMASS',{c:-1,ac:1},(0,1000)),('EX_ac_e',{ac:-1},(0,1000))]:
        r=cobra.Reaction(rid); r.add_metabolites(stoich); r.bounds=bounds; model.add_reactions([r])
    if sink:
        r=cobra.Reaction('SK_glc__D_c'); r.add_metabolites({c:-1}); r.bounds=(-10,1000); model.add_reactions([r])
    model.objective='BIOMASS'; model.solver='gurobi'
    return model

def tax(model):
    path=ROOT/f'{model.id}.json'; cobra.io.save_json_model(model,str(path))
    return pd.DataFrame([{'id':'A','file':str(path),'abundance':1.0}])

def emit(label,value): print('PROBE '+label+' '+json.dumps(value,default=str))

for reverse in [False,True]:
    m=toy('reverse' if reverse else 'normal',reverse=reverse)
    cfg=DfbaConfig(initial_concentrations={'EX_glc__D_e':1.0},initial_biomass=0.1,t_end=0.1,dt=0.1,vmax={'EX_glc__D_e':10},close_untracked_uptake=True)
    result=simulate_dfba(m,cfg)
    emit('single_dfba_reverse='+str(reverse),asdict(result))
for sink in [False,True]:
    t=tax(toy('sink' if sink else 'nosink',sink=sink))
    cfg=CommunityDfbaConfig(initial_concentrations={'EX_glc__D_m':0.0},initial_biomasses={'A':0.1},t_end=0.1,dt=0.1,close_untracked_uptake=True)
    result=run_community_dfba(t,cfg)
    emit('community_hidden_sink='+str(sink),asdict(result))
for name in ['EX_glc__D_e','EX_carbon_e','carbon_exchange']:
    t=tax(toy('name_'+name,ex_name=name)); eng=MicomEngine(); comm=eng.build_community(t)
    r=eng.cooperative_tradeoff(comm,0.5)
    bundle=build_tidy(r)
    emit('exchange_name='+name,{'status':r.status,'growth':r.objective,'external':r.external_exchange,'members':r.member_exchange,'edges':bundle.edges.to_pylist()})
from cmig.core.host_coupling import solve_bigg_host
from cmig.core.stats import two_group_test
from cmig.core.medium_spec import MediumSpec, apply_medium_translated
for reverse in [False,True]:
    host=toy('host',reverse=reverse)
    result=solve_bigg_host(host,{'glc__D':5},exclude_metabolites=None)
    emit('host_reverse='+str(reverse),asdict(result))
for name in ['EX_glc__D_e','EX_carbon_e','carbon_exchange']:
    m=toy('medium',ex_name=name)
    try:
        tr=apply_medium_translated(m,MediumSpec({'EX_glc__D_e':5}),exact=True)
        emit('medium_name='+name,{'mapping':tr.mapping,'growth':m.slim_optimize()})
    except Exception as exc: emit('medium_name='+name,{'error':str(exc)})
emit('constant_distinct_groups',asdict(two_group_test([1,1,1],[10,10,10],parametric=True)))
```

### B. search/worker/checkpoint/Pareto

저장 경로: `/tmp/cmig_search_probes_20260925.py`

```python
from pathlib import Path
from dataclasses import asdict, replace
import json
import cobra
import pandas as pd
from cmig.core.engine import MicomEngine
from cmig.core.medium_spec import MediumSpec
from cmig.core.search import TargetSpec, Direction, rank_consortia
from cmig.core.search_constraints import GrowthPolicy
from cmig.core.search_product import SearchConfig, MultiTargetConfig, search_model_pool_multi
from cmig.core.search_execution import SearchControl, SearchCancelled
from cmig.core.search_ga import GAConfig
from cmig.service.search_service import SearchRequest, SearchService
ROOT=Path('/tmp/cmig_scientific_fixtures_20260925')
def emit(label,v): print('PROBE '+label+' '+json.dumps(v,default=str))
def reduced(result):
    return [(r.members, r.score if hasattr(r,'score') else r.weighted_score, r.target_flux if hasattr(r,'target_flux') else r.target_fluxes,r.status) for r in result.evaluations]
def tradeoff_model():
    m=cobra.Model('tradeoff'); p=cobra.Metabolite('p_c',compartment='c'); g=cobra.Metabolite('g_c',compartment='c')
    for rid,stoich,bounds in [('SOURCE',{p:1},(0,20)),('GROWTH_SOURCE',{g:1},(0,1)),('GROWTH',{g:-1},(0,1)),('EX_a_m',{p:-2},(-10,100)),('EX_b_m',{p:-1},(-10,100))]:
        r=cobra.Reaction(rid);r.add_metabolites(stoich);r.bounds=bounds;m.add_reactions([r])
    m.objective='GROWTH';return m
class ToyEngine:
    def build_community(self,taxonomy,cmig_solver='gurobi'): return tradeoff_model()
def main():
    tax=pd.DataFrame([{'id':f's{i}','file':str(ROOT/'nosink.json'),'abundance':1.0} for i in range(4)])
    medium=MediumSpec({'EX_glc__D_m':10})
    base=SearchConfig(target='ac',min_size=2,max_size=2,top_k=6,growth_policy=GrowthPolicy(0.1,0.2))
    request=SearchRequest(tax,base,medium,exact_medium=True)
    service=SearchService()
    r1=service.run(request,control=SearchControl(workers=1));r2=service.run(request,control=SearchControl(workers=2))
    emit('workers_equality',{'same':reduced(r1)==reduced(r2),'evaluations':reduced(r1)})
    ga=replace(base,strategy='ga',ga_config=GAConfig(pop_size=3,elitism=1,generations=10,max_evaluations=5),seed=7,robustness_fva=True,validation_top=1)
    req=replace(request,config=ga)
    complete=service.run(req)
    checkpoint=Path('/tmp/cmig_scientific_ga_checkpoint_20260925.json'); checkpoint.unlink(missing_ok=True)
    state=SearchControl(checkpoint=checkpoint);state.cancelled=lambda:len(state.records)>=3
    try: service.run(req,control=state)
    except SearchCancelled: pass
    resumed=service.run(req,control=SearchControl(checkpoint=checkpoint,resume=True))
    emit('ga_resume',{'same':reduced(complete)==reduced(resumed),'n':resumed.n_candidates_evaluated,'stop':resumed.ga_metadata['stop_reason'],'history_same':complete.ga_metadata['history']==resumed.ga_metadata['history'],'validation_n':resumed.validation_report['additional_evaluations'],'robustness':[(r.members,r.robustness_status,r.robustness_fva_lo,r.robustness_fva_hi) for r in resumed.ranks]})
    badtax=tax.iloc[:2].copy();badtax['abundance']=[1,1e-8]
    legacy=rank_consortia(MicomEngine(),badtax,TargetSpec('ac'))
    from cmig.core.search_product import search_model_pool
    safe=search_model_pool(MicomEngine(),badtax,base)
    emit('legacy_rank_filtered',{'legacy':[asdict(r) for r in legacy],'product_rank_n':len(safe.ranks),'product_fail':[r.diagnostic for r in safe.unevaluated]})
    cfg=MultiTargetConfig(targets=['a','b'],directions=dict.fromkeys(['a','b'],Direction.MAX_SECRETION),weights={'a':3,'b':1},min_size=1,max_size=1,metric='pareto',top_k=1)
    t=pd.DataFrame({'id':['toy']})
    result=search_model_pool_multi(ToyEngine(),t,cfg,control=SearchControl())
    emit('pareto_real_vectors',{'ranks':len(result.ranks),'archive':len(result.pareto_archive),'valid':all(2*r.target_fluxes['a']+r.target_fluxes['b']<=20+1e-7 for r in result.pareto_archive),'vectors':[r.target_fluxes for r in result.pareto_archive]})
    from unittest.mock import patch
    from cmig.core.search import epsilon_constrained_solve, MultiTargetSolveResult
    calls=[]
    def fail_slices(*args,**kwargs):
        calls.append(1)
        if len(calls)>1: return MultiTargetSolveResult({}, {},0,'time_limit','injected time limit')
        return epsilon_constrained_solve(*args,**kwargs)
    with patch('cmig.core.search.epsilon_constrained_solve',side_effect=fail_slices):
        result=search_model_pool_multi(ToyEngine(),t,cfg,control=SearchControl())
    emit('pareto_partial_timeout',{'calls':len(calls),'ranks':len(result.ranks),'unevaluated':len(result.unevaluated),'warnings':result.warnings,'evaluations':[asdict(r) for r in result.evaluations]})
if __name__=='__main__': main()
```

### C. host 전달 미식별성

저장 경로: `/tmp/cmig_host_ambiguity_probe_20260925.py`

```python
import json
from dataclasses import asdict
from types import SimpleNamespace
import cobra
from cmig.core.host_coupling import solve_bigg_host
from cmig.core.host_impact import host_impact
from cmig.core.host_ko_impact import arm_from_coupling, compute_host_ko_delta
cobra.Configuration().processes=1
m=cobra.Model('alternative_host_fuels')
a=cobra.Metabolite('ac_e',compartment='e'); b=cobra.Metabolite('but_e',compartment='e'); p=cobra.Metabolite('p_c',compartment='c')
for name,stoich,bounds in [('EX_ac_e',{a:-1},(-10,1000)),('EX_but_e',{b:-1},(-10,1000)),('acT',{a:-1,p:1},(0,1000)),('butT',{b:-1,p:1},(0,1000)),('BIOMASS',{p:-1},(0,5))]:
    r=cobra.Reaction(name);r.add_metabolites(stoich);r.bounds=bounds;m.add_reactions([r])
m.objective='BIOMASS'
results=[]
for label,available in [('baseline',{'ac':5,'but':5}),('no_but',{'ac':5,'but':0})]:
    host=solve_bigg_host(m,available)
    impact=host_impact(available,host)
    result=SimpleNamespace(host_result=host,impact=impact,community_status='optimal',community_growth=1.0,matched_exchanges={'ac':'EX_ac_e','but':'EX_but_e'},warnings=['not point-identifiable'] if impact.ambiguous_metabolites else [])
    arm=arm_from_coupling(result,label=label,target='ac')
    results.append(arm)
    print('PROBE '+label+' '+json.dumps({'objective':host.biomass,'ranges':host.lumen_uptake_ranges,'points':impact.microbe_to_host,'ambiguous':impact.ambiguous_metabolites,'arm':asdict(arm)}))
print('PROBE delta '+json.dumps(asdict(compute_host_ko_delta(*results))))
```

### D. 설치된 HiGHS와 COBRA adapter 구분

```bash
uv run --no-sync python - <<'PYTHON'
import cobra
from cmig.core.solver import capability_matrix
from cmig.core.single_model import solve_single_model
from cmig.io.model_import import load_cobra_model
print('optlang interfaces:', sorted(cobra.util.solver.solvers))
print('highs capability:', capability_matrix()['highs'])
m = load_cobra_model('/tmp/cmig_scientific_fixtures_20260925/nosink.json')
for solver in ('highs', 'osqp'):
    try:
        result = solve_single_model(m, solver=solver)
        print(solver, result.status, result.objective)
    except Exception as error:
        print(solver, type(error).__name__, str(error))
PYTHON
```
