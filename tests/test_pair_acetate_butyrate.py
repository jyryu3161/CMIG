"""C5/S3 — synthetic acetate→butyrate cross-feeding 정성 검증. Plan SC: SC-F7.

synthetic toy GEM 쌍(종명 없음)으로 CMIG 의 cross-feeding 추출·sign 규약을 정성 검증한다.
정량 주장 아님. micom 미설치 시 skip.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq
import pytest

pytest.importorskip("micom")

from cmig.core.golden import DEFAULT_DECIMALS, normalized_table_hash  # noqa: E402
from cmig.synthetic_pair import FIXTURE_DIR, solve_pair  # noqa: E402

EXPECTED = FIXTURE_DIR / "expected"


def test_acetate_cross_feeding_edge_present():
    """SC-F7: producer→consumer acetate cross_feeding edge 존재(핵심 시나리오)."""
    _, bundle = solve_pair("gurobi")
    cf = [
        e for e in bundle.edges.to_pylist()
        if e["edge_type"] == "cross_feeding" and e["metabolite"] == "ac"
    ]
    assert cf, "acetate cross-feeding edge 부재"
    assert cf[0]["source_id"] == "producer" and cf[0]["target_id"] == "consumer"
    assert cf[0]["weight"] > 0


def test_consumer_secretes_butyrate():
    """SC-F7: consumer 가 butyrate 분비(secretion edge)."""
    _, bundle = solve_pair("gurobi")
    but_sec = [
        e for e in bundle.edges.to_pylist()
        if e["metabolite"] == "but" and e["edge_type"] == "secretion"
        and e["source_id"] == "consumer"
    ]
    assert but_sec and but_sec[0]["weight"] > 0, "consumer butyrate secretion 부재"


def test_sign_convention_holds():
    """SC-F7: profile 부호 규약(+secretion/−uptake) + ui_flux≥0."""
    _, bundle = solve_pair("gurobi")
    for r in bundle.profile.to_pylist():
        if r["net_flux"] > 0:
            assert r["label"] == "secretion"
        elif r["net_flux"] < 0:
            assert r["label"] == "uptake"
        assert r["ui_flux"] >= 0.0


def test_golden_hash_exact():
    """synthetic golden 회귀(gurobi 결정적, hash-exact)."""
    _, bundle = solve_pair("gurobi")
    for table in ("nodes", "edges", "profile"):
        exp = pq.read_table(EXPECTED / f"{table}.parquet")
        fresh = normalized_table_hash(getattr(bundle, table), DEFAULT_DECIMALS)
        assert fresh == normalized_table_hash(exp, DEFAULT_DECIMALS), f"{table} golden 불일치"


def test_golden_fixtures_committed():
    for f in ("nodes.parquet", "edges.parquet", "profile.parquet", "config.json"):
        assert (EXPECTED / f).exists()
    assert isinstance(EXPECTED, Path)
