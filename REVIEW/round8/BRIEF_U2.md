# Round-8 Track U2 — `fix/edges-weight`

Read `REVIEW/round8/COMMON_BRIEF.md` first. This is the round's highest-stakes
scientific track: the last remaining top-priority known-open item.

## Background

`README.md` (Scope And Limitations) and round-5's final report record that
`edges.parquet.weight` is a **per-taxon flux whose magnitude inverts against
true community contribution** — a member at abundance 0.01 with high per-gDW
flux can out-rank the member actually supplying the community. Only the unit
disclosure landed. Round 5 deferred the value fix for three explicit reasons,
all of which you must resolve, not sidestep:

1. it needs re-blessing the frozen solve goldens **on both solvers**;
2. two reviewers proposed **incompatible `abundance is None` contracts**;
3. neither prior patch **scaled the FVA bounds** consistently with the weight.

Read the round-5 material on this finding first
(`REVIEW/FINAL_REPORT_ROUND5_2026-07-26.md`, `REVIEW/round5/report_*.md`,
`REVIEW/CROSS_REVIEW_round*.md` — search for edges weight / abundance).

## Goal

1. **Make `edges.parquet.weight` a community-basis quantity** (per-taxon flux
   scaled by relative abundance) in `cmig/core/tidy.py` /
   `cmig/core/interactions.py`, so magnitude ranks match actual community
   contribution.
2. **Decide and document the `abundance is None` contract.** Reconstruct both
   round-5 proposals, choose one, and defend the choice scientifically in your
   report (what does a missing abundance mean, what value/na semantics does the
   column carry, what warning is emitted). The losing contract's failure mode
   must be described so the choice is auditable.
3. **Scale FVA bounds consistently**: any `fva_lo`/`fva_hi` (or equivalent
   bound columns) attached to edges must be in the same basis as the weight, or
   be explicitly renamed/documented if they deliberately stay per-taxon. No
   mixed-basis rows.
4. **Schema/versioning honesty**: bump whatever tidy-bundle schema/version
   marker exists so a reader can tell pre-fix from post-fix artifacts; keep the
   old basis documented. Do not touch `workflow_manifest.py` (U1-owned) — if
   the tidy schema marker lives there, record it as an integration note
   instead.
5. **Re-bless the solve goldens on BOTH solvers** (Gurobi and OSQP are both
   installed and licensed here) via the documented golden capture procedure.
   The frozen 11-component `run_hash` must NOT move — it hashes inputs. The
   expected artifacts and any published `result_digest` will move; list every
   changed golden file and the before/after digests in your report.

## Ownership

- `cmig/core/tidy.py`, `cmig/core/interactions.py`
- `fixtures/community_3_member/expected/**` (re-bless via procedure only)
- tests: `tests/test_tidy*.py`, `tests/test_interactions*.py` (whatever exists
  for these modules — enumerate first), new `tests/test_round8_edges_weight.py`
- Do NOT touch: `cmig/cli/main.py` (U1), `cmig/gui/**` (U5 — note: the round-7
  GUI contribution chart multiplies `edge.weight x nodes.abundance` for
  display; once weight is community-basis that multiplication double-counts.
  Do NOT fix the GUI yourself — flag it prominently as an integration note),
  `workflow_manifest.py`/`golden.py` (U1), README (coordinator).

## Verification to include in your report

- A worked numeric example (the round-5 inversion scenario): before the fix the
  low-abundance member out-ranks; after, ranks match community contribution.
  Show the actual numbers from a real solve.
- `golden verify` output on both solvers after the re-bless.
- Confirmation the 11-component solve `run_hash` did not move, with hashes.
- The `abundance is None` decision record.
