"""SC-9 tidy 계약 준수 — §4.6. Plan SC: SC-9."""

import pyarrow as pa
import pytest

from cmig.core.tidy import (
    EDGE_WEIGHT_BASIS,
    EDGES_SCHEMA,
    LEGACY_EDGE_WEIGHT_BASIS,
    NODES_SCHEMA,
    PROFILE_SCHEMA,
    TIDY_SCHEMA_VERSION,
    LegacyEdgeBasisWarning,
    TidyBundle,
    TidyContractError,
    empty_bundle,
    read_legacy_or_upgrade,
)


def _nodes():
    return pa.table({
        "schema_version": [TIDY_SCHEMA_VERSION, TIDY_SCHEMA_VERSION],
        "node_id": ["A", "pool"],
        "node_type": ["member", "environment_pool"],
        "label": ["Org A", "ENV"],
        "growth": [0.42, None],
        "abundance": [1.0, None],
        "organism_type": ["microbe", None],     # F5: host-microbe 확장
        "interface": [None, None],
        "compartment": [None, None],
    }, schema=NODES_SCHEMA)


def _edges():
    return pa.table({
        "schema_version": [TIDY_SCHEMA_VERSION],
        "source_id": ["A"], "target_id": ["B"], "metabolite": ["ac"],
        "edge_type": ["cross_feeding"], "weight": [5.0], "label": ["secretion"],
        # Cross-feeding attribution is allocated, not identified.
        "allocation_method": ["proportional_shared_pool"], "identifiable": [False],
        "weight_lo": [None], "weight_hi": [None],
    }, schema=EDGES_SCHEMA)


def _profile():
    return pa.table({
        "schema_version": [TIDY_SCHEMA_VERSION],
        "metabolite": ["glc"], "net_flux": [-10.0], "ui_flux": [10.0],
        "label": ["uptake"], "fva_lo": [None], "fva_hi": [None],
        "organism_type": [None], "interface": [None], "compartment": [None],
    }, schema=PROFILE_SCHEMA)


def test_valid_bundle_passes():
    TidyBundle(nodes=_nodes(), edges=_edges(), profile=_profile()).validate()


def test_empty_bundle_valid():
    empty_bundle().validate()


def test_schema_version_present_on_all_tables():
    for schema in (NODES_SCHEMA, EDGES_SCHEMA, PROFILE_SCHEMA):
        assert "schema_version" in schema.names


def test_edge_weight_basis_changed_at_schema_13():
    assert TIDY_SCHEMA_VERSION == "1.3"
    assert LEGACY_EDGE_WEIGHT_BASIS == "per_taxon_unweighted"
    assert EDGE_WEIGHT_BASIS == "community_abundance_weighted"


def _node_row(node_type="member", version=TIDY_SCHEMA_VERSION):
    return pa.table({
        "schema_version": [version], "node_id": ["A"], "node_type": [node_type],
        "label": ["x"], "growth": [0.1], "abundance": [1.0],
        "organism_type": ["microbe"], "interface": [None], "compartment": [None],
    }, schema=NODES_SCHEMA)


def test_bad_node_type_rejected():
    with pytest.raises(TidyContractError):
        TidyBundle(nodes=_node_row("alien"), edges=_edges(), profile=_profile()).validate()


def test_wrong_schema_version_rejected():
    with pytest.raises(TidyContractError):
        TidyBundle(nodes=_node_row(version="9.9"), edges=_edges(), profile=_profile()).validate()


def test_roundtrip_write_read(tmp_path):
    b = TidyBundle(nodes=_nodes(), edges=_edges(), profile=_profile())
    b.write(tmp_path)
    rt = TidyBundle.read(tmp_path)
    assert rt.nodes.num_rows == 2
    assert rt.edges.column("weight").to_pylist() == [5.0]
    assert rt.profile.column("label").to_pylist() == ["uptake"]


def test_bundle_reader_semantically_migrates_12_edge_weights_and_bounds(tmp_path):
    import pyarrow.parquet as pq

    nodes = pa.Table.from_pylist([
        {"schema_version": "1.2", "node_id": "A", "node_type": "member", "label": "A",
         "growth": 0.4, "abundance": 0.25, "organism_type": "microbe", "interface": None,
         "compartment": None},
        {"schema_version": "1.2", "node_id": "B", "node_type": "member", "label": "B",
         "growth": 0.4, "abundance": 0.75, "organism_type": "microbe", "interface": None,
         "compartment": None},
        {"schema_version": "1.2", "node_id": "medium", "node_type": "environment_pool",
         "label": "medium", "growth": None, "abundance": None, "organism_type": None,
         "interface": None, "compartment": None},
    ], schema=NODES_SCHEMA)
    edges = pa.Table.from_pylist([
        {"schema_version": "1.2", "source_id": "A", "target_id": "medium",
         "metabolite": "ac", "edge_type": "secretion", "weight": 8.0,
         "label": "secretion", "allocation_method": "direct_flux", "identifiable": True,
         "weight_lo": 1.0, "weight_hi": 9.0},
        {"schema_version": "1.2", "source_id": "medium", "target_id": "B",
         "metabolite": "ac", "edge_type": "uptake", "weight": 5.0, "label": "uptake",
         "allocation_method": "direct_flux", "identifiable": True, "weight_lo": -7.0,
         "weight_hi": -2.0},
        {"schema_version": "1.2", "source_id": "A", "target_id": "B",
         "metabolite": "ac", "edge_type": "cross_feeding", "weight": 5.0,
         "label": "secretion", "allocation_method": "proportional_shared_pool",
         "identifiable": False, "weight_lo": None, "weight_hi": None},
    ], schema=EDGES_SCHEMA)
    profile = pa.Table.from_pylist([
        {"schema_version": "1.2", "metabolite": "ac", "net_flux": -1.75,
         "ui_flux": 1.75, "label": "uptake", "fva_lo": None, "fva_hi": None,
         "organism_type": None, "interface": None, "compartment": None},
    ], schema=PROFILE_SCHEMA)
    for name, table in (("nodes", nodes), ("edges", edges), ("profile", profile)):
        pq.write_table(table, tmp_path / f"{name}.parquet")

    migrated = TidyBundle.read(tmp_path)
    by_type = {str(row["edge_type"]): row for row in migrated.edges.to_pylist()}
    assert by_type["secretion"]["weight"] == pytest.approx(2.0)
    assert (by_type["secretion"]["weight_lo"], by_type["secretion"]["weight_hi"]) \
        == pytest.approx((0.25, 2.25))
    assert by_type["uptake"]["weight"] == pytest.approx(3.75)
    assert (by_type["uptake"]["weight_lo"], by_type["uptake"]["weight_hi"]) \
        == pytest.approx((1.5, 5.25))
    assert by_type["cross_feeding"]["weight"] == pytest.approx(2.0)
    assert set(migrated.edges.column("schema_version").to_pylist()) == {"1.3"}


def test_bare_legacy_edge_upgrade_uses_null_not_a_fabricated_community_value():
    legacy = pa.Table.from_pylist([
        {**_edges().to_pylist()[0], "schema_version": "1.2"},
    ], schema=EDGES_SCHEMA)
    with pytest.warns(LegacyEdgeBasisWarning, match="nodes.abundance is required"):
        row = read_legacy_or_upgrade(legacy, "edges").to_pylist()[0]
    assert row["schema_version"] == "1.3"
    assert row["weight"] is None and row["weight_lo"] is None and row["weight_hi"] is None
