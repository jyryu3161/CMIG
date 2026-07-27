"""dFBA — well-mixed 동적 FBA (Roadmap Phase 3.3, §13).

Design Ref: §13 dFBA / cmig-dfba.design. Plan SC: SC-DF1~DF6.

Static Optimization Approach (Mahadevan 2002): 매 step (1) Michaelis-Menten 흡수 한계로 exchange
lower_bound 설정 → (2) cobra FBA(LP) → (3) explicit Euler 로 biomass·농도 갱신. **non-negativity**
강제(농도<0 방지: dt 적응 halving). 자체 LP 미구현(cobra 위임). scipy 불요(explicit Euler).

부호 규약: cobra exchange flux v<0=흡수(농도↓), v>0=분비(농도↑) → dS = v·X·dt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
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
    # D5: close every uptake outside initial_concentrations before integrating, so growth cannot
    # be supported by an unconstrained default-medium substrate that is never depleted.
    close_untracked_uptake: bool = False

    def __post_init__(self) -> None:
        numeric = {
            "t_end": self.t_end,
            "dt": self.dt,
            "initial_biomass": self.initial_biomass,
            "km": self.km,
            "min_dt": self.min_dt,
            "growth_floor": self.growth_floor,
        }
        if any(
            isinstance(value, bool) or not math.isfinite(float(value))
            for value in numeric.values()
        ):
            raise ValueError("dFBA numeric configuration must contain finite numbers")
        if self.t_end <= 0.0 or self.dt <= 0.0 or self.initial_biomass <= 0.0:
            raise ValueError("dFBA t_end, dt, and initial_biomass must be > 0")
        if self.km < 0.0 or self.min_dt <= 0.0 or self.growth_floor < 0.0:
            raise ValueError("dFBA km/growth_floor must be >= 0 and min_dt must be > 0")
        if self.min_dt > self.dt:
            raise ValueError("dFBA min_dt cannot exceed dt")
        if not self.initial_concentrations:
            raise ValueError("dFBA requires at least one managed exchange concentration")
        for exchange, concentration in self.initial_concentrations.items():
            if (
                not str(exchange).strip()
                or isinstance(concentration, bool)
                or not math.isfinite(float(concentration))
                or concentration < 0.0
            ):
                raise ValueError(
                    f"invalid dFBA initial concentration: {exchange}={concentration}"
                )
        if self.vmax is not None:
            extras = set(self.vmax) - set(self.initial_concentrations)
            if extras:
                raise ValueError(f"dFBA vmax keys are not managed exchanges: {sorted(extras)}")
            for exchange, value in self.vmax.items():
                if (
                    isinstance(value, bool)
                    or not math.isfinite(float(value))
                    or value < 0.0
                ):
                    raise ValueError(f"invalid dFBA vmax: {exchange}={value}")


@dataclass(frozen=True)
class DfbaTimepoint:
    t: float
    biomass: float
    growth_rate: float
    concentrations: dict[str, float]
    step_dt: float = 0.0
    exchange_fluxes: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class DfbaResult:
    timecourse: list[DfbaTimepoint]
    status: str                                # completed | infeasible | stalled
    diagnostic: str | None = None
    managed_exchanges: list[str] = field(default_factory=list)
    # Codex D5: exchanges the organism actually consumed that are NOT tracked. Their bounds come
    # from the model's default medium and are never depleted, so biomass can rise while the
    # tracked substrate sits untouched and the endpoint becomes independent of Km.
    untracked_uptake: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DfbaBalanceAudit:
    n_steps: int
    max_concentration_residual: float
    max_biomass_residual: float
    concentrations_nonnegative: bool


@dataclass(frozen=True)
class DfbaSensitivityRow:
    dt: float
    km: float
    status: str
    n_steps: int
    final_t: float
    final_biomass: float
    final_concentrations: dict[str, float]
    depletion_times: dict[str, float | None]
    max_concentration_residual: float
    max_biomass_residual: float
    relative_biomass_error_to_finest_dt: float
    # Round 5 (opus F4): each grid run can determine that its own result is NOT interpretable as a
    # tracked-substrate/Km experiment (growth fed by untracked, never-depleting default-medium
    # substrates). Dropping that verdict here made the audit certify exactly the runs it exists to
    # catch, so the row carries it. `untracked_uptake` is the structured verdict; `warnings` also
    # carries purely informational notes (e.g. "closed N untracked uptake exchanges"), so the
    # acceptance decision keys on the former, never on warning truthiness.
    untracked_uptake: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DfbaSensitivityResult:
    rows: list[DfbaSensitivityRow]
    source_config: DfbaConfig


def _growth_of(model: Any, sol: Any) -> float:
    from cobra.util.solver import linear_reaction_coefficients
    coeffs = linear_reaction_coefficients(model)
    return sum(float(c) * float(sol.fluxes[rxn.id]) for rxn, c in coeffs.items())


def _exposes_exchanges(model: Any) -> bool:
    """True iff the model can enumerate every reaction that may supply it mass.

    Round 6 (track B, instance 4): this used to probe ``model.exchanges``. That view excludes
    sinks and demands, so both the closure and the diagnostic below were blind to them — measured
    on a sink-fed run: the tracked substrate stayed at 0.0 while biomass went 0.01 -> 5.01 ->
    2510.01, with ``untracked_uptake: {}`` and ``warnings: []``. ``model.boundary`` is the
    complete view; see :mod:`cmig.core.boundary`.
    """
    from cmig.core.boundary import exposes_boundary

    return exposes_boundary(model)


def _record_untracked_uptake(
    model: Any,
    sol: Any,
    managed: list[str],
    untracked_uptake: dict[str, float],
) -> None:
    """Accumulate the peak supply rate of every boundary reaction the run does not track.

    "Supply" rather than "negative flux": for a boundary reaction written ``--> met`` the
    supplying direction is *positive*, so the old ``flux < -1e-9`` test could not see a supplying
    demand at all. :func:`cmig.core.boundary.supply_rate` decides the direction from the
    stoichiometry.
    """
    from cmig.core.boundary import SUPPLY_TOLERANCE, boundary_reactions, supply_rate

    if not _exposes_exchanges(model):
        return
    for reaction in boundary_reactions(model):
        rid = str(reaction.id)
        if rid in managed:
            continue
        try:
            flux = float(sol.fluxes[rid])
        except (KeyError, TypeError, ValueError):
            continue
        rate = supply_rate(reaction, flux)
        if rate > SUPPLY_TOLERANCE:
            untracked_uptake[rid] = max(untracked_uptake.get(rid, 0.0), rate)


def _untracked_warnings(
    untracked_uptake: dict[str, float],
    managed: list[str],
    closed_untracked: list[str],
) -> list[str]:
    """Say plainly when growth was fed by substrates the run does not track (Codex D5).

    Round-2 observed biomass rise 0.05 -> 0.0623 and acetate 0 -> 0.508 while the managed glucose
    pool stayed at exactly 10.0, and the sensitivity endpoint came out independent of Km. That is
    not a dFBA result about glucose: the organism was eating something else, from a default-medium
    pool with no concentration and therefore no depletion and no Michaelis term.
    """
    warnings: list[str] = []
    if closed_untracked:
        warnings.append(
            f"closed {len(closed_untracked)} untracked uptake exchanges before integrating so "
            "the tracked-substrate experiment is controlled"
        )
    if not untracked_uptake:
        return warnings
    ranked = sorted(untracked_uptake.items(), key=lambda kv: -kv[1])[:8]
    detail = ", ".join(f"{rid} (max {rate:.3g})" for rid, rate in ranked)
    warnings.append(
        f"growth was supported by {len(untracked_uptake)} UNCONSTRAINED default-medium "
        f"substrates outside the tracked set {sorted(managed)}: {detail}. Those pools have no "
        "concentration, so they are never depleted and no Michaelis-Menten term applies to them "
        "— biomass can rise while the tracked substrate is untouched, and a Km sweep on the "
        "tracked substrate is NOT interpretable. Re-run with --close-untracked-uptake, or track "
        "these exchanges with --initial, before reporting a substrate/Km result."
    )
    return warnings


def simulate_dfba(model: Any, config: DfbaConfig, *, solver: str = "gurobi") -> DfbaResult:
    """well-mixed dFBA. timecourse + status. non-negativity 강제(dt 적응)."""
    from cmig.core.single_model import _require_lp
    _require_lp(solver)

    with model:
        from cmig.core.single_model import set_model_solver
        set_model_solver(model, solver)

        managed = list(config.initial_concentrations)
        # vmax 기본 = 모델 exchange |lower_bound| (정의된 최대 흡수율)
        vmax = dict(config.vmax) if config.vmax else {}
        for ex in managed:
            if ex not in vmax:
                vmax[ex] = abs(model.reactions.get_by_id(ex).lower_bound)

        # D5: optionally close every uptake the run does not track, so the tracked
        # substrate/Km experiment is actually controlled rather than merely instrumented.
        closed_untracked: list[str] = []
        if config.close_untracked_uptake:
            if not _exposes_exchanges(model):
                # Silently not closing them would report a controlled experiment that never was.
                raise ValueError(
                    "--close-untracked-uptake needs a model exposing .boundary; "
                    "this model does not, so untracked uptake cannot be closed"
                )
            from cmig.core.boundary import close_boundary_supply

            # Against `model.boundary`, so a sink or demand cannot feed the run behind the
            # experiment's back. The managed exchanges are the declared substrates and are kept.
            closure = close_boundary_supply(model, keep=managed)
            closed_untracked = list(closure.closed)

        conc = dict(config.initial_concentrations)
        biomass = config.initial_biomass
        t = 0.0
        dt = config.dt
        tc: list[DfbaTimepoint] = [DfbaTimepoint(0.0, biomass, 0.0, dict(conc))]
        untracked_uptake: dict[str, float] = {}

        while t < config.t_end - 1e-12:
            # (1) Michaelis-Menten 흡수 한계 → exchange lower_bound
            for ex in managed:
                s = max(conc[ex], 0.0)
                uptake = vmax[ex] * s / (config.km + s) if s > 0 else 0.0
                model.reactions.get_by_id(ex).lower_bound = -uptake
            # (2) FBA
            sol = model.optimize()
            if sol.status != "optimal":
                return DfbaResult(
                    tc, "infeasible", f"FBA status={sol.status} at t={t:.4f}", managed,
                    untracked_uptake,
                    _untracked_warnings(untracked_uptake, managed, closed_untracked),
                )
            # Record every uptake outside the managed set; these are the substrates that make a
            # Km sweep on the tracked one uninterpretable. This is a diagnostic: a model that
            # cannot enumerate its exchanges yields no warning rather than aborting the run.
            _record_untracked_uptake(model, sol, managed, untracked_uptake)
            mu = _growth_of(model, sol)
            if mu <= config.growth_floor:                       # 성장 정지 → stalled 종료
                return DfbaResult(
                    tc, "stalled", None, managed, untracked_uptake,
                    _untracked_warnings(untracked_uptake, managed, closed_untracked),
                )
            # (3) explicit Euler + non-negativity (농도<0 이면 dt halving)
            step_dt = min(dt, config.t_end - t)
            growth_scale = 1.0
            while step_dt >= config.min_dt:
                new_conc = {
                    ex: conc[ex] + float(sol.fluxes[ex]) * biomass * step_dt for ex in managed
                }
                if all(v >= -1e-9 for v in new_conc.values()):  # non-negativity OK
                    break
                step_dt /= 2.0                                  # 적응: 농도 음수 방지
            else:
                # min_dt 에서도 음수 → 가용 기질 이하로 flux/growth를 함께 스케일.
                # 잔여 시간이 min_dt 미만이면 t_end 초과(범위 밖 timepoint) 방지로 잔여로 클램프.
                step_dt = min(config.min_dt, config.t_end - t)
                fractions = []
                for ex in managed:
                    flux = float(sol.fluxes[ex])
                    required = -flux * biomass * step_dt
                    if required > 0.0:
                        fractions.append(max(0.0, min(1.0, conc[ex] / required)))
                growth_scale = min(fractions) if fractions else 1.0
                new_conc = {
                    ex: max(conc[ex] + float(sol.fluxes[ex]) * biomass * step_dt * growth_scale,
                            0.0)
                    for ex in managed
                }
            conc = {ex: max(v, 0.0) for ex, v in new_conc.items()}
            effective_mu = mu * growth_scale
            effective_fluxes = {
                ex: float(sol.fluxes[ex]) * growth_scale for ex in managed
            }
            biomass = biomass + effective_mu * biomass * step_dt
            t += step_dt
            tc.append(
                DfbaTimepoint(
                    t,
                    biomass,
                    effective_mu,
                    dict(conc),
                    step_dt=step_dt,
                    exchange_fluxes=effective_fluxes,
                )
            )

        return DfbaResult(
            tc, "completed", None, managed, untracked_uptake,
            _untracked_warnings(untracked_uptake, managed, closed_untracked),
        )


def audit_dfba_balance(result: DfbaResult) -> DfbaBalanceAudit:
    """Recompute explicit-Euler update residuals from stored step fluxes."""
    max_concentration = 0.0
    max_biomass = 0.0
    nonnegative = True
    for previous, current in zip(
        result.timecourse[:-1], result.timecourse[1:], strict=True
    ):
        dt = current.step_dt
        expected_biomass = previous.biomass + current.growth_rate * previous.biomass * dt
        max_biomass = max(max_biomass, abs(current.biomass - expected_biomass))
        for exchange in result.managed_exchanges:
            expected = (
                previous.concentrations[exchange]
                + current.exchange_fluxes[exchange] * previous.biomass * dt
            )
            max_concentration = max(
                max_concentration, abs(current.concentrations[exchange] - expected)
            )
            nonnegative = nonnegative and current.concentrations[exchange] >= -1e-9
    return DfbaBalanceAudit(
        n_steps=max(0, len(result.timecourse) - 1),
        max_concentration_residual=max_concentration,
        max_biomass_residual=max_biomass,
        concentrations_nonnegative=nonnegative,
    )


def _depletion_times(
    result: DfbaResult, *, threshold: float = 1e-6
) -> dict[str, float | None]:
    return {
        exchange: next(
            (
                point.t
                for point in result.timecourse
                if point.concentrations[exchange] <= threshold
            ),
            None,
        )
        for exchange in result.managed_exchanges
    }


def run_dfba_sensitivity(
    model: Any,
    config: DfbaConfig,
    *,
    dts: list[float],
    kms: list[float],
    solver: str = "gurobi",
) -> DfbaSensitivityResult:
    """Run a deterministic dt×Km grid and compare each run to the finest dt per Km."""
    if not dts or not kms:
        raise ValueError("dFBA sensitivity requires non-empty dts and kms")
    if any(not math.isfinite(value) or value <= 0.0 for value in dts):
        raise ValueError("dFBA sensitivity dts must be finite and > 0")
    if any(not math.isfinite(value) or value < 0.0 for value in kms):
        raise ValueError("dFBA sensitivity kms must be finite and >= 0")
    raw: list[tuple[float, float, DfbaResult, DfbaBalanceAudit]] = []
    for km in sorted(set(float(value) for value in kms)):
        for dt in sorted(set(float(value) for value in dts)):
            run_config = replace(config, dt=dt, km=km, min_dt=min(config.min_dt, dt))
            result = simulate_dfba(model, run_config, solver=solver)
            raw.append((dt, km, result, audit_dfba_balance(result)))

    finest = {
        km: next(
            result.timecourse[-1].biomass
            for dt, row_km, result, _audit in raw
            if row_km == km and dt == min(item[0] for item in raw if item[1] == km)
        )
        for km in sorted({item[1] for item in raw})
    }
    rows: list[DfbaSensitivityRow] = []
    for dt, km, result, audit in raw:
        final = result.timecourse[-1]
        reference = finest[km]
        relative_error = abs(final.biomass - reference) / max(abs(reference), 1e-12)
        rows.append(
            DfbaSensitivityRow(
                dt=dt,
                km=km,
                status=result.status,
                n_steps=audit.n_steps,
                final_t=final.t,
                final_biomass=final.biomass,
                final_concentrations=dict(final.concentrations),
                depletion_times=_depletion_times(result),
                max_concentration_residual=audit.max_concentration_residual,
                max_biomass_residual=audit.max_biomass_residual,
                relative_biomass_error_to_finest_dt=relative_error,
                untracked_uptake=dict(result.untracked_uptake),
                warnings=list(result.warnings),
            )
        )
    return DfbaSensitivityResult(rows=rows, source_config=config)


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
