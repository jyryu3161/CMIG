"""Round 8 U2: edge weights and intervals use one community-contribution basis."""

from __future__ import annotations

import math

import pytest

from cmig.core.engine import SolveResult
from cmig.core.interactions import build_tidy
from cmig.core.tidy import (
    EDGE_WEIGHT_BASIS,
    LEGACY_EDGE_WEIGHT_BASIS,
    TIDY_SCHEMA_VERSION,
    MissingAbundanceError,
)


def _result(
    *,
    abundances: dict[str, float | None] | None = None,
    member_exchange: dict[str, dict[str, float]] | None = None,
) -> SolveResult:
    exchange = member_exchange or {"A": {"ac": 8.0}, "B": {"ac": -5.0}}
    members = sorted(exchange)
    return SolveResult(
        objective=0.9,
        member_growth={member: 0.4 for member in members},
        abundances=abundances or {"A": 0.25, "B": 0.75},
        external_exchange={"ac": 0.0},
        member_exchange=exchange,
        status="optimal",
        flux_report_status="full",
        growth_solver="gurobi",
        flux_solver="gurobi",
        members=members,
    )


def _edge(bundle, edge_type: str, member: str) -> dict[str, object]:
    endpoint = "source_id" if edge_type == "secretion" else "target_id"
    return next(
        row
        for row in bundle.edges.to_pylist()
        if row["edge_type"] == edge_type and row[endpoint] == member
    )


def test_schema_13_marks_the_community_basis_semantic_change():
    assert TIDY_SCHEMA_VERSION == "1.3"
    assert LEGACY_EDGE_WEIGHT_BASIS == "per_taxon_unweighted"
    assert EDGE_WEIGHT_BASIS == "community_abundance_weighted"


def test_direct_and_cross_feeding_edges_are_abundance_weighted():
    bundle = build_tidy(_result())

    assert _edge(bundle, "secretion", "A")["weight"] == pytest.approx(8.0 * 0.25)
    assert _edge(bundle, "uptake", "B")["weight"] == pytest.approx(5.0 * 0.75)
    cross = next(row for row in bundle.edges.to_pylist() if row["edge_type"] == "cross_feeding")
    assert cross["weight"] == pytest.approx(min(8.0 * 0.25, 5.0 * 0.75))


def test_community_weighting_fixes_the_low_abundance_ranking_inversion():
    result = _result(
        abundances={"rare": 0.01, "common": 0.99},
        member_exchange={"rare": {"ac": 100.0}, "common": {"ac": 2.0}},
    )
    raw = {member: exchange["ac"] for member, exchange in result.member_exchange.items()}
    assert raw["rare"] > raw["common"]

    secretion = {
        str(row["source_id"]): float(row["weight"])
        for row in build_tidy(result).edges.to_pylist()
        if row["edge_type"] == "secretion"
    }
    assert secretion == {"common": pytest.approx(1.98), "rare": pytest.approx(1.0)}
    assert secretion["common"] > secretion["rare"]


def test_many_to_many_cross_feeding_conserves_weighted_supply_and_demand():
    result = _result(
        abundances={"S1": 0.1, "S2": 0.4, "C1": 0.2, "C2": 0.3},
        member_exchange={
            "S1": {"ac": 8.0},
            "S2": {"ac": 2.0},
            "C1": {"ac": -1.0},
            "C2": {"ac": -5.0},
        },
    )
    cross = [
        row for row in build_tidy(result).edges.to_pylist()
        if row["edge_type"] == "cross_feeding"
    ]
    assert sum(float(row["weight"]) for row in cross) == pytest.approx(1.6)
    supplied = {
        source: sum(float(row["weight"]) for row in cross if row["source_id"] == source)
        for source in ("S1", "S2")
    }
    consumed = {
        target: sum(float(row["weight"]) for row in cross if row["target_id"] == target)
        for target in ("C1", "C2")
    }
    assert supplied == {"S1": pytest.approx(0.8), "S2": pytest.approx(0.8)}
    assert consumed["C1"] <= 0.2 + 1e-12
    assert consumed["C2"] <= 1.5 + 1e-12


def test_fva_bounds_are_scaled_for_secretion_and_uptake():
    bundle = build_tidy(
        _result(),
        edge_fva={
            ("A", "ac"): (1.0, 9.0),
            ("B", "ac"): (-7.0, -2.0),
        },
    )
    secretion = _edge(bundle, "secretion", "A")
    uptake = _edge(bundle, "uptake", "B")
    assert (secretion["weight_lo"], secretion["weight_hi"]) == pytest.approx((0.25, 2.25))
    assert (uptake["weight_lo"], uptake["weight_hi"]) == pytest.approx((1.5, 5.25))
    cross = next(row for row in bundle.edges.to_pylist() if row["edge_type"] == "cross_feeding")
    assert cross["weight_lo"] is None and cross["weight_hi"] is None


def test_sign_crossing_fva_bounds_map_to_each_edge_directions_magnitude():
    bundle = build_tidy(
        _result(),
        edge_fva={
            ("A", "ac"): (-4.0, 10.0),
            ("B", "ac"): (-4.0, 10.0),
        },
    )
    secretion = _edge(bundle, "secretion", "A")
    uptake = _edge(bundle, "uptake", "B")
    assert (secretion["weight_lo"], secretion["weight_hi"]) == pytest.approx((0.0, 2.5))
    assert (uptake["weight_lo"], uptake["weight_hi"]) == pytest.approx((0.0, 3.0))


@pytest.mark.parametrize("missing", [None, math.nan, math.inf, -0.1])
def test_missing_or_invalid_abundance_fails_before_publishing_edges(missing):
    result = _result(abundances={"A": missing, "B": 0.75})
    with pytest.raises(MissingAbundanceError, match="cannot convert|finite and non-negative"):
        build_tidy(result)


def test_zero_abundance_is_a_real_zero_contribution_not_missing():
    bundle = build_tidy(_result(abundances={"A": 0.0, "B": 1.0}))
    assert _edge(bundle, "secretion", "A")["weight"] == 0.0
