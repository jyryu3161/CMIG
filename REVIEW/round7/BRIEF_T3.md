# Round-7 Track T3 — `feat/io-hardening`

Read `REVIEW/round7/COMMON_BRIEF.md` first. You are the ONLY track allowed to
change `pyproject.toml`/`uv.lock`.

## Goal

1. **Atomic binary writes.** `cmig/io/atomic.py` covers text only;
   `REVIEW/FINAL_REPORT_ROUND5_2026-07-26.md` lists parquet/figure writers as
   deliberately deferred. Add an atomic binary/parquet write primitive
   (same-directory tempfile + fsync + `os.replace`, mirroring the existing text
   implementation) and adopt it in every parquet writer inside `cmig/io/`
   (`solve_output.py` and any other `cmig/io/` module that writes parquet).
   Figure writers and parquet writes issued from `cmig/cli/main.py` are OUT of
   your scope (main.py is T1-owned) — list those call sites in your report as
   integration notes instead.
2. **`pytest-randomly`.** Round-5's report records that `-p no:randomly` was
   inert because the plugin was never installed, and calls installing it "an
   open, cheap improvement". Add `pytest-randomly` to the dev dependency group,
   make the seed visible/reproducible, and get the full suite green under
   randomized order. If specific expensive fixtures cannot survive shuffling,
   fix the fixture (scope/caching), and only as a last resort mark the specific
   test file with a documented fixed-seed escape hatch. Record every test that
   needed intervention.
3. **mypy debt in your area:** fix `cmig/io/model_import.py` `list(object)`
   error. Pin mypy to an exact version in the dev group so local and CI runs
   agree (choose the version the current lock resolves to).

## Ownership

- `cmig/io/**`
- `pyproject.toml`, `uv.lock` (dev group + test config only — do not touch
  runtime dependency specs)
- tests: `tests/test_io*.py`, any `tests/test_*` edits strictly required for
  randomized-order stability (list each in your report), new
  `tests/test_round7_atomic*.py`

## Constraints

- Full-suite green under `uv run pytest -q` (randomized) — this is YOUR gate
  since you own test-order behavior this round.
- Atomic write behavior must preserve existing bytes-on-disk output exactly
  (same content, same path); only the write path changes.

## Verification to include in your report

- Two full-suite runs with different random seeds, both green, seeds recorded.
- A crash-safety argument (or test) for the parquet atomic path.
