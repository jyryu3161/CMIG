# Round-7 Track T3 Report — `feat/io-hardening`

Implementation commit: `d1c0a44` (`round7 feat/io-hardening atomic parquet publication`)

## What changed and why

### Atomic binary and Parquet publication

- Added `atomic_write_binary`, `atomic_write_bytes`, and `atomic_write_parquet` in
  `cmig/io/atomic.py`.
- The binary primitive creates its temporary file in the destination directory, invokes the
  writer on an open binary handle, flushes and `fsync`s the completed file, closes it, and then
  publishes it with `os.replace`. Any exception removes the temporary file and leaves an existing
  destination untouched.
- `cmig/io/solve_output.py` now validates the tidy bundle and routes
  `nodes.parquet`, `edges.parquet`, `profile.parquet`, and optional `matrix.parquet` through the
  atomic Parquet primitive. The existing staged-directory publication and final
  `manifest.json` commit marker remain intact.
- Run-level `os.replace` failure injection is kept separate from single-file staging failure
  injection. This preserves the existing manifest commit-marker test while allowing each atomic
  boundary to be exercised independently.
- `tests/test_round7_atomic_io.py` verifies successful binary publication; failure during the
  Parquet writer, `fsync`, and `os.replace`; cleanup of partial temporary files; preservation and
  readability of the previous Parquet file; byte-for-byte equality with direct PyArrow output;
  and solve-output routing for all four tidy tables.

The write path changes only publication mechanics. The regression test writes the same table once
with `pyarrow.parquet.write_table` and once through `atomic_write_parquet` and asserts exact byte
equality.

### Randomized test order and reproducible tooling

- Added `pytest-randomly>=3.15` to the dev dependency group; `uv.lock` resolves it to `4.1.0`.
- Full-suite validation used explicit command-line seeds, so each order is visible and exactly
  reproducible. Two different seeds completed successfully.
- No randomized-order test or fixture needed intervention. An initial run exposed a deterministic
  solve-output failure-injection regression introduced by the new staging layer; the implementation
  boundary was corrected and the existing test was not changed.

### mypy debt

- Pinned mypy to the lock's existing resolution, exactly `mypy==2.1.0`, so local and CI runs use
  the same checker.
- Typed `objective_structure_warning`'s optional reaction collection as
  `Iterable[object] | None` and converted the absent case from `[]` to `()`. This removes the
  `list(object)` error without changing runtime behavior.

## Crash-safety argument

For a destination `artifact.parquet`, the helper creates `.artifact.parquet.<random>.tmp` in the
same directory. Until the final replacement, readers continue to see the previous destination.
The new bytes are fully written, flushed, synced, and the handle is closed before `os.replace`.
Therefore a writer exception or process death before replacement leaves the old complete file;
after replacement, readers see the new complete file. `os.replace` cannot expose the partially
written temporary file as the destination.

The tests inject failures after partial bytes, at `fsync`, and at `os.replace`; in every case the
old Parquet bytes remain exact, PyArrow can still read the old table, and no temporary file remains.

Scope caveat: this mirrors the existing text primitive and `fsync`s the file, not the parent
directory. Atomic reader visibility and process-crash safety are covered; durability of the rename
itself across sudden power loss remains filesystem/platform dependent without a directory `fsync`.

## Verification log

All commands ran from the T3 worktree. A temporary writable uv cache was used for sandboxed setup;
the final GUI-containing full suites ran in the Orca host terminal because the command sandbox
denies Chromium's macOS Mach-port registration.

- `UV_CACHE_DIR=/private/tmp/cmig-round7-t3-uv-cache uv sync --all-extras --group dev`
  - Exit 0; 83 packages resolved, 75 packages audited.
- `uv run python -c 'from importlib.metadata import version; ...'`
  - `mypy 2.1.0`; `pytest-randomly 4.1.0`.
- `uv run pytest -q tests/test_round7_atomic_io.py --randomly-seed=314159`
  - Exit 0; 6 passed.
- `uv run pytest -q tests/test_model_import.py --randomly-seed=271828`
  - Exit 0; 13 passed (affected-code smoke test).
- `uv run pytest -q tests/test_foundations_review_regressions.py::test_write_solve_output_manifest_is_publish_commit_marker --randomly-seed=20260824`
  - Exit 0; 1 passed.
- `uv run mypy cmig/io`
  - Exit 0; no issues in 7 source files.
- `uv run ruff check .`
  - Exit 0; all checks passed.
- `uv run pytest -q --randomly-seed=20260824`
  - Exit 0; reached 100% with no failures. The collection contained 1,228 items. Existing skips
    and the existing UMAP, infeasible-solver, and OSQP pending-deprecation warnings remained.
- `uv run pytest -q --randomly-seed=42424242`
  - Exit 0; reached 100% with no failures over the same collection. Existing skips/warnings
    remained.
- `uv run cmig golden verify-envelope`
  - Exit 0; all 13 workflow kinds and the float-normalization probe reported `[OK]`; envelope
    serialization unchanged.
- `git diff --check`
  - Exit 0.

## Integration notes and risks

### Out-of-scope Parquet call sites in `cmig/cli/main.py`

These remain non-atomic because `main.py` is T1-owned:

- Lines 4036 and 5801: `write_timecourse(..., "timecourse.parquet")`.
- Lines 7178 and 7392: `write_sweep_parquet(..., "sweep.parquet")`.
- Lines 7393 and 7513: `_write_sweep_profiles(..., "sweep_profiles.parquet")`, whose helper calls
  `pq.write_table` directly.

The invoked core writers also remain outside T3 ownership: `cmig/core/dfba.py:470` and
`cmig/core/sweep.py:222`. Other direct core Parquet writers include
`cmig/core/tidy.py:176-180`, `cmig/core/matrix.py:41`, and golden-fixture capture. Only the
`cmig/io/solve_output.py` path was in scope for adoption.

### Out-of-scope figure call sites in `cmig/cli/main.py`

Figure publication remains non-atomic at `render_profile` (lines 1696, 1702, 1707, 1711, 1714),
gene-KO figures (3418), strain-growth figures (3567), abundance-impact figures (3710), host-search
figures (3830), interaction figures (3952), multi-target search figures (4992), the four search
figure calls (5657-5660), and dFBA figures (5838).

### Documentation handoff

- `README.md` still says atomic writes cover text but not Parquet. Updating that scope statement is
  outside T3 ownership.
- The common brief requests a CHANGELOG entry for intentional behavior changes, but `CHANGELOG.md`
  is outside the T3 ownership list. The coordinator should add an Unreleased entry for atomic
  Parquet publication and randomized test order.

## Proposals deliberately not implemented

- No changes to `cmig/cli/main.py`, core Parquet writers, figure writers, README, or CHANGELOG,
  because those files are outside T3 ownership.
- No schema, manifest, golden, or `run_hash` serialization changes. Atomic publication preserves
  artifact bytes.
- No fixed-seed escape hatch and no test fixture/order modification: both required randomized
  orders passed after correcting the implementation boundary.
- No parent-directory `fsync` was added because the brief called for parity with the existing text
  primitive and cross-platform directory syncing needs a separate portability decision.
- No dependencies were added or upgraded outside the dev group.
