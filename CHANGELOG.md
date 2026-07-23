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

### Fixed

- Anaerobic minimal-medium validation and essential-component labeling.
- Host microbial/host biomass scaling and non-identifiable transfer claims.
- Solver `None` results now become per-candidate diagnostics instead of aborting a search.

## [0.1.0] - 2026-07-10

- Initial research software release baseline.
