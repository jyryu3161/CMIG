# cmig/core

## 범위

헤드리스 과학 알고리즘과 엔진·솔버 어댑터. MICOM 호출(`engine.py`), 부호 변환(`sign.py`), namespace gate(`namespace.py`), 경계 격리(`boundary.py`), 배지 해석·적용(`medium_spec.py`, `medium.py`), exchange 물리량(`exchange.py`), 상호작용 추출·tidy(`interactions.py`, `tidy.py`), 조합 탐색(`search*.py`, `targets.py`), 숙주 결합(`host*.py`), dFBA(`dfba.py`, `dfba_community.py`, `spatial.py`), 통계(`stats.py`, `stats_embed.py`), sweep·sandbox·delta·pair·single, 재현성(`manifest.py`, `workflow_manifest.py`, `golden.py`, `workflow_envelope_golden.py`).

패키지 루트의 `cmig/golden_fixture.py`(golden fixture 캡처·검증 진입점, `python -m cmig.golden_fixture`), `cmig/synthetic_host.py`, `cmig/synthetic_pair.py`(정성 검증용 합성 모델 — 정량 해석 금지)도 이 범위의 규칙을 따른다.

범위 아님: 인자 해석·종료 코드·출력 디렉터리 배치(`cmig/cli`), Qt 위젯(`cmig/gui`), 작업 스레드·프로세스 풀(`cmig/service`), 모델 파일 파싱·네트워크·다운로드(`cmig/io`), R 실행(`cmig/render`).

## 경계

- `cmig.gui`, `cmig.cli`를 import하지 않는다. PySide6를 import하지 않는다.
- `cmig.service` 참조는 `search_product.py`, `search_multi.py`의 함수 내부 지연 import(탐색 워커)만 허용된다.
- `cmig.io`는 원자적 쓰기, 모델 로딩·캐시, manifest 보조 함수에 한해 쓴다. `cmig.io.atomic`은 `workflow_manifest.py`, `search_execution.py`, `sweep.py`, `interaction_figures.py`, `workflow_envelope_golden.py`에서 모듈 최상단 import이고(`cmig.io.atomic`은 core를 import하지 않으므로 순환 없음), 모델 로딩 등 나머지는 함수 내부 지연 import다.
- `cmig.render` 참조는 `interaction_figures.py`의 `cmig.render.figure_style`(공통 그림 스타일, 모듈 최상단)뿐이다. `cmig/render/__init__.py`가 `composer`를 import하고 `composer`는 core를 참조하므로, core에서 render의 다른 모듈을 최상단 import하면 순환 import 위험이 있다.
- MICOM·cobra·pandas·scipy 등 선택 의존성은 함수 안에서 import한다. `import cmig.core.sign`, `namespace`, `tidy`, `manifest`는 `pyarrow`만으로 성공해야 한다.

## 불변식

- `micom.Community` 생성과 `cooperative_tradeoff` 호출은 `engine.py`에서만 일어나며 `fluxes=True, pfba=True`의 public 옵션만 쓴다. CMIG solver 이름은 `gurobi`, `osqp`만 MICOM에 매핑된다.
- raw flux → (`ui_flux ≥ 0`, `uptake|secretion`)은 `sign.py`의 함수로만 만든다. `+` = 분비, `−` = 흡수.
- 반응 flux v를 대사체 이동량으로 바꿀 때는 경계 대사체 계수 c로 q = −c·v를 쓰는 `exchange.py` 경로만 쓴다. 반응 방향을 가정하지 않는다.
- 경계 격리는 `boundary.py`가 `model.boundary` 전체(exchange ∪ sink ∪ demand)를 기준으로 판단한다. 비-exchange formula-`X` 공급자만 열어 두고, formula가 비어 있으면 질량으로 본다. exchange는 formula와 무관하게 예외가 아니다.
- namespace gate가 `blocked`이면 MICOM을 호출하지 않는다. low-confidence 매핑을 자동 병합하지 않는다.
- 탐색 후보: taxonomy id 유일·비어 있지 않음, abundance 유한 양수(`validate_taxonomy`); 요청 멤버 = MICOM 실효 멤버(`actual_members`); μ\* ≤ `NON_VIABLE_GROWTH`(1e-6)이면 `non_viable`; 순위에는 유효 후보만.
- 다중 타깃 보고 점수 = LP 목적의 affine 척도, clip 금지. Pareto는 시도 ledger를 남기고 이전 feasible 점을 버리지 않는다.
- 숙주 전달이 식별되지 않으면 점값은 `None`, 구간과 이유를 보존한다. `.get(target, 0.0)`류로 채우지 않는다.
- `RUN_HASH_COMPONENTS`는 11개 고정, `compute_run_hash`가 유일한 solve hash 계산기다. `WORKFLOW_HASH_COMPONENTS`의 각 튜플은 `_EXPECTED_ARITY`와 개수가 같고 `workflow_kind`로 시작하며 `WORKFLOW_COMPONENT_VOCABULARY` 안의 이름만 쓴다(import 시 assert).
- 결과 의미를 바꾸는 정책 수정은 `NON_HASHED_PROVENANCE_MARKERS`의 표식 값을 올린다. 탐색 의미 변경은 `SEARCH_POLICY_VERSION`을 올린다.
- pool의 부분 커뮤니티를 평가하는 경로의 배지는 `PoolMediumCoverage`로 판정한다: `split`이 후보의 없는 id를 커뮤니티 해당 없음(`medium_not_applicable`)·pool 해당 없음(`pool_not_applicable`)·unknown(배지가 pool과 하나도 맞지 않을 때만)으로 나누고, 후보 멤버가 가진 id면 오류다. 후보에 배지 id가 하나도 닿지 않으면(pool은 대응) `split`이 거부해 그 후보는 failed다. 평가 전 거부(`check_namespace`, strict)는 하나도 맞지 않는 배지와 BiGG 표기 near miss(`near_misses`, 표기 함수는 `cmig.io.agora2.bigg_exchange_notation`을 호출자가 넘김 — core가 agora2에 의존하지 않도록)뿐이다. 읽을 수 없거나 exchange identity를 풀 수 없는 모델은 `unreadable`로 빠진다. coverage 없이 부르면 후보마다 기존 strict 규칙이다.
- 선택한 모델 전체를 한 커뮤니티로 푸는 경로와 단일 모델 경로의 배지는 `apply_medium_scoped`(판정만은 `scope_medium`)로 적용한다: 배지를 적용할 그 커뮤니티/모델 자체가 pool이며(`pool_medium_coverage({"selected": model})`), 대응 없는 id는 `not_applicable`(→ `medium_not_applicable_to_pool`), strict에서는 `check_namespace`(하나도 맞지 않음·near miss)만 거부하고, 아니면 그 id가 `not_applied`(→ `medium_unapplied`, degraded)다. 적용 자체는 `apply_medium_translated(strict=False)` 한 경로다. 표기 함수는 호출자가 넘긴다(`host_coupling.run_bigg_host_microbe(medium_notation=)`, `pair.analyze_pair(medium_notation=)`). 숙주 배지(`solve_bigg_host`)는 이 규칙 밖이다.
- 통계: 결정적 조건을 독립 반복으로 보지 않는다(replicate 열과 독립성 확인이 있을 때만 p-value). 분산 0·평균 상이의 효과 크기는 null + 진단.
- pickle 금지.

## 구현 패턴

- 실패는 예외나 상태값으로 명시한다. 지원하지 않거나 계산하지 못한 값은 0이나 성공으로 꾸미지 않고 `None`/상태/진단으로 남긴다.
- 파일 쓰기는 `cmig.io.atomic`의 `atomic_write_text` / `atomic_write_parquet` / `atomic_write_path`.
- 탐색 평가 함수는 spawn 워커에서 돌아가므로 top-level에서 pickle 없이 전달 가능한 인자(경로, 설정 dataclass)만 받는다.
- 결정성: 정렬된 키, seed가 있는 RNG, 동점은 seed로 깬다. 이름순 편향 금지.
- 모듈 docstring에 설계 근거·명세 절을 적는 기존 관례를 따른다.

## 테스트

- 부호: `tests/test_sign.py`의 기준 사례(−10→10 uptake, +8→8 secretion, −5→5 uptake, +3→3 secretion)는 반드시 통과.
- gate: 미해결 high-confidence 1건으로 차단, low-confidence는 경고 진행(`tests/test_namespace_gate.py`).
- 물리량: 정방향·역방향·비단위 계수 exchange에서 농도 변화와 숙주 흡수량이 같아야 한다.
- 경계 격리: 숨은 sink/demand 공급, formula-`X` pseudo-supply, formula 누락 모델.
- 탐색: 잘못된 abundance 거부, 멤버십 불일치 거부, non-viable 격리, 혼합 방향 점수 부호, Pareto 부분 timeout, checkpoint 재개 동일성(`tests/test_search_policy_v2.py`, `tests/test_search_execution.py`, `tests/test_search_ga.py`).
- hash: 구성요소 하나를 바꾸면 hash가 바뀌고 같으면 같다. 고정 golden hash를 테스트 없이 바꾸지 않는다(`tests/test_run_hash.py`, `tests/test_workflow_manifest.py`, `tests/test_engine_golden.py`).
- 과학 수치를 바꾸는 수정에는 정확한 수치 assertion 회귀를 추가한다. golden 허용오차를 완화하지 않는다.
