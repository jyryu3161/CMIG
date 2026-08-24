"""Shared matplotlib policy for publication-oriented CMIG figures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

# A font *stack*: the R/ggplot path aborted on ``unknown family 'Arial'`` and
# matplotlib silently fell back to DejaVu, so the two backends disagreed.
FONT_STACK: tuple[str, ...] = ("Arial", "Helvetica", "DejaVu Sans")

# Journals reject uncompressed RGBA TIFFs; 600 dpi is the line-art expectation.
FIGURE_TIFF_DPI = 600

# matplotlib otherwise stamps wall-clock time into SVG metadata and derives
# generated element ids from a random salt. These exact values are part of the
# byte-reproducibility contract for provenance-hashed figures.
SVG_HASHSALT = "cmig-svg-v1"
SVG_METADATA: dict[str, None] = {"Date": None}


def load_matplotlib_pyplot() -> Any:
    """Load pyplot with CMIG's deterministic, publication-oriented rcParams."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": list(FONT_STACK),
        "axes.titlesize": 14,
        "axes.labelsize": 11,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "svg.fonttype": "none",
        "svg.hashsalt": SVG_HASHSALT,
    })
    return plt


def save_publication_tiff(
    fig: Any,
    out_tiff: Path,
    *,
    dpi: int = FIGURE_TIFF_DPI,
) -> None:
    """Write a submission-ready TIFF at the requested DPI in RGB with LZW."""
    fig.savefig(
        out_tiff,
        format="tiff",
        dpi=dpi,
        facecolor="white",
        pil_kwargs={"compression": "tiff_lzw"},
    )
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - PIL ships with matplotlib
        return
    with Image.open(out_tiff) as image:
        if image.mode == "RGB":
            return
        flattened = Image.new("RGB", image.size, (255, 255, 255))
        flattened.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
        info = dict(image.info)
    flattened.save(
        out_tiff,
        format="tiff",
        compression="tiff_lzw",
        dpi=info.get("dpi", (dpi, dpi)),
    )


def polish_matplotlib_axes(
    ax: Any,
    *,
    grid_axis: str = "x",
    grid_alpha: float = 0.85,
) -> None:
    """Apply CMIG's grid, stacking, and spine policy to an axes object."""
    ax.grid(
        True,
        axis=grid_axis,
        color="#d9dee3",
        linewidth=0.7,
        alpha=grid_alpha,
    )
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
