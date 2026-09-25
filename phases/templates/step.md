# Step N — concrete objective

Role: `implement` (or `plan` / `review`). Read exactly the files named in the phase JSON and the relevant definitions they reference. Write only declared `write_paths`; the runner writes `report_path` for plan/review.

## Objective and behavior

Describe the expected interface, observable behavior, scientific invariants and known boundaries. State non-goals so a fresh session can avoid unrelated changes.

## Acceptance

List each JSON check ID and its exact command from `scripts/harness_checks.py`, plus any justified task-specific argv/deadline/coverage rule. The runner executes these independently; a proposed `completed` response alone never passes.

## Evidence and stop conditions

Identify the report/evidence path and what it must cover. Stop with `blocked` for unavailable prerequisites or `error` for a failed implementation/check. A review gives `pass`, `changes_requested` or `blocked` with evidence-linked findings and coverage limits.
