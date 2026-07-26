# CMIG Functional Test Brief (Phase 1 — TEST & REPORT ONLY)

You are an independent evaluator. Another agent is testing the same thing in
parallel; your report will be cross-reviewed against theirs. Work alone, do not
coordinate, do not read the other agent's report.

## Ground rules

- **PHASE 1 IS READ-ONLY ON SOURCE CODE.** Do NOT edit anything under `cmig/`,
  `tests/`, `pyproject.toml`, or any tracked source file. A second agent works in
  this same worktree; concurrent edits would corrupt both our runs.
- You MAY create files only under your assigned scratch dirs (given in your task).
- Environment is **already installed**. Use `uv run cmig ...`. Do NOT run
  `uv sync`, do NOT install packages, do NOT modify the venv.
- **If your sandbox denies `~/.cache/uv`** (`uv run` fails with "Operation not
  permitted"), skip `uv` entirely and call the in-workspace venv directly:
  `./.venv/bin/cmig <command>` and `./.venv/bin/python`. Both are equivalent.
- Verified working: cobra 0.31.1, micom 0.39.0, **Gurobi academic license (full
  size, expires 2027-05-27)**, PySide6 GUI imports under `QT_QPA_PLATFORM=offscreen`.
- Models in `models/`: iML1515 (2712 rxns), iSFV_1184 (2621), iAF987 (1285),
  iYO844 (1250), iHN637 (785). Fixtures in `fixtures/`. Media in `medium_presets/`.

## Read this first

`.claude/skills/cmig-metabolic-analysis/SKILL.md` — it defines the mandatory
**discover → run → verify** loop:

```bash
uv run cmig workflows --format json      # authoritative command map
uv run cmig <command> --help             # authoritative flags
uv run cmig inspect-run --run-dir <dir> --format json   # verify EVERY run
```

Treat those as ground truth over memory. Prefer small/fast models
(iHN637, iYO844) to keep runtimes sane; escalate to iML1515 only where needed.

## Test as a real scientist, not as a linter

Act like a domain researcher who just installed this tool and wants an answer.
Run the actual commands end to end. A test only counts as PASS if you ran it and
inspected real numeric output. Record exact commands, exit codes, wall-clock
time, and the key numbers. **Never report a number you did not observe.**

Judge each scenario on: (a) does the workflow exist, (b) does it run to
completion, (c) is the result *scientifically interpretable and defensible*, and
(d) would a reviewer accept it.

## The three target scenarios

### S1 — Optimal microbial combination for SCFA production
"Which combination of strains produces the most short-chain fatty acids?"
Relevant surface: `search`/`search-fixture`/`search-advanced`, `cmig/core/targets.py`
(SCFA set = ac, ppa, but, lac__L, lac__D, succ), `search_product.py`, `search_ga.py`.
Probe: can a user rank combinations by **total SCFA**, or only by a single
metabolite at a time? Is combinatorial search tractable? Are ties/degeneracy handled?

### S2 — Microbe–microbe interaction simulation
Relevant: `interactions.py`, `pair.py`, `matrix.py`, `strain-growth`,
`abundance-impact`, `sweep`, `dfba`, `spatial`. Probe: can a user quantify
cross-feeding / competition / mutualism between members, get per-strain growth
alone vs in community, and see who feeds whom?

### S3 — Host–microbe interaction + microbial perturbation → host effect
Relevant: `host-map`, `host-search-bigg`, `host_coupling.py`, `host_impact.py`,
`gene-ko-search` (`--ko-level gene|reaction`), `delta.py`. Probe: can a user
inhibit/knock out a specific microbe (or its genes) and predict the **effect on
the human/host cell**? Is there a clean "suppress microbe X → host objective
changes by Y" path? Note that a real host GEM (e.g. Recon/Human1) is NOT in
`models/` — assess what that means for usability, and use the synthetic host
fixture where needed.

For each scenario report: **SUPPORTED / PARTIAL / NOT SUPPORTED**, with the exact
commands you ran as evidence, and the specific blocking gap if not full.

## Figure quality assessment

Generate real figures (e.g. `uv run cmig render-figure --run-dir <dir> --out
<your scratch>/fig.svg`, try `--format pdf/tiff`, `--journal-preset`, and the
`interaction_figures.py` surface). Then judge them against **Nature Genetics /
Claude Science** publication standards:

- colorblind-safe palette (Okabe-Ito or equivalent) — check actual hex values
- vector output (PDF/EPS/SVG) and ≥300–600 dpi raster (TIFF)
- typography: legible sans-serif, consistent sizes, no clipped labels
- multi-panel composition with proper panel letters (A/B/C)
- axis labels **with units**, informative legend, no chartjunk
- data-ink ratio, no default-matplotlib look

Reference the local `dataviz` skill for the design bar. Open/inspect the actual
produced file (read the SVG/XML, check dimensions, colors, fonts) — do not judge
from the code alone. State plainly whether output is publication-ready or not,
and what exactly is missing.

## Deliverable

Write ONE markdown report to the path given in your task. Structure:

1. **Verdict table** — S1/S2/S3 × {supported?, ran?, evidence, blocking gap}
2. **Evidence log** — command, exit code, runtime, key numbers, artifact path
3. **Figure assessment** — per-criterion pass/fail with observed values, and an
   honest publication-readiness call
4. **Bugs / defects found** — concrete, with repro command and observed vs expected
5. **Prioritized improvement proposals** — P0/P1/P2, each with the specific file
   and function to change and why. Do NOT implement them in phase 1.
6. **What you could not test and why**

Be specific and quantitative. Distinguish clearly between "the tool cannot do
this" and "I could not figure out how". Report failures honestly — a negative
result found early is the most valuable thing you can produce here.
