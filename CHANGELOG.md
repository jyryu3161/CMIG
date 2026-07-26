# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). CMIG uses
semantic versioning for public releases.

## [Unreleased]

### Added

- Claude Code agent skill `cmig-metabolic-analysis` (`.claude/skills/`) that routes requests to the
  correct `cmig` workflow and enforces the scientific-validity guardrails, plus a
  `.claude-plugin/marketplace.json` making it installable following the anthropics/life-sciences
  marketplace pattern.
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
- **Known open — the osqp golden fixture is stale and is not fixed here.** It was captured at
  `golden_decimals: 4` while the gurobi one and the current default are 6, so its published
  `run_hash` `a422eb89…` is not reproducible by a real `cmig solve-fixture --solver osqp`, which
  produces `c491a6a8…`. Both fixtures are internally consistent; nothing in the suite re-derived a
  golden from its own stored components, and `golden verify` compares only `micom_version`, so this
  had been invisible. That invariant is now tested, and the stale state is pinned by
  `test_the_osqp_golden_is_stale_against_the_current_float_decimals_contract`. Recapturing moves a
  frozen contract hash, so it is deferred to a deliberate decision (`python -m cmig.golden_fixture`).
  The gurobi golden `29844e29…` is unaffected and re-derives exactly.
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
