# CMIG 코드 검토 및 조합 탐색 개선 계획

검토일: 2026-09-05 · 기준 커밋: `1d198ef` (`0.3.0`) · Python 3.12.11

후속 구현: 사용자 승인 후 F1–F9 수정 및 검색 실행·GA 개선을 적용했다.
[구현·검증 보고서](CMIG_search_implementation_2026-09-05.md)를 현재 상태의 기준으로 본다.
아래 분석과 수치는 수정 전 기준 커밋에 대한 기록이다.

## 판단

현재 GA는 기본 연산이 없는 초기 구현이 아니다. 고정 크기 swap, 가변 크기 add/remove/swap, seed, 중복 평가 캐시, random immigrant, 평가 예산, patience, 세대 기록, 최종 top-k에 한정한 FVA가 구현되어 있다. 개선의 우선순위는 **평가의 과학적 의미와 오류 수정 → 탐색 품질 측정 → 실행 복구·성능 → 다목적 확장**이다.

실행 코드와 기존 테스트는 수정하지 않았다. 이 문서는 코드 검토, 기존 테스트 실행, 메모리 내 합성 LP 및 GA 실험에 근거한 계획이다. 전체 코드의 무결성을 보증하는 감사는 아니며, 검색 경로를 가장 깊게 검토하고 배지 처리·실행 서비스·산출물·CI를 함께 점검했다.

## 구조와 유지할 기반

| 영역 | 주요 파일 | 판단 |
| --- | --- | --- |
| 진입점 | `cmig/cli/main.py`, `cmig/gui/app.py` | CLI 약 10,714줄, GUI app 약 3,205줄. GUI 검색이 CLI `main(argv)`를 직접 호출한다. |
| 조합·전략·평가·순위 | `cmig/core/search_product.py` | 조합 수 계산과 순회/샘플링 분리, 실패 후보 격리, 단일/다중 타깃 결과 처리. |
| 유전알고리즘 | `cmig/core/search_ga.py` | fitness 주입이 가능한 순수 탐색 계층. 교체보다 점진적 개선이 적합하다. |
| 과학적 목적식 | `cmig/core/search.py` | 성장 제약과 타깃 방향 정의. 아래 확인된 오류의 핵심 위치. |
| 모델·배지 | `engine.py`, `model_pool.py`, `medium_spec.py`, `boundary.py` | MICOM 위임, 엄격한 배지 적용, boundary 공급 차단 정책이 이미 존재한다. |
| 실행·재현 기록 | `service/jobrunner.py`, `workflow_manifest.py`, `io/atomic.py` | 작업 상태·취소 신호·manifest 기반은 있으나 검색 루프와 실행 복구 연결이 부족하다. |

정확한 조합 수 계산, 전체 조합을 만들지 않는 GA/random 경로, 실패 후보를 top-k와 무관하게 보존하는 처리, JSON 비유한 값 방어는 유지해야 한다. 과거 리뷰에서 지적되었던 항목을 현재 미구현으로 다시 분류하지 않았다.

## 확인된 오류와 개선 필요 사항

P1은 결과의 의미 또는 탐색 선택을 왜곡하는 문제, P2는 사용 경로가 제한되거나 운영·검증상의 문제로 구분했다. “재현”과 “코드 확인”을 별도로 표시했다.

### F1 · P1 · 요청한 k종과 실제 계산한 종수가 달라도 정상 조합으로 보고한다 — 재현

- 위치: `cmig/core/engine.py:168`, `cmig/core/search_product.py:384`, `cmig/core/search_product.py:412`.
- `build_community`는 MICOM의 기본 `rel_threshold=1e-6`를 사용한다. 검색 결과의 `members`는 실제 community 구성원이 아니라 입력 튜플이다.
- 번들 taxonomy의 두 행에 abundance `[1.0, 1e-8]`를 주고 exact-2 검색을 실행했다.
- 실제 `community.taxa`: `['Escherichia_coli_1']`.
- 결과 `members`: `('Escherichia_coli_1', 'Escherichia_coli_2')`, `status='optimal'`, `warnings=[]`.
- 이것은 “포함된 균주가 성장하지 않는다”보다 앞선 문제다. 해당 균주가 모델에 아예 없다.
- 계획: 후보 생성 전에 abundance 유효성을 검사하고, 모델 구성 후 requested/effective members를 대조한다. exact-k 불일치는 명시적 실패로 처리한다. threshold를 조정하는 기능은 과학적 정책으로 노출하고 hash에 포함한다. 작은 abundance를 임의로 올려 입력을 변경하지 않는다.
- 완료 기준: zero/tiny/NaN/negative abundance, MICOM 필터링, 실제 구성원 수 불일치를 회귀검증한다. 결과에 요청 구성원과 실제 구성원을 구분해 남긴다.

### F2 · P1 · Pareto 경로의 최소화 방향에서 물리적 부호가 뒤집힌다 — 재현

- 위치: `cmig/core/search.py:262`.
- `epsilon_constrained_solve`가 목적식 방향 보정 부호와 물리적 secretion/uptake domain을 하나의 `sign * flux >= floor` 제약으로 처리한다.
- `min_secretion`은 `-flux >= 0`이 되어 흡수를 허용하고, `min_uptake`는 `flux >= 0`이 되어 분비를 허용한다.
- 동일 합성 모델에서 일반 joint 경로는 두 최소화 방향 모두 flux 0을 반환했다. Pareto 경로는 `min_secretion: a=-10`, `min_uptake: a=+5`를 반환했다.
- CLI는 `--target-directions`로 네 방향을 모두 받으므로 사용자에게 도달하는 오류다.
- 계획: 물리적 domain은 기존 `target_flux_domain`으로 공통 적용한다. epsilon은 최적화 방향과 일치하는 상한/하한으로 별도 정의한다. 혼합 최소화/최대화의 epsilon 의미가 정해지기 전에는 지원 불가 조합을 명시적으로 거부한다.
- 완료 기준: 네 방향과 혼합 방향에 대해 joint/epsilon 경로의 부호·제약 일치를 검증한다.

### F3 · P1 · normalized 점수와 실제 최적화 목적식이 일치하지 않는다 — 재현

- 위치: `cmig/core/search_product.py:932`, `cmig/core/search_product.py:836`, `cmig/core/search_advanced.py:35`.
- LP는 `sum(weight * signed_flux / range_width)`를 최대화하지만, 최종 점수는 capability 최솟값을 빼고 `[0,1]`로 clipping한다.
- 상수 offset만 다르면 최적점은 같지만, clipping과 zero-range 처리까지 들어가면 같은 목적식이 아니다. joint 해는 독립 capability 최솟값보다 낮을 수 있다.
- 재현: `2a+b<=20`, `a,b>=0`, capability ranges `a=(8,10), b=(0,20)`, weights `(1,2)`.
- LP는 `(a,b)=(10,0)`을 택하고 표시 점수는 1이다. 같은 feasible set의 `(0,20)`은 표시 점수가 2다.
- 계획: LP와 보고 점수가 동일한 공통 scalarizer를 사용하도록 한다. 권고 기본안은 고정 기준의 `flux/reference_max` 또는 절대 단위 목적식이다. clipping을 유지할 경우 그 목적 자체를 최적화해야 하므로 별도 문제로 취급한다. 어떤 정책이든 zero-range와 최소화 방향 의미를 명시하고 manifest에 버전으로 기록한다.
- 완료 기준: 작은 feasible polytope의 꼭짓점을 직접 열거해 LP가 반환한 해가 **보고하는 점수**를 최대화함을 검증한다.

### F4 · P1 · GA의 동점 부모 선택이 구성원 이름에 편향된다 — 재현

- 위치: `cmig/core/search_ga.py:61`, `cmig/core/search_ga.py:254`.
- tournament에서 `(-fitness, genome)`의 최솟값을 선택한다. 점수가 같으면 항상 사전순으로 앞선 조합이 우선한다.
- fitness가 모두 0인 10개 단일-member genome으로 k=3 tournament를 10,000회 실행했다(seed 7).
- 선택 횟수: s00 2,995회, s01 2,306회, s07 89회, s08·s09 0회. fitness 근거가 없어도 특정 ID가 선택을 독점한다.
- 실제로 0점 후보가 많거나 실패가 많으면 이 규칙은 생물학적 정보가 없는 선택압을 만든다.
- 계획: 부모 선택의 동점은 seed 기반 무작위 선택으로 처리한다. 보고서 정렬의 사전순 tie-break는 유지할 수 있다. solver 수치 오차를 동점으로 볼 허용오차 정책도 별도로 정한다.
- 완료 기준: 동점 집단에서 위치 때문에 선택 확률이 0이 되는 후보가 없어야 한다. 같은 seed 재현성과 복수 seed 분포를 함께 검증한다.

### F5 · P2 · 현재 Pareto 결과는 제한된 표본의 비지배 집합이다 — 재현 및 코드 확인

- 위치: `cmig/core/search_product.py:685`, `cmig/core/search_product.py:1010`, `cmig/core/search_product.py:1184`, `cmig/core/search_product.py:1233`.
- 모든 타깃에 동일한 epsilon 비율 `0, .05, .15, .3, .5`만 적용한다. 조합을 전수 평가하더라도 각 조합의 목적 공간 전체를 탐색하는 것은 아니다.
- `2a+b<=20`, weights `(3,1)`에서 현재 표본은 `(10,0), (9.5,1), (8.5,3), (7,6), (5,10)`이다. 비지배 극점 `(0,20)`은 빠졌다.
- 비지배 판정은 이 표본끼리만 수행한다. 전체 front를 저장하지 않고 weighted sum 순서의 top-k로 잘라 반환한다.
- 계획: 결과를 sampled Pareto approximation으로 명시한다. 타깃별 극점을 먼저 확보하고 타깃별 epsilon sweep/적응형 세분화를 추가한다. 전체 archive를 저장하고 표시용 top-k와 분리한다.
- 완료 기준: 해석 가능한 2D/3D toy front에서 극점 보존과 coverage를 검증하고, top-k 변경이 전체 archive를 바꾸지 않아야 한다.

### F6 · P2 · 성장 불가 판정이 단일·다중 타깃 core 사이에서 다르다 — core 재현

- 위치: `cmig/core/search.py:159`, `cmig/core/search.py:243`, `cmig/core/search.py:338`.
- `target_max_solve`는 최대 성장률이 `1e-6` 이하이면 `non_viable`이다. joint/epsilon 함수에는 같은 gate가 없다.
- 성장 upper bound를 0으로 둔 toy model에 `mu_community=0`을 전달하면 single은 `non_viable`, joint는 생산 flux 10의 `optimal`을 반환했다.
- 범위 주의: 현재 제품 multi-target 경로는 single-target capability pass를 먼저 거쳐 일반적인 무성장 후보를 걸러낸다. 현재 CLI가 곧바로 이 사례를 통과시킨다고 주장하지 않는다. 직접 core API 사용 및 향후 capability-pass 최적화 시 노출되는 불일치다.
- 계획: baseline 유효성, non-optimal status, 성장 불가 판정을 공통 helper로 추출한다.

### F7 · P2 · GUI 검색에 배지·GA 예산 제어와 실행 중 취소 연결이 없다 — 코드 확인

- 위치: `cmig/gui/builder.py:440`, `cmig/gui/app.py:1643`, `cmig/service/jobrunner.py:162`, `cmig/core/search_ga.py:217`.
- GUI 검색이 넘기는 항목은 model-dir, target, strategy, size, top-k, FVA, out이다. 배지·seed·성장 fraction·GA 평가 예산은 이 경로에 연결되어 있지 않다.
- 검색 시작 전에만 취소 신호를 확인한다. core 검색/fitness 평가 루프에는 cancel/progress callback이 없어 실행 중 요청으로 다음 후보 평가를 막지 못한다.
- 계획: CLI/GUI가 공통 `SearchRequest`와 검색 서비스를 사용하도록 한다. 후보 평가 사이에 cancel check, 진행·예산·세대 상태를 제공한다. 단일 solver 호출에 대한 제한 시간은 별도 설정으로 둔다.
- 완료 기준: 취소 요청 후 새 후보가 시작되지 않아야 하며, GUI와 CLI의 동일 요청이 동일 effective 설정과 과학적 결과를 만들어야 한다.

### F8 · P2 · 검색 산출물 묶음이 원자적으로 게시되지 않는다 — 코드 확인

- 위치: `cmig/cli/main.py:6889`, `cmig/cli/main.py:7052`, `cmig/cli/main.py:7056`.
- CSV는 최종 경로에 직접 쓰고 JSON·그림은 순차 갱신한다. 같은 out에 재실행하다 실패하면 이전 manifest/그림과 새 CSV가 섞일 수 있다. JSON 한 파일의 atomic write만으로 run 전체가 보호되지는 않는다.
- 계획: 기존 solve writer의 staging/게시 패턴을 검색 산출물 전체로 확장한다. staging에서 digest와 파일 목록까지 검증한 후 게시하고, 실패 시 이전 완료 run을 보존한다.
- 완료 기준: CSV/그림/manifest 각 단계에 실패를 주입해 이전 완료 산출물의 일관성을 검증한다.

### F9 · P2 · `.sbml` 지원이 importer와 community 구성 사이에서 다르다 — 코드 확인

- 위치: `cmig/core/model_pool.py:17`, `cmig/io/model_import.py:69`, `cmig/core/engine.py:172`.
- CMIG는 `.sbml`을 검색 pool에서 발견하고 COBRA SBML importer로 읽을 수 있다. 그러나 community 구성은 해당 파일 경로를 MICOM에 그대로 넘긴다.
- 설치된 MICOM 0.39.0의 `util._read_model`은 대소문자를 정규화하지 않은 최종 suffix로 `_read_funcs`를 조회하며, 이 표에 `.sbml`이 없다. 따라서 plain `.sbml`은 import 진단을 통과해도 community 구성에서 실패한다. `.sbml.gz`는 마지막 suffix가 `.gz`라 이 특정 문제와 구분된다. 대문자 확장자에도 같은 dispatch 불일치가 있다.
- 계획: 지원 포맷을 실제 engine 경로까지 통합한다. 원본은 보존하고 지원되는 canonical 형식으로 변환한 모델 cache를 사용하거나, 지원하지 않는 형식을 preflight에서 구체적으로 거부한다.
- 완료 기준: 선언된 각 suffix와 대문자 변형에 대해 발견→진단→community build까지 end-to-end 검증한다.

## GA 성능에 대한 실험적 판단

30개 후보 중 정확히 3개 선택, 전체 4,060개 조합, 각 실행 200회 unique fitness 평가, seed 0–29, GA population 30, generations 상한 1,000, patience 없음. 모든 GA 실행은 실제로 200회 평가를 사용했다. random도 200개 서로 다른 조합을 평가했다. 전수 열거로 합성 목적식의 최적값을 구했다.

| 합성 목적식 | 최적값 | GA 최적 도달 | Random 최적 도달 | GA 평균 best | Random 평균 best |
| --- | ---: | ---: | ---: | ---: | ---: |
| 균주별 점수의 합 | 87 | 26/30 | 1/30 | 86.867 | 81.567 |
| 합산 점수 + 낮은 개별 점수의 특정 3종 동시 포함 시 보너스 200 | 206 | 0/30 | 0/30 | 86.867 | 81.567 |
| 특정 3종 동시 포함만 점수 1, 나머지 0 | 1 | 0/30 | 1/30 | 0 | 0.033 |

이는 실제 GEM의 품질 평가가 아니라 탐색 지형별 sanity check다. 0회와 1회의 차이로 random 우위를 주장할 수 없다. 관측으로 지지되는 결론은 **가산형 문제에서는 GA의 효과가 있지만, 그 테스트만으로 조합 시너지 탐색 품질을 입증할 수 없다**는 것이다. 희소한 해를 어떤 정책도 작은 예산으로 항상 찾을 수는 없다.

현재 `tests/test_search_ga.py:18`의 품질 검증은 좋은 member 포함 개수 기반이다. 다음 benchmark를 보강해야 한다.

1. 소형 실제 GEM pool을 전수 탐색해 정답/동점 집합을 만든다. 독립 생산자, 필수 donor-recipient, 경쟁, 영양요구 상보성 사례를 포함한다.
2. GA/random/restart/local-swap을 동일 **unique evaluation** 예산으로 비교한다. 상위 조합 도달률, regret, top-k recall, feasible 비율, wall time·peak memory를 기록한다.
3. 단일 seed 결과로 정책을 채택하지 않는다. 고정 seed 묶음과 개발에 쓰지 않은 검증 pool에서 개선을 확인한다.
4. 작은 순수 benchmark는 CI에, 큰 GEM benchmark는 별도 검증 작업에 둔다.

## 기능 개선 방향

### 1. “구성원”과 “활성·기여 구성원”을 구분

F1의 실제 구성원 누락을 고친 뒤에도, community growth floor만으로 모든 균주의 성장을 보장하지는 않는다. 현재 문서 `docs/USER_GUIDE.md:337`에도 이 제한이 명시되어 있다.

- `min_member_growth`와 선택적 absolute community growth floor를 추가한다.
- 결과에 균주별 성장, 활성 구성원 수, 실제 abundance를 포함한다.
- 최종 top 후보에 대해 leave-one-out 생산 변화와 단독 배양 대비 변화, 배지 민감도를 계산한다. 균주 제거 시 abundance 재정규화 정책을 명시해 contribution을 단순 인과효과로 과장하지 않는다.
- 필요하면 균주 수/배양 비용을 독립 목적 또는 제약으로 제공한다. 임의의 size penalty를 기본값에 몰래 추가하지 않는다.
- abundance 최적화는 조합 탐색 후 top 후보의 별도 2단계 분석으로 시작한다. 처음부터 혼합 이산·연속 GA로 확장하면 평가 예산과 해석 부담이 커진다.

### 2. 다양성을 측정한 뒤 탐색 정책을 개선

- `unique_genomes`는 이미 중복을 막는 population에서는 다양성 진단력이 약하다. member coverage, 출현 entropy, 조합 간 Jaccard 거리, 새 평가 비율, feasible 비율, size 분포를 추가한다.
- F4 수정 후 plateau 감지 시 mutation/immigrant 비율 조절과 부분 재시작을 비교 실험한다.
- tournament 크기와 elitism을 함께 조절하고, 공통 member를 보존하는 crossover·상위 해의 local swap은 실험 후보로 둔다. 성능 개선을 측정하기 전에 기본 동작으로 채택하지 않는다.
- 가변 크기의 초기 표집은 현재 size-uniform이다(`search_ga.py:164`). random 전략의 조합-uniform과 다르므로 size별 예산과 정책을 명시한다.
- 여러 seed를 하나의 benchmark/report로 실행하고 상위 조합 일치율과 점수 변동을 보고한다.
- 단독 생산능력이 낮은 균주를 일괄 제거하는 prescreen은 피한다. donor 등 cross-feeding 파트너가 사라질 수 있다. prescreen은 초기 population 일부를 구성하는 용도로 우선 사용한다.

### 3. 중단·재개 및 평가 비용 절감

- 전역 오류(가용 solver/라이선스, schema, 필수 모델 로딩)와 후보별 infeasible을 구분한다. 동일 전역 오류로 예산 전체를 소비하지 않도록 preflight를 추가한다. 후보별 생물학적 실패는 현재처럼 기록한다.
- 평가 ledger에 성공/실패 전체를 남긴다. 현재는 성공 후보 중 top-k 밖의 평가가 최종 결과에서 사라지고 cache도 메모리에만 있다.
- checkpoint에 population, fitness/평가 결과, RNG state, 세대, stagnation 상태, used budget, effective config, 입력 hash, 알고리즘 버전을 저장한다. JSON/SQLite/Parquet를 사용하고 solver 객체를 직렬화하지 않는다.
- 재개는 입력과 평가 정책이 같은지 검증한다. 목표는 같은 환경에서 중단 없는 실행과 같은 평가 순서·결과를 얻는 것이다.
- `build / medium / baseline / target LP / FVA`를 분리 계측한다. 큰 pool에 대한 실제 속도 개선 수치는 아직 측정하지 않았다.
- `_community_growth_star`는 성장률 하나를 얻으려고 cooperative tradeoff의 LP+QP를 수행한다. 설치된 MICOM 0.39.0 코드에서 확인했다. 번들 3종 모델에서는 cooperative와 plain optimize가 같은 성장률 약 0.8739215를 냈고, 3회 중앙값은 약 10.1ms 대 5.5ms였다. 대형 모델로 일반화하지 않으며, 상태·목적식 동등성 검증 후 baseline 전용 LP를 검토한다.
- 다중 타깃은 capability pass와 joint pass에서 community를 다시 만들고 target마다 baseline을 다시 계산한다. 같은 후보 내 불변 baseline 재사용부터 최적화한다.
- 이후 독립 worker process로 batch fitness를 평가한다. 입력은 모델 경로·hash·설정이고 worker별 community와 solver를 가진다. 세대 결과 합산은 요청 순서로 고정하고 전체 평가 예산, memory, solver thread 수를 함께 제한한다.

### 4. 다중 타깃 GA

현재 multi-target은 `search_product.py:1077`에서 exhaustive 한도를 넘으면 거부한다. 단일 타깃 GA 옵션을 다중 타깃이 사용하는 것처럼 노출하지 않는다.

- 1차 확장: 고정 절대 단위/고정 reference로 정의한 weighted joint LP를 scalar GA에 연결한다. 동적으로 바뀌는 observed-range를 fitness cache의 기준으로 사용하지 않는다.
- 2차 확장: 조합뿐 아니라 타깃별 trade-off 정책/epsilon도 평가 단위에 포함하고, 실제 동일 해에서 나온 flux vector를 대상으로 Pareto archive를 관리한다. 독립 타깃별 최댓값을 한 벡터로 묶지 않는다.
- NSGA-II의 비지배 순위와 crowding 기반 생존 선택은 후속 구현 후보다. 다만 이를 도입하는 것만으로 한 조합 안의 flux trade-off가 자동 탐색되지는 않으므로 위 평가 설계가 먼저다. [pymoo 공식 NSGA-II 문서](https://pymoo.org/algorithms/moo/nsga2.html)
- 기존 set genome의 cardinality, 필수/금지 member, incompatible pair 제약을 보존한다. 구조적 제약은 생성/repair 단계, 생물학적 feasible 여부는 solver 평가 단계에서 처리한다.

## 권장 구현 순서와 완료 기준

| 단계 | 작업 묶음 | 완료 기준 |
| --- | --- | --- |
| 1 | F1/F2/F3/F6: 평가 의미 수정 | 실제 k 검증, 방향 4종, 보고 점수와 목적식 일치, 성장 gate 공통화. 재현 예제가 회귀 테스트로 통과. |
| 2 | F4 및 GA benchmark | 동점 선택 편향 제거, exact/random/GA 동일 예산 비교, 복수 seed 결과와 diversity 지표. |
| 3 | SearchService·preflight(F9)·progress/cancel·ledger·checkpoint, F8 | 중단 후 새 평가 금지, 재개와 무중단 결과 일치, 실패 중 기존 run 보존. CLI/GUI가 같은 요청 계약 사용. |
| 4 | baseline/모델 구성 계측·재사용·선택적 병렬 평가 | 결과 동등성 유지, 실제 pool의 평가당 시간과 memory 개선 수치 확보, worker 수와 무관한 순위 재현. |
| 5 | 구성원 생존·기여도·배지 민감도, GUI 설정 | 실제 활성 member·배지·seed·예산 표시, 동일 GUI/CLI 요청 결과 일치, top 후보 사후 검증 출력. |
| 6 | F5 개선 및 multi-target GA | 극점과 전체 archive 보존, 제한된 front 근사임을 표시, joint-feasible vector, 소형 정답 대비 coverage 검증. |

단계 1의 오류 수정에서 결과가 바뀌면 알고리즘/목적식 policy 버전과 manifest에 반영한다. 기존 published 결과를 새 의미로 덮어쓰지 않는다. GA 정책 변경 역시 같은 seed의 평가 순서를 바꾸므로 버전으로 구분한다.

구조 정리는 SearchService 추출 시 함께 진행한다. CLI 파일 전체를 먼저 재작성하는 것은 권하지 않는다. 전략 선택은 `search_advanced.select_strategy`와 `search_product.choose_strategy`의 중복 정책을 정리하고, 사용되지 않는 MRO/MIP 경로의 역할을 명확히 한다.

CI에서는 `.github/workflows/ci.yml:66`의 license-free job에 순수 GA·조합 수·샘플링·설정 검증을 포함한다. 현재 full solver job은 같은 저장소의 PR만 실행하므로 fork PR에서 이 핵심 로직을 검사하는 범위가 좁다. Python 3.10/3.12 및 별도 process seed 재현 검증도 그 경로에 둔다.

## 검증 기록

- 기존 검색 관련 8개 파일: 122개 테스트 통과.
- `.venv/bin/python -m ruff check cmig tests scripts`: 통과.
- `.venv/bin/python -m mypy cmig`: 80개 source file 통과.
- 전체 `.venv/bin/python -m pytest -ra`: **1,470 passed, 18 skipped, 16 warnings**, 219.02초. Skip은 로컬에 없는 Recon3D/RECON1 외부 GEM 관련이다.
- 전체 테스트 종료 시 Qt WebEngine profile/page 수명 관련 경고가 3회 출력되었다. 종료 코드는 0이다. 실제 GUI 자원 누수 여부는 별도 추적 대상으로 두며, 이번에 확정한 결함으로 계산하지 않는다.
- F1–F4, F5의 극점 누락, F6: 위 조건으로 별도 재현. 기존 테스트 성공은 이 경계 사례의 정확성을 보증하지 않는다.
- 큰 AGORA2 pool의 GA wall time·memory·실제 최적 도달률은 이번 검토에서 측정하지 않았다.

### GA 비교 실험 재현

저장소 루트에서 다음 명령을 실행한다. 모델이나 산출물을 수정하지 않는 순수 합성 실험이다.

```bash
.venv/bin/python - <<'PY'
from itertools import combinations
from statistics import mean
from cmig.core.search_ga import GAConfig, genetic_search
from cmig.core.search_product import sample_candidate_combinations

ids = [f's{i:02}' for i in range(30)]
key = set(ids[-3:])
def additive(g):
    return sum(int(s[1:]) + 1 for s in g)
def synergy(g):
    return additive(g) + (200 if set(ids[:3]).issubset(g) else 0)
def sparse(g):
    return float(key.issubset(g))

for name, fit in [('additive', additive), ('synergy', synergy), ('sparse', sparse)]:
    optimum = max(fit(g) for g in combinations(ids, 3))
    ga_scores, random_scores = [], []
    for seed in range(30):
        result = genetic_search(ids, fit, GAConfig(
            min_size=3, max_size=3, pop_size=30, generations=1000,
            max_evaluations=200, seed=seed,
        ))
        assert result.evaluations == 200
        ga_scores.append(result.best_fitness)
        random_scores.append(max(fit(g) for g in sample_candidate_combinations(
            ids, 3, 3, n_samples=200, seed=seed,
        )))
    print(name, 'optimum', optimum,
          'GA hits', sum(v == optimum for v in ga_scores),
          'random hits', sum(v == optimum for v in random_scores),
          'means', mean(ga_scores), mean(random_scores))
PY
```
