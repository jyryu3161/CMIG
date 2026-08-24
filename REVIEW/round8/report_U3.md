# Round-8 Track U3 Report — `chore/atomic-adoption`

## What changed and why

### Atomic figure publication

- Added `atomic_write_path` to `cmig/io/atomic.py` for libraries that require a filesystem path
  rather than an already-open binary handle. It creates the temporary file in the destination
  directory, calls the writer with that `.tmp` path, reopens and `fsync`s the completed file, then
  publishes it with `os.replace`. Writer, file-sync, and replace failures remove the temporary file
  and leave any previous destination unchanged.
- Added `save_figure_atomic` to `cmig/render/figure_style.py`. It always passes matplotlib's
  `format` explicitly because the temporary path deliberately ends in `.tmp`, not `.svg`/`.tiff`.
- Made `save_publication_tiff` atomic across the complete matplotlib + Pillow workflow. The first
  render and any RGB flatten/recompression happen on the temporary path; only the final
  submission-ready RGB/LZW TIFF is published.
- Routed `cmig/core/interaction_figures.py` SVG and TIFF renders through the atomic helpers. The
  failure-banner SVG and TIFF rewrites are atomic too, so this module has no remaining direct
  SVG/TIFF overwrite.

The publication mechanism changed; figure content did not. Failure-injection tests cover writer,
file-`fsync`, and `os.replace` errors for SVG and TIFF, asserting exact preservation of the old
artifact and zero temporary-file litter.

### Remaining owned Parquet writers

- `cmig/core/sweep.py:220` now publishes `sweep.parquet` with `atomic_write_parquet`.
- `cmig/golden_fixture.py:103-105` now publishes each solver's `nodes.parquet`, `edges.parquet`, and
  `profile.parquet` with `atomic_write_parquet`.
- Tests inject writer, file-`fsync`, and replace failures into the sweep writer and into each of the
  three golden capture artifacts. Every case preserves the previous readable Parquet bytes and
  cleans its temporary file.
- No fixture or expected-golden file was changed or re-blessed. The existing direct-vs-atomic
  PyArrow byte-identity regression remains green.

### Directory-fsync decision

Implemented automatic **best-effort parent-directory sync** after every successful replacement in
`atomic_write_binary`, `atomic_write_text`, and `atomic_write_path`.

- On Linux and macOS/POSIX, syncing the completed file before rename makes file data durable, while
  opening and syncing the parent directory after rename asks the filesystem to persist the new
  directory entry. Rename atomicity alone does not guarantee that metadata survives sudden power
  loss.
- On Windows, Python's `os.open`/`os.fsync` interface does not provide a portable directory-handle
  flush equivalent, so the helper skips it. POSIX/network filesystems may also reject opening or
  syncing directories.
- Directory open/sync/close `OSError`s are therefore intentionally suppressed. A platform that
  cannot sync directories retains the previous successful-replace behavior. File `fsync` remains
  mandatory and failures still abort before replacement.
- macOS `fsync` is the portable stdlib operation; this does not claim the stronger hardware-cache
  guarantee of platform-specific `F_FULLFSYNC`. Linux durability also remains subject to the
  mounted filesystem's guarantees. The implementation improves rename durability without making
  unsupported platforms fail after the destination has already been replaced.

## Figure byte-identity proof

Basis: before editing and after the final implementation, I rendered the same round-7 T6 synthetic
interaction fixture under Python 3.12.11 / matplotlib 3.10.9 / Agg with the shared fixed SVG salt
and metadata. Member secretion was `alpha={ac: 2, but: 1}`, `beta={ac: 1}`; host uptake and
microbe-to-host transfer were both `ac=2.5`. Each after file was compared directly with its saved
before bytes, not merely with a separately rendered after file.

| Artifact | SHA-256 before and after | Direct comparison |
| --- | --- | --- |
| `interaction_circle.svg` | `1b21080e4894439371ce60f8309d47cc7e7ea4d4295b1cd022963f4420cad479` | identical |
| `interaction_circle.tiff` | `b65f7d19f7543dafbd15f010318aa958658e02f374c536a99b6db29f6f6812ee` | identical |
| `interaction_heatmap.svg` | `c05b8caa35211b516b87ed89033fcef228ce876847c0b3523d00a56f2d7417a2` | identical |
| `interaction_heatmap.tiff` | `02bac4b3576f65455d058e2529da77ca3a5797e2601946bb2bf281f50e0a5f6d` | identical |
| `interaction_bubble.svg` | `d6cf293cfba23c4f72e09ff22a42b5f9439ad76c4470855f30227cc7f7d0d53d` | identical |
| `interaction_bubble.tiff` | `e45d6d4326568c0dfe3c1074f033c405c7359965e3dd97edb08ea8feb3e31004` | identical |
| `member_contribution.svg` | `68fff6f061eb2678507f0cd63e9b7e6263d7ebdcc9329da21228132e7646ceec` | identical |
| `member_contribution.tiff` | `0ae4bfa400adbf06df6b9c4da08c323117c8f6cc0648ded76193c1def16045c3` | identical |

These are also exactly the hashes recorded by round-7 T6.

## Verification log

All project commands used `uv run --no-sync`. `UV_CACHE_DIR=/private/tmp/cmig-u3-uv-cache` avoided
the sandbox-inaccessible user uv cache; matplotlib commands also used
`MPLCONFIGDIR=/private/tmp/cmig-u3-mplconfig`.

- `uv run --no-sync ruff check .`
  - Exit 0: `All checks passed!`
- `uv run --no-sync mypy cmig`
  - Exit 0: `Success: no issues found in 77 source files`
- `uv run --no-sync pytest -o addopts='' -q tests/test_round8_atomic_adoption.py tests/test_round7_atomic_io.py tests/test_interaction_figures_round7.py tests/test_figure_publication_export.py tests/test_sweep.py`
  - Exit 0: 69 passed in 10.09s.
- Selected pre-existing atomic/golden/commit-marker contracts from
  `tests/test_round5_p3_io_exception.py`, `tests/test_foundations_review_regressions.py`,
  `tests/test_workflow_envelope_golden.py`, and `tests/test_validation.py`
  - Exit 0; all 37 selected cases passed.
- `uv run --no-sync cmig golden verify-envelope`
  - Exit 0: all 13 workflow kinds and the float-normalization probe `[OK]`; serialization
    unchanged.
- `uv run --no-sync cmig golden verify`
  - Exit 0: gurobi and osqp MICOM versions and published run hashes `[OK]`.
- Representative before/after render script described above
  - Exit 0: all eight direct byte comparisons reported `IDENTICAL`; hashes are listed above.
- Non-GUI broad suite (the full test tree excluding the 12 files that import PySide6/Qt)
  - Exit 0: 1,144 collected tests reached 100%; existing skips and OSQP, infeasible-solver, UMAP,
    and joblib physical-core warnings remained.
- Unrestricted `uv run --no-sync pytest -q`
  - Reached 11% with no Python test failure, then a native process exited 133. This matches the
    round-7 documented macOS sandbox limitation for Qt/Chromium/Mach-port initialization. All U3
    tests and adjacent contracts were rerun outside that group and passed as above.
- `git diff --check`
  - Exit 0.

## Proposed CHANGELOG entries

- Changed figure publication to use same-directory temporary files, mandatory file sync, and
  atomic replacement for shared matplotlib TIFF output and interaction SVG/TIFF artifacts,
  including failure-banner rewrites; artifact bytes remain unchanged.
- Changed sweep and golden-fixture Parquet publication to preserve an existing artifact on writer,
  sync, or replacement failure.
- Added best-effort parent-directory sync after atomic replacement on supported POSIX filesystems,
  with unchanged successful behavior where directory sync is unsupported.

## Integration notes / risks

### Exact `cmig/cli/main.py` figure adoption mapping for U1/coordinator

Add `save_figure_atomic` to the existing import from `cmig.render.figure_style` at lines 28-31,
then make these exact substitutions:

```python
# line 5900, in _save_screening_figure
save_figure_atomic(fig, out_svg, format="svg", metadata=SVG_METADATA)

# line 6346, in the spatial figure writer
save_figure_atomic(
    fig,
    out_svg,
    format="svg",
    bbox_inches="tight",
    metadata=SVG_METADATA,
)
```

No TIFF call-site edit is needed: `save_publication_tiff` at lines 5901, 6347, 6574, and 6613 now
publishes atomically through the shared helper. Likewise, the `render_interaction_figures` call at
line 4131 inherits U3's atomic SVG/TIFF paths without a main.py edit.

The `render_profile` calls at lines 1865, 1871, 1876, 1880, and 1883 are not direct matplotlib
writers. Their actual fallback overwrite remains `cmig/render/client.py:169`, and the R subprocess
also receives the final output path at `client.py:119`. Wrapping these calls in
`atomic_write_path` only in main.py would misplace the `.figure_spec.json` and provenance sidecars,
so that path needs a coordinated `RenderClient` change rather than a caller-only substitution.

### Out-of-scope Parquet adoption mapping

- U2/U1: `cmig/core/tidy.py:176-180` — replace the three mandatory and one optional
  `pq.write_table(table, destination)` calls with `atomic_write_parquet(destination, table)`.
- U1: `cmig/core/matrix.py:41` — replace `pq.write_table(table, p)` with
  `atomic_write_parquet(p, table)` and keep returning `p`.
- U6: `cmig/core/dfba.py:470` — replace `pq.write_table(table, p)` with
  `atomic_write_parquet(p, table)` and keep returning `p`. Its main.py callers are lines 4215 and
  5921.
- U1/coordinator: `cmig/cli/main.py:7652` (`_write_sweep_profiles`) — replace the direct
  `pq.write_table` with `atomic_write_parquet(path, pa.Table.from_pylist(rows, schema=schema))`.
- `cmig/cli/main.py:7317` and `:7531` already call U3's `write_sweep_parquet` and therefore inherit
  atomic publication without caller edits.

### Risks

- Atomicity is per file, not a transaction across an SVG/TIFF pair or the three golden Parquet
  files. Readers never see a partial individual file, but a process failure between completed
  replacements can leave a mixed multi-file set, as before.
- Best-effort directory sync cannot promise durability on filesystems/platforms that reject it;
  those failures are deliberately non-fatal because the replacement has already occurred.

## Proposals deliberately not implemented

- Did not edit `cmig/cli/main.py`, `cmig/render/client.py`, `cmig/core/tidy.py`,
  `cmig/core/matrix.py`, `cmig/core/dfba.py`, or `cmig/io/dfba_output.py`; the exact handoffs are
  above.
- Did not edit or re-bless any golden, solve fixture, workflow envelope, schema, manifest, or
  `run_hash` implementation.
- Did not edit frozen dependencies, `README.md`, or `CHANGELOG.md`.
- Did not make directory-sync failure fatal, use macOS-only `F_FULLFSYNC`, or add a Windows-native
  directory-handle API. Those would either fail after an already-completed replacement or add
  platform-specific complexity beyond the portable best-effort durability decision.
- Did not introduce a multi-artifact transaction for figure pairs or golden bundles; the requested
  scope was atomic publication of each remaining writer output.
