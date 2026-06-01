"""JobRunner — in-process 비차단 실행 (Option C, Roadmap Phase 0.2).

Design Ref: cmig-jobrunner.design §2. Plan SC: SC-J1~J6.

concurrent.futures.ThreadPoolExecutor 기반(**Qt 비의존**) — submit/poll/cancel/retry/result +
진행률 + 협조적 취소(threading.Event). GUI(0.3)·Sweep View·Sandbox 가 공통 소비.

[협조적 취소 정직 표기] cancel() 은 cancel_event.set() 일 뿐 — job fn 이 ctx.cancelled 를
확인해야 실제 중단된다. MICOM solve 는 GIL-bound C 호출이라 in-flight 1건은 즉시 kill 되지
않고 condition 경계에서 중단된다(즉시 취소 아님).
"""

from __future__ import annotations

import enum
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from cmig.core.diagnostics import Diagnostic

_JobSpec = tuple[str, "Callable[[JobContext], Any]", "Callable[[int, int], None] | None"]


class JobStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobCancelled(Exception):
    """job fn 이 협조적 취소를 감지하면 raise — JobRunner 가 CANCELLED 로 처리."""


@dataclass
class JobContext:
    """job fn 에 주입 — 취소 확인·진행률 보고 채널."""

    cancel_event: threading.Event
    _progress_cb: Callable[[int, int], None] | None = None

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise JobCancelled()

    def report_progress(self, done: int, total: int) -> None:
        if self._progress_cb is not None:
            self._progress_cb(done, total)


@dataclass
class Job:
    """job 상태 스냅샷(poll 반환). error 는 구조화 Diagnostic JSON."""

    job_id: str
    kind: str
    status: JobStatus
    progress: tuple[int, int] | None = None
    result: Any | None = None
    error: str | None = None


class JobRunner:
    """비차단 작업 실행기. job fn 시그니처: Callable[[JobContext], Any]."""

    def __init__(self, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: dict[str, Job] = {}
        self._specs: dict[str, _JobSpec] = {}
        self._events: dict[str, threading.Event] = {}
        self._futures: dict[str, Future[Any]] = {}
        self._lock = threading.Lock()
        self._counter = 0

    def submit(
        self,
        kind: str,
        fn: Callable[[JobContext], Any],
        *,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> str:
        """비차단 제출 → job_id. fn 은 JobContext 를 받아 결과 반환(또는 JobCancelled raise)."""
        with self._lock:
            self._counter += 1
            job_id = f"job-{self._counter:04d}"
            event = threading.Event()
            job = Job(job_id=job_id, kind=kind, status=JobStatus.PENDING)
            self._jobs[job_id] = job
            self._specs[job_id] = (kind, fn, on_progress)
            self._events[job_id] = event
            self._futures[job_id] = self._executor.submit(
                self._run, job_id, fn, event, on_progress
            )
        return job_id

    def _run(
        self,
        job_id: str,
        fn: Callable[[JobContext], Any],
        event: threading.Event,
        on_progress: Callable[[int, int], None] | None,
    ) -> Any:
        def progress_cb(done: int, total: int) -> None:
            with self._lock:
                self._jobs[job_id].progress = (done, total)
            if on_progress is not None:
                on_progress(done, total)

        ctx = JobContext(cancel_event=event, _progress_cb=progress_cb)
        with self._lock:
            self._jobs[job_id].status = JobStatus.RUNNING
        if event.is_set():                                    # 시작 전 취소
            with self._lock:
                self._jobs[job_id].status = JobStatus.CANCELLED
            return None
        try:
            result = fn(ctx)
        except JobCancelled:
            with self._lock:
                self._jobs[job_id].status = JobStatus.CANCELLED
            return None
        except Exception as e:  # 실패도 누락 없이 구조화 diagnostic 으로 기록
            with self._lock:
                self._jobs[job_id].status = JobStatus.FAILED
                self._jobs[job_id].error = Diagnostic.from_exception(e).to_json()
            return None
        with self._lock:
            self._jobs[job_id].status = JobStatus.DONE
            self._jobs[job_id].result = result
        return result

    def poll(self, job_id: str) -> Job:
        """현재 job 상태 스냅샷(thread-safe read)."""
        with self._lock:
            j = self._jobs[job_id]
            return Job(j.job_id, j.kind, j.status, j.progress, j.result, j.error)

    def cancel(self, job_id: str) -> None:
        """협조적 취소 신호 — fn 이 ctx.cancelled 를 확인해야 실제 중단(정직 표기)."""
        with self._lock:
            event = self._events[job_id]
        event.set()

    def result(self, job_id: str, timeout: float | None = None) -> Any:
        """job 완료 대기 후 result 반환(future.result)."""
        self._futures[job_id].result(timeout=timeout)
        return self.poll(job_id).result

    def retry(self, job_id: str) -> str:
        """실패/취소 job 의 (kind, fn, on_progress) 재제출 → 새 job_id."""
        kind, fn, on_progress = self._specs[job_id]
        return self.submit(kind, fn, on_progress=on_progress)

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)


def make_sweep_job(
    axes: Any,
    *,
    run_hash_fn: Callable[[Any], str],
    solve_fn: Callable[[Any], float],
    metric: str,
    cache: Any | None = None,
) -> Callable[[JobContext], Any]:
    """sweep 을 JobRunner 로 구동하는 job fn 어댑터 (SC-J5, 실 wiring).

    ctx.report_progress·ctx.cancelled 를 run_sweep 의 progress/should_cancel 훅에 연결 →
    진행률(condition count) 보고 + 협조적 취소. orphan helper 아님 — JobRunner 가 실제 구동.
    """
    from cmig.core.sweep import run_sweep

    def _job(ctx: JobContext) -> Any:
        return run_sweep(
            axes, run_hash_fn=run_hash_fn, solve_fn=solve_fn, metric=metric, cache=cache,
            progress=ctx.report_progress, should_cancel=lambda: ctx.cancelled,
        )

    return _job
