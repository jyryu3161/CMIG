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
from dataclasses import dataclass
from pathlib import Path

_DECIMALS = 6


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

    spec 의 exchange 중 community 가 아는 medium 키만 설정한다. 미지 exchange 는 기본적으로
    fail-fast 이며, 호출자가 `strict=False` 를 선택한 경우에만 무시한다.
    uptake_limit 은 그대로 MICOM medium 양수값으로 사용(부호 변환 불요).
    """
    return apply_medium_checked(community, spec, strict=True)[0]


def unknown_medium_exchanges(community: object, spec: MediumSpec) -> list[str]:
    """medium spec 중 community.medium 에 없는 exchange 목록."""
    spec.validate()
    known = set(dict(community.medium))  # type: ignore[attr-defined]
    return sorted(ex for ex in spec.uptake if ex not in known)


def apply_medium_checked(
    community: object, spec: MediumSpec, *, strict: bool = True
) -> tuple[dict[str, float], list[str]]:
    """community.medium 에 spec 적용 + 미적용 exchange 목록 반환.

    strict=True 이면 미지 exchange 를 ValueError 로 차단한다. strict=False 는 CLI의
    `--allow-unknown-medium` 같은 명시 옵션에서만 사용하며, 반환된 unknown 목록을 diagnostic에
    기록해야 한다.
    """
    spec.validate()
    current = dict(community.medium)  # type: ignore[attr-defined]
    original = dict(current)
    known = set(current)
    unknown = sorted(ex for ex in spec.uptake if ex not in known)
    if strict and unknown:
        raise ValueError(f"medium exchange not present in the target model: {unknown}")
    applied = {ex: v for ex, v in spec.uptake.items() if ex in known}
    new_medium = dict(current)
    new_medium.update(applied)
    community.medium = new_medium  # type: ignore[attr-defined]
    return original, unknown


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

    @property
    def matched_count(self) -> int:
        return len(self.mapping)


def translate_medium_for_model(model: object, spec: MediumSpec) -> MediumTranslation:
    """Re-key ``spec`` onto the exchange ids ``model`` actually exposes, matching on metabolite."""
    spec.validate()
    index = model_exchange_index(model)
    mapping: dict[str, str] = {}
    translated: dict[str, float] = {}
    unmatched: list[str] = []
    for source_exchange, limit in spec.uptake.items():
        target = index.get(exchange_metabolite(str(source_exchange)))
        if target is None:
            unmatched.append(str(source_exchange))
            continue
        mapping[str(source_exchange)] = target
        translated[target] = float(limit)
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

    ``exact=True`` makes the translated spec the *whole* medium (cobra closes every other
    exchange), which is what "both legs on the same defined medium" requires. ``exact=False``
    merges onto whatever the model already offers.

    Unlike :func:`apply_medium_checked`, this does not gate on ``model.medium`` — that property
    lists only *currently open* uptakes, so gating on it makes opening a closed nutrient
    impossible, which is precisely how a medium silently applies to nothing.
    """
    translation = translate_medium_for_model(model, spec)
    if strict and translation.unmatched:
        raise ValueError(
            "medium exchange has no counterpart in the target model "
            f"(matched on metabolite): {list(translation.unmatched)}"
        )
    if exact:
        target = dict(translation.spec.uptake)
    else:
        target = dict(getattr(model, "medium", {}) or {})
        target.update(translation.spec.uptake)
    model.medium = target  # type: ignore[attr-defined]
    return translation


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
    """결정적 medium 체크섬 (run_hash 구성요소). None → default sentinel(하위호환)."""
    if spec is None:
        return "micom_default_medium"
    payload = json.dumps(
        {k: round(float(v), _DECIMALS) for k, v in sorted(spec.uptake.items())},
        sort_keys=True, ensure_ascii=True, allow_nan=False,
    )
    return "medium:" + hashlib.sha256(payload.encode()).hexdigest()
