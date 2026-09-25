#!/usr/bin/env python3
"""Bounded Stop feedback. Runner acceptance remains independent."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from harness_checks import run_checks  # noqa: E402


def decide(payload: Any, *, root: Path = ROOT, checks=run_checks) -> dict[str, str] | None:
    if not isinstance(payload, dict):
        return {"decision": "block", "reason": "invalid Stop payload"}
    if payload.get("stop_hook_active") or os.environ.get("CMIG_STOP_HOOK_ACTIVE"):
        return None
    os.environ["CMIG_STOP_HOOK_ACTIVE"] = "1"
    try:
        results = checks(["smoke"], root)
    except Exception as exc:
        return {
            "decision": "block",
            "reason": f"smoke unavailable: {type(exc).__name__}: {str(exc)[:200]}",
        }
    finally:
        os.environ.pop("CMIG_STOP_HOOK_ACTIVE", None)
    if len(results) != 2 or any(r.get("status") != "passed" for r in results):
        failed = next((r for r in results if r.get("status") != "passed"), {})
        ident = failed.get("id", "missing-check")
        reason = failed.get("reason", "smoke catalogue incomplete")
        detail = (failed.get("stdout", "") + failed.get("stderr", ""))[-800:]
        return {"decision": "block", "reason": f"CMIG smoke {ident}: {reason}\n{detail}"[:1100]}
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, UnicodeError):
        payload = None
    result = decide(payload)
    if result:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
