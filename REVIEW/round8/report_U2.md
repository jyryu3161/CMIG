# Round 8 U2 report — community-basis `edges.weight`

Date: 2026-08-24  
Track: U2 / `fix/edges-weight`

## Outcome

`edges.parquet.weight` is now an unsigned community-basis contribution magnitude:

`abs(per-taxon member exchange flux) × member relative abundance`

Direct secretion/uptake rows and allocated cross-feeding rows use that same basis. Direct
`weight_lo`/`weight_hi` values are direction-specific, non-negative magnitude intervals derived
from the signed per-taxon FVA interval and multiplied by the same member abundance. Allocated
cross-feeding rows remain `weight_lo = weight_hi = null`, because the reaction interval does not
identify a pairwise transfer interval.

The tidy schema is bumped from `1.2` to `1.3`. Code constants document the boundary explicitly:

- tidy `<=1.2`: `per_taxon_unweighted`
- tidy `>=1.3`: `community_abundance_weighted`, `mmol gDW_community^-1 h^-1`

The full legacy-bundle reader performs a real semantic migration rather than merely restamping
old values: direct rows are abundance-scaled from `nodes.parquet`, and cross-feeding is recomputed
from the scaled supply/demand marginals. A context-free legacy edge-table upgrade cannot know the
scale, so it emits `LegacyEdgeBasisWarning` and sets `weight`, `weight_lo`, and `weight_hi` to null.

## What changed and why

### `cmig/core/interactions.py`

- Validates that every solved member has a finite, non-negative relative abundance before any
  tidy bundle is emitted.
- Scales direct weights by the member endpoint's abundance.
- Applies the per-taxon noise floor before abundance scaling, so a genuine rare-taxon signal is
  not dropped merely because its community contribution is numerically below the engine floor.
- Allocates cross-feeding from already-weighted community supply/demand. This preserves community
  marginals; multiplying an old pairwise allocation by just the donor or recipient abundance
  would not.
- Converts signed per-taxon FVA bounds into row-direction magnitude bounds, then scales them by
  abundance. Sign-crossing intervals correctly have a zero lower magnitude bound.

### `cmig/core/tidy.py`

- Bumps `TIDY_SCHEMA_VERSION` from `1.2` to `1.3` for the semantic basis change.
- Adds named current/legacy basis constants and `MissingAbundanceError`.
- Adds honest semantic migration for tidy `<=1.2`; no legacy per-taxon number is silently
  relabelled as a 1.3 community number.

### Tests

- Added `tests/test_round8_edges_weight.py` covering direct weighting, ranking inversion,
  many-to-many community-mass conservation, FVA scaling for secretion/uptake and sign-crossing
  intervals, the missing/invalid abundance contract, zero abundance, and the 1.3 marker.
- Extended `tests/test_tidy.py` with basis-marker tests, full 1.2 bundle semantic migration, and
  context-free legacy edge NA/warning behavior.

## `abundance is None` decision record

Round 5 recorded two incompatible proposals:

1. replace a missing abundance with factor `1.0` and continue;
2. raise rather than publish a community-basis value without its required scaling input.

I chose proposal 2, fail closed.

`SolveResult.abundances[member] is None` means MICOM's member summary did not report the scaling
input. It does **not** mean the member biologically occupies 100% of the community. For a new
solve, `build_tidy` raises `MissingAbundanceError` (a `TidyContractError`/`ValueError`) before a
bundle is published. Therefore there is no `edges.weight` cell—numeric or NA—and no warning-only
continuation for that invalid new artifact. The CLI's existing `ValueError` boundary prints the
message and exits non-zero. Zero abundance is distinct and valid: its contribution is numeric
`0.0`.

The losing factor-1 contract would put an unchanged per-taxon flux into a column declared to be
community-basis. It silently asserts a missing member is the whole community, recreates the
ranking inversion, and mixes bases row-by-row whenever other members do have abundances. A warning
cannot repair the scientific meaning of the number once it is present and rankable.

Legacy reading has a separate compatibility case: `TidyBundle.read` has node abundances and
migrates numerically; direct use of `read_legacy_or_upgrade(edges, "edges")` lacks that context,
so it returns NA edge quantities and emits `LegacyEdgeBasisWarning` rather than inventing a scale.

## Worked real-solve inversion

Real Gurobi solve, MICOM 0.39.0, `iHN637 + iML1515`, abundances `0.1/0.9`, cooperative tradeoff
fraction `0.5`, acetate secretion:

| member | abundance | old per-taxon edge | new community edge |
|---|---:|---:|---:|
| iHN637 | 0.1 | 3.8761015383488457 | 0.3876101538348846 |
| iML1515 | 0.9 | 0.4594374461248192 | 0.4134937015123373 |

Before: `3.8761015 > 0.4594374`, so the low-abundance iHN637 edge ranked first by about 8.44×.
After: `0.4134937 > 0.3876102`, so iML1515 correctly ranks first by community contribution.
The two new direct edges sum to the real `profile.net_flux` for acetate:
`0.3876101538348846 + 0.4134937015123373 = 0.8011038553472219` (profile value
`0.8011038553472218`, floating-point roundoff only).

## Dual-solver golden capture

Documented capture command:

```text
uv run --no-sync python -m cmig.golden_fixture
```

Because the worktree-local uv invocation attempted to read a sandbox-restricted global cache, all
project commands used the common brief's fallback venv, with a writable uv cache and imports pinned
to this worktree:

```text
UV_CACHE_DIR=/private/tmp/cmig-u2-uv-cache \
UV_PROJECT_ENVIRONMENT=/Users/jaeyongryu/Projects/CMIG/.venv \
PYTHONPATH=. uv run --no-sync ...
```

Capture completed for both Gurobi and OSQP. No `result_digest` field is published by this solve
golden format; its published answer digests are `config.json.tidy_hashes`. All moved as expected
because `schema_version` is a hashed column; the edge digests also include the value-basis change.

### Published normalized tidy digests

| solver/table | before | after |
|---|---|---|
| gurobi/nodes | `e2bfbd7d0700e7dccd329a4e95ddf27841caa4a8c7578bbf8e340cbdbbfed21f` | `84be46a82ce9504ad9990894d583855db8da40ea7fa1ec605993775c35453dd0` |
| gurobi/edges | `c83d82b66ef042267eb2a423a11be4bf3687d9560fa652fe7150b8e7a9e44f8f` | `c2f32999478b9e481a5277ec33224cc0d51fb562dbe612e6bed408f9007226b5` |
| gurobi/profile | `d1abfc4e0d7633daee7b6477603cc9ec0995c76be45e17dfb236d5f00f7f127b` | `3862d140dba3630d3b35aa1019049ea5273148e95a4507d4a3ba39b1f8fa3a2a` |
| osqp/nodes | `5b6f3b8f5f445a1c2374c03c8bb2629973da6ae7f25895f3f781e979fa0eb446` | `116eb303bbe4aae85d41452a8f4e6647c3086a0ff0ddf7b9285317f6cd0313c3` |
| osqp/edges | `591fa48274c9b5299a4f74a053f1221e5bc6f3cf70027f6cb42505031328c79f` | `f2af08d14321dd4e2848c2d49a6afe951b6b19320ab0905147076efc68338730` |
| osqp/profile | `f0b19e6cc035570e800928e3ebf9c909701574f7e7bc52016c7b50e28d5ece8f` | `dd37fca84f10d85687d66dcb7f4f40ade764a941ef5f15282edcf64a03c9d1c9` |

### Every changed golden file, byte SHA-256 before/after

| file | before | after |
|---|---|---|
| `expected/gurobi/config.json` | `e8c1e4c26bcfbff6bde45a31e35fc802cea78737ccf50fb00d04762e32a2ae88` | `3f89665f02a2b02b5e013e1af6b3e8059b7bc4e4a4639c2c4a01d19c40f75fa6` |
| `expected/gurobi/nodes.parquet` | `ce6b1d604757860565932f8d95cb5d951d5c5aa14ae5df76a36a0ed1ed985ece` | `b242e875a809f523ba1d4b2392ac83f8f5bf1c08078ff924bb150d858bf588ea` |
| `expected/gurobi/edges.parquet` | `41be7b46f5c928e69d1b1ca01c24a7c59bd1cff9877ca3e592ee084a4e3c73eb` | `d523b126441197b085ee65a8ed4e8fc6bcb50541a4ef0581fab16036ac2d39b3` |
| `expected/gurobi/profile.parquet` | `799997a11bd722b5bfa2aad7f5b55a56e17c31fcd822c4593efd93cdfd6840e9` | `c42a4a717f111bd5c3bac47cb5185f80bf5625b116734baa6f59facea30dd949` |
| `expected/osqp/config.json` | `aedf9e2fb638c830e7c9eeb86fbf30279a3e17f21ea07e95ff1ff058f3a12c76` | `040e21b11f28d278ac657c5e652020396a3ca24ace2de05d09c5fba50c54cdc9` |
| `expected/osqp/nodes.parquet` | `c774f1adef471c9f086bf0d56d0900ee201686cba313c81c378d8e0cf91ca213` | `a996898f3c6dc15acb30b3af3123c3880463e20b1cd0fa674ce0e3f0b74ea690` |
| `expected/osqp/edges.parquet` | `2c8041d2c940682d0f323af210062047813bc8a433c42c6a75d8c5c78c2d8b23` | `304fb606a62652a713f9ebddd0a95f1744f6756306801eb01af52e5d1c640bca` |
| `expected/osqp/profile.parquet` | `d3e1caf1245e3167c552dcacca237441aeea38df7b9ff96b54e94f6f68ecdb3b` | `6e0787cc7c7a85ffce933f5af7dc01417aa5efe7cf3ecc1aead15f609337b2a1` |

`growth_expected.tsv` and `sign_expected.tsv` were exercised by the capture but remained
byte-identical, so they are not working-tree changes.

### Frozen 11-component solve hashes

The capture changed no input component and neither published hash moved:

- Gurobi before/after:
  `29844e29103603324d118cc9a8b9ae4fa2a79070418860cfc2ed70095cef29ab`
- OSQP before/after:
  `a422eb89d019f917f7fc334db8e9a2eff7d89ce49031ccbf215df7bd404d3d9d`

## Verification log

All commands below used the fallback environment prefix shown above.

```text
uv run --no-sync ruff check .
All checks passed!

uv run --no-sync mypy cmig
Success: no issues found in 77 source files

uv run --no-sync pytest -q \
  tests/test_tidy.py tests/test_round8_edges_weight.py tests/test_engine_golden.py
32 passed; 2 OSQP PendingDeprecationWarnings; exit 0

uv run --no-sync cmig golden verify
MICOM-version + run_hash golden regression (SC-5):
  [OK ] gurobi  golden=0.39.0 installed=0.39.0
      [OK ] run_hash 29844e2910360332…
  [OK ] osqp    golden=0.39.0 installed=0.39.0
      [OK ] run_hash a422eb89d019f917…
all golden versions and published run_hashes match; exit 0

uv run --no-sync cmig golden verify-envelope
13/13 workflow kinds OK + float normalization probe; serialization unchanged; exit 0

git diff --check
clean; exit 0
```

Additional checks:

- The real two-member inversion solve above was executed before and after the change.
- `TidyBundle.read(fixtures/pair_acetate_butyrate/expected)` semantically migrated all 5 legacy
  edge weights and returned in-memory schema `1.3` with 5/5 non-null weights.
- Focused golden regression re-solved both variants; Gurobi was normalized-hash exact and OSQP
  passed its documented tolerance.

## Integration notes / risks — coordinator action required

1. **GUI double-counting (prominent):** round-7 `cmig/gui/views.py::member_contribution_rows`
   multiplies `edge.weight × nodes.abundance`. With tidy 1.3, that multiplies abundance twice.
   U5/coordinator must remove that multiplication for 1.3 and retain version-aware handling for
   raw legacy data if the GUI bypasses `TidyBundle.read`. I did not edit `cmig/gui/**` per ownership.
2. **Manifest currently becomes false:** `cmig/io/solve_output.py` still writes
   `weight_basis: per_taxon_unweighted` and the old taxon unit/note. New 1.3 artifacts are
   community-basis. The coordinator must update this before merge, ideally importing the basis/unit
   constants from `cmig.core.tidy` to prevent another drift. `cmig/cli/main.py` will then report the
   updated manifest field without a U2 edit.
3. **Figure captions/docs are stale:** `cmig/render/composer.py` says edge width is per-taxon;
   README's “Reading edges.parquet” and scope limitation, plus
   `.claude/skills/cmig-metabolic-analysis/references/{outputs,scientific-validity}.md`, describe the
   old basis. These are outside U2 ownership. Update them to say tidy `<=1.2` was per-taxon and
   `>=1.3` is community-basis; explicitly warn consumers not to multiply 1.3 weights again.
4. **Non-owned pair golden:** `fixtures/pair_acetate_butyrate/expected/**` remains stamped 1.2 because
   U2 ownership grants capture changes only under `fixtures/community_3_member/expected/**`.
   Runtime reading is honest via semantic migration, but
   `test_committed_goldens_carry_the_current_schema_version` expects every on-disk golden to be
   current. Coordinator should re-capture/migrate that fixture through its documented procedure or
   change the assertion to recognize an intentionally retained legacy fixture.
5. **Non-owned stale tests:** an audit run of `tests/test_validation.py`,
   `tests/test_phase4_batch2_regressions.py`, and `tests/test_schema_migration.py` has exactly 7
   failures, all pinning the superseded contract: three raw per-taxon weight expectations, one raw
   FVA expectation, two literal `1.2` expectations, and the pair-golden stamp above. Ownership did
   not permit edits. They must be updated by their owner/coordinator to community-weighted values.
6. `cmig/core/metrics.py::community_contributions` independently retains the factor-1 fallback for
   missing abundance. It is outside this edge-artifact track, but it now disagrees with the chosen
   fail-closed policy and can fabricate a target-share contribution. Recommend a separately owned
   follow-up or coordinator adjudication.
7. Edge FVA attachment remains opt-in through `build_tidy(..., edge_fva=...)`; the current service
   path attaches community exchange FVA to `profile`, not member FVA to edges. When edge intervals
   are supplied, the new tests prove they cannot be mixed-basis. Cross-feeding intervals remain
   deliberately null because pairwise attribution is unidentifiable.

## Proposed CHANGELOG entries

- **BREAKING — tidy schema 1.3 / edge basis:** `edges.parquet.weight` is now the unsigned
  relative-abundance-weighted community contribution (`mmol gDW_community^-1 h^-1`), not a
  per-taxon rate. Direct and allocated cross-feeding weights share this basis. Consumers must not
  multiply tidy 1.3 weights by abundance again. Tidy `<=1.2` used the old per-taxon basis.
- `edges.weight_lo`/`weight_hi` now use the same community magnitude basis as `weight`; signed
  per-taxon FVA ranges are converted by edge direction before scaling. Allocated cross-feeding
  intervals remain null because pairwise transfers are not identifiable.
- Missing member abundance now prevents tidy edge publication with `MissingAbundanceError` instead
  of treating the member as abundance 1.0. A recorded abundance of zero remains a valid zero
  contribution.
- Legacy tidy bundles are semantically migrated from node abundances. A bare legacy edge table
  without node context emits `LegacyEdgeBasisWarning` and returns null edge quantities.
- Re-captured Gurobi and OSQP community solve goldens for tidy 1.3; answer digests moved while the
  frozen 11-component input `run_hash` remained unchanged on both solvers.

## Proposals deliberately not implemented

- Did not use `abundance or 1.0`; it fabricates a whole-community assumption and produces a mixed
  basis.
- Did not continue new bundle publication with NA weights plus a warning; the required scaling
  input is absent, so fail-closed is the selected round-5 proposal. NA+warning is used only for a
  context-free legacy table that must remain inspectable without inventing a value.
- Did not leave FVA bounds per-taxon or rename them; scaling them with `weight` gives every direct
  row one basis and preserves the existing schema names.
- Did not change the 11-component `run_hash`, re-bless envelope serialization, or touch U1-owned
  manifest/golden modules.
- Did not edit GUI, renderer, README/CHANGELOG, skill references, non-owned tests, or the pair
  fixture; the exact required integration changes are listed above.

