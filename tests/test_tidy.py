"""SC-9 tidy 계약 준수 — §4.6. Plan SC: SC-9."""

import pyarrow as pa
import pytest

from cmig.core.tidy import (
    EDGES_SCHEMA,
    NODES_SCHEMA,
    PROFILE_SCHEMA,
    TIDY_SCHEMA_VERSION,
    TidyBundle,
    TidyContractError,
    empty_bundle,
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
