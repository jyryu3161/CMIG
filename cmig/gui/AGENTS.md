# cmig/gui

## 범위

PySide6 데스크톱 앱.
- `app.py` — `CmigMainWindow`, 탭(Models / Search / Host / Dynamics / Graph / Profile), "Show Advanced Tools" 뒤의 고급 도구, 분석 버튼 → CLI argv 조립 → `JobRunner` 실행, run 디렉터리 읽기, 상태 표시줄, 문구 카탈로그 `I18N`.
- `builder.py` — Search 화면(`SearchView`), 커뮤니티 builder, constraint sandbox, scenario compare, delta 표.
- `editors.py` — 배지 편집기(설치본 preset 자원 읽기), 모델 관리자.
- `views.py` — profile·기여·heatmap 차트, sweep 화면, dFBA/spatial 화면.
- `host_view.py` — 숙주 영향 화면. `graph_view.py` — QtWebEngine + Cytoscape.js 상호작용 그래프(`assets/`).

범위 아님: 과학 계산, 산출 파일 작성, hash 계산. 모두 CLI가 한다.

## 경계

- 분석은 CLI argv를 만들어 `JobRunner`에서 `cmig.cli.main.main(argv)`로 실행한다. core 분석 함수를 GUI에서 직접 불러 결과를 만드는 새 경로를 만들지 않는다(산출물·manifest·종료 코드가 CLI와 달라진다).
- 결과 표시는 CLI가 쓴 run 디렉터리를 읽어서 한다. 산출물 무결성 판정은 `cmig.cli.main._inspect_run_dir`를 공유한다.
- `cmig/core`, `cmig/service`, `cmig/io`에 Qt 코드를 넣지 않는다.
- `graph_view.py`는 mypy 검사 제외 대상이다. 다른 GUI 파일은 strict mypy를 통과해야 한다.

## 불변식

- 화면에 보이는 설정은 그 설정을 쓰는 workflow에만 적용되고, 어떤 workflow에 적용되는지 화면이 알려 준다(예: cooperative tradeoff는 Strain Growth·Ratio, 방향·성장 하한·예산은 Search). 표시된 결과에 쓰인 설정을 바꾸면 그 결과를 무효로 표시한다.
- 과학적 결과 상태와 산출물 무결성(verified / mismatch / not recorded / 읽을 수 없음)을 따로 표시한다. 종료 코드 3인 실패 run도 manifest·원인·산출 경로를 열어 볼 수 있어야 한다.
- 손상된 manifest·summary를 읽다 난 예외가 읽기 경계 밖으로 새지 않는다. "읽을 수 없음" 상태로 표시한다.
- 그림 선택지는 run에 실제 있는 산출물만 보여 준다. 파일이 없거나 읽을 수 없으면 미리보기를 지우고 내보내기를 막는다. 미리보기는 SVG 종횡비를 유지한다.
- Pareto·다중 타깃 경고는 첫 줄만이 아니라 전체를 펼쳐 볼 수 있어야 한다.
- 긴 한 줄 문구나 숨은 탭의 최소 폭 때문에 창이 목표 크기(1280×800, 1500×950)를 넘어 강제로 커지면 안 된다.
- Sandbox preview는 Apply/Save 전까지 run artifact가 아니다.
- Search 설정은 `cmig search`와 동등하다(`--allow-failed-run`은 CLI 전용, `--solver`는 gurobi만 있어 노출하지 않음). GUI Search 기본값은 CLI parser 기본값과 같고(예외: 배지를 주면 exact가 GUI 기본), 적용 조건이 맞지 않는 설정은 argv에 넣지 않는다. 출력 폴더·merge 배지·unknown 허용·taxonomy/recursive는 Search 전용이며 Gene KO·Strain Growth·Ratio Impact는 모델 폴더, exact 배지, 임시 폴더를 쓴다. Gene KO top-k는 별도 칸(기본 20, 무효화 키 `ko_top_k`)이다.
- 출력 폴더를 지정하면 실행마다 새 `search-YYYYMMDD-HHMMSS` 하위 폴더를 만든다. 기존 폴더를 재사용하거나 덮어쓰지 않는다. 출력 폴더 값은 답을 결정하지 않으므로 결과 무효화·superseded 비교에 넣지 않는다.
- GUI가 넘기는 `SearchControl` 값은 argv보다 우선한다. solver thread처럼 양쪽에 있는 값은 둘 다 같은 값으로 넘긴다(아니면 실행과 provenance가 어긋난다).
- job의 CLI 오류 메시지는 GUI 스레드에서 한 번 설치한 스레드별 stderr router로만 모은다. job 스레드에서 전역 `sys.stderr`를 바꾸지 않는다.
- 후보 inspector는 run 산출물에 기록된 값만 보이고, 없는 값은 "not recorded"로 보인다(0으로 채우지 않음). 표 행과 기록은 기록된 rank나 flux 벡터로 맞춘다(pareto에서는 같은 members가 여러 행).
- Search 취소를 누르면 즉시 Cancel·Run 버튼을 끄고 pending 문구를 job이 실제로 끝날 때까지 유지한다.
- 배지 preset은 `importlib.resources`로 `cmig.resources/medium_presets`를 읽는다(소스 checkout 경로에 기대지 않음). 미리보기는 자원 파일을 수정하지 않는다.

## 구현 패턴

- `app.py`의 문구는 `I18N` 카탈로그 키로 넣고 `self._message(key, ...)`로 꺼낸다. `builder.py`, `views.py`, `host_view.py`는 영어 문구를 코드에 직접 쓰고, `editors.py`의 `_editor_text`는 영어로 대체된다. 각 파일의 기존 방식을 따른다. `_message`는 활성 언어 카탈로그를 fallback 없이 조회하므로, 키가 `"ko"`에 없으면 `--lang ko`에서 `KeyError`가 난다. 한국어화는 더 진행하지 않으므로 새 키는 `"en"`에 영어 문구를 넣고 `"ko"`에도 **같은 영어 문구**를 넣는다(번역하지 않음).
- 장기 작업은 `JobRunner` + `JobsBridge`로 돌리고 완료는 타이머 poll로 받는다. UI 스레드에서 solve를 돌리지 않는다.
- 취소 표시는 협조적 취소의 실제 상태(요청됨 → 경계에서 멈춤)를 그대로 보여 준다.

## 테스트

- `QT_QPA_PLATFORM=offscreen`에서 실행한다.
- 비기본 설정(배지 경로, 방향, 성장 분율)이 해당 workflow의 argv에 실제로 전달되는지 recorder로 검사(`tests/test_gui_audit_regressions.py`, `tests/test_gui_editors_builder.py`).
- Search 동등성: `tests/test_gui_search_parity.py`(argv·기본값), `tests/test_gui_search_output.py`(출력 폴더·checkpoint), `tests/test_gui_search_inspector.py`(Pareto 그림·inspector), `tests/test_gui_search_cancel.py`(취소 pending). 새 GUI 테스트 파일에는 autouse `_deterministic_qt_teardown` fixture를 둔다(없으면 macOS에서 종료 시 segfault로 rc=139).
- 실패 run, 무결성 불일치, 손상 manifest, 없는 그림 선택 시 미리보기 초기화(`tests/test_app_shell.py`, `tests/test_gui_render.py`).
- 창 geometry 회귀는 전체 main window로 측정한다. offscreen 통과는 네이티브 시각 사용성 승인이 아니다.
