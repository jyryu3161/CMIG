# GUI 작업 공간 개편 1단계 설계 — 프로젝트·메뉴·사이드바·모델 목록

작성 2026-10-13. 대상: `cmig/gui/`, 새 `cmig/io/project.py`. 참고: Apple HIG "Designing for macOS"(메뉴 막대, 툴바, 사이드바, 패널, 끌어다 놓기, 파일 관리, 진행 표시, 펼침 단추), CNApy(프로젝트 파일, 입력값과 계산값 구분, Analysis 메뉴. 단일 모델·UI 멈춤·실행 기록 없음은 반면교사).

## 1. 목적

연구자가 GEM 여러 개를 한 번에 프로젝트에 넣고, 분석마다 그 목록에서 모델을 골라 실행하며, 모든 실행 기록을 한 곳에서 다시 여는 데스크톱 작업 공간을 만든다.

현재 문제(2026-10-13 offscreen 캡처, 1280×800):
- Import Model은 파일 하나만 받고, 가져온 모델이 어느 분석에도 쓰이지 않는다(Models 탭 표시 전용). 분석 탭마다 모델 폴더·경로를 따로 입력한다.
- 메뉴 막대가 비어 있다. 툴바는 글자 버튼 다섯 개이며, 그중 Run Fixture·Show Advanced Tools·Cancel Selected Job은 개발자 중심이다.
- Project Explorer는 빈 목록 세 개이고, 작업 목록이 화면 폭의 약 20%를 늘 차지한다.
- Search 탭 한 화면에 Search·Gene KO·Growth/Ratio가 섞여 있다. Host·Dynamics 탭은 1280 폭에서 입력칸과 글자가 잘린다.

성공 기준:
- 파일이나 폴더 여러 개를 대화상자 한 번 또는 끌어다 놓기 한 번으로 프로젝트에 넣을 수 있다.
- 모든 분석이 프로젝트 모델 목록에서 모델을 고르고, 결과는 프로젝트 `runs/`에 쌓인다.
- 모든 명령이 표준 메뉴에 있다.
- 1280×800과 1500×950 창에서 잘리거나 강제로 커지는 화면이 없다.

## 2. 범위

포함(1단계):
- 프로젝트 폴더와 형식
- 모델 목록: 여러 파일, 폴더, 끌어다 놓기, AGORA2
- 배지 목록
- 표준 메뉴 막대와 툴바
- 사이드바, 가운데 화면 전환, 오른쪽 상세 패널, 아래 작업 창, 빈 화면
- 기존 분석 화면의 모델·배지 입력을 목록 선택기로 교체
- 모든 실행 결과를 프로젝트 `runs/`로
- 잘리는 입력칸 정리

제외:
- 분석 화면 내부 재설계. 예: Search 화면에서 Gene KO·Growth를 분리하는 일. 2단계에서 한다.
- 결과 보기 통일·비교 개편. 3단계에서 한다.
- Settings 창, 프로젝트 정리(안 쓰는 모델 파일 삭제), Open Run으로 연 run을 프로젝트로 가져오기
- CLI 옵션·hash·산출물 변경, 한국어화

## 3. 프로젝트 폴더

```
<프로젝트>/
├── cmig-project.json   형식 버전, 이름, 모델 목록, 배지 목록, 분석별 마지막 설정
├── models/             추가한 GEM 사본. AGORA2로 받은 모델은 models/agora2/
├── media/              사용자 배지 사본
└── runs/               실행 결과 <분석>-YYYYMMDD-HHMMSS[-N]/, 입력 기록 runs/_inputs/
```

`cmig-project.json` (형식 버전 `1`):
- `format_version: 1`, `name`, `created`, `models[]`, `media[]`, `analysis_settings{분석 이름: 마지막 입력값}`
- 모델 항목:
  - `id`: 프로젝트 안에서 유일하다. 파일 이름으로 만들며, 겹치면 `cmig.core.model_pool`과 같은 규칙으로 짧은 digest 접미사를 붙인다.
  - `file`: 프로젝트 기준 상대 경로
  - `source_path`: 원본 경로. AGORA2면 원 URL
  - `sha256`, `format`, `added`
  - 점검 결과: `n_reactions`, `n_metabolites`, `n_genes`, `biomass`, `namespace_coverage_pct`, `warnings`, `status`(`ok` | `warning` | `failed`), `error`
  - 파일 상태 `integrity`(`ok` | `changed` | `missing`). 점검 결과 `status`와는 별개다.
- 배지 항목: 사용자 파일이면 `id`, `file`, `sha256`, `source_path`를 둔다. 설치 preset이면 `preset`(이름)만 두며, 복사하지 않고 `importlib.resources`로 읽는다.

규칙:
- 저장은 `cmig.io.atomic`으로 하고, 편집할 때마다 자동 저장한다.
- 파일이 없거나 JSON이 손상됐거나 `format_version`을 모르면 열기를 거부한다. 이유를 보이고 파일은 쓰지 않는다.
- 프로젝트를 열 때 모델·배지 사본의 sha256을 다시 확인한다. 다르거나 없으면 `integrity`를 `changed`/`missing`으로 두고 분석 선택지에서 뺀다.
- 원본 GEM은 읽기만 한다. 사본은 `models/`에 쓰고, 이름이 겹치면 접미사를 붙인다. 기존 파일은 덮어쓰지 않는다.
- 목록에서 모델을 빼도 `models/` 파일은 지우지 않는다. 실행 기록이 참조할 수 있어서다.
- 잠금: 열 때 `.cmig-project.lock`(PID, 호스트, 시각)을 만든다.
  - 같은 프로젝트를 다른 창이나 프로세스가 열려고 하면 "already open in another window"로 거부한다.
  - 잠금의 PID가 같은 호스트에서 살아 있지 않으면 낡은 잠금으로 보고 대체한다.
  - 닫을 때 잠금을 지운다.

## 4. 모델·배지 추가

- 경로: File > Add Models…(⇧⌘A, 여러 파일 선택, 버튼 "Add"), Add Models from Folder…(하위 폴더 포함 체크), 창이나 사이드바 MODELS에 끌어다 놓기(파일·폴더 여러 개).
- 지원 확장자는 `cmig.core.model_pool`과 같다. 끌어다 놓기는 지원 항목이 하나라도 있을 때만 받는다는 표시를 한다. 지원하지 않는 항목은 건너뛰고 알린다.
- 처리 절차(백그라운드 `JobRunner` 작업 하나, 파일마다 진행 표시):
  1. 파일마다 사이드바에 자리 행을 먼저 만든다.
  2. 사본을 복사하고 sha256을 계산한다.
  3. `cmig.io.model_import.import_model`과 `build_import_review`로 점검한다.
  4. 결과를 항목에 쓰고 자동 저장한다.
- 한 파일이 실패해도 나머지는 계속한다. 실패 행은 `failed`와 사유를 남긴다.
- 같은 sha256의 모델이 이미 있으면 다시 추가하지 않고 알린다.
- AGORA2:
  - File > Add Models from AGORA2…가 창을 연다. 창에서 `cmig agora2-list --format json`으로 카탈로그를 읽고, 균주·속을 검색해 고른다.
  - 고른 균주를 `cmig agora2-fetch --strain … --out <프로젝트>/models/agora2 --format json --yes`로 받은 뒤 위 3~4단계로 등록한다.
  - 네트워크 코드는 기존 `cmig/io/agora2.py`만 쓴다(CLI 경유).
- 배지: File > Add Medium…(CSV/JSON 여러 개)은 `media/`에 사본을 둔다. MEDIA 목록에는 설치 preset이 항상 함께 보인다.

## 5. 창 구성

메뉴 막대(Apple HIG 순서). 지금 쓸 수 없는 항목은 흐리게 표시하고 숨기지 않는다.
- **File**:
  - New Project… ⌘N · Open Project… ⌘O · Open Recent ▸(이름만, 최신순, Clear Menu, 최대 10개) · Close Project ⌘W
  - Add Models… ⇧⌘A · Add Models from Folder… · Add Models from AGORA2… · Add Medium…
  - Open Run… ⇧⌘O · Show Project in Finder
- **Edit**:
  - Undo/Redo: 프로젝트 목록 편집(모델·배지 추가, 제거, 이름 바꾸기)에만 적용한다. 메뉴에는 "Undo Remove Model"처럼 무엇을 되돌리는지 표시한다.
  - Cut/Copy/Paste/Select All: 표준 동작
  - Rename, Remove from Project
- **View**: Show/Hide Sidebar ⌃⌘S · Show/Hide Inspector ⌥⌘I · Show/Hide Activity ⇧⌘Y. 항목 이름은 현재 상태에 따라 Show와 Hide가 바뀐다.
- **Analysis**:
  - 자주 쓰는 분석: Combination Search · Gene Knockout · Strain Growth & Ratio · Host–Microbe · Dynamics
  - (구분선) 고급 도구: Community Solve · Medium Editor · Sweep · Constraint Sandbox · Compare Runs
  - (구분선) Run ⌘R · Cancel ⌘.
- **Window**: 표준. **Help**: CMIG User Guide · Try Demo Run(기존 Run Fixture)

툴바:
- 왼쪽: 사이드바 토글, 프로젝트 이름
- 가운데: Add Models…, New Analysis ▾
- 오른쪽: 상세 패널 토글, ▶ Run(가운데 분석을 실행. 분석 화면이 아닐 때는 흐림)
- 툴바의 모든 항목은 메뉴에도 있다.

사이드바(2단계까지):
- **MODELS (n)**:
  - 상태 아이콘 ✓/⚠/✗. 여러 개 선택할 수 있다.
  - 우클릭 메뉴: Search with Selected… · Rename · Remove from Project · Show in Finder
- **MEDIA**: 설치 preset과 프로젝트 배지
- **ANALYSES**: Analysis 메뉴와 같은 목록과 구분
- **RUNS**:
  - `runs/`의 실행을 최신순으로 보인다. 표시 형식은 "<분석> · <요약> · HH:MM"이다(예: Search · but · 10:31).
  - 상태 아이콘: ✓ 성공 / ⚠ 경고·degraded / ✗ 실패 / ⊘ 취소. 상태는 `inspect-run`과 같은 판정을 쓴다.

가운데:
- 사이드바에서 고른 항목 하나를 보이며, 탭 막대는 없다.
- 분석 항목이면 기존 분석 화면을 보인다.
- run 항목이면 해당 결과 화면을 보인다.
  - 기존 `load_run_dir`의 종류 판정을 따른다.
  - 군집 run은 Profile | Graph 보기 전환을 쓴다. 지금 최상위 탭인 Graph·Profile은 여기로 들어간다.

오른쪽 상세 패널(선택을 따라 바뀜, 읽기 전용):
- 모델: 요약, 검색 가능한 exchange 목록, biomass, namespace 일치율, 경고, 원본 경로, sha256
- 배지: 내용 표, 출처
- run:
  - 상태와 산출물 무결성(현재 상태 표시줄의 Integrity details를 대체), run_hash
  - 솔버 표기: Gurobi full-flux / OSQP QP-only 근사
  - 같은 결과를 내는 `cmig …` 명령(복사 버튼), Show in Finder
- 분석: 한두 문장 설명과 사용하는 CLI 명령

아래 작업 창(기본 접힘. 작업이 시작되면 펼침):
- 지금의 오른쪽 작업 목록을 대체한다.
- 작업마다 종류, 상태, 결정적 진행률과 구체적 문구(예: "Combination 34/120"), Cancel을 보인다.
- 선택한 작업의 로그·오류와 `cmig` 명령을 보인다.
- 취소 중 표시는 기존 Search 규칙(누르면 바로 버튼을 끄고, 실제로 끝날 때까지 pending 유지)을 모든 작업에 적용한다.
- 상태 표시줄에는 마지막 메시지와 솔버 상태만 남긴다.

빈 화면(시작할 때 막는 안내창 없음):
- 프로젝트 없음: New Project… · Open Project… · 최근 프로젝트 목록 · Open Run…
- 시작하면 마지막 프로젝트를 다시 연다. 실패하면(없음, 잠김, 손상) 이 화면에 이유를 보인다.
- 모델 없음: 가운데와 MODELS에 "Drop SBML, JSON or MAT files or folders here"와 Add Models… 버튼을 보인다.

## 6. 분석 화면 연결

- 모델 선택기 "Models: [n selected ▾]"를 둔다.
  - 기본값은 `status`가 `ok` 또는 `warning`이고 `integrity`가 `ok`인 모델 전부다. `failed` 모델과 `integrity`가 `changed`/`missing`인 모델은 고를 수 없다.
  - 분석별 선택은 `analysis_settings`에 저장된다.
- 화면별 연결:

| 화면 | 모델 입력 | CLI 전달 |
|---|---|---|
| Combination Search | 여러 개 | `--taxonomy` |
| Gene Knockout | 여러 개(+ 편집 멤버) | `--taxonomy`, `--members` |
| Strain Growth & Ratio | 여러 개 | `--taxonomy` |
| Host–Microbe(두 실행) | 숙주 1개 + 미생물 여러 개 | `--host`, `--taxonomy` |
| Community Solve | 여러 개(+ abundance 표) | `--taxonomy`(abundance 반영) |
| Dynamics dFBA | 1개 | `--model` |
| Medium Editor(성장 확인, minimal medium) | 여러 개 / 1개 | `--taxonomy` / `--model` |
| Sweep | 여러 개 | `--taxonomy` |

- 실행할 때 GUI가 `runs/_inputs/<run 이름>-taxonomy.csv`를 원자적으로 쓴다. 열은 `id`(프로젝트 모델 id), `file`(사본의 절대 경로), `abundance`(기본 1)이다.
  - run 폴더 안에 미리 쓰지 않는다. CLI가 run 폴더를 통째로 게시하기 때문이다.
- 배지 입력칸은 MEDIA 선택기로 바꾼다. 설치 preset은 자원 경로를, 프로젝트 배지는 사본 경로를 `--medium`으로 넘긴다.
- 출력은 항상 새 `runs/<분석>-YYYYMMDD-HHMMSS[-N]/`이고 `--out`으로 넘긴다.
  - 지난 주기에 넣은 Search Output folder 칸과 다른 화면의 Output 칸은 없앤다.
  - 임시 폴더 출력도 없앤다.
- 기존 동작은 유지한다: Search 타깃 표, 고급 설정, 기본값=CLI, inspector, Pareto 그림, checkpoint 검사, 결과 무효화 규칙.
  - 모델 선택과 배지 선택은 답을 결정하는 입력이므로 무효화 대상이다.
- 1280 폭에서 잘리는 Host·Dynamics 입력 줄은 여러 줄 배치로 정리한다. 내부 재설계는 하지 않는다.
- run_hash: 같은 모델이라도 `--model-dir` 대신 `--taxonomy`로 넘기므로 이전 GUI 실행과 hash가 다를 수 있다. CLI 계약은 그대로이며, 사용 설명서에 적는다.

## 7. 코드 구조

- `cmig/io/project.py`(Qt 없음): `create_project`, `open_project`(잠금 포함), `save`, `add_model_files`(복사·sha256·id 결정, 점검은 콜백), `add_media`, `verify_checksums`, `write_run_taxonomy`, `new_run_dir`, `close`. 오류는 `ProjectError`이다. `cmig.gui`·`cmig.cli`를 import하지 않는다.
- `cmig/gui/`:
  - `sidebar.py`(소스 목록·끌어다 놓기·우클릭 메뉴)
  - `inspector.py`(선택별 상세)
  - `activity.py`(작업 창, 기존 jobs panel 대체)
  - `model_picker.py`(모델·배지 선택기)
  - `project_dialogs.py`(새 프로젝트, AGORA2 받기 창)
  - 주 창은 이것들을 조립하고 메뉴·툴바·가운데 전환을 맡는다.
- `app.py`는 이 변경에 필요한 부분만 고친다. 분석 화면 내부 분리는 2단계에서 한다.
- 분석은 계속 CLI argv → `JobRunner` → `cmig.cli.main.main`으로만 실행한다. 모델 점검은 `cmig.io.model_import` 호출이며 과학 계산이 아니다.

## 8. 오류 처리

- 프로젝트 열기 실패(없음, 손상, 모르는 형식, 잠김): 빈 화면에 이유를 보이고 파일은 건드리지 않는다.
- 모델 추가 실패: 그 행만 `failed`와 사유를 남기고, 나머지는 계속한다.
- 복사 중 디스크 오류가 나면 부분 사본을 남기지 않는다(원자적 복사).
- checksum 불일치나 없는 파일: `integrity`를 `changed`/`missing`으로 두어 ⚠로 표시하고 선택지에서 뺀다. 상세 패널에 사유를 보인다.
- 실행 중 프로젝트 닫기·앱 종료: 기존 종료 처리를 따른다(대기 작업 취소, 실행 중 solve는 경계까지). 잠금은 해제한다.
- 실패·취소된 run은 RUNS에 ✗/⊘로 보이고, 결과처럼 표시하지 않는다.

## 9. 검증

- 단위 테스트(Qt 없음), `cmig/io/project.py`:
  - 만들기·저장·다시 열기 왕복
  - 손상 JSON·미래 형식 거부(파일 무변경)
  - 잠금 충돌과 낡은 잠금 대체
  - 이름 충돌 접미사, 같은 sha256 중복 추가 거부
  - checksum 변경·누락 감지
  - taxonomy 내용, run 폴더 이름 비재사용
  - 원본 파일 무변경
- offscreen GUI 테스트:
  - 메뉴 항목과 단축키, 흐린 상태
  - 여러 파일·폴더 가져오기(대화상자 monkeypatch), 가짜 drop 이벤트
  - 실패 파일이 섞인 가져오기
  - 사이드바 선택 → 가운데·상세 패널 전환
  - 각 분석 argv의 `--taxonomy`/`--host`/`--model`/`--medium`/`--out`이 프로젝트 경로인지
  - 빈 화면 세 가지, 잠긴 프로젝트·손상 프로젝트
  - AGORA2 창(offline transport 또는 CLI monkeypatch)
  - 작업 창 진행·취소
  - `--lang ko` 경로
  - 전체 창 geometry 1280×800·1500×950
- 화면 캡처 확인: 빈 프로젝트, 모델 12개, 각 분석 화면, run 결과, 상세 패널, 작업 창 펼침을 1280×800으로 offscreen 캡처한다. 잘림, 겹침, 빈 공간을 눈으로 확인하고 고친다.
- 기존 GUI 테스트 중 탭·explorer·jobs panel 구조에 기대는 것은 의도를 유지한 채 새 구조로 옮긴다.
- 최종: `harness_checks.py --tier quality`, 전체 pytest(Gurobi), `cmig golden verify`, `verify-envelope`
- 문서: `docs/USER_GUIDE.md` GUI 절, `CHANGELOG.md`, `docs/tracking/status.md`, `cmig/gui/AGENTS.md`, `cmig/io/AGENTS.md`
- 사용자 확인: 실제 macOS 화면에서 주요 흐름을 확인한다.

## 10. 불변식

- GUI는 계산하지 않는다. CLI 옵션, hash, envelope, 산출물은 그대로다.
- 원본 GEM은 수정하지 않는다. 프로젝트 폴더 밖에는 쓰지 않는다. 예외는 사용자가 고른 프로젝트 위치를 만드는 것과 Open Run으로 연 run을 읽는 것뿐이다.
- 실패·취소·checksum 문제는 성공처럼 보이지 않는다.
- 새 UI 문구는 영어로만 쓴다. `I18N` 새 키는 `en`·`ko`에 같은 영어 문구로 넣는다.
- strict mypy(graph_view 제외), Ruff, pickle 금지, 원자적 쓰기
