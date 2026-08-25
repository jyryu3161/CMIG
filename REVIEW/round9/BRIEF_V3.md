# Round-9 Track V3 — `feat/render-pipeline`

Read `REVIEW/round9/COMMON_BRIEF.md` first. You own the R render pipeline.
`Rscript` is installed on this machine (`/usr/local/bin/Rscript`) — verify with
real renders, and honestly skip/record anything the R environment refuses.

## Goal

1. **Atomic publication for the R path.** Round-8 U3 determined
   (`REVIEW/round8/report_U3.md`) that wrapping `render_profile` at call sites
   would misplace the `.figure_spec.json`/provenance sidecars, and that the fix
   belongs at the `RenderClient` level (`cmig/render/client.py` — the fallback
   overwrite near line 169 and the subprocess receiving the final output path
   near line 119). Restructure so the R subprocess and the matplotlib fallback
   both write to a staged location and the client publishes figure + sidecars
   with the `cmig/io/atomic.py` primitives, preserving today's bytes and
   sidecar contents exactly (prove with hashes as T6/U3 did).
2. **Wire the orphaned composer panels.** `cmig/render/composer.py`
   (`FigureComposer`, `network`/`heatmap`/`chord` panels) and
   `cmig/render_r/{network,heatmap,chord}.R` have been shipped-but-unreachable
   since round 1 — consumers are tests only. Expose them through a public
   library/service entry point that takes a completed run directory (tidy
   bundle) and a panel list, applies journal presets, and writes the panel
   figure + provenance sidecar through the atomic path. Respect the
   community-basis caption contract (`EDGE_WEIGHT_BASIS_CAPTION`). Do NOT add
   CLI flags (`cmig/cli/main.py` is V1-owned) — write the exact proposed
   `render-figure --panel ...` surface in your report for the coordinator.
3. **Real-render verification.** With Rscript present, render at least: the
   existing single-profile `figure.R` path (regression), and each of the three
   panel scripts on a real run's tidy bundle (produce one from
   `cmig solve-fixture` — running analysis commands is fine; you just may not
   edit their code). If the local R library set is missing packages, record
   exactly which and verify what remains; do not install anything.

## Ownership

- `cmig/render/**`, `cmig/render_r/**`
- tests: `tests/test_render.py`, `tests/test_figure_composer.py`,
  new `tests/test_round9_render_pipeline.py`

## Verification to include in your report

- Byte/hash identity for the existing single-profile path after the atomic
  change (figure AND sidecars).
- The real panel renders: what ran, what was produced, any R-environment gaps.
- Failure-injection coverage for the staged publish (writer/replace failures
  leave prior artifacts intact, no temp litter).
