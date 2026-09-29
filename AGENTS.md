# CMIG

CMIG(Community Metabolic Interaction GUI)는 미생물 커뮤니티의 대사 상호작용을 분석하는 데스크톱 GUI + CLI 도구다(Python 3.10–3.12, 약 4.3만 줄, Apache-2.0, 버전 0.3.0). 사용자는 자기 GEM으로 커뮤니티 FBA, 목표 대사체 생산 조합 탐색, 숙주-미생물 결합, dFBA를 돌려 출판 가능한 결과를 만드는 연구자다. 커뮤니티 FBA는 MICOM(`micom==0.39.0`)에 맡기고, CMIG는 입력 검증·namespace 차단·부호 규약·탐색·재현성 기록 계층을 소유한다. 로컬 단일 사용자 도구이며 서버·원격 실행은 없다.

## 프로젝트 구조

```
CMIG/
├── CLAUDE.md / AGENTS.md          → 개발 규칙 진입점(두 파일 내용 동일)
├── docs/
│   ├── architecture.md            → 구성요소, 의존 방향, 대표 흐름(search, solve, 숙주 결합), 경계
│   ├── business-rules.md          → 과학적 계약: 부호, 배지, gate, 멤버십·성장, 탐색, 숙주, dFBA, 통계, 상태·지문
│   ├── security.md                → 로컬 도구 보안, 네트워크·파일 경계, 라이선스·자격증명, 배포 금지 목록
│   ├── standards.md               → 규칙 전체: 권위 순서, 모듈 경계, 계약 변경 절차, 검증 게이트, 커밋, 실행기
│   ├── engineering-notes.md       → 함정(증상→원인→대응), 비직관적 메커니즘, 반복 작업 체크리스트
│   ├── operations.md              → 설정·실행·검증 tier·CI·단계 실행기·환경 변수·릴리스 절차
│   ├── contracts.md               → CLI 계약: 종료 코드, 입력 형식, inspect-run payload, tidy 스키마, 산출물
│   ├── tracking/
│   │   ├── status.md              → 완료(검증 증거 포함)·남은 작업(우선순위)·범위 제외·차단 요인
│   │   ├── decisions/index.md     → 결정 기록 목록(MICOM 고정, 솔버 역할, 숙주 구성 B, R 격리, hash 밖 표식, 범위 조정)
│   │   └── findings.md            → 지금 풀 수 없는 문제와 이유
│   └── USAGE.md, USER_GUIDE.md, PUBLICATION_VALIDATION.md, HARNESS.md  → 사용자·운영용 문서(앞의 3종은 sdist에 포함)
├── cmig/
│   ├── core/AGENTS.md             → 과학 알고리즘·엔진 어댑터·hash. 단일 진입점과 불변식
│   ├── service/AGENTS.md          → JobRunner, 공유 탐색 서비스·워커, facade, store
│   ├── io/AGENTS.md               → 모델 import·캐시, AGORA2 fetch(유일한 네트워크), 원자적 게시
│   ├── cli/AGENTS.md              → cmig 명령, 종료 코드, inspect-run, workflow 지도
│   ├── gui/AGENTS.md              → PySide6 앱. CLI를 in-process로 실행하고 run 디렉터리를 읽음
│   ├── render/AGENTS.md           → 출판 그림 Python 쪽(R subprocess, fallback, provenance)
│   └── render_r/AGENTS.md         → R 스크립트와 renv.lock
└── scripts/AGENTS.md              → 단계 실행기·검사 tier·배포 감사·버전 검사·GEM 다운로드·preset 빌드
```

과거 기록(`REVIEW/`, `docs/archive/`, `docs/00-pm/`, `docs/01-plan/`, `docs/release-drafts/`, 원본 결정 3건이 있는 `docs/decisions/`)은 증거 자료일 뿐 현재 규칙이 아니다. 루트 명세 `CMIG_명세서_v3.0.md`는 의도를 정하지만, 솔버 역할·golden·숙주 구성·범위는 결정 기록이 우선한다.

## 절대 규칙

1. **MICOM 위임과 정확 고정**: 커뮤니티 구성·cooperative tradeoff는 `cmig/core/engine.py`를 통해 MICOM public API로만 호출한다. `micom==0.39.0`을 바꾸려면 gurobi·osqp golden을 모두 통과해야 한다. 문서화되지 않은 MICOM 내부 결합은 검토 대상으로 표시한다.
2. **부호·경계·배지 의미 보존**: `+` 분비 / `−` 흡수, 환경 기준과 멤버 기준 구분, merge와 exact 배지의 명시적 구분, 모든 경계 흡수의 격리. 대응 없는 입력은 조용히 버리지 않고 오류로 거부한다.
3. **실패는 결과가 아니다**: 실패·non-viable·평가 불가·취소를 유효한 0이나 성공과 섞지 않고, 절대 "최고"로 순위화하지 않는다. 종료 코드 0/2/3과 과학적 성공 ≠ 산출물 성공을 지킨다.
4. **재현성 계약**: solve `run_hash` 11구성요소 고정, workflow hash 구성요소 변경은 envelope 재승인 + CHANGELOG, 결과 의미 변경은 hash 밖 provenance 표식 갱신. pickle 금지, 원자적 게시, 사용자 원본 GEM 수정 금지, preview 데이터는 Apply/Save 전 비기록.
5. **솔버 표기**: Gurobi는 full-flux, OSQP는 QP-only 근사로 정확히 표기한다. golden 허용오차를 완화하지 않고, skip이나 없는 테스트를 통과로 세지 않는다. 단위 테스트 통과는 출판 타당성이 아니다.

## 작업 전 확인

- 항상: `docs/standards.md`, `docs/engineering-notes.md`, 작업할 모듈의 `AGENTS.md`.
- 과학 수치가 바뀔 수 있는 변경(탐색 점수, 배지 적용, exchange 변환, 숙주 전달, dFBA, 통계): `docs/business-rules.md`의 해당 절과 `docs/engineering-notes.md`의 "hash가 같은데 숫자가 다름". 결과 의미가 바뀌면 provenance 표식을 올린다.
- hash·manifest·checkpoint·tidy 스키마 변경: `docs/standards.md`의 "재현성 계약 변경"과 `docs/engineering-notes.md`의 hash 체크리스트. core 버전 변경은 golden 재캡처 절차.
- MICOM·솔버·경계 격리 변경: `docs/tracking/decisions/`의 0001·0002, `docs/tracking/findings.md`의 MICOM 비공개 결합 항목.
- GUI 변경: `cmig/gui/AGENTS.md`의 문구 카탈로그 규칙(한국어화 중단, `ko`에도 영어 문구)과 workflow별 설정 범위.
- AGORA2·다운로드·파일 게시 변경: `docs/security.md`의 경로 경계.
- 단계 실행기 사용: `docs/operations.md`의 "단계 실행기"와 `scripts/AGENTS.md`. 계획·검토는 `gpt-6-astra`, 구현은 `gpt-6-sol`.
- 환경: 동기화된 환경에서 `uv run --no-sync`. worktree에서는 먼저 동기화한다.

## 문제 보고

즉시 사용자에게 보고:
- 과학적으로 틀린 수치가 정상 결과처럼 보이는 경로(식별 불가 값을 0으로 채움, 부호·방향 오류, 숨은 공급으로 인한 거짓 성장, 실패 후보가 순위에 들어감, OSQP 근사를 full-flux로 표기).
- 입력이 같은데 `run_hash`가 바뀌거나, 입력이 다른데 같은 hash가 나오는 경우. golden·envelope drift.
- `--out` 밖 파일 생성·덮어쓰기, 사용자 원본 GEM 변경, 허용 경로 밖 네트워크 요청.
- 외부 GEM·자격증명·`.run` 데이터가 git이나 배포물에 들어가는 경우.
- 명세·결정 기록과 구현의 과학적 의미 불일치(조용히 한쪽으로 맞추지 않는다).

그 밖에 지금 풀 수 없는 문제는 원인과 "지금 못 푸는 이유"를 적어 `docs/tracking/findings.md`에 기록한다.

## 사용자용 skill

`.claude/skills/cmig-metabolic-analysis`는 CMIG로 대사 분석을 하는 사용자를 위한 skill이다. 개발 규칙의 출처가 아니다.
