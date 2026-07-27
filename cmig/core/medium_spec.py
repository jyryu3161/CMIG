"""C6 — Medium 입력/preset. Design Ref(foundations): §4. Plan SC: SC-F3·F4.

사용자가 배지(diet)를 지정해 community solve 입력으로 쓸 수 있는 기반.
- MediumSpec: {exchange_id: uptake_limit} where uptake_limit >= 0 (흡수 허용 magnitude, 부호 없음).
- apply_medium: **MICOM public API `community.medium`** (양수 dict) 에 설정 — 자체 bound 조작 금지.
- medium_checksum: 결정적 해시 → run_hash medium_checksum 구성요소(§4.2)에 반영(재현성).
csv(`exchange_id,uptake_limit`) / json 입력 (pyyaml 비의존).
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

_DECIMALS = 6

# Round 5 (blocker 5): the CC-11 fix changes the numbers a `--medium` run produces WITHOUT moving
# `run_hash` — measured, identical inputs, identical hash: solve growth 0.881561 -> 1.125065
# (hash 6960d9ca9412a572…), search target flux 18.13 -> 13.64 (hash cf395ca787e9957b…). A
# previously published hash therefore now maps to a different number. It cannot be recorded by
# bumping a hash component (`cmig_core_version` is frozen), so it is stamped into the manifest's
# **non-hashed** `provenance` block instead: enough to tell the two eras apart mechanically,
# without touching the frozen contract. See the CHANGELOG entry.
MEDIUM_POLICY = "exchange_reactions_by_metabolite_v2"   # was: open_uptakes_exact_key_v1

# Round 6 (track B, instances 1 and 3): a medium is applied in exactly one of two modes, and they
# give **different answers on identical input**, so which one ran has to travel with the result.
#
#   merge  — the requested uptakes are added on top of whatever the model already offers. MICOM's
#            default community medium is permissive, so this leaves undeclared nutrients open;
#            measured on iML1515+iYO844+iHN637 with the shipped `western_diet.csv`, `EX_o2_m`
#            stayed at 999999 and community growth came out 1.2677557 against 0.6990206751 with
#            oxygen closed — an 81 % overestimate from one absent row.
#   exact  — the requested uptakes are the model's ONLY mass sources. Every other boundary
#            reaction that could supply mass is closed, `model.boundary` included, so this is a
#            defined medium rather than an overlay.
#
# `exact` used to be a lie: it delegated to cobra's `Model.medium` setter, which does
# `frozenset(self.exchanges)` and cannot close a sink or a demand. It now goes through
# `cmig.core.boundary`, which is written against `model.boundary`.
MEDIUM_APPLICATION_MERGE = "merge_onto_model_default"
MEDIUM_APPLICATION_EXACT = "exact_boundary_isolation"


@dataclass(frozen=True)
class MediumSpec:
    """배지 사양 — exchange 별 흡수 허용량(uptake_limit >= 0)."""

    uptake: dict[str, float]

    def validate(self) -> None:
        for ex, v in self.uptake.items():
            if not isinstance(ex, str) or not ex:
                raise ValueError(f"빈 exchange_id (medium): {ex!r}")
            if not math.isfinite(v) or v < 0:
                raise ValueError(f"uptake_limit 은 유한·≥0 이어야 함 ({ex}={v}) [§4]")
        self._reject_contradictory_aliases()

    def _reject_contradictory_aliases(self) -> None:
        """Two ids for one metabolite must not request different limits.

        Round 5 (blocker 1). ``EX_ac_e`` and ``EX_ac_m`` name the same molecule, so under the
        metabolite-keyed medium semantics they resolve to a single exchange — whichever row came
        last silently won, and reordering identical CSV rows moved community growth 1.125065 ->
        0.954612 while ``medium_checksum`` (which sorts, and hashes both rows) stayed identical.

        The contradiction is a property of the *request*, not of any particular model, so it is
        caught here at load/validate time. That makes it a clean input error (exit 2) on every
        subcommand rather than a per-candidate analysis failure buried in diagnostics.
        Aliases that agree are not contradictory and are merged downstream.
        """
        by_metabolite: dict[str, dict[str, float]] = {}
        for exchange, limit in self.uptake.items():
            by_metabolite.setdefault(exchange_metabolite(str(exchange)), {})[str(exchange)] = float(
                limit
            )
        conflicts = [
            f"{metabolite} <- {{"
            + ", ".join(f"{source}={sources[source]!r}" for source in sorted(sources))
            + "}"
            for metabolite, sources in sorted(by_metabolite.items())
            if len(set(sources.values())) > 1
        ]
        if conflicts:
            raise ValueError(
                "medium spec requests conflicting uptake limits for the same metabolite "
                f"(namespace aliases): {conflicts}. Resolve the duplicate rows — refusing rather "
                "than silently picking one, because the choice would change the result without "
                "changing the medium checksum."
            )


def load_medium(path: str | Path) -> MediumSpec:
    """csv(exchange_id,uptake_limit) 또는 json({exchange_id: uptake_limit}) → MediumSpec."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"medium file not found: {p}")
    uptake: dict[str, float] = {}
    if p.suffix == ".json":
        # AF-2: 중복 키 fail-fast (object_pairs_hook — CSV 경로와 대칭).
        def _no_dup(pairs: list[tuple[str, object]]) -> dict[str, object]:
            d: dict[str, object] = {}
            for k, v in pairs:
                if k in d:
                    raise ValueError(f"medium json 중복 exchange_id: {k}")
                d[k] = v
            return d

        raw = json.loads(p.read_text(), object_pairs_hook=_no_dup)
        if not isinstance(raw, dict):
            raise ValueError("medium json 은 {exchange_id: uptake_limit} 객체여야 함")
        for k, v in raw.items():
            if isinstance(v, bool):       # AF-3: bool→float silent 강제 차단(float(True)=1.0)
                raise ValueError(f"uptake_limit 은 숫자여야 함(bool 불가): {k}={v}")
            uptake[str(k)] = float(v)
    elif p.suffix == ".csv":
        with open(p, newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None or "exchange_id" not in reader.fieldnames \
                    or "uptake_limit" not in reader.fieldnames:
                raise ValueError("medium csv 헤더는 exchange_id,uptake_limit 필요")
            for row in reader:
                ex = (row["exchange_id"] or "").strip()
                if not ex:
                    continue
                if ex in uptake:
                    raise ValueError(f"medium csv 중복 exchange_id: {ex}")
                uptake[ex] = float(row["uptake_limit"])
    else:
        raise ValueError(f"미지원 medium 확장자: {p.suffix} (.csv/.json)")
    spec = MediumSpec(uptake=uptake)
    spec.validate()
    return spec


def apply_medium(community: object, spec: MediumSpec) -> dict[str, float]:
    """community.medium(MICOM public API)에 spec 적용. 원래 medium 반환(undo).

    대상 모델이 **exchange 반응을 실제로 가진** 대사체만 설정한다. 대응 exchange 가 아예 없는
    대사체는 기본적으로 fail-fast 이며, 호출자가 `strict=False` 를 선택한 경우에만 무시한다.
    uptake_limit 은 그대로 MICOM medium 양수값으로 사용(부호 변환 불요).
    """
    return apply_medium_checked(community, spec, strict=True)[0]


def unknown_medium_exchanges(community: object, spec: MediumSpec) -> list[str]:
    """medium spec 중 대상 모델에 대응 exchange **반응**이 없는 exchange 목록.

    ``community.medium`` 은 *현재 열려 있는* uptake 만 나열하므로 "이 모델이 제공할 수 있는가"
    판정에 쓸 수 없다 — 닫힌 exchange 도 medium 으로 열 수 있어야 하기 때문이다.
    :func:`apply_medium_checked` 와 정확히 같은 판정을 쓴다(둘이 어긋나면 pre-flight 가 거짓말을
    하게 된다).
    """
    spec.validate()
    return list(translate_medium_for_model(community, spec).unmatched)


def medium_application_report(
    community: object, spec: MediumSpec, *, strict: bool = True, exact: bool = False
) -> MediumTranslation:
    """Apply ``spec`` and return the full record of how it was applied.

    Same single code path as :func:`apply_medium_checked` — this is the entry point for callers
    that publish provenance (``solve``, ``search``), which need
    :meth:`MediumTranslation.as_provenance` and not just the unmatched list. Round 6: two
    functions that apply a medium differently is how the product ended up with two medium
    semantics in the first place, so there is exactly one implementation and two views of it.
    """
    return apply_medium_translated(community, spec, strict=strict, exact=exact)


def apply_medium_checked(
    community: object, spec: MediumSpec, *, strict: bool = True, exact: bool = False
) -> tuple[dict[str, float], list[str]]:
    """community.medium 에 spec 적용 + 미적용(대응 exchange 부재) exchange 목록 반환.

    strict=True 이면 대응 exchange 가 없는 대사체를 ValueError 로 차단한다. strict=False 는 CLI의
    `--allow-unknown-medium` 같은 명시 옵션에서만 사용하며, 반환된 unknown 목록을 diagnostic에
    기록해야 한다.

    P0(round 5): 예전 구현은 ``dict(community.medium)`` 의 키를 "모델이 아는 exchange" 로 삼았다.
    그 속성은 *현재 열린 uptake* 만 나열하므로 **닫힌 exchange 는 절대 열 수 없었고**(실측:
    2-member community 의 257 개 ``EX_*_m`` 중 26 개만 해당), acetate·butyrate·lactate·succinate·
    glycerol 등 대부분의 SCFA/탄소원이 strict 에서는 거짓 오류로, permissive 에서는 조용히
    누락됐다. 그러면서 manifest 는 요청된 medium_checksum 과 고유 run_hash 를 찍어, 쓰지 않은
    배지 위의 run 으로 발표된다. 이제 :func:`apply_medium_translated` 와 **동일한 단일 경로**
    (대사체 기준 exchange 반응 조회)를 쓴다 — subcommand 마다 배지 의미가 갈리지 않는다.

    Round 6 (track B, instance 1): ``exact`` is now selectable here too. It defaults to False —
    isolation is opt-in-to-close, and flipping the default would silently reinterpret every
    stored medium file — but the *choice* is no longer unavailable, and which mode ran is recorded
    in the manifest's non-hashed provenance so the two eras cannot be confused. Callers that
    publish provenance should use :func:`medium_application_report` instead of this two-tuple.
    """
    spec.validate()
    original = dict(community.medium)  # type: ignore[attr-defined]
    translation = apply_medium_translated(community, spec, strict=strict, exact=exact)
    return original, list(translation.unmatched)


# ── Namespace-bridged effective medium (P0-A) ──────────────────────────────────
# A community exposes environment exchanges as ``EX_<met>_m`` while each member model exposes
# ``EX_<met>_e``. Applying one MediumSpec object to both therefore silently applies it to *neither*
# unless the ids are translated. The metabolite is the invariant, so every comparison below is
# keyed on the metabolite, never on the raw exchange id.


def exchange_metabolite(exchange_id: str) -> str:
    """``EX_glc__D_m``/``EX_glc__D_e``/``EX_etoh_lumen`` → ``glc__D``/``glc__D``/``etoh``.

    BiGG-style exchange ids are ``EX_<metabolite>_<compartment>`` and the metabolite part may
    itself contain ``__`` (``lac__L``), so the compartment is the final ``_``-delimited token.
    """
    name = exchange_id[3:] if exchange_id.startswith("EX_") else exchange_id
    head, separator, _tail = name.rpartition("_")
    return head if separator else name


def model_exchange_index(model: object) -> dict[str, str]:
    """metabolite → this model's exchange id, over *all* exchanges (not just open uptakes).

    ``model.medium`` lists only currently-open uptakes, so it cannot be used to decide whether a
    nutrient is offerable; a closed exchange can still be opened by a medium.
    """
    index: dict[str, str] = {}
    for reaction in getattr(model, "exchanges", []):
        index.setdefault(exchange_metabolite(str(reaction.id)), str(reaction.id))
    return index


@dataclass(frozen=True)
class MediumTranslation:
    """A MediumSpec re-expressed in one model's exchange namespace."""

    spec: MediumSpec                      # translated (keys are this model's exchange ids)
    mapping: dict[str, str]               # source exchange id → this model's exchange id
    unmatched: tuple[str, ...]            # source exchange ids with no counterpart in the model
    # Round 6 (track B): which medium semantics actually ran, and — under `exact` — what was
    # closed to achieve them. Carried on the translation rather than returned separately so that
    # every caller of `apply_medium_translated` can disclose it without changing its signature.
    application_mode: str = MEDIUM_APPLICATION_MERGE
    isolation: Any = None                 # cmig.core.boundary.BoundaryIsolation | None
    #: Boundary reactions still able to supply mass that the spec does not declare. Empty under
    #: `exact`. Under `merge` this is the count that made the 81 % oxygen overestimate publishable.
    undeclared_suppliers: tuple[str, ...] = ()

    @property
    def matched_count(self) -> int:
        return len(self.mapping)

    def as_provenance(self) -> dict[str, Any]:
        """JSON-ready, non-hashed record of how the medium was applied."""
        record: dict[str, Any] = {
            "medium_application_mode": self.application_mode,
            "n_undeclared_boundary_suppliers": len(self.undeclared_suppliers),
            "undeclared_boundary_suppliers": list(self.undeclared_suppliers[:20]),
        }
        if self.isolation is not None:
            record["boundary_isolation"] = self.isolation.as_dict()
        return record


def translate_medium_for_model(model: object, spec: MediumSpec) -> MediumTranslation:
    """Re-key ``spec`` onto the exchange ids ``model`` actually exposes, matching on metabolite.

    Because the match is on the *metabolite*, two different source ids can resolve to one target
    exchange — ``EX_glc__D_m`` and ``EX_glc__D_e`` both mean glucose. Round 5 (blocker 1): the
    first cut wrote ``translated[target] = limit`` unconditionally, so the last row of the medium
    file silently won. Reordering *identical* CSV rows then changed community growth
    ``1.125065`` -> ``0.954612`` while ``medium_checksum`` (which sorts, and hashes **both**
    entries) stayed byte-identical — a different scientific answer certified by the same
    fingerprint, which is the exact failure class this round exists to close.

    This is reachable rather than exotic: hedging both namespaces in one file was the natural
    user workaround for the pre-CC-11 bug, since the old code required an exact key match.

    Resolution: aliases that request the **same** limit are merged deterministically (the user
    asked for one thing twice, so there is nothing to choose). Aliases that request **different**
    limits are a contradictory input and are refused — never silently resolved in favour of one.
    """
    spec.validate()
    index = model_exchange_index(model)
    mapping: dict[str, str] = {}
    requested: dict[str, dict[str, float]] = {}
    unmatched: list[str] = []
    for source_exchange, limit in spec.uptake.items():
        target = index.get(exchange_metabolite(str(source_exchange)))
        if target is None:
            unmatched.append(str(source_exchange))
            continue
        mapping[str(source_exchange)] = target
        requested.setdefault(target, {})[str(source_exchange)] = float(limit)

    translated: dict[str, float] = {}
    conflicts: list[str] = []
    for target in sorted(requested):
        sources = requested[target]
        distinct = sorted(set(sources.values()))
        if len(distinct) > 1:
            detail = ", ".join(f"{source}={sources[source]!r}" for source in sorted(sources))
            conflicts.append(f"{target} <- {{{detail}}}")
            continue
        translated[target] = distinct[0]
    if conflicts:
        raise ValueError(
            "medium spec requests conflicting uptake limits for the same model exchange "
            f"(aliases of one metabolite): {conflicts}. Resolve the duplicate rows — refusing "
            "rather than silently picking one, because the choice would change the result "
            "without changing the medium checksum."
        )
    return MediumTranslation(
        spec=MediumSpec(uptake=translated),
        mapping=mapping,
        unmatched=tuple(sorted(unmatched)),
    )


def effective_medium_by_metabolite(model: object) -> dict[str, float]:
    """This model's *current* effective medium as metabolite → uptake limit.

    Namespace-free, so a community (`_m`) and a member model (`_e`) become directly comparable.
    """
    medium = dict(getattr(model, "medium", {}) or {})
    return {
        exchange_metabolite(str(exchange)): float(limit)
        for exchange, limit in medium.items()
    }


def apply_medium_translated(
    model: object, spec: MediumSpec, *, strict: bool = True, exact: bool = False
) -> MediumTranslation:
    """Translate ``spec`` into ``model``'s namespace and apply it. Returns the translation.

    ``strict=True`` refuses when a requested metabolite has no exchange in this model — that is a
    request the model cannot honour, so silently dropping it would fake a controlled medium.

    ``exact=True`` makes the translated spec the *whole* set of mass sources the model has, which
    is what "both legs on the same defined medium" requires. ``exact=False`` merges onto whatever
    the model already offers.

    Unlike :func:`apply_medium_checked`, this does not gate on ``model.medium`` — that property
    lists only *currently open* uptakes, so gating on it makes opening a closed nutrient
    impossible, which is precisely how a medium silently applies to nothing.

    Round 6 (track B, instance 3): ``exact=True`` used to assign ``model.medium``, and cobra's own
    setter computes ``exchange_rxns = frozenset(self.exchanges)`` and turns off only those. Sinks
    and demands are not exchanges, so on Recon3D 95 boundary reactions stayed at
    ``lower_bound = -1000`` and "exact" was not exact — measured: declared uptake 1.0, achieved
    growth 1000.0, the sink still wide open. It now goes through :mod:`cmig.core.boundary`, which
    enumerates ``model.boundary``. Because the per-reaction arithmetic is identical to cobra's
    ``set_active_bound``, a model with no sinks or demands gets bit-identical bounds either way.
    """
    from cmig.core.boundary import (
        isolate_boundary,
        mass_supplying_boundary,
        open_boundary_supply,
    )

    translation = translate_medium_for_model(model, spec)
    if strict and translation.unmatched:
        raise ValueError(
            "medium exchange has no counterpart in the target model "
            f"(matched on metabolite): {list(translation.unmatched)}"
        )
    declared = dict(translation.spec.uptake)
    if exact:
        isolation = isolate_boundary(model, declared, strict_unmatched=False)
        return replace(
            translation,
            application_mode=MEDIUM_APPLICATION_EXACT,
            isolation=isolation,
            undeclared_suppliers=(),
        )
    open_boundary_supply(model, declared, strict=False)
    # Merge mode leaves everything the model already offered open. That is a legitimate mode, but
    # it is not the medium the manifest's `medium_checksum` names, so the difference is measured
    # and handed back rather than assumed to be empty.
    undeclared = tuple(
        reaction_id
        for reaction_id in sorted(mass_supplying_boundary(model))
        if reaction_id not in declared
    )
    return replace(
        translation,
        application_mode=MEDIUM_APPLICATION_MERGE,
        isolation=None,
        undeclared_suppliers=undeclared,
    )


def compare_effective_media(
    reference: dict[str, float],
    candidate: dict[str, float],
    *,
    tolerance: float = 1e-9,
    exempt: set[str] | frozenset[str] = frozenset(),
) -> tuple[bool, dict[str, list[str]]]:
    """Are two metabolite-keyed effective media the same offer? Returns (equal, differences).

    ``exempt`` holds metabolites the candidate model has no exchange for — it cannot be offered
    them at all, which is biology, not a loss of experimental control, so those are excluded from
    the equality decision and reported separately by the caller.
    """
    reference_keys = set(reference) - set(exempt)
    candidate_keys = set(candidate) - set(exempt)
    differences: dict[str, list[str]] = {
        "missing_from_candidate": sorted(reference_keys - candidate_keys),
        "extra_in_candidate": sorted(candidate_keys - reference_keys),
        "bound_mismatch": sorted(
            metabolite
            for metabolite in reference_keys & candidate_keys
            if abs(float(reference[metabolite]) - float(candidate[metabolite])) > tolerance
        ),
    }
    equal = not any(differences.values())
    return equal, differences


def medium_checksum(spec: MediumSpec | None) -> str:
    """결정적 medium 체크섬 (run_hash 구성요소). None → default sentinel(하위호환).

    R5-P3 V1: 예전에는 uptake 값을 6자리로 반올림했다. medium 은 사용자가 파일로 준 **답을
    결정하는 입력**이므로, 1e-6 아래에서 다른 두 배지가 같은 checksum → 같은 run_hash 를
    받으면 "같은 hash = 같은 입력" 이라는 manifest 의 주장이 깨진다 (CC-4 와 동일한 결함이
    canonicalizer 가 아니라 checksum builder 안에 숨어 있던 것). 값은 그대로 해싱한다 —
    `json.dumps` 의 float 직렬화는 repr 기반이라 정확히 round-trip 한다.
    """
    if spec is None:
        return "micom_default_medium"
    payload = json.dumps(
        {k: float(v) for k, v in sorted(spec.uptake.items())},
        sort_keys=True, ensure_ascii=True, allow_nan=False,
    )
    return "medium:" + hashlib.sha256(payload.encode()).hexdigest()
