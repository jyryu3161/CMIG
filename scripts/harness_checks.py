#!/usr/bin/env python3
"""CMIG harness checks. Runner and Stop hook share this command catalogue.

Adapted from kbase_kinase hooks and runner at 77354f94b844a8c64e7cd47691ac20a2e96214b3;
CMIG requires runner-owned acceptance, JUnit coverage and bounded process groups.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
HARNESS_TESTS = [
    "tests/test_harness_execute.py",
    "tests/test_harness_hooks.py",
    "tests/test_harness_checks.py",
]
CI_TESTS = [
    "tests/test_sign.py",
    "tests/test_namespace_gate.py",
    "tests/test_run_hash.py",
    "tests/test_stats.py",
    "tests/test_model_quality.py",
    "tests/test_workflow_manifest.py",
    "tests/test_workflow_envelope_golden.py",
    "tests/test_search_ga.py",
    "tests/test_search_execution.py",
    "tests/test_search_benchmark.py",
    "tests/test_search_product_ga_scaling.py",
    "tests/test_cli_search_ga_config.py",
    "tests/test_run_transaction.py",
    *HARNESS_TESTS,
]


@dataclass(frozen=True)
class Check:
    id: str
    argv: tuple[str, ...]
    timeout_s: int
    junit: bool = False
    allow_skips: bool = False


CHECKS = {
    "ruff": Check("ruff", (PYTHON, "-m", "ruff", "check", "."), 30),
    "harness-tests": Check(
        "harness-tests", (PYTHON, "-m", "pytest", "-q", *HARNESS_TESTS), 65, True
    ),
    "lock": Check("lock", ("uv", "lock", "--check"), 90),
    "versions": Check("versions", (PYTHON, "scripts/check_release_versions.py"), 30),
    "mypy": Check("mypy", (PYTHON, "-m", "mypy", "cmig"), 120),
    "envelope": Check(
        "envelope",
        (
            PYTHON,
            "-c",
            "from cmig.cli.main import main; raise SystemExit(main())",
            "golden",
            "verify-envelope",
        ),
        30,
    ),
    "ci-tests": Check("ci-tests", (PYTHON, "-m", "pytest", "-q", *CI_TESTS), 480, True),
    "golden": Check(
        "golden",
        (
            PYTHON,
            "-c",
            "from cmig.cli.main import main; raise SystemExit(main())",
            "golden",
            "verify",
        ),
        120,
    ),
    "gurobi-license": Check(
        "gurobi-license",
        (
            PYTHON,
            "-c",
            "import gurobipy as gp; m=gp.Model(); x=m.addVar(lb=0); "
            "m.setObjective(x, gp.GRB.MAXIMIZE); m.addConstr(x<=1); m.optimize(); "
            "raise SystemExit(0 if m.Status==gp.GRB.OPTIMAL else 1)",
        ),
        30,
    ),
    "solver-tests": Check(
        "solver-tests",
        (
            PYTHON,
            "-m",
            "pytest",
            "-q",
            "tests/test_engine_golden.py",
            "tests/test_search_policy_v2.py",
            "tests/test_search_service.py",
        ),
        1500,
        True,
    ),
    "gui-tests": Check(
        "gui-tests",
        (
            PYTHON,
            "-m",
            "pytest",
            "-q",
            "tests/test_app_shell.py",
            "tests/test_gui_round5_p2.py",
            "tests/test_gui_launcher.py",
        ),
        1500,
        True,
    ),
    "full-tests": Check("full-tests", (PYTHON, "-m", "pytest", "-q"), 2400, True),
    "publication-smoke": Check(
        "publication-smoke",
        (PYTHON, "-m", "pytest", "-q", "tests/test_publication_benchmark.py"),
        240,
        True,
    ),
}
TIERS = {
    "smoke": ("ruff", "harness-tests"),
    "quality": ("ruff", "harness-tests", "lock", "versions", "mypy", "envelope", "ci-tests"),
    "solver": ("gurobi-license", "golden", "solver-tests"),
    "gui": (
        "ruff",
        "harness-tests",
        "lock",
        "versions",
        "mypy",
        "envelope",
        "ci-tests",
        "gui-tests",
    ),
    "full": (
        "ruff",
        "harness-tests",
        "lock",
        "versions",
        "mypy",
        "envelope",
        "ci-tests",
        "gurobi-license",
        "golden",
        "full-tests",
        "publication-smoke",
    ),
}
TIER_LIMITS = {"smoke": 75, "quality": 900, "solver": 1800, "gui": 1800, "full": 2700}


def catalogue_hash() -> str:
    payload = {"checks": {k: asdict(v) for k, v in CHECKS.items()}, "tiers": TIERS}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def resolve(ids: list[str]) -> list[Check]:
    if not ids:
        raise ValueError("at least one check is required")
    seen: set[str] = set()
    result = []
    for check_id in ids:
        for expanded in TIERS.get(check_id, (check_id,)):
            if expanded not in CHECKS:
                raise ValueError(f"unknown check: {expanded}")
            if expanded not in seen:
                seen.add(expanded)
                result.append(CHECKS[expanded])
    return result


def project_python(root: Path) -> Path:
    for p in (root / ".venv/bin/python", root / ".venv/Scripts/python.exe"):
        if p.is_file():
            return p
    raise FileNotFoundError("CMIG .venv Python missing; run explicit uv sync before checks")


def _windows_descendants(parent_pid: int) -> list[int]:
    """Snapshot descendant PIDs, including when the original leader already exited."""
    import ctypes
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32FirstW.restype = wintypes.BOOL
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        return []
    parents: dict[int, int] = {}
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(ProcessEntry)
        found = kernel.Process32FirstW(handle, ctypes.byref(entry))
        while found:
            parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            found = kernel.Process32NextW(handle, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(handle)
    found: list[int] = []
    frontier = [parent_pid]
    while frontier:
        children = [pid for pid, ppid in parents.items() if ppid in frontier and pid not in found]
        found.extend(children)
        frontier = children
    return found


def _terminate_windows(proc: subprocess.Popen[bytes]) -> None:
    try:
        descendants = _windows_descendants(proc.pid)
    except (OSError, AttributeError):
        descendants = []
    try:
        result = subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
            capture_output=True,
            check=False,
            timeout=3,
        )
        tree_killed = result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        tree_killed = False
    if not tree_killed:
        for pid in reversed(descendants):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
    if proc.poll() is None:
        proc.kill()


def _terminate(proc: subprocess.Popen[bytes]) -> tuple[bytes, bytes]:
    if os.name == "nt":
        _terminate_windows(proc)
    else:
        try:
            # The Stop hook shares this group, but its checks have their own.
            # Give the hook time to clean those checks before forcing the group down.
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            # Waiting for pipe EOF also covers a leader that exits before its children.
            return proc.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)
    return _drain_after_termination(proc)


def _drain_after_termination(proc: subprocess.Popen[bytes]) -> tuple[bytes, bytes]:
    try:
        return proc.communicate(timeout=2)
    except subprocess.TimeoutExpired as exc:
        for stream in (proc.stdout, proc.stderr):
            if stream is not None:
                stream.close()
        return exc.stdout or b"", exc.stderr or b""


def run_process(
    argv: list[str],
    *,
    cwd: Path,
    timeout_s: int,
    input_bytes: bytes | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run one bounded tree. Bytes survive TimeoutExpired on every Python version."""
    start = time.monotonic()
    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            stdin=subprocess.PIPE if input_bytes is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            start_new_session=os.name != "nt",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
    except OSError as exc:
        return {
            "argv": argv,
            "exit_code": None,
            "stdout": "",
            "stderr": str(exc),
            "timed_out": False,
            "cancelled": False,
            "elapsed_s": time.monotonic() - start,
        }
    timed_out = cancelled = False
    out = err = b""
    old_term = None
    if os.name != "nt" and hasattr(signal, "SIGTERM"):
        try:
            old_term = signal.getsignal(signal.SIGTERM)

            def on_term(_signum: int, _frame: Any) -> None:
                raise KeyboardInterrupt

            signal.signal(signal.SIGTERM, on_term)
        except ValueError:  # non-main thread: caller owns its signal lifecycle
            old_term = None
    try:
        out, err = proc.communicate(input=input_bytes, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        out = exc.stdout or b""
        err = exc.stderr or b""
        extra_out, extra_err = _terminate(proc)
        out = extra_out or out
        err = extra_err or err
    except KeyboardInterrupt:
        cancelled = True
        out, err = _terminate(proc)
    finally:
        if old_term is not None:
            signal.signal(signal.SIGTERM, old_term)
    return {
        "argv": argv,
        "exit_code": proc.returncode,
        "stdout": out.decode("utf-8", "replace"),
        "stderr": err.decode("utf-8", "replace"),
        "timed_out": timed_out,
        "cancelled": cancelled,
        "elapsed_s": time.monotonic() - start,
    }


def parse_junit(path: Path) -> dict[str, Any]:
    tree = ET.parse(path)
    cases = tree.findall(".//testcase")
    if not cases:
        raise ValueError("JUnit contains no test cases")
    skipped = []
    failures = []
    for case in cases:
        node = f"{case.get('classname', '')}::{case.get('name', '')}"
        if case.find("skipped") is not None:
            skipped.append(node)
        if case.find("failure") is not None or case.find("error") is not None:
            failures.append(node)
    return {
        "collected": len(cases),
        "executed": len(cases) - len(skipped),
        "skipped": len(skipped),
        "skip_nodes": skipped,
        "failure_nodes": failures,
    }


def run_check(
    check: Check,
    root: Path = ROOT,
    *,
    output_dir: Path | None = None,
    timeout_s: int | None = None,
) -> dict[str, Any]:
    try:
        python = project_python(root)
    except FileNotFoundError as exc:
        return {"id": check.id, "status": "blocked", "reason": str(exc), "argv": list(check.argv)}
    argv = [str(python) if x == PYTHON else x for x in check.argv]
    junit_path = None
    if check.junit:
        if output_dir is None:
            output_dir = Path(tempfile.mkdtemp(prefix="cmig-check-"))
        output_dir.mkdir(parents=True, exist_ok=True)
        junit_path = output_dir / f"{check.id}.xml"
        argv += [f"--junitxml={junit_path}"]
    env = os.environ.copy()
    if check.id == "gui-tests":
        env["QT_QPA_PLATFORM"] = "offscreen"
    process = run_process(argv, cwd=root, timeout_s=timeout_s or check.timeout_s, env=env)
    result: dict[str, Any] = {
        "id": check.id,
        "argv": argv,
        "exit_code": process["exit_code"],
        "elapsed_s": process["elapsed_s"],
        "timed_out": process["timed_out"],
        "cancelled": process["cancelled"],
        "stdout": process["stdout"],
        "stderr": process["stderr"],
        "junit_path": str(junit_path) if junit_path else None,
    }
    if process["timed_out"] or process["cancelled"]:
        result.update(status="failed", reason="check timed out or was cancelled")
    elif process["exit_code"] is None:
        result.update(status="blocked", reason="command unavailable")
    elif process["exit_code"] != 0:
        result.update(
            status="blocked" if check.id == "gurobi-license" else "failed",
            reason=f"exit {process['exit_code']}",
        )
    else:
        result.update(status="passed", reason="")
    if junit_path:
        try:
            counts = parse_junit(junit_path)
            result.update(counts)
            if result["status"] == "passed" and (
                counts["executed"] == 0 or counts["failure_nodes"]
            ):
                result.update(status="failed", reason="no executed tests or JUnit failures")
            elif result["status"] == "passed" and counts["skipped"] and not check.allow_skips:
                result.update(status="partial", reason="unexpected skipped tests")
        except (OSError, ET.ParseError, ValueError) as exc:
            if result["status"] == "passed":
                result.update(status="failed", reason=f"invalid/missing JUnit: {exc}")
            else:
                result["junit_error"] = f"invalid/missing JUnit: {exc}"
    return result


def run_checks(
    ids: list[str], root: Path = ROOT, *, output_dir: Path | None = None
) -> list[dict[str, Any]]:
    checks = resolve(ids)
    results = []
    started = time.monotonic()
    limit = TIER_LIMITS.get(ids[0]) if len(ids) == 1 else None
    for check in checks:
        remaining = max(0, math.ceil(limit - (time.monotonic() - started))) if limit else None
        if remaining == 0:
            results.append(
                {
                    "id": check.id,
                    "status": "failed",
                    "reason": "tier deadline exceeded",
                    "timed_out": True,
                    "cancelled": False,
                }
            )
            break
        result = run_check(
            check,
            root,
            output_dir=output_dir,
            timeout_s=min(check.timeout_s, remaining) if remaining else check.timeout_s,
        )
        results.append(result)
        if result["status"] != "passed":
            break
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CMIG harness validation tiers")
    parser.add_argument("--tier", choices=sorted(TIERS), required=True)
    args = parser.parse_args()
    results = run_checks([args.tier])
    for result in results:
        print(f"{result['id']}: {result['status']} {result.get('reason', '')}")
        if result["status"] != "passed":
            print((result.get("stdout", "") + result.get("stderr", ""))[-1500:])
    return (
        0
        if len(results) == len(resolve([args.tier]))
        and all(r["status"] == "passed" for r in results)
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
