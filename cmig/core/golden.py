"""Golden fixture hashing — float rounding/tolerance 후 정규화 hash.

Design Ref: §16·A17 / schema §4.3 [HASH-FLOAT] / Plan SC: SC-1, SC-6.

float 컬럼은 hash 전 rounding(기본 6 decimal, OD-12)하여 부동소수·alternate-optima
잡음을 흡수한다. 행 정렬(determinism) 후 SHA-256.
OD-47 (Resolved): normalized_hash = 정렬된 행의 canonical JSON → SHA-256.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import pyarrow as pa

DEFAULT_DECIMALS = 6  # OD-12 안전 시작값 (§16 'spec 예: 6 decimal')


def _round(v: Any, decimals: int) -> Any:
    if isinstance(v, float):
        # NaN/inf 정규화 (OD-47: NaN 처리)
        if v != v:  # NaN
            return "NaN"
        if math.isinf(v):
            return "Infinity" if v > 0 else "-Infinity"
        return round(v, decimals)
    return v


def normalized_rows(table: pa.Table, decimals: int = DEFAULT_DECIMALS) -> list[dict[str, Any]]:
    """테이블 → 컬럼 정렬·float rounding·행 정렬된 dict 리스트 (결정적)."""
    cols = sorted(table.column_names)
    rows: list[dict[str, Any]] = []
    pylist = table.to_pylist()
    for r in pylist:
        rows.append({c: _round(r.get(c), decimals) for c in cols})
    # 행 정렬: canonical JSON 키 기준
    rows.sort(key=lambda r: json.dumps(r, sort_keys=True, ensure_ascii=True))
    return rows


def normalized_table_hash(table: pa.Table, decimals: int = DEFAULT_DECIMALS) -> str:
    """float rounding·정렬 후 SHA-256 (SC-1 golden 비교용)."""
    payload = json.dumps(
        normalized_rows(table, decimals), sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def bundle_hashes(bundle: Any, decimals: int = DEFAULT_DECIMALS) -> dict[str, str]:
    """TidyBundle 의 nodes/edges/profile 정규화 hash (audit 기록·deterministic solver용, §16)."""
    return {
        "nodes": normalized_table_hash(bundle.nodes, decimals),
        "edges": normalized_table_hash(bundle.edges, decimals),
        "profile": normalized_table_hash(bundle.profile, decimals),
    }


# ── tolerance 기반 golden 비교 (alternate-optima/iterative solver 잡음 흡수, §16·OD-47) ──
# 결정적 solver(gurobi)는 hash-exact, OSQP 등 iterative 는 tolerance 비교가 옳다.

class GoldenMismatch(AssertionError):
    """golden tolerance 비교 실패."""


def _sorted_rows(table: pa.Table, key_cols: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = list(table.to_pylist())
    rows.sort(key=lambda r: tuple(str(r.get(k)) for k in key_cols))
    return rows


def tables_close(
    actual: pa.Table,
    expected: pa.Table,
    key_cols: list[str],
    float_cols: list[str],
    *,
    atol: float = 1e-4,
    rtol: float = 1e-5,
) -> bool:
    """행 키(key_cols)로 정렬 후, 문자열 컬럼=정확 일치 / float 컬럼=atol·rtol 허용 비교.

    행 정렬은 **안정적 키 컬럼**(id/문자열)만 사용 — float 정렬은 jitter 로 행 오정렬 위험.
    None vs None 은 동일로 본다.
    """
    if actual.column_names != expected.column_names:
        raise GoldenMismatch(f"컬럼 불일치: {actual.column_names} != {expected.column_names}")
    ra, re_ = _sorted_rows(actual, key_cols), _sorted_rows(expected, key_cols)
    if len(ra) != len(re_):
        raise GoldenMismatch(f"행 수 불일치: {len(ra)} != {len(re_)}")
    str_cols = [c for c in actual.column_names if c not in float_cols]
    for i, (a, e) in enumerate(zip(ra, re_, strict=True)):
        for c in str_cols:
            if a.get(c) != e.get(c):
                raise GoldenMismatch(f"row{i}.{c}: {a.get(c)!r} != {e.get(c)!r}")
        for c in float_cols:
            av, ev = a.get(c), e.get(c)
            if av is None or ev is None:
                if av is not ev and not (av is None and ev is None):
                    raise GoldenMismatch(f"row{i}.{c}: None 불일치 {av} != {ev}")
                continue
            if isinstance(av, float) and isinstance(ev, float):
                if math.isnan(av) or math.isnan(ev):
                    raise GoldenMismatch(f"row{i}.{c}: NaN 불일치 {av} != {ev}")
                if math.isinf(av) or math.isinf(ev):
                    if av != ev:
                        raise GoldenMismatch(f"row{i}.{c}: inf 불일치 {av} != {ev}")
                    continue
            if abs(av - ev) > atol + rtol * abs(ev):
                raise GoldenMismatch(
                    f"row{i}.{c}: |{av}-{ev}|={abs(av - ev):.2e} > atol={atol}+rtol·|e|"
                )
    return True
