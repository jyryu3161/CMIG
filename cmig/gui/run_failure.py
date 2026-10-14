"""Why a CLI-backed GUI run failed, in the user's terms (Qt-free).

Every analysis page runs `cmig.cli.main.main(argv)` in a job. When that returns non-zero the
page used to show `"<kind> failed with rc=N"` wrapped in a `solver_error` Diagnostic: the CLI's
own reason (written to stderr) was lost, an input refusal (exit 2) read as a solver failure,
and the CLI's hint "pass --allow-failed-run" — a flag the GUI does not have — was shown as the
cause. These helpers are shared by every page so the wording and the rules are the same.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from typing import Any

#: Lines the CLI writes that are not a reason in the GUI: its exit-3 hint names a CLI-only
#: flag and a staging path that no longer exists once the run is published; the solver
#: prints its licence banner on first use.
_NOT_A_REASON = (
    "--allow-failed-run",
    "analysis failed: artifacts were written to",
    "Set parameter ",
    "Academic license",
    "Restricted license",
    "Using license file",
)

_MAX_REASON = 220


def cli_error_text(chunks: Iterable[str]) -> str:
    """The CLI's stderr reason, without CLI-only hints and solver banners."""
    lines = "".join(chunks).splitlines()
    kept = [
        line.strip() for line in lines
        if line.strip() and not any(marker in line for marker in _NOT_A_REASON)
    ]
    return "\n".join(kept)


def cli_failure(label: str, rc: int, error_text: str) -> Exception:
    """The exception a GUI job raises for a non-zero CLI exit.

    Exit 2 is an input refusal (`JobInputError`, recorded as `input_error`), never a solver
    error. The message keeps `rc=N` so the run list and the tooltips still show the exit code.
    """
    from cmig.service.jobrunner import JobInputError

    message = f"{label} failed (rc={rc})" + (f": {error_text}" if error_text else "")
    if rc == 2:
        return JobInputError(message)
    return RuntimeError(message)


def job_error_text(error: str | None) -> str:
    """A job's recorded error as readable text (a serialized Diagnostic or plain text)."""
    if not error:
        return ""
    from cmig.core.diagnostics import parse_diagnostic

    message = str((parse_diagnostic(error) or {}).get("message") or error)
    return message.removeprefix("RuntimeError: ").strip()


def _diagnostic_message(diagnostic: object) -> str:
    if isinstance(diagnostic, dict):
        return str(diagnostic.get("message") or diagnostic.get("code") or "")
    text = str(diagnostic or "").strip()
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
        except ValueError:
            return text
        if isinstance(parsed, dict):
            return str(parsed.get("message") or parsed.get("code") or text)
    return text


def _shorten(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _MAX_REASON else text[: _MAX_REASON - 1].rstrip() + "…"


def ranked_failure_reason(summary: dict[str, Any]) -> str:
    """"N of M candidates could not be evaluated: <most common cause>" from a run summary.

    Reads the run's own `unevaluated` record (search, host search, gene KO). Returns "" when
    the summary has none, so a caller can fall back to the CLI's reason.
    """
    rows = summary.get("unevaluated")
    if not isinstance(rows, list) or not rows:
        return ""
    causes = Counter(
        _diagnostic_message(row.get("diagnostic")) or str(row.get("status") or "unknown")
        for row in rows if isinstance(row, dict)
    )
    if not causes:
        return ""
    cause, count = causes.most_common(1)[0]
    total = summary.get("n_candidates_total")
    n_total = total if isinstance(total, int) and total >= len(rows) else len(rows)
    share = "" if count == len(rows) else f" ({count} of {len(rows)})"
    noun = "candidate" if n_total == 1 else "candidates"
    return (
        f"{len(rows)} of {n_total} {noun} could not be evaluated: {_shorten(cause)}{share}"
    )
