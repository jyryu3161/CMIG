"""Phase-4 — workflow-level manifest + run_hash, and the frozen 11-component contract it must
not disturb.

Round-2 (R2-C F6) found that only `solve`/`solve-fixture` emitted a manifest: for every other
science command `inspect-run` returned `run_hash: null`, so the parameters that *determine* the
answer were recorded nowhere and a published result could not be re-derived. The fix is an
envelope, not an extension — these tests pin both halves of that:

1. **The 11-component contract is untouched.** `RUN_HASH_COMPONENTS` still has exactly its 11
   names in order, `DEFAULT_FLOAT_DECIMALS` is unchanged, and a known solve's run_hash is
   bit-identical to the value recorded before the workflow envelope existed. `golden verify`
   (SC-5) and the sweep run-hash cache depend on all three.
2. **The envelope is deterministic and complete.** Identical inputs give an identical workflow
   hash; changing *any* recorded parameter changes it; a missing determining component is an
   error rather than a silently weaker hash.

No solver required.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from cmig.core.manifest import (
    DEFAULT_FLOAT_DECIMALS,
    RUN_HASH_COMPONENTS,
    RunHashComponents,
    canonicalize_floats,
    compute_run_hash,
)
from cmig.core.workflow_manifest import (
    WORKFLOW_COMPONENT_VOCABULARY,
    WORKFLOW_HASH_COMPONENTS,
    WORKFLOW_MANIFEST_SCHEMA_VERSION,
    WorkflowManifestError,
    build_workflow_manifest,
    canonical_workflow_payload,
    compute_workflow_hash,
    mapping_checksum,
    medium_component,
    workflow_components_for,
    write_workflow_manifest,
)
from cmig.golden_fixture import SOLVER_VARIANTS

# ── the frozen contract ──────────────────────────────────────────────────────────

def test_run_hash_components_are_still_exactly_the_eleven_in_order():
    """[HASH-11]. golden verify and the sweep cache key off this tuple."""
    assert RUN_HASH_COMPONENTS == (
        "model_checksum",
        "medium_checksum",
        "member_set",
        "abundance",
        "bounds",
        "tradeoff_f",
        "solver_setting",
        "micom_version",
        "cmig_core_version",
        "namespace_mapping_decisions",
        "flux_normalization_method",
    )
    assert len(RUN_HASH_COMPONENTS) == 11


def test_default_float_decimals_is_unchanged():
    assert DEFAULT_FLOAT_DECIMALS == 6


def _known_components() -> RunHashComponents:
    """A fixed 11-component input whose hash must never move."""
    return RunHashComponents(
        model_checksum="micom_test_taxonomy_3",
        medium_checksum="micom_default_medium",
        member_set=["a", "b", "c"],
        abundance={"a": 0.333333, "b": 0.333333, "c": 0.333333},
        bounds={},
        tradeoff_f=0.5,
        solver_setting={"growth_solver": "gurobi", "flux_solver": "gurobi"},
        micom_version="0.39.0",
        cmig_core_version="0.1.0",
        namespace_mapping_decisions=[],
        flux_normalization_method="pfba",
    )


# Computed from the components above via the one canonical implementation. If the serialization,
# the component set, or the float rounding ever drifts, this fails — which is the entire point.
KNOWN_SOLVE_RUN_HASH = "cf3c73d97be5c3555d5d9e228c08e5088661cc6f1ba36fc7a333d2a9b2aaa633"

# The bundled 3-member fixture solve, as emitted by `cmig solve-fixture --solver gurobi`. Recorded
# independently by a round-2 evaluator before the workflow envelope existed, so it doubles as an
# outside check that phase 4 did not disturb the frozen contract.
GOLDEN_SOLVE_FIXTURE_RUN_HASH = (
    "29844e29103603324d118cc9a8b9ae4fa2a79070418860cfc2ed70095cef29ab"
)


def test_a_known_solve_run_hash_is_bit_identical():
    """The regression the phase-4 brief asks for: existing solve hashes must not move."""
    assert compute_run_hash(_known_components()) == KNOWN_SOLVE_RUN_HASH


def test_shipped_golden_fixture_run_hash_is_unchanged():
    """The gurobi golden fixture's stored run_hash is what `golden verify` (SC-5) gates on."""
    import json
    from pathlib import Path

    config = Path("fixtures/community_3_member/expected/gurobi/config.json")
    if not config.exists():                       # fixture not present in a trimmed checkout
        pytest.skip("gurobi golden fixture not present")
    assert json.loads(config.read_text())["run_hash"] == GOLDEN_SOLVE_FIXTURE_RUN_HASH


def test_every_shipped_golden_is_reproducible_from_its_own_recorded_components():
    """The invariant that was never checked: a golden must re-derive from what it stores.

    `test_shipped_golden_fixture_run_hash_is_unchanged` above pins the *gurobi* fixture only, and
    `golden verify` (SC-5) compares nothing but `micom_version`, so nothing in the suite ever
    re-derived a golden's hash from the components stored beside it. Each fixture records the
    `golden_decimals` it was captured under, so that is the contract each is checked against.
    """
    import json
    from pathlib import Path

    from cmig.core.manifest import RunHashComponents, compute_run_hash

    checked = 0
    for solver in ("gurobi", "osqp"):
        config = Path(f"fixtures/community_3_member/expected/{solver}/config.json")
        if not config.exists():                   # fixture not present in a trimmed checkout
            continue
        payload = json.loads(config.read_text())
        recomputed = compute_run_hash(
            RunHashComponents(**payload["components"]), decimals=payload["golden_decimals"]
        )
        assert recomputed == payload["run_hash"], (
            f"{solver} golden is internally inconsistent: its stored run_hash is not the hash of "
            f"its own stored components at its own golden_decimals"
        )
        checked += 1
    assert checked, "no golden fixture was available to check"


@pytest.mark.parametrize("solver", SOLVER_VARIANTS)
def test_each_shipped_golden_re_derives_its_own_run_hash_at_its_own_decimals(solver):
    """Every shipped golden must reproduce its own published hash from its own stored components.

    History, because this test replaced one that asserted the opposite. It was originally written
    to pin the osqp golden as *stale*: captured at `golden_decimals: 4` while the builder
    pre-rounded at 6, so `a422eb89…` was a stored artifact no code path reproduced, and its author
    made it fail "the moment someone recaptures" so that the decision would be visible. Track P3
    then repaired the fixture — correcting the three stored abundances to 4 decimals so it
    reproduces itself again, *without* moving the published hash — which made the staleness pin
    fail by design. Pinning a known-bad state is only useful until it is fixed; the invariant
    underneath it is permanent, so that is what is asserted now.

    Two things make this stronger than the state it replaced, both lessons of the round:

    * It is parametrized over `SOLVER_VARIANTS` rather than naming solvers inline. The osqp
      regression reached integration precisely because every hash pin in the suite was
      gurobi-only; a pin that covers "whichever solvers exist" cannot acquire that blind spot
      when a third variant is added.
    * A declared variant may not silently skip. `xfail`-by-absence is how a fixture stops being
      checked without anyone deciding to stop checking it.
    """
    import json
    from pathlib import Path

    from cmig.core.manifest import RunHashComponents, compute_run_hash

    config = Path(f"fixtures/community_3_member/expected/{solver}/config.json")
    if not config.exists():                       # trimmed checkout: no fixtures shipped at all
        available = [
            s for s in SOLVER_VARIANTS
            if Path(f"fixtures/community_3_member/expected/{s}/config.json").exists()
        ]
        assert not available, (
            f"{solver} is a declared solver variant but ships no golden, while {available} do — "
            "a variant that cannot be checked must not be declared"
        )
        pytest.skip("no golden fixtures present in this checkout")

    payload = json.loads(config.read_text())
    decimals = payload["golden_decimals"]
    components = RunHashComponents(**payload["components"])

    assert compute_run_hash(components, decimals=decimals) == payload["run_hash"], (
        f"the {solver} golden is internally inconsistent: its published run_hash is not the hash "
        f"of the components stored beside it at its own golden_decimals={decimals}. Either the "
        "components were edited without recapturing, or the hash was."
    )

    # Guard on the guard (CC-22's mandatory "would this catch deletion?" audit): the assertion
    # above must be discriminating, not satisfied by any components at all.
    perturbed = replace(components, tradeoff_f=float(components.tradeoff_f) + 0.25)
    assert compute_run_hash(perturbed, decimals=decimals) != payload["run_hash"], (
        "the re-derivation above is vacuous — a changed input produced the published hash"
    )


def test_solve_hash_is_stable_across_repeated_computation():
    assert compute_run_hash(_known_components()) == compute_run_hash(_known_components())


def test_solve_hash_still_responds_to_its_own_inputs():
    """Sanity: the pin above is not pinning a constant."""
    from dataclasses import replace

    changed = replace(_known_components(), tradeoff_f=0.6)
    assert compute_run_hash(changed) != KNOWN_SOLVE_RUN_HASH


def test_canonicalize_floats_is_the_same_normalization_the_solve_hash_uses():
    """The envelope shares one float rule with the solve hash rather than inventing a second.

    R5-P3 CC-4 changed *what* that shared rule is: a value that six decimals represent exactly
    still serializes as that number (which is why the frozen fixture hashes did not move), and
    only a value rounding would destroy keeps its exact form.
    """
    from cmig.core.manifest import RunHashComponents, canonical_payload

    assert canonicalize_floats(0.333333) == round(0.333333, DEFAULT_FLOAT_DECIMALS)

    # Same input, both code paths, same serialization.
    components = RunHashComponents(
        model_checksum="m", medium_checksum="d", member_set=["a"],
        abundance={}, bounds={"R": [0.0, 1.0 / 3.0]}, tradeoff_f=0.5,
        solver_setting={}, micom_version="0", cmig_core_version="0",
        namespace_mapping_decisions=[], flux_normalization_method="pfba",
    )
    assert canonical_payload(components)["bounds"]["R"][1] == canonicalize_floats(1.0 / 3.0)
    assert canonicalize_floats(float("nan")) == "NaN"
    assert canonicalize_floats(float("inf")) == "Infinity"
    assert canonicalize_floats(-0.0) == 0.0          # signed-zero collapse preserved


# ── per-kind contracts ───────────────────────────────────────────────────────────

def test_every_kind_declares_an_ordered_component_tuple():
    assert WORKFLOW_HASH_COMPONENTS, "at least one workflow kind must be declared"
    for kind, components in WORKFLOW_HASH_COMPONENTS.items():
        assert isinstance(components, tuple), f"{kind} must declare a tuple (ordered)"
        assert components[0] == "workflow_kind"
        assert len(set(components)) == len(components)
        assert set(components) <= WORKFLOW_COMPONENT_VOCABULARY


def test_the_science_commands_named_in_the_gap_all_have_a_kind():
    """Every command round-2 reported as run_hash=null must now be hashable."""
    for kind in (
        "model_pool_search", "multi_target_model_pool_search", "host_microbe_bigg",
        "host_search_bigg", "host_ko_impact", "gene_ko_search", "strain_growth",
        "abundance_impact", "sweep", "dfba", "model_quality",
    ):
        assert kind in WORKFLOW_HASH_COMPONENTS


def test_unknown_kind_is_an_error_not_an_empty_hash():
    with pytest.raises(WorkflowManifestError, match="unknown workflow kind"):
        workflow_components_for("not_a_workflow")


@pytest.mark.parametrize("kind", sorted(WORKFLOW_HASH_COMPONENTS))
def test_every_kind_records_versions_solver_models_and_medium(kind):
    """The determining basics R2-C F6 found missing, required of every kind."""
    components = WORKFLOW_HASH_COMPONENTS[kind]
    for required in (
        "cmig_core_version", "dependency_versions", "solver_setting",
        "model_checksum", "medium",
    ):
        assert required in components, f"{kind} must record {required}"


def test_host_kinds_record_host_model_and_biomass_basis():
    for kind in ("host_microbe_bigg", "host_search_bigg", "host_ko_impact"):
        assert "host_spec" in WORKFLOW_HASH_COMPONENTS[kind]
        assert "biomass_basis" in WORKFLOW_HASH_COMPONENTS[kind]


def test_knockout_kinds_record_the_ko_spec():
    for kind in ("gene_ko_search", "host_ko_impact"):
        assert "knockout_spec" in WORKFLOW_HASH_COMPONENTS[kind]


def test_search_kinds_record_target_and_search_policy():
    for kind in ("model_pool_search", "multi_target_model_pool_search"):
        assert "target_spec" in WORKFLOW_HASH_COMPONENTS[kind]
        assert "search_spec" in WORKFLOW_HASH_COMPONENTS[kind]
        assert "growth_fraction" in WORKFLOW_HASH_COMPONENTS[kind]


def test_the_two_commands_round_5_added_have_a_kind():
    """Round-4's report named these as the two coverage gaps that mattered."""
    assert "host_map" in WORKFLOW_HASH_COMPONENTS
    assert "publication_benchmark" in WORKFLOW_HASH_COMPONENTS


def test_host_map_records_the_host_the_pool_and_the_matching_policy():
    """host-map never solves; the host model, the pool and the policy are all that determine it."""
    components = WORKFLOW_HASH_COMPONENTS["host_map"]
    assert "host_spec" in components
    assert "map_spec" in components
    assert "model_checksum" in components


def test_a_bundling_kind_records_what_it_bundled():
    """A bundle that recorded only its own arguments would certify runs it never saw."""
    assert "bundle_spec" in WORKFLOW_HASH_COMPONENTS["publication_benchmark"]


def test_host_spec_has_one_shape_shared_by_every_kind_that_records_it():
    """Five kinds hash `host_spec`; a second literal would eventually disagree with the first."""
    from cmig.core.workflow_manifest import host_spec_component

    keys = set(host_spec_component(host_model=None, host_model_checksum=None))
    assert keys == {
        "host_model", "host_model_checksum", "host_objective",
        "host_medium", "host_medium_checksum",
        "microbe_medium", "microbe_medium_checksum",
        "interface_map", "interface_map_checksum",
        "exchange_suffix", "exclude_metabolites",
        "include_currency_metabolites", "keep_host_uptake",
    }
    for kind in (
        "host_microbe_bigg", "host_search_bigg", "host_ko_impact", "host_map",
        "publication_benchmark",
    ):
        assert "host_spec" in WORKFLOW_HASH_COMPONENTS[kind]


def test_the_same_file_at_a_different_path_is_the_same_host_spec():
    """Round-5 P2: identical bytes reached by a different path fingerprinted as a different run.

    Every path in `host_spec` has a checksum companion that already pins the content, so hashing
    the path made the reader's directory layout a scientific input: re-running a published
    `host-map` with an absolute path, or from another working directory, produced a different
    `run_hash` from identical science and looked like a failed reproduction.
    """
    from cmig.core.workflow_manifest import host_spec_component

    relative = host_spec_component(
        host_model="models/host.xml", host_model_checksum="sha256:1",
        host_medium="diet/med.csv", host_medium_checksum="sha256:2",
        microbe_medium="diet/mic.csv", microbe_medium_checksum="sha256:3",
        interface_map="maps/iface.json", interface_map_checksum="sha256:4",
    )
    absolute = host_spec_component(
        host_model="/elsewhere/models/host.xml", host_model_checksum="sha256:1",
        host_medium="/elsewhere/diet/med.csv", host_medium_checksum="sha256:2",
        microbe_medium="/elsewhere/diet/mic.csv", microbe_medium_checksum="sha256:3",
        interface_map="/elsewhere/maps/iface.json", interface_map_checksum="sha256:4",
    )
    assert relative == absolute
    assert relative["host_model"] == "host.xml"
    # …but different bytes are still a different run: the checksum, not the path, carries identity.
    other_bytes = host_spec_component(
        host_model="models/host.xml", host_model_checksum="sha256:different",
    )
    assert other_bytes != relative


def test_host_spec_component_records_an_unexposed_option_rather_than_dropping_it():
    """An absent key and an inert default are different hashes; only the latter is honest."""
    from cmig.core.workflow_manifest import host_spec_component

    minimal = host_spec_component(host_model="h.xml", host_model_checksum="sha256:1")
    assert minimal["keep_host_uptake"] is False
    assert minimal["exclude_metabolites"] == []
    assert minimal["interface_map_checksum"] is None
    # ... and it is order-insensitive where order is not meaningful.
    assert host_spec_component(
        host_model="h.xml", host_model_checksum="sha256:1", exclude_metabolites=["b", "a"],
    )["exclude_metabolites"] == ["a", "b"]


def test_bundle_component_hashes_child_hashes_not_just_child_kinds():
    """The documented decision: the bundle hash includes what it certified."""
    from cmig.core.workflow_manifest import bundle_component

    one = bundle_component([{"kind": "dfba", "artifacts_dir": "dfba", "run_hash": "a" * 64}])
    other = bundle_component([{"kind": "dfba", "artifacts_dir": "dfba", "run_hash": "b" * 64}])
    assert one["bundle_hash_includes_child_hashes"] is True
    assert one != other


def test_kinds_wrapping_a_community_solve_embed_its_hash():
    """[HASH-SINGLE]: the 11-component hash is carried, never recomputed or extended."""
    for kind in ("strain_growth", "host_microbe_bigg"):
        assert "solve_run_hash" in WORKFLOW_HASH_COMPONENTS[kind]


def test_flux_normalization_is_recorded_where_a_solve_happens():
    """Phase-3 made this the normalization ACTUALLY used; it must reach the hash."""
    for kind in ("strain_growth", "abundance_impact", "host_microbe_bigg"):
        assert "flux_normalization_method" in WORKFLOW_HASH_COMPONENTS[kind]


# ── hashing behaviour ────────────────────────────────────────────────────────────

def _dfba_components(**overrides):
    base = {
        "workflow_kind": "dfba",
        "cmig_core_version": "0.1.0",
        "dependency_versions": {"micom": "0.39.0", "cobra": "0.31.1"},
        "solver_setting": {"solver": "gurobi"},
        "model_checksum": "sha256:abc",
        "medium": {"checksum": "m", "source": None},
        "dfba_spec": {"dt": 0.1, "t_end": 10.0, "km": 0.01},
    }
    base.update(overrides)
    return base


def test_identical_inputs_give_an_identical_hash():
    assert compute_workflow_hash("dfba", _dfba_components()) == compute_workflow_hash(
        "dfba", _dfba_components()
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cmig_core_version", "9.9.9"),
        ("dependency_versions", {"micom": "0.40.0", "cobra": "0.31.1"}),
        ("solver_setting", {"solver": "osqp"}),
        ("model_checksum", "sha256:different"),
        ("medium", {"checksum": "other", "source": None}),
        ("dfba_spec", {"dt": 0.2, "t_end": 10.0, "km": 0.01}),
    ],
)
def test_changing_any_recorded_parameter_changes_the_hash(field, value):
    """Both directions are required: same in → same hash, any change → different hash."""
    baseline = compute_workflow_hash("dfba", _dfba_components())
    assert compute_workflow_hash("dfba", _dfba_components(**{field: value})) != baseline


def test_two_kinds_cannot_collide_on_one_hash():
    """Every tuple leads with workflow_kind, so distinct kinds hash differently."""
    shared = {
        "cmig_core_version": "0.1.0",
        "dependency_versions": {},
        "solver_setting": {},
        "model_checksum": "c",
        "medium": {},
    }
    dfba = compute_workflow_hash("dfba", {**shared, "workflow_kind": "dfba", "dfba_spec": {}})
    quality = compute_workflow_hash(
        "model_quality", {**shared, "workflow_kind": "model_quality", "quality_spec": {}}
    )
    assert dfba != quality


def test_declared_component_order_is_part_of_the_hash():
    """Serializing as ordered pairs, not a dict, makes a reordered tuple a real change."""
    payload = canonical_workflow_payload("dfba", _dfba_components())
    assert [name for name, _value in payload] == list(workflow_components_for("dfba"))


def test_a_missing_determining_component_is_rejected():
    incomplete = _dfba_components()
    del incomplete["dfba_spec"]
    with pytest.raises(WorkflowManifestError, match="missing determining components"):
        compute_workflow_hash("dfba", incomplete)


def test_a_component_outside_the_contract_is_rejected():
    """Silently ignoring an extra would let a caller think it was hashed."""
    with pytest.raises(WorkflowManifestError, match="outside its contract"):
        compute_workflow_hash("dfba", _dfba_components(quality_spec={"x": 1}))


def test_kind_mismatch_between_argument_and_component_is_rejected():
    with pytest.raises(WorkflowManifestError, match="!= manifest kind"):
        compute_workflow_hash("dfba", _dfba_components(workflow_kind="sweep"))


def test_a_determining_input_below_the_rounding_floor_still_moves_the_hash():
    """Contract change, R5-P3 CC-4 (was: "float noise below the rounding floor does not move the
    hash").

    ``dfba_spec.dt`` is a user-supplied parameter that determines the answer, not a number that
    came out of a solve, so two different values of it are two different runs. Under the old rule
    *every* input below 5e-7 collapsed onto 0.0, which meant a solver tolerance of 1e-7 and one of
    4e-7 shared a run_hash — "same hash" no longer implied "same inputs", which is the one claim
    the manifest exists to make. Solver noise is now absorbed where it enters (the CLI rounds
    solve-derived abundances before they become components) instead of by blurring every input.
    """
    baseline = compute_workflow_hash("dfba", _dfba_components())
    nudged = _dfba_components(dfba_spec={"dt": 0.1 + 1e-12, "t_end": 10.0, "km": 0.01})
    assert compute_workflow_hash("dfba", nudged) != baseline

    # An identical input is of course still identical.
    assert compute_workflow_hash("dfba", _dfba_components()) == baseline


def test_non_finite_floats_serialize_deterministically():
    """NaN/inf appear in real cobra bounds; they must not make the hash non-deterministic."""
    components = _dfba_components(dfba_spec={"vmax": float("inf"), "km": float("nan")})
    assert compute_workflow_hash("dfba", components) == compute_workflow_hash("dfba", components)


# ── the written manifest ─────────────────────────────────────────────────────────

def test_manifest_payload_is_self_describing(tmp_path):
    run_hash = write_workflow_manifest(
        tmp_path, "dfba", _dfba_components(),
        status="ok", artifacts=["dfba_summary.json"], summary={"n_steps": 3},
    )
    payload = json.loads((tmp_path / "manifest.json").read_text())
    assert payload["manifest_schema_version"] == WORKFLOW_MANIFEST_SCHEMA_VERSION
    assert payload["manifest_scope"] == "workflow"
    assert payload["workflow_kind"] == "dfba"
    assert payload["run_hash"] == run_hash
    # A reader must be able to see WHAT was hashed, and in what order, from the file alone.
    assert payload["hash_components"] == list(workflow_components_for("dfba"))
    assert [name for name, _v in payload["components"]] == payload["hash_components"]
    assert payload["status"] == "ok"
    assert payload["summary"] == {"n_steps": 3}


def test_env_lock_is_recorded_but_excluded_from_the_hash():
    """[HASH-ENVLOCK], same rule the solve manifest follows."""
    manifest = build_workflow_manifest("dfba", _dfba_components())
    assert manifest.env_lock and manifest.env_lock.startswith("sha256:")
    assert "env_lock" not in [name for name, _v in manifest.to_payload()["components"]]
    assert manifest.run_hash == compute_workflow_hash("dfba", _dfba_components())


def test_rewriting_the_same_run_is_byte_stable(tmp_path):
    first = write_workflow_manifest(tmp_path, "dfba", _dfba_components())
    text_first = (tmp_path / "manifest.json").read_text()
    second = write_workflow_manifest(tmp_path, "dfba", _dfba_components())
    assert first == second
    # env_lock and platform are derived, not timestamped, so the file itself is reproducible.
    assert (tmp_path / "manifest.json").read_text() == text_first


# ── component builders ───────────────────────────────────────────────────────────

def test_medium_component_records_the_namespace_bridge():
    """Phase-3's `_m`/`_e` bridge changes what was actually applied, so it belongs in the hash."""
    component = medium_component(
        "diet.csv", "medium:abc",
        namespace_bridge={"unavailable_per_member": {"iYO844": ["o2"]}},
        allow_unknown=True,
    )
    assert component["source"] == "diet.csv"
    assert component["checksum"] == "medium:abc"
    assert component["allow_unknown_medium"] is True
    assert component["namespace_bridge"]["unavailable_per_member"] == {"iYO844": ["o2"]}


def test_a_different_bridge_decision_changes_the_hash():
    def strain(bridge):
        return {
            "workflow_kind": "strain_growth",
            "cmig_core_version": "0.1.0",
            "dependency_versions": {},
            "solver_setting": {"solver": "gurobi"},
            "model_checksum": "c",
            "medium": medium_component(None, "micom_default_medium", namespace_bridge=bridge),
            "abundances": {"a": 0.5},
            "tradeoff_f": 0.5,
            "flux_normalization_method": "pfba",
            "solve_run_hash": "abc",
        }

    controlled = compute_workflow_hash("strain_growth", strain({"single_medium_mode": "community"}))
    native = compute_workflow_hash(
        "strain_growth", strain({"single_medium_mode": "model_default"})
    )
    assert controlled != native


def test_mapping_checksum_is_order_independent_and_none_safe():
    assert mapping_checksum(None) is None
    assert mapping_checksum({"a": "1", "b": "2"}) == mapping_checksum({"b": "2", "a": "1"})
    assert mapping_checksum({"a": "1"}) != mapping_checksum({"a": "2"})
