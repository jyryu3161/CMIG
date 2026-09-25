#!/usr/bin/env python3
"""Small accident guard shared by Codex and Claude; no subprocesses."""

from __future__ import annotations

import json
import re
import shlex
import sys
from typing import Any


def _tokens(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def dangerous(command: str | list[str]) -> bool:
    if isinstance(command, list):
        tokens = [str(x) for x in command]
    else:
        tokens = _tokens(command)
    low = [x.lower() for x in tokens]
    for i, token in enumerate(low):
        if token in ("rm", "git") or token.endswith(("/rm", "\\rm", "/git", "\\git")):
            args = low[i + 1 :]
            if token.endswith("rm"):
                flags = [x for x in args if x.startswith("-")]
                recursive = any("r" in x.lstrip("-") or x == "--recursive" for x in flags)
                force = any("f" in x.lstrip("-") or x == "--force" for x in flags)
                if recursive and force:
                    return True
            else:
                if "push" in args and any(
                    x in ("-f", "--force", "--force-with-lease") for x in args
                ):
                    return True
                if "reset" in args and "--hard" in args:
                    return True
                if "clean" in args and any(
                    re.fullmatch(r"-[a-z]*f[a-z]*", x) or x == "--force" for x in args
                ):
                    return True
    return bool(re.search(r"\bdrop\s+table\b", " ".join(low), re.I))


def decide(payload: Any) -> tuple[int, str]:
    if not isinstance(payload, dict):
        return 2, "invalid hook payload"
    tool_input = payload.get("tool_input", payload)
    if not isinstance(tool_input, dict):
        return 2, "invalid tool input"
    command = tool_input.get("command", tool_input.get("cmd"))
    if command is None:
        return 0, ""
    if (
        not isinstance(command, (str, list))
        or isinstance(command, list)
        and not all(isinstance(x, str) for x in command)
    ):
        return 2, "invalid shell command type"
    return (2, "destructive shell operation blocked") if dangerous(command) else (0, "")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, UnicodeError):
        print("invalid hook JSON", file=sys.stderr)
        return 2
    code, message = decide(payload)
    if message:
        print(message, file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
