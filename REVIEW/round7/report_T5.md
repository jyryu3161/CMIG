# Round-7 T5 Report — `feat/host-two-interface`

## What changed and why

Implemented an evidence-backed host interface layer in the T5-owned host core.

- Added `cmig/core/host_types.py` as the shared, cycle-free home for host result types,
  interface-map types, validation helpers, and interface classification.
- Replaced suffix-only classification with conservative evidence aggregation over:
  - reviewed interface-map overrides;
  - the historical `_lumen` / `_blood` suffixes;
  - reaction and metabolite annotations;
  - reaction and metabolite names carrying side-specific terms such as `intestinal lumen`,
    `apical`, `portal blood`, and `basolateral`;
  - explicit compartment ids/names;
  - a paired-compartment rule in which generic external `e`/`s` is called lumen only when the
    same model exposes a distinct, explicit blood-side compartment;
  - the complete `model.boundary` view, so a second external compartment omitted by cobra's
    single-external-compartment `model.exchanges` inference is not lost.
- Every classified exchange has structured evidence (`rule`, `source`, `value`, `interface`).
  Conflicting signals remain unclassified unless a reviewed-map entry explicitly overrides them.
  Generic `e` alone is never silently guessed to be lumen.
- `HostModelSummary` now carries a JSON-ready `interface_classification` audit. A model reports
  `has_lumen_blood_interfaces=True` only when both sides have evidence. Quantitative coupling
  readiness is stricter: every exchange must be classified and both sides must exist.
- `host_map.py` now carries `interface`, `interface_evidence`, and side counts on its core result
  entries, accepts optional reviewed side overrides, and finds explicit second-side boundaries
  without changing the matcher's first-wins model order.
- `host_map_probe.py` has a separate side/evidence probe. It deliberately does not enter the
  existing hashed `map_spec.match_behavior`, so this track does not move published run hashes.
- `solve_bigg_host` / `run_bigg_host_microbe` accept both reviewed-map value forms:

  ```json
  {"ac": "EX_ac_e"}
  ```

  remains the legacy form with unchanged routing, while:

  ```json
  {"ac": {"host_exchange": "EX_ac_e", "interface": "lumen"}}
  ```

  activates side-aware semantics. Microbial availability can open only lumen/apical entries;
  `host_medium` can open only blood/basolateral entries. A microbial secretion mapped to blood is
  not coupled and is named in warnings. A host-medium entry explicitly mapped to lumen is refused.
  Whole-boundary isolation is still performed before either side is reopened.
- Removed `host.py.__getattr__`. `host_coupling.py` imports only the shared leaf module, and
  `host.py` statically re-exports `solve_bigg_host` / `run_bigg_host_microbe`. This removes the
  cycle workaround and gives mypy real callable types without ignores.

No maintenance-objective guard, `host_isolation_policy = all_boundary_uptake_v2`, or
`boundary_isolation_policy = boundary_reactions_v1` behavior was weakened.

Implementation commit: `83a1ebb round7 feat/host-two-interface: evidence-backed host sides`.

## Real-GEM classification evidence

Basis: downloaded by `python scripts/download_human_gems.py` and checksum-verified against
`data/gems/GEM_SOURCES.json`; measured with cobra 0.31.1 from the verified SBML bytes.

| Model | Compartments / annotation evidence found | Classified | Remained unclassified | Readiness |
| --- | --- | ---: | ---: | --- |
| Recon3D | Compartments `c,l,m,r,e,x,n,g,i`; all 1,560 exchanges use generic `e = extracellular space`. Reaction `sbo` and `bigg.reaction` annotations and metabolite `sbo` and `bigg.metabolite` annotations cover all 1,560 exchanges, but none of their values is side-specific. Side-bearing metadata occurs in 53 reaction names and 3 metabolite names. | 25 lumen + 31 blood = **56**. Examples include `EX_tacr_e` (`intestinal lumen`), `EX_1ohmdz_e` (`portal blood`), and `EX_M02560_e` (`Nefa-Blood-Pool-In`). Every row records the exact name field and rule. | **1,504**, zero conflicts. Generic `e` is insufficient to distinguish apical from basolateral. | Both sides detected, but classification is partial; `quantitative_coupling_ready=False`. |
| RECON1 | Compartments `c,e,l,m,r,g,n,x`; all 404 exchanges use generic `e = extracellular space`. Reaction and metabolite BiGG/SBO annotations cover all 404 exchanges, with no side-bearing values or names. | **0 lumen, 0 blood**. | **404**, zero conflicts. | Honest no-pair result; `has_lumen_blood_interfaces=False`, `quantitative_coupling_ready=False`. |

This is intentionally not a claim that Recon3D's 56 classified drug/pool exchanges form a complete
intestinal host model. The classifier exposes evidence; it does not manufacture physiology.

## Regression expectation note — prominent

`tests/test_recon3d_host.py` intentionally changed two expectations because the old assertions
encoded the suffix-only limitation:

- `has_lumen_blood_interfaces` changes from false to true because 25 lumen and 31 blood exchanges
  now have direct side-specific metadata evidence.
- the generic solve now reports 56 evidence-bearing interface flux rows instead of an empty list.

The same test still requires `quantitative_coupling_ready=False` because 1,504 exchanges remain
unclassified. No expectation in `tests/test_round6_*.py` was changed. Both round-6 host regression
files pass unchanged (25 tests total), including whole-boundary isolation, objective warnings,
case-preserving exchange resolution, and generic-GEM refusal in `solve_host`.

## Toy-host behavior proof

- `tests/test_host.py`: 21/21 existing tests pass with no file or expectation changes. These pin
  the synthetic two-interface outcomes, including acetate uptake 8, butyrate uptake 4, lumen and
  blood sign labels, maintenance behavior, FVA attribution, biomass scaling, and bound restoration.
- The no-model `classify_host_exchanges` entry point still uses the original suffix rule and
  `sign.convert` semantics; it now only adds evidence records.
- The host-map behavioral digest remains exactly
  `sha256:36059e16f8322762d50c8abfcbe6f2542f9410f7e30f6f5f2be2f2d10b425357`.
- `cmig golden verify-envelope` reports unchanged serialization for all 13 workflow kinds.

Together, the unchanged pinned toy expectations, unchanged matcher digest, and unchanged envelope
show that the established toy path and published hash inputs did not move.

## Verification log

Environment setup:

```text
UV_CACHE_DIR=/tmp/cmig-round7-t5-uv-cache uv sync --all-extras --group dev
→ installed/synced the existing 74-package environment; no dependency files changed
```

Owned host tests (the QtWebEngine flags avoid a macOS Mach-rendezvous denial in the restricted
sandbox; `--single-process` is test-runtime configuration only):

```text
QT_QPA_PLATFORM=minimal \
QTWEBENGINE_DISABLE_SANDBOX=1 \
QTWEBENGINE_CHROMIUM_FLAGS='--no-sandbox --disable-gpu --disable-software-rasterizer --single-process' \
UV_CACHE_DIR=/tmp/cmig-round7-t5-uv-cache \
uv run pytest -q \
  tests/test_host.py tests/test_host_ko_impact.py tests/test_host_map.py \
  tests/test_host_map_behavior_digest.py tests/test_host_map_workflow_manifest.py \
  tests/test_host_medium_strictness.py tests/test_host_view.py tests/test_recon3d_host.py \
  tests/test_round6_boundary_regressions.py tests/test_round6_human_gem_host.py \
  tests/test_round7_host_interface.py
→ 168 passed; two expected cobra warnings from deliberately infeasible toy-host tests
```

Quality and envelope gates:

```text
UV_CACHE_DIR=/tmp/cmig-round7-t5-uv-cache uv run ruff check .
→ All checks passed!

UV_CACHE_DIR=/tmp/cmig-round7-t5-uv-cache uv run cmig golden verify-envelope
→ envelope serialization unchanged for 13 workflow kinds
```

Typing for the edited host stack and its publication consumer:

```text
UV_CACHE_DIR=/tmp/cmig-round7-t5-uv-cache uv run mypy \
  cmig/core/host.py cmig/core/host_types.py cmig/core/host_coupling.py \
  cmig/core/host_map.py cmig/core/host_map_probe.py \
  cmig/service/publication_benchmark.py
→ Success: no issues found in 6 source files
```

The full `uv run mypy cmig` audit has **zero** `"object" not callable` findings at the five former
host re-export call sites. It still exits 1 with 12 unrelated findings in three files outside T5
ownership: `cmig/io/model_import.py`, `cmig/gui/builder.py`, and `cmig/cli/main.py` (optional-value /
collection typing). I did not modify those files.

Import order is also covered by the unchanged
`tests/test_round5_domain_accuracy.py::test_host_coupling_is_importable_as_the_first_import` plus
the new assertion that `host.__dict__` has no module `__getattr__`.

## Integration notes / risks for the coordinator

1. **T1-owned CLI serialization hook is still required.** Core parsing and host-map results support
   the structured optional `interface` field, but `cmig/cli/main.py::_load_host_interface_map`
   currently accepts string values only, and `_write_host_map_outputs` currently omits
   `interface` / `interface_evidence`. T1 should:
   - preserve legacy strings unchanged;
   - accept `{host_exchange, interface}` objects in `interface_map` and `needs_review`;
   - write the optional side/evidence columns to `host_exchange_map.csv`,
     `host_interface_map.json`, and `host_map_summary.json`;
   - pass the structured mapping through without flattening it before the host core.
   No new flag is needed; the existing `--interface-map` and `--accept-unreviewed-map` flow is the
   intended surface.
2. `host-generic`'s T1-owned explicit model payload currently omits
   `summary.interface_classification`; `host-benchmark` uses `summary.__dict__` and already exposes
   it. The coordinator may want T1 to surface the same audit consistently.
3. This intentional scientific behavior change needs an `## [Unreleased]` CHANGELOG entry, but
   `CHANGELOG.md` is outside T5 ownership. The entry should state that partial Recon3D interface
   evidence is now visible while completeness/readiness stays false.
4. Side-specific name matching is deliberately narrow and lexical. It recognizes explicit
   lumen/apical/blood/basolateral/portal/plasma/serum terms and leaves everything else unresolved.
   Reviewed overrides are the authority when metadata is absent or conflicting.
5. The separate side probe is not part of the hashed map behavior component, by design and per the
   no-run-hash-drift constraint. Once T1 serializes side/evidence into host-map artifacts, their
   existing `result_digest` will certify those answer bytes. Manifest/schema changes remain out of
   T5 scope.

## Proposals deliberately not implemented

- No edits to `cmig/cli/main.py`, workflow-manifest serialization, run-hash components, envelope
  fixtures, `CHANGELOG.md`, README, GUI, or service code; all are outside T5 ownership.
- No new CLI flag. The optional reviewed-map field fits the existing interface-map workflow.
- No blanket `e -> lumen` rule. That would turn RECON1 and most of Recon3D into silently guessed
  intestinal models.
- No attempt to assign all Recon3D exchanges from drug-oriented names or general biochemical
  annotations; 1,504 remain explicitly unclassified.
- No changes to round-6 regression expectations or to the maintenance/isolation provenance
  markers.
