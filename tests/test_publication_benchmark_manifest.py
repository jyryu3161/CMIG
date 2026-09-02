"""Round-5 P4 — `publication-benchmark` must emit a workflow manifest that names what it certified.

Phase 4 left this command without a manifest, which is the worst of the twelve gaps to leave: it
is the surface that claims to bundle the whole publication audit, so a reader is invited to treat
its output as the provenance record for a paper. Recording only its own arguments would not be
enough either — a bundle is a claim about a *set of runs*, and a reader has to be able to tell
which runs. So the bundle manifest carries each sub-run's kind and run_hash, and the child hashes
are inside the bundle hash (see `workflow_manifest.bundle_component`).

Solver required (the benchmark really solves); the pure-serialization properties are tested
without one below.
"""

from __future__ import annotations

import json
import os

import pytest

cobra = pytest.importorskip("cobra")
micom = pytest.importorskip("micom")

from cmig.core.dfba import DfbaConfig  # noqa: E402
from cmig.core.workflow_manifest import (  # noqa: E402
    WORKFLOW_HASH_COMPONENTS,
    bundle_component,
    compute_workflow_hash,
    workflow_components_for,
)
from cmig.service.publication_benchmark import (  # noqa: E402
    PublicationBenchmarkConfig,
    run_publication_benchmark,
)
from cmig.synthetic_host import build_host_model  # noqa: E402
from cmig.synthetic_pair import build_pair_taxonomy  # noqa: E402


def _benchmark_config(base, out, **overrides):
    taxonomy = build_pair_taxonomy(base / "microbes")
    dfba_model = base / "ecoli.xml"
    if not dfba_model.exists():
        core = cobra.io.read_sbml_model(
            os.path.join(os.path.dirname(micom.__file__), "data", "e_coli_core.xml.gz")
        )
        cobra.io.write_sbml_model(core, str(dfba_model))
    host_model = base / "host.xml"
    if not host_model.exists():
        cobra.io.write_sbml_model(build_host_model(), str(host_model))
    settings = {
        "taxonomy": taxonomy,
        "taxonomy_base_dir": base,
        "out_dir": out,
        "namespace_policy": "assume_bigg",
        "search_target": "but",
        "search_min_size": 2,
        "search_max_size": 2,
        "dfba_model": dfba_model,
        "dfba_config": DfbaConfig(
            t_end=0.2, dt=0.1, initial_concentrations={
                        # Every substrate e_coli_core consumes is tracked: the benchmark's
                        # dFBA verdict is the writer's `acceptance.interpretable`, which
                        # fails a grid fed by untracked, never-depleting default-medium
                        # uptake (nh4/o2/pi).
                        "EX_glc__D_e": 10.0, "EX_o2_e": 20.0, "EX_nh4_e": 20.0, "EX_pi_e": 20.0,
                    }
        ),
        "dfba_dts": [0.1],
        "dfba_kms": [0.01],
        "host_model": host_model,
        "host_source": {"name": "synthetic test host", "version": "1"},
        "host_interface_map": {"but": "EX_but_lumen"},
        "microbial_biomass_gdw": 1.0,
        "host_biomass_gdw": 1.0,
        "biomass_basis_kind": "measured",
        "biomass_basis_source": "synthetic fixture dry-mass definition",
        "keep_host_uptake": True,
    }
    settings.update(overrides)
    return PublicationBenchmarkConfig(**settings)


@pytest.fixture(scope="module")
def bundle_runs(tmp_path_factory):
    """Two runs of the same benchmark on identical inputs, plus one with a changed argument."""
    base = tmp_path_factory.mktemp("bundle")
    manifests = {}
    for name, overrides in (
        ("a", {}),
        ("b", {}),
        ("changed_tradeoff", {"tradeoff_f": 0.7}),
    ):
        out = base / name
        run_publication_benchmark(_benchmark_config(base, out, **overrides))
        manifests[name] = json.loads((out / "manifest.json").read_text())
        manifests[f"{name}_dir"] = out
    return manifests


# ── the manifest exists and is a bundle ──────────────────────────────────────────

def test_publication_benchmark_is_a_registered_workflow_kind():
    assert "publication_benchmark" in WORKFLOW_HASH_COMPONENTS
    assert "bundle_spec" in workflow_components_for("publication_benchmark")


def test_the_bundle_writes_its_own_manifest(bundle_runs):
    payload = bundle_runs["a"]
    assert payload["workflow_kind"] == "publication_benchmark"
    assert payload["manifest_scope"] == "workflow"
    assert len(payload["run_hash"]) == 64
    assert payload["artifacts"] == ["publication_benchmark.json"]
    assert payload["status"] in {"ok", "degraded", "failed"}


def test_the_bundle_manifest_is_not_one_of_its_own_certified_artifacts(bundle_runs):
    """It is written after publication_benchmark.json, so it cannot checksum itself."""
    package = json.loads(
        (bundle_runs["a_dir"] / "publication_benchmark.json").read_text()
    )
    assert "manifest.json" not in package["artifacts"]


def test_inspect_run_reports_the_bundle_not_a_community_solve(bundle_runs):
    from cmig.cli.main import _inspect_run_dir

    inspected = _inspect_run_dir(bundle_runs["a_dir"])
    assert inspected["kind"] == "publication_benchmark"
    assert inspected["run_hash"] == bundle_runs["a"]["run_hash"]


# ── it records WHICH runs it certifies ───────────────────────────────────────────

def _bundle_spec(payload):
    return dict(payload["components"])["bundle_spec"]


def test_the_bundle_names_every_sub_run_it_certified(bundle_runs):
    spec = _bundle_spec(bundle_runs["a"])
    assert spec["bundle_hash_includes_child_hashes"] is True
    assert set(spec["child_kinds"]) == {
        "community_solve", "model_quality", "model_pool_search", "dfba",
        "host_map", "host_microbe_bigg",
    }
    # two model_quality legs: the microbial pool and the host model
    assert spec["n_children"] == 7 == len(spec["children"])


def test_every_certified_child_carries_a_real_hash(bundle_runs):
    for child in _bundle_spec(bundle_runs["a"])["children"]:
        assert child["run_hash"] is not None, f"child {child['kind']} was bundled without a hash"
        assert len(child["run_hash"]) == 64


def test_each_child_hash_is_verifiable_from_its_own_manifest_on_disk(bundle_runs):
    """The inverse direction: bundle -> sub-run -> that sub-run's own manifest."""
    out = bundle_runs["a_dir"]
    for child in _bundle_spec(bundle_runs["a"])["children"]:
        manifest = out / child["artifacts_dir"] / "manifest.json"
        assert manifest.exists(), f"{child['kind']} has no manifest at {child['artifacts_dir']}"
        payload = json.loads(manifest.read_text())
        assert payload["run_hash"] == child["run_hash"]
        if child["kind"] == "community_solve":
            # [HASH-SINGLE]: the frozen 11-component solve hash is carried, never re-enveloped.
            # Round-5 P2: the solve manifest now *states* its scope instead of leaving a reader to
            # infer it from a missing key. It names the payload and is not an input to the hash,
            # so no published solve run_hash moves.
            assert payload["manifest_scope"] == "solve"
            assert "manifest_scope" not in payload["components"]
        else:
            assert payload["workflow_kind"] == child["kind"]


def test_a_certified_child_hash_is_reproducible_from_its_recorded_components(bundle_runs):
    """Each child manifest is a real envelope record, not a label."""
    out = bundle_runs["a_dir"]
    for child in _bundle_spec(bundle_runs["a"])["children"]:
        if child["kind"] == "community_solve":
            continue
        payload = json.loads((out / child["artifacts_dir"] / "manifest.json").read_text())
        recomputed = compute_workflow_hash(
            payload["workflow_kind"], dict(payload["components"])
        )
        assert recomputed == child["run_hash"]


def test_the_host_map_leg_fingerprints_the_same_as_a_standalone_host_map(bundle_runs, tmp_path):
    """Same host + same pool = same interface-map pre-flight, on either surface."""
    from cmig.cli.main import main

    out = bundle_runs["a_dir"]
    child = next(
        c for c in _bundle_spec(bundle_runs["a"])["children"] if c["kind"] == "host_map"
    )
    taxonomy = build_pair_taxonomy(out.parent / "microbes")
    taxonomy_path = tmp_path / "taxonomy.csv"
    taxonomy.to_csv(taxonomy_path, index=False)
    rc = main([
        "host-map", "--host", str(out.parent / "host.xml"),
        "--taxonomy", str(taxonomy_path), "--out", str(tmp_path / "standalone"),
    ])
    assert rc == 0
    standalone = json.loads((tmp_path / "standalone" / "manifest.json").read_text())
    assert standalone["run_hash"] == child["run_hash"]


# ── determinism, both directions ─────────────────────────────────────────────────

def test_identical_inputs_reproduce_the_bundle_hash(bundle_runs):
    assert bundle_runs["a"]["run_hash"] == bundle_runs["b"]["run_hash"]


def test_every_child_hash_is_reproduced_too(bundle_runs):
    first = {(c["kind"], c["artifacts_dir"]): c["run_hash"]
             for c in _bundle_spec(bundle_runs["a"])["children"]}
    second = {(c["kind"], c["artifacts_dir"]): c["run_hash"]
              for c in _bundle_spec(bundle_runs["b"])["children"]}
    assert first == second


def test_changing_a_benchmark_argument_changes_the_bundle_hash(bundle_runs):
    assert bundle_runs["changed_tradeoff"]["run_hash"] != bundle_runs["a"]["run_hash"]


def test_changing_only_a_child_hash_changes_the_bundle_hash(bundle_runs):
    """The design decision, proved: child hashes are *inside* the bundle hash.

    A bundle assembled from identical arguments but certifying a different community solve is a
    different scientific object and must not share a fingerprint.
    """
    components = dict(bundle_runs["a"]["components"])
    baseline = compute_workflow_hash("publication_benchmark", components)
    assert baseline == bundle_runs["a"]["run_hash"]
    perturbed = json.loads(json.dumps(components))
    perturbed["bundle_spec"]["children"][0]["run_hash"] = "0" * 64
    assert compute_workflow_hash("publication_benchmark", perturbed) != baseline


def test_losing_a_child_changes_the_bundle_hash(bundle_runs):
    components = dict(bundle_runs["a"]["components"])
    baseline = compute_workflow_hash("publication_benchmark", components)
    perturbed = json.loads(json.dumps(components))
    dropped = perturbed["bundle_spec"]["children"].pop()
    perturbed["bundle_spec"]["n_children"] -= 1
    assert dropped
    assert compute_workflow_hash("publication_benchmark", perturbed) != baseline


@pytest.mark.parametrize(
    "component",
    [c for c in workflow_components_for("publication_benchmark") if c != "workflow_kind"],
)
def test_changing_any_single_recorded_component_changes_the_bundle_hash(component, bundle_runs):
    """Every recorded parameter must determine the hash, or recording it is theatre."""
    components = dict(bundle_runs["a"]["components"])
    baseline = compute_workflow_hash("publication_benchmark", components)
    perturbed = json.loads(json.dumps(components))
    perturbed[component] = {"perturbed": component}
    assert perturbed[component] != components[component]
    assert compute_workflow_hash("publication_benchmark", perturbed) != baseline


# ── bundle_component, without a solver ───────────────────────────────────────────

def test_bundle_component_is_order_independent():
    """Bundle identity is the *set* of certified runs, not the order they happened to run in."""
    children = [
        {"kind": "dfba", "artifacts_dir": "dfba", "run_hash": "b" * 64, "status": "ok"},
        {"kind": "model_quality", "artifacts_dir": "model_quality", "run_hash": "a" * 64,
         "status": "ok"},
    ]
    assert bundle_component(children) == bundle_component(list(reversed(children)))


def test_bundle_component_keeps_an_unfingerprinted_child_rather_than_dropping_it():
    """A bundle that could not fingerprint a child certifies less — and must hash differently."""
    complete = bundle_component([
        {"kind": "dfba", "artifacts_dir": "dfba", "run_hash": "b" * 64, "status": "ok"},
    ])
    degraded = bundle_component([
        {"kind": "dfba", "artifacts_dir": "dfba", "run_hash": None, "status": "ok"},
    ])
    assert degraded["children"][0]["run_hash"] is None
    assert degraded["n_children"] == complete["n_children"] == 1
    assert degraded != complete


def test_bundle_component_distinguishes_two_runs_of_the_same_kind():
    """The benchmark audits two model_quality legs; they must not collapse into one entry."""
    spec = bundle_component([
        {"kind": "model_quality", "artifacts_dir": "model_quality", "run_hash": "a" * 64},
        {"kind": "model_quality", "artifacts_dir": "host/model_quality", "run_hash": "b" * 64},
    ])
    assert spec["n_children"] == 2
    assert spec["child_kinds"] == ["model_quality"]


# ── round-5 P2: the carried solve hash must be a solve hash ──────────────────────

def test_a_workflow_scope_manifest_is_never_carried_as_the_community_solve_hash(tmp_path):
    """[HASH-SINGLE]: a workflow envelope and a solve manifest are different hashes.

    Both are `manifest.json` with a 64-hex `run_hash`, so carrying one for the other would label a
    workflow fingerprint `community_solve` in the bundle with nothing to contradict it.
    """
    from cmig.service.publication_benchmark import _child_solve_run_hash

    community = tmp_path / "community"
    community.mkdir()
    manifest = community / "manifest.json"

    manifest.write_text(json.dumps({"manifest_scope": "solve", "run_hash": "a" * 64}))
    assert _child_solve_run_hash(community) == "a" * 64
    # A manifest written before `manifest_scope` existed carries no key and is still accepted.
    manifest.write_text(json.dumps({"manifest_schema_version": "2.0", "run_hash": "b" * 64}))
    assert _child_solve_run_hash(community) == "b" * 64
    # A workflow envelope is refused rather than mislabelled.
    manifest.write_text(json.dumps({
        "manifest_scope": "workflow", "workflow_kind": "dfba", "run_hash": "c" * 64,
    }))
    assert _child_solve_run_hash(community) is None
