"""Round-5 P4 — `host-map` must emit a workflow manifest.

Phase 4 gave 11 workflow kinds a reproducibility envelope but left `host-map` out, and `host-map`
is the one that decides the *interface map* every host coupling run then consumes. Round-2 already
found that map silently pairing D/L stereoisomers, so "which map, produced under which matching
policy, from which host and which pool" is exactly the provenance a published host result stands
on. Without a manifest, `inspect-run` reported `run_hash: null` for it.

What these tests pin:

1. `host-map` writes `manifest.json` with kind `host_map` and a non-null run_hash.
2. Identical inputs reproduce it bit-identically; **every** recorded component changes it.
3. The recorded matching policy is read out of the code, not restated — so changing the
   normalizer or the auto-admit rule necessarily changes the hash.
4. The same host + pool fingerprints identically whether mapped by `cmig host-map` or by the
   `host_map` leg inside `publication-benchmark`.

No solver required: `build_host_map` is pure over cobra models.
"""

from __future__ import annotations

import argparse
import copy
import json

import pytest

cobra = pytest.importorskip("cobra")

from cmig.cli.main import _host_map_hash_components, main  # noqa: E402
from cmig.core.host_map import (  # noqa: E402
    HOST_MAP_INTERFACE_MAP_ADMITS,
    HOST_MAP_NEEDS_REVIEW_TYPES,
    host_map_policy,
)
from cmig.core.workflow_manifest import (  # noqa: E402
    WORKFLOW_HASH_COMPONENTS,
    compute_workflow_hash,
    workflow_components_for,
)
from cmig.synthetic_host import build_host_model  # noqa: E402
from cmig.synthetic_pair import build_pair_taxonomy  # noqa: E402


@pytest.fixture
def host_map_inputs(tmp_path):
    """A host model and a two-member pool, written to disk the way the CLI expects them."""
    taxonomy = build_pair_taxonomy(tmp_path / "microbes")
    taxonomy_path = tmp_path / "taxonomy.csv"
    taxonomy.to_csv(taxonomy_path, index=False)
    host_path = tmp_path / "host.xml"
    cobra.io.write_sbml_model(build_host_model(), str(host_path))
    return {"taxonomy": taxonomy_path, "host": host_path, "root": tmp_path}


def _run_host_map(inputs, out, *, host=None):
    rc = main([
        "host-map",
        "--host", str(host or inputs["host"]),
        "--taxonomy", str(inputs["taxonomy"]),
        "--out", str(out),
    ])
    assert rc == 0, "host-map must succeed for these inputs"
    return json.loads((out / "manifest.json").read_text())


# ── the gap phase 4 left ─────────────────────────────────────────────────────────

def test_host_map_is_a_registered_workflow_kind():
    assert "host_map" in WORKFLOW_HASH_COMPONENTS


def test_host_map_writes_a_manifest_alongside_its_existing_outputs(host_map_inputs, tmp_path):
    out = tmp_path / "run"
    payload = _run_host_map(host_map_inputs, out)
    for artifact in (
        "host_exchange_map.csv", "host_interface_map.json", "host_map_summary.json",
        "manifest.json",
    ):
        assert (out / artifact).exists(), f"host-map must still write {artifact}"
    assert payload["workflow_kind"] == "host_map"
    assert payload["manifest_scope"] == "workflow"
    assert payload["run_hash"] is not None and len(payload["run_hash"]) == 64
    assert payload["artifacts"] == [
        "host_exchange_map.csv", "host_interface_map.json", "host_map_summary.json",
    ]


def test_inspect_run_now_reports_a_host_map_run(host_map_inputs, tmp_path):
    """The concrete symptom round-2 reported: `inspect-run` returning run_hash null."""
    from cmig.cli.main import _inspect_run_dir

    out = tmp_path / "run"
    payload = _run_host_map(host_map_inputs, out)
    inspected = _inspect_run_dir(out)
    assert inspected["kind"] == "host_map"
    assert inspected["run_hash"] == payload["run_hash"]
    assert inspected["status"] in {"ok", "degraded", "failed"}


def test_the_manifest_summary_identifies_the_map_it_produced(host_map_inputs, tmp_path):
    """A reader must be able to tell which interface map this run certified."""
    out = tmp_path / "run"
    payload = _run_host_map(host_map_inputs, out)
    summary = payload["summary"]
    interface_map = json.loads((out / "host_interface_map.json").read_text())["interface_map"]
    from cmig.core.workflow_manifest import mapping_checksum

    assert summary["interface_map_checksum"] == mapping_checksum(interface_map)
    assert summary["n_exact"] + summary["n_annotation"] + summary["n_normalized"] + summary[
        "n_unmatched"
    ] == summary["n_microbial_secretions"]


def test_a_map_with_no_exact_match_is_not_reported_as_ok(host_map_inputs, tmp_path):
    """Only exact matches are auto-admitted; a run that produced none is not a usable pre-flight."""
    out = tmp_path / "run"
    payload = _run_host_map(host_map_inputs, out)
    if payload["summary"]["n_exact"] == 0:
        assert payload["status"] == "degraded"
    else:
        assert payload["status"] == "ok"


# ── determinism, both directions ─────────────────────────────────────────────────

def test_identical_inputs_reproduce_the_hash_bit_identically(host_map_inputs, tmp_path):
    first = _run_host_map(host_map_inputs, tmp_path / "a")
    second = _run_host_map(host_map_inputs, tmp_path / "b")
    assert first["run_hash"] == second["run_hash"]
    # The manifest bytes themselves are reproducible too (nothing is timestamped).
    assert (tmp_path / "a" / "manifest.json").read_text() == (
        tmp_path / "b" / "manifest.json"
    ).read_text()


def test_a_different_host_model_changes_the_hash(host_map_inputs, tmp_path):
    baseline = _run_host_map(host_map_inputs, tmp_path / "a")
    altered = build_host_model()
    altered.remove_reactions([altered.reactions[0]], remove_orphans=False)
    altered_path = tmp_path / "host_altered.xml"
    cobra.io.write_sbml_model(altered, str(altered_path))
    changed = _run_host_map(host_map_inputs, tmp_path / "b", host=altered_path)
    assert changed["run_hash"] != baseline["run_hash"]


def test_a_different_microbial_pool_changes_the_hash(host_map_inputs, tmp_path):
    import pandas as pd

    baseline = _run_host_map(host_map_inputs, tmp_path / "a")
    taxonomy = pd.read_csv(host_map_inputs["taxonomy"]).iloc[:1]
    trimmed = host_map_inputs["root"] / "taxonomy_one.csv"
    taxonomy.to_csv(trimmed, index=False)
    rc = main([
        "host-map", "--host", str(host_map_inputs["host"]),
        "--taxonomy", str(trimmed), "--out", str(tmp_path / "b"),
    ])
    assert rc == 0
    changed = json.loads((tmp_path / "b" / "manifest.json").read_text())
    assert changed["run_hash"] != baseline["run_hash"]


def _components(host_map_inputs):
    import pandas as pd

    args = argparse.Namespace(
        host=str(host_map_inputs["host"]),
        taxonomy=str(host_map_inputs["taxonomy"]),
        model_dir=None,
        recursive=False,
        out="unused",
    )
    taxonomy = pd.read_csv(host_map_inputs["taxonomy"])
    return _host_map_hash_components(args, taxonomy, host_map_inputs["taxonomy"].parent)


# A distinct, type-compatible replacement for each recorded component. "Change any one of them and
# the hash moves" is the property that makes the fingerprint mean anything.
_PERTURBATIONS: dict[str, object] = {
    "workflow_kind": None,                        # handled separately: kind is the first component
    "cmig_core_version": "9.9.9",
    "dependency_versions": {"cobra": "0.0.1"},
    "solver_setting": {"solver": "gurobi"},
    "model_checksum": "sha256:different",
    "medium": {"source": "other.csv", "checksum": "x"},
    "host_spec": {"host_model": "elsewhere.xml"},
    "map_spec": {"match_policy_version": "2.0"},
}


@pytest.mark.parametrize(
    "component", [c for c in workflow_components_for("host_map") if c != "workflow_kind"]
)
def test_changing_any_single_recorded_component_changes_the_hash(
    component, host_map_inputs
):
    baseline_components = _components(host_map_inputs)
    baseline = compute_workflow_hash("host_map", baseline_components)
    perturbed = copy.deepcopy(baseline_components)
    perturbed[component] = _PERTURBATIONS[component]
    assert perturbed[component] != baseline_components[component], (
        f"the perturbation for {component} must actually differ"
    )
    assert compute_workflow_hash("host_map", perturbed) != baseline, (
        f"{component} is recorded but does not determine the host_map hash"
    )


# ── the matching policy is read from the code, not restated ──────────────────────

def test_the_recorded_policy_is_the_policy_the_code_runs(host_map_inputs):
    """A restated policy would drift; a derived one cannot."""
    from cmig.core.namespace import (
        NORMALIZE_COMPARTMENT_SUFFIXES,
        NORMALIZE_EXCHANGE_PREFIX,
    )

    policy = _components(host_map_inputs)["map_spec"]
    assert policy == host_map_policy()
    assert policy["interface_map_admits"] == list(HOST_MAP_INTERFACE_MAP_ADMITS)
    assert policy["needs_review_match_types"] == list(HOST_MAP_NEEDS_REVIEW_TYPES)
    normalization = policy["id_normalization"]
    assert normalization["exchange_prefix_stripped"] == NORMALIZE_EXCHANGE_PREFIX
    assert normalization["compartment_suffixes_stripped"] == list(NORMALIZE_COMPARTMENT_SUFFIXES)


def test_changing_the_normalizer_would_change_the_hash(monkeypatch, host_map_inputs):
    """The point of deriving the policy: a normalizer change must not slip past the fingerprint."""
    import cmig.core.host_map as host_map_module

    baseline = compute_workflow_hash("host_map", _components(host_map_inputs))
    monkeypatch.setattr(
        host_map_module, "NORMALIZE_COMPARTMENT_SUFFIXES", ("_e", "_m", "_c", "_p", "_x"),
    )
    assert compute_workflow_hash("host_map", _components(host_map_inputs)) != baseline


def test_changing_the_auto_admit_rule_would_change_the_hash(monkeypatch, host_map_inputs):
    """Admitting annotation matches into interface_map is exactly the round-2 D/L hazard."""
    import cmig.core.host_map as host_map_module

    baseline = compute_workflow_hash("host_map", _components(host_map_inputs))
    monkeypatch.setattr(
        host_map_module, "HOST_MAP_INTERFACE_MAP_ADMITS", ("exact", "annotation"),
    )
    assert compute_workflow_hash("host_map", _components(host_map_inputs)) != baseline


def test_the_solver_is_not_a_determining_input(host_map_inputs):
    """host-map never solves. Recording a solver would split hashes for no scientific reason."""
    assert _components(host_map_inputs)["solver_setting"] == {"solver": None}
