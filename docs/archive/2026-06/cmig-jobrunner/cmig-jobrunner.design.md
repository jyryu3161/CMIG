# cmig-jobrunner Design Document (Option C)

> Plan: cmig-jobrunner.plan.md. Architecture: Option C — generic JobRunner + sweep 어댑터(실 wiring).

## Context Anchor
| WHY | facade 동기 → GUI 멈춤·취소/진행률 부재 |
| RISK | thread 경쟁·MICOM C 호출 협조적 취소 한계 |
| SUCCESS | submit/poll/cancel/retry + progress + sweep 실 wiring + Qt 비의존 |

## Architecture (Option C 선택)
- A(직접 Thread): 저수준·취소/진행률 수동. B(과한 actor/queue 프레임워크): 과설계. **C(ThreadPoolExecutor + JobContext)**: Qt 비의존·표준 라이브러리·취소(Event)/진행률(callback) 1급. → C.

## 1. Module Map
| 모듈 | 신규/수정 | 역할 |
|------|----------|------|
| `cmig/service/jobrunner.py` | 신규 | JobRunner·Job·JobStatus·JobContext·JobCancelled·make_sweep_job |
| `cmig/core/sweep.py` | 수정 | run_sweep 에 optional `progress`/`should_cancel`(default None, 무변) |
| `cmig/service/__init__.py` | 수정 | JobRunner export |
| `tests/test_jobrunner.py` | 신규 | submit/cancel/progress/retry/sweep-wiring/qt-isolation |

## 2. JobRunner 설계
```python
class JobStatus(Enum): PENDING RUNNING DONE FAILED CANCELLED
@dataclass JobContext:  cancel_event: Event;  report_progress(done,total);  @property cancelled
@dataclass Job:  job_id kind status progress(=(done,total)|None) result error(구조화 Diagnostic|None)
class JobCancelled(Exception)
class JobRunner:
  __init__(max_workers=4): ThreadPoolExecutor + _jobs/_specs/_events/_lock
  submit(kind, fn: Callable[[JobContext],Any], *, on_progress=None) -> job_id  # 비차단
  poll(job_id) -> Job        # 현재 상태(thread-safe read)
  cancel(job_id)             # 협조적: event.set() — fn 이 ctx.cancelled 확인해야 실제 중단
  result(job_id, timeout=None) -> Any   # future.result 대기
  retry(job_id) -> new_job_id           # _specs 의 (kind,fn,on_progress) 재제출
  shutdown()
```
- `_run(job,ctx,fn)`: status=RUNNING → `fn(ctx)` → DONE/result; `JobCancelled`→CANCELLED; `Exception`→FAILED+`Diagnostic.from_exception().to_json()`.
- thread 안전: status/progress 전이는 `_lock`; poll 은 dataclass read(GIL).
- **협조적 취소 정직 표기**: MICOM solve 는 GIL-bound C 호출 → in-flight 1건은 완료 후 경계에서 중단(즉시 kill 아님). docstring 명시.

## 3. sweep 훅 (실 wiring)
- `run_sweep(..., progress: Callable[[int,int],None]|None=None, should_cancel: Callable[[],bool]|None=None)`.
- 각 condition 전: `if should_cancel and should_cancel(): raise JobCancelled`; 후: `if progress: progress(i+1, total)`.
- default None → 기존 204 tests 무변.
- `make_sweep_job(axes, run_hash_fn, solve_fn, metric, cache=None) -> Callable[[JobContext],list[SweepRow]]`: ctx.report_progress·ctx.cancelled 를 run_sweep 훅에 연결 → **JobRunner 가 sweep 을 실제 구동**(orphan 아님, SC-J5).

## 4. Test Plan
| 테스트 | SC |
|--------|----|
| submit→DONE+result / raise→FAILED+diag | SC-J1 |
| cancel 협조적(루프 job) → CANCELLED | SC-J2 |
| progress 보고 → poll 반영 | SC-J3 |
| retry(failed) → 새 job 재실행 | SC-J4 |
| make_sweep_job → 진행률 advance·cancel 중단 | SC-J5 |
| Qt isolation(subprocess) · run_sweep 무변 회귀 | SC-J6 |

## 5. Next Steps
do → analyze → report → archive → Phase 0.3.
