# cmig-jobrunner Planning Document

> Roadmap Phase 0.2 — facade(0.1) 위 비차단 실행 계층. GUI(0.3+)·Sweep View·Sandbox 가 소비.

## Executive Summary
| 관점 | 내용 |
|------|------|
| **Problem** | facade 는 동기(blocking)다. GUI 가 sweep/solve 를 호출하면 UI 가 멈추고, 취소·진행률·재시도가 없다. |
| **Solution** | `cmig/service/jobrunner.py` — in-process **JobRunner**(concurrent.futures.ThreadPoolExecutor, **Qt 비의존**): submit/poll/cancel/retry/result + 진행률 + 협조적 취소(threading.Event). sweep 에 backward-compat `progress`/`should_cancel` 훅 추가해 실제 wiring. |
| **Function UX Effect** | GUI 가 작업을 비차단 제출, 진행률 표시, 중간 취소, 실패 재시도. sweep 진행률=condition count. |
| **Core Value** | 비차단·취소가능 실행 — GUI 반응성(NFR-Perf)의 토대. facade 와 동일하게 CLI·GUI 공통. |

## Context Anchor
| WHY | facade 동기 → GUI 멈춤·취소/진행률 부재 |
|---|---|
| RISK | thread 안전(worker↔poll 경쟁)·MICOM GIL-bound C 호출의 협조적 취소 한계 |
| SUCCESS | submit→poll(progress)→cancel(협조적)→retry 동작 + sweep 실제 wiring + Qt 비의존 |
| SCOPE | JobRunner + sweep progress/cancel 훅. OUT: GUI 배선(0.3)·UI 위젯 |

## Scope
**In**: `cmig/service/jobrunner.py`(JobRunner·Job·JobStatus·JobContext·JobCancelled) · sweep.py 에 optional `progress`/`should_cancel` 훅 · `make_sweep_job` 어댑터(실 wiring) · tests.
**Out**: Qt signal bridge·UI(0.3) · process-based runner(thread 협조적 취소로 충분).

## Success Criteria
- **SC-J1**: submit(fn)→poll DONE·result 정확; raise→FAILED+구조화 diagnostic.
- **SC-J2**: 협조적 cancel — ctx.cancelled 체크 루프 job → cancel()→CANCELLED.
- **SC-J3**: progress — ctx.report_progress(i,n)→poll 진행률 반영.
- **SC-J4**: retry(failed)→새 job_id 재실행.
- **SC-J5**: sweep 실 wiring — make_sweep_job 가 run_sweep(progress,should_cancel) 구동, 진행률·취소 동작(orphan 아님).
- **SC-J6**: Qt 비의존(subprocess) · run_sweep 기존 테스트 무변(default None) · 204+ green · ruff/mypy clean.

## Risks
| 위험 | 완화 |
|------|------|
| worker↔poll thread 경쟁 | status/progress 전이에 Lock; 단순 read 는 GIL |
| MICOM C 호출 취소 불가 | 협조적 취소(condition 경계 체크) — in-flight solve 는 완료 후 중단(정직 표기) |
| sweep 훅이 기존 동작 변경 | default None → 기존 204 tests 무변 회귀 |

## Next Steps
design → do → analyze → report → archive. 이후 Phase 0.3 app-shell(JobRunner signal bridge).
