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
    """재귀적으로 float 를 rounding (부동소수·alternate-optima 잡음 흡수, [HASH-FLOAT]).

    비유한(non-finite) float(±inf/NaN, COBRA bound 에 흔함)는 결정적 sentinel 문자열로
    정규화한다 (NaN≠NaN·Infinity 직렬화 비결정성 제거, I-6).
    """
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        if math.isnan(obj):
            return "NaN"
        if math.isinf(obj):
            return "Infinity" if obj > 0 else "-Infinity"
        return round(obj, decimals)
    if isinstance(obj, dict):
        return {k: _round_floats(v, decimals) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round_floats(v, decimals) for v in obj]
    return obj


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


def sha256_checksum(data: bytes) -> str:
    """model/medium checksum (OD-10: SHA-256)."""
    return hashlib.sha256(data).hexdigest()


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
