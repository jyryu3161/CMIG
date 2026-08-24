# Round-7 T4 report — `docs/release-freshness`

## What changed and why

### Operational documentation

- Replaced `docs/cmig_workflow_tutorial.html` with a current live-contract guide. It covers all 35
  top-level commands, the 15 GUI-to-CLI workflow records, and the previously missing
  `host-ko-impact`, `dfba-sensitivity`, `host-search-bigg`, `host-generic`, `host-benchmark`,
  `publication-benchmark`, `namespace-suggest`, and `search-advanced-fixture` workflows. The search
  section now documents single-target GA selection and all eight `--ga-*` controls.
- Rebuilt `docs/PUBLICATION_VALIDATION.md` around the post-round-6 boundary-isolation contract. The
  obsolete host expectation near 368.01 is explicitly invalidated; the controlled result is an
  honest 0.0 null. Every claim is labelled `VERIFIED AGAINST CODE`,
  `VERIFIED AGAINST REVIEW/SCENARIO_RESULTS_ROUND6.md`, or `TO RE-RUN AT RELEASE`, and every
  solver-dependent release result has an exact command.
- Reordered `RELEASE_CHECKLIST.md` to mirror CI dependency order and added the missing
  `cmig golden verify-envelope` quality gate.

### Skill-document hygiene

- Replaced the three unpinned Python line citations with `_cmd_search` and `_cmd_strain_growth`
  symbol references.
- Expanded the `--allow-unknown-medium` roster to all nine commands that expose it and added the
  flag to the gene-KO and three host command references.
- Corrected the stale statement that `--allow-failed-run` was universal; the accepted and rejected
  command rosters now match live help.
- Did not add documentation for T1's in-progress CLI flag.

### 0.2.0 release preparation

- Added `docs/release-drafts/0.2.0-changelog-draft.md`, a release-facing organization of the current
  `[Unreleased]` material plus an explicit reconciliation note for GA and concurrent round-7 work.
- Added `docs/release-drafts/0.2.0-version-alignment.md`, covering the five requested metadata files,
  `uv.lock`, the run-hash consequence of changing `CMIG_CORE_VERSION`, release order, and a
  standard-library CI version-alignment guard proposal.
- Added `docs/release-drafts/human-gem-fixture-decision.md`. It recommends deleting the unregistered
  local Human-GEM fixture during release cleanup and using the checksum-verified Recon3D path. It
  also defines the provenance/resolver work required if versioned Human-GEM support is added later.
  No asset was deleted.

## Verification log

### Environment setup

| Command | Result |
|---|---|
| `uv run pytest --version` | Blocked before pytest: the global uv cache contains an inaccessible `.git` path. |
| `uv sync --all-extras --group dev` | Same sandbox cache error. A retry with `UV_CACHE_DIR=/tmp/cmig-round7-t4-uv-cache` did not complete in the network-restricted environment. |
| `UV_CACHE_DIR=/tmp/cmig-round7-t4-uv-cache uv run --no-sync pytest --version` | Passed: pytest 9.0.2. |
| `UV_CACHE_DIR=/tmp/cmig-round7-t4-uv-cache uv run --no-sync ruff --version` | Passed: ruff 0.15.0. |

Because the sync could not install the project console script, live CLI checks below used the
equivalent entry point `uv run --no-sync python -m cmig.cli.main ...`. The command parser and code
path are the same as the `cmig` console script.

### Live CLI outputs used for the documentation

| Document(s) | Commands inspected | Result used |
|---|---|---|
| Workflow tutorial | `cmig --help`; `cmig workflows --format json` | 35 top-level commands; 15 workflow-map records. |
| Search tutorial/changelog draft | `cmig search --help`; `cmig search-advanced-fixture --help` | `ga` strategy, auto threshold behavior, and all eight `--ga-*` controls; fixture accepts `auto`, `exhaustive`, and `ga`. |
| Medium roster and skill docs | `cmig solve --help`; `search --help`; `strain-growth --help`; `abundance-impact --help`; `gene-ko-search --help`; `sweep --help`; `host-microbe-bigg --help`; `host-search-bigg --help`; `host-ko-impact --help` | `--allow-unknown-medium` is present on exactly the nine documented commands. |
| Host tutorial/publication guide | `cmig host-generic --help`; `host-benchmark --help`; `host-map --help`; `host-microbe-bigg --help`; `host-search-bigg --help`; `host-ko-impact --help` | Required biomass provenance, explicit host objective availability on host commands, map-review controls, and host medium options. |
| dFBA tutorial/publication guide | `cmig dfba --help`; `cmig dfba-sensitivity --help` | Both expose `--close-untracked-uptake`; sensitivity exposes `--dts`, `--kms`, `--initial`, and interpretability-oriented exit behavior. |
| Publication guide/checklist | `cmig publication-benchmark --help`; `cmig inspect-run --help`; `cmig golden --help`; `cmig workflows --format json` | The integrated benchmark exposes neither `--close-untracked-uptake` nor `--host-objective`; the checklist contains both golden gates. |
| Model/QC tutorial | `cmig model-review --help`; `cmig model-quality --help`; `cmig namespace-suggest --help` | Current input alternatives and output requirements. |

The tutorial-specific static coverage check found every required formerly missing command and all
of `--ga-pop-size`, `--ga-generations`, `--ga-mutation-rate`,
`--ga-immigrant-fraction`, `--ga-tournament-k`, `--ga-elitism`,
`--ga-max-evaluations`, and `--ga-patience`.

### Publication-validation claim audit

| Claim group | Basis recorded in the document |
|---|---|
| Boundary and host isolation markers; CLI flag availability; benchmark/output contracts | `VERIFIED AGAINST CODE` using current help and `BOUNDARY_ISOLATION_POLICY`, `HOST_ISOLATION_POLICY`, `NON_HASHED_PROVENANCE_MARKERS`, and publication-manifest code. |
| Three-member VMH growth, host `0.0` null, unmatched `EX_n2_m`, and five-member pool failure | `VERIFIED AGAINST REVIEW/SCENARIO_RESULTS_ROUND6.md`. |
| Interface-map counts, model/community/search/host outputs, timings, dFBA grid, release versions/checksums, and all new numeric results | `TO RE-RUN AT RELEASE` with exact commands. |

No solver-derived number was recomputed in this worktree: `cmig solvers` reported Gurobi, HiGHS,
and OSQP unavailable. The old publication numbers were removed rather than silently carried
forward.

### Gates

| Command | Result |
|---|---|
| `UV_CACHE_DIR=/tmp/cmig-round7-t4-uv-cache uv run --no-sync ruff check .` | Passed: `All checks passed!`. |
| `PYTHONPATH=. UV_CACHE_DIR=/tmp/cmig-round7-t4-uv-cache uv run --no-sync pytest -q tests/test_cli_workflows.py tests/test_cli_search_ga_config.py tests/test_publication_benchmark_manifest.py tests/test_workflow_envelope_golden.py` | Passed (exit 0). These are adjacent contract tests; T4 owns no test files. |
| `UV_CACHE_DIR=/tmp/cmig-round7-t4-uv-cache uv run --no-sync python -m cmig.cli.main golden verify-envelope` | Passed: 13/13 workflow kinds plus the float-normalization probe; serialization unchanged. |
| `UV_CACHE_DIR=/tmp/cmig-round7-t4-uv-cache uv run --no-sync python -m cmig.cli.main golden verify` | Blocked as expected: engine stack unavailable; exit 2. No licensed solver gate was claimed. |
| `git diff --check` | Passed. |
| Citation scan over `.claude/skills/**` and `medium_presets/PROVENANCE_gut_media.md` | Passed: no `file.py:NNNN` citations remain. |
| HTML structural count check | Passed: opening/closing counts match for document, section, table, list, code, and heading elements. |

## Integration notes and risks

- The release coordinator must run the `TO RE-RUN AT RELEASE` commands in
  `docs/PUBLICATION_VALIDATION.md` with the final 0.2.0 commit, a licensed solver, the verified
  external host, a reviewed interface map, complete dFBA initial medium, and real biomass bases.
- `publication-benchmark` still lacks both `--close-untracked-uptake` and `--host-objective`. The
  document therefore requires separate dFBA and explicit-host-objective controls and forbids reading
  Recon3D's shipped maintenance objective as growth.
- The 0.2.0 version bump changes `CMIG_CORE_VERSION`, a run-hash input. Version alignment must be
  coordinated with T1's schema/golden ownership and the documented re-blessing process.
- `CHANGELOG.md` has repeated `Added`/`Fixed` headings inside `[Unreleased]`; the draft consolidates
  them but deliberately does not edit the shared source block. Reconcile after all tracks merge.
- The Human-GEM fixture was absent in this worktree. The decision memo relies on the track brief's
  reported 43 MB local asset and records deletion as a coordinator action, not a completed deletion.
- Git metadata for this linked worktree is outside the writable sandbox. The requested
  `git checkout -B docs/release-freshness` failed with `index.lock: Operation not permitted`; the
  existing branch is `jyryu3161/round7-T4-docs-release`. Orca's runtime was unavailable
  (`stale_bootstrap`) and could not proxy Git writes. This also blocks staging and committing from
  the current environment; the working-tree deliverables are complete but uncommitted unless that
  external Git permission becomes available.

## Proposals deliberately not implemented

- No edit to `CHANGELOG.md`, `README.md`, `pyproject.toml`, `uv.lock`, `cmig/__init__.py`,
  `CITATION.cff`, `.zenodo.json`, `.claude-plugin/marketplace.json`, any Python file, or any test.
- No 0.2.0 version bump, version-check script, CI workflow change, run-hash re-bless, or release tag.
- No Human-GEM deletion, provenance registration, resolver/download-script change, or model-byte
  redistribution.
- No solver/publication rerun and no reuse of pre-round-6 numeric outputs.
- No documentation of T1's in-progress CLI surface; the coordinator must reconcile that work after
  merge.
