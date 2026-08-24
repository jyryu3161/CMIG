# Round-8 Track U3 — `chore/atomic-adoption`

Read `REVIEW/round8/COMMON_BRIEF.md` first. You finish what round-7 T3 scoped
out: atomic publication for the remaining writers T3 listed in
`REVIEW/round7/report_T3.md` §Integration notes — within YOUR ownership only.

## Goal

1. **Atomic figure publication.** Add an atomic save path to
   `cmig/render/figure_style.py` (temp file in the destination directory →
   fsync → `os.replace`, mirroring `cmig/io/atomic.py`; mind that matplotlib
   needs the format passed explicitly when the temp name has no proper suffix)
   and adopt it in `cmig/core/interaction_figures.py`'s SVG/TIFF writers.
   Figure bytes must remain identical — prove it the way round-7 T6 did
   (hash a representative set before/after). The `cmig/cli/main.py` figure call
   sites are U1-owned: provide the exact adoption mapping in your report for
   the coordinator, as T6 did.
2. **Atomic Parquet in your remaining core sites**: `cmig/core/sweep.py`
   (T3 listed line ~222) and the golden-fixture capture writer
   (`cmig/golden_fixture.py`). `cmig/core/tidy.py` and `cmig/core/matrix.py`
   parquet writes are owned by U2/U1 this round — list their exact call sites
   as integration notes instead of editing them. `cmig/core/dfba.py` belongs to
   U6 — same treatment.
3. **Directory-fsync decision.** T3 deferred fsyncing the parent directory as a
   portability decision. Make the decision: evaluate macOS/Linux/Windows
   semantics, then either implement an opt-in/`best-effort` directory sync in
   `cmig/io/atomic.py` used by all atomic paths, or write a short decision
   record in your report explaining why not. If you implement it, every
   existing atomic test must stay green and the behavior must be identical when
   the platform cannot sync directories.
4. **Tests**: extend `tests/test_round7_atomic_io.py` conventions into
   `tests/test_round8_atomic_adoption.py` — failure injection for the figure
   path (writer exception, fsync failure, replace failure → old artifact intact,
   no temp litter) and for the sweep/golden-fixture parquet paths.

## Ownership

- `cmig/io/atomic.py`
- `cmig/render/figure_style.py`, `cmig/core/interaction_figures.py`
- `cmig/core/sweep.py` (write-path mechanics only — no behavior change),
  `cmig/golden_fixture.py` (same)
- tests: `tests/test_round8_atomic_adoption.py`, plus existing atomic/figure
  test files if an assertion must learn the new path
- Do NOT touch: `cmig/cli/main.py` (U1), `cmig/core/tidy.py`/`matrix.py`
  (U2/U1), `cmig/core/dfba.py`/`io/dfba_output.py` (U6), goldens.

## Verification to include in your report

- Byte-identity hashes for figures before/after atomic adoption.
- `cmig golden verify-envelope` unchanged; if you touched
  `cmig/golden_fixture.py`, show `golden verify` still green (bytes must be
  unchanged — only publication mechanics may change).
- The directory-fsync decision with its platform reasoning.
- The exact main.py adoption mapping for the coordinator.
