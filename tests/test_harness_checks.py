"""Coverage and process isolation regressions for the shared catalogue."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scripts import harness_checks as hc


def test_catalogue_expands_without_duplicates() -> None:
    ids = [c.id for c in hc.resolve(["smoke", "quality"])]
    assert ids.count("ruff") == 1
    assert "ci-tests" in ids
    with pytest.raises(ValueError):
        hc.resolve(["does-not-exist"])


def test_junit_counts_and_missing_coverage(tmp_path: Path) -> None:
    xml = tmp_path / "x.xml"
    xml.write_text(
        '<testsuite><testcase classname="a" name="ok"/>'
        '<testcase classname="a" name="skip"><skipped/></testcase></testsuite>'
    )
    counts = hc.parse_junit(xml)
    assert (counts["collected"], counts["executed"], counts["skipped"]) == (2, 1, 1)
    xml.write_text("<testsuite/>")
    with pytest.raises(ValueError, match="no test cases"):
        hc.parse_junit(xml)


def test_missing_venv_is_blocked(tmp_path: Path) -> None:
    result = hc.run_check(hc.CHECKS["harness-tests"], tmp_path)
    assert result["status"] == "blocked"


def test_tier_deadline_between_checks_is_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter((0, 0, 76))
    calls = []

    def passed(check: hc.Check, *_args: object, **_kwargs: object) -> dict[str, object]:
        calls.append(check.id)
        return {"id": check.id, "status": "passed"}

    with monkeypatch.context() as patch:
        patch.setattr(hc.time, "monotonic", lambda: next(clock))
        patch.setattr(hc, "run_check", passed)
        results = hc.run_checks(["smoke"])
    assert calls == ["ruff"]
    assert [r["id"] for r in results] == ["ruff", "harness-tests"]
    assert results[-1]["status"] == "failed"
    assert results[-1]["timed_out"] is True


def test_timeout_preserves_byte_output(tmp_path: Path) -> None:
    result = hc.run_process(
        [
            sys.executable,
            "-c",
            "import sys,time;"
            "sys.stdout.buffer.write(b'partial\\xff');"
            "sys.stdout.flush();time.sleep(10)",
        ],
        cwd=tmp_path,
        timeout_s=1,
    )
    assert result["timed_out"]
    assert "partial" in result["stdout"]
    assert result["elapsed_s"] < 5


def test_windows_argv_uses_supplied_path_and_preserves_arguments(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin with spaces"
    bin_dir.mkdir()
    command = bin_dir / ("sample.cmd" if os.name == "nt" else "sample")
    command.write_text("@echo off\r\n" if os.name == "nt" else "#!/bin/sh\n", encoding="utf-8")
    if os.name != "nt":
        command.chmod(0o755)
    argv = ["sample", "argument with spaces", "한글"]
    env = os.environ.copy()
    env["PATH"] = str(bin_dir)
    assert hc._windows_argv(argv, env) == [str(command), *argv[1:]]
    assert hc._windows_argv(["unavailable", "arg"], env) == ["unavailable", "arg"]


def test_run_process_restores_exact_signal_handler(tmp_path: Path) -> None:
    watched = signal.SIGBREAK if os.name == "nt" else signal.SIGTERM
    original = signal.getsignal(watched)

    def prior_handler(_signum: int, _frame: object) -> None:
        pass

    signal.signal(watched, prior_handler)
    try:
        result = hc.run_process(
            [sys.executable, "-c", "print('done')"], cwd=tmp_path, timeout_s=3
        )
        assert result["exit_code"] == 0
        assert result["cancelled"] is False and result["timed_out"] is False
        assert signal.getsignal(watched) is prior_handler
    finally:
        signal.signal(watched, original)


def test_windows_communicate_uses_one_deadline_and_sends_input_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProcess:
        args = ["fake"]

        def __init__(self) -> None:
            self.calls: list[tuple[bytes | None, float]] = []

        def communicate(self, *, input: bytes | None, timeout: float) -> tuple[bytes, bytes]:
            self.calls.append((input, timeout))
            raise subprocess.TimeoutExpired(self.args, timeout)

    clock = iter((0.0, 0.05, 0.3, 0.7, 1.01))
    proc = FakeProcess()
    with monkeypatch.context() as patch:
        patch.setattr(hc.time, "monotonic", lambda: next(clock))
        with pytest.raises(subprocess.TimeoutExpired):
            hc._communicate_windows(proc, b"input", 1.0)  # type: ignore[arg-type]
    assert proc.calls == [(b"input", 0.1), (None, 0.1)]


def test_pytest_exit_five_and_all_skipped_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".venv/bin").mkdir(parents=True)
    (tmp_path / ".venv/bin/python").write_text("")
    check = hc.Check("fake", (hc.PYTHON, "-m", "pytest"), 1, True)
    monkeypatch.setattr(
        hc,
        "run_process",
        lambda *_a, **_k: {
            "exit_code": 5,
            "timed_out": False,
            "cancelled": False,
            "elapsed_s": 0.1,
            "stdout": "",
            "stderr": "",
        },
    )
    assert hc.run_check(check, tmp_path, output_dir=tmp_path)["status"] == "failed"
    (tmp_path / "fake.xml").write_text(
        '<testsuite><testcase classname="a" name="skip"><skipped/></testcase></testsuite>'
    )
    monkeypatch.setattr(
        hc,
        "run_process",
        lambda *_a, **_k: {
            "exit_code": 0,
            "timed_out": False,
            "cancelled": False,
            "elapsed_s": 0.1,
            "stdout": "",
            "stderr": "",
        },
    )
    assert hc.run_check(check, tmp_path, output_dir=tmp_path)["status"] == "failed"


def test_process_failure_with_junit_skips_stays_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".venv/bin").mkdir(parents=True)
    (tmp_path / ".venv/bin/python").write_text("")
    check = hc.Check("fake", (hc.PYTHON, "-m", "pytest"), 1, True)
    (tmp_path / "fake.xml").write_text(
        '<testsuite><testcase classname="a" name="ok"/>'
        '<testcase classname="a" name="skip"><skipped/></testcase></testsuite>'
    )
    monkeypatch.setattr(
        hc,
        "run_process",
        lambda *_a, **_k: {
            "exit_code": 1,
            "timed_out": False,
            "cancelled": False,
            "elapsed_s": 0.1,
            "stdout": "",
            "stderr": "failure",
        },
    )
    result = hc.run_check(check, tmp_path, output_dir=tmp_path)
    assert result["status"] == "failed"
    assert result["skipped"] == 1 and result["exit_code"] == 1


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups")
def test_parent_exits_before_pipe_inheriting_descendant(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    code = (
        "import pathlib,subprocess,sys;"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);"
        "pathlib.Path(sys.argv[1]).write_text(str(p.pid))"
    )
    result = hc.run_process([sys.executable, "-c", code, str(pid_file)], cwd=tmp_path, timeout_s=1)
    assert result["timed_out"] and result["elapsed_s"] < 5
    pid = int(pid_file.read_text())
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        status = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True
        )
        if status.returncode or status.stdout.strip().startswith("Z"):
            break
        time.sleep(0.05)
    else:
        pytest.fail("pipe-inheriting descendant survived timeout")


@pytest.mark.skipif(os.name == "nt", reason="POSIX SIGTERM")
def test_sigterm_parent_cleans_its_check_child(tmp_path: Path) -> None:
    marker = tmp_path / "child.pid"
    script = (
        "import json,signal,sys;from pathlib import Path;from scripts import harness_checks as h;"
        "prior=signal.getsignal(signal.SIGTERM);"
        "code='import os,pathlib,sys,time;"
        "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()));time.sleep(30)';"
        "r=h.run_process([sys.executable,'-c',code,sys.argv[1]],cwd=Path(sys.argv[2]),timeout_s=30);"
        "r['handler_restored']=signal.getsignal(signal.SIGTERM) is prior;"
        "print(json.dumps(r))"
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", script, str(marker), str(tmp_path)],
        cwd=hc.ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert marker.exists()
        child_pid = int(marker.read_text())
        parent.send_signal(signal.SIGTERM)
        out, err = parent.communicate(timeout=5)
        assert parent.returncode == 0, err.decode()
        result = json.loads(out)
        assert result["cancelled"] is True and result["timed_out"] is False
        assert result["handler_restored"] is True
        status = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(child_pid)], capture_output=True, text=True
        )
        assert status.returncode or status.stdout.strip().startswith("Z")
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.communicate(timeout=3)


@pytest.mark.parametrize("failure", ["error", "timeout"])
def test_windows_taskkill_failure_has_bounded_fallback(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    class FakeProcess:
        pid = 123
        killed = False

        def poll(self):
            return None

        def kill(self):
            self.killed = True

    def failed_run(*_args, **_kwargs):
        if failure == "error":
            raise OSError("taskkill unavailable")
        raise subprocess.TimeoutExpired("taskkill", 3)

    monkeypatch.setattr(hc.subprocess, "run", failed_run)
    monkeypatch.setattr(hc, "_windows_descendants", lambda _pid: [456, 789])
    killed_descendants = []
    monkeypatch.setattr(hc.os, "kill", lambda pid, _signal: killed_descendants.append(pid))
    proc = FakeProcess()
    hc._terminate_windows(proc)  # type: ignore[arg-type]
    assert proc.killed
    assert killed_descendants == [789, 456]
