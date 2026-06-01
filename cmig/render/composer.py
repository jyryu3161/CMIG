"""Figure Composer — 다중 패널 R 그림 (Roadmap Phase 1.3, §9).

Design Ref: §9 (ggraph network · ComplexHeatmap · circlize chord) / cmig-figure-composer.design.
Plan SC: SC-FC1~FC5.

RenderClient(profile→ggplot2) 위에 패널 dispatch: network(ggraph, edges)·heatmap(ComplexHeatmap,
matrix)·chord(circlize, edges). GPL 격리(R subprocess). R 부재/패키지 부재 → 명시적 RenderError
(silent 위장 금지). 패키지는 .Rlib(project-local) 경유.
"""

from __future__ import annotations

import csv
import json
import math
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cmig.render.client import RenderError, rscript_path

_RENDER_R_DIR = Path(__file__).resolve().parent.parent / "render_r"
_RLIB = Path(__file__).resolve().parents[2] / ".Rlib"

# Journal preset → (width_in, height_in, dpi). 출판사 규격(단일/이중 컬럼). §9.
JOURNAL_PRESETS: dict[str, tuple[float, float, int]] = {
    "default": (6.0, 5.0, 600),
    "nature": (3.50, 3.0, 300),          # Nature 단일 컬럼 89mm
    "nature_double": (7.20, 5.0, 300),   # Nature 이중 컬럼 183mm
    "cell": (3.35, 3.0, 300),            # Cell 단일 컬럼 85mm
    "science": (2.30, 2.0, 600),         # Science 단일 컬럼 ~57mm
    "plos": (5.20, 4.0, 600),
}

PANEL_KINDS = ("network", "heatmap", "chord")
PANEL_CSV_COLUMNS: dict[str, tuple[str, ...]] = {
    "network": ("source_id", "target_id", "weight", "edge_type"),
    "chord": ("source_id", "target_id", "weight"),
    "heatmap": ("row_key", "col_key", "value"),
}
SUPPORTED_FORMATS = frozenset({"svg", "tiff"})


@dataclass(frozen=True)
class PanelSpec:
    """패널 그림 사양 (FigureSpec 확장). kind ∈ network|heatmap|chord."""

    kind: str
    title: str = "Panel"
    width_in: float = 6.0
    height_in: float = 5.0
    dpi: int = 600
    format: str = "svg"
    seed: int = 42
    journal_preset: str = "default"

    def validate(self) -> None:
        if self.kind not in PANEL_KINDS:
            raise RenderError(f"미지원 panel kind: {self.kind} (지원: {PANEL_KINDS})")
        if self.format not in SUPPORTED_FORMATS:
            raise RenderError(f"미지원 format: {self.format}")

    def with_journal(self, preset: str) -> PanelSpec:
        """출판사 규격(width/height/dpi) 적용 → 새 PanelSpec (§9 journal preset)."""
        from dataclasses import replace
        if preset not in JOURNAL_PRESETS:
            raise RenderError(f"미지원 journal preset: {preset} (지원: {sorted(JOURNAL_PRESETS)})")
        w, h, dpi = JOURNAL_PRESETS[preset]
        return replace(self, width_in=w, height_in=h, dpi=dpi, journal_preset=preset)


def _csv_cell(col: str, value: Any) -> Any:
    if col != "value" and col != "weight":
        return "" if value is None else value
    if value is None:
        return ""
    v = float(value)
    return "" if not math.isfinite(v) else f"{v:.6f}"


def _write_panel_csv(kind: str, rows: list[dict[str, Any]], path: Path) -> None:
    cols = PANEL_CSV_COLUMNS[kind]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(cols))
        w.writeheader()
        for r in rows:
            w.writerow({c: _csv_cell(c, r.get(c)) for c in cols})


class FigureComposer:
    """다중 패널 R 렌더러. kind별 R 스크립트 dispatch. R/패키지 부재 → RenderError(정직)."""

    def __init__(self, rscript: str | None = None) -> None:
        self._rscript = rscript if rscript is not None else rscript_path()

    def available(self) -> bool:
        return bool(self._rscript)

    def render_panel(
        self, rows: list[dict[str, Any]], spec: PanelSpec, out_path: str | Path,
    ) -> Path:
        """단일 패널 렌더 → 그림 파일 + figure_spec sidecar(재현). R 부재 → RenderError."""
        spec.validate()
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.with_name(out.name + ".figure_spec.json").write_text(
            json.dumps(asdict(spec), indent=2, sort_keys=True, ensure_ascii=True)
        )
        if not self.available():
            raise RenderError(
                f"Rscript 부재 — {spec.kind} 패널은 R 전용(ggraph/ComplexHeatmap/circlize). "
                f"matplotlib fallback 없음(정직: 패널 미생성)."
            )
        script = _RENDER_R_DIR / f"{spec.kind}.R"
        with tempfile.TemporaryDirectory() as td:
            data_csv = Path(td) / "data.csv"
            _write_panel_csv(spec.kind, rows, data_csv)
            cmd = [
                str(self._rscript), str(script),
                "--data", str(data_csv), "--out", str(out), "--format", spec.format,
                "--width", str(spec.width_in), "--height", str(spec.height_in),
                "--dpi", str(spec.dpi), "--title", spec.title, "--seed", str(spec.seed),
                "--rlib", str(_RLIB),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode != 0 or not out.exists():
                raise RenderError(
                    f"R {spec.kind} 패널 실패 (rc={proc.returncode}): {proc.stderr.strip()[:400]}"
                )
        return out

    def render_panels(
        self, panels: list[tuple[PanelSpec, list[dict[str, Any]]]], out_dir: str | Path,
    ) -> list[Path]:
        """다중 패널 → 파일 목록 (Figure Composer). 각 패널 독립 산출."""
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        out: list[Path] = []
        for i, (spec, rows) in enumerate(panels):
            fname = f"panel_{i:02d}_{spec.kind}.{spec.format}"
            out.append(self.render_panel(rows, spec, d / fname))
        return out
