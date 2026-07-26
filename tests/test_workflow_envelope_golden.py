"""Round-5 P4 — the missing drift gate for the workflow-envelope serialization.

`golden verify` (SC-5) pins the solve side: it catches MICOM moving underneath the frozen
11-component `community_solve` hash. Phase 4's report named the gap on the other side — nothing
would catch a change to `cmig.core.workflow_manifest`'s serialization silently rewriting every
published workflow `run_hash`. That is a P0-shaped failure: the same inputs would produce a
different fingerprint with nothing announcing it, so a reader holding a published hash could not
reproduce the run and would not be told why.

These tests pin the envelope itself, not one workflow's inputs: a golden
`(kind, canonical_input_dict) -> (canonical_json, hash)` for every registered kind. Adding a
component, reordering a tuple, changing the canonical JSON form, or changing the float
normalization all break it loudly, with instructions for re-blessing.

No solver required.
"""

from __future__ import annotations

import json

import pytest

from cmig.core.manifest import DEFAULT_FLOAT_DECIMALS
from cmig.core.workflow_envelope_golden import (
    ENVELOPE_GOLDEN_PATH,
    REBLESS_COMMAND,
    EnvelopeDrift,
    assert_envelope_golden,
    build_golden_payload,
    float_probe_components,
    golden_components,
    load_golden,
    verify_envelope_golden,
    write_golden,
)
from cmig.core.workflow_manifest import (
    WORKFLOW_HASH_COMPONENTS,
    WORKFLOW_MANIFEST_SCHEMA_VERSION,
    canonical_workflow_json,
    compute_workflow_hash,
    workflow_components_for,
)

# ── the gate, as it must stand on a clean tree ───────────────────────────────────

def test_the_envelope_golden_ships_inside_the_package():
    """`fixtures/` is excluded from every distribution, so the gate must not live there.

    A gate that silently skips on a trimmed checkout is not a gate.
    """
    assert ENVELOPE_GOLDEN_PATH.exists(), (
        f"workflow-envelope golden missing; capture it with `{REBLESS_COMMAND}`"
    )
    assert ENVELOPE_GOLDEN_PATH.parent.name == "core"
    assert ENVELOPE_GOLDEN_PATH.parts[-3] == "cmig"


def test_the_envelope_serialization_has_not_drifted():
    """The gate itself. If this fails, published workflow run_hashes have moved."""
    assert_envelope_golden()


def test_every_currently_declared_kind_is_covered():
    """Not required by the gate (a new kind must not break a build), but it must be blessed."""
    report = verify_envelope_golden()
    assert report["uncovered"] == [], (
        f"workflow kinds declared but not covered by the envelope golden: {report['uncovered']}. "
        f"Re-bless with `{REBLESS_COMMAND}` so they are protected."
    )


def test_the_gate_reports_every_kind_as_checked():
    report = verify_envelope_golden()
    assert sorted(report["checked"]) == sorted(WORKFLOW_HASH_COMPONENTS)
    assert report["ok"] is True
    assert report["removed"] == []
    assert report["float_normalization_probe_ok"] is True


def test_the_golden_file_records_what_it_pinned():
    """A reader must see the component tuple and the exact serialized form, not only a hash."""
    golden = load_golden()
    assert golden["float_decimals"] == DEFAULT_FLOAT_DECIMALS
    assert golden["workflow_manifest_schema_version"] == WORKFLOW_MANIFEST_SCHEMA_VERSION
    for kind, entry in golden["kinds"].items():
        assert entry["components"] == list(workflow_components_for(kind))
        assert [name for name, _v in json.loads(entry["canonical_json"])] == entry["components"]
        assert len(entry["hash"]) == 64


def test_the_stored_hash_is_the_hash_of_the_stored_input():
    """The stored input is fed back through the real envelope — no second implementation."""
    for kind, entry in load_golden()["kinds"].items():
        assert compute_workflow_hash(kind, dict(entry["input"])) == entry["hash"]
        assert canonical_workflow_json(kind, dict(entry["input"])) == entry["canonical_json"]


def test_rebless_on_a_clean_tree_reproduces_the_committed_file(tmp_path):
    """Re-blessing must be a no-op when nothing changed, or the gate would churn."""
    regenerated = tmp_path / "envelope_golden.json"
    write_golden(regenerated)
    assert regenerated.read_text() == ENVELOPE_GOLDEN_PATH.read_text()


def test_the_golden_inputs_do_not_depend_on_the_running_environment():
    """A version bump is not envelope drift; only a serialization change is."""
    from cmig import CMIG_CORE_VERSION

    for entry in load_golden()["kinds"].values():
        assert entry["input"]["cmig_core_version"] == "0.0.0-envelope-golden"
        assert entry["input"]["cmig_core_version"] != CMIG_CORE_VERSION
        versions = entry["input"]["dependency_versions"]
        assert set(versions.values()) == {"0.0.0-golden"}


# ── the gate actually fires ──────────────────────────────────────────────────────
# Each case perturbs the golden the way a corresponding source change would, and asserts the gate
# reports it. Written against a temp copy so the committed golden is never touched.

def _golden_copy(tmp_path, mutate=None):
    payload = build_golden_payload()
    if mutate is not None:
        mutate(payload)
    path = tmp_path / "envelope_golden.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def test_a_changed_hash_is_reported_as_drift(tmp_path):
    """What a changed canonical JSON form would look like from the gate's side."""
    def mutate(payload):
        payload["kinds"]["dfba"]["hash"] = "0" * 64

    report = verify_envelope_golden(_golden_copy(tmp_path, mutate))
    assert report["ok"] is False
    assert [item["kind"] for item in report["drifted"]] == ["dfba"]
    assert report["drifted"][0]["reason"] == "serialization changed"


def test_a_changed_serialization_names_the_first_differing_character(tmp_path):
    def mutate(payload):
        entry = payload["kinds"]["dfba"]
        entry["canonical_json"] = entry["canonical_json"].replace("dfba_spec", "dfbaXspec", 1)
        entry["hash"] = "1" * 64

    with pytest.raises(EnvelopeDrift) as excinfo:
        assert_envelope_golden(_golden_copy(tmp_path, mutate))
    message = str(excinfo.value)
    assert "first difference at character" in message
    assert REBLESS_COMMAND in message


def test_adding_a_component_to_an_existing_kind_breaks_the_gate(tmp_path):
    """The stored input is checked against the *declared* tuple, so a widened contract fails."""
    def mutate(payload):
        del payload["kinds"]["dfba"]["input"]["dfba_spec"]

    with pytest.raises(EnvelopeDrift, match="missing determining components"):
        assert_envelope_golden(_golden_copy(tmp_path, mutate))


def test_component_fixtures_are_built_by_their_builders_not_transcribed():
    """Round-5 P2: a transcribed literal makes the gate certify a *copy* of the contract.

    Changing `host_spec_component` to hash a file's name rather than its path moved real published
    hashes for five kinds, and the gate stayed silent because its `host_spec` fixture was a
    hand-written dict the builder never touched. Each fixture below is now the builder's own
    output for synthetic inputs, so a change to the builder's shape *or* its normalization is
    drift.
    """
    from cmig.core.workflow_envelope_golden import _COMPONENT_FIXTURES, BUILDER_DERIVED_FIXTURES
    from cmig.core.workflow_manifest import (
        bundle_component,
        host_spec_component,
        medium_component,
    )

    assert _COMPONENT_FIXTURES["medium"] == medium_component(
        "golden/diet.csv",
        "sha256:1111111111111111111111111111111111111111111111111111111111111111",
        namespace_bridge={"unavailable_per_member": {"m_b": ["o2_e"], "m_a": []}},
    )
    # The builder normalizes: the fixture is built from an unsorted list and a bare path, so if a
    # builder stopped sorting or stopped taking the basename, the fixture — and the gate — moves.
    assert _COMPONENT_FIXTURES["host_spec"]["exclude_metabolites"] == ["co2", "h", "h2o"]
    assert _COMPONENT_FIXTURES["host_spec"]["host_model"] == "host.xml"
    assert set(_COMPONENT_FIXTURES["host_spec"]) == set(
        host_spec_component(host_model=None, host_model_checksum=None)
    )
    assert _COMPONENT_FIXTURES["bundle_spec"]["children"] == bundle_component([
        {"kind": "community_solve", "run_hash": "aaaa", "artifacts_dir": "community",
         "status": "ok"},
        {"kind": "model_quality", "run_hash": None, "artifacts_dir": "model_quality",
         "status": "degraded"},
    ])["children"]
    # map_spec keeps the builder's shape while its live values are synthetic, so a new policy key
    # cannot appear without the gate noticing.
    from cmig.core.host_map import host_map_policy

    assert set(_COMPONENT_FIXTURES["map_spec"]) == set(host_map_policy())
    assert _COMPONENT_FIXTURES["map_spec"]["match_behavior"]["digest"] == "sha256:4444"
    assert BUILDER_DERIVED_FIXTURES == {"medium", "host_spec", "map_spec", "bundle_spec"}


def test_editing_a_component_fixture_without_reblessing_breaks_the_gate(monkeypatch):
    """Round-5: a changed fixture *value* used to be invisible, so the golden drifted in silence.

    Verification re-derives from the stored copy of the input, so growing a component a new sub-key
    — which is what happened when `map_spec` gained `match_behavior` — left the golden pinning a
    shape the code no longer produces while the gate still reported 13/13 OK. The stored input is
    only a contract check while it is still the declared fixture.
    """
    import cmig.core.workflow_envelope_golden as module

    grown = dict(module._COMPONENT_FIXTURES["map_spec"])
    grown["match_behavior"] = {"probe_version": "golden", "digest": "sha256:a-new-sub-key"}
    monkeypatch.setitem(module._COMPONENT_FIXTURES, "map_spec", grown)

    # The shipped golden is internally consistent — its stored hash is still the hash of its
    # stored input — so only the fixture comparison can catch this.
    report = verify_envelope_golden()
    assert [item["kind"] for item in report["drifted"]] == ["host_map"]
    with pytest.raises(EnvelopeDrift, match="no longer matches the declared component fixture"):
        assert_envelope_golden()


def test_narrowing_a_kinds_contract_breaks_the_gate(tmp_path):
    """Dropping a component from a kind is the dangerous direction: a silently weaker hash."""
    def mutate(payload):
        payload["kinds"]["dfba"]["input"]["quality_spec"] = {"x": 1}

    with pytest.raises(EnvelopeDrift, match="outside its contract"):
        assert_envelope_golden(_golden_copy(tmp_path, mutate))


def test_removing_a_declared_kind_breaks_the_gate(tmp_path):
    """A kind that disappears orphans every hash published under it."""
    def mutate(payload):
        payload["kinds"]["not_a_real_kind"] = payload["kinds"]["dfba"]

    with pytest.raises(EnvelopeDrift, match="no longer declared"):
        assert_envelope_golden(_golden_copy(tmp_path, mutate))


def test_adding_a_new_kind_does_not_break_the_gate(tmp_path):
    """Required by design: a new kind is unprotected, not a build failure."""
    def mutate(payload):
        payload["kinds"].pop("dfba")

    path = _golden_copy(tmp_path, mutate)
    report = verify_envelope_golden(path)
    assert report["ok"] is True                    # the remaining kinds still verify
    assert report["uncovered"] == ["dfba"]         # ... and the gap is reported
    assert_envelope_golden(path)


def test_a_changed_float_normalization_breaks_the_gate(tmp_path):
    """NaN / ±inf / -0.0 cannot round-trip through JSON, so they are probed separately."""
    def mutate(payload):
        payload["float_normalization_probe"]["hash"] = "2" * 64

    with pytest.raises(EnvelopeDrift, match="float normalization"):
        assert_envelope_golden(_golden_copy(tmp_path, mutate))


def test_the_float_probe_covers_the_cases_json_cannot_store():
    """Pin what the probe is for, so it cannot be quietly reduced to finite floats."""
    spec = float_probe_components()["dfba_spec"]
    assert spec["nan"] != spec["nan"]                 # NaN
    assert spec["pos_inf"] == float("inf")
    assert spec["neg_inf"] == float("-inf")
    assert str(spec["negative_zero"]) == "-0.0"
    serialized = json.loads(
        canonical_workflow_json("dfba", float_probe_components())
    )
    values = dict(serialized)["dfba_spec"]
    assert values["nan"] == "NaN"
    assert values["pos_inf"] == "Infinity"
    assert values["neg_inf"] == "-Infinity"
    assert values["negative_zero"] == 0.0             # signed-zero collapse
    assert values["below_rounding_floor"] == 0.1      # noise under the 6-decimal floor


def test_a_missing_golden_file_is_an_error_not_a_skip(tmp_path):
    with pytest.raises(EnvelopeDrift, match="golden not found"):
        assert_envelope_golden(tmp_path / "absent.json")


# ── the gate is wired into the CLI next to `golden verify` ───────────────────────

def test_golden_verify_envelope_exits_zero_on_a_clean_tree(capsys):
    from cmig.cli.main import main

    assert main(["golden", "verify-envelope"]) == 0
    out = capsys.readouterr().out
    assert "Workflow-envelope serialization gate" in out
    for kind in WORKFLOW_HASH_COMPONENTS:
        assert f"[OK ] {kind}" in out


@pytest.mark.parametrize("kind", sorted(WORKFLOW_HASH_COMPONENTS))
def test_the_golden_input_for_a_kind_is_exactly_its_declared_components(kind):
    assert sorted(golden_components(kind)) == sorted(workflow_components_for(kind))
    assert golden_components(kind)["workflow_kind"] == kind
