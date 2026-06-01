"""dFBA — well-mixed 동적 FBA (Roadmap Phase 3.3, §13).

Design Ref: §13 dFBA / cmig-dfba.design. Plan SC: SC-DF1~DF6.

Static Optimization Approach (Mahadevan 2002): 매 step (1) Michaelis-Menten 흡수 한계로 exchange
lower_bound 설정 → (2) cobra FBA(LP) → (3) explicit Euler 로 biomass·농도 갱신. **non-negativity**
강제(농도<0 방지: dt 적응 halving). 자체 LP 미구현(cobra 위임). scipy 불요(explicit Euler).

부호 규약: cobra exchange flux v<0=흡수(농도↓), v>0=분비(농도↑) → dS = v·X·dt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

TIMECOURSE_SCHEMA_VERSION = "1.0"

TIMECOURSE_SCHEMA = pa.schema([
    ("schema_version", pa.string()),
    ("t", pa.float64()),
    ("series", pa.string()),       # "biomass" | "growth_rate" | exchange_id(농도)
    ("value", pa.float64()),
])


@dataclass(frozen=True)
class DfbaConfig:
    """dFBA 시뮬레이션 설정."""

    t_end: float
    initial_concentrations: dict[str, float]   # exchange_id → 초기 농도(mmol/L)
    dt: float = 0.1
    initial_biomass: float = 0.01              # gDW/L
    km: float = 0.01                           # Michaelis 상수
    vmax: dict[str, float] | None = None       # exchange_id → 최대 흡수(기본=모델 |lb|)
    min_dt: float = 1e-4
    growth_floor: float = 1e-6                 # μ ≤ floor → stalled 종료


@dataclass(frozen=True)
class DfbaTimepoint:
    t: float
    biomass: float
    growth_rate: float
    concentrations: dict[str, float]


@dataclass(frozen=True)
class DfbaResult:
    timecourse: list[DfbaTimepoint]
    status: str                                # completed | infeasible | stalled
    diagnostic: str | None = None
    managed_exchanges: list[str] = field(default_factory=list)


def _growth_of(model: Any, sol: Any) -> float:
    from cobra.util.solver import linear_reaction_coefficients
    coeffs = linear_reaction_coefficients(model)
    return sum(float(c) * float(sol.fluxes[rxn.id]) for rxn, c in coeffs.items())


def simulate_dfba(model: Any, config: DfbaConfig, *, solver: str = "gurobi") -> DfbaResult:
    """well-mixed dFBA. timecourse + status. non-negativity 강제(dt 적응)."""
    from cmig.core.single_model import _require_lp
    _require_lp(solver)
    model.solver = solver

    managed = list(config.initial_concentrations)
    # vmax 기본 = 모델 exchange |lower_bound| (정의된 최대 흡수율)
    vmax = dict(config.vmax) if config.vmax else {}
    for ex in managed:
        if ex not in vmax:
            vmax[ex] = abs(model.reactions.get_by_id(ex).lower_bound)

    conc = dict(config.initial_concentrations)
    biomass = config.initial_biomass
    t = 0.0
    dt = config.dt
    tc: list[DfbaTimepoint] = [DfbaTimepoint(0.0, biomass, 0.0, dict(conc))]

    while t < config.t_end - 1e-12:
        # (1) Michaelis-Menten 흡수 한계 → exchange lower_bound
        for ex in managed:
            s = max(conc[ex], 0.0)
            uptake = vmax[ex] * s / (config.km + s) if s > 0 else 0.0
            model.reactions.get_by_id(ex).lower_bound = -uptake
        # (2) FBA
        sol = model.optimize()
        if sol.status != "optimal":
            return DfbaResult(tc, "infeasible", f"FBA status={sol.status} at t={t:.4f}", managed)
        mu = _growth_of(model, sol)
        if mu <= config.growth_floor:                       # 성장 정지 → stalled 종료
            return DfbaResult(tc, "stalled", None, managed)
        # (3) explicit Euler + non-negativity (농도<0 이면 dt halving)
        step_dt = min(dt, config.t_end - t)
        while step_dt >= config.min_dt:
            new_conc = {
                ex: conc[ex] + float(sol.fluxes[ex]) * biomass * step_dt for ex in managed
            }
            if all(v >= -1e-9 for v in new_conc.values()):  # non-negativity OK
                break
            step_dt /= 2.0                                  # 적응: 농도 음수 방지
        else:
            # min_dt 에서도 음수 → 0 으로 clamp(고갈) 후 진행
            new_conc = {ex: max(conc[ex] + float(sol.fluxes[ex]) * biomass * config.min_dt, 0.0)
                        for ex in managed}
            step_dt = config.min_dt
        conc = {ex: max(v, 0.0) for ex, v in new_conc.items()}
        biomass = biomass + mu * biomass * step_dt
        t += step_dt
        tc.append(DfbaTimepoint(t, biomass, mu, dict(conc)))

    return DfbaResult(tc, "completed", None, managed)


def timecourse_rows(result: DfbaResult) -> list[dict[str, Any]]:
    """DfbaResult → timecourse long-format 행 (series별)."""
    rows: list[dict[str, Any]] = []
    for tp in result.timecourse:
        rows.append({"t": tp.t, "series": "biomass", "value": tp.biomass})
        rows.append({"t": tp.t, "series": "growth_rate", "value": tp.growth_rate})
        for ex, v in tp.concentrations.items():
            rows.append({"t": tp.t, "series": ex, "value": v})
    return rows


def build_timecourse(result: DfbaResult) -> pa.Table:
    return pa.Table.from_pylist(
        [{"schema_version": TIMECOURSE_SCHEMA_VERSION, **r} for r in timecourse_rows(result)],
        schema=TIMECOURSE_SCHEMA,
    )


def write_timecourse(table: pa.Table, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, p)
    return p
