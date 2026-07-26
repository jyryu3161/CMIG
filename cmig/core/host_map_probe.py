"""Behavioural fingerprint of the host-map matcher (the guard `map_spec` descriptions are not).

`map_spec` used to certify `build_host_map`'s answer by *describing* its rules — `match_order`,
`secretion_criterion`, `annotation_requires_unique_target`, `annotation_sources` were string and
boolean literals, and the only thing standing between an edited matcher and an unchanged
fingerprint was a hand-bumped `HOST_MAP_MATCH_POLICY_VERSION`. Round-5 verification broke that
end-to-end: changing one comparison in `build_host_map` moved the produced interface map from 67
entries to 11 while `run_hash` stayed bit-identical, and the manifest's own
`summary.interface_map_checksum` moved underneath it — the artifact contradicted itself.

This module closes that gap by *measuring* the matcher instead of describing it. It runs the real
`build_host_map` (and the real id normalizer) over a frozen synthetic host and pool, and hashes
everything they produced. Any change to what the matcher does to these inputs changes the digest,
which changes `map_spec`, which changes the host-map `run_hash` — with no version to remember.

Why a behavioural probe rather than a source fingerprint (`inspect.getsource`):

* **Source text is not behaviour.** A reflowed line, a fixed typo in a comment, or a clarified
  docstring would move every previously published host-map hash. A fingerprint that fires on
  cosmetics trains its readers to ignore it, and the one time it means something they re-bless
  reflexively. This digest is invariant to comments, formatting and docstrings, and moves only when
  an answer changes.
* **Source is not guaranteed to exist at runtime.** `inspect.getsource` needs the `.py` file
  (through `linecache` → `loader.get_source`). It works from a wheel and from a zipimport, but it
  raises `OSError` on any distribution that ships bytecode only. The envelope golden was
  deliberately shipped *inside the package* so the gate could not silently skip on a trimmed
  install; a fingerprint that can raise on the same install would reintroduce exactly that hole.
  This probe needs only the imported module objects.
* **Bytecode and AST fingerprints trade one fragility for a worse one.** `co_code` changes between
  CPython releases and `co_consts` carries docstrings that `python -OO` strips, so the same code
  would fingerprint differently per interpreter and per optimisation flag. `ast.dump` output has
  gained fields across versions with the same effect. This probe is pure dict/list/float work over
  stub objects: same answer on every interpreter, under `-O` and `-OO`, from a wheel or a zipapp.

**The cost of measuring rather than reading is coverage, and it is a real limit, not a caveat.**
The digest sees only what the probe exercises. The fixture below is built directly from the ten
perturbations round-5 verification constructed against the matcher, one designed case per decision
point, and `tests/test_host_map_behavior_digest.py` asserts each case is still distinguishable —
weakening the fixture fails a test. But a fixture can only cover decision points somebody has
already written, and this one is a single small instance (~16 secretions, invented ids), so
anything keyed on *scale* or on *real BiGG vocabulary* is structurally invisible to it.
Re-verification demonstrated three such changes — capping reported entries, capping the host index
build, filtering currency metabolites — each rewriting the real interface map on real GEMs
(67 entries → 22, → 62; 144 → 73 on a larger host) with this digest bit-identical.

So this module is **half** of the guarantee, not the whole of it. The other half is
`result_digest` (`cmig.core.workflow_manifest.artifact_result_digest`), which fingerprints the
artifact bytes a run produced rather than its inputs, and which `cmig inspect-run` re-derives from
disk. Certifying an implementation from the input side cannot be completed; certifying the answer
can. Note also the asymmetry in how the two candidate input-side mechanisms fail: a source
fingerprint's failure mode is false positives (annoying, safe), a behaviour probe's is false
negatives (silent, unsafe) — which is why this one is not relied on alone.

The stubs are duck-typed, not cobra models: `build_host_map` only ever reads `.exchanges`,
`.reactions`, `.id`, `.metabolites`, `.lower_bound`, `.upper_bound` and `.annotation`, so the probe
costs microseconds and adds no engine dependency to manifest emission.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

#: Bumped when the probe fixture below is deliberately extended. It is recorded next to the digest
#: so a digest move caused by *widening the guard* is distinguishable from one caused by a change
#: in the science.
HOST_MAP_BEHAVIOR_PROBE_VERSION = "1.0"


@dataclass(frozen=True)
class _ProbeMetabolite:
    id: str
    annotation: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _ProbeReaction:
    id: str
    lower_bound: float
    upper_bound: float
    metabolites: tuple[_ProbeMetabolite, ...]
    annotation: dict[str, Any] = field(default_factory=dict)


class _ProbeModel:
    """A model that exposes a cobra-style `exchanges` accessor distinct from `reactions`."""

    def __init__(self, reactions: tuple[_ProbeReaction, ...], exchange_ids: tuple[str, ...]):
        self.reactions = list(reactions)
        self._exchange_ids = set(exchange_ids)

    @property
    def exchanges(self) -> list[_ProbeReaction]:
        return [rxn for rxn in self.reactions if rxn.id in self._exchange_ids]


class _ProbeModelWithoutExchanges:
    """A model with no `exchanges` accessor, so `_iter_exchanges` must take its fallback branch."""

    def __init__(self, reactions: tuple[_ProbeReaction, ...]):
        self.reactions = list(reactions)

    @property
    def exchanges(self) -> list[_ProbeReaction]:
        raise AttributeError("this probe model deliberately has no exchanges accessor")


def _met(met_id: str, annotation: dict[str, Any] | None = None) -> _ProbeMetabolite:
    return _ProbeMetabolite(id=met_id, annotation=dict(annotation or {}))


def _rxn(
    rxn_id: str,
    lb: float,
    ub: float,
    metabolites: tuple[_ProbeMetabolite, ...],
    annotation: dict[str, Any] | None = None,
) -> _ProbeReaction:
    return _ProbeReaction(
        id=rxn_id,
        lower_bound=lb,
        upper_bound=ub,
        metabolites=metabolites,
        annotation=dict(annotation or {}),
    )


# ── the frozen probe fixture ───────────────────────────────────────────────────
# Each entry is annotated with the matcher decision it makes observable. Removing one narrows the
# guarantee, so `tests/test_host_map_behavior_digest.py` asserts every one of them still bites.

_HOST_REACTIONS: tuple[_ProbeReaction, ...] = (
    # host_can_uptake is `lower_bound < 0`: an open and a closed uptake, so `<` vs `<=` shows up.
    _rxn("EX_ac_e", -1000.0, 1000.0, (_met("ac_e"),)),
    _rxn("EX_but_e", 0.0, 1000.0, (_met("but_e"),)),
    # first-wins `setdefault` tie-break: two exchanges claiming the same metabolite id, with
    # different uptake capability, so first-wins and last-wins produce different entries.
    _rxn("EX_tie_e", -1000.0, 1000.0, (_met("tie_e"),)),
    _rxn("EX_tie_alt", 0.0, 1000.0, (_met("tie_e"),)),
    # match-order revealer: `xmet_e` is reachable by all three strategies, each pointing at a
    # different host exchange, so the applied priority is readable straight off the entry.
    _rxn("EX_xmet_m", -1000.0, 1000.0, (_met("xmet_m"),)),          # normalized -> xmet
    _rxn("EX_xmet_e", 0.0, 1000.0, (_met("xmet_e"),)),              # exact       -> xmet_e
    _rxn("HOSTX_ann", -1000.0, 1000.0,                              # annotation  -> xmet
         (_met("MAMxmet", {"bigg.metabolite": "xmet"}),)),
    # annotation-vs-normalized priority with no exact match to mask it. This is the shape of the
    # real break: on iHN637/iYO844 the six D/L stereoisomer needs-review entries are reachable both
    # ways, and swapping the two strategies relabels every one of them.
    _rxn("EX_ord_m", -1000.0, 1000.0, (_met("ord_m"),)),            # normalized -> ord
    _rxn("HOSTX_ord", -1000.0, 1000.0,                              # annotation -> ord
         (_met("MAMord", {"bigg.metabolite": "ord"}),)),
    # annotation uniqueness: two host exchanges claim the same BiGG id, so requiring a unique
    # target drops the candidate and dropping that requirement admits the first.
    _rxn("EX_ambig1", -1000.0, 1000.0, (_met("AMB1", {"bigg.metabolite": "ambig"}),)),
    _rxn("EX_ambig2", 0.0, 1000.0, (_met("AMB2", {"bigg.metabolite": "ambig"}),)),
    # reaction-level annotation fallback: no metabolite cross-reference, only a reaction one.
    _rxn("MAR_fbk", -1000.0, 1000.0, (_met("MAM_fbk"),),
         {"bigg.reaction": "EX_fbk_e"}),
    # case folding in the normalizer.
    _rxn("EX_mixedcase_e", -1000.0, 1000.0, (_met("mixedcase_e"),)),
    # stereo-descriptor preservation: the host offers the *bare* metabolite. A normalizer that
    # folds `ste__D` onto `ste` matches here; the correct one leaves both member entries
    # unmatched. So this one host reaction is what makes the round-5 P0 observable at entry level.
    _rxn("EX_ste_e", -1000.0, 1000.0, (_met("ste_e"),)),
    # compartment-suffix stripping beyond `_e`.
    _rxn("EX_sfx_lumen", -1000.0, 1000.0, (_met("sfx_lumen"),)),
    # exchange discovery: in `exchanges` but not `EX_`-prefixed …
    _rxn("TRANS_hx", -1000.0, 1000.0, (_met("hx_e"),)),
    # … and `EX_`-prefixed but not in `exchanges`.
    _rxn("EX_ghost_e", -1000.0, 1000.0, (_met("ghost_e"),)),
    # "exactly one metabolite" rule: a two-metabolite reaction is not an exchange.
    _rxn("EX_multi_e", -1000.0, 1000.0, (_met("multi_a_e"), _met("multi_b_e"))),
    # ── host bound regimes ────────────────────────────────────────────────────
    # Independent verification broke the probe here: every host reaction above uses
    # upper_bound=1000 and lower_bound in {-1000, 0}, so no host-index rule keyed on a
    # *non-positive host upper bound* or an *intermediate negative uptake bound* could be
    # observed — and a one-line host-exchange eligibility change (`skip if upper_bound <= 0`)
    # dropped `ac_e` and `fe3_e` from the real iAF987 map, 40 entries → 38, with this digest
    # bit-identical. Those regimes are not hypothetical: iAF987 ships `EX_ac_e` at [-8.88, -6.84]
    # and `EX_fe3_e` at [-67.37, -49.21], and iSFV_1184 has `EX_cbl1_e` in the same class. The
    # bounds below are those real ones.
    _rxn("EX_nposub_e", -8.88, -6.84, (_met("nposub_e"),)),      # negative upper bound
    _rxn("EX_zeroub_e", -67.37, 0.0, (_met("zeroub_e"),)),       # upper bound exactly 0
    _rxn("EX_midlb_e", -12.5, 1000.0, (_met("midlb_e"),)),       # intermediate negative lb
)

#: Everything except `EX_ghost_e` — which exists only to be *missed* by the exchanges accessor.
_HOST_EXCHANGE_IDS: tuple[str, ...] = tuple(
    rxn.id for rxn in _HOST_REACTIONS if rxn.id != "EX_ghost_e"
)

_MEMBER_A_REACTIONS: tuple[_ProbeReaction, ...] = (
    _rxn("EX_ac_e", 0.0, 1000.0, (_met("ac_e"),)),              # secretion-only
    _rxn("EX_rev_e", -1000.0, 1000.0, (_met("rev_e"),)),        # reversible
    _rxn("EX_upt_e", -1000.0, 0.0, (_met("upt_e"),)),           # uptake-only  -> not a secretion
    _rxn("EX_closed_e", 0.0, 0.0, (_met("closed_e"),)),         # closed       -> `> 0` vs `>= 0`
    _rxn("EX_negub_e", -1000.0, -1.0, (_met("negub_e"),)),      # negative ub  -> `> 0` vs `!= 0`
    _rxn("EX_xmet_e", 0.0, 1000.0, (_met("xmet_e"),)),
    _rxn("EX_ord_e", 0.0, 1000.0, (_met("ord_e"),)),            # annotation vs normalized
    _rxn("EX_tie_e", 0.0, 1000.0, (_met("tie_e"),)),
    _rxn("EX_ambig_e", 0.0, 1000.0, (_met("ambig_e"),)),
    _rxn("EX_fbk_e", 0.0, 1000.0, (_met("fbk_e"),)),
    _rxn("EX_MixedCase_e", 0.0, 1000.0, (_met("MixedCase_e"),)),
    # Both must stay `ste__d` and so stay unmatched against the host's bare `ste_e`: the uppercase
    # one because the descriptor is part of the identity, the lowercase one because case is not
    # what decides. Either matching `EX_ste_e` means the D/L-collapsing normalizer is back.
    _rxn("EX_ste__D_e", 0.0, 1000.0, (_met("ste__D_e"),)),
    _rxn("EX_ste__d_e", 0.0, 1000.0, (_met("ste__d_e"),)),
    _rxn("EX_sfx_c", 0.0, 1000.0, (_met("sfx_c"),)),
    _rxn("EX_hx_e", 0.0, 1000.0, (_met("hx_e"),)),
    _rxn("EX_ghost_e", 0.0, 1000.0, (_met("ghost_e"),)),
    _rxn("EX_multi_e", 0.0, 1000.0, (_met("multi_a_e"), _met("multi_b_e"))),
    _rxn("EX_novel_e", 0.0, 1000.0, (_met("novel_e"),)),        # unmatched -> warning text
    # Counterparts for the host bound regimes above, so those host exchanges are actually reached.
    _rxn("EX_nposub_e", 0.0, 1000.0, (_met("nposub_e"),)),
    _rxn("EX_zeroub_e", 0.0, 1000.0, (_met("zeroub_e"),)),
    _rxn("EX_midlb_e", 0.0, 1000.0, (_met("midlb_e"),)),
)

#: A second member so the multi-member merge (shared secretion, sorted `secreting_members`) and the
#: `_iter_exchanges` fallback branch are both exercised.
_MEMBER_B_REACTIONS: tuple[_ProbeReaction, ...] = (
    _rxn("EX_ac_e", 0.0, 1000.0, (_met("ac_e"),)),
    _rxn("EX_but_e", 0.0, 1000.0, (_met("but_e"),)),
    _rxn("TRANSPORT_x", 0.0, 1000.0, (_met("tx_e"),)),          # not `EX_`-prefixed
)

#: Ids pushed through the normalizer directly, so a normalizer change is caught at full
#: sensitivity rather than only where it happens to change a match. The D/L pairs are here
#: deliberately: folding them is the round-2 stereoisomer hazard, and any fix to it *must* move
#: every published host-map hash — which is exactly what round 5 did when CC-7 was closed.
_NORMALIZATION_PROBE_IDS: tuple[str, ...] = (
    "ac_e", "EX_ac_e", "EX_glc__D_e",
    "lac__D_e", "lac__L_e", "glc__D_e", "arab__L_e", "ala__D_e",
    "MixedCase_e", "UPPER_E",
    "x_lumen", "y_blood", "z_p", "w_c", "v_m", "u_e",
    "ste__d_e", "ste__D", "ste__RR", "trailing__", "EX_", "plain",
)


def probe_host() -> _ProbeModel:
    return _ProbeModel(_HOST_REACTIONS, _HOST_EXCHANGE_IDS)


def probe_members() -> dict[str, Any]:
    return {
        "probe_member_a": _ProbeModel(
            _MEMBER_A_REACTIONS, tuple(rxn.id for rxn in _MEMBER_A_REACTIONS)
        ),
        "probe_member_b": _ProbeModelWithoutExchanges(_MEMBER_B_REACTIONS),
    }


def probe_observations() -> list[Any]:
    """Everything the matcher produced for the frozen fixture, as JSON-serialisable data.

    Imports are deferred to call time so importing this module never re-enters
    :mod:`cmig.core.host_map` while that module is still initialising, and — more importantly —
    so the names resolved here are the ones the matcher *actually* uses, which is what makes a
    swapped-out helper visible to the digest.
    """
    from cmig.core import host_map

    result = host_map.build_host_map(probe_host(), probe_members())
    # Resolved through the module dict rather than imported, so the id vector below fingerprints
    # the *binding the matcher resolves* — swap the normalizer out from under `host_map` and this
    # sees it. (A plain `from … import` would bind the original and miss exactly that.)
    normalize = host_map.__dict__["_normalize_metabolite_id"]
    return [
        ["counts", {
            "n_microbial_secretions": result.n_microbial_secretions,
            "n_exact": result.n_exact,
            "n_annotation": result.n_annotation,
            "n_normalized": result.n_normalized,
            "n_unmatched": result.n_unmatched,
            "n_host_uptake_capable": result.n_host_uptake_capable,
        }],
        # Every field of every entry: the CSV, the interface map and the needs-review reasons are
        # all built from these, so anything a reader could act on is inside the digest.
        ["entries", [
            [
                entry.metabolite,
                entry.microbial_exchange,
                list(entry.secreting_members),
                entry.host_exchange,
                entry.match_type,
                bool(entry.host_can_uptake),
                entry.suggestion,
            ]
            for entry in result.entries
        ]],
        ["warnings", list(result.warnings)],
        ["id_normalization", [
            [raw, normalize(raw)] for raw in _NORMALIZATION_PROBE_IDS
        ]],
    ]


def matching_behavior_digest() -> str:
    """`sha256:…` over everything the matcher did to the frozen probe fixture.

    Deliberately uncached: it costs microseconds, it is computed once per manifest emission, and a
    cache would hand back a stale answer to the tests that verify the digest actually tracks the
    implementation.
    """
    payload = json.dumps(
        probe_observations(), sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def match_behavior_component() -> dict[str, Any]:
    """The `map_spec` sub-object that makes the matching behaviour a determining input."""
    return {
        "probe_version": HOST_MAP_BEHAVIOR_PROBE_VERSION,
        "digest": matching_behavior_digest(),
    }


if __name__ == "__main__":  # pragma: no cover - convenience for re-pinning the canary
    print(matching_behavior_digest())
