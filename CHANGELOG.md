# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). CMIG uses
semantic versioning for public releases.

## [Unreleased]

### Added

- Claude Code agent skill `cmig-metabolic-analysis` (`.claude/skills/`) that routes requests to the
  correct `cmig` workflow and enforces the scientific-validity guardrails, plus a
  `.claude-plugin/marketplace.json` making it installable following the anthropics/life-sciences
  marketplace pattern.

### Documentation

- **Skill/README guardrails synced with the round-5 hardening.** The skill layer predated the
  round-5 scientific fixes and named none of their vocabulary, so following it faithfully could
  still produce a wrong conclusion. Added, in `.claude/skills/cmig-metabolic-analysis/` and
  mirrored in `README.md`:
  - **Multi-target search.** `--targets` / `--target-preset scfa` / `--multi-metric` /
    `--target-directions` were entirely undocumented. A "total SCFA" question answered with the
    default `normalized_weighted` scalarisation collapses onto a single-metabolite specialist:
    measured over the 5 bundled models, all 9 ranked candidates returned `ac=0, but=0, ppa=0,
    succ=0`, and rank 1 (`iHN637+iSFV_1184`) was reported as `lac__D=17.44, ac=0` — while
    `--multi-metric pareto` shows that same pair reaching `ac=27.75`. All three metrics were run
    over the identical pool; the same pair is reported as `lac__D=17.44` (`normalized_weighted`),
    `ac=8.19 + succ=10.41` (`carbon_equivalent`), or `ac=27.75` (`pareto` rank 1) — so
    `normalized_weighted` claims lactate and no succinate while `carbon_equivalent` claims
    succinate and no lactate, about one community on one medium. **`carbon_equivalent` is not an
    escape from the collapse**: it returned `but=0, lac__D=0, lac__L=0, ppa=0` for all 9 of its
    ranked candidates. The docs now state that the vertex collapse is a property of linear
    scalarisation rather than of the weighting, so only `pareto` answers a "best overall"
    question. The `pareto` **mode** (an N-dimensional epsilon-constraint frontier, any number of
    targets) is distinguished from the `pareto` **column** on a scalarised ranking (computed only
    for exactly 2 targets; `False` elsewhere means "not evaluated", not "dominated").
  - **`edges.parquet.weight` is a per-taxon flux.** Comparing raw edge magnitudes inverts member
    rankings; measured on a 2-member solve, acetate edges were `3.876` (abundance 0.1) vs `0.459`
    (abundance 0.9) while the community contributions were `0.388` vs `0.413`. Documented the
    reconstruction (exclude `cross_feeding`, sign by direction, multiply by abundance → equals
    `profile.net_flux`) and pointed at the `edges.weight basis:` line `inspect-run` prints.
  - **Custom-medium invalidation.** Pre-fix runs that used `--medium` must be re-run, the
    `run_hash` will not reveal it, and `provenance.medium_policy` is the discriminator. Documented
    the real cost of `--allow-unknown-medium` (exit 0, `status: degraded`, dropped nutrients, and a
    `medium_checksum` still covering the full requested medium) and the namespace-alias input error.
  - **dFBA interpretability.** `--close-untracked-uptake` was undocumented, so the previous advice
    sent users to audit `--dt`/`--km` on an experiment where Km is not rate-limiting. On
    `models/iML1515.xml` the naive recipe reports `status: completed` and a biomass number with
    `n_untracked_uptake: 14`.
  - **Exit-code contract** (`0` / `2` input error / `3` failed science) and `--allow-failed-run`,
    which no skill or README text mentioned.
  - **Two fingerprints:** `run_hash` certifies the inputs, `result_digest` certifies the answer;
    `artifact_integrity`; `cmig golden verify-envelope`; and the honest scope note that `cmig solve`
    emits no `result_digest`. Also documented `result_digest.cross_run_comparable` — digests are
    comparable *between* runs only for `host_map`, so cross-run comparison elsewhere manufactures
    false alarms.
  - **`inspect-run`'s payload (`schema_version 1.2`)**: documented `status_source` and all ten of
    its values, `degraded` as a tier, and `result_digest_absent_reason` with its four values. Stated
    that **`unknown` is a real answer, not a tool failure** — a recognised summary recording no
    run-level outcome now reports `status: unknown` / `status_source: no_status_signal` instead of a
    fabricated `ok` — and that `acceptance.interpretable: false` is a **veto** that overrides a
    rosier `manifest.status` and owns `status_source` when it wins, so the two can legitimately
    disagree. Also flagged that the status vocabulary is **not closed**: `infeasible` and `stalled`
    still reach `status` verbatim because the legacy alias table maps only `optimal`/`completed`, so
    a gate matching just the four tiers will miss them.
  - **`cmig host-ko-impact`** — a shipped workflow (GUI `Host / Knockout Impact`) that the skill's
    routing table and per-command reference both omitted.
  - `strain-growth --single-medium` (`model_default` reports native capability, not an interaction
    effect), `abundance-impact --fva`, `--accept-unreviewed-map` and the D/L stereoisomer hazard it
    waives, `--keep-host-uptake`, and the `search_unevaluated.csv` partition.
- **Preflight step added** to the skill (`uv run cmig version && uv run cmig solvers`): a
  genome-scale analysis can run 15+ minutes, and an environment missing the `engine` extra fails
  only once it reaches the solve. Documented the subtler case it also catches — `uv run` resolves the
  **nearest** project root, so running it from a git worktree or sibling checkout (each carrying its
  own `pyproject.toml`) resolves a *different* project and provisions a fresh minimal `.venv` with no
  `engine` extra; `cmig workflows` still succeeds there while every analysis command fails with
  `… 는 엔진 stack 필요`, and that message names a fix that would sync the wrong project. Measured:
  from the synced checkout `uv run` gives `…/CMIG/.venv` with `micom 0.39.0`; from a worktree of the
  same repo it creates `…/CMIG-wt-*/.venv` with 14 packages and no micom. `uv run cmig …` remains the
  documented invocation, matching the examples `cmig workflows` emits.
- Documented that `cmig solvers` lists `highs` although no command's `--solver` accepts it, and that
  the bundled `models/` pool is not a gut community (only *E. coli* is a common gut resident), so
  results over it are a methods demonstration rather than gut biology.
- Corrected stale multi-target artifact claims: multi-target `search` writes `pool_taxonomy.csv`,
  `search_plot.tiff` and conditionally `search_unevaluated.csv`, and does **not** write
  `search_member_matrix.csv` or `search_scatter.svg`.
- **Corrected over-confident guardrails found by independent verification.** Each had asserted more
  than the code supports:
  - `--close-untracked-uptake` **must be paired with a complete `--initial`**, and
    `dfba-sensitivity` accepts `--initial`. The previously prescribed example failed on the model it
    named: exit 3, 4/4 rows stalled at `final_biomass 0.01` (the initial value — no dynamics), after
    closing 22 exchanges. Supplying all 14 nutrients from a plain run's `untracked_uptake` gives
    exit 0, `interpretable: True`, 4/4 completed, and a real step-size signal (0.0536 at dt 0.1 vs
    0.0503 at dt 0.2). Both forms are now shown.
  - `--allow-failed-run` is **not universal.** It is rejected by `dfba`, `model-quality`,
    `publication-benchmark`, `spatial-preview` and `model-review` as an argparse error — which exits
    **2**, the same code documented for a bad medium spec, so the docs now warn against debugging
    the wrong thing.
  - `--robustness-fva` is **silently inert in multi-target mode** (`cli/main.py:4151` returns to the
    multi-target path before the flag is read; no columns, no warning, exit 0). It had been
    prescribed *in that mode* as the remedy for the scalarisation collapse. Documented as a current
    limitation, with `--multi-metric pareto` as the available route.
  - `publication-benchmark` exposes **33 options** (previously undocumented) and accepts **no
    `--close-untracked-uptake`**, so `publication_ready` cannot certify the dFBA guardrail; a
    load-bearing dFBA endpoint must come from a separate `dfba-sensitivity` run.
  - Recon3D loads in **~6–7 s**, not the ~30–60 s previously stated as "verified".
  - The edge→`net_flux` reconstruction is **not exact for every metabolite**: 23/25 agreed to
    <1e-9 while `mobd` and `btn` were off by ~1e-8 near the 1e-6 noise floor, and 19 of 44 edge
    metabolites had no profile row at all.
  - `per_target_capability_not_simultaneous` lives in **`flux_basis`**, not `diagnostic`.
  - `inspect-run` exits **2** on an unusable directory (missing `--run-dir`, corrupt
    `manifest.json`), not only 3 on `artifact_integrity: mismatch`.
  - `status: degraded` is the **normal** search outcome when any candidate is unevaluable.
  - Added `host_ko_impact.csv`, `gene-ko-search --rank-by {effect,remaining}` (which sets the whole
    KO ordering), `host-search-bigg --include-currency-metabolites`, and
    `strain-growth`'s `medium_metabolites_unavailable_to_member`.
- Integrated publication benchmark with model quality, community, search, dFBA sensitivity, host
  scale/mapping/coupling, checksums, acceptance checks, and artifact manifests.
- Annotation-aware host interface mapping and objective-fixed FVA transfer intervals.
- Cross-platform CI quality matrix and distribution-content audit.
- Apache-2.0 licensing, citation/Zenodo metadata, release checklist, and checksummed external-model
  source records.
- A pinned R 4.3.2/Bioconductor 3.18 `renv.lock` and per-figure runtime/input/script/output
  provenance sidecars.
- Mandatory host/microbial gDW basis kind and measurement/citation provenance; GUI and publication
  commands no longer prefill an equal-mass assumption.

### Changed

- **BREAKING (scientific): `--medium` now actually applies.** `apply_medium_checked` gated on
  `model.medium`, which lists only *currently open* uptakes, so a closed exchange could never be
  opened — roughly 90% of nutrients (acetate, butyrate, lactate, succinate, glycerol) were
  unreachable. Under `--allow-unknown-medium` they were dropped silently while the manifest still
  recorded the requested `medium_checksum` and minted a distinct `run_hash`, publishing a run as
  being on a medium it never used. Every consumer (`solve`, `search` and all multi-target
  variants, `host-microbe-bigg`, `abundance-impact`, and the GUI via `EngineService`) now shares
  the one metabolite-keyed path that `strain-growth` already used.

  **This changes published numbers without changing `run_hash`.** Measured on identical inputs:
  `solve --medium` growth `0.881561` → `1.125065` and `search --medium` target flux `18.13` →
  `13.64`, both under a byte-identical hash. The discontinuity cannot be encoded in a hash
  component (`cmig_core_version` is frozen), so runs are now stamped with a **non-hashed**
  `medium_policy` marker — `provenance.medium_policy` in a solve manifest and a top-level
  `medium_policy` in a workflow manifest — whose value moved from `open_uptakes_exact_key_v1` to
  `exchange_reactions_by_metabolite_v2`.

  **Action required:** any run produced before this change with `--medium` is suspect; its
  `medium_checksum` describes a medium that was only partially applied, or not applied at all.
  Re-run it. A manifest with no `medium_policy` key is from the old era.

- A medium file that gives two namespace aliases of one metabolite (`EX_ac_e` and `EX_ac_m`)
  different uptake limits is now refused as an input error (exit 2). Previously the last row
  silently won, so reordering identical CSV rows changed community growth `1.125065` → `0.954612`
  while `medium_checksum` — which sorts, and hashes both rows — stayed byte-identical. Aliases
  that request the *same* limit are merged and are unaffected.


- Cross-feeding allocation now conserves shared-pool supply and demand.
- Multi-target search returns one jointly feasible flux vector.
- Namespace review is mandatory unless the BiGG assumption is explicit.
- Run manifests now capture analysis settings, dependency versions, individual model checksums, and
  applied namespace mappings.
- Model-directory discovery now distinguishes COBRA JSON models from adjacent provenance and
  analysis JSON files.
- Weighted host ranking now requires explicit reference scales and combines only dimensionless
  normalized quantities; single-metric target transfer is the default.
- Deterministic sweep conditions no longer generate p-values without confirmed independent
  replicate IDs.

### Added

- `manifest.json` for every workflow kind now carries a **`result_digest`**: a sha256 over the
  artifact bytes the run produced, with a per-artifact breakdown. `run_hash` certifies the
  *inputs*; `result_digest` certifies the *answer*. Neither implies the other, and the gap between
  them was exploitable — three changes to `build_host_map` (capping reported entries, capping the
  host index, dropping currency metabolites) each rewrote the real interface map on real GEMs
  (67 entries → 22, → 62, and 144 → 73 on a larger host) while `run_hash`, `map_spec` and the
  matching-behaviour digest stayed bit-identical. `cmig inspect-run` recomputes the digest from the
  files on disk and reports a mismatch loudly, which also catches an artifact edited, truncated or
  deleted after the run. **`result_digest` is outside the input hash**, so no published `run_hash`
  moves because of it. `cross_run_comparable` marks the kinds whose artifacts have been *measured*
  byte-deterministic (currently `host_map`), so a digest difference between two runs of those kinds
  is a finding rather than noise.

### Fixed

- **The `strain-growth` figure turned "never measured" into a measured zero.** `single` and
  `community` bar heights were built with `_optional_float(...) or 0.0`, so a member whose
  alone-solve raised (`single_growth: null`, `single_status: "failed"`) was drawn as a zero-height
  "Single model" bar beside a real "Community" bar — which reads as obligate syntrophy, a
  biological conclusion invented by a plotting default. Every other layer of the command was
  already honest (blank CSV cell, `null` in JSON, degraded summary tier, a run-level warning naming
  the member, an em dash in the GUI table); only `strain_growth_plot.svg`/`.tiff` — the artifacts
  that go in a manuscript — fabricated. An unmeasured leg is now NaN (no bar drawn), each omitted
  bar is labelled "not evaluable" in place, and the title states `N of M members not evaluable`.
  A genuinely measured zero is still drawn as zero.
- **`sweep` certified an all-failed grid as `status: "ok"`, and exited 0.** The summary carried a
  hard-coded literal and the manifest derived `"ok" if rows else "failed"` — but a failed condition
  *stays* in `rows` by `core/sweep.py`'s no-drop contract, so the `failed` branch was reachable only
  for an empty grid. Reproduced with an ordinary medium file and no flags: every condition
  `status: failed` with `value: NaN` in `sweep.parquet`, while the summary, the manifest,
  `inspect-run` and `$?` all said ok with no warning printed. The run-level tier is now derived from
  the per-condition statuses (all failed → `failed`, some failed → `degraded`), the failed
  condition ids are named in `warnings` and printed, `sweep_summary.json` gains `n_ok`/`n_failed`,
  and **`sweep` now exits 3 when every condition failed** (`--allow-failed-run` waives the exit
  code, never the recorded status). `run_hash` is unchanged — none of these fields is hashed.
- **`host-search-bigg` ranked and plotted a non-optimal host LP as an evaluated result.**
  `evaluation_status` was the literal `"ok"` in the success branch, but
  `core/host_coupling.solve_bigg_host` *returns* `HostSolveResult(False, status, 0.0, …)` for a
  non-optimal host LP rather than raising — so that branch was taken, `host_objective` became a
  fabricated `0.0`, and the candidate was ranked with `n_candidates_failed: 0`, painted in the
  "evaluated ok" colour and exited 0, while the same row's `warnings` cell read "the reported host
  objective is not a result". `evaluation_status` is now derived from the community and host solve
  statuses (matching the sibling `host-microbe-bigg`), an unevaluable candidate publishes NaN rather
  than `0.0` in every scientific field and moves to the `unevaluated` block, and the ranking figure
  states `N of M candidates not evaluable (excluded)`.
- **`inspect-run` claimed to certify artifact bytes it did not check.** `result_digest` only digests
  the artifacts the *manifest* declares, and no workflow declared its publication figures — so a
  `gene_ko_plot.svg` overwritten with `<svg>FABRICATED FIGURE</svg>` still printed
  "certifies the ARTIFACT BYTES — verified", with the tampered file listed under `artifacts:` in the
  same output. Meanwhile each summary JSON's own `artifacts` field *did* list the figures, so the two
  lists in one run directory disagreed. Every workflow writer now returns the artifact list it
  actually wrote and the manifest declares exactly that list, so the two agree by construction and
  the figures are covered by `result_digest`. `run_hash` is unchanged (`artifacts` is not a hash
  component); `result_digest` values move for every kind that writes a figure.
- **A detected `result_digest` mismatch did not reach `status`, `$?` or `--format json`.** The
  mismatch was reported loudly on stderr — but only in the text branch, while the payload said
  `status: "ok"` beside `result_digest.match: false` and the command exited 0. Any gate written
  against `status` or `$?` (as `SKILL.md`'s mandated verification step is) accepted a run whose
  artifacts are not the artifacts its manifest fingerprinted. `inspect-run` now reports
  `artifact_integrity: verified | mismatch | not_recorded`, reports `status: failed` with
  `status_source: result_digest_mismatch` on a mismatch (the manifest's own status stays readable
  under `manifest.status`), emits the stderr block in **both** output formats, and **exits 3**. A
  failed *solve* still exits 0 here — `inspect-run` reports on a run, it does not re-judge it.
  `inspect-run`'s payload `schema_version` moves 1.0 → 1.1.
- `inspect-run` dropped the signals the manifest already recorded. `_compact_manifest` whitelisted
  12 keys, so the `medium_unapplied` diagnostic naming dropped nutrients, the `medium_policy` marker
  created for the `--medium` discontinuity above, `provenance`, `warnings` and the summary *values*
  (only the key names were listed) were all invisible to the tool's own inspection command. All five
  are now surfaced.
- `provenance.medium_policy` in a solve manifest is now stamped writer-last, so a caller passing its
  own `medium_policy` key cannot silently overwrite it — the adjacent comment claimed as much, but
  the dict ordering said otherwise.
- A gene knockout whose solve *raised* was published as the screen's strongest result. The
  exception handler wrote `score: 0.0` and `score_delta: -baseline.score` — a finite,
  large-magnitude, entirely plausible effect size that was never measured — and the writer
  numbered every row it was given, so the failure reached `gene_ko_rankings.csv` as rank 1 and was
  printed as "rank 1 (largest effect)". An unevaluated knockout now carries NaN in every
  scientific field (blank in CSV, null in JSON), takes `rank 0` = "no rank", is published under
  `unevaluated` rather than `top_ranked`, and the rank-1 headline is suppressed when nothing was
  evaluable. `gene_ko_summary.json`'s `status` is derived from the rows instead of being the
  literal `"ok"` it always was. This aligns the gene-KO artifacts with the convention the four
  search paths already used, so one rule — "is `rank` nonzero?" — answers "was this row measured?"
  everywhere.
- **Breaking for published `host_map`, `host_microbe_bigg`, `host_search_bigg`, `host_ko_impact`
  and `publication_benchmark` run_hashes** (five kinds — see the two entries below for which change
  moves which). Re-derive any published run_hash of these kinds against this release.
- The host-map matching policy recorded in `map_spec` described the matcher instead of deriving
  from it: `match_order`, `secretion_criterion`, `annotation_requires_unique_target` and
  `annotation_sources` were inert literals no code path read, guarded only by a hand-bumped
  `HOST_MAP_MATCH_POLICY_VERSION`. Changing one comparison in `build_host_map` took the
  auto-admitted interface map from 67 entries to 11 while `run_hash` stayed bit-identical, and the
  manifest's own `summary.interface_map_checksum` moved underneath it. `map_spec` now carries
  `match_behavior`, a digest of what the matcher and the id normalizer actually do to a frozen
  probe fixture (`cmig.core.host_map_probe`), and the four constants above now drive the matcher
  rather than merely describing it. **This narrows the gap; it does not close it.** The probe
  measures one small synthetic instance, so a change keyed on *scale* (a cap) or on *real BiGG
  vocabulary* (a currency-metabolite filter) can still leave `match_behavior` unmoved — that is
  what `result_digest` above is for. What is guaranteed: any change to the matching *rules the
  probe exercises* moves the `host_map` hash, and any change to the produced artifacts moves
  `result_digest`. Moves `host_map` and `publication_benchmark`. The produced interface maps are
  unchanged by this release; only the fingerprint over them is.
- `host_spec` hashed the *path* used to reach each file alongside the checksum that already pinned
  its bytes, so the same host model reached by an absolute path — or from a different working
  directory — fingerprinted as a different run. Only the file name is hashed now. Moves all five
  kinds that record `host_spec`: `host_microbe_bigg`, `host_search_bigg`, `host_ko_impact`,
  `host_map`, `publication_benchmark`.
- The osqp golden fixture no longer reproduced its own published hash. It stored components
  pre-rounded at 6 decimals while recording `golden_decimals: 4`, so `a422eb89…` was an artifact
  no code path re-derived; nothing in the suite re-derived a golden from its own stored
  components, and `golden verify` compared only `micom_version`, so it had been invisible. The
  three stored abundances are corrected to 4 decimals, which makes the fixture self-consistent
  **without moving the published hash** — `a422eb89…` still verifies, and now genuinely
  reproduces. `golden verify` compares run_hashes as well as versions, and
  `test_each_shipped_golden_re_derives_its_own_run_hash_at_its_own_decimals` asserts the invariant
  for every declared solver variant rather than for gurobi alone (the blind spot that let this
  through: every hash pin in the suite was gurobi-only). The gurobi golden `29844e29…` is
  unaffected and re-derives exactly.
- **The id normalizer destroyed D/L stereochemistry, and the manifest recorded that as policy.**
  `_normalize_metabolite_id` stripped any trailing `__<Uppercase>` token as a MICOM taxon suffix,
  but BiGG writes stereoisomers exactly that way, so `lac__D_e` and `lac__L_e` both normalized to
  `lac` — as did `glc__D`, the most common carbon source in the bundled models. Because
  `solve_bigg_host` normalizes both the reviewed interface-map keys and the microbial
  availability, a reviewed D-isomer mapping matched L-isomer availability and opened the D
  exchange: the host took up, and grew on, a molecule it cannot transport. The descriptor is now
  preserved (`lac__D_e` → `lac__d`, `lac__L_e` → `lac__l`) while genuine taxon suffixes are still
  stripped (`EX_ac_m__Escherichia_coli` → `ac`), the discriminator being token length rather than
  case. **Breaking for published `host_map` and `publication_benchmark` run_hashes:**
  `map_spec.id_normalization.uppercase_stereoisomer_suffix_folded` was `true` and is now `false`,
  and it is measured off the live normalizer rather than restated, so it cannot go stale again.
  The matching-behaviour digest moved with it
  (`sha256:70782b1b…` → `sha256:36059e16…`). Re-derive any published run_hash of these two kinds.
- Envelope-golden component fixtures are now **built by the same builders real runs use**
  (`medium_component`, `host_spec_component`, `host_map_policy`, `bundle_component`) instead of
  being transcribed as literals. A transcribed literal made the drift gate certify a *copy* of the
  contract: the `host_spec` change above moved five kinds' published hashes and the gate stayed
  silent, because its `host_spec` fixture was a hand-written dict no builder ever touched.
- The `publication_benchmark` bundle refused to carry a workflow-scope `manifest.json` as its
  `community_solve` child hash, and solve manifests now state `manifest_scope: "solve"` instead of
  leaving a reader to infer scope from a missing key (outside the hash; no solve run_hash moves).
- The workflow-envelope drift gate now also fails when a component fixture is edited without
  re-blessing; previously a changed fixture value left the golden pinning a shape the code no
  longer produced while the gate still reported every kind OK.
- Anaerobic minimal-medium validation and essential-component labeling.
- Host microbial/host biomass scaling and non-identifiable transfer claims.
- Solver `None` results now become per-candidate diagnostics instead of aborting a search.

## [0.1.0] - 2026-07-10

- Initial research software release baseline.
