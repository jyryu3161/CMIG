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

import pyarrow as pa

from cmig.core.engine import SolveResult
from cmig.core.sign import NOISE_FLOOR, Label, Scope, convert
from cmig.core.tidy import (
    EDGES_SCHEMA,
    NODES_SCHEMA,
    PROFILE_SCHEMA,
    TIDY_SCHEMA_VERSION,
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

    ``secretors`` values are positive raw secretion fluxes and ``consumers`` values are negative
    raw uptake fluxes. Because a steady-state shared pool does not identify pairwise transfers,
    CMIG uses a transparent proportional allocation rather than emitting every pairwise minimum
    (which double-counts mass whenever more than one donor or consumer exists).

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


def build_tidy(result: SolveResult, eps: float = NOISE_FLOOR) -> TidyBundle:
    """SolveResult → TidyBundle. 정렬 결정적(determinism) for golden 비교."""
    members = sorted(result.members)

    # ── nodes: 멤버 + 환경 pool ──
    n_sv, n_id, n_type, n_label, n_growth, n_ab = [], [], [], [], [], []
    for m in members:
        n_sv.append(TIDY_SCHEMA_VERSION)
        n_id.append(m)
        n_type.append("member")
        n_label.append(m)
        n_growth.append(result.member_growth.get(m))
        n_ab.append(result.abundances.get(m))
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
    edges: list[tuple[str, str, str, str, float, str]] = []
    # 1) 멤버↔pool 방향 edge
    for m in members:
        for metab in sorted(result.member_exchange.get(m, {})):
            raw = result.member_exchange[m][metab]
            sf = convert(raw, Scope.MEMBER_POOL, eps=eps)
            if sf.label is Label.SECRETION:
                edges.append((m, ENV_POOL_ID, metab, "secretion", sf.ui_flux, "secretion"))
            elif sf.label is Label.UPTAKE:
                edges.append((ENV_POOL_ID, m, metab, "uptake", sf.ui_flux, "uptake"))
    # 2) cross-feeding: 동일 metabolite 의 secretor → consumer.
    # Shared-pool 해는 pairwise donor attribution을 식별하지 않으므로 대사체별 총 전달 가능량을
    # 공급/수요 비례로 보존 배분한다(CROSS_FEEDING_ALLOCATION_METHOD).
    metabolites = sorted({x for ex in result.member_exchange.values() for x in ex})
    for metab in metabolites:
        secretors = {m: result.member_exchange[m][metab]
                     for m in members if result.member_exchange.get(m, {}).get(metab, 0.0) > eps}
        consumers = {m: result.member_exchange[m][metab]
                     for m in members if result.member_exchange.get(m, {}).get(metab, 0.0) < -eps}
        for source, target, weight in allocate_cross_feeding(secretors, consumers, eps=eps):
            edges.append((source, target, metab, "cross_feeding", weight, "secretion"))
    edges.sort()
    edges_tbl = pa.table(
        {
            "schema_version": [TIDY_SCHEMA_VERSION] * len(edges),
            "source_id": [e[0] for e in edges],
            "target_id": [e[1] for e in edges],
            "metabolite": [e[2] for e in edges],
            "edge_type": [e[3] for e in edges],
            "weight": [e[4] for e in edges],
            "label": [e[5] for e in edges],
        },
        schema=EDGES_SCHEMA,
    )

    bundle = TidyBundle(nodes=nodes, edges=edges_tbl, profile=profile)
    bundle.validate()
    return bundle
