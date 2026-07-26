"""Phase-4 — `inspect-run` must report kind, status and run_hash uniformly for every run kind.

Two failure modes this pins, both introduced by giving workflows a `manifest.json`:

1. **Kind confusion.** `RUN_SUMMARY_FILES` maps `manifest.json -> community_solve` and is scanned
   first, so without the workflow-scope check every search/host/KO run would be relabelled a
   community solve.
2. **Status vocabulary.** Round-2 F11 found `inspect-run` emitting `optimal` and `completed`
   alongside the `ok`/`degraded`/`failed` tiers any automated gate is written against.

No solver required — the manifests are written directly.
"""

from __future__ import annotations

import json

import pytest

from cmig.cli.main import _inspect_run_dir, _normalize_run_status, _resolve_run_status
from cmig.core.workflow_manifest import WORKFLOW_HASH_COMPONENTS, write_workflow_manifest

STATUS_VOCABULARY = {"ok", "degraded", "failed"}


def _workflow_run(tmp_path, kind: str, *, status: str = "ok"):
    """Write a minimally complete workflow manifest for `kind`."""
    placeholder = {
        "workflow_kind": kind,
        "cmig_core_version": "0.1.0",
        "dependency_versions": {"micom": "0.39.0"},
        "solver_setting": {"solver": "gurobi"},
        "model_checksum": "sha256:abc",
        "medium": {"checksum": "m"},
    }
    for name in WORKFLOW_HASH_COMPONENTS[kind]:
        placeholder.setdefault(name, {})
    run_hash = write_workflow_manifest(tmp_path, kind, placeholder, status=status)
    return run_hash


@pytest.mark.parametrize("kind", sorted(WORKFLOW_HASH_COMPONENTS))
def test_every_kind_is_reported_with_its_own_name_and_a_non_null_hash(kind, tmp_path):
    run_hash = _workflow_run(tmp_path, kind)
    payload = _inspect_run_dir(tmp_path)
    assert payload["kind"] == kind, "a workflow manifest must not be read as a community solve"
    assert payload["run_hash"] == run_hash
    assert payload["run_hash"] is not None


@pytest.mark.parametrize("kind", sorted(WORKFLOW_HASH_COMPONENTS))
def test_status_is_always_in_the_gate_vocabulary(kind, tmp_path):
    _workflow_run(tmp_path, kind, status="degraded")
    assert _inspect_run_dir(tmp_path)["status"] in STATUS_VOCABULARY


def test_workflow_manifest_beats_a_legacy_summary_status(tmp_path):
    """The manifest carries the derived run-level tier; a summary may carry a raw solve status."""
    _workflow_run(tmp_path, "dfba", status="degraded")
    (tmp_path / "dfba_summary.json").write_text(json.dumps({"status": "completed"}))
    payload = _inspect_run_dir(tmp_path)
    assert payload["status"] == "degraded"
    assert payload["status_source"] == "manifest"


def test_a_solve_manifest_is_still_read_as_a_community_solve(tmp_path):
    """The workflow check must not break the original solve path."""
    (tmp_path / "manifest.json").write_text(json.dumps({
        "manifest_schema_version": "2.0",
        "run_hash": "deadbeef",
        "diagnostic": None,
    }))
    payload = _inspect_run_dir(tmp_path)
    assert payload["kind"] == "community_solve"
    assert payload["run_hash"] == "deadbeef"


def test_workflow_manifest_components_are_surfaced_for_reading(tmp_path):
    """A reader must see what the answer depended on without opening the file by hand."""
    _workflow_run(tmp_path, "model_pool_search")
    manifest = _inspect_run_dir(tmp_path)["manifest"]
    assert manifest["manifest_scope"] == "workflow"
    assert manifest["workflow_kind"] == "model_pool_search"
    assert manifest["hash_components"] == list(WORKFLOW_HASH_COMPONENTS["model_pool_search"])
    assert [name for name, _v in manifest["components"]] == manifest["hash_components"]


def test_legacy_raw_statuses_are_normalized():
    assert _normalize_run_status("optimal") == "ok"
    assert _normalize_run_status("completed") == "ok"
    assert _normalize_run_status("degraded") == "degraded"
    # An unrecognized value stays visible instead of being coerced into a success.
    assert _normalize_run_status("who_knows") == "who_knows"


def test_a_summary_without_a_manifest_still_resolves():
    status, source = _resolve_run_status({"status": "optimal"}, {})
    assert (status, source) == ("ok", "summary")


def test_an_empty_run_dir_is_still_honestly_unknown(tmp_path):
    payload = _inspect_run_dir(tmp_path)
    assert payload["kind"] == "unknown"
    assert payload["status"] == "unknown"
    assert payload["run_hash"] is None
