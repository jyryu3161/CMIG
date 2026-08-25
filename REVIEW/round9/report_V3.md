# Round-9 Track V3 Report — `feat/render-pipeline`

## What changed and why

### Staged, atomic render publication

- Added `cmig/render/publication.py`, which defines the figure artifact set (figure,
  `.figure_spec.json`, and `.render_provenance.json`), creates a same-parent staging directory,
  verifies that all three staged artifacts exist, and publishes each through
  `cmig.io.atomic.atomic_write_path`.
- `RenderClient` now gives both `figure.R` and the matplotlib fallback a staged path with the same
  basename and format suffix as the requested output. The spec, figure, and provenance are all
  completed in staging before any destination artifact is replaced. This retains the renderer's
  previous byte production while preventing a failed renderer or provenance writer from
  truncating/replacing the last successful output.
- `FigureComposer` uses the same staged publication path for network, heatmap, and chord panels.
  Its shipped R scripts remain subprocess-only; no R package is imported or linked into Python.
- An unsuccessful render no longer publishes an orphan new figure-spec sidecar. If an older
  artifact set exists, a renderer/provenance failure leaves it unchanged; if no older set exists,
  no public artifact is created.

### Public completed-run panel service

- Added and exported `cmig.render.render_panels_from_run(run_dir, panels, out_dir, ...)`.
  `panels` accepts ordered strings (`network`, `heatmap`, `chord`) or `PanelSpec` objects.
  The entry point reads the completed directory through `TidyBundle.read`, applies either the
  shared requested journal preset or each spec's preset, and delegates to `FigureComposer`.
- Network and chord panels consume the validated community-basis `edges.parquet` weights.
  Null/non-finite weights fail explicitly instead of being silently discarded.
- The heatmap is a deterministic member-by-metabolite projection of direct member↔pool edges:
  secretion is positive and uptake is negative. Allocated cross-feeding rows are excluded because
  adding them would count the same shared-pool flux twice. Duplicate direct cells, if present, are
  summed and output in sorted order.
- Network and chord titles still pass through `panel_title_with_basis`; the real SVGs contain
  `EDGE_WEIGHT_BASIS_CAPTION`. Heatmap titles do not receive that edge-width caption.
- `PanelSpec.validate` now rejects unknown journal presets even on direct `FigureComposer` calls;
  the run service actually applies a recognized non-default preset to width, height, and DPI.

## Byte/hash identity for the existing single-profile R path

Basis: before editing, I produced a real completed run with
`cmig solve-fixture --solver gurobi` and rendered it through the forced R path. After the staged
implementation, I rendered the same run and the same default `FigureSpec` to a separate directory
under the same basename, `profile.svg`. Both runs used `/usr/local/bin/Rscript` 4.3.2 and the same
installed R library. `cmp` succeeded independently for the figure and both sidecars.

| Artifact | SHA-256 before | SHA-256 after | Direct comparison |
| --- | --- | --- | --- |
| `profile.svg` | `6a28b08ba3f832778294282b614a53433dd4e4dc781f70574e5dcf5cdea09e1b` | same | identical |
| `profile.svg.figure_spec.json` | `b06c6ebfe9e2aafeb2d23c57821bbdf59db24690ee916a37c6a509d52cec4b91` | same | identical |
| `profile.svg.render_provenance.json` | `0525efe6df4f8fd189d3de1c0af173da139de90443b43469db8c382808d041d8` | same | identical |

The source run's manifest records the unchanged frozen solve hash
`29844e29103603324d118cc9a8b9ae4fa2a79070418860cfc2ed70095cef29ab`.

## Real panel renders from the fixture tidy bundle

I invoked the new public API on that same `solve-fixture` run with the ordered panel list
`["network", "heatmap", "chord"]`, `figure_format="svg"`, and
`journal_preset="nature"`. The observed input projection contained 24 rows for each script.
Every output had a figure-spec and render-provenance sidecar; all specs recorded the applied
Nature geometry of 3.5 × 3.0 inches at 300 DPI.

| Panel/script | SVG bytes | SVG SHA-256 | R packages recorded by provenance |
| --- | ---: | --- | --- |
| `network.R` | 42,725 | `36f6ee0ca846729d66a03ce9275d6fb350edb6765c7479473bc695aa4f982919` | ggraph 2.2.1; graphlayouts 1.2.2; igraph 2.1.4; ggplot2 3.5.2; svglite 2.2.1; systemfonts 1.2.3 |
| `heatmap.R` | 22,666 | `d145d459517beb54e12d67c607047e3892704e81c5f69ebf3a9f327091a9fda4` | ComplexHeatmap 2.18.0; circlize 0.4.18; svglite 2.2.1; systemfonts 1.2.3 |
| `chord.R` | 115,958 | `61d372ccb495eb8a46077312f5f204c41bfef70917c052f6ea9c622802b003ee` | circlize 0.4.18; svglite 2.2.1; systemfonts 1.2.3 |

There were no R-environment package gaps. These panel hashes are observations from this stated
fixture/R environment, not new project goldens. `rg` found the exact community-weighted basis
caption in the real network and chord SVGs.

## Failure-injection coverage

`tests/test_round9_render_pipeline.py` covers these staged-publication boundaries:

- an R subprocess that writes partial staged output and then fails;
- a matplotlib `savefig` that writes partial staged output and then fails;
- a publication copy writer that writes a partial atomic temporary file and then fails;
- an injected final `os.replace` failure;
- successful publication of the exact staged bytes with final/logical sidecar filenames;
- composer routing of the figure and both sidecars through the atomic helper.

For each injected writer/replace failure, the affected previous public artifacts retain their
exact bytes and both the staging directory and atomic `.tmp` file are removed. The renderer
failures occur before publication and therefore preserve the complete prior three-file set.

Atomicity remains per file, not a transaction across all three files: if the process fails after
one completed replacement but before the next, a mixed set remains possible. That is the existing
project-wide multi-file limitation recorded as a round-8/9 deferred item; this track did not claim
to solve it.

## Verification log

Every project command used `UV_CACHE_DIR=/tmp/cmig-round9-V3-uv-cache uv run --no-sync`.

- Real source run: `cmig solve-fixture --solver gurobi --out <run>`
  - Exit 0; completed tidy bundle and manifest produced.
  - Run hash: `29844e29103603324d118cc9a8b9ae4fa2a79070418860cfc2ed70095cef29ab`.
- Pre/post regression: forced-R `cmig render-figure` on the source run, followed by three `cmp`
  calls and SHA-256 calculation.
  - Exit 0; figure and both sidecars identical as tabulated above.
- Public API real render: all three requested panel scripts on the real tidy bundle.
  - Exit 0; all nine artifacts (three figures plus six sidecars) produced; no package gap.
- Owned focused set:
  `pytest -o addopts='' -q tests/test_render.py tests/test_figure_composer.py tests/test_round9_render_pipeline.py`
  - Exit 0: 27 passed in 16.05 s.
- Adjacent atomic/provenance/export regressions, including the real profile R pipeline test:
  - Exit 0: 126 passed in 22.33 s.
  - One retained OSQP `PendingDeprecationWarning`; no test failure.
- `ruff check .`
  - Exit 0: `All checks passed!`
- `mypy cmig`
  - Exit 0: `Success: no issues found in 79 source files`.
- `cmig golden verify-envelope`
  - Exit 0: all 17 workflow kinds and the float-normalization probe `[OK]`; serialization
    unchanged.
- `cmig golden verify`
  - Exit 0: gurobi and osqp MICOM versions and published run hashes `[OK]`.

The real PyArrow reads emitted sandbox-only `sysctlbyname` cache-query warnings on macOS; the
reads and renders completed successfully. No Qt/WebEngine test was needed for this non-GUI track.

## Proposed CHANGELOG entries

- Added a public `render_panels_from_run` service that renders ordered network, signed direct-edge
  heatmap, and chord panels from a completed tidy run, applies journal presets, records R/script/
  input provenance, and preserves the community-basis caption on edge-width panels.
- Changed R profile, matplotlib fallback, and R Figure Composer publication to render complete
  figure/spec/provenance sets in staging and atomically replace each destination file; the existing
  profile R figure and sidecar bytes are unchanged.
- Changed failed renders to leave existing public figure artifacts untouched and to avoid
  publishing an orphan figure-spec sidecar before a figure succeeds.
- Changed direct `PanelSpec` rendering to reject unknown journal preset names rather than recording
  an unapplied/invalid preset.

## Exact proposed CLI surface for V1/coordinator

Add repeatable `--panel` to the existing command, preserving current behavior when it is absent:

```text
cmig render-figure \
  --run-dir runs/solve_fixture \
  --panel network \
  --panel heatmap \
  --panel chord \
  --out runs/solve_fixture/figures \
  --renderer r \
  --format svg \
  --journal-preset nature \
  --title "Community exchange" \
  --seed 42
```

Exact parser/behavior contract:

- `--panel` uses `action="append"`, `choices=("network", "heatmap", "chord")`, and preserves
  request order and duplicates. No `--panel` continues to render the single external profile and
  treats `--out` as a file, exactly as today.
- With one or more `--panel`, `--out` is the output directory. Files are
  `panel_00_<kind>.<format>`, `panel_01_<kind>.<format>`, etc., each with its two sidecars.
- Panel mode accepts only `svg`/`tiff`. `--renderer matplotlib` is an explicit exit-2 error;
  `auto` may locate R but must not silently substitute a matplotlib panel because no equivalent
  panel renderer exists. R/package failure remains an explicit exit-2 diagnostic.
- Build one `PanelSpec` per requested kind using the existing title/width/height/dpi/format/seed/
  journal arguments, then call `render_panels_from_run`. A non-default journal preset overrides
  width/height/DPI through the existing preset table, matching profile-mode policy.
- Update `--out` help to say "figure path; output directory when --panel is used" and update the
  command's import-error text to refer to the R panel dependency set when panel mode is selected.

No `cmig/cli/main.py` edit was made because it is V1-owned.

## Integration notes / risks

- Publication is atomic per artifact, not transactional across figure/spec/provenance, as described
  under failure coverage. A directory-level artifact-set transaction remains a separate design.
- Panel rendering is deliberately R-only. Missing ggraph/ComplexHeatmap/circlize/svglite packages
  raise `RenderError`; there is no scientifically different silent fallback.
- The new heatmap's signed direct-edge definition should be documented alongside the CLI surface:
  values are community-basis secretion (+) and uptake (−), and allocated pairwise cross-feeding is
  excluded to avoid double counting.
- `render_panels_from_run` reads through `TidyBundle.read`, so legacy tidy edges receive the existing
  semantic migration before plotting. Legacy bundles without enough abundance information fail
  closed when their migrated weights are null.
- The new package-level exports are lazy with respect to tidy/pyarrow loading: `TidyBundle` is
  imported only when the completed-run service is called.

## Proposals deliberately not implemented

- Did not edit `cmig/cli/main.py`; the exact coordinator handoff is above.
- Did not edit `pyproject.toml`, `uv.lock`, CHANGELOG, README, documentation, skills, manifests,
  workflow envelope fixtures, or solve goldens.
- Did not change any R script drawing behavior or install/update any R package.
- Did not add a matplotlib fallback for network/heatmap/chord, expand panel formats to PDF/EPS, or
  silently omit edges with missing/non-finite weights.
- Did not implement a multi-file transaction or claim power-loss atomicity for the three-file set.
- Did not freeze the observed panel hashes as goldens; they are environment-qualified verification
  evidence only.
