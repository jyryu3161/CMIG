# CMIG Independent Re-Evaluation — Round 2 (TEST & REPORT ONLY)

A first evaluation round already happened and a set of fixes was implemented.
You are a **fresh independent evaluator**. Two other evaluators are working the
same brief in parallel. Work alone.

## Ground rules

- **READ-ONLY ON SOURCE.** Do NOT edit anything under `cmig/`, `tests/`,
  `pyproject.toml`. Three agents share this worktree. Write only to the scratch
  dirs named in your task.
- Environment is already installed. Use `uv run cmig ...`. If your sandbox
  denies `~/.cache/uv`, use `./.venv/bin/cmig` and `./.venv/bin/python` instead.
  Do NOT install anything or run `uv sync`.
- Verified env: cobra 0.31.1, micom 0.39.0, Gurobi academic (full size, exp.
  2027-05-27), R 4.3.2 + ggplot2, PySide6 (offscreen via `QT_QPA_PLATFORM=offscreen`).
- Models: `models/` (iHN637 785 rxns, iYO844 1250, iAF987 1285, iSFV_1184 2621,
  iML1515 2712). Prefer the small three to keep runtimes sane.
- **Do NOT read `REVIEW/report_opusA.md`, `REVIEW/report_codexB.md`, or any other
  agent's round-2 report.** Your assessment must be genuinely independent.

## Method

Follow the CMIG skill's discover → run → verify loop:
`uv run cmig workflows --format json` → `uv run cmig <cmd> --help` → run with an
explicit `--out` → `uv run cmig inspect-run --run-dir <dir> --format json`.

Act like a working scientist, not a linter. A claim counts only if you ran the
command and read the number out of a real artifact. **Never report a number you
did not observe.** Record exact command, exit code, wall-clock, key numbers.

## What to evaluate

Three scenarios, each verdict SUPPORTED / PARTIAL / NOT SUPPORTED with evidence:

- **S1** — find the microbial combination that best produces short-chain fatty
  acids. Note `search` now has `--target-preset scfa` and
  `--multi-metric {normalized_weighted,carbon_equivalent,raw_sum}`. Judge whether
  "which combo makes the most SCFA" is now answerable *and scientifically
  defensible* — including whether candidates get silently excluded, whether ties
  and all-zero rankings are flagged, and whether the score means anything.
- **S2** — microbe–microbe interaction: cross-feeding, per-strain growth alone
  vs in community, abundance sweeps, dFBA. Check whether alone-vs-community is a
  controlled comparison, and whether inferred (non-identifiable) edges are
  labelled as such.
- **S3** — host–microbe coupling AND microbial perturbation (inhibition/KO)
  predicting the effect on the host cell. Assess whether a user can go from
  "suppress microbe/gene X" to "host objective changes by Y" in a supported way.

Also verify these **recent fixes** actually hold, and hunt for regressions:
a solver failure must degrade gracefully rather than raise a raw traceback;
unevaluable candidates must not be ranked as zeros; top-level `status` must
reflect the worst sub-status; `strain-growth` must use the same medium for both
legs.

## Figure quality

Generate real figures and inspect the **produced files** (SVG XML, TIFF headers
via PIL, colors, fonts, legends, units, panel letters). Judge against Nature
Genetics / Claude Science standards: colorblind-safe palette (Okabe-Ito or
equivalent), vector output, 300–600 dpi raster with sane compression/mode,
typography, multi-panel with panel letters, axis labels **with units**,
informative legends, data-ink ratio. Give an honest publication-readiness call.

## Deliverable

One markdown report at the path in your task:
1. Verdict table S1/S2/S3 (verdict, ran end-to-end?, evidence, blocking gap)
2. Evidence log (command, exit code, runtime, key numbers, artifact path)
3. Figure assessment per criterion with observed values + readiness call
4. Bugs/defects with repro command and observed vs expected
5. Prioritized P0/P1/P2 proposals naming file + function
6. What you could not test and why

Be quantitative and specific. Distinguish "the tool cannot do this" from "I could
not work out how". Honest negative results are the most valuable output.
