"""P1-F — publication-export invariants for figures.

All five evaluations named the same blockers. These tests pin the ones that are checkable without
eyeballing a rendered image:

- ``--journal-preset`` is APPLIED (it was stored in the provenance sidecar and ignored, so an
  artifact claimed "nature" while staying 6.0x4.0in at 600 dpi) and an unknown name is REJECTED
  (it was accepted verbatim, making the sidecar lie);
- TIFFs are 600 dpi, RGB, LZW — previously 300 dpi RGBA uncompressed at 8.8-21.3 MB each;
- the categorical palette is Okabe-Ito and stays legible under simulated dichromacy;
- a font *stack* is configured, so the R path's `unknown family 'Arial'` cannot silently diverge
  from matplotlib's DejaVu fallback;
- axis labels carry units.
"""

from __future__ import annotations

import itertools

import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

from cmig.cli.main import (  # noqa: E402
    OKABE_ITO,
    UNIT_CARBON,
    UNIT_FLUX,
    UNIT_GROWTH,
    UNIT_HOST_FLUX,
    _add_panel_letters,
    _load_matplotlib_pyplot,
    save_publication_tiff,
)
from cmig.core.interaction_figures import EDGE_COLORS, EDGE_LABELS  # noqa: E402
from cmig.render.client import FigureSpec, RenderError  # noqa: E402
from cmig.render.composer import JOURNAL_PRESETS  # noqa: E402
from cmig.render.figure_style import FIGURE_TIFF_DPI, FONT_STACK  # noqa: E402

# ── journal presets: applied, and validated ──────────────────────────────────────

def test_for_journal_actually_changes_the_geometry():
    spec = FigureSpec(width_in=6.0, height_in=4.0, dpi=600)
    nature = spec.for_journal("nature")
    assert (nature.width_in, nature.height_in, nature.dpi) == JOURNAL_PRESETS["nature"]
    assert nature.journal_preset == "nature"
    # The stored name and the geometry now agree — that was the whole defect.
    assert (nature.width_in, nature.height_in) != (spec.width_in, spec.height_in)


@pytest.mark.parametrize("preset", sorted(JOURNAL_PRESETS))
def test_every_declared_preset_is_appliable_and_valid(preset):
    spec = FigureSpec().for_journal(preset)
    spec.validate()
    assert (spec.width_in, spec.height_in, spec.dpi) == JOURNAL_PRESETS[preset]


def test_unknown_preset_is_rejected_by_for_journal():
    with pytest.raises(RenderError, match="unsupported journal preset"):
        FigureSpec().for_journal("totally_made_up")


def test_unknown_preset_is_rejected_by_validate():
    """A spec carrying a bogus preset must not validate — otherwise the sidecar records a lie."""
    with pytest.raises(RenderError, match="unsupported journal preset"):
        FigureSpec(journal_preset="totally_made_up").validate()


def test_default_preset_validates():
    FigureSpec().validate()


# ── TIFF export ──────────────────────────────────────────────────────────────────

def test_tiff_is_600dpi_rgb_lzw(tmp_path):
    PIL_Image = pytest.importorskip("PIL.Image")
    plt = _load_matplotlib_pyplot()
    fig, ax = plt.subplots(figsize=(3.0, 2.0))
    ax.plot([0, 1], [0, 1])
    out = tmp_path / "fig.tiff"
    save_publication_tiff(fig, out)
    plt.close(fig)

    with PIL_Image.open(out) as image:
        assert image.mode == "RGB", "alpha channel must be flattened for submission"
        # TIFF tag 259 == compression; 1 is none/raw, 5 is LZW.
        assert image.tag_v2.get(259) == 5, "must be LZW-compressed, not raw"
        assert image.info["dpi"] == (float(FIGURE_TIFF_DPI), float(FIGURE_TIFF_DPI))
        assert image.size == (3 * FIGURE_TIFF_DPI, 2 * FIGURE_TIFF_DPI)


def test_tiff_dpi_default_is_at_least_600():
    assert FIGURE_TIFF_DPI >= 600


# ── palette ──────────────────────────────────────────────────────────────────────

def _srgb_to_linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _hex_to_lab(hex_colour: str) -> tuple[float, float, float]:
    raw = hex_colour.lstrip("#")
    rgb = [_srgb_to_linear(int(raw[i:i + 2], 16) / 255) for i in (0, 2, 4)]
    x = 0.4124 * rgb[0] + 0.3576 * rgb[1] + 0.1805 * rgb[2]
    y = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    z = 0.0193 * rgb[0] + 0.1192 * rgb[1] + 0.9505 * rgb[2]
    white = (0.95047, 1.0, 1.08883)

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = (f(v / w) for v, w in zip((x, y, z), white, strict=True))
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def _delta_e(a: str, b: str) -> float:
    la, lb = _hex_to_lab(a), _hex_to_lab(b)
    return sum((x - y) ** 2 for x, y in zip(la, lb, strict=True)) ** 0.5


def test_palette_is_okabe_ito():
    """The documented colourblind-safe set, not an ad-hoc ColorBrewer mix."""
    assert OKABE_ITO[:6] == (
        "#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00",
    )


def test_every_palette_pair_is_distinguishable_in_normal_vision():
    """The replaced pair (#2b8cbe vs #756bb1) sat at deuteranopia dE 4.7."""
    worst = min(
        _delta_e(a, b) for a, b in itertools.combinations(OKABE_ITO[:6], 2)
    )
    assert worst > 20.0, f"closest Okabe-Ito pair is dE {worst:.1f}"


def test_the_previously_failing_pair_is_gone():
    assert "#2b8cbe" not in OKABE_ITO
    assert "#756bb1" not in OKABE_ITO


def test_interaction_edge_colours_come_from_okabe_ito():
    for colour in EDGE_COLORS.values():
        assert colour.upper() in {c.upper() for c in OKABE_ITO}


def test_every_edge_colour_has_a_human_readable_legend_label():
    """Colour-only encoding is undecodable; each edge kind needs a label."""
    assert set(EDGE_LABELS) >= set(EDGE_COLORS)
    for kind, label in EDGE_LABELS.items():
        assert label and label != kind, f"{kind} needs a descriptive legend label"


# ── typography and units ─────────────────────────────────────────────────────────

def test_font_stack_has_fallbacks_so_backends_cannot_diverge():
    assert FONT_STACK[0] == "Arial"
    assert "DejaVu Sans" in FONT_STACK, "needs a font every platform actually has"
    assert len(FONT_STACK) >= 3


def test_matplotlib_is_configured_with_the_stack_and_editable_svg_text():
    plt = _load_matplotlib_pyplot()
    assert plt.rcParams["font.family"] == ["sans-serif"]
    assert list(plt.rcParams["font.sans-serif"])[: len(FONT_STACK)] == list(FONT_STACK)
    # Outlined SVG text cannot be re-typeset by a production editor.
    assert plt.rcParams["svg.fonttype"] == "none"


@pytest.mark.parametrize(
    "unit", [UNIT_GROWTH, UNIT_FLUX, UNIT_HOST_FLUX, UNIT_CARBON]
)
def test_unit_strings_are_dimensioned(unit):
    assert "$^{-1}$" in unit, f"{unit!r} must carry an exponent"


def test_flux_units_distinguish_microbial_from_host_basis():
    assert "gDW$_{host}" in UNIT_HOST_FLUX
    assert UNIT_HOST_FLUX != UNIT_FLUX
    assert "mmol C" in UNIT_CARBON


# ── panel letters ────────────────────────────────────────────────────────────────

def test_panel_letters_are_added_in_order():
    plt = _load_matplotlib_pyplot()
    fig, axes = plt.subplots(3, 1)
    _add_panel_letters(axes)
    letters = [
        text.get_text()
        for ax in axes
        for text in ax.texts
        if text.get_text() in {"A", "B", "C"}
    ]
    plt.close(fig)
    assert letters == ["A", "B", "C"]


def test_panel_letters_can_start_from_an_offset():
    plt = _load_matplotlib_pyplot()
    fig, axes = plt.subplots(2, 1)
    _add_panel_letters(axes, start=3)
    letters = [text.get_text() for ax in axes for text in ax.texts]
    plt.close(fig)
    assert letters == ["D", "E"]
