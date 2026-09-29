# cmig/service

## 범위

실행 조정 계층.
- `jobrunner.py` — `ThreadPoolExecutor` 기반 비차단 실행. submit/poll/cancel/retry/result, 진행률, `threading.Event` 협조적 취소. GUI·Sweep·Sandbox가 공통으로 쓴다.
- `search_service.py` — CLI와 GUI가 공유하는 탐색 요청(`SearchRequest`), preflight(모델 캐시 준비, 솔버 사용 가능성), `spawn` 컨텍스트 `ProcessPoolExecutor` 워커, 워커 붕괴(`BrokenProcessPool`) 처리.
- `engine_service.py` — solve facade. 기존 core/io 함수를 같은 순서·같은 인자로 위임만 한다.
- `outcome.py` — 한 solve의 산출 묶음 값 객체.
- `store.py` — `FileSystemStore`(`root/<run_hash>/` + `index.sqlite`). core의 `RunStore` Protocol 구현. 현재 어떤 CLI·GUI 경로에도 연결되어 있지 않다.
- `publication_benchmark.py` — 출판 벤치마크 묶음 실행.

범위 아님: 과학 계산(→ `cmig/core`), 인자 해석·종료 코드(→ `cmig/cli`), 위젯(→ `cmig/gui`).

## 경계

- PySide6를 import하지 않는다(Qt 비의존).
- `cmig.gui`, `cmig.cli`를 import하지 않는다. 의존 방향은 service → core/io 뿐이다.
- 새 계산 로직을 넣지 않는다. 필요한 계산은 core에 두고 여기서 호출한다.

## 불변식

- `run_hash`를 계산하거나 재구현하지 않는다. 항상 core가 쓴 manifest에서 읽는다.
- 솔버가 없어 실행하지 못한 결과는 `result`/`run_hash`를 `None`으로 비운다. 가짜 성공 금지.
- 취소는 협조적이다. `cancel()`은 이벤트만 세우며, job 함수가 `ctx.cancelled`를 후보/조건 경계에서 확인해야 멈춘다. 진행 중인 MICOM solve 1건은 즉시 멈추지 않는다. 이를 "즉시 취소"라고 표시하지 않는다.
- GUI job은 `cmig.cli.main.main(argv)`를 같은 프로세스에서 부르므로 `SystemExit`도 job 결과(종료 코드)로 잡는다.
- 탐색 워커 제출 순서와 결과 수집은 결정적이어야 한다: workers=1과 workers=N의 순위·점수·history가 같다.
- 재개는 요청 identity(입력 checksum, 정책 버전, 설정)가 checkpoint와 같을 때만 허용한다.
- Sandbox preview 결과는 store에 쓰지 않는다. `RunStore`는 commit(Apply/Save) 때만 호출된다.

## 구현 패턴

- 공유 요청은 frozen dataclass로 만들고 CLI·GUI 둘 다 같은 타입을 생성한다. GUI 전용 필드를 따로 두지 않는다.
- 워커로 넘기는 인자는 spawn 경계를 넘을 수 있는 단순 값(경로, dataclass)만.
- 저장은 stdlib `sqlite3`와 JSON만.

## 테스트

- `tests/test_jobrunner.py`: 취소·재시도·진행률·`SystemExit` 포착.
- `tests/test_search_service.py`: workers 1/2 동일 결과, 취소 후 재개가 연속 실행과 같은 순서·점수·history, 워커 붕괴 처리, preflight 실패.
- `tests/test_service_facade.py`: facade 결과의 `run_hash`가 manifest 값과 같음.
- `tests/test_filesystem_store.py`: store가 hash를 다시 계산하지 않음.
