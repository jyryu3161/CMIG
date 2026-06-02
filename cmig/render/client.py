"""RenderClient — tidy profile → R(ggplot2) subprocess → SVG/TIFF.

Design Ref: §9 (출판 그림) / FR-2.5 / schema RunManifest.figure_specs.
GPL 격리: R 은 별도 프로세스(subprocess)로만 실행(§2). figure_spec(seed 포함) sidecar 로
재현성 보장(§9). R 부재 시 Python(matplotlib) fallback.
"""

from __future__ import annotations

import csv
import json
import math
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# cmig/render/client.py → cmig/render_r/figure.R
R_SCRIPT = Path(__file__).resolve().parent.parent / "render_r" / "figure.R"
_RLIB = Path(__file__).resolve().parents[2] / ".Rlib"

PROFILE_COLUMNS = ("metabolite", "net_flux", "ui_flux", "label")
SUPPORTED_FORMATS = frozenset({"svg", "tiff", "pdf", "eps"})
PROFILE_LABEL_COLORS = {
    "secretion": "#d62728",
    "uptake": "#1f77b4",
}


class RenderError(RuntimeError):
    """R 렌더 실패 또는 렌더러 부재."""


@dataclass(frozen=True)
class FigureSpec:
    """출판 그림 사양 (재현 단위, §9). seed/dims/format/journal preset."""

    title: str = "External Profile"
    width_in: float = 6.0
    height_in: float = 4.0
    dpi: int = 600
    format: str = "svg"            # svg | tiff
    seed: int = 42
    journal_preset: str = "default"

    def validate(self) -> None:
        if self.format not in SUPPORTED_FORMATS:
            raise RenderError(f"미지원 format: {self.format} (지원: {sorted(SUPPORTED_FORMATS)})")


def rscript_path() -> str | None:
    return shutil.which("Rscript")


def rscript_available() -> bool:
    return rscript_path() is not None


class RenderClient:
    """R Render 클라이언트. R 가용 시 subprocess, 부재 시 matplotlib fallback."""

    def __init__(self, rscript: str | None = None) -> None:
        self._rscript = rscript if rscript is not None else rscript_path()

    def available(self) -> bool:
        return bool(self._rscript)

    def render(
        self, profile_rows: list[dict[str, Any]], spec: FigureSpec, out_path: str | Path
    ) -> Path:
        """external profile rows → 그림 파일. figure_spec sidecar 동반(§9 재현)."""
        spec.validate()
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        # figure_spec sidecar (seed·dims 재현 자산)
        out.with_name(out.name + ".figure_spec.json").write_text(
            json.dumps(asdict(spec), indent=2, sort_keys=True, ensure_ascii=True)
        )
        if not self.available():
            return self._fallback(profile_rows, spec, out)
        with tempfile.TemporaryDirectory() as td:
            data_csv = Path(td) / "data.csv"
            _write_csv(profile_rows, data_csv)
            cmd = [
                str(self._rscript), str(R_SCRIPT),
                "--data", str(data_csv), "--out", str(out), "--format", spec.format,
                "--width", str(spec.width_in), "--height", str(spec.height_in),
                "--dpi", str(spec.dpi), "--title", spec.title, "--seed", str(spec.seed),
                "--rlib", str(_RLIB),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode != 0 or not out.exists():
                err = proc.stderr.strip()[:400]
                raise RenderError(f"R render 실패 (rc={proc.returncode}): {err}")
        return out

    def _fallback(self, rows: list[dict[str, Any]], spec: FigureSpec, out: Path) -> Path:
        """R 부재 시 matplotlib(plotnine/matplotlib) fallback (§9). render extra 필요."""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError as e:  # pragma: no cover - env-dependent
            raise RenderError(
                "Rscript 부재 + matplotlib fallback 미설치 (`uv sync --extra render`)."
            ) from e
        ordered = sorted(rows, key=lambda r: r.get("net_flux") or 0.0)
        labels = [r["metabolite"] for r in ordered]
        vals = [r.get("net_flux") or 0.0 for r in ordered]
        colors = []
        for row in ordered:
            label = _profile_label(row)
            colors.append("#7f7f7f" if label is None else PROFILE_LABEL_COLORS[label])
        fig, ax = plt.subplots(figsize=(spec.width_in, spec.height_in), dpi=spec.dpi)
        ax.barh(labels, vals, color=colors)
        ax.set_title(spec.title)
        ax.set_xlabel("net exchange flux (+ secretion / - uptake)")
        fig.tight_layout()
        try:
            fig.savefig(out, format=spec.format)
        finally:
            plt.close(fig)
        return out


def _profile_label(row: dict[str, Any], *, eps: float = 1e-12) -> str | None:
    label = row.get("label")
    if label in PROFILE_LABEL_COLORS:
        return str(label)
    flux = float(row.get("net_flux") or 0.0)
    if flux > eps:
        return "secretion"
    if flux < -eps:
        return "uptake"
    return None


_CSV_FLOAT_COLS = ("net_flux", "ui_flux")
_CSV_DECIMALS = 6


def _csv_cell(col: str, value: Any) -> Any:
    """CSV 셀 직렬화 (TC-7): float 컬럼은 고정 자릿수 반올림(결정성),
    None/비유한(NaN/inf)은 빈 문자열(R read.csv → NA). 'nan'/'inf' 문자열 방출 금지.
    """
    if col not in _CSV_FLOAT_COLS:
        return value
    if value is None:
        return ""
    v = float(value)
    if not math.isfinite(v):          # NaN/inf → NA (가짜 0 금지·R 오파싱 방지)
        return ""
    return f"{v:.{_CSV_DECIMALS}f}"


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(PROFILE_COLUMNS))
        writer.writeheader()
        for r in rows:
            writer.writerow({c: _csv_cell(c, r.get(c)) for c in PROFILE_COLUMNS})


def render_profile(
    bundle: Any, spec: FigureSpec, out_path: str | Path, client: RenderClient | None = None
) -> Path:
    """TidyBundle.profile → 그림 (편의 함수)."""
    rows = bundle.profile.to_pylist()
    return (client or RenderClient()).render(rows, spec, out_path)
