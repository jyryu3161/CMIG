"""Signed multi-target publication figure regressions."""

from __future__ import annotations

import math
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from xml.etree import ElementTree

import pytest

pytest.importorskip("matplotlib")

from cmig.cli import main  # noqa: E402
from cmig.core.search_product import MULTI_METRIC_UNITS  # noqa: E402


def _result(
    values: tuple[float, float], *, metric: str = "raw_sum",
    unit: str | None = None, targets: tuple[str, str] = ("glc__D", "ac"),
) -> SimpleNamespace:
    row = SimpleNamespace(
        rank=1, members=("Escherichia_coli_1",), status="optimal",
        target_scores=dict(zip(targets, values, strict=True)),
        weighted_score=sum(values),
    )
    return SimpleNamespace(
        ranks=[row], targets=list(targets), metric=metric,
        score_unit=unit or MULTI_METRIC_UNITS[metric],
        normalizer="none_raw_sum_absolute_units",
        weights={target: 1.0 for target in targets},
    )


@pytest.mark.parametrize(
    ("values", "expected_bases"),
    [
        ((-10.0, 13.3588519882), (0.0, 0.0)),
        ((-4.0, -3.0), (0.0, -4.0)),
        ((4.0, 3.0), (0.0, 4.0)),
        ((-5.0, 5.0), (0.0, 0.0)),
    ],
)
def test_signed_bar_geometry_and_total(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    values: tuple[float, float], expected_bases: tuple[float, float],
) -> None:
    captured: list[Any] = []
    monkeypatch.setattr(main, "save_figure_atomic", lambda fig, *a, **k: captured.append(fig))
    monkeypatch.setattr(main, "save_publication_tiff", lambda *a, **k: None)
    main._write_multi_target_figure(_result(values), tmp_path / "signed.svg")
    fig = captured[0]
    ax = fig.axes[0]
    assert [patch.get_x() for patch in ax.patches] == pytest.approx(expected_bases)
    assert [patch.get_width() for patch in ax.patches] == pytest.approx(values)
    assert ax.collections[0].get_offsets()[0, 0] == pytest.approx(sum(values))
    assert ax.texts[0].get_text() == f"{sum(values):.6g}"
    assert [text.get_text() for text in ax.get_yticklabels()] == ["Escherichia_coli_1"]
    assert ax.get_xlabel() == "Signed score contribution"
    assert MULTI_METRIC_UNITS["raw_sum"] in fig.texts[1].get_text()


@pytest.mark.parametrize(
    ("scores", "message"),
    [({"ac": 2.0}, "no contribution"),
     ({"glc__D": float("nan"), "ac": 2.0}, "nonfinite"),
     ({"glc__D": 1.0, "ac": float("inf")}, "nonfinite"),
     ({"glc__D": None, "ac": 2.0}, "nonnumeric")],
)
def test_missing_or_nonfinite_contribution_rejected(
    tmp_path: Path, scores: dict[str, float], message: str,
) -> None:
    result = _result((1.0, 2.0))
    result.ranks[0].target_scores = scores
    with pytest.raises(ValueError, match=message):
        main._write_multi_target_figure(result, tmp_path / "invalid.svg")
    assert not (tmp_path / "invalid.svg").exists()


def test_total_must_match_stored_score(tmp_path: Path) -> None:
    result = _result((-10.0, 13.3588519882))
    result.ranks[0].weighted_score = 13.3588519882
    with pytest.raises(ValueError, match="disagree"):
        main._write_multi_target_figure(result, tmp_path / "inconsistent.svg")


def test_audit_stored_total_and_positive_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[Any] = []
    monkeypatch.setattr(main, "save_figure_atomic", lambda fig, *a, **k: captured.append(fig))
    monkeypatch.setattr(main, "save_publication_tiff", lambda *a, **k: None)
    mixed = _result((-10.0, 13.3588519882))
    mixed.ranks[0].weighted_score = 3.35885198817  # recorded audit total
    main._write_multi_target_figure(mixed, tmp_path / "mixed.svg")
    assert captured[0].axes[0].collections[0].get_offsets()[0, 0] == pytest.approx(
        3.35885198817
    )
    assert captured[0].axes[0].texts[0].get_text() == "3.35885"

    positive = _result((2.0, 5.0), targets=("first", "second"))
    positive.ranks.append(SimpleNamespace(
        rank=2, members=("second_member",), status="optimal",
        target_scores={"first": 1.0, "second": 4.0}, weighted_score=5.0,
    ))
    main._write_multi_target_figure(positive, tmp_path / "positive.svg")
    ax = captured[1].axes[0]
    assert [patch.get_x() for patch in ax.patches] == pytest.approx([0, 0, 2, 1])
    assert [patch.get_width() for patch in ax.patches] == pytest.approx([2, 1, 5, 4])
    assert [item.get_text() for item in ax.get_yticklabels()] == [
        "Escherichia_coli_1", "second_member"
    ]


def test_normalized_target_scores_keep_stored_values_but_bars_include_weights(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[Any] = []
    monkeypatch.setattr(main, "save_figure_atomic", lambda fig, *a, **k: captured.append(fig))
    monkeypatch.setattr(main, "save_publication_tiff", lambda *a, **k: None)
    result = _result((-2.0, 4.0), metric="normalized_weighted")
    result.weights = {"glc__D": 3.0, "ac": 2.0}
    result.ranks[0].weighted_score = 2.0
    main._write_multi_target_figure(result, tmp_path / "weighted.svg")
    assert result.ranks[0].target_scores == {"glc__D": -2.0, "ac": 4.0}
    ax = captured[0].axes[0]
    assert [patch.get_width() for patch in ax.patches] == pytest.approx([-6.0, 8.0])
    assert ax.collections[0].get_offsets()[0, 0] == pytest.approx(2.0)
    assert "recorded weight" in captured[0].texts[1].get_text()


def test_long_pareto_text_fits_svg_and_tiff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PIL import Image

    captured: list[Any] = []
    original = main.save_figure_atomic

    def save_and_capture(fig: Any, *args: Any, **kwargs: Any) -> Any:
        captured.append(fig)
        return original(fig, *args, **kwargs)

    monkeypatch.setattr(main, "save_figure_atomic", save_and_capture)
    result = _result(
        (13.3588519882, 0.0), metric="pareto",
        unit=MULTI_METRIC_UNITS["pareto"],
        targets=("acetate_target_with_a_long_readable_name", "butyrate"),
    )
    out = tmp_path / "pareto.svg"
    main._write_multi_target_figure(result, out)
    assert out.exists() and out.with_suffix(".tiff").exists()
    svg = out.read_text()
    assert "report order" in svg
    assert "unless --target-weights are carbon numbers" in svg
    with Image.open(out.with_suffix(".tiff")) as image:
        assert image.size[0] > 5000 and image.size[1] > 2500
        assert image.mode == "RGB"
    fig = captured[0]
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    legend = fig.axes[0].get_legend()
    assert legend is not None
    for artist in [*fig.texts, *legend.get_texts(), legend.get_title(),
                   *fig.axes[0].get_yticklabels(), *fig.axes[0].texts]:
        bounds = artist.get_window_extent(renderer)
        assert math.isfinite(bounds.width)
        assert bounds.x0 >= fig.bbox.x0 - 2 and bounds.x1 <= fig.bbox.x1 + 2
        assert bounds.y0 >= fig.bbox.y0 - 2 and bounds.y1 <= fig.bbox.y1 + 2


@pytest.mark.parametrize("case", ["pareto", "normalized", "long_labels"])
def test_saved_multi_target_svg_text_fits_qt_consumer(
    tmp_path: Path, case: str,
) -> None:
    """Measure the final editable SVG with the same renderer used by the GUI."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6.QtSvg")
    from PIL import Image
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    assert app is not None
    if case == "normalized":
        result = _result((-2.0, 4.0), metric="normalized_weighted")
        result.weights = {"glc__D": 3.0, "ac": 2.0}
        result.ranks[0].weighted_score = 2.0
    elif case == "long_labels":
        result = _result(
            (10.0, 1.0), metric="pareto",
            targets=("acetate_target_with_a_long_readable_identifier",
                     "butyrate_target_with_a_long_readable_identifier"),
        )
        members = (
            "Faecalibacterium_prausnitzii_ATCC_27768",
            "Roseburia_intestinalis_L1_82",
            "Eubacterium_rectale_ATCC_33656",
        )
        result.ranks = [SimpleNamespace(
            rank=index + 1, members=members, status="optimal",
            target_scores=dict(zip(result.targets, values, strict=True)),
            weighted_score=sum(values),
        ) for index, values in enumerate(((10., 1.), (8., 2.), (6., 3.),
                                          (4., 4.), (2., 5.)))]
    else:
        result = _result((13.3588519882, 0.0), metric="pareto")

    path = tmp_path / f"{case}.svg"
    main._write_multi_target_figure(result, path)
    svg = ElementTree.parse(path).getroot()
    editable_text = [element for element in svg.iter() if element.tag.endswith("}text")]
    assert editable_text
    families = [part.strip() for element in editable_text
                for part in element.attrib.get("style", "").split(";")
                if part.strip().startswith("font-family:")]
    assert families and all("," not in family for family in families)

    renderer = QSvgRenderer(str(path))
    assert renderer.isValid()
    canvas = renderer.viewBoxF()
    text_bounds = {}
    for element in svg.iter():
        element_id = element.attrib.get("id", "")
        if not element_id.startswith("text_"):
            continue
        bounds = renderer.transformForElement(element_id).mapRect(
            renderer.boundsOnElement(element_id)
        )
        text_bounds[element_id] = ("".join(element.itertext()).strip(), bounds)
        assert bounds.x() >= 0.5 and bounds.y() >= 0.5
        assert bounds.right() <= canvas.width() - 0.5
        assert bounds.bottom() <= canvas.height() - 0.5
    assert text_bounds
    caption = next(bounds for text, bounds in text_bounds.values()
                   if text.startswith("Targets:"))
    axis_label = next(bounds for text, bounds in text_bounds.values()
                      if text == "Signed score contribution")
    assert caption.y() >= axis_label.bottom() + 2

    if case == "long_labels":
        plot_left, plot_right = 0.23 * canvas.width(), 0.74 * canvas.width()
        members = sorted(
            (bounds for text, bounds in text_bounds.values()
             if text.startswith("Faecalibacterium")),
            key=lambda bounds: bounds.y(),
        )
        legends = sorted(
            (bounds for text, bounds in text_bounds.values()
             if text.startswith(("acetate_target", "butyrate_target"))),
            key=lambda bounds: bounds.y(),
        )
        assert len(members) == 5 and len(legends) == 2
        assert all(bounds.right() <= plot_left - 2 for bounds in members)
        assert all(bounds.x() >= plot_right + 2 for bounds in legends)
        assert all(left.bottom() + 1 <= right.y()
                   for left, right in zip(members, members[1:], strict=False))
        assert legends[0].bottom() + 1 <= legends[1].y()

    with Image.open(path.with_suffix(".tiff")) as image:
        assert image.mode == "RGB"
        assert tuple(float(value) for value in image.info["dpi"]) == (600., 600.)
        assert image.tag_v2[259] == 5  # TIFF LZW
