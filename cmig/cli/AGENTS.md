# cmig/cli

## 범위

`cmig` 명령 전체. `main.py`에 parser 구성, 명령 함수(`_cmd_<name>`), 종료 코드 결정(`_exit_code_for_status`), workflow manifest 작성 호출, `inspect-run` 판독기(`_inspect_run_dir`), GUI↔CLI 대응표(`GUI_CLI_WORKFLOWS`)가 있다. `publication.py`에는 `model-quality`와 `publication-benchmark` 명령이 있다.

범위 아님: 과학 계산(→ `cmig/core`), 파일 파싱·네트워크·원자적 쓰기 구현(→ `cmig/io`), 워커 풀(→ `cmig/service`), R 실행(→ `cmig/render`). 명령 함수에 과학 계산을 새로 넣지 않는다.

## 경계

- `cmig.gui`는 `gui` 명령이 앱을 띄울 때만 지연 import한다. 그 외에는 GUI를 참조하지 않는다.
- GUI가 이 모듈의 `main(argv)`와 `_inspect_run_dir`를 같은 프로세스에서 직접 부른다. 이 두 함수의 시그니처와 반환 의미를 바꾸면 GUI도 함께 바꿔야 한다.
- 선택 의존성(엔진·렌더·통계)은 명령 함수 안에서 import한다. `cmig version`, `cmig workflows`, `cmig --help`는 엔진 없이 동작해야 한다.

## 불변식

- 종료 코드는 `_exit_code_for_status`가 정한다: 상태 `failed`만 `EXIT_ANALYSIS_FAILED`(3), `ok`·`degraded`는 0, `--allow-failed-run`이면 `failed`도 0. 인자·입력 오류는 분석 시작 전에 2로 끝낸다. 예상하지 못한 실행 실패는 1이다(`solve` facade 실패, `dfba` 엔진·쓰기 실패, `agora2-fetch` 일부 실패; 전부 실패는 3). 새 명령도 이 구분을 따른다.
- 과학적 실패에도 진단 산출물은 쓴다. 산출물이 있다는 이유로 성공 상태를 주지 않는다.
- manifest 작성이 실패해도 완료된 결과는 지우지 않는다. 대신 "run_hash 없음" 경고를 낸다.
- `inspect-run`은 판정을 다시 내리지 않는다. 종료 코드가 0이 아닌 경우는 `artifact_integrity: mismatch`뿐이다. 상태는 더 나빠지는 방향으로만 덮어쓰고 `status_source`로 출처를 밝힌다. 인식하지 못한 상태 값은 그대로 전달한다(`ok`로 바꾸지 않음). payload `schema_version`을 바꾸면 소비자 계약 변경이다.
- 배지를 받는 명령(`--medium`, 숙주 명령의 `--microbe-medium`/`--host-medium`, 배지 행렬의 `--mediums`)은 모두 `--exact-medium`도 받고 모드를 manifest에 기록한다(`tests/test_round7_exact_medium.py`가 집합을 검사).
- 솔버 선택지: `{gurobi, osqp}`는 `solve`, `solve-fixture`, `single`, `dfba`, `dfba-sensitivity`, `sandbox-fixture`뿐이고, 솔버를 받는 나머지 명령은 `{gurobi}`만. 멤버 flux 전체가 필요한 경로에 osqp를 추가하지 않는다. HiGHS·CPLEX는 선택지에 넣지 않는다.
- 새 GUI 분석 기능을 추가하면 `GUI_CLI_WORKFLOWS`에 항목(명령, 필수 인자, 흔한 옵션, 산출물, 예시)을 추가한다(`tests/test_workflow_map_coverage.py`가 검사).
- README와 사용 안내서에 적힌 `uv run cmig …` 줄은 이 parser로 해석 가능해야 한다(`tests/test_docs_commands.py`가 검사). 플래그를 바꾸면 그 문서들도 함께 고친다.

## 구현 패턴

- 명령 추가: `_cmd_<name>(args) -> int` + parser 등록 + `set_defaults(func=...)`. 결과 상태를 정한 뒤 `_exit_code_for_status(status, args)`로 반환한다.
- workflow manifest는 `cmig.core.workflow_manifest`의 builder로 만들고 kind별 구성요소를 모두 채운다. hash를 명령 안에서 직접 계산하지 않는다.
- 결과 파일은 `cmig.io.atomic` 또는 run 트랜잭션으로 쓴다.
- 오류 메시지에 원인과 다음 행동(예: `--exact-medium`, `cmig medium-gap`)을 적는다.
- `main.py`는 약 1.1만 줄이다. 새 명령 묶음은 `publication.py`처럼 별도 모듈에 두고 `main.py`에서 등록하는 방식이 분리 계획과 맞는다.

## 테스트

- 종료 코드: 성공 0, 입력 오류 2, 과학 실패 3, `--allow-failed-run` 0, 미지원 명령에 플래그 주면 2(`tests/test_run_status_reporting.py`).
- `inspect-run`: 무결성 불일치 → failed·3, `unknown` 유지, 손상 manifest(`tests/test_inspect_run_status_honesty.py`, `tests/test_inspect_run_workflow_manifest.py`).
- 새 hash 인자는 envelope golden 테스트와 함께(`tests/test_workflow_envelope_golden.py`).
- 문서 명령 파싱(`tests/test_docs_commands.py`), workflow 지도 커버리지.
