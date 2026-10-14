# cmig/gui

## 범위

PySide6 데스크톱 앱. 프로젝트 폴더(`cmig-project.json`, `models/`, `media/`, `runs/`)를 중심으로 한 작업 공간이다.
- `app.py` — `CmigMainWindow`: 메뉴·도구줄·가운데 `QStackedWidget`(분석 화면·모델 표·모델 브라우저·run 결과·시작 화면), 분석 버튼 → CLI argv 조립 → `JobRunner` 실행, run 디렉터리 읽기와 화면 복원, 색인·검색 행 백그라운드 작업, Check Growth, 상태 표시줄(마지막 실행), 문구 카탈로그 `I18N`.
- `analysis_page.py` — 모든 분석 화면의 틀 `AnalysisPage`(제목·설명, 입력 카드와 Run/Cancel, `AdvancedSection`, `ResultsArea`, 복원 배너)와 입력 등록(`register`/`register_custom`, `snapshot`/`restore`), 계산값 강조(`paint_computed`, `mark_computed_headers`), flux 범례, 행 번호 숨김.
- `pages/` — 화면 하나당 모듈: `gene_ko.py`, `strain_growth.py`, `ratio_impact.py`, `host_search.py`, `spatial.py`, `tools.py`(`ToolPage`: Medium Editor·Sweep·Sandbox·Compare의 기존 위젯을 틀로 감쌈). Combination Search·Community Solve는 `builder.py`, Host–Microbe는 `host_view.py`, dFBA는 `views.py`(`DfbaView`)에 있다.
- `search_results.py` — 순위 결과 위젯 `SearchResultsPanel`(순위 표, 후보 inspector, 그림, 무효화). Search·Gene KO·Strain Growth·Ratio Impact·Host Search가 함께 쓴다.
- `model_browser.py` — 읽기 전용 모델 브라우저(반응·대사체·유전자·exchange 탭, 상세 이동)와 머리글(namespace 확인, 목적함수, Check Growth). `growth.py` — Check Growth run(`single_summary.json`) 판독(Qt 없음). `find.py` — 전역 검색 표·순위(`build_table`, `find`, Qt 없음)와 도구줄 검색 칸 `FindField`. `run_restore.py` — run이 어느 화면 것인지(`analysis_for_run`)와 복원 배너 문구(Qt 없음).
- `project_session.py` — 열린 프로젝트를 감싸는 Qt 계층: 변경 신호, undo/redo(모델·배지 편집만), run 목록(`inspect_run`, 실패·취소 표식 병합), 최근 프로젝트(`RecentProjects`).
- `sidebar.py` — MODELS/MEDIA/ANALYSES/RUNS 목록, 상태 기호, 끌어다 놓기, 우클릭 메뉴. `inspector.py` — 선택을 따르는 읽기 전용 상세 패널(모델·배지·run·분석, 솔버 표기, Copy Command). `activity.py` — 아래 작업 창(작업 표, 취소, 로그, `cmig` 명령).
- `pickers.py` — 모델·배지 선택기(`ModelPicker`, `MediumPicker`). 여러 모델 선택기는 메뉴 안의 목록(필터, 보이는 행에만 적용되는 Select All/None, 체크하는 동안 닫히지 않음)이고, 한 모델 선택기는 고르면 닫히는 메뉴다. `agora2_dialog.py` — AGORA2 카탈로그 검색·선택 창과 다운로드 크기 추정.
- `builder.py` — Combination Search 화면(`SearchView`), Community Solve 화면(`CommunityBuilderView`), constraint sandbox, scenario compare, delta 표.
- `editors.py` — 배지 편집기(설치본 preset 자원 읽기), 모델 관리자.
- `views.py` — profile·기여·heatmap 차트, sweep 화면, dFBA 화면과 dFBA·Spatial 공용 결과(`DynamicsResults`).
- `host_view.py` — 숙주 영향 화면. `graph_view.py` — QtWebEngine + Cytoscape.js 상호작용 그래프(`assets/`).

범위 아님: 과학 계산, 산출 파일 작성, hash 계산. 모두 CLI가 한다.

## 경계

- 분석은 CLI argv를 만들어 `JobRunner`에서 `cmig.cli.main.main(argv)`로 실행한다. core 분석 함수를 GUI에서 직접 불러 결과를 만드는 새 경로를 만들지 않는다(산출물·manifest·종료 코드가 CLI와 달라진다).
- 결과 표시는 CLI가 쓴 run 디렉터리를 읽어서 한다. 산출물 무결성 판정은 `cmig.cli.main._inspect_run_dir`를 공유한다.
- `cmig/core`, `cmig/service`, `cmig/io`에 Qt 코드를 넣지 않는다.
- `graph_view.py`는 mypy 검사 제외 대상이다. 다른 GUI 파일은 strict mypy를 통과해야 한다.

## 불변식

- 화면에 보이는 설정은 그 설정을 쓰는 workflow에만 적용되고, 어떤 workflow에 적용되는지 화면이 알려 준다(예: cooperative tradeoff는 Strain Growth·Ratio, 방향·성장 하한·예산은 Search). 표시된 결과에 쓰인 설정을 바꾸면 그 결과를 무효로 표시한다.
- 분석 화면 키는 13개다: `search`, `gene_ko`, `strain_growth`, `ratio_impact`, `community`, `host`, `host_search`, `dfba`, `spatial`, `medium`, `sweep`, `sandbox`, `compare`(`sidebar.ANALYSIS_GROUPS`의 네 묶음, `w.analysis_pages`). Check Growth의 분석 키 `check_growth`는 화면이 아니라 모델 브라우저다. 새 분석 화면은 `AnalysisPage` 틀을 쓰고, run이 기록·복원할 입력을 모두 `register`(또는 `register_custom`)한다. 등록하지 않은 입력은 `<run>-request.json`에 남지 않아 다시 열 때 돌아오지 않는다. 결과 기본값에 영향을 주는 Advanced 입력은 `advanced.track`에 넣어 "· N changed"에 세게 한다.
- 화면을 나눠도 같은 입력이면 같은 argv가 나와야 한다. `tests/test_phase2_argv_parity.py`의 `EXPECTED`는 고치지 않는다. 화면 구성이 바뀌면 `tests/argv_drivers.py`의 입력 설정 방식만 고친다.
- 공동체 결과 위젯(Profile | Graph, `community_result_page`)은 하나뿐이며, `_show_profile(host_key)`/`_host_community_result(host_key)`로 그 결과를 보이는 화면(`community`, `medium`, `sandbox`, `compare`)의 결과 영역으로 옮겨 다닌다. 옮길 때 이전 화면의 결과 영역은 비운다. Compare·Sandbox 겹쳐 보기는 불러 둔 run의 profile·targets·graph·배지를 지운다(`_blank_base_for_overlay`). 관계없는 run의 숫자를 비교 아래에 두지 않는다.
- 실패·취소된 run, 읽기에 실패한 결과, 프로젝트 전환은 그 화면의 이전 결과(순위·도구·공동체·Host·dFBA/Spatial)를 지우고 상태 줄에 사유를 적는다. 이전 결과가 지금 결과처럼 보이면 안 된다.
- run을 열면(`_open_run_entry`) 기록(`<run>-request.json`)으로 화면 입력을 먼저 복원하고 결과를 읽는다. 기록이 없거나 일부만 복원됐으면 그 화면의 지금 입력을 그 run의 입력처럼 표시하지 않는다(순위 화면은 "입력을 모름"으로 적는다). 결과를 보일 수 없으면 화면을 비우고 "No result shown for <run>: <사유>"를 적는다.
- 모델 색인(`models/.index/<sha256>.json`)은 브라우저와 전역 검색을 위한 보기·검색용 캐시다. 분석 입력, taxonomy, CLI 인자에 쓰지 않는다. 색인을 여는 일은 GUI 스레드에서 하지 않고 보이지 않는 조회 작업(`index_check`)이 하며, 쓸 수 없는 색인만 "Index Models" 작업이 다시 만든다.
- namespace 확인은 사용자의 명시적 동작(Confirm…)으로만 생기고 그 파일의 sha256에 묶인다(`cmig.io.project.confirmation_state`). Community Solve·Medium Editor의 "already BiGG" 확인란은 고른 모델이 모두 확인됐을 때만 미리 체크하고, 사용자가 직접 바꾼 상태는 그 화면의 모델 선택이 바뀔 때까지 둔다. Check Growth는 확인된 모델만 실행하고 `--assume-bigg-namespace`를 넘긴다.
- Check Growth 머리글은 실패·취소·판독 실패·무결성 불일치·성장 없음·FBA 비최적을 성장처럼 보이지 않는다. 목적함수 경고가 있는 모델의 값은 "Objective value"이고 "Growth"가 아니다(`growth.read_growth`).
- 계산값 강조는 유한한 숫자나 숫자 범위로 읽히는 칸에만 한다. 상태가 실패·경고·평가 불가인 행은 칠하지 않는다(`analysis_page.is_failed_status`).
- run 판독의 hash 계산과 AGORA2 카탈로그 조회는 `_run_off_thread`로 GUI 스레드 밖에서 하며, 그동안 사용자 입력은 대기열에 둔다(판독 중에 다른 run이나 프로젝트로 바뀌어 결과가 엉뚱한 입력 아래 보이는 일을 막는다).
- 과학적 결과 상태와 산출물 무결성(verified / mismatch / not recorded / 읽을 수 없음)을 따로 표시한다. 종료 코드 3인 실패 run도 manifest·원인·산출 경로를 열어 볼 수 있어야 한다.
- 손상된 manifest·summary를 읽다 난 예외가 읽기 경계 밖으로 새지 않는다. "읽을 수 없음" 상태로 표시한다.
- 그림 선택지는 run에 실제 있는 산출물만 보여 준다. 파일이 없거나 읽을 수 없으면 미리보기를 지우고 내보내기를 막는다. 미리보기는 SVG 종횡비를 유지한다.
- Pareto·다중 타깃 경고는 첫 줄만이 아니라 전체를 펼쳐 볼 수 있어야 한다.
- 긴 한 줄 문구나 보이지 않는 분석 화면의 최소 폭 때문에 창이 목표 크기(1280×800, 1500×950)를 넘어 강제로 커지면 안 된다.
- Sandbox preview는 Apply/Save 전까지 run artifact가 아니다.
- Search 설정은 `cmig search`와 동등하다(`--allow-failed-run`은 CLI 전용, `--solver`는 gurobi만 있어 노출하지 않음). GUI Search 기본값은 CLI parser 기본값과 같고(예외: 배지를 주면 exact가 GUI 기본), 적용 조건이 맞지 않는 설정은 argv에 넣지 않는다. 배지 적용 모드 제어는 화면마다 다르며 없는 제어는 argv에 넣지 않는다: Search는 배지 선택기와 고급 설정의 exact/merge·unknown 허용, Gene KO·Strain Growth·Ratio Impact는 같은 선택기를 쓰되 항상 exact, Host–Microbe·Host Combination Search는 숙주·미생물 배지 선택기와 unknown 허용, Sweep·Medium Editor는 각자의 exact 배지·unknown 허용 체크박스, Community Solve·dFBA는 배지 제어가 없다. Check Growth는 배지를 고르면 항상 exact로 적용한다. 모두 선택한 모델과 새 run 폴더를 쓴다. Gene KO top-k는 별도 칸(기본 20, 무효화 키 `ko_top_k`)이다.
- 분석은 열린 프로젝트가 있어야 실행된다. 모델과 배지는 프로젝트 선택기에서만 받는다(경로·폴더 입력칸 없음). 선택기는 `status`가 `ok`/`warning`이고 `integrity`가 `ok`인 모델만 고를 수 있게 하고, 실행 직전에 사본의 sha256을 다시 확인한다(`write_run_taxonomy`, `refresh_integrity`). 바뀌었거나 없는 사본이 포함된 실행은 거부한다. 모델·배지 선택은 답을 결정하는 입력이므로 Tools를 뺀 모든 분석 화면에서 바꾸면 표시된 결과를 무효화한다. Medium Editor는 배지 delta overlay만 지우고 Sweep은 화면 결과를 무효화하지 않는다(run마다 별도 폴더).
- 모델 입력은 `runs/_inputs/<run>-taxonomy.csv`(`id,file,abundance`)로 CLI에 넘기고(단일 모델 화면은 `--host`/`--model`, 편집한 배지는 `<run>-medium.json`), run 폴더 안에는 미리 쓰지 않는다. CLI가 run 폴더를 통째로 게시하기 때문이다.
- 출력은 항상 `runs/<kind>-YYYYMMDD-HHMMSS[-N]` 새 폴더이고 `--out`으로 넘긴다. 기존 폴더를 재사용하거나 덮어쓰지 않는다. 출력 폴더 입력칸과 임시 폴더 출력은 없다. 입력이 거부되면 미리 만든 run 폴더와 입력 파일을 지운다.
- 실패·취소된 job의 run 폴더는 지우지 않고 RUNS에 ✗/⊘로 남긴다. 재시작 뒤에도 같도록 `runs/_inputs/<run>-state.json` 표식(`failed`/`cancelled`)을 쓰며, 표식은 run 요약보다 나쁜 쪽으로만 반영한다. 읽기 거부(readback invalid)된 run은 RUNS와 상세 패널에서 ✗이고, 프로젝트 run이면 같은 자리에 `unreadable` 표식을 써서 재시작 뒤에도 ✗로 둔다(job의 `failed`/`cancelled` 표식은 덮지 않는다. 프로젝트 밖 run 옆에는 쓰지 않는다). 다시 읽어 성공하면 `unreadable` 표식만 지운다(`clear_run_state`).
- 툴바의 모든 항목은 메뉴에도 있다. 지금 쓸 수 없는 명령은 숨기지 않고 흐리게 둔다. Run(⌘R)은 가운데 화면의 Run 버튼을 누르며(`_run_buttons`, Sandbox·Compare는 없음), 그 버튼이 꺼져 있으면(job 실행 중·취소 대기) 함께 꺼진다. 화면 안의 Cancel은 Combination Search에만 있고, 다른 분석은 작업 창에서 취소한다. Rename…은 MODELS에서 모델 하나, Remove from Project는 하나 이상 선택했을 때만 켠다.
- 다른 프로젝트 열기·만들기는 대상을 먼저 잠그고 읽는다(만들기는 만든 뒤 잠근다, `ProjectSession.lock_and_open`/`create_and_lock`). 실패하면 열린 프로젝트와 그 job을 건드리지 않고 상태 표시줄(프로젝트가 없으면 시작 화면)에 알린다. 실행·대기 중인 job이 있으면 Close Project와 전환 전에 "N jobs are running — close the project anyway?"를 묻고(기본 No) Yes일 때만 취소한다. 프로그램 호출 `close_project()`와 창 닫기는 묻지 않는다.
- 모델 추가(여러 파일·폴더·끌어다 놓기)는 `JobRunner` 백그라운드 작업이고, GUI 스레드(끌어다 놓기 판정 포함)는 폴더인지와 파일 이름만 본다(`model_import_candidates`). 폴더 탐색과 `.json`이 모델인지 판별(`supported_model_paths`)은 import job 안에서 하며, 읽을 수 없는 폴더는 job 실패와 사유로 알린다. 자리 행은 놓은 이름으로 시작해 탐색이 끝나면 파일마다 하나로 바뀐다. job은 파일마다 사본·sha256·점검을 하며 실패한 파일만 `failed`와 사유로 격리하고 나머지는 계속한다. 모델 가져오기와 AGORA2 다운로드는 `models/` 쓰기 경쟁을 막으려고 한 번에 하나만 돈다. 같은 sha256의 모델은 거부한다. 취소 중에는 "cancelling (finishing the current file)", 끝나면 "cancelled (N of M not imported)"로 표시하며 solver 문구를 쓰지 않는다(AGORA2 다운로드는 "cancelling (download cannot be interrupted)").
- AGORA2 다운로드는 `agora2-fetch`(CLI)를 호출하고 매번 `models/agora2/<YYYYMMDD-HHMMSS>[-N]/` 새 폴더에 받는다. CLI가 호출마다 출력 옆 `agora2_manifest.json`을 새로 쓰므로(`docs/tracking/findings.md`), 폴더를 나눠야 이전 출처 기록이 남는다. 모델 항목의 원본 경로는 다운로드 URL이다. 카탈로그 캐시는 항상 프로젝트의 `models/agora2/agora2_catalogue.json`(`--catalogue`)이고 저장소 데이터 폴더에 쓰지 않는다. 1 GB를 넘거나 크기를 모르는 다운로드는 먼저 묻는다.
- `analysis_settings`에는 선택기 값만 저장한다. 키: `search`, `gene_ko`, `strain_growth`, `ratio_impact`, `community`, `host_model`, `host`, `host_search_model`, `host_search`, `dfba`, `sweep`, `medium`, `medium_single` 각각 `{"models": [id…]}`, 그리고 배지 참조 `search.medium`, `gene_ko.medium`, `strain_growth.medium`, `ratio_impact.medium`, `host.host_medium`, `host.microbe_medium`, `host_search.host_medium`, `host_search.microbe_medium`, `check_growth.medium`(`""` = 모델 기본, `preset:<이름>`, `medium:<id>`). 1단계 키(`growth`, `dynamics` 등)는 프로젝트를 열 때 `cmig.io.project.migrate_analysis_settings`가 새 키로 옮긴다. 저장된 모델이 더는 실행 불가하면 선택에서 빼고 상태 표시줄에 알린다. 선택은 사용자가 선택기를 바꿀 때만 저장한다(실행할 때 저장하지 않으므로 고른 적 없는 분석은 나중에 추가한 모델도 포함한다). 모델 이름 바꾸기(`rename_model`)는 `analysis_settings`의 `models` 목록 id도 같은 변경으로 바꾸며(새 id로 남아 있던, 제거된 모델의 기억은 먼저 지운다) undo는 바꾸기 전 설정을 그대로 되돌린다. 프로젝트는 편집할 때마다 `ProjectSession.save` → `cmig.io.project.save_project`로 원자적으로 자동 저장하며, 저장 실패는 상태 표시줄에 알리고 Qt로 예외를 올리지 않는다.
- GUI가 넘기는 `SearchControl` 값은 argv보다 우선한다. solver thread처럼 양쪽에 있는 값은 둘 다 같은 값으로 넘긴다(아니면 실행과 provenance가 어긋난다).
- job의 CLI 오류 메시지는 GUI 스레드에서 한 번 설치한 스레드별 stderr router로만 모은다. job 스레드에서 전역 `sys.stderr`를 바꾸지 않는다.
- 후보 inspector는 run 산출물에 기록된 값만 보이고, 없는 값은 "not recorded"로 보인다(0으로 채우지 않음). 표 행과 기록은 기록된 rank나 flux 벡터로 맞춘다(pareto에서는 같은 members가 여러 행).
- Search 취소를 누르면 즉시 Cancel·Run 버튼을 끄고 pending 문구를 job이 실제로 끝날 때까지 유지한다.
- 배지 preset은 `importlib.resources`로 `cmig.resources/medium_presets`를 읽는다(소스 checkout 경로에 기대지 않음). 미리보기는 자원 파일을 수정하지 않는다.

## 구현 패턴

- 새 표는 `analysis_page.hide_row_numbers`로 행 번호를 숨긴다. 계산값 열은 `mark_computed_headers`로 머리글 도움말을 달고, 값을 넣은 뒤 `paint_computed`로 칠한다. flux 표 위에는 `FLUX_LEGEND`를 둔다.
- 화면 확인용 캡처·REA 스크립트는 scratchpad에 두고 저장소에 넣지 않는다. 사이드바 이동은 접근성 '누름'으로 안 되므로(`docs/tracking/findings.md`) 실행 스크립트에서 `sidebar.select(group, key)`를 부른다.
- 문구: `app.py`의 기존 job 상태·분석 화면 문구는 `I18N` 카탈로그 키(`self._message(key, ...)`)를 쓴다. 작업 공간 chrome(메뉴·도구줄·사이드바·상세 패널·작업 창·AGORA2 창·대화상자·상태 표시줄 메시지)은 한국어화를 멈췄으므로 영어 리터럴로 직접 쓰고 `I18N`을 거치지 않으며, `--lang ko`에서도 영어다. `builder.py`, `views.py`, `host_view.py`는 영어 문구를 코드에 직접 쓰고, `editors.py`의 `_editor_text`는 영어로 대체된다. 각 파일의 기존 방식을 따른다. `_message`는 활성 언어 카탈로그를 fallback 없이 조회하므로, `I18N`에 새 키를 넣을 때는 `"en"`과 `"ko"`에 **같은 영어 문구**를 넣는다(번역하지 않음). `"ko"`에 없으면 `--lang ko`에서 `KeyError`가 난다.
- 장기 작업은 `JobRunner` + `JobsBridge`로 돌리고 완료는 타이머 poll로 받는다. 작업 창에 보이는 작업은 사용자가 시작한 것과 "Index Models"뿐이고, 색인 확인(`index_check`)과 검색 행 읽기는 보이지 않는 조회 작업이다. UI 스레드에서 solve를 돌리지 않는다. 작업 창 Kind 열은 사용자용 이름(`activity.JOB_KIND_NAMES`)을 보이고 run 표식의 `job_kind`는 내부 kind 그대로 둔다. 상세 패널의 exchange 조회는 Activity job이 아니다(`runner.submit`만, bridge 추적 없음). 보이는 모델이 바뀌면 이전 조회를 취소한다.
- 취소 표시는 협조적 취소의 실제 상태(요청됨 → 경계에서 멈춤)를 그대로 보여 준다.

## 테스트

- `QT_QPA_PLATFORM=offscreen`에서 실행한다.
- 비기본 설정(배지 경로, 방향, 성장 분율)이 해당 workflow의 argv에 실제로 전달되는지 recorder로 검사(`tests/test_gui_audit_regressions.py`, `tests/test_gui_editors_builder.py`).
- Search 동등성: `tests/test_gui_search_parity.py`(argv·기본값), `tests/test_gui_search_output.py`(프로젝트 run 폴더·checkpoint), `tests/test_gui_search_inspector.py`(Pareto 그림·inspector), `tests/test_gui_search_cancel.py`(취소 pending).
- 작업 공간: `tests/test_project_io.py`(프로젝트 형식·잠금·run 입력, Qt 없음), `tests/test_workspace_session.py`, `test_workspace_sidebar.py`, `test_workspace_panels.py`, `test_workspace_shell.py`(메뉴·창), `test_workspace_import.py`, `test_workspace_pickers.py`, `test_workspace_agora2.py`, `test_workspace_analysis_inputs.py`(argv의 `--taxonomy`/`--host`/`--model`/`--medium`/`--out`이 프로젝트 경로인지), `test_workspace_activity_flow.py`(취소·실패 run 표시). 프로젝트가 필요한 테스트는 `tests/gui_project_helpers.py`의 `open_test_project`를 쓴다. 최근 프로젝트는 임시 `QSettings`로 격리해 사용자 설정에 쓰지 않는다.
- 새 GUI 테스트 파일에는 `from gui_project_helpers import _deterministic_qt_teardown`으로 autouse fixture를 가져온다(없으면 macOS에서 종료 시 segfault로 rc=139). `tests/`에는 `__init__.py`가 없으므로 `tests.` 접두 없이 import한다.
- 실패 run, 무결성 불일치, 손상 manifest, 없는 그림 선택 시 미리보기 초기화(`tests/test_app_shell.py`, `tests/test_gui_render.py`).
- 2단계: argv 동일성(`test_phase2_argv_parity.py`, 입력 설정은 `argv_drivers.py`), 틀(`test_phase2_analysis_page.py`), 화면별(`test_phase2_community_pages.py`, `test_phase2_community_solve.py`, `test_phase2_host_pages.py`, `test_phase2_dynamics_pages.py`, `test_phase2_tool_pages.py`, `test_phase2_search_results.py`), 실행 기록·복원(`test_phase2_run_restore.py`), 모델 브라우저·색인(`test_phase2_model_browser.py`, `test_model_index.py`), Check Growth(`test_phase2_check_growth.py`, `test_growth_reading.py`), 검색(`test_find.py`, `test_phase2_find_field.py`), 결과 표시(`test_phase2_results_display.py`), 화면 밖 판독(`test_phase2_off_thread.py`), 셸(`test_phase2_shell.py`, `test_workspace_shell.py`의 1280 폭 가로 스크롤 없음), 프로젝트 필드(`test_project_phase2.py`).
- 창 geometry 회귀는 전체 main window로 측정한다. offscreen 통과는 네이티브 시각 사용성 승인이 아니다.
