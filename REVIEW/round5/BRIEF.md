# Track P4 — FOLLOW-UP IMPLEMENTATION (manifest coverage + envelope drift gate)

Worktree: `/Users/jaeyongryu/orca/CMIG-wt-followup` (branch `feat/p4-manifest-drift`)

Read `/private/tmp/claude-501/-Users-jaeyongryu-orca-CMIG/55ffea12-ed16-4a80-8fbd-99261aefeaef/scratchpad/round5/COMMON_BRIEF.md` — the execution-environment and
evidence rules are binding. Unlike tracks P1–P3, **this track implements**.

## Background (from `REVIEW/FINAL_REPORT_2026-07-25.md`, phase 4)

A versioned workflow manifest (`cmig/core/workflow_manifest.py`) now covers 11
workflow kinds / 12 commands: `model_pool_search`, `multi_target_model_pool_search`,
`strain_growth`, `abundance_impact`, `gene_ko_search`, `host_microbe_bigg`,
`host_search_bigg`, `host_ko_impact`, `sweep`, `dfba`, `model_quality`.

The report names two remaining gaps, and they are this track's work:

> **Still emitting no workflow manifest:** `host-map`, `publication-benchmark`,
> `dfba-fixture`, `dfba-sensitivity`, `spatial-preview`, `stats-*`,
> `sandbox-fixture`, `host-fixture`, `host-generic`, `host-benchmark`,
> `namespace-suggest`, `model-review`. Two of these matter more than the rest:
> `host-map` produces the interface-map decisions that every host run depends on,
> and `publication-benchmark` is the surface that claims to bundle the whole audit.
>
> **No drift gate.** `golden verify` (SC-5) protects the 11-component solve hash,
> but nothing equivalent would catch a future change to the workflow envelope's
> serialization silently altering workflow hashes.

## Task 1 — `host-map` workflow manifest

`host-map` currently writes `host_map_summary.json`, `host_exchange_map.csv` and
`host_interface_map.json` but no `manifest.json`. Add one via the existing
`_emit_workflow_manifest` path in `cmig/cli/main.py`, following exactly the
conventions the 11 existing kinds use. The recorded parameters must be the
**answer-determining** inputs — i.e. everything that, if changed, could change the
produced interface map (host model + hash, microbe exchange source, namespace
settings, matching thresholds/policies, any stereoisomer or fuzzy-match option,
CMIG version). Verify by construction, not by assumption: change each recorded
parameter and confirm the hash moves; re-run identical inputs and confirm the hash
is bit-identical.

## Task 2 — `publication-benchmark` workflow manifest

Same, for `cmig publication-benchmark` (`cmig/service/publication_benchmark.py`,
`cmig/cli/publication.py`). This surface claims to bundle the whole audit, so its
manifest must record the set of sub-runs it bundled (their kinds and hashes), not
only its own arguments — a reader must be able to tell *which* runs the bundle
certifies. Decide and document whether the bundle hash includes the child hashes
(it should) and prove determinism both ways.

## Task 3 — envelope drift gate

Build the missing gate: a regression test that fails if a future change to the
workflow-envelope serialization silently alters workflow manifest hashes.

Design constraints:
- It must pin the **envelope serialization**, not just one workflow's inputs — i.e.
  a golden set of `(kind, canonical_input_dict) → expected_hash` covering every
  registered kind, so adding a field, reordering keys, or changing the canonical
  JSON form breaks the test loudly.
- It must fail with a message that tells the developer *what* changed and how to
  intentionally re-bless it (mirroring how `golden verify` is re-blessed).
- Adding a **new** kind must not break the gate, but silently changing an existing
  kind's serialization must.
- Wire it so `pytest` runs it. If there is a natural home next to `golden verify`
  (SC-5) or a CI job in `.github/`, wire it there too.

Look at how `cmig/core/golden.py` and the existing golden verification are
structured and stay consistent with that idiom rather than inventing a new one.

## Constraints

- The frozen 11-component `community_solve` hash must remain **bit-identical**
  (`29844e29…cef29ab`). Verify with `golden verify` on both solvers before you
  finish.
- Follow the existing code's conventions exactly (naming, error handling, the
  "report the failure and return no hash rather than fabricate one" behaviour of
  `_emit_workflow_manifest`).
- Add regression tests for everything you add, in the style of the existing tests.
- The full suite (`$CMIG_PY -m pytest -q tests/`) must stay green (baseline: 731
  passed, 2 pre-existing skips). `ruff check cmig tests` must stay clean.

## Deliverable

1. Implement in the worktree. Do **not** commit — leave it in the working tree.
2. Write a report at
   `/private/tmp/claude-501/-Users-jaeyongryu-orca-CMIG/55ffea12-ed16-4a80-8fbd-99261aefeaef/scratchpad/round5/p4/report_impl.md`
   with: what you changed (file:line), the determinism evidence (actual hashes,
   both directions), the drift-gate design and a demonstration that it **actually
   fires** when you deliberately perturb the envelope serialization (show the
   failure output, then revert the perturbation), and the final test/ruff/golden
   output.
