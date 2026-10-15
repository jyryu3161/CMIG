# 규칙

## 권위 순서

1. 사용자의 명시적 지시.
2. 수락된 결정 기록과 루트 명세서(`CMIG_명세서_v3.0.md`)가 **의도**를 정한다. 둘이 다르면 수락된 결정이 우선한다(솔버 역할, golden 변형, 숙주 구성 B).
3. 현재 코드·테스트·CI가 **구현된 동작**을 정한다.
4. `REVIEW/`, `docs/archive/`, `docs/00-pm/`, `docs/01-plan/`, `docs/release-drafts/`, `docs/decisions/`(2026-06 원본 결정 3건 — 현재 결정 기록은 `docs/tracking/decisions/`)는 과거 증거다. 여기 적힌 결론을 현재 결함·현재 규칙의 근거로 쓰지 않는다.

의도와 구현이 다르면 과학적 의미를 조용히 바꾸지 말고 차이를 보고한다.

## 의존성과 환경

- 환경은 `uv`로만 관리한다. `uv.lock`은 커밋되며 `uv lock --check`가 통과해야 한다. 이미 동기화된 환경에서는 `uv run --no-sync`로 실행한다.
- `micom==0.39.0`은 정확히 고정한다. MICOM 버전 변경은 gurobi·osqp golden을 모두 통과한 뒤에만 승격한다.
- `gurobipy>=12,<13`(라이선스 버전 일치), `mypy==2.1.0`은 고정이다.
- 기본 의존성은 `pyarrow` 하나다. 엔진·GUI·통계·렌더 의존성은 선택 extra이며 모듈 최상단이 아니라 사용 시점에 import한다. `engine` extra 없이 `import cmig`와 순수 로직(부호·namespace·tidy·manifest)이 동작해야 한다.

## 모듈 경계

- `cmig/core`, `cmig/service`, `cmig/io`는 PySide6를 import하지 않는다.
- `cmig/core`는 `cmig.gui`, `cmig.cli`를 import하지 않는다. `core`가 `service`를 참조하는 곳은 탐색 워커(`search_product`, `search_multi`의 함수 내부 지연 import)뿐이며 이를 넓히지 않는다.
- MICOM 호출은 `cmig/core/engine.py`를 통한다. MICOM에서는 public API와 문서화된 flux 반환 옵션만 쓴다. 불가피한 비공개 결합(현재: 버전별 pool/member 식별자 해석)은 버전 확인을 붙이고 검토 대상으로 표시한다.
- 모든 raw flux → (크기, uptake/secretion) 변환은 `cmig/core/sign.py`만 통한다.
- 경계 공급 판정(무엇이 모델에 질량을 공급할 수 있는가)은 `cmig/core/boundary.py`만 한다. `model.medium`이나 `model.exchanges` 열거로 격리를 대신하지 않는다.
- solve `run_hash`는 `cmig.core.manifest.compute_run_hash` 한 곳에서, workflow hash는 `cmig.core.workflow_manifest.compute_workflow_hash` 한 곳에서만 계산한다. service·GUI는 hash를 다시 계산하지 않고 manifest에서 읽는다.
- 파일 산출은 `cmig.io.atomic`(단일 파일)이나 `cmig.io.run_transaction`(디렉터리)을 쓴다. `Path.write_text`로 결과 파일을 직접 덮어쓰지 않는다.
- 구조가 규칙과 어긋난 곳을 발견하면 보고하고 검토를 받는다. 요청받지 않은 모듈 이동·재배치로 맞추지 않는다.
- GUI의 분석 실행은 CLI argv를 조립해 `cmig.cli.main.main`을 `JobRunner`에서 호출하는 경로를 쓴다. GUI 전용 계산 경로를 새로 만들지 않는다.

## 재현성 계약 변경

- solve hash 구성요소는 정확히 11개다. 추가·삭제·순서 변경은 금지다.
- workflow kind마다 구성요소 튜플과 기대 개수(`_EXPECTED_ARITY`)가 import 시점에 검사된다. 튜플을 바꾸면 개수도 함께 바꿔야 하며, 이것은 계약 변경이다.
- 계약 변경(구성요소 추가, canonical 직렬화 변경, 새 hash 인자 추가)은 envelope golden 재승인, `WORKFLOW_MANIFEST_SCHEMA_VERSION` 판단, `CHANGELOG.md` 기록을 한 변경 안에서 함께 한다. `cmig golden verify-envelope` drift를 재승인 없이 통과시키지 않는다.
- 결과 값을 바꾸지만 입력은 바꾸지 않는 정책 변경은 `NON_HASHED_PROVENANCE_MARKERS`의 해당 표식 값을 올린다(예: `..._v2` → `_v3`). 표식 없이 결과 의미를 바꾸지 않는다.
- 탐색·GA 의미가 바뀌면 `SEARCH_POLICY_VERSION`(현재 `consortium_search_v2`)과 GA 정책 이름을 올린다. checkpoint identity가 바뀌면 이전 checkpoint는 새 경로를 요구해야 한다.
  - 예외 기록(2026-10-14, `medium_policy` v3; 2026-10-15 출시 전에 v3의 의미를 "일부만 없으면 빼고 진행"으로 재정의하고 값은 그대로 둠; 같은 날 사용자 결정으로 같은 규칙을 모든 배지 workflow — 선택한 모델 전체를 한 커뮤니티로 푸는 workflow와 단일 모델 명령 — 로 넓혔고, v3가 아직 출시되지 않았으므로 값은 다시 그대로 둠. 이 확장은 탐색 경로를 바꾸지 않으며 solve·workflow hash 구성요소도 바꾸지 않는다): 배지 적용 규칙만 바뀌고 점수·GA·순위 규칙은 그대로인 변경(pool 단위 배지 판정)은 `SEARCH_POLICY_VERSION`을 올리지 않았다. 이 버전은 hash되는 `search_spec` 구성요소 안에 있어 올리면 입력이 같은 모든 탐색의 `run_hash`가 움직이기 때문이다. 대신 hash 밖 `medium_policy` 표식을 올리고 탐색 checkpoint identity(`search_identity`)에 `medium_policy`를 넣어 이전 checkpoint 재개를 막았다. 탐색 자체의 의미가 바뀌는 변경에는 이 예외를 쓰지 않는다.
- tidy 스키마(현재 1.3)나 AggregationStore 컬럼이 바뀌면 `schema_version`을 올리고 이전 번들 읽기를 유지한다.
- golden 허용오차·반올림 자릿수를 완화하지 않는다.

## 결과 표기

- 실패·non-viable·평가 불가·취소는 유효한 0 및 성공과 다른 상태로 남긴다. 순위·평균·최고값에 넣지 않는다. 실패 ledger와 경고, 종료 코드(0/2/3)를 유지한다.
- Gurobi full-flux와 OSQP QP-only 근사를 정확히 표기한다. OSQP 결과를 full-flux로 표시하는 코드는 결함이다.
- 과학적 성공과 산출물 성공을 구분한다. 산출물이 있다는 이유로 성공 상태를 주지 않는다.
- 미리보기(sandbox preview) 데이터는 Apply/Save 전까지 store·cache·sweep에 쓰지 않는다. 사용자 원본 GEM을 수정하지 않고, 임시 데이터를 결과로 게시하지 않는다.

## 직렬화

- pickle import 금지(Ruff `TID` 금지 API로 빌드 실패).
- 결과 산출은 Parquet/JSON/CSV/SVG/TIFF, 메타는 JSON/YAML/SQLite.

## 검증 게이트

변경을 마치기 전에 아래를 통과시킨다. 건너뛴 테스트나 존재하지 않는 테스트를 통과로 세지 않는다. 필수 tier에서 skip은 허용되지 않는다(선택적 외부 인간 GEM fixture skip은 부분 커버리지로 보고).

| 게이트 | 명령 | 필요 조건 |
|---|---|---|
| Lint | `uv run --no-sync ruff check .` (line-length 100, `E,F,I,B,UP,TID`) | 없음 |
| 타입 | `uv run --no-sync mypy cmig` (strict) | 없음 |
| Lock | `uv lock --check` | 없음 |
| 버전 정합 | `uv run --no-sync python scripts/check_release_versions.py` | 없음 |
| Envelope | `uv run --no-sync cmig golden verify-envelope` | 없음 |
| 무라이선스 테스트 | CI `quality` job의 테스트 목록 | 없음 |
| 묶음 | `uv run --no-sync python scripts/harness_checks.py --tier quality` | 없음 |
| Solver golden | `uv run --no-sync cmig golden verify` | Gurobi 라이선스 |
| 전체 | `QT_QPA_PLATFORM=offscreen uv run --no-sync pytest -q` | 모든 extra, Gurobi, fixture |
| 배포 | `uv build` 후 `uv run --no-sync python scripts/audit_distribution.py dist/*` | 없음 |

- 변경한 동작에는 그 동작을 검증하는 테스트를 추가한다. 과학 수치 변경은 정확한 수치 assertion으로 고정한다.
- `mypy` 예외 override(`disallow_untyped_calls=false`, `graph_view` ignore)는 `pyproject.toml`에 나열된 모듈에만 적용된다. 목록을 넓히지 않는다.
- README와 `docs/USAGE.md`의 모든 `uv run cmig …` 줄은 실제 parser로 검사되고 상대 링크도 검사된다. 명령이나 플래그를 바꾸면 두 문서를 함께 고친다.

## 버전과 릴리스

- 공개 버전 표면(`pyproject.toml`, `cmig/__init__.py`, `CITATION.cff`, `.zenodo.json`, `.claude-plugin/marketplace.json`, `uv.lock`)은 항상 같은 값이다. `vX.Y.Z` 태그에서는 확정된 CHANGELOG 제목과 실제 CITATION 날짜도 요구된다.
- 모든 사용자 영향 변경은 `CHANGELOG.md`의 `[Unreleased]`에 적는다. 계약 변경은 hash 이동과 비교 불가 범위를 명시한다.

## 커밋과 브랜치

- 사용자가 요청할 때만 커밋·푸시한다. 기본은 현재 브랜치(`main`)에서 작업한다.
- 기존 사용자 편집과 작업 범위를 보존한다. 다른 사람의 미커밋 변경을 되돌리지 않는다.

## 단계 실행기

- 단계(phase)는 `phases/<name>/`에 템플릿으로 만들고, 각 step은 `plan` / `implement` / `review` 역할, 정확한 읽기 파일, 소유 쓰기 경로, 실행 가능한 인수 검사 ID, 제한 시간, (plan·review는) 보고서 경로를 선언한다. 마지막 step은 review여야 한다.
- 모델 배정: `plan`·`review`는 `gpt-6-astra`, `implement`는 `gpt-6-sol`. 추론 강도 medium, 모델 fallback 없음.
- 완료는 실행기가 가진 상태와 독립 검사로만 판정한다. review가 `pass`를 반환해야 단계가 끝난다.
- 실행 전 `--dry-run`으로 검증한다. 사용자가 요청하지 않으면 실제 단계를 시작하지 않는다.
- 일상적인 구현은 기존 작업 승인으로 진행하고, 정말로 열린 선택만 묻는다.

## 사용자 인터페이스 문구

- GUI 한국어화는 더 진행하지 않는다. 새 UI 문구는 영어로만 쓰고 한국어로 번역하지 않는다. 기존 `--lang ko` 경로는 그대로 둔다.
- 문구 카탈로그 `I18N`에 새 키를 넣을 때는 `"en"`과 `"ko"` 양쪽에 넣고, `"ko"` 값도 같은 영어 문구로 둔다. 한쪽에만 넣으면 그 언어 모드에서 `KeyError`로 화면이 깨진다.

## 배지 preset

- `medium_presets/`가 원본이고 `cmig/resources/medium_presets/`는 설치본용 사본이다. 두 디렉터리의 파일 목록과 바이트가 완전히 같아야 한다(테스트로 검사). preset은 `python -m scripts.build_gut_media`로만 다시 만들고, 만든 뒤 사본에 똑같이 복사한다.
