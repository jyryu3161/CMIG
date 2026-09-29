# scripts

## 범위

패키지 밖 개발·릴리스 도구.
- `execute.py` — 단계(phase) 실행기. `phases/<name>/`의 step을 순서대로 Codex에 넘기고 상태·검사·잠금을 소유한다.
- `harness_checks.py` — 실행기와 Stop hook이 공유하는 검사 카탈로그와 tier(`smoke`, `quality`, `solver`, `gui`, `full`). `harness_result.schema.json`은 step 최종 JSON 스키마.
- `audit_distribution.py` — wheel/sdist 허용 목록 감사.
- `check_release_versions.py` — 공개 버전 표면 정합 검사.
- `download_human_gems.py` — Recon3D/RECON1 다운로드·checksum·개수 검증.
- `build_gut_media.py` — 장내 배지 preset 재생성(오프라인, `medium_presets/sources/` 미러 사용).
- `benchmark_search.py` — 같은 예산·여러 seed의 탐색 벤치마크.

범위 아님: 제품 기능. 여기서 과학 계산을 구현하지 않는다(필요하면 `cmig`를 import해 쓴다).

## 경계

- `execute.py`, `harness_checks.py`, `harness_result.schema.json`, `tests/test_harness_*.py`는 sdist에서 제외된다(`pyproject.toml`의 exclude). 이 파일들이 `AGENTS.md`, `.codex/`, `.claude/`, `phases/`에 의존하기 때문이다. 새 실행기 전용 파일도 같은 exclude에 넣는다.
- `.codex/hooks/pre_tool_use.py`, `.codex/hooks/stop.py`는 Codex와 Claude가 같이 쓴다. `stop.py`는 `smoke` tier만 90초 안에서 돌리고 재진입을 막는다(`CMIG_STOP_HOOK_ACTIVE`).

## 불변식

실행기(`execute.py`):
- 실행 전 역할·경로·인수 절(Acceptance)·검사 ID·정수 제한 시간·시도 횟수를 검증한다. 마지막 step은 review.
- 모델: plan·review = `gpt-6-astra`, implement = `gpt-6-sol`, 추론 강도 medium, fallback 없음. plan·review는 읽기 전용이며 보고서는 실행기가 구조화 응답에서 쓴다.
- 완료 판정: child 종료 0 + 스키마에 맞는 최종 JSON + 역할에 맞는 결과 + 범위 준수 + 실행기가 돌린 모든 검사 통과. 최종 review가 `pass`여야 한다. pytest 수집 실패·skip, 없는 명령, 시간 초과, 깨진 JUnit은 성공이 아니다.
- `max_attempts` 기본 1, 최대 3. 시간 초과·중단·blocker·범위 위반은 재시도 없이 즉시 멈춘다.
- 상태 쓰기는 원자적이고 배타 잠금으로 두 번째 writer를 거부한다. 중첩 실행기는 거부한다(`CMIG_HARNESS_DEPTH`).
- 기본: 현재 브랜치·index·무관한 편집 유지, 커밋·푸시 없음. 소유 경로에 기존 변경이 있으면 시작하지 않는다. 예상 밖 쓰기는 진단하고 보존하며 되돌리지 않는다.
- 로그에 자격증명이나 전체 환경을 기록하지 않는다.
- 시간 초과 시 POSIX는 프로세스 그룹 전체 종료, Windows는 `taskkill /T`와 하위 프로세스 스냅샷.

검사(`harness_checks.py`):
- hook·검사는 저장소 `.venv`의 Python(`.venv/bin/python`, Windows `.venv/Scripts/python.exe`)을 요구한다. 없으면 blocked + 설정 안내.
- 필수 tier에서 skip은 허용하지 않는다.

기타:
- `audit_distribution.py`의 금지 목록·허용 목록을 줄이는 변경은 배포 정책 변경이다.
- `check_release_versions.py`는 `pyproject.toml`, `cmig/__init__.py`, `CITATION.cff`, `.zenodo.json`, `.claude-plugin/marketplace.json`, `uv.lock`을 모두 읽는다. 버전 표면을 추가하면 여기에도 추가한다.
- `build_gut_media.py`는 `medium_presets/`만 다시 쓴다. 이후 `cmig/resources/medium_presets/`에 바이트 그대로 복사해야 한다. 네트워크를 쓰지 않는다.
- `download_human_gems.py`는 `data/gems/`에만 쓰고 `GEM_SOURCES.json`의 checksum과 맞지 않으면 실패한다.

## 테스트

- `tests/test_harness_execute.py`, `tests/test_harness_hooks.py`, `tests/test_harness_checks.py`(smoke tier에 포함).
- `tests/test_distribution_audit.py`: 금지 구성원 거부, preset 사본 일치, 새 배포물의 preset 자원과 README 링크.
- `tests/test_release_versions.py`.
- 변경 후 `uv run --no-sync python scripts/execute.py <phase> --dry-run`으로 단계 정의를 검증한다(모델 계정·라이선스 불필요, 아무것도 바꾸지 않음).
