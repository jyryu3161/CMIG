"""Hook payload, subprocess protocol and no-recursion checks."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pretool_protocol_and_variants() -> None:
    path = ROOT / ".codex/hooks/pre_tool_use.py"
    for command in (
        "rm -fr /tmp/x",
        "git -c foo=bar reset --hard HEAD",
        "git push origin main -f",
        "git clean -dfx",
    ):
        proc = subprocess.run(
            [sys.executable, str(path)],
            input=json.dumps({"tool_input": {"cmd": command}}),
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 2
        assert command not in proc.stderr
    safe = subprocess.run(
        [sys.executable, str(path)],
        input='{"tool_input":{"command":"rm -f file"}}',
        capture_output=True,
        text=True,
    )
    assert safe.returncode == 0
    bad = subprocess.run([sys.executable, str(path)], input="[", capture_output=True, text=True)
    assert bad.returncode == 2


def test_stop_reentrant_and_first_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CMIG_STOP_HOOK_ACTIVE", raising=False)
    stop = load("cmig_stop", ROOT / ".codex/hooks/stop.py")
    called = []

    def fake(*_args):
        called.append(True)
        return [{"id": "ruff", "status": "failed", "reason": "exit 1", "stdout": "bad"}]

    assert stop.decide({"stop_hook_active": True}, checks=fake) is None
    assert not called
    result = stop.decide({}, checks=fake)
    assert result and result["decision"] == "block" and "ruff" in result["reason"]
    assert len(called) == 1


def test_stop_subprocess_reentrant_no_tests_launched() -> None:
    path = ROOT / ".codex/hooks/stop.py"
    proc = subprocess.run(
        [sys.executable, str(path)],
        input='{"stop_hook_active":true}',
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert proc.returncode == 0 and proc.stdout == ""


def test_client_configs_shared_and_bounded() -> None:
    codex = json.loads((ROOT / ".codex/hooks.json").read_text())
    claude = json.loads((ROOT / ".claude/settings.json").read_text())
    for config in (codex, claude):
        assert "stop.py" in config["hooks"]["Stop"][0]["hooks"][0]["command"]
        assert config["hooks"]["Stop"][0]["hooks"][0]["timeout"] == 90
        assert "pre_tool_use.py" in config["hooks"]["PreToolUse"][0]["hooks"][0]["command"]


def test_launcher_from_nested_directory_with_spaces(tmp_path: Path) -> None:
    root = tmp_path / "a space"
    hook = root / ".codex/hooks/pre_tool_use.py"
    hook.parent.mkdir(parents=True)
    hook.write_text((ROOT / ".codex/hooks/pre_tool_use.py").read_text())
    nested = root / "nested/deeper"
    nested.mkdir(parents=True)
    command = json.loads((ROOT / ".codex/hooks.json").read_text())["hooks"]["PreToolUse"][0][
        "hooks"
    ][0]["command"]
    result = subprocess.run(
        command,
        shell=True,
        cwd=nested,
        input='{"tool_input":{"command":"git reset --hard HEAD"}}',
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 2
    assert "destructive" in result.stderr
