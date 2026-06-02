"""Phase 0.2 — JobRunner. Plan SC: SC-J1~J6.

비차단 submit/poll/cancel/retry/result + 진행률 + 협조적 취소 + sweep 실 wiring. micom 불필요.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time

import pytest

from cmig.core.diagnostics import parse_diagnostic
from cmig.service import JobRunner, JobStatus, make_sweep_job
from cmig.service.jobrunner import JobCancelled, JobContext, JobFailed


def _runner() -> JobRunner:
    return JobRunner(max_workers=2)


def test_submit_done_and_result():
    """SC-J1: submit→DONE + result 정확."""
    r = _runner()
    jid = r.submit("calc", lambda ctx: 6 * 7)
    assert r.result(jid, timeout=5) == 42
    assert r.poll(jid).status is JobStatus.DONE
    r.shutdown()


def test_submit_failure_structured_diagnostic():
    """SC-J1: raise → FAILED + 구조화 diagnostic."""
    r = _runner()

    def boom(ctx: JobContext) -> int:
        raise RuntimeError("kaboom")

    jid = r.submit("boom", boom)
    with pytest.raises(JobFailed):
        r.result(jid, timeout=5)
    job = r.poll(jid)
    assert job.status is JobStatus.FAILED
    diag = parse_diagnostic(job.error)
    assert diag is not None and diag["code"] in ("solver_error", "infeasible")
    r.shutdown()


def test_cooperative_cancel():
    """SC-J2: ctx.cancelled 확인 루프 job → cancel() → CANCELLED."""
    r = _runner()
    started = threading.Event()

    def loop(ctx: JobContext) -> str:
        started.set()
        for _ in range(1000):
            ctx.raise_if_cancelled()
            time.sleep(0.005)
        return "finished"

    jid = r.submit("loop", loop)
    started.wait(timeout=2)
    r.cancel(jid)
    with pytest.raises(JobCancelled):
        r.result(jid, timeout=5)
    assert r.poll(jid).status is JobStatus.CANCELLED
    r.shutdown()


def test_progress_reporting():
    """SC-J3: ctx.report_progress → poll 진행률 반영 + on_progress 콜백."""
    r = _runner()
    seen: list[tuple[int, int]] = []

    def work(ctx: JobContext) -> int:
        for i in range(5):
            ctx.report_progress(i + 1, 5)
        return 5

    jid = r.submit("work", work, on_progress=lambda d, t: seen.append((d, t)))
    r.result(jid, timeout=5)
    assert r.poll(jid).progress == (5, 5)
    assert seen[-1] == (5, 5)
    r.shutdown()


def test_retry_failed_job():
    """SC-J4: retry(failed) → 새 job_id 재실행."""
    r = _runner()
    calls = {"n": 0}

    def flaky(ctx: JobContext) -> int:
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("first fails")
        return 99

    jid = r.submit("flaky", flaky)
    with pytest.raises(JobFailed):
        r.result(jid, timeout=5)
    assert r.poll(jid).status is JobStatus.FAILED
    jid2 = r.retry(jid)
    assert jid2 != jid
    assert r.result(jid2, timeout=5) == 99
    assert r.poll(jid2).status is JobStatus.DONE
    r.shutdown()


def test_make_sweep_job_progress_and_cancel():
    """SC-J5: make_sweep_job 가 run_sweep 을 실제 구동 — 진행률 advance."""
    from cmig.core.sweep import SweepAxis

    r = _runner()
    axes = [SweepAxis("tradeoff_f", [0.3, 0.5, 0.7, 0.9])]
    progress: list[tuple[int, int]] = []

    job = make_sweep_job(
        axes,
        run_hash_fn=lambda c: f"rh-{c.condition_id}",
        solve_fn=lambda c: float(c.axis_values["tradeoff_f"]),
        metric="growth",
    )
    jid = r.submit("sweep", job, on_progress=lambda d, t: progress.append((d, t)))
    rows = r.result(jid, timeout=5)
    assert len(rows) == 4
    assert progress[-1] == (4, 4)                 # 진행률 condition count
    assert r.poll(jid).status is JobStatus.DONE
    r.shutdown()


def test_sweep_cooperative_cancel_partial():
    """SC-J5: should_cancel → run_sweep 부분 결과 + service 층 JobCancelled → CANCELLED."""
    from cmig.core.sweep import SweepAxis, run_sweep

    # core run_sweep 직접: should_cancel 즉시 True → 0 rows (부분 결과, core 는 service 미의존)
    rows = run_sweep(
        [SweepAxis("tradeoff_f", [0.3, 0.5])],
        run_hash_fn=lambda c: c.condition_id,
        solve_fn=lambda c: 1.0,
        metric="g",
        should_cancel=lambda: True,
    )
    assert rows == []

    r = _runner()
    started = threading.Event()
    axes = [SweepAxis("tradeoff_f", [0.3, 0.5, 0.7])]

    def slow_solve(c):
        started.set()
        time.sleep(0.05)
        return 1.0

    jid = r.submit(
        "sweep",
        make_sweep_job(
            axes,
            run_hash_fn=lambda c: c.condition_id,
            solve_fn=slow_solve,
            metric="g",
        ),
    )
    started.wait(timeout=2)
    r.cancel(jid)
    with pytest.raises(JobCancelled):
        r.result(jid, timeout=5)
    assert r.poll(jid).status is JobStatus.CANCELLED
    r.shutdown()


def test_jobrunner_qt_independent():
    """SC-J6: cmig.service.jobrunner 단독 import 가 PySide6 미로드(subprocess)."""
    code = (
        "import sys; import cmig.service.jobrunner; "
        "assert 'PySide6' not in sys.modules; print('ok')"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert "ok" in res.stdout
