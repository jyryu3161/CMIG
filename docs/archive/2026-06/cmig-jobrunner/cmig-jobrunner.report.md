# cmig-jobrunner — Completion Report (v1.0)

## Executive Summary
| 관점 | Value Delivered |
|------|-----------------|
| **Problem** | facade 동기 → GUI 멈춤·취소/진행률/재시도 부재 |
| **Solution** | `cmig/service/jobrunner.py` — in-process JobRunner(ThreadPoolExecutor, Qt 비의존): submit/poll/cancel/retry/result + progress + 협조적 취소. sweep 에 backward-compat progress/should_cancel 훅 + `make_sweep_job` 실 wiring |
| **Function UX Effect** | 비차단 제출·진행률·중간 취소·실패 재시도. sweep 진행률=condition count |
| **Core Value** | GUI 반응성 토대. CLI·GUI 공통. 212 tests·잔여 결함 0 |

## SC 최종 (6/6 Met)
SC-J1 submit/result/FAILED · SC-J2 협조적 cancel · SC-J3 progress · SC-J4 retry · SC-J5 sweep 실 wiring(orphan 아님) · SC-J6 Qt 비의존·무회귀.

## 산출물
**신규**: `service/jobrunner.py`(JobRunner·Job·JobStatus·JobContext·JobCancelled·make_sweep_job) · `tests/test_jobrunner.py`(8)
**수정**: `core/sweep.py`(optional progress/should_cancel, default None 무변) · `service/__init__.py`(export)

## Key Decisions
- ThreadPoolExecutor(Qt 비의존) > QThreadPool — service 가 Qt 무관, GUI 어댑터(0.3)에서 signal bridge.
- 협조적 취소(Event) — MICOM C 호출 즉시 kill 불가 정직 표기.
- core 미오염: run_sweep 부분결과 반환, JobCancelled 은 service 층.

## Quality
212 passed(+8) · ruff clean · mypy strict clean · 0 placeholder · Qt-isolation subprocess.

## 결론
Phase 0.2 완료. Phase 0.3 app-shell 이 JobRunner→Qt signal bridge 로 소비. 다음: Phase 0.3.

| v1.0 | 2026-06-01 | SC-J 6/6, 212 tests, 잔여 결함 0. |
