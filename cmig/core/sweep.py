"""G4 Sweep — parameter sweep + run_hash 캐시 + 실패 diagnostic.

Design Ref: §10 AN-SWEEP·§5 AggregationStore / schema §6 / glossary AN-SWEEP.
Plan SC: SC-4 (run_hash 캐시 정확성).

축{medium variant·abundance·member set·bounds·tradeoff f·solver}×값 → N-run 배치 →
long-format `sweep.parquet`. **동일 run_hash → 캐시 hit(재계산 회피)**; 구성요소 변경 →
miss·재계산. **실패 run 도 condition_id별 diagnostic 으로 저장(누락 금지)**.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from cmig.core.diagnostics import Diagnostic
from cmig.core.manifest import DEFAULT_FLOAT_DECIMALS

# AggregationStore sweep.parquet 스키마 버전 (schema §6.1 첫 컬럼·OD-46, tidy 와 독립).
SWEEP_SCHEMA_VERSION = "1.0"

# 축 enum (§10 6종) — schema §6.1 의 per-axis 컬럼명에 1:1 대응.
AXIS_KINDS = (
    "medium_variant", "abundance", "member_set", "bounds", "tradeoff_f", "solver",
)
# schema §6.1: 각 축은 독립 컬럼(axis_*). tradeoff_f 만 float64, 나머지는 식별자 string (TC-2).
AXIS_COLUMNS = tuple(f"axis_{k}" for k in AXIS_KINDS)

# AggregationStore sweep.parquet 컬럼 (schema §6.1 — 6개 per-axis 컬럼, axis_tradeoff_f=float64).
SWEEP_SCHEMA = pa.schema([
    ("schema_version", pa.string()),       # 첫 컬럼·nullable=false (schema §6.1, 단일-계약)
    ("condition_id", pa.string()),
    ("axis_medium_variant", pa.string()),  # 축 값(식별자) — nullable
    ("axis_abundance", pa.string()),
    ("axis_member_set", pa.string()),
    ("axis_bounds", pa.string()),
    ("axis_tradeoff_f", pa.float64()),     # 축 값(float) — A17 rounding (TC-3)
    ("axis_solver", pa.string()),
    ("metric", pa.string()),
    ("value", pa.float64()),               # nullable (failed=null)
    ("run_hash", pa.string()),
    ("status", pa.string()),               # {ok, failed}
    ("diagnostic", pa.string()),           # nullable; failed 면 필수(≠null)
    ("cache_hit", pa.bool_()),             # (TC-12 defer — view 플래그, known issue)
])


@dataclass(frozen=True)
class SweepAxis:
    """sweep 축 1개. kind 는 폐쇄 enum(§10 6종)."""

    kind: str
    values: list[Any]

    def __post_init__(self) -> None:
        if self.kind not in AXIS_KINDS:
            raise ValueError(f"미지원 sweep 축: {self.kind} (허용: {sorted(AXIS_KINDS)})")


@dataclass(frozen=True)
class SweepCondition:
    condition_id: str
    axis_values: dict[str, Any]       # {axis_kind: value}


# 캐시 항목 = (value, status, diagnostic). 실패도 결정적 결과로 캐시 (I-2, schema §6.2·A14).
CacheEntry = tuple[float | None, str, str | None]


@dataclass
class RunHashCache:
    """run_hash → (value, status, diagnostic) 캐시 (재계산 회피, SC-4).

    동일 run_hash 는 성공/실패 모두 안정적 결과 → 재solve 없이 replay (실패도 캐시).
    """

    _store: dict[str, CacheEntry] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0

    def get(self, run_hash: str) -> CacheEntry | None:
        if run_hash in self._store:
            self.hits += 1
            return self._store[run_hash]
        self.misses += 1
        return None

    def put(self, run_hash: str, value: float | None, status: str, diagnostic: str | None) -> None:
        self._store[run_hash] = (value, status, diagnostic)


def enumerate_conditions(axes: list[SweepAxis]) -> list[SweepCondition]:
    """축들의 데카르트 곱 → 조건 목록 (결정적 순서)."""
    kinds = [a.kind for a in axes]
    combos = itertools.product(*[a.values for a in axes])
    conditions = []
    for i, combo in enumerate(combos):
        axis_values = dict(zip(kinds, combo, strict=True))
        conditions.append(SweepCondition(condition_id=f"cond-{i:04d}", axis_values=axis_values))
    return conditions


@dataclass(frozen=True)
class SweepRow:
    condition_id: str
    axis_values: dict[str, Any]
    metric: str
    value: float | None
    run_hash: str
    status: str
    diagnostic: str | None
    cache_hit: bool


def run_sweep(
    axes: list[SweepAxis],
    *,
    run_hash_fn: Callable[[SweepCondition], str],
    solve_fn: Callable[[SweepCondition], float],
    metric: str,
    cache: RunHashCache | None = None,
    progress: Callable[[int, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> list[SweepRow]:
    """sweep 실행. 캐시 hit → 재계산 회피; solve 예외 → status=failed+diagnostic(누락 금지).

    Phase 0.2 (JobRunner wiring): optional `progress(done, total)`·`should_cancel()` 훅.
    should_cancel→True 면 condition 경계에서 **부분 결과 반환**(협조적 취소; core 는 service 미의존
    → JobCancelled 은 service 층에서 raise). default None → 기존 동작 무변.
    """
    cache = cache if cache is not None else RunHashCache()
    rows: list[SweepRow] = []
    conditions = enumerate_conditions(axes)
    total = len(conditions)
    for i, cond in enumerate(conditions):
        if should_cancel is not None and should_cancel():   # 협조적 취소 → 부분 결과
            break
        rh = run_hash_fn(cond)
        cached = cache.get(rh)
        if cached is not None:                       # 성공/실패 모두 캐시에서 replay (I-2)
            value, status, diag = cached
            rows.append(SweepRow(cond.condition_id, cond.axis_values, metric, value, rh,
                                 status, diag, cache_hit=True))
            if progress is not None:
                progress(i + 1, total)
            continue
        try:
            value = solve_fn(cond)
        except Exception as e:  # 실패 run 도 캐시·기록 (SC-4, [STATUS-CLOSED], 누락 금지)
            diag = Diagnostic.from_exception(e).to_json()   # R5: 구조화 {code,message,detail}
            cache.put(rh, None, "failed", diag)
            rows.append(SweepRow(cond.condition_id, cond.axis_values, metric, None, rh,
                                 "failed", diag, cache_hit=False))
            if progress is not None:
                progress(i + 1, total)
            continue
        cache.put(rh, value, "ok", None)
        rows.append(SweepRow(cond.condition_id, cond.axis_values, metric, value, rh,
                             "ok", None, cache_hit=False))
        if progress is not None:
            progress(i + 1, total)
    return rows


def _axis_str(axis_values: dict[str, Any], kind: str) -> str | None:
    """string 축 값 → 결정적 식별자 문자열(미지정=null). (TC-2·TC-3)"""
    if kind not in axis_values or axis_values[kind] is None:
        return None
    return str(axis_values[kind])


def _axis_tradeoff_f(axis_values: dict[str, Any]) -> float | None:
    """tradeoff_f 축 값 → A17 rounding float(미지정/비유한=null). (TC-3 canonical)"""
    if "tradeoff_f" not in axis_values or axis_values["tradeoff_f"] is None:
        return None
    v = float(axis_values["tradeoff_f"])
    if not math.isfinite(v):                       # 비유한은 null (float 컬럼은 sentinel 불가)
        return None
    return round(v, DEFAULT_FLOAT_DECIMALS)


def write_sweep_parquet(rows: list[SweepRow], path: str | Path) -> None:
    """AggregationStore sweep.parquet 저장 (pickle 금지).

    schema §6.1: 6개 per-axis 컬럼으로 전개(axis_tradeoff_f=float64, A17 rounding). (TC-2·TC-3)
    """
    table = pa.table(
        {
            "schema_version": [SWEEP_SCHEMA_VERSION] * len(rows),
            "condition_id": [r.condition_id for r in rows],
            "axis_medium_variant": [_axis_str(r.axis_values, "medium_variant") for r in rows],
            "axis_abundance": [_axis_str(r.axis_values, "abundance") for r in rows],
            "axis_member_set": [_axis_str(r.axis_values, "member_set") for r in rows],
            "axis_bounds": [_axis_str(r.axis_values, "bounds") for r in rows],
            "axis_tradeoff_f": [_axis_tradeoff_f(r.axis_values) for r in rows],
            "axis_solver": [_axis_str(r.axis_values, "solver") for r in rows],
            "metric": [r.metric for r in rows],
            "value": [r.value for r in rows],
            "run_hash": [r.run_hash for r in rows],
            "status": [r.status for r in rows],
            "diagnostic": [r.diagnostic for r in rows],
            "cache_hit": [r.cache_hit for r in rows],
        },
        schema=SWEEP_SCHEMA,
    )
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, p)
