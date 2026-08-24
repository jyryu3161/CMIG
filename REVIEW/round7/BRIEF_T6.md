# Round-7 Track T6 — `chore/figure-dedup-tests`

Read `REVIEW/round7/COMMON_BRIEF.md` first. Quality track: consolidate duplicated
figure plumbing and raise test coverage on under-tested modules. No behavior
changes visible to users.

## Goal

1. **Extract `cmig/render/figure_style.py`.** The matplotlib figure policy is
   defined twice: in `cmig/cli/main.py` (~lines 5580–5650: `FIGURE_TIFF_DPI`,
   `SVG_HASHSALT`, `_load_matplotlib_pyplot`, `save_publication_tiff`,
   `_polish_matplotlib_axes`) and in `cmig/core/interaction_figures.py`
   (`FIGURE_TIFF_DPI`, `SVG_HASHSALT`, `_load_matplotlib`,
   `_save_publication_tiff`, `_polish_axes`). Create ONE shared module under
   `cmig/render/` holding the constants and helpers, and make
   `cmig/core/interaction_figures.py` use it. You may NOT edit
   `cmig/cli/main.py` (T1-owned) — the coordinator adopts it there after merge.
   Design the shared API so main.py's call sites can switch with a pure
   import-swap (document the exact intended replacement mapping in your report).
   Constants must keep their exact current values — figures are
   provenance-hashed (`SVG_HASHSALT` changes output identity; do not touch the
   value or the hashing behavior).
2. **Dedicated tests for under-tested modules:**
   - `cmig/cli/publication.py` (295 LOC, ZERO direct test files): argument
     handling, error paths, and the `add_publication_parsers` registration —
     new `tests/test_cli_publication.py`. Test through the public CLI entry
     (`cmig model-quality`, `cmig publication-benchmark`) without editing the
     module unless a bug is found (bug fixes in `cli/publication.py` are within
     your ownership; document any).
   - `cmig/core/interaction_figures.py` (614 LOC, 1 test file): cover figure
     spec generation, deterministic output hashing, and the degraded path when
     matplotlib is absent — new `tests/test_interaction_figures_round7.py`.
   - `cmig/core/search_product.py` (now with the GA landing, no dedicated test
     file): create `tests/test_search_product.py` covering
     `count_candidate_combinations`, `sample_candidate_combinations`
     determinism/uniformity-at-small-N, `_unrank_combination` edge cases,
     `choose_strategy` thresholds, and `PoolSearchResult` accounting invariants
     (ranked + unevaluated == evaluated; `n_robustness_failed`). Pure-python
     tests only — no solver.
3. **Do NOT** refactor `search_product.py`/`search_ga.py` themselves — tests
   only (they just landed; the coordinator wants regression pinning, not churn).

## Ownership

- `cmig/render/**` (new `figure_style.py` + adopting changes in the render
  package if any)
- `cmig/core/interaction_figures.py`
- `cmig/cli/publication.py` (bug fixes only, justified in report)
- tests: `tests/test_figure_composer.py`, `tests/test_render.py`, new test
  files listed above

## Verification to include in your report

- Before/after proof that figure outputs are byte-identical (or hash-identical
  via the existing provenance sidecars) for a representative figure.
- Coverage delta for the three targeted modules (rough: test count per module).
- The exact main.py adoption mapping for the coordinator.
