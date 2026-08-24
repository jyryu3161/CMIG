# Round-8 Track U6 — `feat/community-dfba`

Read `REVIEW/round8/COMMON_BRIEF.md` first. Scientific feature track:
item 3 of `REVIEW/CMIG_COMETS_dfba_spatial_notes_2026-06-05.md`
§"Next Practical Extensions" — a **well-mixed community dFBA prototype for
MICOM communities**, before any spatial work.

## Background

`cmig/core/dfba.py` is a single-model well-mixed dFBA: Michaelis-Menten uptake,
adaptive Δt, event log, non-negativity, `acceptance.interpretable` gating, and
an untracked-uptake honesty guard (`--close-untracked-uptake` semantics). The
community version must inherit that honesty culture, not just the mechanics.

## Goal

1. **Library-level `run_community_dfba`** in `cmig/core/dfba.py` (or a sibling
   `cmig/core/dfba_community.py` if that keeps the module readable):
   - state = shared extracellular metabolite pool + per-member biomass;
   - each step: bound each member's uptake from the shared pool via the same
     MM kinetics style as the single-model path, solve the MICOM community
     (build once, rebind bounds per step — measure and report the per-step
     cost), apply growth and exchange fluxes to per-member biomass and the
     shared pool, non-negativity clamps with events;
   - deterministic; adaptive Δt with the same acceptance/interpretability
     gating philosophy — a run that depletes an untracked substrate or hits a
     solver failure must say so explicitly, never continue silently;
   - death/washout is out of scope; state it.
2. **Timecourse output**: per-member biomass + tracked metabolite
   concentrations, written through the existing dFBA output conventions
   (`cmig/io/dfba_output.py`) with a clearly distinct kind/marker so a reader
   cannot mistake a community timecourse for a single-model one. Parquet writes
   should use the atomic primitive from `cmig/io/atomic.py` (already available)
   — but do not modify `io/atomic.py` itself (U3 owns it this round).
3. **Validation tests** (`tests/test_round8_community_dfba.py`), pure
   scientific pinning:
   - a 2-member cross-feeding synthetic case (producer secretes what consumer
     needs) where the consumer's growth demonstrably depends on the producer —
     the qualitative signature must be asserted, with tolerances justified;
   - glucose-depletion dynamics vs the single-model path for a 1-member
     "community" (should closely track the existing single-model result — this
     is the strongest regression anchor; quantify the agreement);
   - explicit-infeasibility and untracked-uptake honesty cases.
   Use the MICOM `test_taxonomy()` / synthetic models the existing tests use;
   Gurobi is available.
4. **No CLI.** `cmig/cli/main.py` is U1-owned. Design the config surface
   (dataclass) so a future `cmig dfba-community` subcommand is a thin wrapper,
   and write the exact proposed CLI in your report's integration notes. No
   workflow-manifest changes either (U1) — propose the manifest components in
   the report.

## Ownership

- `cmig/core/dfba.py` (or new `cmig/core/dfba_community.py` + minimal glue in
  `dfba.py`), `cmig/io/dfba_output.py`
- tests: `tests/test_dfba.py` (only additive/refactor-safe edits),
  `tests/test_round8_community_dfba.py`
- Do NOT touch: `cmig/cli/main.py`, `cmig/core/engine.py` (22 importers — use
  its public surface; if it is missing something, integration note),
  `io/atomic.py` (U3), manifests/goldens (U1), GUI (U5).

## Verification to include in your report

- The 1-member community vs single-model agreement numbers.
- The cross-feeding dependence demonstration with actual trajectories.
- Per-step solve cost measurement (build-once vs naive rebuild).
- Existing `tests/test_dfba.py` green, `golden verify-envelope` unchanged.
