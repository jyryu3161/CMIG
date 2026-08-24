"""Round-7 regression coverage for interaction figure specifications and rendering."""

from __future__ import annotations

import builtins
import hashlib
import json

import pytest

from cmig.core import interaction_figures as figures
from cmig.render.figure_style import (
    FIGURE_TIFF_DPI,
    FONT_STACK,
    SVG_HASHSALT,
    SVG_METADATA,
    load_matplotlib_pyplot,
    polish_matplotlib_axes,
    save_publication_tiff,
)


def _interaction_data():
    member_secretion = {
        "zeta": {"but": 1.0, "ac": 1.0},
        "alpha": {"ac": 3.0},
    }
    transfer = {"ac": 2.0}
    edges = figures.host_microbe_interaction_rows(
        microbial_secretion={"ac": 4.0, "but": 1.0},
        host_uptake={"ac": 2.0},
        microbe_to_host=transfer,
        member_secretion=member_secretion,
        condition="treated",
    )
    contributions = figures.contribution_rows(member_secretion, transfer)
    return edges, figures.matrix_rows(edges, condition="treated"), contributions


def _write_spec(out):
    edges, matrix, contributions = _interaction_data()
    manifest = {
        "figure_schema_version": "1.0",
        "figure_modes": ["circle", "heatmap", "bubble", "contribution"],
        "hidden_by_default": ["h", "h2o", "co2"],
    }
    return figures.write_interaction_artifacts(
        out,
        edge_rows=edges,
        matrix=matrix,
        contributions=contributions,
        figure_manifest=manifest,
    )


def test_interaction_module_adopts_the_shared_figure_policy() -> None:
    assert figures.FONT_STACK is FONT_STACK
    assert figures.FIGURE_TIFF_DPI == FIGURE_TIFF_DPI == 600
    assert figures.SVG_HASHSALT == SVG_HASHSALT == "cmig-svg-v1"
    assert figures.SVG_METADATA is SVG_METADATA
    assert figures._load_matplotlib is load_matplotlib_pyplot
    assert figures._save_publication_tiff is save_publication_tiff
    assert figures._polish_axes is polish_matplotlib_axes


def test_figure_rows_are_sorted_normalized_and_attribution_is_explicit() -> None:
    edges, matrix, contributions = _interaction_data()

    assert [(row["source"], row["metabolite"], row["edge_type"]) for row in edges] == [
        ("alpha", "ac", "secretion"),
        ("zeta", "ac", "secretion"),
        ("zeta", "but", "secretion"),
        ("met:ac", "ac", "host_uptake"),
        ("microbiome", "ac", "cross_feeding"),
    ]
    assert [row["normalized_flux"] for row in edges[:3]] == [0.75, 0.25, 0.25]
    assert all(row["condition"] == "treated" for row in edges)
    assert matrix == sorted(
        matrix,
        key=lambda row: (row["source"], row["target"], row["measure"]),
    )
    assert [(row["member"], row["contribution_fraction"]) for row in contributions] == [
        ("alpha", 0.75),
        ("zeta", 0.25),
    ]
    assert all(row["identifiable"] is False for row in contributions)


def test_figure_spec_artifacts_and_hashes_are_deterministic(tmp_path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    assert _write_spec(first) == _write_spec(second)
    for name in (
        "interaction_edges.csv",
        "interaction_matrix.csv",
        "member_contribution.csv",
        "figure_manifest.json",
    ):
        left = (first / name).read_bytes()
        right = (second / name).read_bytes()
        assert hashlib.sha256(left).digest() == hashlib.sha256(right).digest()
    manifest = json.loads((first / "figure_manifest.json").read_text())
    assert manifest["figure_modes"] == ["circle", "heatmap", "bubble", "contribution"]


def test_rendered_svg_and_tiff_hashes_are_deterministic_when_matplotlib_is_available(
    tmp_path,
) -> None:
    pytest.importorskip("matplotlib")
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    _write_spec(first)
    _write_spec(second)

    first_names = figures.render_interaction_figures(first)
    second_names = figures.render_interaction_figures(second)

    assert first_names == second_names
    assert first_names == [
        "interaction_circle.svg",
        "interaction_circle.tiff",
        "interaction_heatmap.svg",
        "interaction_heatmap.tiff",
        "interaction_bubble.svg",
        "interaction_bubble.tiff",
        "member_contribution.svg",
        "member_contribution.tiff",
    ]
    for name in first_names:
        assert hashlib.sha256((first / name).read_bytes()).digest() == hashlib.sha256(
            (second / name).read_bytes()
        ).digest()


def test_tables_and_figure_spec_survive_when_matplotlib_is_absent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _write_spec(tmp_path)
    real_import = builtins.__import__

    def without_matplotlib(name, *args, **kwargs):
        if name == "matplotlib" or name.startswith("matplotlib."):
            raise ModuleNotFoundError("matplotlib intentionally unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_matplotlib)

    with pytest.raises(ModuleNotFoundError, match="matplotlib intentionally unavailable"):
        figures.render_interaction_figures(tmp_path)
    assert (tmp_path / "interaction_edges.csv").exists()
    assert json.loads((tmp_path / "figure_manifest.json").read_text())[
        "figure_schema_version"
    ] == "1.0"
