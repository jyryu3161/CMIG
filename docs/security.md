# 보안 정책

CMIG는 사용자 한 명이 자기 기계에서 쓰는 로컬 데스크톱/CLI 도구다. 로그인, 계정, 역할, 세션, 원격 API가 없다. 보호 대상은 사용자 파일 시스템, 외부 모델의 라이선스, 솔버 라이선스 자격증명, 실행 결과에 담긴 연구 데이터다.

## 인증

- 앱 자체의 인증 단계는 없다. 로컬 OS 사용자 권한이 곧 권한이다.
- 유일한 외부 자격증명은 Gurobi 라이선스다. 로컬에서는 사용자의 Gurobi 설치·라이선스 파일, CI에서는 GitHub 저장소 비밀값(`GRB_WLSACCESSID`, `GRB_WLSSECRET`, `GRB_LICENSEID`)을 solver 작업 중에만 `$HOME/gurobi.lic`로 쓴다.
  - 비밀값이 없으면 CI `solver-tests`는 명시적으로 실패한다(건너뛰어 통과로 만들지 않는다).
  - 외부 fork의 pull request에서는 solver 작업이 돌지 않는다(비밀값 노출 방지).
  - 라이선스 유효성은 솔버 목록이 아니라 실제 작은 solve로만 확인한다.

## 권한 모델

| 주체 | 허용 | 금지 |
|---|---|---|
| CMIG 프로세스 | 사용자가 지정한 입력 읽기, 지정한 `--out` 경계 안에 결과 게시, 폐기 가능한 모델 캐시 사본 작성. 예외: `--catalogue`·`--out` 없는 `agora2-list`/`agora2-fetch`는 카탈로그 캐시를 패키지 상위 `data/agora2/`(gitignore됨)에 쓴다 | 사용자 원본 GEM 수정, `--out` 경계(와 위 예외) 밖 파일 생성·덮어쓰기 |
| AGORA2 fetcher | `https://www.vmh.life/files/reconstructions/AGORA2/` 아래 허용 경로의 HTTPS 요청, 사용자가 고른 모델만 | 허용 origin·경로 밖 요청(리다이렉트의 각 다음 요청도 전송 전 검사), `../`·절대 경로·Windows 구분자·symlink로 출력 폴더를 벗어나는 파일명, `--all`(약 70 GB 전체 카탈로그)이나 8 GB 초과 선택을 `--yes` 확인 없이 받기 |
| 인간 GEM 다운로드 스크립트 | 사용자가 직접 실행할 때만 BiGG에서 Recon3D/RECON1을 `data/gems/`로 받고 checksum·개수 검증 | 자동 실행, 모델 바이트의 git 커밋·재배포 |
| R 렌더러 | 별도 subprocess에서 프로젝트 로컬 `.Rlib` 패키지로 실행 | CMIG 프로세스에 GPL 코드 적재, 전역 R 라이브러리 수정 |
| 에이전트 도구 hook | `.codex/hooks/pre_tool_use.py`가 흔한 파괴적 셸 사고를 10초 안에 차단 | hook 판정으로 실행기 인수 판정을 대체 |

## 직렬화와 입력

- pickle(`pickle`, `cPickle`)은 어디서도 쓰지 않는다. 허용 직렬화는 Parquet/Arrow/JSON/YAML/SQLite이며, TSV는 golden fixture 전용이다. 이 금지는 Ruff 금지 API 규칙으로 강제된다.
- 모델 입력은 SBML/JSON/MAT만 받는다. 모르는 확장자·파싱 실패는 명시적 오류다.
- 손상된 manifest나 summary를 읽을 때 파싱 예외가 GUI 읽기 경계를 빠져나가면 안 된다. 읽기 실패는 "읽을 수 없음"으로 따로 보고한다.

## 민감 데이터와 배포

- 실행 결과(`.run/`, `runs/`, 단계 실행기의 `.run/harness/<phase>/` 로그)는 사용자 연구 데이터와 원시 모델 출력을 담을 수 있으므로 git에 넣지 않고 로컬에만 둔다. 단계 실행기는 자격증명이나 전체 환경 변수를 기록하지 않는다.
- 외부 GEM(BiGG Recon3D/RECON1은 UCSD 비상업 라이선스, AGORA2, Human-GEM)은 재배포하지 않는다. 바이트는 gitignore되고, 출처·라이선스·checksum·크기·구조 개수는 `data/gems/GEM_SOURCES.json` 같은 추적 파일에 남긴다. 검증 모델 `models/`는 Apache 라이선스가 아니며 배포물에서 제외된다.
- 배포물(wheel/sdist)은 명시적 허용 목록으로 감사한다. `.git`, `.run`, `.omc`, `.bkit`, `.Rlib`, `models`, `fixtures`, `REVIEW`, `__pycache__`, `.env`, `gurobi.lic`, `credentials.json`이 들어 있으면 실패, 25 MB 초과 전개도 실패다. sdist 문서는 `USAGE.md`, `USER_GUIDE.md`, `PUBLICATION_VALIDATION.md`만 허용한다.
- 라이선스 격리: GLPK(GPL)는 번들하지 않는다. Gurobi·CPLEX는 번들하지 않는다. R은 프로세스 격리로만 쓴다.

## 기록 대상

별도 보안 감사 로그는 없다. 추적 가능성은 run 기록으로 확보한다.

- 모든 workflow run: `run_hash`, 입력 모델·배지 checksum, 의존성 버전, 솔버, 선언된 산출물의 `result_digest`.
- namespace gate의 모든 차단·경고 결정.
- AGORA2 fetch: 원 요청 URL, 실효 URL, 받은 바이트와 적용한 변환(문자 인코딩 수리, id 변환).
- 인간 GEM 다운로드: 출처 URL, 라이선스, 받은 날짜, 압축/해제 SHA-256, 바이트 수, 구조 개수.
