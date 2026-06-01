"""F5 — tidy schema v1.1 migration. Plan SC: SC-C5.

writer 항상 v1.1 · v1.0 parquet 는 read_legacy_or_upgrade 로 승격(하위호환) · 신규 컬럼.
"""

from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from cmig.core.tidy import (
    NODES_SCHEMA,
    NODES_SCHEMA_V10,
    PROFILE_SCHEMA_V10,
    TIDY_SCHEMA_VERSION,
    TidyBundle,
    read_legacy_or_upgrade,
)


def test_schema_version_is_11():
    assert TIDY_SCHEMA_VERSION == "1.1"
    # v1.1 = v1.0 + host-microbe 확장 3컬럼 (nodes)
    assert set(NODES_SCHEMA.names) - set(NODES_SCHEMA_V10.names) == {
        "organism_type", "interface", "compartment",
    }


def test_writer_emits_v11(tmp_path):
    """build_tidy/write 는 항상 v1.1 + 신규 컬럼."""
    pytest.importorskip("micom")
    from cmig.golden_fixture import solve

    _, bundle = solve("gurobi")
    bundle.write(tmp_path)
    nodes = pq.read_table(tmp_path / "nodes.parquet")
    assert "organism_type" in nodes.column_names
    assert set(nodes.column("schema_version").to_pylist()) == {"1.1"}
    # member 노드는 organism_type=microbe, pool 은 null
    rows = nodes.to_pylist()
    members = [r for r in rows if r["node_type"] == "member"]
    assert members and all(r["organism_type"] == "microbe" for r in members)


def _v10_nodes():
    return pa.table({
        "schema_version": ["1.0", "1.0"], "node_id": ["A", "pool"],
        "node_type": ["member", "environment_pool"], "label": ["A", "ENV"],
        "growth": [0.4, None], "abundance": [1.0, None],
    }, schema=NODES_SCHEMA_V10)


def _v10_edges():
    return pa.table({
        "schema_version": ["1.0"], "source_id": ["A"], "target_id": ["pool"],
        "metabolite": ["ac"], "edge_type": ["secretion"], "weight": [5.0], "label": ["secretion"],
    })


def _v10_profile():
    return pa.table({
        "schema_version": ["1.0"], "metabolite": ["ac"], "net_flux": [5.0],
        "ui_flux": [5.0], "label": ["secretion"], "fva_lo": [None], "fva_hi": [None],
    }, schema=PROFILE_SCHEMA_V10)


def test_legacy_v10_parquet_read_upgrades(tmp_path):
    """SC-C5 핵심: v1.0 parquet 을 read() 로 읽으면 v1.1 로 승격(default 주입)·검증 통과."""
    pq.write_table(_v10_nodes(), tmp_path / "nodes.parquet")
    pq.write_table(_v10_edges(), tmp_path / "edges.parquet")
    pq.write_table(_v10_profile(), tmp_path / "profile.parquet")

    bundle = TidyBundle.read(tmp_path)              # 즉시 exact-validate 실패 없이 승격
    assert set(bundle.nodes.column("schema_version").to_pylist()) == {"1.1"}
    assert "organism_type" in bundle.nodes.column_names
    # default microbe 계약: member→microbe, environment_pool→None
    org = dict(zip(
        bundle.nodes.column("node_id").to_pylist(),
        bundle.nodes.column("organism_type").to_pylist(),
        strict=True,
    ))
    assert org["A"] == "microbe" and org["pool"] is None


def test_empty_v10_table_upgrades():
    """#3: 빈 v1.0 테이블도 컬럼-존재 기준으로 승격(row 0 견고)."""
    empty_v10 = PROFILE_SCHEMA_V10.empty_table()
    upgraded = read_legacy_or_upgrade(empty_v10, "profile")
    assert "organism_type" in upgraded.column_names      # 신규 컬럼 주입됨
    assert "interface" in upgraded.column_names and "compartment" in upgraded.column_names


def test_read_legacy_or_upgrade_idempotent_on_v11():
    """이미 v1.1 인 테이블은 read_legacy_or_upgrade 가 그대로 반환."""
    pytest.importorskip("micom")
    from cmig.golden_fixture import solve

    _, bundle = solve("gurobi")
    same = read_legacy_or_upgrade(bundle.nodes, "nodes")
    assert same.column_names == bundle.nodes.column_names
