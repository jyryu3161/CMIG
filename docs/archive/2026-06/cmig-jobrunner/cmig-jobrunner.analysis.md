# cmig-jobrunner Analysis

> Phase 0.2. Match ≈100% (SC-J1~J6 전량 Met). 212 tests green · ruff/mypy clean.

## Success Criteria
| SC | 상태 | 증거 |
|----|------|------|
| SC-J1 submit/DONE·result·FAILED+diag | ✅ Met | `test_submit_done_and_result`·`test_submit_failure_structured_diagnostic` |
| SC-J2 협조적 cancel | ✅ Met | `test_cooperative_cancel`(루프 job→CANCELLED) |
| SC-J3 progress | ✅ Met | `test_progress_reporting`(poll (5,5)+on_progress) |
| SC-J4 retry | ✅ Met | `test_retry_failed_job`(새 job_id 재실행) |
| SC-J5 sweep 실 wiring | ✅ Met | `test_make_sweep_job_progress_and_cancel`(진행률 advance)·`test_sweep_cooperative_cancel_partial`(부분 결과) — **orphan 아님** |
| SC-J6 Qt 비의존·무회귀 | ✅ Met | `test_jobrunner_qt_independent`(subprocess)·sweep 회귀 green·212 passed·ruff/mypy clean |

## 정직성
- 협조적 취소 한계 명시(MICOM GIL-bound C 호출 → in-flight 1건은 condition 경계에서 중단, 즉시 kill 아님) — docstring.
- core 레이어 불변: run_sweep 의 should_cancel→True 는 **부분 결과 반환**(core 는 service 미의존), JobCancelled 은 service 층에서 raise → 역전 없음.
- run_sweep progress/should_cancel default None → 기존 sweep 테스트 무변.

## Findings
없음(Critical/Important/Minor 0). 기계적 인프라 feature — 정직성 게이트(실 wiring·Qt 격리·무회귀) 전량 충족.

## Version History
| v1.0 | 2026-06-01 | Match ≈100%, SC-J 6/6, 212 tests. |
