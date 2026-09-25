# CMIG phase planning

Create a concrete phase under `phases/<name>/` from `phases/templates/`. Follow `AGENTS.md` and `docs/HARNESS.md`. Give each step an explicit `plan`, `implement` or `review` role, exact read and owned paths, check IDs, deadline and report path for plan/review. Plans and reviews use `gpt-6-astra`; implementation uses `gpt-6-sol`. Use the user's existing authorization for routine implementation. Identify only genuinely unresolved choices. Validate with `uv run --no-sync python scripts/execute.py <name> --dry-run`; do not start a live phase unless requested.
