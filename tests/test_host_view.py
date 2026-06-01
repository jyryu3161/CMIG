"""Phase 3.2 — Host Impact Dashboard offscreen 검증. Plan SC: SC-HV1~HV4."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.core.host import HostSolveResult, InterfaceFlux  # noqa: E402
from cmig.core.host_impact import HostImpact  # noqa: E402
from cmig.gui.host_view import HostImpactView  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _viable_result() -> HostSolveResult:
    return HostSolveResult(
        viable=True, status="optimal", biomass=30.25,
        interface_fluxes=[
            InterfaceFlux("EX_but_lumen", "lumen", "but", -6.25, "uptake"),
            InterfaceFlux("EX_o2_blood", "blood", "o2", -31.0, "uptake"),
            InterfaceFlux("EX_co2_blood", "blood", "co2", 25.0, "secretion"),
        ],
        lumen_uptake={"but": 6.25})


def test_host_view_viable():
    """SC-HV1: viable → biomass + 2-interface flux 표."""
    _app()
    v = HostImpactView()
    v.load_host_result(_viable_result())
    assert "viable" in v.viability_label.text() and "30.25" in v.viability_label.text()
    assert v.iface_table.rowCount() == 3
    assert v.iface_table.item(0, 0).text() == "lumen"
    assert v.iface_table.item(0, 3).text() == "uptake"


def test_host_view_non_viable_explicit():
    """SC-HV2: non-viable 명시(silent 위장 금지)."""
    _app()
    v = HostImpactView()
    v.load_host_result(HostSolveResult(viable=False, status="infeasible", biomass=0.0))
    assert "non-viable" in v.viability_label.text()


def test_host_view_cross_feeding():
    """SC-HV3: microbe→host cross-feeding 표."""
    _app()
    v = HostImpactView()
    v.load_impact(HostImpact(microbe_to_host={"but": 6.25, "ac": 2.0}, host_viable=True))
    assert v.cross_table.rowCount() == 2
    rows = {v.cross_table.item(i, 0).text(): v.cross_table.item(i, 1).text()
            for i in range(v.cross_table.rowCount())}
    assert rows["but"] == "6.25"
