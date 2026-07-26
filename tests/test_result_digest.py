"""Round-5 P0 (second pass) — the manifest must fingerprint the ANSWER, not only the inputs.

The first fix certified the host-map matcher from the input side: `map_spec.match_behavior` is a
digest of what the matcher does to a frozen synthetic probe. Independent verification then broke it
again, and the break is structural rather than a missing fixture case. Three changes to
`build_host_map` — capping the reported entries, capping the host index build, dropping currency
metabolites — each rewrote the real interface map on real GEMs while `run_hash`, `map_spec` **and**
`match_behavior` stayed bit-identical:

    run_hash      49d362dc8f138b82…  identical across base / A1 / A4
    match_behavior sha256:6f6f8b85…  identical across base / A1 / A4
    interface_map  67 → 22 (A1) → 62 (A4)

The probe measures one small synthetic instance (~16 secretions, invented ids), so anything keyed
on *scale* or on *real BiGG vocabulary* is invisible to it — and a fixture can only cover decision
points somebody has already written. A4 is the realistic one: CMIG already ships
`--exclude-metabolites` and `--include-currency-metabolites` on the host-coupling surfaces, so
wiring the same policy into `host-map` is obvious next feature work and would silently reuse a
published fingerprint.

`result_digest` closes it from the answer side. It is **additive and outside the hash**, so no
published `run_hash` moves. Two runs sharing a `run_hash` while differing in `result_digest` become
*detectable*, which is exactly the false negative.

Note the asymmetry these tests exist to protect against: a source fingerprint's failure mode is
false positives (annoying, safe); a behaviour probe's is false negatives (silent, unsafe).
"""

from __future__ import annotations

import json

import pytest

from cmig.core.workflow_manifest import (
    DETERMINISTIC_ARTIFACT_KINDS,
    artifact_result_digest,
    write_workflow_manifest,
)


def _components(kind: str = "host_map") -> dict[str, object]:
    from cmig.core.workflow_envelope_golden import golden_components

    return golden_components(kind)


def _write_run(tmp_path, *, entries: int, kind: str = "host_map"):
    """A run directory with the artifacts a `host-map` run writes."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "host_exchange_map.csv").write_text(
        "metabolite,host_exchange\n"
        + "".join(f"met{i}_e,EX_met{i}_e\n" for i in range(entries))
    )
    (tmp_path / "host_interface_map.json").write_text(
        json.dumps({"interface_map": {f"met{i}_e": f"EX_met{i}_e" for i in range(entries)}},
                   sort_keys=True)
    )
    (tmp_path / "host_map_summary.json").write_text(json.dumps({"n_exact": entries}))
    return write_workflow_manifest(
        tmp_path, kind, _components(kind),
        artifacts=["host_exchange_map.csv", "host_interface_map.json", "host_map_summary.json"],
    )


# ── the field exists, and says what it certifies ─────────────────────────────────

def test_the_manifest_carries_a_result_digest(tmp_path):
    _write_run(tmp_path, entries=3)
    payload = json.loads((tmp_path / "manifest.json").read_text())
    digest = payload["result_digest"]
    assert digest["digest"].startswith("sha256:")
    assert set(digest["artifacts"]) == {
        "host_exchange_map.csv", "host_interface_map.json", "host_map_summary.json",
    }
    assert digest["missing_artifacts"] == []
    assert digest["cross_run_comparable"] is True
    assert "host_map" in DETERMINISTIC_ARTIFACT_KINDS


def test_the_result_digest_is_additive_and_never_enters_the_input_hash(tmp_path):
    """The whole point of it being safe to add: no published run_hash moves."""
    baseline = _write_run(tmp_path / "a", entries=3)
    changed = _write_run(tmp_path / "b", entries=99)
    assert baseline == changed, "different artifacts must NOT move the input hash"

    payload = json.loads((tmp_path / "a" / "manifest.json").read_text())
    assert "result_digest" not in payload["components"]
    assert "result_digest" not in payload["hash_components"]
    # …and it does not participate in the hash by any other route either.
    from cmig.core.workflow_manifest import compute_workflow_hash

    assert compute_workflow_hash("host_map", _components()) == baseline


def test_a_changed_answer_moves_the_result_digest(tmp_path):
    """The A1/A4 shape: same declared inputs, different produced interface map."""
    _write_run(tmp_path / "a", entries=67)
    _write_run(tmp_path / "b", entries=22)
    a, b = (
        json.loads((tmp_path / name / "manifest.json").read_text()) for name in ("a", "b")
    )
    assert a["run_hash"] == b["run_hash"], "this test is only meaningful while the inputs match"
    assert a["result_digest"]["digest"] != b["result_digest"]["digest"]


def test_identical_runs_produce_an_identical_result_digest(tmp_path):
    """Otherwise a mismatch would mean nothing — it has to be quiet when nothing changed."""
    _write_run(tmp_path / "a", entries=5)
    _write_run(tmp_path / "b", entries=5)
    a, b = (
        json.loads((tmp_path / name / "manifest.json").read_text()) for name in ("a", "b")
    )
    assert a["result_digest"] == b["result_digest"]


def test_a_run_that_failed_to_write_an_artifact_does_not_digest_as_a_complete_one(tmp_path):
    """A missing output is recorded, not skipped — half a result must not look like a whole one."""
    _write_run(tmp_path, entries=3)
    complete = json.loads((tmp_path / "manifest.json").read_text())["result_digest"]
    (tmp_path / "host_interface_map.json").unlink()
    partial = artifact_result_digest(tmp_path, "host_map", list(complete["artifacts"]))
    assert partial["missing_artifacts"] == ["host_interface_map.json"]
    assert partial["digest"] != complete["digest"]


def test_a_kind_with_no_measured_determinism_is_not_claimed_comparable(tmp_path):
    """`cross_run_comparable` is a measured claim; an unmeasured kind gets a digest, not a claim."""
    _write_run(tmp_path, entries=2, kind="model_quality")
    digest = json.loads((tmp_path / "manifest.json").read_text())["result_digest"]
    assert digest["digest"].startswith("sha256:")      # still fingerprinted and still checkable
    assert digest["cross_run_comparable"] is False     # but not advertised as diffable across runs


# ── inspect-run recomputes it and says so loudly ─────────────────────────────────

def test_inspect_run_verifies_the_result_digest_against_the_files_on_disk(tmp_path):
    from cmig.cli.main import _inspect_run_dir

    _write_run(tmp_path, entries=4)
    verified = _inspect_run_dir(tmp_path)["result_digest"]
    assert verified["match"] is True
    assert verified["changed_artifacts"] == []


def test_inspect_run_reports_an_edited_artifact_as_a_mismatch(tmp_path):
    """The failure run_hash structurally cannot report: same inputs, different answer."""
    from cmig.cli.main import _inspect_run_dir

    _write_run(tmp_path, entries=4)
    payload = json.loads((tmp_path / "host_interface_map.json").read_text())
    payload["interface_map"].pop("met0_e")
    (tmp_path / "host_interface_map.json").write_text(json.dumps(payload, sort_keys=True))

    inspected = _inspect_run_dir(tmp_path)
    assert inspected["run_hash"] is not None, "the input hash still matches — that is the point"
    verified = inspected["result_digest"]
    assert verified["match"] is False
    assert verified["changed_artifacts"] == ["host_interface_map.json"]
    assert verified["recorded"] != verified["actual"]


def test_inspect_run_reports_a_deleted_artifact_as_missing(tmp_path):
    from cmig.cli.main import _inspect_run_dir

    _write_run(tmp_path, entries=4)
    (tmp_path / "host_map_summary.json").unlink()
    verified = _inspect_run_dir(tmp_path)["result_digest"]
    assert verified["match"] is False
    assert verified["missing_artifacts"] == ["host_map_summary.json"]
    assert "host_map_summary.json" in verified["changed_artifacts"]


def test_inspect_run_reports_absence_rather_than_passing_off_a_match(tmp_path):
    """A manifest predating result digests must not read as "verified"."""
    from cmig.cli.main import _inspect_run_dir

    _write_run(tmp_path, entries=4)
    payload = json.loads((tmp_path / "manifest.json").read_text())
    del payload["result_digest"]
    (tmp_path / "manifest.json").write_text(json.dumps(payload, sort_keys=True))
    assert _inspect_run_dir(tmp_path)["result_digest"] is None


def test_the_text_report_names_which_claim_failed(tmp_path, capsys):
    """A reader has to be told run_hash and result_digest certify different things."""
    import argparse

    from cmig.cli.main import _cmd_inspect_run

    _write_run(tmp_path, entries=4)
    (tmp_path / "host_exchange_map.csv").write_text("metabolite,host_exchange\n")
    _cmd_inspect_run(argparse.Namespace(run_dir=str(tmp_path), format="text"))
    captured = capsys.readouterr()
    assert "result_digest: MISMATCH" in captured.err
    assert "host_exchange_map.csv: changed" in captured.err
    assert "run_hash certifies the inputs" in captured.err
    assert "certifies the INPUTS" in captured.out


@pytest.mark.parametrize("kind", sorted(DETERMINISTIC_ARTIFACT_KINDS))
def test_every_kind_claimed_deterministic_is_a_real_workflow_kind(kind):
    from cmig.core.workflow_manifest import WORKFLOW_HASH_COMPONENTS

    assert kind in WORKFLOW_HASH_COMPONENTS
