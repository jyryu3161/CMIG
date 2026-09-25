"""Runner contracts with temporary Git repos and fake Codex/check results."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import venv
from pathlib import Path

import pytest

from scripts import execute


@pytest.fixture(autouse=True)
def isolate_nested_runner_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    # These fixture repositories are independent of the parent harness run.
    monkeypatch.delenv("CMIG_HARNESS_DEPTH", raising=False)
    monkeypatch.delenv("CMIG_STOP_HOOK_ACTIVE", raising=False)


def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "phases/demo").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "AGENTS.md").write_text("rules")
    (root / ".gitignore").write_text(".run/\n.venv/\n")
    (root / "scripts/harness_result.schema.json").write_text("{}")
    spec = {
        "schema_version": 1,
        "project": "CMIG",
        "phase": "demo",
        "steps": [
            {
                "step": 0,
                "name": "implement",
                "role": "implement",
                "read_files": ["AGENTS.md"],
                "write_paths": ["out.txt"],
                "checks": ["ruff"],
                "timeout_s": 20,
                "max_attempts": 2,
            },
            {
                "step": 1,
                "name": "review",
                "role": "review",
                "read_files": ["AGENTS.md"],
                "write_paths": [],
                "report_path": "review.md",
                "checks": ["ruff"],
                "timeout_s": 20,
            },
        ],
    }
    (root / "phases/demo/index.json").write_text(json.dumps(spec))
    for n in range(2):
        (root / f"phases/demo/step{n}.md").write_text("# Objective\n\n## Acceptance\n\nruff\n")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
    return root


def response(role: str, **changes: str) -> dict[str, str]:
    data = {
        "status": "completed",
        "summary": "done",
        "error_message": "",
        "blocked_reason": "",
        "report_markdown": "review evidence" if role == "review" else "",
        "verdict": "pass" if role == "review" else "",
    }
    data.update(changes)
    return data


def fake_run(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcomes: list[dict[str, str]],
    checks: list[list[dict[str, str]]] | None = None,
) -> list[list[str]]:
    monkeypatch.setattr(execute, "preflight", lambda _: "codex-cli test")
    seen: list[list[str]] = []

    def invoke(argv: list[str], **kwargs: object) -> dict[str, object]:
        seen.append(argv)
        role = "review" if "gpt-6-astra" in argv else "implement"
        if role == "implement":
            (root / "out.txt").write_text("implemented")
        final = Path(argv[argv.index("--output-last-message") + 1])
        final.write_text(json.dumps(outcomes.pop(0) if outcomes else response(role)))
        return {
            "exit_code": 0,
            "timed_out": False,
            "cancelled": False,
            "elapsed_s": 0.1,
            "stdout": '{"event":"done"}\n',
            "stderr": "",
        }

    monkeypatch.setattr(execute, "run_process", invoke)
    queue = checks or []
    monkeypatch.setattr(
        execute,
        "run_checks",
        lambda *_args, **_kwargs: queue.pop(0) if queue else [{"id": "ruff", "status": "passed"}],
    )
    return seen


def test_dry_run_no_process_or_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repo(tmp_path)
    monkeypatch.setattr(execute, "preflight", lambda _: pytest.fail("preflight on dry run"))
    assert execute.run_phase("demo", root=root, dry_run=True) == 0
    plan = json.loads(capsys.readouterr().out)
    assert [s["model"] for s in plan["steps"]] == ["gpt-6-sol", "gpt-6-astra"]
    assert not (root / ".run").exists()


def test_completed_requires_runner_checks_and_astra_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repo(tmp_path)
    seen = fake_run(root, monkeypatch, [response("implement"), response("review")])
    assert execute.run_phase("demo", root=root) == 0
    state = json.loads((root / ".run/harness/demo/state.json").read_text())
    assert state["status"] == "completed"
    assert state["steps"][1]["attempts"][0]["checks_reused"]
    assert [x["status"] for x in state["steps"]] == ["completed", "completed"]
    assert "--sandbox" not in seen[0]
    assert seen[1][seen[1].index("--sandbox") + 1] == "read-only"
    assert not any("dangerously-bypass" in item for argv in seen for item in argv)
    assert (
        subprocess.check_output(["git", "log", "-1", "--format=%s"], cwd=root).decode().strip()
        == "fixture"
    )


def test_failed_check_retries_but_never_silently_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repo(tmp_path)
    seen = fake_run(
        root,
        monkeypatch,
        [response("implement"), response("implement"), response("review")],
        [
            [{"id": "ruff", "status": "failed", "reason": "lint"}],
            [{"id": "ruff", "status": "passed"}],
            [{"id": "ruff", "status": "passed"}],
        ],
    )
    assert execute.run_phase("demo", root=root) == 0
    assert len(seen) == 3
    assert (root / ".run/harness/demo/step0-attempt1/events.jsonl").is_file()
    assert (root / ".run/harness/demo/step0-attempt2/events.jsonl").is_file()


def test_tier_expiry_stops_attempts_but_failed_checks_still_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repo(tmp_path)
    seen = fake_run(
        root,
        monkeypatch,
        [response("implement"), response("implement")],
        [
            [
                {
                    "id": "ruff",
                    "status": "failed",
                    "reason": "tier deadline exceeded",
                    "timed_out": True,
                }
            ]
        ],
    )
    with pytest.raises(execute.HarnessError, match="tier deadline exceeded"):
        execute.run_phase("demo", root=root)
    state = json.loads((root / ".run/harness/demo/state.json").read_text())
    assert len(seen) == len(state["steps"][0]["attempts"]) == 1
    assert state["status"] == "error"
    assert state["steps"][0]["attempts"][0]["timed_out"] is True


@pytest.mark.parametrize(
    "check",
    [
        {"id": "ruff", "status": "failed", "reason": "exit 5"},
        {"id": "ruff", "status": "partial", "reason": "skipped"},
        {"id": "ruff", "status": "blocked", "reason": "missing tool"},
    ],
)
def test_bad_check_cannot_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, check: dict[str, str]
) -> None:
    root = repo(tmp_path)
    fake_run(root, monkeypatch, [response("implement"), response("implement")], [[check], [check]])
    with pytest.raises(execute.HarnessError):
        execute.run_phase("demo", root=root)
    state = json.loads((root / ".run/harness/demo/state.json").read_text())
    assert state["status"] != "completed"


def test_review_changes_requested_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repo(tmp_path)
    fake_run(
        root, monkeypatch, [response("implement"), response("review", verdict="changes_requested")]
    )
    with pytest.raises(execute.HarnessError):
        execute.run_phase("demo", root=root)
    assert json.loads((root / ".run/harness/demo/state.json").read_text())["status"] == "error"


def test_dirty_overlap_rejected_and_unrelated_edit_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repo(tmp_path)
    (root / "out.txt").write_text("user")
    with pytest.raises(execute.HarnessError, match="overlap"):
        execute.run_phase("demo", root=root)
    assert (root / "out.txt").read_text() == "user"
    assert not (root / ".run").exists()


def test_unrelated_staged_selection_survives_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repo(tmp_path)
    (root / "notes.txt").write_text("user staged content")
    subprocess.run(["git", "add", "notes.txt"], cwd=root, check=True)
    before = subprocess.check_output(["git", "diff", "--cached", "--binary"], cwd=root)
    fake_run(root, monkeypatch, [response("implement"), response("review")])
    assert execute.run_phase("demo", root=root) == 0
    assert subprocess.check_output(["git", "diff", "--cached", "--binary"], cwd=root) == before
    assert (root / "notes.txt").read_text() == "user staged content"


def test_opt_in_commit_scopes_owned_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = repo(tmp_path)
    fake_run(root, monkeypatch, [response("implement"), response("review")])
    assert execute.run_phase("demo", root=root, commit=True) == 0
    changed = (
        subprocess.check_output(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"], cwd=root
        )
        .decode()
        .splitlines()
    )
    assert set(changed) == {"out.txt", "review.md"}
    assert json.loads((root / ".run/harness/demo/state.json").read_text())["status"] == "completed"


def test_invalid_phase_and_resume_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repo(tmp_path)
    spec_path = root / "phases/demo/index.json"
    spec = json.loads(spec_path.read_text())
    spec["steps"][0]["timeout_s"] = True
    spec_path.write_text(json.dumps(spec))
    with pytest.raises(execute.HarnessError, match="timeout"):
        execute.run_phase("demo", root=root, dry_run=True)
    spec["steps"][0]["timeout_s"] = 20
    spec_path.write_text(json.dumps(spec))
    fake_run(root, monkeypatch, [response("implement"), response("review")])
    execute.run_phase("demo", root=root)
    spec["steps"][0]["timeout_s"] = 21
    spec_path.write_text(json.dumps(spec))
    with pytest.raises(execute.HarnessError, match="fingerprint"):
        execute.run_phase("demo", root=root, resume=True)


def test_lock_and_atomic_write(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    execute.write_json(path, {"a": 1})
    assert json.loads(path.read_text()) == {"a": 1}
    assert execute.validate_result(json.dumps(response("review")), "review")["verdict"] == "pass"
    with pytest.raises(execute.HarnessError):
        execute.validate_result("{}", "review")


@pytest.mark.parametrize("mode", ["timeout", "nonzero", "missing-final", "scope"])
def test_child_failure_cannot_complete_or_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    root = repo(tmp_path)
    monkeypatch.setattr(execute, "preflight", lambda _: "codex-cli test")
    calls = []

    def invoke(argv: list[str], **_kwargs: object) -> dict[str, object]:
        calls.append(argv)
        if mode != "missing-final":
            Path(argv[argv.index("--output-last-message") + 1]).write_text(
                json.dumps(response("implement"))
            )
        if mode == "scope":
            (root / "outside.txt").write_text("unexpected")
        return {
            "exit_code": 1 if mode == "nonzero" else 0,
            "timed_out": mode == "timeout",
            "cancelled": False,
            "elapsed_s": 0.1,
            "stdout": "partial",
            "stderr": "unavailable model" if mode == "nonzero" else "",
        }

    monkeypatch.setattr(execute, "run_process", invoke)
    monkeypatch.setattr(execute, "run_checks", lambda *_a, **_k: pytest.fail("checks ran"))
    with pytest.raises(execute.HarnessError):
        execute.run_phase("demo", root=root)
    assert len(calls) == 1
    state = json.loads((root / ".run/harness/demo/state.json").read_text())
    assert state["status"] != "completed"
    assert state["steps"][0]["attempts"][0]["status"] == (
        "blocked" if mode == "nonzero" else "error"
    )


def test_lock_rejected_before_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = repo(tmp_path)
    lock = root / ".run/harness/demo/lock.json"
    lock.parent.mkdir(parents=True)
    lock.write_text('{"pid":1}')
    monkeypatch.setattr(execute, "preflight", lambda _: "codex-cli test")
    monkeypatch.setattr(execute, "run_process", lambda *_a, **_k: pytest.fail("child started"))
    with pytest.raises(execute.HarnessError, match="lock"):
        execute.run_phase("demo", root=root)
    assert lock.exists()


def test_nested_live_runner_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = repo(tmp_path)
    monkeypatch.setenv("CMIG_HARNESS_DEPTH", "1")
    with pytest.raises(execute.HarnessError, match="nested"):
        execute.run_phase("demo", root=root)
    assert execute.run_phase("demo", root=root, dry_run=True) == 0


def real_cli_fixture(root: Path, monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    source = Path(execute.__file__).parent
    for name in ("execute.py", "harness_checks.py"):
        shutil.copy2(source / name, root / "scripts" / name)
    subprocess.run(["git", "add", "scripts"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture runner"], cwd=root, check=True)
    bin_dir = root / "fake-bin"
    bin_dir.mkdir()
    codex = bin_dir / ("codex.py" if os.name == "nt" else "codex")
    shebang = "" if os.name == "nt" else "#!/usr/bin/env python3\n"
    codex.write_text(
        shebang + "import json, os, pathlib, subprocess, sys\n"
        "a=sys.argv[1:]\n"
        "if '--help' in a:\n"
        " print('--model --sandbox --json --output-schema --output-last-message')\n"
        " sys.exit(0)\n"
        "if '--version' in a: print('codex-cli fake'); sys.exit(0)\n"
        "role='review' if 'gpt-6-astra' in a else 'implement'\n"
        "mode=os.environ.get('CMIG_FAKE_MODE')\n"
        "if role=='implement':\n"
        " pathlib.Path('out.txt').write_text('implemented')\n"
        " if mode=='branch': subprocess.run(['git','checkout','-qb','unexpected'],check=True)\n"
        " if mode=='stage': subprocess.run(['git','add','out.txt'],check=True)\n"
        " if mode=='commit':\n"
        "  pathlib.Path('outside.txt').write_text('unowned')\n"
        "  subprocess.run(['git','add','out.txt','outside.txt'],check=True)\n"
        "  subprocess.run(['git','commit','-qm','unauthorized'],check=True)\n"
        "data={'status':'completed','summary':'done','error_message':'','blocked_reason':'',"
        "'report_markdown':'review findings 한글' if role=='review' else '',"
        "'verdict':'pass' if role=='review' else ''}\n"
        "pathlib.Path(a[a.index('--output-last-message')+1]).write_text("
        "json.dumps(data, ensure_ascii=False), encoding='utf-8')\n",
        encoding="utf-8",
        newline="\n",
    )
    if os.name == "nt":
        (bin_dir / "codex.cmd").write_text(
            f'@"{sys.executable}" "{codex}" %*\r\n', encoding="utf-8", newline=""
        )
    else:
        codex.chmod(0o755)
    # POSIX links retain the uv-managed runtime location; Windows uses native copies.
    venv.EnvBuilder(with_pip=False, symlinks=os.name != "nt").create(root / ".venv")
    checker_python = (
        root / ".venv/Scripts/python.exe"
        if os.name == "nt"
        else root / ".venv/bin/python"
    )
    site_packages = Path(
        subprocess.check_output(
            [str(checker_python), "-c", "import site; print(site.getsitepackages()[0])"],
            cwd=root,
            text=True,
        ).strip()
    )
    (site_packages / "ruff.py").write_text(
        "import os, pathlib, time\n"
        "mode=os.environ.get('CMIG_FAKE_MODE')\n"
        "if mode=='checkwrite': pathlib.Path('outside-check.txt').write_text('unowned')\n"
        "if mode=='cancelcheck':\n"
        " pathlib.Path('.run/harness/demo/check-started').write_text("
        "str(os.getpid()), encoding='utf-8')\n"
        " time.sleep(30)\n",
        encoding="utf-8",
        newline="\n",
    )
    monkeypatch.setenv("CMIG_FAKE_MODE", mode)
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])


@pytest.mark.parametrize("mode", ["branch", "commit", "stage", "checkwrite"])
def test_real_cli_rejects_unauthorized_git_and_check_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    root = repo(tmp_path)
    real_cli_fixture(root, monkeypatch, mode)
    original_head = execute.git("rev-parse", "HEAD", root=root)
    proc = subprocess.run(
        [sys.executable, str(root / "scripts/execute.py"), "demo"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode != 0, proc.stderr
    state = json.loads((root / ".run/harness/demo/state.json").read_text())
    assert state["status"] != "completed"
    assert len(state["steps"][0]["attempts"]) == 1
    assert "scope violation" in state["steps"][0]["reason"]
    assert state["steps"][1]["status"] == "pending"
    assert state["steps"][1]["attempts"] == []
    if mode == "branch":
        assert execute.git("branch", "--show-current", root=root) == "unexpected"
    elif mode == "commit":
        assert execute.git("rev-parse", "HEAD", root=root) != original_head
        assert (root / "outside.txt").read_text() == "unowned"
    elif mode == "stage":
        assert execute.git("diff", "--cached", "--name-only", root=root) == "out.txt"
    else:
        assert (root / "outside-check.txt").read_text() == "unowned"


def test_real_cli_korean_review_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repo(tmp_path / "fixture path with spaces")
    real_cli_fixture(root, monkeypatch, "success")
    proc = subprocess.run(
        [sys.executable, str(root / "scripts/execute.py"), "demo"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, proc.stderr
    report = root / "review.md"
    assert report.read_bytes() == bytes("review findings 한글", encoding="utf-8")
    assert report.read_text(encoding="utf-8") == "review findings 한글"
    state = json.loads((root / ".run/harness/demo/state.json").read_text(encoding="utf-8"))
    assert state["status"] == "completed"
    assert state["steps"][1]["attempts"][0]["response"]["report_markdown"] == (
        "review findings 한글"
    )
    final = Path(state["steps"][1]["attempts"][0]["final_path"])
    assert bytes("한글", encoding="utf-8") in final.read_bytes()


def _process_exited(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        if pid <= 0:
            raise ValueError(f"invalid process ID: {pid}")
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            error = ctypes.get_last_error()
            if error == 87:  # ERROR_INVALID_PARAMETER: the PID no longer exists
                return True
            raise OSError(error, f"OpenProcess failed for PID {pid}")
        try:
            exit_code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                raise OSError(ctypes.get_last_error(), f"GetExitCodeProcess failed for PID {pid}")
            return exit_code.value != 259  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    status = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True
    )
    return status.returncode != 0 or status.stdout.strip().startswith("Z")


_WINDOWS_CANCEL_CONTROLLER = """\
import ctypes
import json
import pathlib
import signal
import subprocess
import sys
import time
from ctypes import wintypes

root = pathlib.Path(sys.argv[1])
runner_pid_path = pathlib.Path(sys.argv[2])
runner = subprocess.Popen(
    [sys.executable, str(root / 'scripts/execute.py'), 'demo'],
    cwd=root,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
)
runner_pid_path.write_text(str(runner.pid), encoding='utf-8')
try:
    marker = root / '.run/harness/demo/check-started'
    deadline = time.monotonic() + 10
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not marker.exists():
        raise AssertionError('real check did not start before CTRL_BREAK')
    check_pid = int(marker.read_text(encoding='utf-8'))

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetConsoleProcessList.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
    kernel.GetConsoleProcessList.restype = wintypes.DWORD
    capacity = 16
    while True:
        attached = (wintypes.DWORD * capacity)()
        count = kernel.GetConsoleProcessList(attached, capacity)
        if count == 0:
            raise OSError(ctypes.get_last_error(), 'controller has no console')
        if count <= capacity:
            break
        capacity = count
    if runner.pid not in attached[:count]:
        raise AssertionError('runner is not attached to controller console')

    runner.send_signal(signal.CTRL_BREAK_EVENT)
    _out, err = runner.communicate(timeout=10)
    print(json.dumps({
        'returncode': runner.returncode,
        'stderr': err.decode('utf-8', 'replace'),
        'check_pid': check_pid,
        'shared_console': True,
    }), flush=True)
finally:
    if runner.poll() is None:
        runner.kill()
        runner.communicate(timeout=3)
"""


def _cancel_real_check_windows(root: Path) -> tuple[int, str, int]:
    runner_pid_path = root.parent / "controller-runner.pid"
    controller = subprocess.run(
        [sys.executable, "-c", _WINDOWS_CANCEL_CONTROLLER, str(root), str(runner_pid_path)],
        cwd=root,
        capture_output=True,
        timeout=20,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    assert controller.returncode == 0, controller.stderr.decode("utf-8", "replace")
    result = json.loads(controller.stdout.decode("utf-8"))
    assert result["shared_console"] is True
    return result["returncode"], result["stderr"], result["check_pid"]


def test_real_cli_sigint_during_check_stops_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repo(tmp_path)
    real_cli_fixture(root, monkeypatch, "cancelcheck")
    proc: subprocess.Popen[bytes] | None = None
    try:
        if os.name == "nt":
            returncode, stderr, check_pid = _cancel_real_check_windows(root)
        else:
            proc = subprocess.Popen(
                [sys.executable, str(root / "scripts/execute.py"), "demo"],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            deadline = time.monotonic() + 10
            while (
                not (root / ".run/harness/demo/check-started").exists()
                and time.monotonic() < deadline
            ):
                time.sleep(0.05)
            marker = root / ".run/harness/demo/check-started"
            assert marker.exists()
            check_pid = int(marker.read_text(encoding="utf-8"))
            proc.send_signal(signal.SIGINT)
            _out, err = proc.communicate(timeout=10)
            returncode, stderr = proc.returncode, err.decode()
        assert returncode == 130, stderr
        state = json.loads((root / ".run/harness/demo/state.json").read_text(encoding="utf-8"))
        assert state["status"] == "cancelled"
        assert state["steps"][1]["status"] == "pending"
        assert state["steps"][1]["attempts"] == []
        attempts = state["steps"][0]["attempts"]
        assert len(attempts) == 1
        assert attempts[0]["cancelled"] is True
        assert attempts[0]["timed_out"] is False
        assert len(attempts[0]["checks"]) == 1
        assert attempts[0]["checks"][0]["cancelled"] is True
        assert attempts[0]["checks"][0]["timed_out"] is False
        deadline = time.monotonic() + 2
        while not _process_exited(check_pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert _process_exited(check_pid), "cancelled check process survived"
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=3)
        if os.name == "nt":
            runner_pid_path = root.parent / "controller-runner.pid"
            if runner_pid_path.exists():
                runner_pid = int(runner_pid_path.read_text(encoding="utf-8"))
                if not _process_exited(runner_pid):
                    subprocess.run(
                        ["taskkill", "/T", "/F", "/PID", str(runner_pid)],
                        capture_output=True,
                        check=False,
                        timeout=3,
                    )
        marker = root / ".run/harness/demo/check-started"
        if marker.exists():
            check_pid = int(marker.read_text(encoding="utf-8"))
            if not _process_exited(check_pid):
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/T", "/F", "/PID", str(check_pid)],
                        capture_output=True,
                        check=False,
                        timeout=3,
                    )
                else:
                    try:
                        os.kill(check_pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups; native Windows unverified")
@pytest.mark.parametrize("interruption", ["deadline", "sigint"])
def test_real_codex_stop_pytest_tree_cleans_on_model_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interruption: str
) -> None:
    root = repo(tmp_path)
    source = Path(execute.__file__).parents[1]
    for rel in (
        "scripts/execute.py",
        "scripts/harness_checks.py",
        ".codex/hooks/stop.py",
        "pyproject.toml",
    ):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / rel, target)
    (root / "scripts/check_release_versions.py").write_text('print("fixture")\n')
    (root / ".venv").symlink_to(source / ".venv", target_is_directory=True)
    (root / "tests").mkdir()
    for name in ("checks", "hooks"):
        (root / f"tests/test_harness_{name}.py").write_text("")
    (root / "tests/test_harness_execute.py").write_text(
        "import json\nimport os\nimport time\nfrom pathlib import Path\n\n\n"
        "def test_long_running():\n"
        "    Path('.run/pytest.pid').write_text(str(os.getpid()))\n"
        "    Path('.run/pytest-env.json').write_text(json.dumps({\n"
        "        'depth': os.environ.get('CMIG_HARNESS_DEPTH'),\n"
        "        'stop': os.environ.get('CMIG_STOP_HOOK_ACTIVE'),\n"
        "    }))\n"
        "    time.sleep(60)\n"
    )
    spec_path = root / "phases/demo/index.json"
    spec = json.loads(spec_path.read_text())
    spec["steps"][0]["timeout_s"] = 4
    spec_path.write_text(json.dumps(spec))
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "nested hook fixture"], cwd=root, check=True)
    bin_dir = root / "fake-bin"
    bin_dir.mkdir()
    codex = bin_dir / "codex"
    codex.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, subprocess, sys, time\n"
        "if '--help' in sys.argv:\n"
        " print('--model --sandbox --json --output-schema --output-last-message')\n"
        " sys.exit(0)\n"
        "if '--version' in sys.argv: print('codex-cli fixture'); sys.exit(0)\n"
        "hook = subprocess.Popen([sys.executable, '.codex/hooks/stop.py'], stdin=subprocess.PIPE)\n"
        "pathlib.Path('.run/hook.pid').write_text(str(hook.pid))\n"
        "hook.stdin.write(b'{}')\n"
        "hook.stdin.close()\n"
        "time.sleep(60)\n"
    )
    codex.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    proc = subprocess.Popen(
        [sys.executable, str(root / "scripts/execute.py"), "demo"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        marker = root / ".run/pytest.pid"
        deadline = time.monotonic() + 8
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert marker.exists(), "real Stop hook did not reach pytest"
        if interruption == "sigint":
            proc.send_signal(signal.SIGINT)
        out, err = proc.communicate(timeout=12)
        assert proc.returncode == (130 if interruption == "sigint" else 1), (out, err)
        state = json.loads((root / ".run/harness/demo/state.json").read_text())
        assert state["status"] == ("cancelled" if interruption == "sigint" else "error")
        assert len(state["steps"][0]["attempts"]) == 1
        attempt = state["steps"][0]["attempts"][0]
        assert attempt["cancelled" if interruption == "sigint" else "timed_out"] is True
        assert json.loads((root / ".run/pytest-env.json").read_text()) == {
            "depth": "1",
            "stop": "1",
        }
        pytest_pid = int(marker.read_text())
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            status = subprocess.run(
                ["ps", "-o", "stat=", "-p", str(pytest_pid)], capture_output=True, text=True
            )
            if status.returncode or status.stdout.strip().startswith("Z"):
                break
            time.sleep(0.05)
        else:
            pytest.fail("Stop pytest descendant survived model interruption")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=3)
        for name in ("pytest.pid", "hook.pid"):
            pid_file = root / ".run" / name
            if pid_file.exists():
                try:
                    os.kill(int(pid_file.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass


def test_noncanonical_and_alias_outputs_rejected_before_launch(tmp_path: Path) -> None:
    root = repo(tmp_path)
    (root / "user.txt").write_text("precious pre-existing user edit")
    spec_path = root / "phases/demo/index.json"
    spec = json.loads(spec_path.read_text())
    for alias in ("./user.txt", "dir//user.txt", "user.txt/"):
        spec["steps"][1]["report_path"] = alias
        spec_path.write_text(json.dumps(spec))
        with pytest.raises(execute.HarnessError):
            execute.run_phase("demo", root=root, dry_run=True)
    (root / "alias").symlink_to(root, target_is_directory=True)
    spec["steps"][1]["report_path"] = "alias/user.txt"
    spec_path.write_text(json.dumps(spec))
    with pytest.raises(execute.HarnessError):
        execute.run_phase("demo", root=root, dry_run=True)
    spec["steps"][1]["report_path"] = "USER.txt"
    spec_path.write_text(json.dumps(spec))
    with pytest.raises(execute.HarnessError, match="case alias|overlap"):
        execute.run_phase("demo", root=root)
    assert (root / "user.txt").read_text() == "precious pre-existing user edit"
    assert execute.path_identity("Dir/File.TXT", windows=True) == "dir/file.txt"
    assert execute.path_identity(".GIT/config", windows=True).startswith(".git/")
    for protected in (".git/config", ".run/harness/demo/state.json"):
        with pytest.raises(execute.HarnessError, match="metadata|runtime"):
            execute.output_path(root, protected)
    assert execute.output_path(root, "한글 폴더/file name.txt") == root / "한글 폴더/file name.txt"


def test_tracked_owned_edit_and_benign_index_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repo(tmp_path)
    (root / "out.txt").write_text("old tracked content")
    subprocess.run(["git", "add", "out.txt"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "tracked output"], cwd=root, check=True)
    before = execute.git_identity(root)
    subprocess.run(["git", "update-index", "--refresh"], cwd=root, check=True)
    assert execute.git_identity(root) == before
    fake_run(root, monkeypatch, [response("implement"), response("review")])
    assert execute.run_phase("demo", root=root) == 0
    assert (root / "out.txt").read_text() == "implemented"


def test_resume_rejects_changed_input_and_incompatible_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repo(tmp_path)
    fake_run(root, monkeypatch, [response("implement"), response("review")])
    assert execute.run_phase("demo", root=root) == 0
    state_path = root / ".run/harness/demo/state.json"
    original = json.loads(state_path.read_text())
    assert execute.run_phase("demo", root=root, resume=True) == 0
    (root / "AGENTS.md").write_text("changed input")
    with pytest.raises(execute.HarnessError, match="input changed"):
        execute.run_phase("demo", root=root, resume=True)
    (root / "AGENTS.md").write_text("rules")
    with monkeypatch.context() as patch:
        patch.setenv("GRB_LICENSE_FILE", "changed-license-context")
        with pytest.raises(execute.HarnessError, match="fingerprint"):
            execute.run_phase("demo", root=root, resume=True)
    for mutate in (
        lambda s: s.update(schema_version=999),
        lambda s: s.update(status="error"),
        lambda s: s["steps"][0].update(attempts=[], evidence={}),
        lambda s: s["steps"][0]["attempts"][-1].update(checks=[]),
        lambda s: s["steps"][0].update(status="pending"),
    ):
        damaged = json.loads(json.dumps(original))
        mutate(damaged)
        state_path.write_text(json.dumps(damaged))
        with pytest.raises(execute.HarnessError):
            execute.run_phase("demo", root=root, resume=True)


def test_resume_accepts_ordered_tracked_edit_and_rejects_later_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repo(tmp_path)
    (root / "out.txt").write_text("old tracked content")
    spec_path = root / "phases/demo/index.json"
    spec = json.loads(spec_path.read_text())
    spec["steps"].insert(
        0,
        {
            "step": 0,
            "name": "plan",
            "role": "plan",
            "read_files": ["AGENTS.md", "out.txt"],
            "write_paths": [],
            "report_path": "plan.md",
            "checks": ["ruff"],
        },
    )
    for index, step in enumerate(spec["steps"]):
        step["step"] = index
    spec["steps"][1]["read_files"] += ["plan.md", "out.txt"]
    spec["steps"][2]["read_files"].append("out.txt")
    spec_path.write_text(json.dumps(spec))
    (root / "phases/demo/step2.md").write_text("# Objective\n\n## Acceptance\n\nruff\n")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "planned tracked edit"], cwd=root, check=True)
    seen = fake_run(
        root,
        monkeypatch,
        [response("review", verdict=""), response("implement"), response("review")],
    )
    assert execute.run_phase("demo", root=root) == 0
    assert execute.run_phase("demo", root=root, resume=True) == 0
    assert len(seen) == 3
    state_path = root / ".run/harness/demo/state.json"
    original = json.loads(state_path.read_text())
    stale = json.loads(json.dumps(original))
    stale["steps"][0]["attempts"][-1]["read_evidence"]["out.txt"] = {"content": "stale"}
    state_path.write_text(json.dumps(stale))
    with pytest.raises(execute.HarnessError, match="input changed"):
        execute.run_phase("demo", root=root, resume=True)
    state_path.write_text(json.dumps(original))
    (root / "out.txt").write_text("external tampering")
    with pytest.raises(execute.HarnessError, match="evidence changed"):
        execute.run_phase("demo", root=root, resume=True)
    assert len(seen) == 3


@pytest.mark.parametrize("bad_attempt", [None, {"checks": [None]}, {"checks": ["ruff"]}])
def test_resume_rejects_malformed_attempt_evidence_without_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad_attempt: object
) -> None:
    root = repo(tmp_path)
    seen = fake_run(root, monkeypatch, [response("implement"), response("review")])
    assert execute.run_phase("demo", root=root) == 0
    state_path = root / ".run/harness/demo/state.json"
    state = json.loads(state_path.read_text())
    state["steps"][0]["attempts"][-1] = bad_attempt
    state_path.write_text(json.dumps(state))
    with pytest.raises(execute.HarnessError, match="attempt evidence|role/check evidence"):
        execute.run_phase("demo", root=root, resume=True)
    assert len(seen) == 2
    assert json.loads(state_path.read_text()) == state


@pytest.mark.parametrize("malformed", [True, False])
def test_changed_phase_after_child_records_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, malformed: bool
) -> None:
    root = repo(tmp_path)
    fake_run(root, monkeypatch, [response("implement")])
    original_invoke = execute.run_process

    def corrupt(argv: list[str], **kwargs: object) -> dict[str, object]:
        result = original_invoke(argv, **kwargs)
        if malformed:
            (root / "phases/demo/index.json").write_text("{")
        else:
            spec = json.loads((root / "phases/demo/index.json").read_text())
            spec["steps"][0]["timeout_s"] = 21
            (root / "phases/demo/index.json").write_text(json.dumps(spec))
        return result

    monkeypatch.setattr(execute, "run_process", corrupt)
    with pytest.raises(execute.HarnessError, match="invalid phase JSON|phase definition changed"):
        execute.run_phase("demo", root=root)
    state = json.loads((root / ".run/harness/demo/state.json").read_text())
    assert state["status"] == "error"
    attempt = state["steps"][0]["attempts"][0]
    assert attempt["status"] == "error" and Path(attempt["final_path"]).exists()
    assert len(state["steps"][0]["attempts"]) == 1


@pytest.mark.parametrize("verdict", ["changes_requested", "blocked"])
def test_review_findings_published_on_nonpassing_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verdict: str
) -> None:
    root = repo(tmp_path)
    fake_run(root, monkeypatch, [response("implement"), response("review", verdict=verdict)])
    with pytest.raises(execute.HarnessError):
        execute.run_phase("demo", root=root)
    assert (root / "review.md").read_text() == "review evidence"
    state = json.loads((root / ".run/harness/demo/state.json").read_text())
    assert state["status"] != "completed"


def test_review_blocked_response_publishes_valid_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repo(tmp_path)
    fake_run(
        root,
        monkeypatch,
        [
            response("implement"),
            response(
                "review",
                status="blocked",
                blocked_reason="needs independent review",
                verdict="blocked",
            ),
        ],
    )
    with pytest.raises(execute.HarnessError):
        execute.run_phase("demo", root=root)
    assert (root / "review.md").read_text() == "review evidence"
    state = json.loads((root / ".run/harness/demo/state.json").read_text())
    assert state["status"] == "blocked"


def test_later_steps_read_declared_prior_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repo(tmp_path)
    spec_path = root / "phases/demo/index.json"
    spec = json.loads(spec_path.read_text())
    spec["steps"] = [
        {
            "step": 0,
            "name": "plan",
            "role": "plan",
            "read_files": ["AGENTS.md"],
            "write_paths": [],
            "report_path": "plan.md",
            "checks": ["ruff"],
        },
        {**spec["steps"][0], "step": 1, "read_files": ["AGENTS.md", "plan.md"]},
        {**spec["steps"][1], "step": 2, "read_files": ["AGENTS.md", "out.txt"]},
    ]
    spec_path.write_text(json.dumps(spec))
    (root / "phases/demo/step2.md").write_text("# Review\n\n## Acceptance\n\nruff\n")
    assert execute.run_phase("demo", root=root, dry_run=True) == 0
    forward = json.loads(spec_path.read_text())
    forward["steps"][0]["read_files"].append("out.txt")
    spec_path.write_text(json.dumps(forward))
    with pytest.raises(execute.HarnessError, match="required file missing"):
        execute.run_phase("demo", root=root, dry_run=True)
    spec_path.write_text(json.dumps(spec))
    monkeypatch.setattr(execute, "preflight", lambda _: "codex-cli test")
    roles = iter(["plan", "implement", "review"])

    def invoke(argv: list[str], **_kwargs: object) -> dict[str, object]:
        role = next(roles)
        if role == "implement":
            assert (root / "plan.md").read_text() == "plan evidence"
            (root / "out.txt").write_text("implemented")
        elif role == "review":
            assert (root / "out.txt").read_text() == "implemented"
        final = Path(argv[argv.index("--output-last-message") + 1])
        final.write_text(json.dumps(response(role, report_markdown=f"{role} evidence")))
        return {
            "exit_code": 0,
            "timed_out": False,
            "cancelled": False,
            "elapsed_s": 0.1,
            "stdout": "",
            "stderr": "",
        }

    monkeypatch.setattr(execute, "run_process", invoke)
    monkeypatch.setattr(
        execute, "run_checks", lambda *_a, **_k: [{"id": "ruff", "status": "passed"}]
    )
    assert execute.run_phase("demo", root=root) == 0
    assert (root / "review.md").read_text() == "review evidence"


def test_check_timeout_ends_without_correction_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repo(tmp_path)
    seen = fake_run(
        root,
        monkeypatch,
        [response("implement")],
        [
            [
                {
                    "id": "ruff",
                    "status": "failed",
                    "reason": "check timed out",
                    "timed_out": True,
                }
            ]
        ],
    )
    with pytest.raises(execute.HarnessError, match="timed out"):
        execute.run_phase("demo", root=root)
    assert len(seen) == 1
    state = json.loads((root / ".run/harness/demo/state.json").read_text())
    assert state["status"] == "error"
    assert state["steps"][0]["attempts"][0]["timed_out"]
