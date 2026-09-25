#!/usr/bin/env python3
"""Sequential CMIG phase runner, adapted from kbase_kinase/scripts/execute.py
at 77354f94b844a8c64e7cd47691ac20a2e96214b3. CMIG owns state/checks,
keeps the invoking checkout and never commits unless explicitly requested.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import ntpath
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .harness_checks import ROOT, catalogue_hash, resolve, run_checks, run_process
except ImportError:  # direct `python scripts/execute.py`
    from harness_checks import ROOT, catalogue_hash, resolve, run_checks, run_process

MODELS = {"plan": "gpt-6-astra", "implement": "gpt-6-sol", "review": "gpt-6-astra"}
VALID_STATUS = {"pending", "running", "completed", "error", "blocked", "cancelled"}
DEFAULT_TIMEOUT = 1800
RESULT_SCHEMA = ROOT / "scripts/harness_result.schema.json"


class HarnessError(Exception):
    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Atomic state replacement; failures retain the old file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def path_identity(value: str, *, windows: bool = os.name == "nt") -> str:
    """One spelling per declared path; Windows comparisons ignore case."""
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or any(part in ("", ".", "..") for part in value.split("/"))
        or (windows and (ntpath.isabs(value) or ":" in value))
    ):
        raise HarnessError(f"invalid relative path: {value!r}")
    return ntpath.normcase(value).replace("\\", "/") if windows else value.casefold()


def contained(root: Path, value: str, *, exists: bool = False) -> Path:
    path_identity(value)
    path = root / value
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()) or resolved != path.absolute():
        raise HarnessError(f"path escapes repository: {value!r}")
    parent = root
    for component in value.split("/"):
        if parent.is_dir():
            for existing in parent.iterdir():
                if existing.name != component and existing.name.casefold() == component.casefold():
                    candidate = parent / component
                    if candidate.exists() and candidate.samefile(existing):
                        raise HarnessError(f"case alias is not a canonical path: {value!r}")
        parent /= component
    if exists and not path.is_file():
        raise HarnessError(f"required file missing: {value}")
    return path


def output_path(root: Path, value: str) -> Path:
    path = contained(root, value)
    if value.split("/", 1)[0].casefold() in (".git", ".run"):
        raise HarnessError(f"output targets Git metadata or harness runtime: {value}")
    return path


def git_identity(root: Path) -> tuple[str, str, str]:
    staged = subprocess.run(
        ["git", "ls-files", "--stage", "-z"], cwd=root, capture_output=True, check=True
    ).stdout
    return (
        git("rev-parse", "HEAD", root=root),
        git("branch", "--show-current", root=root),
        digest(staged),
    )


def verify_scope(
    root: Path,
    before: tuple[str, str, str],
    dirty: set[str],
    protected: dict[str, dict[str, str | None]],
    allowed: set[str],
) -> None:
    after = git_paths(root)
    allowed_ids = {path_identity(p) for p in allowed}
    before_ids = {path_identity(p) for p in dirty}
    unexpected = {p for p in after if path_identity(p) not in before_ids | allowed_ids}
    changed = [
        p
        for p in dirty
        if path_identity(p) not in allowed_ids and fingerprint_path(root, p) != protected[p]
    ]
    if git_identity(root) != before or unexpected or changed:
        raise HarnessError(
            f"scope violation: Git identity/index changed={git_identity(root) != before}, "
            f"new={sorted(unexpected)}, protected={sorted(changed)}",
            1,
        )


def git(*args: str, root: Path = ROOT) -> str:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    if proc.returncode:
        raise HarnessError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def git_paths(root: Path = ROOT) -> set[str]:
    proc = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    parts = proc.stdout.split(b"\0")
    paths: set[str] = set()
    i = 0
    while i < len(parts) and parts[i]:
        entry = parts[i]
        status = entry[:2].decode("ascii", "replace")
        paths.add(entry[3:].decode("utf-8", "surrogateescape"))
        if "R" in status or "C" in status:
            i += 1
            if i < len(parts):
                paths.add(parts[i].decode("utf-8", "surrogateescape"))
        i += 1
    return paths


def fingerprint_path(root: Path, rel: str) -> dict[str, str | None]:
    path = root / rel
    content = digest(path.read_bytes()) if path.is_file() else None
    mode = "symlink" if path.is_symlink() else "file" if path.is_file() else "absent"
    proc = subprocess.run(
        ["git", "ls-files", "-s", "--", rel], cwd=root, capture_output=True, check=True
    )
    return {"content": content, "mode": mode, "index": digest(proc.stdout)}


def tree_fingerprint(root: Path) -> str:
    paths = sorted(git_paths(root))
    payload = {
        "head": git("rev-parse", "HEAD", root=root),
        "paths": {p: fingerprint_path(root, p) for p in paths},
        "python": sys.executable,
        "environment_hash": digest(
            json.dumps(
                {
                    k: os.environ.get(k, "")
                    for k in ("VIRTUAL_ENV", "PATH", "GRB_LICENSE_FILE", "QT_QPA_PLATFORM")
                },
                sort_keys=True,
            ).encode()
        ),
    }
    return digest(json.dumps(payload, sort_keys=True).encode())


def runtime_fingerprint(
    codex_version: str, approval: str, sandbox: str | None, hook_trust_bypass: bool
) -> str:
    return digest(
        json.dumps(
            {
                "codex_version": codex_version,
                "python": sys.executable,
                "python_version": sys.version.split()[0],
                "approval": approval,
                "sandbox": sandbox or "user-configured",
                "hook_trust_bypass": hook_trust_bypass,
                "environment": {
                    key: os.environ.get(key, "")
                    for key in ("VIRTUAL_ENV", "PATH", "GRB_LICENSE_FILE", "QT_QPA_PLATFORM")
                },
            },
            sort_keys=True,
        ).encode()
    )


def validate_phase(phase: str, root: Path = ROOT) -> tuple[dict[str, Any], str]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", phase) or phase == "templates":
        raise HarnessError("phase must be a simple name under phases/")
    phase_dir = root / "phases" / phase
    index = contained(phase_dir, "index.json", exists=True)
    try:
        spec = json.loads(index.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HarnessError(f"invalid phase JSON: {exc}") from exc
    if (
        not isinstance(spec, dict)
        or spec.get("schema_version") != 1
        or spec.get("project") != "CMIG"
        or spec.get("phase") != phase
    ):
        raise HarnessError("invalid phase header/schema")
    steps = spec.get("steps")
    if not isinstance(steps, list) or not steps:
        raise HarnessError("phase requires nonempty steps")
    occupied: set[str] = set()
    produced: set[str] = set()
    names: set[str] = set()
    hashes = [index.read_bytes()]
    for n, step in enumerate(steps):
        if not isinstance(step, dict) or type(step.get("step")) is not int or step["step"] != n:
            raise HarnessError("step numbers must be unique and consecutive from zero")
        if (
            not isinstance(step.get("name"), str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", step["name"])
            or step["name"] in names
        ):
            raise HarnessError("step names must be unique, simple and nonempty")
        names.add(step["name"])
        role = step.get("role")
        if role not in MODELS:
            raise HarnessError(f"invalid role: {role}")
        for key in ("read_files", "write_paths", "checks"):
            if not isinstance(step.get(key), list) or (
                key in ("read_files", "checks") and not step[key]
            ):
                raise HarnessError(f"step {n} needs {key}")
        if role != "implement" and step["write_paths"]:
            raise HarnessError("plan/review must be read-only")
        if role == "implement" and not step["write_paths"]:
            raise HarnessError("implement needs owned write_paths")
        for rel in step["read_files"]:
            identity = path_identity(rel)
            if identity not in produced:
                contained(root, rel, exists=True)
        for rel in step["write_paths"]:
            output_path(root, rel)
            identity = path_identity(rel)
            if identity in occupied:
                raise HarnessError(f"duplicate owned path: {rel}")
            occupied.add(identity)
            produced.add(identity)
        report = step.get("report_path")
        if role in ("plan", "review") and not report:
            raise HarnessError(f"{role} requires report_path")
        if report:
            output_path(root, report)
            identity = path_identity(report)
            if identity in occupied:
                raise HarnessError(f"report collision: {report}")
            occupied.add(identity)
            produced.add(identity)
        if (
            type(step.get("timeout_s", DEFAULT_TIMEOUT)) is not int
            or not 0 < step.get("timeout_s", DEFAULT_TIMEOUT) <= 7200
        ):
            raise HarnessError("timeout_s must be an integer from 1 to 7200")
        if (
            type(step.get("max_attempts", 1)) is not int
            or not 1 <= step.get("max_attempts", 1) <= 3
        ):
            raise HarnessError("max_attempts must be 1..3")
        resolve(step["checks"])
        prompt = contained(phase_dir, f"step{n}.md", exists=True)
        body = prompt.read_text(encoding="utf-8")
        if not body.strip() or "## Acceptance" not in body:
            raise HarnessError(f"step{n}.md needs nonempty objective and Acceptance")
        hashes.append(prompt.read_bytes())
    if steps[-1]["role"] != "review":
        raise HarnessError("final step must be Astra review")
    hashes.append(catalogue_hash().encode())
    for source in (ROOT / "scripts/execute.py", ROOT / "scripts/harness_checks.py"):
        hashes.append(source.read_bytes())
    return spec, digest(b"\0".join(hashes))


def validate_result(raw: str, role: str) -> dict[str, str]:
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise HarnessError(f"invalid final JSON: {exc}", 1) from exc
    if not isinstance(data, dict) or set(data) != {
        "status",
        "summary",
        "error_message",
        "blocked_reason",
        "report_markdown",
        "verdict",
    }:
        raise HarnessError("final response fields mismatch schema", 1)
    if (
        any(not isinstance(v, str) for v in data.values())
        or data["status"] not in ("completed", "error", "blocked")
        or not data["summary"].strip()
    ):
        raise HarnessError("invalid final response values", 1)
    if data["status"] == "error" and not data["error_message"].strip():
        raise HarnessError("error response needs error_message", 1)
    if data["status"] == "blocked" and not data["blocked_reason"].strip():
        raise HarnessError("blocked response needs blocked_reason", 1)
    if role in ("plan", "review") and not data["report_markdown"].strip():
        raise HarnessError("plan/review needs report_markdown", 1)
    if role == "review" and data["verdict"] not in ("pass", "changes_requested", "blocked"):
        raise HarnessError("review needs verdict", 1)
    if role != "review" and data["verdict"]:
        raise HarnessError("non-review verdict is invalid", 1)
    return data


def codex_argv(
    step: dict[str, Any],
    root: Path,
    final: Path,
    *,
    sandbox: str | None,
    approval: str,
    hook_trust_bypass: bool,
) -> list[str]:
    argv = [
        "codex",
        "-a",
        approval,
        "exec",
        "--model",
        MODELS[step["role"]],
        "-c",
        'model_reasoning_effort="medium"',
        "--enable",
        "hooks",
        "--json",
        "--output-schema",
        str(root / "scripts/harness_result.schema.json"),
        "--output-last-message",
        str(final),
    ]
    effective_sandbox = "read-only" if step["role"] in ("plan", "review") else sandbox
    if effective_sandbox:
        argv += ["--sandbox", effective_sandbox]
    if hook_trust_bypass:
        argv += ["--dangerously-bypass-hook-trust"]
    return argv + ["-"]


def preflight(root: Path) -> str:
    result = run_process(["codex", "exec", "--help"], cwd=root, timeout_s=10)
    help_text = result["stdout"] + result["stderr"]
    required = ("--model", "--sandbox", "--json", "--output-schema", "--output-last-message")
    if result["exit_code"] != 0 or any(x not in help_text for x in required):
        raise HarnessError("Codex CLI missing or lacks required exec flags")
    version = run_process(["codex", "--version"], cwd=root, timeout_s=10)
    if version["exit_code"] != 0:
        raise HarnessError("Codex version preflight failed")
    return version["stdout"].strip()


def phase_prompt(
    root: Path, phase: str, step: dict[str, Any], state: dict[str, Any], retry: str
) -> str:
    previous = [
        f"Step {s['step']}: {s['summary']}" for s in state["steps"] if s["status"] == "completed"
    ]
    files = "\n\n".join(
        f"## {p}\n{(root / p).read_text(encoding='utf-8')}" for p in step["read_files"]
    )
    instructions = (
        f"CMIG phase {phase}, step {step['step']} ({step['role']}). Root AGENTS.md is auto-loaded. "
        "Read the declared context and inspect needed code. "
        "Do not edit phase specs or runner state. "
        f"Write only {step['write_paths']}; the runner writes report_path. "
        "Do not commit, push, switch branches or start a nested harness. "
        "Do not send Orca lifecycle messages. "
        "Return schema-valid final JSON. The runner independently executes checks.\n"
    )
    return (
        instructions
        + "\n"
        + "\n".join(previous)
        + "\n"
        + (f"Previous attempt failed: {retry}\n" if retry else "")
        + files
        + "\n\n"
        + (root / "phases" / phase / f"step{step['step']}.md").read_text(encoding="utf-8")
    )


def commit_scoped(root: Path, paths: list[str], phase: str) -> None:
    if not paths:
        return
    proc = subprocess.run(["git", "add", "--", *paths], cwd=root, capture_output=True, text=True)
    if proc.returncode:
        raise HarnessError(f"scoped stage failed: {proc.stderr.strip()}", 1)
    staged = set(
        filter(
            None,
            subprocess.run(
                ["git", "diff", "--cached", "--name-only", "-z"],
                cwd=root,
                capture_output=True,
                check=True,
            )
            .stdout.decode()
            .split("\0"),
        )
    )
    if not staged <= set(paths):
        raise HarnessError("staged content outside validated scope", 1)
    if staged:
        proc = subprocess.run(
            ["git", "commit", "-m", f"feat({phase}): validated harness phase"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        if proc.returncode:
            raise HarnessError(f"commit failed: {proc.stderr.strip()}", 1)


def validate_resume_state(
    state: Any,
    spec: dict[str, Any],
    root: Path,
    phase: str,
    phase_hash: str,
    identity: tuple[str, str, str],
    runtime_hash: str,
) -> None:
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise HarnessError("incompatible state schema")
    if (
        state.get("phase") != phase
        or state.get("phase_hash") != phase_hash
        or state.get("catalogue_hash") != catalogue_hash()
        or state.get("runtime_fingerprint") != runtime_hash
        or (state.get("head"), state.get("branch"), state.get("index_hash")) != identity
    ):
        raise HarnessError("resume fingerprint/HEAD/branch/index mismatch")
    steps = state.get("steps")
    if not isinstance(steps, list) or len(steps) != len(spec["steps"]):
        raise HarnessError("malformed state steps")
    if state.get("status") not in ("pending", "completed"):
        raise HarnessError("unresolved state; diagnose before resuming")
    completed = [s for s in steps if isinstance(s, dict) and s.get("status") == "completed"]
    if len(completed) != sum(s.get("status") == "completed" for s in steps if isinstance(s, dict)):
        raise HarnessError("malformed state steps")
    if any(not isinstance(s, dict) or s.get("step") != n for n, s in enumerate(steps)):
        raise HarnessError("malformed state step identity")
    statuses = [s.get("status") for s in steps]
    if statuses != ["completed"] * len(completed) + ["pending"] * (len(steps) - len(completed)):
        raise HarnessError("non-prefix or unresolved state steps")
    if (state["status"] == "completed") != (len(completed) == len(steps)):
        raise HarnessError("phase and step completion disagree")
    protected = state.get("protected")
    inputs = state.get("input_baseline")
    if not isinstance(protected, dict) or not isinstance(inputs, dict):
        raise HarnessError("missing state fingerprint evidence")
    if sorted(protected) != state.get("dirty_paths"):
        raise HarnessError("malformed protected path evidence")
    for rel, value in protected.items():
        if fingerprint_path(root, rel) != value:
            raise HarnessError(f"protected path changed since run: {rel}")
    completed_outputs = {
        p
        for definition in spec["steps"][: len(completed)]
        for p in [
            *definition["write_paths"],
            *([definition["report_path"]] if definition.get("report_path") else []),
        ]
    }
    for rel, value in inputs.items():
        if rel not in completed_outputs and fingerprint_path(root, rel) != value:
            raise HarnessError(f"declared input changed since run: {rel}")
    dirty_ids = {path_identity(p) for p in state["dirty_paths"]}
    output_ids = {path_identity(p) for p in completed_outputs}
    unexpected_dirty = {
        p for p in git_paths(root) if path_identity(p) not in dirty_ids | output_ids
    }
    if unexpected_dirty:
        raise HarnessError(f"unrelated paths changed since run: {sorted(unexpected_dirty)}")
    # Replay the recorded ownership order. A later completed owner may replace
    # a planner's input or an earlier output, but only its final evidence may
    # match the current file. Inputs with no owner remain bound to the baseline.
    expected_current = dict(inputs)
    for definition, record in zip(spec["steps"], steps, strict=True):
        if record["status"] != "completed":
            if not isinstance(record.get("attempts"), list) or record["attempts"]:
                raise HarnessError("pending step has unresolved attempts")
            continue
        attempts = record.get("attempts")
        evidence = record.get("evidence")
        if not isinstance(attempts, list) or not attempts or not isinstance(evidence, dict):
            raise HarnessError("completed step lacks attempt/evidence")
        expected_outputs = set(definition["write_paths"])
        if definition.get("report_path"):
            expected_outputs.add(definition["report_path"])
        if set(evidence) != expected_outputs:
            raise HarnessError("completed step output evidence mismatch")
        good = attempts[-1]
        if any(not isinstance(item, dict) for item in attempts):
            raise HarnessError("malformed completed-step attempt evidence")
        checks = good.get("checks")
        expected_checks = [c.id for c in resolve(definition["checks"])]
        read_evidence = good.get("read_evidence")
        if (
            good.get("status") != "completed"
            or good.get("exit_code") != 0
            or good.get("timed_out")
            or good.get("cancelled")
            or good.get("model") != MODELS[definition["role"]]
            or not isinstance(checks, list)
            or any(not isinstance(c, dict) for c in checks)
            or [c.get("id") for c in checks] != expected_checks
            or any(c.get("status") != "passed" for c in checks)
            or not isinstance(good.get("response"), dict)
            or good["response"].get("status") != "completed"
            or (definition["role"] == "review" and good["response"].get("verdict") != "pass")
            or not isinstance(read_evidence, dict)
            or set(read_evidence) != set(definition["read_files"])
        ):
            raise HarnessError("completed step lacks successful role/check evidence")
        for rel, value in read_evidence.items():
            expected = evidence if rel in definition["write_paths"] else expected_current
            if rel not in expected or value != expected[rel]:
                raise HarnessError(f"completed-step input changed: {rel}")
        expected_current.update(evidence)
    for rel, value in expected_current.items():
        if fingerprint_path(root, rel) != value:
            label = "completed-step evidence" if rel in completed_outputs else "declared input"
            raise HarnessError(f"{label} changed since run: {rel}")


def run_phase(
    phase: str,
    *,
    root: Path = ROOT,
    dry_run: bool = False,
    resume: bool = False,
    branch: str | None = None,
    commit: bool = False,
    sandbox: str | None = None,
    approval: str = "never",
    hook_trust_bypass: bool = False,
) -> int:
    if not dry_run and os.environ.get("CMIG_HARNESS_DEPTH"):
        raise HarnessError("nested live harness invocation refused")
    spec, phase_hash = validate_phase(phase, root)
    plan = [
        {
            "step": s["step"],
            "role": s["role"],
            "model": MODELS[s["role"]],
            "effort": "medium",
            "write_paths": s["write_paths"],
            "report_path": s.get("report_path"),
            "checks": [c.id for c in resolve(s["checks"])],
            "timeout_s": s.get("timeout_s", DEFAULT_TIMEOUT),
            "max_attempts": s.get("max_attempts", 1),
        }
        for s in spec["steps"]
    ]
    if dry_run:
        print(json.dumps({"phase": phase, "fingerprint": phase_hash, "steps": plan}, indent=2))
        return 0
    if branch and resume:
        raise HarnessError("cannot create branch while resuming")
    initial_dirty = git_paths(root)
    if not resume:
        for s in spec["steps"]:
            output_ids = {
                path_identity(p)
                for p in [*s["write_paths"], *([s["report_path"]] if s.get("report_path") else [])]
            }
            if {path_identity(p) for p in initial_dirty}.intersection(output_ids):
                raise HarnessError(f"declared output overlaps pre-existing edit: step {s['step']}")
    if (commit or branch) and initial_dirty:
        raise HarnessError("--commit/--branch require a clean initial worktree and index")
    if branch:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_/-]*", branch) or git(
            "branch", "--list", branch, root=root
        ):
            raise HarnessError("branch name invalid or already exists")
        git("checkout", "-b", branch, root=root)
    head, current_branch, index_hash = git_identity(root)
    identity = (head, current_branch, index_hash)
    run_dir = root / ".run" / "harness" / phase
    state_path = run_dir / "state.json"
    lock_path = run_dir / "lock.json"
    if state_path.exists() and not resume:
        raise HarnessError("existing state requires --resume or diagnosed manual recovery")
    if resume and not state_path.exists():
        raise HarnessError("no state to resume")
    codex_version = preflight(root)
    runtime_hash = runtime_fingerprint(codex_version, approval, sandbox, hook_trust_bypass)
    loaded_state_bytes = state_path.read_bytes() if resume else None
    if resume:
        assert loaded_state_bytes is not None
        try:
            state = json.loads(loaded_state_bytes)
        except (ValueError, UnicodeError) as exc:
            raise HarnessError(f"malformed state JSON: {exc}") from exc
        validate_resume_state(state, spec, root, phase, phase_hash, identity, runtime_hash)
        state["check_cache"] = {}
    else:
        state = {
            "schema_version": 1,
            "phase": phase,
            "phase_hash": phase_hash,
            "catalogue_hash": catalogue_hash(),
            "head": head,
            "branch": current_branch,
            "index_hash": index_hash,
            "created_at": stamp(),
            "dirty_paths": sorted(initial_dirty),
            "protected": {p: fingerprint_path(root, p) for p in initial_dirty},
            "input_baseline": {
                p: fingerprint_path(root, p)
                for p in {r for s in spec["steps"] for r in s["read_files"]}
                if (root / p).is_file()
            },
            "approval": approval,
            "sandbox": sandbox or "user-configured",
            "hook_trust_bypass": hook_trust_bypass,
            "codex_version": codex_version,
            "runtime_fingerprint": runtime_hash,
            "python_version": sys.version.split()[0],
            "status": "pending",
            "steps": [
                {"step": s["step"], "status": "pending", "attempts": []} for s in spec["steps"]
            ],
        }
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise HarnessError(
            f"another writer or stale lock at {lock_path}; inspect it manually"
        ) from exc
    with os.fdopen(fd, "w") as handle:
        json.dump({"pid": os.getpid(), "phase": phase, "started_at": stamp()}, handle)
    try:
        if not resume and state_path.exists():
            raise HarnessError("state appeared while acquiring the lock; retry with --resume")
        if resume and state_path.read_bytes() != loaded_state_bytes:
            raise HarnessError("state changed while acquiring the lock")
        write_json(state_path, state)
        for step, record in zip(spec["steps"], state["steps"], strict=True):
            if record["status"] == "completed":
                continue
            retry = ""
            for attempt in range(1, step.get("max_attempts", 1) + 1):
                before_dirty = git_paths(root)
                before_protected = {p: fingerprint_path(root, p) for p in before_dirty}
                for rel in step["read_files"]:
                    contained(root, rel, exists=True)
                record["status"] = state["status"] = "running"
                write_json(state_path, state)
                attempt_dir = run_dir / f"step{step['step']}-attempt{attempt}"
                attempt_dir.mkdir(parents=True, exist_ok=False)
                final_path = attempt_dir / "final.json"
                argv = codex_argv(
                    step,
                    root,
                    final_path,
                    sandbox=sandbox,
                    approval=approval,
                    hook_trust_bypass=hook_trust_bypass,
                )
                env = {k: v for k, v in os.environ.items() if not k.startswith("ORCA_")}
                env["CMIG_HARNESS_DEPTH"] = "1"
                started_at = stamp()
                process = run_process(
                    argv,
                    cwd=root,
                    timeout_s=step.get("timeout_s", DEFAULT_TIMEOUT),
                    input_bytes=phase_prompt(root, phase, step, state, retry).encode(),
                    env=env,
                )
                (attempt_dir / "events.jsonl").write_text(process["stdout"], encoding="utf-8")
                (attempt_dir / "stderr.txt").write_text(process["stderr"], encoding="utf-8")
                attempt_data: dict[str, Any] = {
                    "attempt": attempt,
                    "started_at": started_at,
                    "ended_at": stamp(),
                    "head": head,
                    "branch": current_branch,
                    "dirty_paths": sorted(before_dirty),
                    "read_evidence": {p: fingerprint_path(root, p) for p in step["read_files"]},
                    "phase_hash": phase_hash,
                    "catalogue_hash": catalogue_hash(),
                    "model": MODELS[step["role"]],
                    "effort": "medium",
                    "codex_version": codex_version,
                    "python_version": sys.version.split()[0],
                    "argv": argv,
                    "exit_code": process["exit_code"],
                    "timed_out": process["timed_out"],
                    "cancelled": process["cancelled"],
                    "elapsed_s": process["elapsed_s"],
                    "events_path": str(attempt_dir / "events.jsonl"),
                    "stderr_path": str(attempt_dir / "stderr.txt"),
                    "final_path": str(final_path),
                    "checks": [],
                }
                record["attempts"].append(attempt_data)
                reason = ""
                fatal = False
                blocked_response = False
                if process["timed_out"] or process["cancelled"]:
                    reason, fatal = "Codex timed out or was cancelled", True
                elif process["exit_code"] != 0:
                    reason = f"Codex exited {process['exit_code']}: {process['stderr'][-300:]}"
                    if process["exit_code"] is None or any(
                        word in process["stderr"].lower()
                        for word in ("model", "auth", "license", "not found", "no such file")
                    ):
                        fatal = True
                        blocked_response = True
                elif not final_path.is_file():
                    reason, fatal = "Codex final response missing", True
                else:
                    try:
                        response = validate_result(
                            final_path.read_text(encoding="utf-8"), step["role"]
                        )
                        attempt_data["response"] = response
                        if response["status"] != "completed":
                            reason = (
                                response["blocked_reason"]
                                if response["status"] == "blocked"
                                else response["error_message"]
                            )
                            fatal = response["status"] == "blocked"
                            blocked_response = fatal
                        elif step["role"] == "review" and response["verdict"] != "pass":
                            reason, fatal = f"review verdict: {response['verdict']}", True
                            blocked_response = response["verdict"] == "blocked"
                    except HarnessError as exc:
                        reason, fatal = str(exc), True
                try:
                    if validate_phase(phase, root)[1] != phase_hash:
                        raise HarnessError("phase definition changed during attempt", 1)
                    verify_scope(
                        root, identity, before_dirty, before_protected, set(step["write_paths"])
                    )
                    for rel, value in attempt_data["read_evidence"].items():
                        if rel not in step["write_paths"] and fingerprint_path(root, rel) != value:
                            raise HarnessError(f"declared input changed during attempt: {rel}", 1)
                except (HarnessError, OSError, ValueError) as exc:
                    reason, fatal = str(exc), True
                if not reason:
                    check_ids = [c.id for c in resolve(step["checks"])]
                    cache_key = digest(
                        json.dumps(
                            {
                                "tree": tree_fingerprint(root),
                                "checks": check_ids,
                                "catalogue": catalogue_hash(),
                            },
                            sort_keys=True,
                        ).encode()
                    )
                    cached = state.setdefault("check_cache", {}).get(cache_key)
                    check_dirty = git_paths(root)
                    check_protected = {p: fingerprint_path(root, p) for p in check_dirty}
                    checks: list[dict[str, Any]] = []
                    try:
                        checks = (
                            cached
                            if cached is not None
                            else run_checks(step["checks"], root, output_dir=attempt_dir)
                        )
                        verify_scope(root, identity, check_dirty, check_protected, set())
                        if validate_phase(phase, root)[1] != phase_hash:
                            raise HarnessError("phase definition changed during checks", 1)
                    except (HarnessError, OSError, ValueError) as exc:
                        reason, fatal = str(exc), True
                    attempt_data["checks"] = checks
                    attempt_data["checks_reused"] = cached is not None
                    if not reason and (
                        len(checks) != len(resolve(step["checks"]))
                        or any(c["status"] != "passed" for c in checks)
                    ):
                        failed = checks[-1] if checks else {"id": "none", "reason": "no checks"}
                        reason = f"check {failed['id']}: {failed.get('reason', 'failed')}"
                        fatal = bool(
                            failed.get("status") == "blocked"
                            or failed.get("cancelled")
                            or failed.get("timed_out")
                        )
                        blocked_response = failed.get("status") == "blocked"
                        if failed.get("cancelled"):
                            attempt_data["cancelled"] = True
                        if failed.get("timed_out"):
                            attempt_data["timed_out"] = True
                    elif not reason and cached is None:
                        state["check_cache"][cache_key] = checks
                response = attempt_data.get("response")
                report = step.get("report_path")
                publish_review = (
                    step["role"] == "review"
                    and isinstance(response, dict)
                    and (
                        (
                            response.get("status") == "completed"
                            and response.get("verdict") in ("changes_requested", "blocked")
                            and reason.startswith("review verdict:")
                        )
                        or (
                            response.get("status") == "blocked"
                            and reason == response.get("blocked_reason")
                        )
                    )
                )
                if not reason or publish_review:
                    try:
                        verify_scope(
                            root, identity, before_dirty, before_protected, set(step["write_paths"])
                        )
                        if report:
                            path = output_path(root, report)
                            if report in git_paths(root) and report not in before_dirty:
                                raise HarnessError(
                                    f"report target appeared during attempt: {report}", 1
                                )
                            path.parent.mkdir(parents=True, exist_ok=True)
                            path.write_text(response["report_markdown"], encoding="utf-8")
                        verify_scope(
                            root,
                            identity,
                            before_dirty,
                            before_protected,
                            set(step["write_paths"]) | ({report} if report else set()),
                        )
                    except (HarnessError, OSError, ValueError) as exc:
                        reason, fatal = str(exc), True
                        publish_review = False
                if not reason:
                    response = attempt_data["response"]
                    record.update(
                        status="completed",
                        summary=response["summary"],
                        completed_at=stamp(),
                        evidence={
                            p: fingerprint_path(root, p)
                            for p in [*step["write_paths"], *([report] if report else [])]
                        },
                    )
                    attempt_data["status"] = "completed"
                    write_json(state_path, state)
                    break
                attempt_data.update(
                    status="cancelled"
                    if attempt_data["cancelled"]
                    else "blocked"
                    if blocked_response
                    else "error",
                    reason=reason,
                )
                record.update(
                    status=attempt_data["status"],
                    reason=reason,
                )
                state["status"] = record["status"]
                write_json(state_path, state)
                if fatal or attempt == step.get("max_attempts", 1):
                    raise HarnessError(
                        reason,
                        130
                        if attempt_data["cancelled"]
                        else 2
                        if record["status"] == "blocked"
                        else 1,
                    )
                retry = reason
                record["status"] = state["status"] = "pending"
                write_json(state_path, state)
        if any(s["status"] != "completed" for s in state["steps"]):
            raise HarnessError("not all steps completed", 1)
        last = state["steps"][-1]["attempts"][-1].get("response", {})
        if last.get("verdict") != "pass":
            raise HarnessError("final Astra review did not pass", 1)
        try:
            verify_scope(
                root,
                identity,
                initial_dirty,
                state["protected"],
                {
                    p
                    for s in spec["steps"]
                    for p in [
                        *s["write_paths"],
                        *([s["report_path"]] if s.get("report_path") else []),
                    ]
                },
            )
        except HarnessError as exc:
            state["status"] = "error"
            state["reason"] = str(exc)
            write_json(state_path, state)
            raise
        if commit:
            owned = [
                p
                for s in spec["steps"]
                for p in [*s["write_paths"], *([s["report_path"]] if s.get("report_path") else [])]
            ]
            try:
                commit_scoped(root, owned, phase)
            except HarnessError as exc:
                state["status"] = "error"
                state["reason"] = str(exc)
                write_json(state_path, state)
                raise
        state["status"] = "completed"
        state["completed_at"] = stamp()
        write_json(state_path, state)
        return 0
    finally:
        lock_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a validated CMIG phase on the current checkout"
    )
    parser.add_argument("phase")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--branch", help="create a new branch; requires clean checkout")
    parser.add_argument("--commit", action="store_true", help="commit only validated owned paths")
    parser.add_argument(
        "--sandbox",
        choices=["read-only", "workspace-write", "danger-full-access"],
        help="implementation sandbox; default uses user configuration",
    )
    parser.add_argument("--approval-policy", choices=["never", "on-request"], default="never")
    parser.add_argument(
        "--trusted-hooks", action="store_true", help="use hook trust bypass for vetted automation"
    )
    args = parser.parse_args()
    try:
        return run_phase(
            args.phase,
            dry_run=args.dry_run,
            resume=args.resume,
            branch=args.branch,
            commit=args.commit,
            sandbox=args.sandbox,
            approval=args.approval_policy,
            hook_trust_bypass=args.trusted_hooks,
        )
    except HarnessError as exc:
        print(f"harness: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
