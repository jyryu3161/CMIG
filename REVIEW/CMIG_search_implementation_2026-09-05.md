# CMIG 조합 탐색 개선 구현·검증

2026-09-05 · 수정 전 기준 `1d198ef` · Python 3.12.11 / MICOM 0.39.0

## 적용 결과

검토에서 확인한 F1–F9를 수정하고, 단일/다중 타깃 GA의 실행 복구·평가 기록·병렬화·GUI 설정과 상위 후보 사후 검증을 구현했다. 기존 solve 버전/골든은 유지하며, 결과 의미가 달라진 검색에는 `consortium_search_v2`, GA에는 `set_ga_v2`를 기록한다. 기존 seed의 구버전 결과와 새 검색 결과를 같은 정책으로 취급하면 안 된다.

| 검토 항목 | 구현 | 핵심 회귀 검증 |
| --- | --- | --- |
| F1 실제 구성원 누락 | abundance 입력 검증, requested/effective taxa 대조, 불일치 후보 순위 제외 | tiny/zero/negative/NaN/Inf abundance, 실제 MICOM 필터링 |
| F2 epsilon 부호 | 물리적 분비/흡수 domain과 방향 보정 utility 경계 분리 | 네 방향 및 혼합 최소화/최대화, 최소화 interior slice |
| F3 점수/목적식 불일치 | LP와 동일한 unclipped affine 점수, zero-width scale 1, 고정 reference 지원 | 해석 가능한 LP 꼭짓점 점수와 최적해 비교 |
| F4 동점 선택 편향 | 부모·생존 동점에 seed 기반 선택, 수치 동점 허용오차 | 모든 동점 후보 선택 가능, seed 및 checkpoint 재현 |
| F5 제한된 Pareto | 타깃별 극점, 독립 epsilon slice, 실제 feasible vector archive, 표시 top-k 분리 | 극점과 2D 내부 구간, top-k와 archive 독립성 |
| F6 성장 불가 불일치 | single/joint/epsilon 공통 non-viable gate | 최대 성장이 0인 모델의 세 경로 일치 |
| F7 GUI 실행 제어 | 배지·seed·예산·worker·성장 하한·timeout·다중 타깃·checkpoint·취소 | 요청 전달/결과 무효화 회귀 및 실행 서비스 테스트 |
| F8 산출물 혼합 | staging, writer lock, manifest digest 재검증, 게시 rollback | CSV/그림/manifest 실패 주입, rename 실패, 복구 실패 시 backup 보존, symlink |
| F9 모델 포맷 | 원본 보존 canonical JSON cache, importer/engine 경로 통합 | SBML/JSON/MAT 및 압축·대문자 변형의 실제 community build |

## 추가 구현

- `SearchRequest` / `SearchService`: typed 설정, 모델·solver/license preflight, exact medium 정책, 파일 입력/정책/런타임 identity 검증. GUI의 CLI adapter도 같은 서비스와 산출물 writer를 사용한다.
- JSON checkpoint: 성공·실패 평가 ledger, population, RNG, 세대, stagnation, fitness cache, 설정 identity, 사후 검증 결과. checkpoint 전용 writer lock. solver 객체는 직렬화하지 않는다.
- 재개 시 배지 경고와 FVA 결과/계측을 보존한다. worker batch의 앞선 완료 결과는 다음 worker가 비정상 종료해도 버리지 않는다. GUI/context로 주입한 checkpoint도 게시 디렉터리 내부에 둘 수 없도록 검증한다.
- 독립 process worker와 제출 순서 수집, solver thread 수/호출별 timeout. 후보 또는 batch 사이에 취소하며, 이미 실행 중인 solver 호출은 강제 종료하지 않는다.
- growth-only baseline LP와 다중 타깃 내 baseline 재사용. 모델 parsing cache와 build / medium / baseline / target LP / FVA 계측. telemetry는 과학적 점수와 RNG에 영향을 주지 않는다.
- GA diversity: member coverage/entropy, Jaccard 거리, feasible 비율, 신규 평가 비율, size 분포. Jaccard 계산은 최대 2,048쌍으로 제한한다.
- 부분 재시작, local mutation, 공통 member 보존 crossover는 선택 옵션이다. 성능 검증 없이 기본값으로 켜지 않았다.
- 다중 타깃 GA/random: 절대 단위 또는 고정 reference의 joint LP. Pareto 모드는 실제 해의 front/crowding을 조합 선택에 사용하며, 독립 capability들을 하나의 가상 해로 합치지 않는다. scalar patience는 Pareto 모드에서 비활성화한다.
- 균주별/군집 성장 하한, 같은 해에서 측정한 성장과 abundance. `--validate-top N`은 별도 예산으로 leave-one-out, monoculture, 배지 0.5×/2×, 개별 abundance 0.5×/2×를 비교한다.
- 새 산출물: `search_evaluations.json`, `search_ga_history.csv`, `search_pareto_archive.json`, `search_profile.json`, 선택적 `search_validation.json`.
- CI의 license-free 행렬에 순수 GA, checkpoint, benchmark, 조합 수/샘플링, CLI 설정, 게시 transaction 회귀를 추가했다. 사용자 가이드와 changelog도 갱신했다.

## 동일 예산 벤치마크

`scripts/benchmark_search.py`는 작은 문제의 전수 평가로 oracle을 만든 뒤 GA/random/restart/local-swap을 동일 unique-consortium 예산과 여러 seed로 비교한다. 알고리즘 시간은 oracle replay 비용이며 실제 GEM 처리량으로 오인하면 안 된다. GEM oracle 구성 시간은 별도로 기록한다.

설정·모델 checksum·결과의 기계 판독용 기록: [벤치마크 요약 JSON](CMIG_search_benchmark_summary_2026-09-05.json).

합성 실험: 후보 20개 중 정확히 3개, 전체 1,140개 조합, 평가 예산 100, seed 0–9, GA population 25. 표는 최적값 도달 횟수(10회 중)다. 모든 실행이 예산을 채웠다.

| 목적 지형 | Random | GA | Restart | Local swap |
| --- | ---: | ---: | ---: | ---: |
| 가산형 | 0 | 6 | 6 | 8 |
| 숨은 3종 시너지 | 1 | 0 | 0 | 0 |
| 희소한 시너지 신호 | 1 | 1 | 1 | 0 |
| 경쟁 페널티 | 1 | 5 | 5 | 6 |
| 성장 가능한 영역 제한 | 0 | 3 | 3 | 7 |

실제 GEM 실험: 저장소 `models`의 5개 GEM, 정확히 2종, 총 10조합, acetate 최대화, MICOM 기본 배지, growth fraction 0.5, seed 0–9, 예산 5, population 3. 전수 최적값은 약 **27.74850561**이며, GA/restart/local-swap은 각각 6/10회, random은 4/10회 도달했다. 평균 regret은 GA 계열 1.5154, random 3.7973이었다. oracle 구성은 이 로컬 실행에서 92.52초였다.

이 작은 실험으로 모든 GEM/배지 또는 희소한 cross-feeding 조합에서 GA가 우월하다고 결론내리지 않는다. 특히 숨은 시너지에서는 개선이 입증되지 않았다. donor를 단독 생산량만으로 제거하는 prescreen도 추가하지 않았다.

재현:

```bash
uv run python scripts/benchmark_search.py --pool-size 20 --size 3 --budget 100 \
  --seeds 0,1,2,3,4,5,6,7,8,9 --out runs/search_synthetic_benchmark.json
uv run python scripts/benchmark_search.py --model-dir models --target ac --size 2 \
  --budget 5 --seeds 0,1,2,3,4,5,6,7,8,9 --out runs/search_gem_benchmark.json
```

## 실행 시간·메모리 확인

동일한 실제 5-GEM pool, random seed 7, 2종 조합 3개 평가, solver threads 1로 CLI를 순차 실행했다. 이 단회 측정에서 end-to-end 시간은 worker 1의 **38.06초**, worker 2의 **33.33초**였다. 순위, 타깃 flux와 scientific run hash는 동일했다. worker별 build 시간의 합은 각각 15.73초/18.08초, baseline 합은 4.20초/4.15초, target LP 합은 4.14초/4.06초였다. 병렬 worker 시간의 합을 wall time으로 해석하면 안 된다.

macOS `/usr/bin/time -l`이 보고한 maximum RSS는 각각 1,143,521,280 / 1,000,079,360 bytes였다. 이것은 전체 worker의 동시 합산 메모리 측정이 아니므로 “병렬화로 메모리가 감소했다”고 주장하지 않는다. 큰 pool의 최적 worker 수와 aggregate memory는 실행 환경에 맞춰 측정해야 한다. 기본 worker는 1로 유지했다.

## 검증 상태와 해석 범위

전체 회귀 실행은 **1,537 passed, 18 skipped, 18 warnings**로 통과했다(248.99초). 이후 마지막 worker-completion 보존 보강은 `test_search_execution.py`와 `test_search_service.py`의 **24개 회귀 테스트**로 다시 검증했다. 이 24개에는 마지막에 추가한 worker 장애 테스트 1개가 포함되어 있다. 숫자를 합산해 전체 실행 건수처럼 표시하지 않는다.

- Ruff, strict mypy(89개 source file), release-version 정합성: 통과.
- 18개 workflow-envelope 골든: 변경 없음.
- GUI Search 패널은 offscreen 렌더링으로 1,180×850 배치와 새 제어 요소를 확인했다(최소 크기 945×722).
- skip은 로컬에 없는 Recon3D/RECON1 외부 GEM 테스트다. 이를 통과했다고 간주하지 않는다.
- Pareto는 유한한 sampled approximation이다. NSGA-II 표준 구현과 같다고 주장하지 않으며, frontier rank는 보고 순서다.
- abundance 결과는 시험한 국소 perturbation 중 최상값이다. 제거 후 재정규화와 시나리오별 성장 최댓값 재계산이 들어가므로 변화량을 단순 인과 기여도로 부르지 않는다.
- 과거 문서의 비용 목적함수·혼합 이산/연속 abundance GA 등은 후속 연구 후보이지 기본 과학 정책으로 추가하지 않았다. 현재 제공하는 것은 조합 탐색 후 명시적 사후 민감도 분석이다.
- checkpoint를 다른 모델/배지/정책에서 재사용하지 못하도록 차단한다. 강제 종료로 lock이 남으면 활성 writer가 없는지 확인한 뒤 사용자가 해제해야 한다.
