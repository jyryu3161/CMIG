# Windows golden CLI console remediation — 2026-09-25

Status: **PASS** — bounded implementation accepted; new remote CI verification
remains with Root.

## Evidence and scope

The supplied log `.run/remediation-20260925/integration-final-r2/windows-ci-failure.log`
records Windows job `107977995642` in run `36105827828` failing after authorized push
`e32d7d9`. The recorded `integration-final-r2/remote-ci-result.json` confirms
Windows release alignment, Ruff and mypy passed first.
The log independently shows all 18 envelope kinds and the float normalization probe
reported OK, followed by `UnicodeEncodeError` when `cmig/cli/main.py:1511` prints
U+2192 to strict cp1252. This is a newly reached console-reporting failure after
earlier gates, not evidence of envelope drift or of any previous remote CI pass.
The job exits 1 despite a successful scientific/serialization check.

That remote run concluded **failure**. Ubuntu Python 3.10/3.12 and macOS Python
3.12 quality jobs passed. Windows deterministic tests were skipped after the
envelope command failed; the dependent distribution and full solver/GUI/publication
jobs were also skipped. None of those skips establishes validation of its scope.

Reviewed inputs: `AGENTS.md`; the failure log; both golden handlers and their
argparse bindings in `cmig/cli/main.py`; `cmig/core/workflow_envelope_golden.py`
report construction and `_report_lines`; `cmig/golden_fixture.py` version/hash
verification; `tests/test_workflow_envelope_golden.py` including its existing
in-process CLI smoke; `tests/test_solver_and_cli.py`; golden-related test discovery;
`.github/workflows/ci.yml`; and `docs/HARNESS.md`.

The existing CLI smoke captures text in process and cannot establish Windows
console encoding compatibility. Both golden handlers contain fixed non-ASCII
output: U+2192 is outside cp1252, and the version gate also emits Korean text.
cp1252 can encode the existing ellipsis, em dash and plus/minus symbols, but ASCII
spellings in these two handlers keep the correction simple and portable.
Core report helpers remain untouched; their existing fixed punctuation is cp1252
representable. This bounded fix does not establish universal ASCII-console support
for arbitrary diagnostic data or other CLI commands.

## Sol implementation contract

Production writes: only `cmig/cli/main.py`, within `_cmd_golden_verify` and
`_cmd_golden_verify_envelope`. Tests: existing golden CLI test files, preferably
`tests/test_workflow_envelope_golden.py`, which the Windows quality job executes.

Replace fixed reporting literals with clear ASCII English, covering success,
mismatch/drift, missing-engine guidance, truncated-hash suffixes, the float-probe
label and uncovered-kind warning. Preserve report construction, imports/laziness,
`ok` and `hash_ok` decisions, stdout/stderr routing, 16-character hash display,
return codes 0/2, and the nonfailure meaning of uncovered kinds. Do not change
hashes, normalization, golden data, tolerances, solver behavior, dependencies,
workflow settings or global stream/environment encoding policy. No broad CLI
redesign or helper framework is needed.

Subprocess regressions must exercise actual CLI dispatch with strict cp1252
stdout **and** stderr: Python normally gives stderr `backslashreplace`, so the
test child must explicitly require strict errors on both streams. Exercise real
clean envelope success (0), controlled envelope drift with actionable diagnostics
(2), uncovered-kind warning (0), stubbed solver-version/hash success (0) and
mismatch (2), plus missing-engine guidance (2) if practical. Assert return codes,
expected diagnostics and no encoding traceback. Stub only scientific providers
when needed to avoid solver execution; do not replace the reporting code.

Acceptance commands, all without syncing the environment:

```text
uv run --no-sync ruff check .
uv run --no-sync mypy cmig
uv run --no-sync python scripts/check_release_versions.py
uv run --no-sync cmig golden verify-envelope
uv run --no-sync pytest -q tests/test_workflow_envelope_golden.py
```

Run any other touched golden CLI module only if needed. Do not rerun the full
suite or unrelated solver/GUI/publication checks. Prior full acceptance is the
coordinator-supplied `1752 passed, 18 existing GEM skips`; it is historical evidence,
not a newly run result or proof of Windows success.

The contract was sent through Orca orchestration for immediate Sol dispatch, with
a 4–5 minute implementation target and an approximately 10-minute combined bound.
This Astra worker owns this report and ignored
`.run/remediation-20260925/windows-ci-review/` only. Root owns commit, push and
verification of the next remote run.

## Final review

Independent pre-fix reproduction:

```text
uv run --no-sync python .run/remediation-20260925/windows-ci-review/strict_console.py baseline
```

With both child streams explicitly `cp1252:strict`, real `golden verify-envelope`
exited 1 after reporting 18 checked kinds and the float probe OK, then raising
`UnicodeEncodeError` for U+2192. Full bytes decoded for inspection are recorded in
`.run/remediation-20260925/windows-ci-review/baseline-strict-console.json`.
This script changes child streams only; no environment, production stream policy
or repository inputs are changed.

Sol completion was received through the coordinator after the implementation
worker settled. The reviewed production diff is confined to the two golden
handlers in `cmig/cli/main.py`: ASCII English summaries and instructions, ASCII
punctuation, and a local three-replacement rendering step for punctuation from
`_report_lines`. This last step changes presentation only; the core helper, report
data, hashes, solver integration and scientific checks remain untouched. The
return branches and stdout/stderr routing are unchanged. No global reconfiguration,
environment bypass, dependency/workflow edits or golden recapture was introduced.

The 137 added test lines in `tests/test_workflow_envelope_golden.py` use real
subprocess streams, actual CLI dispatch and the unchanged core report renderer.
Only provider reports are injected for controlled failures. Both child streams
explicitly use `cp1252` with strict errors, so stderr escaping cannot hide an
unencodable message. Six cases verify real envelope success, drift including
removed-kind and float-probe diagnostics, uncovered-kind nonfailure, solver
version/hash success and mismatch, and missing-engine guidance. They check the
expected 0/2 statuses, actionable output, ASCII output and absence of tracebacks.
The current CI selection already includes this test module.

Independent checks against the settled diff:

| Check | Result | Reviewer evidence |
| --- | --- | --- |
| Real `golden verify-envelope`, both streams strict cp1252 | Exit 0, 18 kinds and float probe OK, empty stderr | `windows-ci-review/final-strict-console.json` |
| Real `golden verify`, both streams strict cp1252 | Exit 0, MICOM 0.39.0 and both published solver hashes match, empty stderr | Same JSON |
| `uv run --no-sync pytest -q tests/test_workflow_envelope_golden.py -k cp1252` | Six cases passed, no skips | `windows-ci-review/cp1252-review.log` |
| `git diff --check` and final diff inspection | Pass; production/tests confined to the two assigned files | `windows-ci-review/reviewed.diff` |

Evidence paths in this table are relative to `.run/remediation-20260925/`.
The real-command checks use the reviewer-owned `strict_console.py final` script.
No solver is re-solved by version/hash verification.

Reviewed Sol acceptance evidence in
`.run/remediation-20260925/windows-ci-correction/verification.md` and its logs:
Ruff passed; mypy passed for all 91 source files; release surfaces agree at 0.3.0;
the envelope command passed for all 18 kinds; and the focused envelope/solver-CLI
modules passed **52 tests**. An intermediate `str.maketrans` typing error was
corrected with local chained replacements before final acceptance. The final
source and successful mypy log were inspected; that intermediate failure is not
being counted as a pass.

No blocking findings remain for this output-only correction. Review writes were
limited to this report and its ignored evidence directory; no production/tests,
Git state or persistent environment settings were changed by the reviewer.
Neither the prior 1752-test result nor these local checks establishes a successful
new Windows job. Root must commit/push the accepted patch and verify the fresh
remote run, including downstream jobs that the failed run skipped.
