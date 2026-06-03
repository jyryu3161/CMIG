"""Interaction tables and publication-oriented SVG figures for CMIG runs."""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

INTERACTION_EDGE_COLUMNS = (
    "source",
    "target",
    "metabolite",
    "edge_type",
    "flux",
    "normalized_flux",
    "condition",
    "used_by_host",
)
INTERACTION_MATRIX_COLUMNS = ("source", "target", "measure", "value", "condition")
MEMBER_CONTRIBUTION_COLUMNS = (
    "member",
    "metabolite",
    "secretion_flux",
    "transfer_flux",
    "contribution_fraction",
)
CURRENCY_METABOLITES = frozenset({"h", "h2o", "co2"})
EDGE_COLORS = {
    "secretion": "#2ca25f",
    "host_uptake": "#3182bd",
    "cross_feeding": "#e6550d",
}
BAR_COLORS = ("#3182bd", "#2ca25f", "#756bb1", "#e6550d", "#636363")


def host_microbe_interaction_rows(
    *,
    microbial_secretion: dict[str, float],
    host_uptake: dict[str, float],
    microbe_to_host: dict[str, float],
    member_secretion: dict[str, dict[str, float]] | None = None,
    condition: str = "default",
) -> list[dict[str, Any]]:
    """Build edge rows for host-microbe interactions."""
    member_fluxes = [
        abs(v)
        for secretion in (member_secretion or {}).values()
        for v in secretion.values()
    ]
    max_flux = max(
        [abs(v) for v in microbial_secretion.values()]
        + [abs(v) for v in host_uptake.values()]
        + [abs(v) for v in microbe_to_host.values()]
        + member_fluxes
        + [1.0]
    )
    rows: list[dict[str, Any]] = []
    member_sources = member_secretion or {}
    if member_sources:
        for member, secretion in sorted(member_sources.items()):
            for met, flux in sorted(secretion.items()):
                if flux > 1e-9:
                    rows.append(_edge_row(
                        source=member,
                        target=f"met:{met}",
                        metabolite=met,
                        edge_type="secretion",
                        flux=flux,
                        max_flux=max_flux,
                        condition=condition,
                        used_by_host=met in microbe_to_host,
                    ))
    else:
        for met, flux in sorted(microbial_secretion.items()):
            if flux > 1e-9:
                rows.append(_edge_row(
                    source="microbiome",
                    target=f"met:{met}",
                    metabolite=met,
                    edge_type="secretion",
                    flux=flux,
                    max_flux=max_flux,
                    condition=condition,
                    used_by_host=met in microbe_to_host,
                ))
    for met, flux in sorted(host_uptake.items()):
        if flux > 1e-9:
            rows.append(_edge_row(
                source=f"met:{met}",
                target="host",
                metabolite=met,
                edge_type="host_uptake",
                flux=flux,
                max_flux=max_flux,
                condition=condition,
                used_by_host=True,
            ))
    for met, flux in sorted(microbe_to_host.items()):
        if flux > 1e-9:
            rows.append(_edge_row(
                source="microbiome",
                target="host",
                metabolite=met,
                edge_type="cross_feeding",
                flux=flux,
                max_flux=max_flux,
                condition=condition,
                used_by_host=True,
            ))
    return rows


def contribution_rows(
    member_secretion: dict[str, dict[str, float]],
    microbe_to_host: dict[str, float],
) -> list[dict[str, Any]]:
    """Member contribution to transferred host metabolites."""
    totals: dict[str, float] = defaultdict(float)
    for secretion in member_secretion.values():
        for met, flux in secretion.items():
            if flux > 1e-9:
                totals[met] += flux
    rows: list[dict[str, Any]] = []
    for member, secretion in sorted(member_secretion.items()):
        for met, flux in sorted(secretion.items()):
            if met not in microbe_to_host:
                continue
            total = totals.get(met, 0.0)
            if flux <= 1e-9 or total <= 0.0:
                continue
            frac = flux / total
            rows.append({
                "member": member,
                "metabolite": met,
                "secretion_flux": flux,
                "transfer_flux": microbe_to_host.get(met, 0.0) * frac,
                "contribution_fraction": frac,
            })
    return rows


def matrix_rows(
    edge_rows: list[dict[str, Any]], *, condition: str = "default"
) -> list[dict[str, Any]]:
    """Aggregate source-target interaction matrix rows."""
    grouped: dict[tuple[str, str, str], float] = defaultdict(float)
    for row in edge_rows:
        key = (str(row["source"]), str(row["target"]), str(row["edge_type"]))
        grouped[key] += float(row["flux"])
    return [
        {"source": s, "target": t, "measure": measure, "value": value, "condition": condition}
        for (s, t, measure), value in sorted(grouped.items())
    ]


def write_interaction_artifacts(
    out_dir: str | Path,
    *,
    edge_rows: list[dict[str, Any]],
    matrix: list[dict[str, Any]],
    contributions: list[dict[str, Any]],
    figure_manifest: dict[str, Any],
) -> list[str]:
    """Write reusable interaction tables and return artifact names."""
    out = Path(out_dir)
    artifacts = [
        "interaction_edges.csv",
        "interaction_matrix.csv",
        "member_contribution.csv",
        "figure_manifest.json",
    ]
    _write_csv(out / "interaction_edges.csv", edge_rows, INTERACTION_EDGE_COLUMNS)
    _write_csv(out / "interaction_matrix.csv", matrix, INTERACTION_MATRIX_COLUMNS)
    _write_csv(out / "member_contribution.csv", contributions, MEMBER_CONTRIBUTION_COLUMNS)
    (out / "figure_manifest.json").write_text(
        json.dumps(figure_manifest, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    )
    return artifacts


def render_interaction_figures(out_dir: str | Path, *, top_n: int = 20) -> list[str]:
    """Render circle, heatmap, bubble, and contribution SVG/TIFF figures from saved CSV."""
    out = Path(out_dir)
    edges = _read_csv(out / "interaction_edges.csv")
    contributions = _read_csv(out / "member_contribution.csv")
    svg_artifacts = [
        _render_circle(edges, out / "interaction_circle.svg", top_n=top_n),
        _render_heatmap(edges, out / "interaction_heatmap.svg"),
        _render_bubble(edges, out / "interaction_bubble.svg", top_n=top_n),
        _render_contribution(contributions, out / "member_contribution.svg", top_n=top_n),
    ]
    names: list[str] = []
    for path in svg_artifacts:
        names.append(path.name)
        tiff = path.with_suffix(".tiff")
        if tiff.exists():
            names.append(tiff.name)
    return names


def _edge_row(
    *,
    source: str,
    target: str,
    metabolite: str,
    edge_type: str,
    flux: float,
    max_flux: float,
    condition: str,
    used_by_host: bool,
) -> dict[str, Any]:
    return {
        "source": source,
        "target": target,
        "metabolite": metabolite,
        "edge_type": edge_type,
        "flux": float(flux),
        "normalized_flux": float(flux) / max_flux if max_flux else 0.0,
        "condition": condition,
        "used_by_host": bool(used_by_host),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: tuple[str, ...]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(columns))
        writer.writeheader()
        for row in rows:
            writer.writerow({col: _csv_cell(row.get(col)) for col in columns})


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _csv_cell(value: Any) -> Any:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return "" if not math.isfinite(value) else f"{value:.12g}"
    return "" if value is None else value


def _load_matplotlib() -> Any:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.family": "Arial",
        "axes.titlesize": 14,
        "axes.labelsize": 11,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "svg.fonttype": "none",
    })
    return plt


def _save_svg_and_tiff(fig: Any, path: Path) -> None:
    fig.savefig(path, format="svg")
    fig.savefig(path.with_suffix(".tiff"), format="tiff", dpi=300)


def _polish_axes(ax: Any, *, grid_axis: str = "x") -> None:
    ax.grid(True, axis=grid_axis, color="#d9dee3", linewidth=0.7, alpha=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def _filtered_edges(rows: list[dict[str, str]], *, top_n: int) -> list[dict[str, str]]:
    items = [
        row for row in rows
        if row.get("metabolite") not in CURRENCY_METABOLITES
    ]
    items.sort(key=lambda r: abs(float(r.get("flux") or 0.0)), reverse=True)
    return items[:top_n]


def _render_circle(rows: list[dict[str, str]], path: Path, *, top_n: int) -> Path:
    plt = _load_matplotlib()
    edges = _filtered_edges(rows, top_n=top_n)
    nodes = sorted({r["source"] for r in edges} | {r["target"] for r in edges})
    fig, ax = plt.subplots(figsize=(8.2, 7.2), dpi=300)
    ax.axis("off")
    ax.set_title("Interaction circle", pad=24)
    ax.set_xlim(-1.62, 1.62)
    ax.set_ylim(-1.56, 1.72)
    if not nodes:
        _save_svg_and_tiff(fig, path)
        plt.close(fig)
        return path
    coords = {}
    radius = 1.14
    for i, node in enumerate(nodes):
        angle = 2 * math.pi * i / len(nodes)
        coords[node] = (radius * math.cos(angle), radius * math.sin(angle))
    max_flux = max(abs(float(r.get("flux") or 0.0)) for r in edges) if edges else 1.0
    for row in edges:
        x1, y1 = coords[row["source"]]
        x2, y2 = coords[row["target"]]
        width = 0.5 + 4.5 * abs(float(row["flux"])) / max_flux
        ax.annotate(
            "",
            xy=(x2, y2),
            xytext=(x1, y1),
            arrowprops={
                "arrowstyle": "->",
                "lw": width,
                "color": EDGE_COLORS.get(row["edge_type"], "#777777"),
                "alpha": 0.65,
                "shrinkA": 16,
                "shrinkB": 16,
            },
        )
    for node, (x, y) in coords.items():
        color = "#e6550d" if node == "host" else "#9aa0a6" if node.startswith("met:") else "#3182bd"
        ax.scatter([x], [y], s=430, color=color, edgecolor="white", linewidth=1.4, zorder=3)
        ax.text(
            x * 1.23,
            y * 1.23,
            node.replace("met:", ""),
            ha="center",
            va="center",
            fontsize=10,
        )
    fig.tight_layout()
    fig.subplots_adjust(top=0.9)
    _save_svg_and_tiff(fig, path)
    plt.close(fig)
    return path


def _render_heatmap(rows: list[dict[str, str]], path: Path) -> Path:
    plt = _load_matplotlib()
    filtered = [r for r in rows if r.get("metabolite") not in CURRENCY_METABOLITES]
    sources = sorted({r["source"] for r in filtered})
    targets = sorted({r["target"] for r in filtered})
    values = [[0.0 for _ in targets] for _ in sources]
    s_idx = {s: i for i, s in enumerate(sources)}
    t_idx = {t: i for i, t in enumerate(targets)}
    for row in filtered:
        values[s_idx[row["source"]]][t_idx[row["target"]]] += float(row["flux"] or 0.0)
    width = max(6.5, 0.42 * len(targets) + 2.5)
    height = max(4.8, 0.42 * len(sources) + 2.2)
    fig, ax = plt.subplots(figsize=(width, height), dpi=300)
    if sources and targets:
        im = ax.imshow(values, cmap="viridis", aspect="auto")
        fig.colorbar(im, ax=ax, shrink=0.8, label="Flux")
    ax.set_xticks(
        range(len(targets)),
        [x.replace("met:", "") for x in targets],
        rotation=45,
        ha="right",
    )
    ax.set_yticks(range(len(sources)), [x.replace("met:", "") for x in sources])
    ax.set_title("Aggregate interaction heatmap")
    ax.tick_params(axis="both", labelsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_xticks([x - 0.5 for x in range(1, len(targets))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, len(sources))], minor=True)
    ax.grid(which="minor", color="white", linewidth=0.6, alpha=0.55)
    fig.tight_layout()
    fig.subplots_adjust(bottom=0.28, left=0.18, right=0.88)
    _save_svg_and_tiff(fig, path)
    plt.close(fig)
    return path


def _render_bubble(rows: list[dict[str, str]], path: Path, *, top_n: int) -> Path:
    plt = _load_matplotlib()
    edges = _filtered_edges(rows, top_n=top_n)
    sources = sorted({r["source"] for r in edges})
    metabolites = sorted({r["metabolite"] for r in edges})
    width = max(6.5, 0.45 * len(sources) + 2.4)
    height = max(4.8, 0.32 * len(metabolites) + 2.0)
    fig, ax = plt.subplots(figsize=(width, height), dpi=300)
    x_map = {s: i for i, s in enumerate(sources)}
    y_map = {m: i for i, m in enumerate(metabolites)}
    max_flux = max([abs(float(row.get("flux") or 0.0)) for row in edges] + [1.0])
    for row in edges:
        flux = abs(float(row["flux"] or 0.0))
        ax.scatter(
            x_map[row["source"]],
            y_map[row["metabolite"]],
            s=70 + 380 * flux / max_flux,
            color=EDGE_COLORS.get(row["edge_type"], "#777777"),
            alpha=0.82,
            edgecolor="white",
            linewidth=0.8,
        )
    ax.set_xticks(range(len(sources)), sources, rotation=45, ha="right")
    ax.set_yticks(range(len(metabolites)), metabolites)
    ax.set_title("Interaction bubble plot")
    _polish_axes(ax, grid_axis="both")
    fig.tight_layout()
    fig.subplots_adjust(bottom=0.28, left=0.18)
    _save_svg_and_tiff(fig, path)
    plt.close(fig)
    return path


def _render_contribution(rows: list[dict[str, str]], path: Path, *, top_n: int) -> Path:
    plt = _load_matplotlib()
    items = [r for r in rows if float(r.get("transfer_flux") or 0.0) > 1e-12]
    items.sort(key=lambda r: float(r.get("transfer_flux") or 0.0), reverse=True)
    items = items[:top_n]
    labels = [f"{r['member']}:{r['metabolite']}" for r in items]
    values = [float(r["transfer_flux"]) for r in items]
    fig, ax = plt.subplots(figsize=(7.2, 4.8), dpi=300)
    colors = [BAR_COLORS[i % len(BAR_COLORS)] for i, _ in enumerate(labels[::-1])]
    ax.barh(labels[::-1], values[::-1], color=colors, edgecolor="white", linewidth=0.8, height=0.55)
    ax.set_xlabel("Transfer flux")
    ax.set_title("Member contribution to host transfer")
    _polish_axes(ax, grid_axis="x")
    fig.tight_layout()
    _save_svg_and_tiff(fig, path)
    plt.close(fig)
    return path
