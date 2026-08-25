# Round-9 Track V6 — `analysis/second-solver-repro`

Read `REVIEW/round9/COMMON_BRIEF.md` first. Analysis/verification track:
`REVIEW/SCENARIO_RESULTS_ROUND6.md` §5 records a standing limitation — beyond
the solve golden, "nothing reproduced on a second solver — Gurobi only". Since
then rounds 7–8 changed medium semantics and edge weights. Your deliverable is
a REPORT, not code: quantify what OSQP can and cannot reproduce today.

## Goal

1. **Inventory the OSQP-capable surface.** From `cmig solvers`, the engine
   guard, and each command's `--solver` choices, list exactly which analyses
   can run on OSQP today and which are Gurobi-only (host stack, GA search,
   dfba-community, MILP-needing paths…), each with the code-level reason.
2. **Reproduce what can be reproduced.** For at least:
   - the 3-member bundled-pool solve on the AGORA Western overlay (the round-8
     tutorial scenario: Gurobi growth 0.1502) — run it on both solvers with
     identical inputs and compare growth, profile, and community-basis edge
     weights;
   - the solve fixture (already dual-golden — confirm `golden verify` and use
     its documented OSQP tolerance as the reference for what "agrees" means);
   - a `pair` run and a `single`/`minimal-medium` run if their surfaces accept
     OSQP — if they refuse, record the refusal verbatim as a finding.
   Report per-quantity deltas against the documented QP-approximation
   tolerance; classify each as within-tolerance / material / not-comparable.
3. **Honest verdict.** A table: analysis → OSQP status (reproduced within
   tolerance / deviates materially (numbers) / cannot run (reason)). No
   recommendation to loosen any tolerance; where deviation is material, say
   what a reader of published Gurobi numbers should conclude.
4. If you find an actual defect (e.g. an OSQP path crashing where the
   capability matrix says it works), do NOT fix code — record a minimal
   reproduction in the report as an integration note.

## Ownership

- `REVIEW/round9/report_V6.md` (your only repo deliverable)
- scratch space for runs: `/tmp/cmig-round9-v6/` (never commit run outputs)

## Constraints

- Zero changes to `cmig/**`, `tests/**`, docs, or fixtures.
- Every number in the report carries its command line, solver, and MICOM/
  solver versions (`cmig version`, `cmig solvers`).
