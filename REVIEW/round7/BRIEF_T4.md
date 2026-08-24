# Round-7 Track T4 — `docs/release-freshness`

Read `REVIEW/round7/COMMON_BRIEF.md` first. You touch documentation and release
metadata ONLY — zero Python changes.

## Goal

1. **Refresh the three stale operational docs** (all predate rounds 5–6):
   - `docs/cmig_workflow_tutorial.html` — covers only 25 commands; missing
     host-ko-impact, dfba-sensitivity, host-search-bigg, host-generic,
     host-benchmark, publication-benchmark, namespace-suggest,
     search-advanced-fixture, and the new round-6/GA options
     (`--allow-unknown-medium`, `--strategy ga`, `--ga-*`). Update it against
     the live `cmig --help` output.
   - `docs/PUBLICATION_VALIDATION.md` — DANGEROUS: it predates the round-6
     boundary-isolation change (Human-GEM host objective moved 368.01 → 0.0)
     and the release checklist requires re-running it. Update every number,
     command, and expectation to post-round-6 semantics; where a number needs a
     solver run you cannot perform, mark it clearly as `TO RE-RUN AT RELEASE`
     with the exact command.
   - `RELEASE_CHECKLIST.md` — add the missing `cmig golden verify-envelope`
     gate (it protects every non-solve run_hash and is absent), and re-order
     steps if needed to match current CI (`.github/workflows/ci.yml`).
2. **Skill-doc hygiene** in `.claude/skills/cmig-metabolic-analysis/`:
   - Replace unpinned `file.py:NNNN` line citations with symbol names (at least
     the known-rotten ones: the `--robustness-fva` early-return citation and
     the strain-growth exact-medium citation in
     `medium_presets/PROVENANCE_gut_media.md` §9).
   - Complete the `--allow-unknown-medium` roster (it is also on
     gene-ko-search, host-microbe-bigg, host-ko-impact, host-search-bigg).
   - Do NOT document `--exact-medium` (T1 is building it; the coordinator will
     reconcile after merge).
3. **0.2.0 release prep (documents only, no version bump):**
   - Draft the `## [0.2.0]` section by organizing the current `[Unreleased]`
     block — as a NEW file `docs/release-drafts/0.2.0-changelog-draft.md`; do
     NOT edit `CHANGELOG.md` itself (other tracks append to `[Unreleased]`
     concurrently).
   - Write `docs/release-drafts/0.2.0-version-alignment.md`: what must change in
     `pyproject.toml` / `cmig/__init__.py` / `CITATION.cff` / `.zenodo.json` /
     `.claude-plugin/marketplace.json` (currently at an unrelated 1.0.0), and a
     proposal for a CI guard asserting the version strings agree.
4. **Orphan asset decision memo**: `fixtures/Human-GEM-v1.19.0.xml` (43 MB,
   gitignored, no consumer, no checksum, absent from `data/gems/GEM_SOURCES.json`).
   Write a short recommendation (register with provenance + resolver entry, or
   delete) in `docs/release-drafts/human-gem-fixture-decision.md`. Do not delete
   anything.

## Ownership

- `docs/**` (except `docs/archive/**` — leave history alone)
- `RELEASE_CHECKLIST.md`
- `.claude/skills/**`
- `medium_presets/PROVENANCE_gut_media.md` (citation fixes only)
- Do NOT touch: `CHANGELOG.md`, `CITATION.cff`, `.zenodo.json`, `README.md`,
  any `.py`, any `cmig/**`

## Verification to include in your report

- For each doc: the command outputs (`cmig --help`, `cmig <cmd> --help`,
  `cmig workflows --format json`) you validated against, and a claim-by-claim
  note for PUBLICATION_VALIDATION.md distinguishing "verified against code",
  "verified against REVIEW/SCENARIO_RESULTS_ROUND6.md", and "TO RE-RUN AT
  RELEASE".
