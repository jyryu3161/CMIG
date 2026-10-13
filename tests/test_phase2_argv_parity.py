"""Phase 2 moves every analysis input to a new page; the CLI argv must not change.

EXPECTED was recorded from main d6a1d31 (before phase 2) with tests/argv_drivers.py.
Never edit EXPECTED: when a page moves, change only the driver.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from argv_drivers import DRIVERS  # noqa: E402
from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.editors import installed_medium_preset_path  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402

APP = QApplication.instance() or QApplication([])
_STAMP = re.compile(r"-\d{8}-\d{6}(?:-\d+)?")


def normalize(argv: list[str], root: Path) -> list[str]:
    presets = str(installed_medium_preset_path("western_diet").parent)
    return [
        _STAMP.sub("-<STAMP>", a.replace(presets, "<PRESETS>").replace(str(root), "<P>"))
        for a in argv
    ]


EXPECTED: dict[str, list[str]] = {
    "search_default": [
        "search", "--taxonomy", "<P>/runs/_inputs/search-<STAMP>-taxonomy.csv", "--target", "but",
        "--direction", "max_secretion", "--strategy", "auto", "--min-size", "2", "--max-size", "2",
        "--top-k", "10", "--seed", "0", "--workers", "1", "--solver-threads", "1",
        "--growth-fraction", "0.5", "--min-member-growth", "0.0", "--min-community-growth", "0.0",
        "--validate-top", "0", "--exhaustive-max", "100", "--ga-pop-size", "30",
        "--ga-generations", "20", "--ga-mutation-rate", "0.2", "--ga-immigrant-fraction", "0.1",
        "--ga-tournament-k", "3", "--ga-elitism", "2", "--ga-local-search-fraction", "0.0",
        "--medium", "<PRESETS>/western_diet.csv", "--exact-medium", "--out",
        "<P>/runs/search-<STAMP>",
    ],
    "search_advanced": [
        "search", "--taxonomy", "<P>/runs/_inputs/search-<STAMP>-taxonomy.csv", "--targets",
        "but,ac", "--target-directions", "max_secretion,max_secretion", "--target-weights", "1,2",
        "--target-scales", "but=2,ac=3", "--multi-metric", "raw_sum", "--strategy", "exhaustive",
        "--min-size", "1", "--max-size", "3", "--top-k", "5", "--seed", "7", "--workers", "1",
        "--solver-threads", "1", "--growth-fraction", "0.25", "--min-member-growth", "0.01",
        "--min-community-growth", "0.0", "--validate-top", "2", "--out", "<P>/runs/search-<STAMP>",
    ],
    "gene_ko": [
        "gene-ko-search", "--taxonomy", "<P>/runs/_inputs/gene-ko-<STAMP>-taxonomy.csv",
        "--members", "a,b", "--target", "ac", "--max-genes", "10", "--top-k", "5", "--direction",
        "min_uptake", "--growth-fraction", "0.3", "--out", "<P>/runs/gene-ko-<STAMP>", "--medium",
        "<PRESETS>/high_fiber.csv", "--exact-medium", "--member", "a",
    ],
    "strain_growth": [
        "strain-growth", "--taxonomy", "<P>/runs/_inputs/strain-growth-<STAMP>-taxonomy.csv",
        "--tradeoff-f", "0.4", "--single-medium", "community", "--out",
        "<P>/runs/strain-growth-<STAMP>", "--medium", "<PRESETS>/high_fiber.csv", "--exact-medium",
    ],
    "ratio_impact": [
        "abundance-impact", "--taxonomy", "<P>/runs/_inputs/abundance-impact-<STAMP>-taxonomy.csv",
        "--member", "b", "--fractions", "0.2,0.8", "--target", "but", "--tradeoff-f", "0.6",
        "--out", "<P>/runs/abundance-impact-<STAMP>",
    ],
    "community": [
        "solve", "--taxonomy", "<P>/runs/_inputs/community-<STAMP>-taxonomy.csv", "--tradeoff-f",
        "0.3", "--out", "<P>/runs/community-<STAMP>", "--assume-bigg-namespace",
    ],
    "host": [
        "host-microbe-bigg", "--host", "<P>/models/host.xml", "--taxonomy",
        "<P>/runs/_inputs/host-microbe-<STAMP>-taxonomy.csv", "--tradeoff-f", "0.7",
        "--microbial-biomass-gdw", "0.5", "--host-biomass-gdw", "10", "--biomass-basis-kind",
        "measured", "--biomass-basis-source", "lab record 12", "--out",
        "<P>/runs/host-microbe-<STAMP>", "--keep-host-uptake", "--host-medium",
        "<PRESETS>/western_diet.csv",
    ],
    "host_search": [
        "host-search-bigg", "--host", "<P>/models/host.xml", "--taxonomy",
        "<P>/runs/_inputs/host-search-<STAMP>-taxonomy.csv", "--target", "but", "--metric",
        "objective_value", "--min-size", "1", "--max-size", "2", "--tradeoff-f", "0.7",
        "--microbial-biomass-gdw", "0.5", "--host-biomass-gdw", "10", "--biomass-basis-kind",
        "measured", "--biomass-basis-source", "lab record 12", "--out",
        "<P>/runs/host-search-<STAMP>", "--keep-host-uptake", "--host-medium",
        "<PRESETS>/western_diet.csv",
    ],
    "dfba": [
        "dfba", "--model", "<P>/models/a.xml", "--initial", "EX_glc__D_e=5,EX_o2_e=10", "--t-end",
        "2", "--dt", "0.05", "--initial-biomass", "0.02", "--out", "<P>/runs/dfba-<STAMP>",
        "--close-untracked-uptake",
    ],
    "spatial": [
        "spatial-preview", "--metabolite", "EX_ac_e", "--width", "16", "--height", "16", "--steps",
        "10", "--dt", "0.2", "--diffusion", "0.3", "--source-edge", "top", "--sink-edge", "bottom",
        "--out", "<P>/runs/spatial-<STAMP>",
    ],
    "medium_growth": [
        "solve", "--taxonomy", "<P>/runs/_inputs/medium-growth-<STAMP>-taxonomy.csv", "--out",
        "<P>/runs/medium-growth-<STAMP>", "--assume-bigg-namespace", "--medium",
        "<P>/runs/_inputs/medium-growth-<STAMP>-medium.json", "--exact-medium",
    ],
    "minimal_medium": [
        "minimal-medium", "--model", "<P>/models/a.xml", "--min-growth", "0.1", "--oxygen-mode",
        "aerobic", "--out", "<P>/runs/minimal-medium-<STAMP>", "--assume-bigg-namespace",
        "--medium", "<P>/runs/_inputs/minimal-medium-<STAMP>-medium.json",
    ],
    "sweep": [
        "sweep", "--taxonomy", "<P>/runs/_inputs/sweep-<STAMP>-taxonomy.csv", "--tradeoff-fs",
        "0.2,0.4", "--solvers", "gurobi", "--metric", "growth", "--out", "<P>/runs/sweep-<STAMP>",
        "--assume-bigg-namespace", "--fva",
    ],
}


@pytest.mark.parametrize("name", sorted(DRIVERS))
def test_argv_unchanged(name: str, tmp_path: Path, monkeypatch) -> None:
    make_project(tmp_path / "p", ["a", "b", "host"])
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(tmp_path / "p")
    calls: list[list[str]] = []

    def recorder(argv: list[str]) -> int:
        calls.append(list(argv))
        return 2

    monkeypatch.setattr("cmig.cli.main.main", recorder)
    try:
        job = DRIVERS[name](w)
        assert job, f"{name}: the page refused to run"
        deadline = time.time() + 10
        while not calls and time.time() < deadline:
            APP.processEvents()
            time.sleep(0.02)
        w._poll_completed_jobs()
        assert calls, f"{name}: no CLI call"
        assert normalize(calls[0], w.session.require().root) == EXPECTED[name]
    finally:
        w.close_project()
