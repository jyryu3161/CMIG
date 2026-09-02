"""Reproducibility — RunManifest + run_hash (정확히 11개 구성요소).

Design Ref: §4.3 / schema §4.2 [HASH-11·HASH-FLOAT·HASH-ENVLOCK·HASH-SINGLE].
Plan SC: SC-4 (run_hash 캐시 정확성).

run_hash = 다음 11개 구성요소를 canonical 직렬화·float rounding 후 SHA-256:
  1 model_checksum            2 medium_checksum        3 member_set
  4 abundance                 5 bounds                 6 tradeoff_f
  7 solver_setting            8 micom_version          9 cmig_core_version
 10 namespace_mapping_decisions  11 flux_normalization_method
env_lock 은 **미포함** (manifest.inputs 에만, [HASH-ENVLOCK]).
OD-11/OD-10 (Resolved): canonical = 정렬키 JSON(분리자 고정) → SHA-256.
OD-12 (Deferred): float rounding 자릿수(기본 6) 는 golden 안정화 후 보정.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any, cast

# run_hash 구성요소 canonical 순서 (11개, 빠짐·추가 금지 [HASH-11]).
RUN_HASH_COMPONENTS: tuple[str, ...] = (
    "model_checksum",
    "medium_checksum",
    "member_set",
    "abundance",
    "bounds",
    "tradeoff_f",
    "solver_setting",
    "micom_version",
    "cmig_core_version",
    "namespace_mapping_decisions",
    "flux_normalization_method",
)
assert len(RUN_HASH_COMPONENTS) == 11, "run_hash must have exactly 11 components (schema §4.2)"

DEFAULT_FLOAT_DECIMALS = 6  # OD-12 안전 시작값 (§16 'spec 예: 6 decimal')

# R5-P3 CC-4: plain `round(x, 6)` maps *every* input below 5e-7 onto 0.0, so a solver tolerance of
# 1e-7 and one of 4e-7 — which produce different numbers — used to share a run_hash. Rounding is
# the right rule for absorbing solver noise in a value that came *out* of a solve; it is the wrong
# rule for an input that *determines* the answer.
#
# The fix has to be backward compatible, because the frozen 11-component fixture hash
# (0721dcc0…307e46d under core 0.2.0, 31d5647d…0e0bf63 under 0.3.0) is a published
# contract. So: a value that is already exactly representable in
# six decimals serializes exactly as it does today, and only a value the old rule would have
# destroyed gets a lossless form. Every stored hash whose inputs were six-decimal-exact — which is
# what the fixtures and the pre-rounded abundance vectors contain — is therefore preserved, while
# sub-micro distinctions stop colliding. Verified empirically against the frozen fixtures.
_LOSSLESS_FLOAT_PREFIX = "f64:"
# A float's lossless token is a string, so in principle a *string* component whose value happened
# to be "f64:0.3333333333333333" would serialize identically to the float 1/3 and the two would
# share a hash. No reachable path produces such a string today (components are checksums, ids,
# versions and controlled vocabularies), but "no reachable path" is not the same as "impossible",
# and this is the wrong-number class. Strings that would collide are escaped by prefixing
# `str:`, which makes the mapping injective: a float token always starts `f64:`, and no string can
# produce one. `str:` is itself escaped so the scheme stays reversible.
_STRING_ESCAPE_PREFIX = "str:"


@dataclass(frozen=True)
class RunHashComponents:
    """run_hash 입력 11구성요소. float 구성요소는 hash 전 rounding 적용."""

    model_checksum: str
    medium_checksum: str
    member_set: list[str]                       # 정렬 후 직렬화
    abundance: dict[str, float]                  # member_id → abundance
    bounds: dict[str, list[float]]               # reaction_id → [lower, upper]
    tradeoff_f: float
    solver_setting: dict[str, Any]               # growth_solver/flux_solver/tolerance (OD-13)
    micom_version: str
    cmig_core_version: str
    namespace_mapping_decisions: list[str]       # 결정 키(정렬) — 자동병합 없음
    flux_normalization_method: str               # 예: "pfba"


def _round_floats(obj: Any, decimals: int) -> Any:
    """재귀적으로 float 를 정규화 (부동소수·alternate-optima 잡음 흡수, [HASH-FLOAT]).

    비유한(non-finite) float(±inf/NaN, COBRA bound 에 흔함)는 결정적 sentinel 문자열로
    정규화한다 (NaN≠NaN·Infinity 직렬화 비결정성 제거, I-6).

    R5-P3 CC-4: ``round(x, decimals)`` 가 값을 손실 없이 표현하면 (즉 반올림 결과가 원본과
    같으면) 지금까지와 완전히 동일하게 그 숫자를 낸다 — 기존 hash 는 그대로 보존된다.
    반올림이 값을 파괴하는 경우(1e-7 과 4e-7 이 모두 0.0 이 되는 경우)에만 shortest
    round-trip repr 을 sentinel 문자열로 낸다. 이렇게 해야 "동일 hash = 동일 입력" 이라는
    manifest 의 핵심 주장이 solver tolerance 자릿수 아래에서도 유지된다.
    """
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, str):
        # Escape only the strings that could impersonate a float token (see the prefixes above).
        # Nothing in the current component vocabulary starts with either prefix, so no existing
        # hash moves; this closes the collision structurally rather than by assumption.
        if obj.startswith(_LOSSLESS_FLOAT_PREFIX) or obj.startswith(_STRING_ESCAPE_PREFIX):
            return _STRING_ESCAPE_PREFIX + obj
        return obj
    if isinstance(obj, float):
        if math.isnan(obj):
            return "NaN"
        if math.isinf(obj):
            return "Infinity" if obj > 0 else "-Infinity"
        # `+ 0.0` collapses -0.0 → 0.0 so semantically identical near-zero fluxes that round to
        # opposite signed zeros do not serialize differently (run_hash determinism).
        rounded = round(obj, decimals) + 0.0
        if rounded == obj:
            return rounded
        # repr() is the shortest string that round-trips exactly, and CPython's algorithm is
        # deterministic across platforms for IEEE-754 doubles.
        return f"{_LOSSLESS_FLOAT_PREFIX}{obj!r}"
    if isinstance(obj, dict):
        return {k: _round_floats(v, decimals) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round_floats(v, decimals) for v in obj]
    return obj


def canonicalize_floats(obj: Any, decimals: int = DEFAULT_FLOAT_DECIMALS) -> Any:
    """Public alias for the run_hash float normalization ([HASH-FLOAT]).

    The workflow-level envelope (`cmig.core.workflow_manifest`) hashes a *different*, per-kind
    component set, but it must normalize floats exactly the same way. Sharing this one
    implementation keeps both hashes deterministic under the same rules instead of drifting.
    This is a read-only alias — it does not touch RUN_HASH_COMPONENTS or DEFAULT_FLOAT_DECIMALS.

    Since R5-P3 CC-4 the rule is "round when rounding is lossless, otherwise keep the exact
    value", so two inputs that differ below the sixth decimal no longer share a hash.
    """
    return _round_floats(obj, decimals)


def canonical_payload(
    c: RunHashComponents, decimals: int = DEFAULT_FLOAT_DECIMALS
) -> dict[str, Any]:
    """11구성요소를 결정적(deterministic) payload 로 정규화.

    - member_set / namespace_mapping_decisions: 정렬(순서 무관 결정성)
    - dict: 키 정렬은 직렬화 단계에서 sort_keys 로 처리
    - float: rounding 적용
    """
    raw = asdict(c)
    raw["member_set"] = sorted(raw["member_set"])
    raw["namespace_mapping_decisions"] = sorted(raw["namespace_mapping_decisions"])
    # env_lock 은 애초에 구성요소에 없다 ([HASH-ENVLOCK]) — 방어적 검증.
    assert set(raw.keys()) == set(RUN_HASH_COMPONENTS), (
        "run_hash payload != 11 canonical components"
    )
    return cast("dict[str, Any]", _round_floats(raw, decimals))


def canonical_json(c: RunHashComponents, decimals: int = DEFAULT_FLOAT_DECIMALS) -> str:
    """canonical 직렬화 문자열 (OD-11: 정렬키 JSON·고정 분리자)."""
    payload = canonical_payload(c, decimals)
    # allow_nan=False: 비유한 float 가 남아있으면 fail-loud (이미 _round_floats 가 sentinel 화).
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def compute_run_hash(c: RunHashComponents, decimals: int = DEFAULT_FLOAT_DECIMALS) -> str:
    """run_hash = SHA-256(canonical_json). 동일 11구성요소 → 동일 hash (SC-4)."""
    return hashlib.sha256(canonical_json(c, decimals).encode("utf-8")).hexdigest()



@dataclass(frozen=True)
class RunManifest:
    """재현 manifest. inputs.env_lock 은 기록하되 run_hash 에는 미포함 (§7).

    `run_hash` 는 components 로부터 산출되어 Scenario/AggregationStore 와 비트 단위 일치
    ([HASH-SINGLE]).
    """

    components: RunHashComponents
    env_lock: str | None = None                  # manifest 에만 (HASH 미포함)
    figure_specs: list[dict[str, Any]] = field(default_factory=list)
    platform: dict[str, str] = field(default_factory=dict)
    float_decimals: int = DEFAULT_FLOAT_DECIMALS

    @property
    def run_hash(self) -> str:
        return compute_run_hash(self.components, self.float_decimals)
