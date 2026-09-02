"""Drift gate for the workflow-envelope serialization (the workflow-hash analogue of SC-5).

`golden verify` (SC-5) pins the *solve* side: it catches a MICOM version moving underneath the
frozen 11-component `community_solve` hash. Nothing pinned the *envelope* side. Phase 4 gave every
science command a `manifest.json` whose `run_hash` a published paper can be re-derived from, but
that hash is only as durable as `cmig.core.workflow_manifest`'s serialization: adding a component
to a kind's tuple, reordering one, changing the canonical JSON form, or changing the float
normalization all silently rewrite every previously published hash of that kind. A reader holding
last year's run_hash would then be unable to reproduce it and — worse — would get a *different*
hash from identical inputs with nothing announcing why.

This module is that missing gate. It stores, per registered kind, a fixed canonical input dict
together with the exact canonical JSON and hash the envelope produced for it, and re-derives both
on every test run.

Design, and why it is shaped this way:

* **It pins the serialization, not one workflow's inputs.** The fixture inputs are synthetic
  constants (no live `CMIG_CORE_VERSION`, no installed dependency versions), so a version bump is
  not drift — only a change to *how* the envelope serializes is.
* **The stored input dict is the contract check.** It is fed back through
  `canonical_workflow_payload`, so adding a component to an existing kind's tuple makes that kind's
  stored input incomplete and the gate fails with "missing determining components" rather than
  quietly hashing a different shape.
* **New kinds do not break it.** Verification iterates the *stored* kinds. A newly declared kind is
  reported as uncovered so it can be blessed, but it cannot fail a build that did not touch the
  envelope.
* **Re-blessing is explicit and mirrors SC-5.** `python -m cmig.core.workflow_envelope_golden`
  rewrites the file, exactly as `python -m cmig.golden_fixture` recaptures the solve golden.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from cmig.core.manifest import DEFAULT_FLOAT_DECIMALS
from cmig.core.workflow_manifest import (
    WORKFLOW_HASH_COMPONENTS,
    WORKFLOW_MANIFEST_SCHEMA_VERSION,
    bundle_component,
    canonical_workflow_json,
    compute_workflow_hash,
    host_spec_component,
    medium_component,
    workflow_components_for,
)
from cmig.io.atomic import atomic_write_text

ENVELOPE_GOLDEN_SCHEMA_VERSION = "1.0"
#: Ships inside the package (not under `fixtures/`, which is excluded from every distribution) so
#: the gate runs wherever the tests run, rather than skipping on a trimmed checkout.
ENVELOPE_GOLDEN_PATH = Path(__file__).with_name("workflow_envelope_golden.json")

REBLESS_COMMAND = "python -m cmig.core.workflow_envelope_golden"


class EnvelopeDrift(AssertionError):
    """The workflow-envelope serialization changed, so published workflow hashes moved."""


# ── synthetic component fixtures ───────────────────────────────────────────────
# One fixed value per component name in the vocabulary. Deliberately *not* derived from the running
# environment: this gate must fire on serialization changes and stay silent on version bumps.
# Values are chosen to exercise the parts of the serialization that can drift — nesting, key
# ordering inside a value, list ordering, and float rounding at and below the 6-decimal floor.
#
# **Where a component has a builder, the fixture is BUILT BY IT, not transcribed.** A literal copy
# makes the gate certify a *copy* of the contract instead of the contract: round-5 changed
# `host_spec_component` to hash a file's name instead of its path, which moved real published
# hashes for five kinds, and the gate stayed silent because its `host_spec` fixture was a
# hand-written dict the builder never touched. Synthetic *inputs* keep the gate about
# serialization; the builder supplies the *shape and normalization*, so a change to either now
# fires. Components with no shared builder (their shape lives in one command) stay literal below.


def _golden_map_spec() -> dict[str, Any]:
    """`map_spec` as `host_map_policy()` shapes it, with its live values made synthetic.

    Built by the real builder so a new policy key cannot appear without the gate noticing, then
    the two environment-derived values are replaced: `match_behavior` is a digest of what the
    matcher *does*, which is pinned by `host_map_probe`'s own canary and must not turn a change in
    the science into envelope drift.
    """
    from cmig.core.host_map import host_map_policy

    spec = copy.deepcopy(host_map_policy())
    spec["match_policy_version"] = "golden"
    spec["match_behavior"] = {"probe_version": "golden", "digest": "sha256:4444"}
    return spec


_COMPONENT_FIXTURES: dict[str, Any] = {
    "cmig_core_version": "0.0.0-envelope-golden",
    "dependency_versions": {
        "cobra": "0.0.0-golden", "micom": "0.0.0-golden", "optlang": "0.0.0-golden",
    },
    "solver_setting": {"solver": "golden", "growth_solver": "golden", "flux_solver": "golden"},
    "model_checksum": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
    "medium": medium_component(
        "golden/diet.csv",
        "sha256:1111111111111111111111111111111111111111111111111111111111111111",
        namespace_bridge={"unavailable_per_member": {"m_b": ["o2_e"], "m_a": []}},
        allow_unknown=False,
    ),
    "abundances": {"m_b": 0.6666665, "m_a": 0.3333335},
    "tradeoff_f": 0.5,
    "growth_fraction": 0.1234565,
    "target_spec": {"target": "but", "direction": "max_secretion", "mode": "single_target"},
    "search_spec": {
        "min_size": 2, "max_size": 3, "strategy": "exhaustive", "top_k": 10,
        "n_samples": 100, "seed": 0, "robustness_fva": False,
    },
    "knockout_spec": {
        "level": "gene", "member": "m_a", "genes": ["b0001", "b0002"], "selection": "all",
        "seed": 7, "cap": 25,
    },
    "host_spec": host_spec_component(
        host_model="golden/host.xml",
        host_model_checksum="sha256:2222",
        host_objective="biomass_host",
        interface_map="golden/interface.json",
        interface_map_checksum="sha256:3333",
        exchange_suffix="_e",
        exclude_metabolites=["h2o", "co2", "h"],   # unsorted on purpose: the builder sorts
        include_currency_metabolites=False,
        keep_host_uptake=True,
    ),
    "biomass_basis": {
        "kind": "measured", "source": "golden dry-mass record",
        "microbial_biomass_gdw": 0.25, "host_biomass_gdw": 1.5,
    },
    "flux_normalization_method": "pfba",
    "solve_run_hash": "cf3c73d97be5c3555d5d9e228c08e5088661cc6f1ba36fc7a333d2a9b2aaa633",
    "sweep_spec": {"kind": "member_abundance", "n_points": 3, "grid": [0.25, 0.5, 0.75]},
    "dfba_spec": {
        "mode": "sensitivity", "t_end": 10.0, "dt": 0.1, "km": 0.01,
        "initial_concentrations": {"EX_glc__D_e": 10.0}, "dts": [0.2, 0.1], "kms": [0.01],
    },
    "community_dfba_spec": {
        "integrator": "explicit_euler_adaptive_nonnegative",
        "t_end": 0.6,
        "dt": 0.1,
        "min_dt": 0.0001,
        "km": 0.01,
        "growth_floor": 0.000001,
        "tradeoff_fraction": 1.0,
        "initial_biomasses": {"consumer": 0.01, "producer": 0.01},
        "initial_abundances": {"consumer": 0.5, "producer": 0.5},
        "initial_concentrations": {"EX_glc_m": 2.0, "EX_xfeed_m": 0.0},
        "member_vmax": {
            "consumer": {"EX_xfeed_m": 10.0},
            "producer": {"EX_glc_m": 10.0, "EX_xfeed_m": 10.0},
        },
        "close_untracked_uptake": True,
        "death_washout": "not_modeled",
    },
    "quality_spec": {
        "n_models": 2, "check_blocked_reactions": True, "scope": "microbial_pool",
        "sources": ["golden/a.xml", "golden/b.xml"],
    },
    "map_spec": _golden_map_spec(),
    "bundle_spec": bundle_component([
        # Reversed on purpose: the builder sorts, so a change to bundle identity shows up here.
        {"kind": "model_quality", "run_hash": None, "artifacts_dir": "model_quality",
         "status": "degraded"},
        {"kind": "community_solve", "run_hash": "aaaa", "artifacts_dir": "community",
         "status": "ok"},
    ]),
    "namespace_spec": {
        "policy": "require_reviewed",
        "decisions": ["golden:ac:model:ac->bigg:ac"],
    },
    "pair_spec": {
        "per_medium": True,
        "conditions": [
            {"medium_id": "diet_a", "checksum": "sha256:aaaa"},
            {"medium_id": "diet_b", "checksum": "sha256:bbbb"},
        ],
    },
    "delta_spec": {
        "baseline_run_hash": "sha256:aaaa",
        "variant_run_hash": "sha256:bbbb",
        "significance_threshold": 1e-6,
    },
    "single_spec": {
        "methods": ["FBA", "pFBA"],
        "fva": True,
        "fva_fraction": 1.0,
        "exchange_summary": True,
    },
    "minimal_medium_spec": {
        "min_growth": 0.1,
        "oxygen_mode": "aerobic",
        "exclude_blocked": True,
    },
}

#: Components whose fixture above is built by the shared builder that real runs use. Pinned as a
#: test assertion, so a future component that gains a builder cannot keep a transcribed literal.
BUILDER_DERIVED_FIXTURES: frozenset[str] = frozenset(
    {"medium", "host_spec", "map_spec", "bundle_spec"}
)

# Every vocabulary entry except `workflow_kind`, which is the kind's own name.
assert set(_COMPONENT_FIXTURES) | {"workflow_kind"} >= {
    name for names in WORKFLOW_HASH_COMPONENTS.values() for name in names
}, "every component a declared kind uses needs a golden fixture value"


def golden_components(kind: str) -> dict[str, Any]:
    """The synthetic input dict for ``kind`` — exactly its declared components, nothing else.

    Deep-copied: the fixture values are nested mutables shared by every kind that records them, so
    handing out references let a caller that edited a returned component silently redefine the
    golden's own reference inputs for the rest of the process.
    """
    return {
        name: kind if name == "workflow_kind" else copy.deepcopy(_COMPONENT_FIXTURES[name])
        for name in workflow_components_for(kind)
    }


# ── float-normalization probe ──────────────────────────────────────────────────
# NaN/-inf/-0.0 cannot survive a JSON round-trip, so they cannot live in the golden file's stored
# inputs. They are pinned here instead: this probe fails if the non-finite or signed-zero handling
# in `canonicalize_floats` ever changes, which would move every hash carrying a cobra bound.
_PROBE_KIND = "dfba"


def float_probe_components() -> dict[str, Any]:
    components = golden_components(_PROBE_KIND)
    components["dfba_spec"] = {
        "nan": float("nan"),
        "pos_inf": float("inf"),
        "neg_inf": float("-inf"),
        "negative_zero": -0.0,
        "below_rounding_floor": 0.1 + 1e-12,
        "at_rounding_floor": 0.1234565,
    }
    return components


# ── payload build / verify ─────────────────────────────────────────────────────

def build_golden_payload() -> dict[str, Any]:
    """Regenerate the golden payload from the currently declared kinds (the re-bless product)."""
    return {
        "envelope_golden_schema_version": ENVELOPE_GOLDEN_SCHEMA_VERSION,
        "workflow_manifest_schema_version": WORKFLOW_MANIFEST_SCHEMA_VERSION,
        "float_decimals": DEFAULT_FLOAT_DECIMALS,
        "float_normalization_probe": {
            "kind": _PROBE_KIND,
            "canonical_json": canonical_workflow_json(_PROBE_KIND, float_probe_components()),
            "hash": compute_workflow_hash(_PROBE_KIND, float_probe_components()),
        },
        "kinds": {
            kind: {
                "components": list(workflow_components_for(kind)),
                "input": golden_components(kind),
                "canonical_json": canonical_workflow_json(kind, golden_components(kind)),
                "hash": compute_workflow_hash(kind, golden_components(kind)),
            }
            for kind in sorted(WORKFLOW_HASH_COMPONENTS)
        },
    }


def load_golden(path: Path = ENVELOPE_GOLDEN_PATH) -> dict[str, Any]:
    if not path.exists():
        raise EnvelopeDrift(
            f"workflow-envelope golden not found at {path}. It ships inside the package and must "
            f"exist; capture it with `{REBLESS_COMMAND}`."
        )
    payload: dict[str, Any] = json.loads(path.read_text())
    return payload


def write_golden(path: Path = ENVELOPE_GOLDEN_PATH) -> dict[str, Any]:
    payload = build_golden_payload()
    atomic_write_text(
        path,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n",
    )
    return payload


def _first_difference(expected: str, actual: str) -> str:
    """Where two canonical serializations first diverge, with a little context on each side."""
    limit = min(len(expected), len(actual))
    index = next((i for i in range(limit) if expected[i] != actual[i]), limit)
    window = slice(max(0, index - 40), index + 40)
    return (
        f"first difference at character {index}:\n"
        f"      golden … {expected[window]!r}\n"
        f"      actual … {actual[window]!r}"
    )


def verify_envelope_golden(path: Path = ENVELOPE_GOLDEN_PATH) -> dict[str, Any]:
    """Re-derive every stored kind's hash. Returns a report; never raises on drift itself.

    ``drifted`` — a stored kind whose canonical JSON or hash changed, or whose stored input no
    longer satisfies its declared component tuple.
    ``removed`` — a stored kind that is no longer declared (published hashes of it are orphaned).
    ``uncovered`` — a declared kind with no golden entry; reported, but not a failure, so adding a
    kind does not break a build that left the envelope alone.
    """
    golden = load_golden(path)
    stored: dict[str, Any] = golden.get("kinds", {})
    drifted: list[dict[str, Any]] = []
    removed: list[str] = []
    checked: list[str] = []

    for kind in sorted(stored):
        entry = stored[kind]
        if kind not in WORKFLOW_HASH_COMPONENTS:
            removed.append(kind)
            continue
        declared = list(workflow_components_for(kind))
        try:
            actual_json = canonical_workflow_json(kind, dict(entry["input"]))
            actual_hash = compute_workflow_hash(kind, dict(entry["input"]))
        except Exception as error:  # noqa: BLE001 - the contract change IS the finding
            drifted.append({
                "kind": kind,
                "reason": f"{type(error).__name__}: {error}",
                "golden_components": entry.get("components"),
                "declared_components": declared,
            })
            continue
        if actual_hash != entry["hash"] or actual_json != entry["canonical_json"]:
            drifted.append({
                "kind": kind,
                "reason": "serialization changed",
                "golden_hash": entry["hash"],
                "actual_hash": actual_hash,
                "golden_components": entry.get("components"),
                "declared_components": declared,
                "difference": _first_difference(entry["canonical_json"], actual_json),
            })
            continue
        # The stored input is only a contract check while it still *is* the declared fixture.
        # Editing `_COMPONENT_FIXTURES` — e.g. giving a component a new sub-key because the real
        # component grew one — otherwise left the golden pinning a shape the code no longer
        # produces, silently, because verification re-derives from the stored copy. Round-5 found
        # this while adding `map_spec.match_behavior`: the fixture changed and the gate stayed
        # green. Checked last, so a widened or narrowed contract still reports its own, more
        # specific reason. Compared through JSON so a tuple/list distinction is not called drift.
        if json.loads(json.dumps(entry["input"], sort_keys=True)) != json.loads(
            json.dumps(golden_components(kind), sort_keys=True)
        ):
            drifted.append({
                "kind": kind,
                "reason": "stored input no longer matches the declared component fixture",
                "golden_components": entry.get("components"),
                "declared_components": declared,
            })
            continue
        checked.append(kind)

    probe = golden.get("float_normalization_probe") or {}
    probe_ok = True
    probe_detail: dict[str, Any] = {}
    if probe:
        actual_probe_json = canonical_workflow_json(probe["kind"], float_probe_components())
        actual_probe_hash = compute_workflow_hash(probe["kind"], float_probe_components())
        probe_ok = (
            actual_probe_hash == probe["hash"] and actual_probe_json == probe["canonical_json"]
        )
        if not probe_ok:
            probe_detail = {
                "golden_hash": probe["hash"],
                "actual_hash": actual_probe_hash,
                "difference": _first_difference(probe["canonical_json"], actual_probe_json),
            }

    return {
        "path": str(path),
        "float_decimals_golden": golden.get("float_decimals"),
        "float_decimals_installed": DEFAULT_FLOAT_DECIMALS,
        "manifest_schema_version_golden": golden.get("workflow_manifest_schema_version"),
        "manifest_schema_version_installed": WORKFLOW_MANIFEST_SCHEMA_VERSION,
        "checked": checked,
        "drifted": drifted,
        "removed": removed,
        "uncovered": sorted(set(WORKFLOW_HASH_COMPONENTS) - set(stored)),
        "float_normalization_probe_ok": probe_ok,
        "float_normalization_probe": probe_detail,
        "ok": not drifted and not removed and probe_ok,
    }


def _report_lines(report: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for item in report["drifted"]:
        lines.append(f"  kind {item['kind']!r}: {item['reason']}")
        if item.get("golden_components") != item.get("declared_components"):
            lines.append(f"      golden components:   {item.get('golden_components')}")
            lines.append(f"      declared components: {item.get('declared_components')}")
        if "golden_hash" in item:
            lines.append(f"      golden hash: {item['golden_hash']}")
            lines.append(f"      actual hash: {item['actual_hash']}")
        if "difference" in item:
            lines.append("      " + item["difference"].replace("\n", "\n      "))
    for kind in report["removed"]:
        lines.append(
            f"  kind {kind!r}: no longer declared — every published run_hash of this kind is "
            "now orphaned"
        )
    if not report["float_normalization_probe_ok"]:
        detail = report["float_normalization_probe"]
        lines.append("  float normalization (NaN / ±inf / -0.0 / rounding floor) changed:")
        lines.append(f"      golden hash: {detail.get('golden_hash')}")
        lines.append(f"      actual hash: {detail.get('actual_hash')}")
        if detail.get("difference"):
            lines.append("      " + detail["difference"].replace("\n", "\n      "))
    return lines


def assert_envelope_golden(path: Path = ENVELOPE_GOLDEN_PATH) -> None:
    """Gate: any drift in the envelope serialization raises :class:`EnvelopeDrift`."""
    report = verify_envelope_golden(path)
    if report["ok"]:
        return
    raise EnvelopeDrift(
        "workflow-envelope serialization drift — every previously published workflow run_hash "
        "listed below now derives differently from identical inputs, so a reader cannot "
        "reproduce it:\n"
        + "\n".join(_report_lines(report))
        + "\n\nIf the change is intentional, re-bless the envelope golden and say so in the "
        f"changelog:\n    {REBLESS_COMMAND}\n"
        "(this mirrors `python -m cmig.golden_fixture` for the SC-5 solve golden). "
        "Re-blessing invalidates the affected published hashes — it is a contract change, not a "
        "formatting fix."
    )


if __name__ == "__main__":  # pragma: no cover - re-bless entry point
    written = write_golden()
    print(f"workflow-envelope golden re-blessed -> {ENVELOPE_GOLDEN_PATH}")
    for name, entry in sorted(written["kinds"].items()):
        print(f"  {name:32} {entry['hash']}")
    print(f"  {'float_normalization_probe':32} {written['float_normalization_probe']['hash']}")
