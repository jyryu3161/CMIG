"""Round-5 P0 regression — the host-map fingerprint must track the matcher, not describe it.

Round-5 verification broke the `host_map` reproducibility claim end-to-end on real GEMs. `map_spec`
recorded `match_order`, `secretion_criterion`, `annotation_requires_unique_target` and
`annotation_sources` as inert literals that no code path read, guarded only by a hand-bumped
`HOST_MAP_MATCH_POLICY_VERSION`. Changing one comparison in `build_host_map` took the auto-admitted
interface map from **67 entries to 11** — 56 metabolites silently dropped — while `run_hash` stayed
bit-identical at `c5a6c402…c66257a5`; a second change relabelled all six D/L stereoisomer
needs-review entries, also under a stable hash. The manifest's own `summary.interface_map_checksum`
moved while `run_hash` did not, so the artifact contradicted itself.

The property these tests pin, stated at the strength it actually holds:

    **a change to any matching rule the probe fixture exercises moves the host_map run_hash.**

They check it in both places it has to hold — at the digest (`matching_behavior_digest`) and
end-to-end at the workflow hash the manifest publishes — for every decision point the verifier's
ten perturbations attacked. `test_the_probe_fixture_still_distinguishes_every_decision_point` is the
guard on the guard: the digest only sees what the probe fixture exercises, so narrowing the fixture
must fail a test rather than quietly narrowing the guarantee.

**This is deliberately NOT the stronger claim** that no behaviour change can leave the hash
unchanged. Re-verification refuted that: capping the reported entries, capping the host index build,
and filtering currency metabolites each rewrote the real interface map with this digest identical,
because the probe is one small synthetic instance and those changes key on scale and on real BiGG
vocabulary. Those are caught on the answer side, by `result_digest` — see
`tests/test_result_digest.py`. Do not restore the stronger wording here without an argument for why
a fixture can cover a decision point nobody has written yet.
"""

from __future__ import annotations

import argparse
import copy
from typing import Any

import pytest

cobra = pytest.importorskip("cobra")

import cmig.core.host_map as host_map_module  # noqa: E402
from cmig.cli.main import _host_map_hash_components  # noqa: E402
from cmig.core.host_map import build_host_map, host_map_policy  # noqa: E402
from cmig.core.host_map_probe import (  # noqa: E402
    HOST_MAP_BEHAVIOR_PROBE_VERSION,
    matching_behavior_digest,
    probe_host,
    probe_members,
)
from cmig.core.workflow_manifest import compute_workflow_hash  # noqa: E402
from cmig.synthetic_host import build_host_model  # noqa: E402
from cmig.synthetic_pair import build_pair_taxonomy  # noqa: E402

#: The behaviour of the matcher, pinned. This is the canary the *implementation* answers to: any
#: change to what `build_host_map` or `_normalize_metabolite_id` does to the probe fixture lands
#: here, including ones no monkeypatch below can express (the first-wins `setdefault` tie-break in
#: `_host_exchange_index`, the `lower_bound < 0` uptake test, the exact wording of a suggestion
#: written into `host_exchange_map.csv`). Updating it is a deliberate contract change: every
#: published `host_map` and `publication_benchmark` run_hash moves with it, so say so in the
#: changelog. Recapture with `python -m cmig.core.host_map_probe`.
#:
#: Round-5 integration moved it once, deliberately: CC-7's stereochemistry fix changed what
#: `_normalize_metabolite_id` does to the probe's D/L ids, so `map_spec` and every host_map /
#: publication_benchmark run_hash moved with it. That is the gate reporting a real semantic
#: change, not drift — previously published host-map fingerprints no longer reproduce, and the
#: CHANGELOG says so.
PINNED_BEHAVIOR_DIGEST = "sha256:36059e16f8322762d50c8abfcbe6f2542f9410f7e30f6f5f2be2f2d10b425357"


# ── perturbations: one per decision point the verifier attacked ──────────────────
# Each replaces a name `build_host_map` resolves at call time, so it changes what the matcher does
# without touching `map_spec`'s descriptive fields — exactly the shape of the original break.

def _always_first_metabolite(rxn: Any) -> str | None:
    """P-F: `len(mets) == 1` relaxed to `>= 1`, so multi-metabolite reactions become exchanges."""
    mets = list(rxn.metabolites)
    return str(mets[0].id) if mets else None


def _ex_prefix_scan(model: Any) -> list[Any]:
    """P-J: discover exchanges by id prefix instead of the model's own accessor."""
    return [rxn for rxn in model.reactions if str(rxn.id).startswith("EX_")]


def _normalize_without_case_folding(raw: str) -> str:
    """P-G: the normalizer stops case-folding."""
    from cmig.core.namespace import _normalize_metabolite_id

    result = _normalize_metabolite_id(raw)
    return result.upper() if raw[:1].isupper() else result


def _normalize_folding_the_stereo_descriptor(raw: str) -> str:
    """P-H, restated for the policy that now holds: the pre-round-5 normalizer, verbatim.

    The original P-H ("fold a trailing `__<token>` whatever its case") went inert when CC-7 was
    fixed — the fixed normalizer preserves the descriptor in *either* case, so upper-casing the
    input no longer changes the output and the perturbation stopped perturbing anything. The
    decision point it was standing in for is still live and is the P0 itself, so express it
    directly: this is the exact body that collapsed `lac__D` onto `lac__L`. If it ever comes
    back, the digest must move.
    """
    from cmig.core.namespace import NORMALIZE_COMPARTMENT_SUFFIXES, NORMALIZE_EXCHANGE_PREFIX

    x = raw.strip()
    if x.startswith(NORMALIZE_EXCHANGE_PREFIX):
        x = x[len(NORMALIZE_EXCHANGE_PREFIX):]
    if "__" in x and x.rsplit("__", 1)[-1]:
        maybe_member = x.rsplit("__", 1)[-1]
        if maybe_member and maybe_member[0].isupper():
            x = x.rsplit("__", 1)[0]
    for suffix in NORMALIZE_COMPARTMENT_SUFFIXES:
        if x.endswith(suffix):
            x = x[: -len(suffix)]
            break
    return x.lower()


def _secretes_when_reversible(rxn: Any) -> bool:
    """P-I: the criterion the verifier used to drop 56 metabolites under a stable hash."""
    return float(rxn.upper_bound) > 0.0 and float(rxn.lower_bound) < 0.0


def _secretes_when_upper_bound_ge_0(rxn: Any) -> bool:
    """P-A: `> 0` relaxed to `>= 0`, admitting closed exchanges as secretions."""
    return float(rxn.upper_bound) >= 0.0


def _ineligible_when_upper_bound_not_positive(rxn: Any) -> str | None:
    """The break the second verifier found: host-exchange eligibility keyed on the upper bound.

    Routed through `_sole_metabolite_id` because that is the module-level name
    `_host_exchange_index` resolves; returning None excludes the reaction from the index just as
    an inline `if float(rxn.upper_bound) <= 0.0: continue` would. On iAF987 that dropped `ac_e`
    (bounds [-8.88, -6.84]) and `fe3_e` ([-67.37, -49.21]) from the interface map, 40 entries → 38,
    with the run_hash and this digest bit-identical — because every host reaction in the original
    probe fixture had upper_bound=1000.
    """
    if float(rxn.upper_bound) <= 0.0:
        return None
    mets = list(rxn.metabolites)
    return str(mets[0].id) if len(mets) == 1 else None


def _uptake_only_when_fully_open(rxn: Any) -> str | None:
    """An intermediate negative lower bound treated as "not really an uptake"."""
    if -1000.0 < float(rxn.lower_bound) < 0.0:
        return None
    mets = list(rxn.metabolites)
    return str(mets[0].id) if len(mets) == 1 else None


MATCHER_PERTURBATIONS: dict[str, tuple[str, Any]] = {
    "match_order":              ("HOST_MAP_MATCH_ORDER", ("exact", "normalized", "annotation")),
    "secretion_requires_reversible": (
        "_SECRETION_CRITERIA", {"exchange_upper_bound_gt_0": _secretes_when_reversible},
    ),
    "secretion_admits_closed": (
        "_SECRETION_CRITERIA", {"exchange_upper_bound_gt_0": _secretes_when_upper_bound_ge_0},
    ),
    "annotation_uniqueness_dropped": ("HOST_MAP_ANNOTATION_REQUIRES_UNIQUE_TARGET", False),
    "annotation_reaction_fallback_dropped": (
        "HOST_MAP_ANNOTATION_SOURCES", (("metabolite", "bigg.metabolite"),),
    ),
    "sole_metabolite_rule_relaxed": ("_sole_metabolite_id", _always_first_metabolite),
    # Bound regimes — the blind spot the second verifier found and the fixture now covers.
    "host_eligibility_by_upper_bound": (
        "_sole_metabolite_id", _ineligible_when_upper_bound_not_positive,
    ),
    "uptake_must_be_fully_open": ("_sole_metabolite_id", _uptake_only_when_fully_open),
    "exchange_discovery_by_prefix": ("_iter_exchanges", _ex_prefix_scan),
    "normalizer_stops_case_folding": ("_normalize_metabolite_id",
                                      _normalize_without_case_folding),
    "normalizer_folds_the_stereo_descriptor": ("_normalize_metabolite_id",
                                               _normalize_folding_the_stereo_descriptor),
    "suggestion_wording": (
        "_MATCH_SUGGESTIONS",
        {
            "exact": lambda host_ex, can_uptake: "reworded exact note",
            "annotation": lambda host_ex, can_uptake: "reworded annotation note",
            "normalized": lambda host_ex, can_uptake: "reworded normalized note",
        },
    ),
}


@pytest.fixture
def host_map_inputs(tmp_path):
    """A host model and a two-member pool on disk, as `_host_map_hash_components` reads them."""
    taxonomy = build_pair_taxonomy(tmp_path / "microbes")
    taxonomy_path = tmp_path / "taxonomy.csv"
    taxonomy.to_csv(taxonomy_path, index=False)
    host_path = tmp_path / "host.xml"
    cobra.io.write_sbml_model(build_host_model(), str(host_path))
    return {"taxonomy": taxonomy_path, "host": host_path}


def _host_map_hash(host_map_inputs) -> str:
    import pandas as pd

    args = argparse.Namespace(
        host=str(host_map_inputs["host"]), taxonomy=str(host_map_inputs["taxonomy"]),
        model_dir=None, recursive=False, out="unused",
    )
    taxonomy = pd.read_csv(host_map_inputs["taxonomy"])
    components = _host_map_hash_components(
        args, taxonomy, host_map_inputs["taxonomy"].parent
    )
    return compute_workflow_hash("host_map", components)


# ── the digest exists and is stable ──────────────────────────────────────────────

def test_map_spec_records_the_matching_behaviour_it_ran():
    behavior = host_map_policy()["match_behavior"]
    assert behavior["probe_version"] == HOST_MAP_BEHAVIOR_PROBE_VERSION
    assert behavior["digest"].startswith("sha256:") and len(behavior["digest"]) == 71


def test_the_digest_is_deterministic_and_never_served_from_a_stale_cache():
    assert matching_behavior_digest() == matching_behavior_digest()
    assert host_map_policy()["match_behavior"]["digest"] == matching_behavior_digest()


def test_the_pinned_behaviour_digest_has_not_moved():
    """The canary. A move here means every published host-map fingerprint moved with it."""
    assert matching_behavior_digest() == PINNED_BEHAVIOR_DIGEST, (
        "host-map matching behaviour changed. If that is intended, update "
        "PINNED_BEHAVIOR_DIGEST, re-bless the envelope golden, and record in the changelog that "
        "previously published host_map / publication_benchmark run_hashes no longer reproduce."
    )


# ── the P0: a behaviour change must move the fingerprint ─────────────────────────

@pytest.mark.parametrize("case", sorted(MATCHER_PERTURBATIONS))
def test_a_matcher_change_moves_the_behaviour_digest(case, monkeypatch):
    attribute, replacement = MATCHER_PERTURBATIONS[case]
    baseline = matching_behavior_digest()
    monkeypatch.setattr(host_map_module, attribute, replacement)
    assert matching_behavior_digest() != baseline, (
        f"{case} changes what the matcher does but the behaviour digest did not notice"
    )


@pytest.mark.parametrize("case", sorted(MATCHER_PERTURBATIONS))
def test_a_matcher_change_moves_the_host_map_run_hash(case, monkeypatch, host_map_inputs):
    """The end-to-end property: the published fingerprint moves, not merely an internal digest."""
    attribute, replacement = MATCHER_PERTURBATIONS[case]
    baseline = _host_map_hash(host_map_inputs)
    monkeypatch.setattr(host_map_module, attribute, replacement)
    assert _host_map_hash(host_map_inputs) != baseline, (
        f"{case} changes the interface map this run publishes, under an unchanged run_hash"
    )


def test_the_descriptive_map_spec_fields_are_no_longer_the_only_guard(monkeypatch):
    """A matcher change must move `map_spec` even when every described field stays identical."""
    baseline = copy.deepcopy(host_map_policy())
    monkeypatch.setattr(host_map_module, "_SECRETION_CRITERIA",
                        {"exchange_upper_bound_gt_0": _secretes_when_reversible})
    perturbed = host_map_policy()
    described = [
        "match_policy_version", "match_order", "interface_map_admits",
        "needs_review_match_types", "annotation_sources",
        "annotation_requires_unique_target", "secretion_criterion", "id_normalization",
    ]
    assert all(perturbed[key] == baseline[key] for key in described), (
        "this test is only meaningful while the described fields are unchanged"
    )
    assert perturbed != baseline
    assert perturbed["match_behavior"] != baseline["match_behavior"]


# ── the constants the manifest names are the constants the matcher obeys ─────────

def test_the_recorded_match_order_is_the_order_that_runs(monkeypatch):
    """`xmet_e` is reachable by all three strategies, each pointing at a different exchange."""
    def matched(order: tuple[str, ...]) -> tuple[str, str | None]:
        monkeypatch.setattr(host_map_module, "HOST_MAP_MATCH_ORDER", order)
        entry = next(
            e for e in build_host_map(probe_host(), probe_members()).entries
            if e.metabolite == "xmet_e"
        )
        return entry.match_type, entry.host_exchange

    assert matched(("exact", "annotation", "normalized")) == ("exact", "EX_xmet_e")
    assert matched(("annotation", "normalized", "exact")) == ("annotation", "HOSTX_ann")
    assert matched(("normalized", "exact", "annotation")) == ("normalized", "EX_xmet_m")


def test_the_recorded_secretion_criterion_names_the_predicate_that_runs(monkeypatch):
    baseline = build_host_map(probe_host(), probe_members()).n_microbial_secretions
    monkeypatch.setattr(host_map_module, "_SECRETION_CRITERIA",
                        {"exchange_upper_bound_gt_0": _secretes_when_reversible})
    assert build_host_map(probe_host(), probe_members()).n_microbial_secretions != baseline


def test_the_recorded_annotation_policy_drives_the_annotation_index(monkeypatch):
    by_metabolite = {e.metabolite: e for e in build_host_map(probe_host(), probe_members()).entries}
    assert by_metabolite["ambig_e"].match_type == "unmatched"      # unique-target required
    assert by_metabolite["fbk_e"].match_type == "annotation"       # reaction-level fallback

    monkeypatch.setattr(host_map_module, "HOST_MAP_ANNOTATION_REQUIRES_UNIQUE_TARGET", False)
    relaxed = {e.metabolite: e for e in build_host_map(probe_host(), probe_members()).entries}
    assert relaxed["ambig_e"].match_type == "annotation"

    monkeypatch.setattr(host_map_module, "HOST_MAP_ANNOTATION_SOURCES",
                        (("metabolite", "bigg.metabolite"),))
    without_fallback = {
        e.metabolite: e for e in build_host_map(probe_host(), probe_members()).entries
    }
    assert without_fallback["fbk_e"].match_type == "unmatched"


# ── the guard on the guard: the probe fixture must keep biting ───────────────────

def test_the_probe_fixture_still_distinguishes_every_decision_point():
    """The digest only sees what the fixture exercises; narrowing it must fail here.

    One assertion per decision point the round-5 perturbation matrix attacked, written as the
    observable consequence rather than as source text.
    """
    result = build_host_map(probe_host(), probe_members())
    entries = {entry.metabolite: entry for entry in result.entries}
    seen = set(entries)

    # secretion criterion: reversible and secretion-only in, uptake-only / closed / negative out.
    assert {"ac_e", "rev_e"} <= seen
    assert not {"upt_e", "closed_e", "negub_e"} & seen
    # match order: one metabolite reachable by all three strategies, distinct targets each …
    assert entries["xmet_e"].match_type == "exact"
    assert entries["xmet_e"].host_exchange == "EX_xmet_e"
    # … and one reachable by annotation *and* normalized with no exact match masking the choice.
    # That is the real break's shape: the D/L needs-review entries are reachable both ways.
    assert entries["ord_e"].match_type == "annotation"
    assert entries["ord_e"].host_exchange == "HOSTX_ord"
    # first-wins `setdefault` tie-break in the exact index (last-wins would give EX_tie_alt/False).
    assert entries["tie_e"].host_exchange == "EX_tie_e" and entries["tie_e"].host_can_uptake
    # host_can_uptake is `lower_bound < 0`, not `<= 0`.
    assert entries["ac_e"].host_can_uptake and not entries["but_e"].host_can_uptake
    # annotation index: unique target required, reaction level used only as a fallback.
    assert entries["ambig_e"].match_type == "unmatched"
    assert entries["fbk_e"].match_type == "annotation"
    # id normalization: case folding, stereo-descriptor PRESERVATION, compartment suffixes.
    assert entries["MixedCase_e"].match_type == "normalized"
    # CC-7: the host offers bare `ste_e`. A normalizer that folds `__D` matches it and hands a
    # reviewed D-isomer mapping to L-isomer availability; the fixed one cannot reach it. Both
    # cases are pinned because case is no longer what decides — length/descriptor identity is.
    assert entries["ste__D_e"].match_type == "unmatched"
    assert entries["ste__d_e"].match_type == "unmatched"
    assert entries["sfx_c"].host_exchange == "EX_sfx_lumen"
    # exchange discovery: the model's accessor, not an `EX_` prefix scan.
    assert entries["hx_e"].host_exchange == "TRANS_hx"     # in `exchanges`, not `EX_`-prefixed
    assert entries["ghost_e"].match_type == "unmatched"    # `EX_`-prefixed, not in `exchanges`
    # "exactly one metabolite" rule.
    assert not {"multi_a_e", "multi_b_e"} & seen
    # host bound regimes: a non-positive host upper bound and an intermediate negative uptake
    # bound must both be *reachable* in the fixture, or no rule keyed on them can be observed.
    # These are the real iAF987 bounds that produced the second verifier's break.
    host = {rxn.id: rxn for rxn in probe_host().reactions}
    assert float(host["EX_nposub_e"].upper_bound) < 0.0
    assert float(host["EX_zeroub_e"].upper_bound) == 0.0
    assert -1000.0 < float(host["EX_midlb_e"].lower_bound) < 0.0
    assert entries["nposub_e"].host_exchange == "EX_nposub_e"
    assert entries["zeroub_e"].host_exchange == "EX_zeroub_e"
    assert entries["midlb_e"].host_exchange == "EX_midlb_e"
    # the `_iter_exchanges` fallback branch, taken by the member with no `exchanges` accessor.
    assert entries["ac_e"].secreting_members == ["probe_member_a", "probe_member_b"]
    assert "tx_e" not in seen                              # fallback keeps the `EX_` rule
    # warnings are part of the artifact and part of the digest.
    assert len(result.warnings) == 3
