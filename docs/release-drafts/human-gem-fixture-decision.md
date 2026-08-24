# Decision memo: orphan Human-GEM v1.19.0 fixture

## Recommendation

Delete the local `fixtures/Human-GEM-v1.19.0.xml` copy during release cleanup; do not register or
redistribute it in its current form.

This track does **not** delete the file. It is gitignored and absent from this worktree, so any copy
on another release machine remains a local, recoverable operator asset until the coordinator acts.

## Basis

- The reported file is about 43 MB, gitignored, and has no tracked checksum or retrieval record.
- It is absent from `data/gems/GEM_SOURCES.json` and from the resolver/download workflow shared by
  the CLI and tests.
- No code path selects the versioned fixture name. The only tracked references were the stale
  publication-validation commands, which now use the registered Recon3D acquisition path.
- Keeping an unverified external GEM under `fixtures/` invites accidental dependence on bytes that
  CI, collaborators, and release archives cannot reproduce.
- CMIG already has a coherent external-host pattern: model bytes stay untracked, while source URL,
  licence, checksums, byte counts, structural counts, objectives/warnings, and retrieval tooling live
  under `data/gems/`.

## Release action

1. Confirm no private run or manuscript still names the local path.
2. If it is not needed, remove the local file and record that cleanup in the release log; no Git
   history changes are needed because the bytes are ignored.
3. Continue publication validation with the checksum-verified Recon3D path documented in
   `docs/PUBLICATION_VALIDATION.md`.

## If Human-GEM becomes a required supported host later

Do not restore it as an ad hoc fixture. Register it through the same provenance pattern as
Recon3D/RECON1:

- add the exact versioned source/release DOI, licence, retrieval date, compressed and decompressed
  SHA-256 values, byte counts, server metadata, structural counts, compartments, default objective,
  and objective warning to `data/gems/GEM_SOURCES.json`;
- extend the download/verify script and the shared human-GEM resolver with an explicit stable id;
- add checksum/count and resolver tests plus distribution-exclusion coverage;
- update publication validation to name the registered id and archive the verified checksum.

That is a separate feature and crosses T4's documentation-only ownership, so it is intentionally
not implemented here.
