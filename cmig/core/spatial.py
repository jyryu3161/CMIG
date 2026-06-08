"""Lightweight COMETS-inspired spatial medium preview.

This module intentionally does not implement full spatial dFBA. It provides a
small dependency-free 2D diffusion/source-sink simulator that helps users design
COMETS-like spatial media conditions before running heavier community models.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Literal

Edge = Literal["left", "right", "top", "bottom", "center", "none"]


@dataclass(frozen=True)
class SpatialPreviewConfig:
    width: int = 32
    height: int = 32
    steps: int = 80
    dt: float = 0.1
    diffusion: float = 0.15
    initial_value: float = 0.0
    source_edge: Edge = "left"
    source_value: float = 10.0
    sink_edge: Edge = "right"
    sink_value: float = 0.0
    store_every: int = 10


@dataclass(frozen=True)
class SpatialFrame:
    step: int
    t: float
    values: list[list[float]]


@dataclass(frozen=True)
class SpatialPreviewResult:
    frames: list[SpatialFrame]
    status: str
    diagnostic: str | None = None

    @property
    def final(self) -> SpatialFrame:
        return self.frames[-1]


def validate_spatial_config(config: SpatialPreviewConfig) -> None:
    if config.width < 3 or config.height < 3:
        raise ValueError("spatial grid requires width and height >= 3")
    if config.steps < 1:
        raise ValueError("spatial preview requires steps >= 1")
    if config.dt <= 0.0:
        raise ValueError("spatial preview requires dt > 0")
    if config.diffusion < 0.0:
        raise ValueError("spatial preview requires diffusion >= 0")
    if config.store_every < 1:
        raise ValueError("spatial preview requires store_every >= 1")
    if _edges_overlap(config.source_edge, config.sink_edge):
        raise ValueError(
            "spatial source_edge and sink_edge overlap; choose non-overlapping edges"
        )


def run_spatial_preview(config: SpatialPreviewConfig) -> SpatialPreviewResult:
    """Run a stable explicit 2D diffusion preview with maintained source/sink edges."""
    validate_spatial_config(config)
    grid = [[float(config.initial_value) for _x in range(config.width)]
            for _y in range(config.height)]
    _apply_edge(grid, config.source_edge, config.source_value)
    _apply_edge(grid, config.sink_edge, config.sink_value)
    frames = [SpatialFrame(0, 0.0, _copy_grid(grid))]
    alpha = config.diffusion * config.dt
    substeps = max(1, int(ceil(alpha / 0.24))) if alpha > 0.0 else 1
    sub_dt = config.dt / substeps
    sub_alpha = config.diffusion * sub_dt

    for step in range(1, config.steps + 1):
        for _ in range(substeps):
            grid = _diffuse_once(grid, sub_alpha)
            _apply_edge(grid, config.source_edge, config.source_value)
            _apply_edge(grid, config.sink_edge, config.sink_value)
        if step % config.store_every == 0 or step == config.steps:
            frames.append(SpatialFrame(step, step * config.dt, _copy_grid(grid)))
    return SpatialPreviewResult(frames=frames, status="completed")


def spatial_rows(result: SpatialPreviewResult) -> list[dict[str, float | int]]:
    rows: list[dict[str, float | int]] = []
    for frame in result.frames:
        for y, row in enumerate(frame.values):
            for x, value in enumerate(row):
                rows.append({"step": frame.step, "t": frame.t, "x": x, "y": y, "value": value})
    return rows


def _diffuse_once(grid: list[list[float]], alpha: float) -> list[list[float]]:
    if alpha == 0.0:
        return _copy_grid(grid)
    height = len(grid)
    width = len(grid[0])
    out = [[0.0 for _x in range(width)] for _y in range(height)]
    for y in range(height):
        for x in range(width):
            center = grid[y][x]
            up = grid[y - 1][x] if y > 0 else center
            down = grid[y + 1][x] if y < height - 1 else center
            left = grid[y][x - 1] if x > 0 else center
            right = grid[y][x + 1] if x < width - 1 else center
            out[y][x] = max(center + alpha * (up + down + left + right - 4.0 * center), 0.0)
    return out


def _apply_edge(grid: list[list[float]], edge: Edge, value: float) -> None:
    height = len(grid)
    width = len(grid[0])
    if edge == "none":
        return
    if edge == "left":
        for y in range(height):
            grid[y][0] = value
    elif edge == "right":
        for y in range(height):
            grid[y][width - 1] = value
    elif edge == "top":
        for x in range(width):
            grid[0][x] = value
    elif edge == "bottom":
        for x in range(width):
            grid[height - 1][x] = value
    elif edge == "center":
        grid[height // 2][width // 2] = value


def _edges_overlap(source: Edge, sink: Edge) -> bool:
    if source == "none" or sink == "none":
        return False
    if source == sink:
        return True
    border_edges = {"left", "right", "top", "bottom"}
    opposite = {("left", "right"), ("right", "left"), ("top", "bottom"), ("bottom", "top")}
    if source in border_edges and sink in border_edges:
        return (source, sink) not in opposite
    return False


def _copy_grid(grid: list[list[float]]) -> list[list[float]]:
    return [list(row) for row in grid]
