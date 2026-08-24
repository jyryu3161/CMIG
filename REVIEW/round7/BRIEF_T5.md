# Round-7 Track T5 — `feat/host-two-interface`

Read `REVIEW/round7/COMMON_BRIEF.md` first. You own the host science core. This
is the scientifically deepest track — correctness beats coverage.

## Background

Spec §12 (`CMIG_명세서_v3.0.md`) requires a 2-interface host coupling
(lumen/apical vs blood/basolateral). Today `cmig/core/host.py` classifies
interfaces by an `_lumen`/`_blood` **id suffix** that only CMIG's toy/synthetic
host has. For real GEMs (Recon3D, RECON1, Human-GEM) the classifier finds
nothing, sets `has_lumen_blood_interfaces=False` and
`quantitative_coupling_ready=False`, and the production path
(`host-microbe-bigg`) is effectively single-interface. The basolateral leg of
§12 is therefore unavailable for every real host model.

## Goal

1. **Compartment/annotation-driven interface classification.** Extend the
   classifier so real GEMs can be classified: use compartment ids/names
   (e.g. extracellular `e`/`s` vs blood-side compartments), reaction/metabolite
   annotations, and boundary topology (`cmig/core/boundary.py` primitives) —
   with the id-suffix rule retained as one signal, not the only one. The result
   must be **reviewable, not silently guessed**: every classified interface
   carries its evidence (which rule fired), and unclassifiable models keep
   today's explicit `has_lumen_blood_interfaces=False` honesty.
2. **Interface assignment in the host-map review flow.** Carry the per-exchange
   interface assignment through `cmig/core/host_map.py` /
   `host_map_probe.py` so the existing reviewed-interface-map workflow
   (`--interface-map`, `--accept-unreviewed-map`) can record and override
   interface sides. The reviewed-map file format may gain an optional column;
   old files must keep loading with unchanged meaning.
3. **Coupling semantics.** Where a real classification succeeds, extend
   `cmig/core/host_coupling.py` so uptake/secretion constraints can be applied
   per interface side. Preserve every existing guard: maintenance-objective
   guard, `host_isolation_policy = all_boundary_uptake_v2` semantics,
   `boundary_isolation_policy = boundary_reactions_v1` semantics. If the round-6
   host regression tests conflict with a change you believe is correct, STOP and
   record it — do not adjust a regression expectation without flagging it
   prominently in your report.
4. **Untangle the import cycle.** `cmig/core/host.py:596` module-level
   `__getattr__` re-exporting `run_bigg_host_microbe`/`solve_bigg_host` breaks
   the host↔host_coupling cycle and causes 5 mypy `"object" not callable`
   errors downstream. Restructure (e.g. move shared types to a small
   `host_types.py`, import directly) so the `__getattr__` disappears and mypy
   passes for these sites WITHOUT `# type: ignore`.

## Hard constraints

- **No CLI flags.** `cmig/cli/main.py` is T1-owned. New behavior must be
  reachable through existing flags/APIs; propose any new flag in your report's
  Integration notes for the coordinator to wire.
- Existing host tests must stay green, including (after
  `uv run python scripts/download_human_gems.py`) `tests/test_recon3d_host.py`
  and the round-6 human-GEM host regressions.
- No run_hash drift: manifest serialization is out of your ownership. New
  provenance can be added to payloads only where the schema already allows
  free-form diagnostics.

## Ownership

- `cmig/core/host.py`, `host_coupling.py`, `host_map.py`, `host_map_probe.py`,
  `host_impact.py`, plus a new `cmig/core/host_types.py` if needed
- tests: `tests/test_host*.py`, `tests/test_recon3d_host.py`, host-related
  `tests/test_round6_*.py` (expectation changes require prominent flagging),
  new `tests/test_round7_host_interface*.py`

## Verification to include in your report

- Classification evidence table for Recon3D (and RECON1 if downloadable):
  which compartments/annotations were found, what was classified, what remained
  unclassified — honestly.
- Proof the toy host path is byte-identical in behavior (existing tests).
- mypy output for the 5 previously failing call sites.
