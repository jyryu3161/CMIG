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

### Fixed

- Anaerobic minimal-medium validation and essential-component labeling.
- Host microbial/host biomass scaling and non-identifiable transfer claims.
- Solver `None` results now become per-candidate diagnostics instead of aborting a search.

## [0.1.0] - 2026-07-10

- Initial research software release baseline.
