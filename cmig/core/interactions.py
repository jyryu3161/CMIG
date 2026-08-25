"""Interaction extraction — SolveResult → tidy (nodes/edges/profile).

Design Ref: §4.3·§4.6 / schema §2 / glossary §1.A·§1.E.
Plan SC: SC-9 (tidy 계약), SC-2 (sign 단일 진입점 경유).

cross-feeding (m→m′): m 분비(raw>0) ∧ m′ 흡수(raw<0). Shared-pool flux만으로
donor→recipient 실제 전달은 식별되지 않으므로, 대사체별 총 전달량
``min(total secretion, total uptake)``을 donor 공급·consumer 수요에 비례 배분한다. 이 방식은
결정적이며 모든 donor/consumer marginal에서 질량보존 상한을 지킨다.
모든 부호 변환은 sign 모듈 단일 진입점만 경유.
"""

from __future__ import annotations

import math
from typing import Any

import pyarrow as pa

from cmig.core.engine import SolveResult
from cmig.core.sign import NOISE_FLOOR, Label, Scope, convert
from cmig.core.tidy import (
    EDGES_SCHEMA,
    NODES_SCHEMA,
    PROFILE_SCHEMA,
    TIDY_SCHEMA_VERSION,
    MissingAbundanceError,
    TidyBundle,
)

ENV_POOL_ID = "medium"
CROSS_FEEDING_ALLOCATION_METHOD = "proportional_shared_pool"


def _label_str(label: Label | None) -> str | None:
    return label.value if label is not None else None


def allocate_cross_feeding(
    secretors: dict[str, float], consumers: dict[str, float], *, eps: float = NOISE_FLOOR
) -> list[tuple[str, str, float]]:
    """Mass-conserving shared-pool allocation for one metabolite.

    ``secretors`` values are positive secretion fluxes and ``consumers`` values are negative
    uptake fluxes, both on the same caller-selected basis. Because a steady-state shared pool does
    not identify pairwise transfers, CMIG uses a transparent proportional allocation rather than
    emitting every pairwise minimum (which double-counts mass whenever more than one donor or
    consumer exists).

    Returned weights satisfy, within floating tolerance:

    - ``sum_j w[i,j] <= secretion[i]`` for every donor,
    - ``sum_i w[i,j] <= abs(uptake[j])`` for every consumer,
    - ``sum_ij w[i,j] = min(total secretion, total uptake)``.
    """
    supply = {m: float(v) for m, v in secretors.items() if float(v) > eps}
    demand = {m: -float(v) for m, v in consumers.items() if float(v) < -eps}
    total_supply = sum(supply.values())
    total_demand = sum(demand.values())
    transferable = min(total_supply, total_demand)
    if transferable <= eps or total_supply <= eps or total_demand <= eps:
        return []

    rows: list[tuple[str, str, float]] = []
    for source in sorted(supply):
        source_share = supply[source] / total_supply
        for target in sorted(demand):
            weight = transferable * source_share * (demand[target] / total_demand)
            if weight > eps:
                rows.append((source, target, weight))
    return rows


# Direct member<->pool edges ARE read off the flux vector; only the cross-feeding attribution is
# an allocation. Naming both makes the difference visible on the row.
DIRECT_ALLOCATION_METHOD = "direct_flux"


def _community_abundances(result: SolveResult) -> dict[str, float]:
    """Return finite, non-negative relative abundances or fail before emitting a mixed basis.

    Round 5 considered falling back to a factor of 1.0 for a missing abundance. That turns
    "MICOM did not report the scaling input" into "this taxon is the entire community" and leaves
    a per-taxon number in a column declared to be community-basis. Failing bundle construction is
    the only contract that cannot publish that fabricated quantity.
    """
    missing = [member for member in sorted(result.members) if result.abundances.get(member) is None]
    if missing:
        raise MissingAbundanceError(
            "member abundance missing; cannot convert edges.weight and its FVA interval to "
            f"community basis: {missing}"
        )

    abundances: dict[str, float] = {}
    for member in sorted(result.members):
        abundance = result.abundances.get(member)
        if abundance is None:  # narrowed above; kept local so the type and contract stay coupled
            raise MissingAbundanceError(
                f"member abundance missing; cannot convert edges.weight: {member}"
            )
        abundances[member] = float(abundance)
    invalid = {
        member: abundance
        for member, abundance in abundances.items()
        if not math.isfinite(abundance) or abundance < 0.0
    }
    if invalid:
        raise MissingAbundanceError(
            "member abundance must be finite and non-negative to convert edges.weight and its "
            f"FVA interval to community basis: {invalid}"
        )
    return abundances


def build_tidy(
    result: SolveResult,
    eps: float = NOISE_FLOOR,
    *,
    edge_fva: dict[tuple[str, str], tuple[float, float]] | None = None,
) -> TidyBundle:
    """SolveResult → TidyBundle with community-basis edge magnitudes.

    Member exchange fluxes arrive from MICOM on a per-taxon basis. Direct edge weights and their
    FVA bounds are multiplied by relative abundance here. Cross-feeding allocation is performed
    *after* the same scaling, so direct and allocated rows share one basis.

    Sorting remains deterministic for golden comparison.
    """
    members = sorted(result.members)
    abundances = _community_abundances(result)

    # ── nodes: 멤버 + 환경 pool ──
    n_sv: list[str] = []
    n_id: list[str] = []
    n_type: list[str] = []
    n_label: list[str] = []
    n_growth: list[float | None] = []
    n_ab: list[float | None] = []
    for m in members:
        n_sv.append(TIDY_SCHEMA_VERSION)
        n_id.append(m)
        n_type.append("member")
        n_label.append(m)
        n_growth.append(result.member_growth.get(m))
        n_ab.append(abundances[m])
    # 환경 pool 노드 1개
    n_sv.append(TIDY_SCHEMA_VERSION)
    n_id.append(ENV_POOL_ID)
    n_type.append("environment_pool")
    n_label.append(ENV_POOL_ID)
    n_growth.append(None)
    n_ab.append(None)
    # F5/C11: host-microbe 확장 — member=microbe, pool=null. interface/compartment null.
    n_org = ["microbe" if t == "member" else None for t in n_type]
    n_null: list[None] = [None] * len(n_id)
    nodes = pa.table(
        {"schema_version": n_sv, "node_id": n_id, "node_type": n_type,
         "label": n_label, "growth": n_growth, "abundance": n_ab,
         "organism_type": n_org, "interface": n_null, "compartment": n_null},
        schema=NODES_SCHEMA,
    )

    # ── profile: 환경 net exchange (medium pool) ──
    p_rows = []
    for metab in sorted(result.external_exchange):
        raw = result.external_exchange[metab]
        sf = convert(raw, Scope.ENVIRONMENT, eps=eps)
        if sf.label is None:
            continue  # 무흐름 drop
        p_rows.append((metab, raw, sf.ui_flux, _label_str(sf.label)))
    p_null: list[None] = [None] * len(p_rows)        # F5: host 확장 placeholder(microbe-only)
    profile = pa.table(
        {
            "schema_version": [TIDY_SCHEMA_VERSION] * len(p_rows),
            "metabolite": [r[0] for r in p_rows],
            "net_flux": [r[1] for r in p_rows],
            "ui_flux": [r[2] for r in p_rows],
            "label": [r[3] for r in p_rows],
            "fva_lo": [None] * len(p_rows),
            "fva_hi": [None] * len(p_rows),
            "organism_type": p_null, "interface": p_null, "compartment": p_null,
        },
        schema=PROFILE_SCHEMA,
    )

    # ── edges: 멤버↔pool (secretion/uptake) + cross-feeding (m→m′) ──
    edges: list[tuple[str, str, str, str, float, str, str, bool]] = []
    # 1) 멤버↔pool 방향 edge
    for m in members:
        for metab in sorted(result.member_exchange.get(m, {})):
            raw = result.member_exchange[m][metab]
            sf = convert(raw, Scope.MEMBER_POOL, eps=eps)
            community_weight = sf.ui_flux * abundances[m]
            if sf.label is Label.SECRETION:
                edges.append((
                    m, ENV_POOL_ID, metab, "secretion", community_weight, "secretion",
                    DIRECT_ALLOCATION_METHOD, True,
                ))
            elif sf.label is Label.UPTAKE:
                edges.append((
                    ENV_POOL_ID, m, metab, "uptake", community_weight, "uptake",
                    DIRECT_ALLOCATION_METHOD, True,
                ))
    # 2) cross-feeding: 동일 metabolite 의 secretor → consumer.
    # Shared-pool 해는 pairwise donor attribution을 식별하지 않으므로 대사체별 총 전달 가능량을
    # 공급/수요 비례로 보존 배분한다(CROSS_FEEDING_ALLOCATION_METHOD).
    metabolites = sorted({x for ex in result.member_exchange.values() for x in ex})
    for metab in metabolites:
        # Select signal on the engine's per-taxon noise floor, then allocate the already-scaled
        # community contributions. Passing eps=0 avoids discarding a real rare-taxon contribution
        # merely because abundance scaling made its magnitude smaller than the engine noise floor.
        secretors = {m: result.member_exchange[m][metab] * abundances[m]
                     for m in members if result.member_exchange.get(m, {}).get(metab, 0.0) > eps}
        consumers = {m: result.member_exchange[m][metab] * abundances[m]
                     for m in members if result.member_exchange.get(m, {}).get(metab, 0.0) < -eps}
        for source, target, weight in allocate_cross_feeding(secretors, consumers, eps=0.0):
            # identifiable=False: the shared-pool solution does not determine WHO fed WHOM.
            edges.append((
                source, target, metab, "cross_feeding", weight, "secretion",
                CROSS_FEEDING_ALLOCATION_METHOD, False,
            ))
    edges.sort()
    intervals = edge_fva or {}

    def _bounds(edge: tuple[Any, ...]) -> tuple[float | None, float | None]:
        """Community-basis magnitude interval for a direct edge.

        An allocated weight has no FVA interval of its own — the interval belongs to the exchange
        flux, not to the pairwise attribution, and pretending otherwise would dress an
        unidentifiable number in a determined-looking range. Direct FVA input is a signed
        per-taxon reaction interval. It is first mapped to the row direction's non-negative
        magnitude, then scaled by the member's relative abundance, exactly like ``weight``.
        """
        if edge[3] == "cross_feeding":
            return None, None
        found = intervals.get((str(edge[0]), str(edge[2]))) or intervals.get(
            (str(edge[1]), str(edge[2]))
        )
        if found is None:
            return None, None
        raw_lo, raw_hi = sorted((float(found[0]), float(found[1])))
        member = str(edge[0] if edge[3] == "secretion" else edge[1])
        abundance = abundances[member]
        if edge[3] == "secretion":
            magnitude_lo, magnitude_hi = max(0.0, raw_lo), max(0.0, raw_hi)
        else:
            magnitude_lo, magnitude_hi = max(0.0, -raw_hi), max(0.0, -raw_lo)
        return magnitude_lo * abundance, magnitude_hi * abundance

    edge_bounds = [_bounds(edge) for edge in edges]

    edges_tbl = pa.table(
        {
            "schema_version": [TIDY_SCHEMA_VERSION] * len(edges),
            "source_id": [e[0] for e in edges],
            "target_id": [e[1] for e in edges],
            "metabolite": [e[2] for e in edges],
            "edge_type": [e[3] for e in edges],
            "weight": [e[4] for e in edges],
            "label": [e[5] for e in edges],
            "allocation_method": [e[6] for e in edges],
            "identifiable": [e[7] for e in edges],
            "weight_lo": [bounds[0] for bounds in edge_bounds],
            "weight_hi": [bounds[1] for bounds in edge_bounds],
        },
        schema=EDGES_SCHEMA,
    )

    bundle = TidyBundle(nodes=nodes, edges=edges_tbl, profile=profile)
    bundle.validate()
    return bundle


def edge_profile_consistency(
    bundle: Any, *, atol: float = 1e-4, rtol: float = 1e-5
) -> dict[str, Any]:
    """Check the documented edge↔profile mass identity on a tidy bundle.

    Since tidy 1.3 the signed sum of direct member↔pool edges (secretion +,
    uptake −; allocated cross_feeding excluded) must equal each metabolite's
    ``profile.net_flux``. Round-9 V6 measured a real OSQP community state where
    160/161 union keys violate this identity by up to ~1.5e3 while the run still
    reported ``optimal`` — a mass-inconsistent artifact set must not be published
    as a successful solve. The tolerance is the documented cross-solver rule
    (``atol + rtol * |net_flux|``); metabolites missing from one side count as 0
    on that side, matching the audit's method.
    """
    profile_net: dict[str, float] = {}
    for row in bundle.profile.to_pylist():
        profile_net[str(row["metabolite"])] = float(row["net_flux"])
    edge_sum: dict[str, float] = {}
    for row in bundle.edges.to_pylist():
        edge_type = str(row["edge_type"])
        if edge_type not in ("secretion", "uptake"):
            continue
        weight = row["weight"]
        if weight is None or not math.isfinite(float(weight)):
            continue
        signed = float(weight) if edge_type == "secretion" else -float(weight)
        key = str(row["metabolite"])
        edge_sum[key] = edge_sum.get(key, 0.0) + signed

    failing: list[dict[str, float | str]] = []
    max_residual = 0.0
    keys = sorted(set(profile_net) | set(edge_sum))
    for key in keys:
        net = profile_net.get(key, 0.0)
        summed = edge_sum.get(key, 0.0)
        residual = abs(summed - net)
        max_residual = max(max_residual, residual)
        if residual > atol + rtol * abs(net):
            failing.append({
                "metabolite": key, "edge_sum": summed,
                "net_flux": net, "residual": residual,
            })
    failing.sort(key=lambda item: -float(item["residual"]))
    return {
        "n_keys": len(keys),
        "n_failing": len(failing),
        "max_residual": max_residual,
        "worst": failing[:5],
        "consistent": not failing,
    }
