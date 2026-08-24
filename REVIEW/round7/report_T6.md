# Round-7 T6 report — `chore/figure-dedup-tests`

## What changed and why

- Added `cmig/render/figure_style.py` as the single matplotlib publication-policy module. It owns:
  - `FONT_STACK = ("Arial", "Helvetica", "DejaVu Sans")`
  - `FIGURE_TIFF_DPI = 600`
  - `SVG_HASHSALT = "cmig-svg-v1"`
  - `SVG_METADATA = {"Date": None}`
  - `load_matplotlib_pyplot`, `save_publication_tiff`, and `polish_matplotlib_axes`
- Replaced the duplicate constants/helpers in `cmig/core/interaction_figures.py` with aliases to
  the shared policy. The existing interaction contribution grid opacity remains explicitly `0.8`;
  the shared default is `0.85`, matching `cmig/cli/main.py`. This preserves both existing render
  paths exactly while allowing main.py to adopt the shared implementation without call-site edits.
- Added `tests/test_cli_publication.py` for public-entry parser registration, mutually exclusive
  source arguments, argument forwarding, missing-input errors, and missing dependency errors for
  `cmig model-quality` and `cmig publication-benchmark`.
- Added `tests/test_interaction_figures_round7.py` for shared-policy adoption, deterministic/sorted
  figure rows and manifest artifacts, byte-identical SVG/TIFF rendering, and the matplotlib-absent
  path (tables and figure specification remain available; rendering reports the missing optional
  dependency).
- Added `tests/test_search_product.py` with solver-free coverage of exact combination counts,
  seeded and small-N-uniform sampling, unranking boundaries, strategy thresholds, and
  `PoolSearchResult` ranked/unevaluated and robustness accounting.
- No bug was found in `cmig/cli/publication.py`, so it was not changed. No user-visible behavior
  changed, so no CHANGELOG entry was needed.

## Figure byte-identity proof

Basis: the same synthetic interaction fixture was rendered before and after extraction with Python
3.12.11, matplotlib 3.10.9, Agg, the fixed SVG salt, and the same writable matplotlib cache. The
fixture had member secretion `alpha={ac: 2, but: 1}`, `beta={ac: 1}`, host uptake `ac=2.5`, and
microbe-to-host transfer `ac=2.5`. `diff -rq` over both complete output directories returned no
output. The SHA-256 values below were identical before and after:

| Artifact | SHA-256 before and after |
| --- | --- |
| `interaction_circle.svg` | `1b21080e4894439371ce60f8309d47cc7e7ea4d4295b1cd022963f4420cad479` |
| `interaction_circle.tiff` | `b65f7d19f7543dafbd15f010318aa958658e02f374c536a99b6db29f6f6812ee` |
| `interaction_heatmap.svg` | `c05b8caa35211b516b87ed89033fcef228ce876847c0b3523d00a56f2d7417a2` |
| `interaction_heatmap.tiff` | `02bac4b3576f65455d058e2529da77ca3a5797e2601946bb2bf281f50e0a5f6d` |
| `interaction_bubble.svg` | `d6cf293cfba23c4f72e09ff22a42b5f9439ad76c4470855f30227cc7f7d0d53d` |
| `interaction_bubble.tiff` | `e45d6d4326568c0dfe3c1074f033c405c7359965e3dd97edb08ea8feb3e31004` |
| `member_contribution.svg` | `68fff6f061eb2678507f0cd63e9b7e6263d7ebdcc9329da21228132e7646ceec` |
| `member_contribution.tiff` | `0ae4bfa400adbf06df6b9c4da08c323117c8f6cc0648ded76193c1def16045c3` |

## Coverage delta

The requested rough measure is collected direct test cases per targeted module:

| Target | Before | Round-7 direct cases | Basis |
| --- | ---: | ---: | --- |
| `cmig/cli/publication.py` | 0 dedicated files | 10 | `pytest --collect-only -q tests/test_cli_publication.py` |
| `cmig/core/interaction_figures.py` | 1 existing direct file | 5 new | `pytest --collect-only -q tests/test_interaction_figures_round7.py` |
| `cmig/core/search_product.py` | 0 dedicated files | 11 | `pytest --collect-only -q tests/test_search_product.py` |

This adds 26 collected direct regression cases. The owned five-file run collected and passed 44
tests including the pre-existing `test_figure_composer.py` and `test_render.py` cases.

## Verification log

- `UV_CACHE_DIR=/tmp/cmig-t6-uv-cache uv run --no-sync ruff check .`
  - Result: `All checks passed!`
- `UV_PROJECT_ENVIRONMENT=/Users/jaeyongryu/Projects/CMIG/.venv UV_CACHE_DIR=/tmp/cmig-t6-uv-cache MPLCONFIGDIR=/tmp/cmig-t6-mplconfig uv run --no-sync python -m pytest -q tests/test_cli_publication.py tests/test_interaction_figures_round7.py tests/test_search_product.py tests/test_figure_composer.py tests/test_render.py`
  - Result: 44 passed.
- `UV_PROJECT_ENVIRONMENT=/Users/jaeyongryu/Projects/CMIG/.venv UV_CACHE_DIR=/tmp/cmig-t6-uv-cache MPLCONFIGDIR=/tmp/cmig-t6-mplconfig uv run --no-sync python -m pytest -q tests/test_figure_publication_export.py tests/test_search_product_ga_scaling.py tests/test_round5_domain_accuracy.py -k 'matplotlib_svg_writers or screening_svg_bytes or interaction_figures_share or test_combination_count_uses or test_auto_strategy_boundary or test_random_sampler or test_large_random_search or test_robustness'`
  - Result: 10 passed.
- `UV_PROJECT_ENVIRONMENT=/Users/jaeyongryu/Projects/CMIG/.venv UV_CACHE_DIR=/tmp/cmig-t6-uv-cache PYTHONPATH=/Users/jaeyongryu/orca/workspaces/CMIG/round7-T6-figure-dedup-tests uv run --no-sync cmig golden verify-envelope`
  - Result: 13/13 workflow kinds OK; float-normalization probe OK; serialization unchanged.
- `diff -rq /tmp/cmig-t6-before.znbAtu /tmp/cmig-t6-after.mB2n8c`
  - Result: no output; all representative CSV/JSON/SVG/TIFF bytes identical.
- `git diff --check`
  - Result: clean.

Environment note: the initial `uv run pytest --version` attempted to read the sandbox-inaccessible
user cache. A retry with a task-local cache found the worktree venv had no pytest/matplotlib; the
required `uv sync --all-extras --group dev` then stalled without output under restricted network and
was interrupted after two minutes. Verification therefore selected the already-synced project venv
through `UV_PROJECT_ENVIRONMENT`, while the working directory/PYTHONPATH ensured all imports came
from this T6 worktree. No dependency or lockfile was changed.

## Main.py adoption mapping for the coordinator

`cmig/cli/main.py` is T1-owned and was not edited. Delete its duplicate `FONT_STACK`,
`FIGURE_TIFF_DPI`, `SVG_HASHSALT`, `SVG_METADATA`, `_load_matplotlib_pyplot`,
`_polish_matplotlib_axes`, and `save_publication_tiff` definitions, then use this pure import swap:

```python
from cmig.render.figure_style import (
    FIGURE_TIFF_DPI,
    FONT_STACK,
    SVG_HASHSALT,
    SVG_METADATA,
    load_matplotlib_pyplot as _load_matplotlib_pyplot,
    polish_matplotlib_axes as _polish_matplotlib_axes,
    save_publication_tiff,
)
```

No main.py call site needs to change. Its current grid alpha is `0.85`, which is the shared helper's
default.

## Integration notes and risks

- The shared constants retain their exact values and SVG metadata behavior; all eight representative
  hashes prove that adopting the module in `interaction_figures.py` did not move figure identity.
- The worktree-local environment is not self-contained because the all-extras sync could not finish
  without network/cache access. The tests were still executed against this worktree's source using
  the already-synced project interpreter; the coordinator should be able to rerun the plain brief
  commands in a normally provisioned worktree.
- Startup branch creation and later Git metadata writes are blocked by the managed sandbox: the
  worktree Git directory resolves to `/Users/jaeyongryu/Projects/CMIG/.git/worktrees/round7-T6-figure-dedup-tests`,
  where creating `index.lock` returns `Operation not permitted`. Orca CLI and Computer Use recovery
  both returned `runtime_unavailable` because the Orca app runtime is not running. Source changes
  and this report are complete, but the requested branch/commit operations require the coordinator
  or a session with write access to the parent repository metadata.

## Deliberately not implemented

- Did not edit `cmig/cli/main.py`; the exact T1/coordinator import mapping is above.
- Did not refactor `cmig/core/search_product.py` or `cmig/core/search_ga.py`; this track pins their
  current behavior with tests only.
- Did not add a new catch-and-continue policy for missing matplotlib. That would be a user-visible
  behavior decision; the regression test instead pins the current lazy optional-dependency failure
  while proving the non-render interaction specification remains available.
- Did not add or upgrade dependencies, edit `pyproject.toml`/`uv.lock`, or touch serialization and
  `run_hash` code outside T6 ownership.
