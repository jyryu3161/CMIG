# 현재 상태

기준: `main` @ `3621868`, 패키지 버전 `0.3.0`(태그 `v0.3.0` = `1d198ef`, annotated이며 서명 없음). 이후 변경은 `CHANGELOG.md`의 `[Unreleased]`에 있다(2026-09-25 감사 결함 20건 수정, 조합 탐색 정확성 수정, 재개 가능한 탐색, GUI 작업 공간 1단계는 `main`에 병합(`d6a1d31`), 2단계는 브랜치 `gui-workspace-phase2`).

## 검증 증거

| 증거 | 결과 | 날짜 |
|---|---|---|
| 로컬 `harness_checks.py --tier quality` (Ruff, 실행기 회귀, lock, 버전 정합, strict mypy, envelope, CI 무라이선스 테스트) | 모두 통과 | 2026-09-29, `3621868` |
| GitHub CI `quality` 4개 OS/Python 조합, `package` | `3621868`에서 통과. 직전 3개 커밋(`e32d7d9`, `387ccce`, `c0ff2b5`)은 quality(Windows py3.12, 한 번은 Ubuntu py3.10)에서 실패 | 2026-09-25 |
| GitHub CI `solver-tests` | **실패** — `3621868`에서 처음 이 단계에 도달했고, 저장소에 Gurobi WLS 비밀값이 없어 라이선스 설정 단계에서 중단. 이전 run들은 quality 실패로 이 단계를 건너뜀. golden·전체 pytest·출판 smoke는 원격에서 실행된 적이 없음 | 2026-09-25 |
| 로컬 `harness_checks.py --tier quality`, 전체 pytest(Gurobi, offscreen Qt), `cmig golden verify`, `verify-envelope` — GUI·CLI Search 동등성 변경 | quality 통과. pytest 1856 passed, 0 failed, 18 skipped(인간 GEM fixture 부재), 요약 출력 후 종료 시 rc=139(macOS QtWebEngine 정리 문제, 변경 전 `9a407bb`에서도 동일). golden·envelope 변화 없음 | 2026-09-29, `dryforge/gui-cli-parity` |
| 로컬 `harness_checks.py --tier quality`, 전체 pytest(Gurobi, offscreen Qt), `cmig golden verify`, `verify-envelope` — GUI 작업 공간 1단계 | quality 통과. pytest 2184 passed, 0 failed, 0 errors(junit), 18 skipped(인간 GEM fixture 부재), 요약 출력 후 종료 시 rc=139(위 macOS QtWebEngine 정리 문제와 동일). golden(gurobi `31d5647d…`, osqp `b8ca28e3…`)·envelope(18 kind) 변화 없음. offscreen 캡처 1280×800·1500×950(시작, 모델 12개, 모델 선택, Search, Host, Dynamics, 작업 창, AGORA2 창)에서 강제 확대 없음 | 2026-10-13, `gui-workspace-phase1` @ `a0b62cd` |
| 로컬 전체 pytest (Gurobi 라이선스, offscreen Qt) | 1752 passed, 0 failed, 18 skipped(인간 GEM fixture 부재) — `e32d7d9` 커밋 기록 기준. 이후 3개 커밋(Windows 이식성, 실행기)에 대한 로컬 전체 재실행 기록은 없음 | 2026-09-25 |
| 로컬 `harness_checks.py --tier quality`, 전체 pytest(Gurobi, offscreen Qt), `cmig golden verify`, `verify-envelope` — GUI 작업 공간 2단계 | quality 통과(ruff, harness-tests, lock, versions, mypy, envelope, ci-tests). pytest junit 2481개 중 2463 passed, 0 failed, 0 errors, 18 skipped(인간 GEM fixture 부재). 이번에는 warnings summary 뒤 마지막 요약 줄이 찍히기 전에 rc=139로 끝나(위 macOS QtWebEngine 정리 문제) junit으로 판정했다. golden(gurobi `31d5647d…`, osqp `b8ca28e3…`)·envelope(18 kind) 변화 없음 | 2026-10-14, `gui-workspace-phase2` @ `e3012c3` |
| 화면 확인 — GUI 작업 공간 2단계 | offscreen 1280×800·1500×950, 밝은·어두운 팔레트 강제: 13개 분석 화면(결과 없음), Advanced를 펼친 Combination Search, 다시 연 Search·Community run(배너·결과·계산값 강조), 모델 표, 모델 브라우저 3종, 검색 목록. REA로 macOS 실제 창(시스템 어두운 모드) 1500×950·1280×800: Combination Search(+Advanced), Community Solve, Host–Microbe, 모델 브라우저, 검색 목록, 다시 연 run, Medium Editor·Sweep. 찾은 화면 문제 8건을 고침(빈 결과 줄 위치, 1280 폭 Medium/Sweep 가로 스크롤, 브라우저의 이전 모델 행 선택, 모델 표 Check 열 잘림, 검색 목록 가로 스크롤, 어두운 모드의 Search 그림, 상태 표시줄 빈 단추 상자, 긴 모델 id의 창 강제 확대). 밝은 모드 실제 창은 미확인 | 2026-10-14 |
| 출판 검증 절차(`docs/PUBLICATION_VALIDATION.md`) Recon3D 재실행 | **미실행**. 현재 문서의 수치는 코드 대조 또는 round-6 기록(`ac1adf3`)이며 릴리스 결과가 아님 | — |
| 네이티브 GUI 시각 검증(macOS/Windows, HiDPI, 접근성) | macOS 어두운 모드 실제 창만 REA로 확인(위 행). 밝은 모드 실제 창, Windows, HiDPI, 접근성, 사람의 조작 확인은 **미실행** | 2026-10-14 |

## 완료된 기능

"검증됨"은 해당 테스트가 존재하고 위 증거에서 통과했다는 뜻이다. 솔버가 필요한 테스트는 로컬 라이선스 실행에서만 통과가 확인됐다.

| 영역 | 상태 |
|---|---|
| 기반: 부호 단일 진입점, namespace 차단 gate, tidy 1.3, solve `run_hash`(11구성요소), workflow manifest 1.2(18 kind), `result_digest`, 원자적 게시 | 검증됨(무라이선스 CI 포함) |
| MICOM community solve(Gurobi full-flux, OSQP QP-only 근사), golden 2종(gurobi `31d5647d…`, osqp `b8ca28e3…`) | 로컬 라이선스에서 검증됨. 원격 golden 미실행 |
| 배지: merge/exact, 경계 격리 v2(formula-`X` pseudo-supply), 장내 preset + 행 단위 출처, `medium-gap`, `minimal-medium` | 검증됨 |
| 모델 준비: SBML/JSON/MAT import, 정규화 캐시, `model-quality`, `model-review`, `namespace-suggest`, AGORA2 fetch(경로 탈출·리다이렉트 방어) | 검증됨(AGORA2는 offline transport만) |
| 기본 분석: `pair`, `delta`, `single`, `strain-growth`, `abundance-impact`, `sweep`(캐시·실패 행), sandbox(preview/commit) | 검증됨 |
| 조합 탐색: exhaustive/random/GA, 성장 하한, 멤버십 검사, non-viable 격리, 다중 타깃 4 metric, 표본 Pareto + 시도 ledger, checkpoint·재개·취소, spawn 워커, 사후 민감도, GA 벤치마크 | 검증됨. GA 전역 최적성·실제 대형 AGORA2 pool 처리량은 미검증 |
| `gene-ko-search` | 검증됨 |
| 숙주 결합(구성 B): `host-map`, `host-microbe-bigg`, `host-search-bigg`, `host-ko-impact`, 식별 불가 전달의 null 보존 | 합성 숙주·Recon3D 테스트로 검증됨. 대형 host-map의 생화학 대응 정답은 미검증 |
| dFBA: 단일 모델, `dfba-community`(Gurobi), `dfba-sensitivity`, 방향·비단위 계수 물리량 변환, 숨은 sink 공급 폐쇄 | 검증됨. 장시간 dt 수렴은 미검증 |
| `spatial-preview`(확산 배지 설계) | 검증됨 |
| 통계 5a(효과 크기·검정·BH-FDR), 5b/5c 일부(`StatsConfig`, seed 고정 임베딩, volcano 준비) | 검증됨 |
| 출판 그림: R(renv lock, provenance sidecar) + matplotlib 대체, signed 다중 타깃 기여 그림 | 검증됨(R 전용 다중 패널은 R 설치 환경에서만) |
| GUI 작업 공간(1단계): 프로젝트 폴더(`cmig-project.json`, `models/`, `media/`, `runs/`) 중심. File/Edit/View/Analysis/Window/Help 메뉴, 도구줄, 사이드바(MODELS·MEDIA·ANALYSES·RUNS), 선택을 따르는 상세 패널(모델 exchange, run 상태·무결성·솔버 표기, Copy Command), 아래 작업 창(작업별 취소). 모델은 여러 파일·폴더·끌어다 놓기·AGORA2(검색, 대용량 확인, 배치별 manifest)로 추가하고 sha256 사본·중복 거부·열 때와 실행 직전 재검증. 모든 분석이 모델·배지 선택기로 입력을 받고 `runs/<kind>-YYYYMMDD-HHMMSS`에 쓰며 `--taxonomy runs/_inputs/…`로 넘긴다. 실패·취소·읽기 거부 run은 RUNS에 ✗/⊘로 남는다. 기존 분석 화면의 동작은 유지: 워크플로별 설정 범위, 실패 run 진단, 무결성 표시, Search는 `cmig search`와 동등(타깃 행, 탐색 옵션, Pareto 그림, 후보 inspector, 취소 pending). Search 결과는 Open Run으로 다시 열린다 | 기능 테스트 검증됨(offscreen). 네이티브 시각 QA 미실행 |
| GUI 작업 공간(2단계): 분석 하나에 화면 하나(13개, 사이드바·Analysis 메뉴 네 묶음). 모든 화면이 입력 카드·Advanced("· N changed")·결과 영역 틀을 쓰고, 같은 입력이면 나누기 전과 같은 argv. 실행 입력 기록(`runs/_inputs/<run>-request.json`)과 RUNS에서 열 때 화면·입력·결과 복원(배너). 모델 표의 점검 이유, 읽기 전용 모델 브라우저와 모델별 색인(`models/.index/<sha256>.json`, 보기·검색용), 파일 sha256에 묶인 모델별 namespace 확인, Check Growth(`cmig single --fba`). 전역 검색(⌘F). 상태 표시줄의 마지막 실행, 계산값 강조색, flux 범례, 행 번호 숨김. 실패·취소·판독 실패·프로젝트 전환 때 이전 결과 지움. 키보드 다중 선택기, run 판독 hash와 AGORA2 조회를 화면 스레드 밖으로. CLI·`run_hash`·manifest·tidy 스키마·golden 불변 | 기능 테스트 검증됨(offscreen), macOS 어두운 모드 실제 창 확인. 사용자 실제 화면 확인 대기 |
| 배포: wheel/sdist 허용 목록 감사, 설치본 preset 자원, 버전 정합 가드 | 검증됨 |
| 단계 실행기(`scripts/execute.py`), 검사 tier, Codex/Claude hook | 검증됨(POSIX). Windows 프로세스 정리는 CI quality 통과 외 네이티브 확인 없음 |

## 남은 작업 (우선순위 순)

1. **GUI 3단계: 결과 보기·비교 통일**: 결과 화면과 run 비교를 하나의 보기 방식으로 맞춘다(Compare 개편, 그림 개선 포함). 2단계에서 넘어온 것: 어두운 모드 계산값 강조색 대비(`docs/tracking/findings.md`), 밝은 모드 실제 창 확인, `docs/cmig_hands_on_tutorial.html`을 새 화면 기준으로 다시 만들기(아직 이전 UI의 탭·Show Advanced Tools를 설명), 1280 폭 dFBA "Initial" 칸의 긴 기본값 잘림, 시작 화면 최근 프로젝트 목록 상자의 빈 공간(이번에 보지 않음), Host 결과 표 머리글(짧게 바꾸고 단위를 도움말로 옮겼으나 숙주 모델이 없어 결과 화면을 캡처하지 못함).
2. **타깃별 임계값**: per-target threshold를 `MultiTargetConfig`·CLI·GUI에 공통 설계로 추가. 내부 epsilon slice는 이 기능이 아니다. hash 인자 추가이므로 envelope 재승인이 따른다.
3. **탐색 방법 확장**: abundance 동시 최적화, 명시적 synergy/null-model fitness, 자동 MIP/MRO 사전선별, greedy/Bayesian 탐색. 각각 별도 과학 설계와 비교 벤치마크가 먼저 필요하다.
4. **내부 정리**
   - exchange id → 대사체 정규화 함수가 여러 벌(`medium_spec.exchange_metabolite`, `dfba_community._exchange_metabolite` 등). `medium_spec` 쪽을 기준으로 통합. engine 쪽 변환은 hash에 영향을 주므로 계약 확인 후 진행.
   - 후보마다 MICOM community를 2~3번 새로 조립하는 탐색 성능 문제.
   - `cmig/cli/main.py`(약 1.1만 줄) 분리: inspect-run, 그림, 입력, workflow 지도, gene-ko.
   - 연결되지 않은 `FileSystemStore` 처리(연결 또는 제거).

## 범위에서 제외

- CPLEX: 솔버 타입 정의에는 이름이 있으나 어떤 명령에서도 고를 수 없고 번들하지 않는다.

- 원격 서버/HPC 백엔드와 토큰, Docker Compose 실행.
- Escher 대사 지도 뷰.
- GUI 한국어화 확장.
- 공간 격자별 FBA(COMETS류), 사멸·washout, strain engineering, 모델 자동 재구성, SaaS.

## 차단 요인

- 원격 `solver-tests`: 저장소에 Gurobi WLS 비밀값(`GRB_WLSACCESSID`, `GRB_WLSSECRET`, `GRB_LICENSEID`)이 등록돼야 원격에서 golden·전체 테스트가 돈다.
