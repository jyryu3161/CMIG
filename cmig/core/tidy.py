"""Tidy 데이터 계약 — 단일 출력 계약 (nodes/edges/profile/matrix/timecourse).

Design Ref: §4.6 / schema §2 [CARVE-OUT] / glossary §1.E.
Plan SC: SC-9 (tidy 계약 준수).

전 분석 산출은 이 계약(parquet)으로만 출력되고, 전 소비자는 단일 reader 경유.
모든 테이블은 `schema_version` 컬럼을 가진다(스키마 변경 시 bump + 계약 테스트, Plan §6.2/§6.3).
golden 회귀는 nodes/edges/profile 3종만(§16). matrix 는 baseline 산출, timecourse 는
PART II(§13 dFBA) placeholder — baseline 미산출.
sweep store(sweep.parquet)는 §4.6 5종이 아니라 §5 AggregationStore 규약 지배.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

# 1.2→1.3 is a semantic change, not a column addition: edge ``weight`` and its
# ``weight_lo``/``weight_hi`` interval moved from per-taxon flux to relative-abundance-weighted
# community contribution.  The version stamp is therefore the machine-readable boundary between
# artifacts that must and must not be abundance-scaled by a consumer.
TIDY_SCHEMA_VERSION = "1.3"

LEGACY_EDGE_WEIGHT_BASIS = "per_taxon_unweighted"       # tidy <= 1.2
EDGE_WEIGHT_BASIS = "community_abundance_weighted"      # tidy >= 1.3
EDGE_WEIGHT_UNIT = "mmol gDW_community^-1 h^-1"

# F5/C11: host-microbe 확장 컬럼 (nullable placeholder; 로직은 microbe-only).
#   organism_type {microbe, host}  · interface {lumen, blood}  · compartment
_HOST_EXT_FIELDS = [
    ("organism_type", pa.string()),   # 노드 organism 유형 (default microbe; pool/profile=null)
    ("interface", pa.string()),       # lumen/blood (host, nullable)
    ("compartment", pa.string()),     # 구획 (host, nullable)
]

# ── 컬럼 계약 (schema §2.1–§2.3) ───────────────────────────────────
# v1.0 (legacy 읽기·승격 기준)
NODES_SCHEMA_V10 = pa.schema([
    ("schema_version", pa.string()),
    ("node_id", pa.string()),
    ("node_type", pa.string()),       # {member, environment_pool}
    ("label", pa.string()),
    ("growth", pa.float64()),         # μ; status=ok 에서 유효 (nullable)
    ("abundance", pa.float64()),      # normalize 시 상대 (nullable; pool=null)
])

# v1.1 edges (legacy read/upgrade baseline)
EDGES_SCHEMA_V11 = pa.schema([
    ("schema_version", pa.string()),
    ("source_id", pa.string()),
    ("target_id", pa.string()),
    ("metabolite", pa.string()),
    ("edge_type", pa.string()),       # {cross_feeding, uptake, secretion}
    ("weight", pa.float64()),         # v1.3: unsigned community-basis contribution magnitude
    ("label", pa.string()),           # sign label (uptake|secretion)
])

# A-B15 / B-D6: a cross-feeding weight reads as a measured pairwise transfer, but a steady-state
# shared pool does not identify donor->recipient attribution — allocate_cross_feeding says so in
# its docstring and the string appeared in no artifact. These columns put that on the row itself,
# and carry the FVA interval when --fva ran so a point weight is not mistaken for a determined one.
_EDGE_IDENTIFIABILITY_FIELDS = [
    ("allocation_method", pa.string()),   # e.g. proportional_shared_pool | direct
    ("identifiable", pa.bool_()),         # False for allocated cross-feeding
    ("weight_lo", pa.float64()),          # v1.3: community-basis magnitude FVA lower bound
    ("weight_hi", pa.float64()),          # v1.3: community-basis magnitude FVA upper bound
]

EDGES_SCHEMA = pa.schema(list(EDGES_SCHEMA_V11) + _EDGE_IDENTIFIABILITY_FIELDS)

PROFILE_SCHEMA_V10 = pa.schema([
    ("schema_version", pa.string()),
    ("metabolite", pa.string()),
    ("net_flux", pa.float64()),       # raw net 환경 exchange (부호 有)
    ("ui_flux", pa.float64()),        # 정규화 magnitude (≥0)
    ("label", pa.string()),           # uptake|secretion
    ("fva_lo", pa.float64()),         # optional
    ("fva_hi", pa.float64()),         # optional
])

# v1.1 = v1.0 + host-microbe 확장 컬럼 (nodes·profile). edges 는 schema_version 만 1.1.
NODES_SCHEMA = pa.schema(list(NODES_SCHEMA_V10) + _HOST_EXT_FIELDS)
PROFILE_SCHEMA = pa.schema(list(PROFILE_SCHEMA_V10) + _HOST_EXT_FIELDS)

NODE_TYPES = frozenset({"member", "environment_pool"})
EDGE_TYPES = frozenset({"cross_feeding", "uptake", "secretion"})


class TidyContractError(ValueError):
    """tidy 스키마/계약 위반."""


class MissingAbundanceError(TidyContractError):
    """A community-basis edge cannot be derived because member abundance is absent.

    ``SolveResult.abundances[member] is None`` means the engine summary did not report the
    scaling input.  It is not a biological abundance of one and must never be replaced by 1.0:
    doing so would put an unweighted per-taxon value in a community-basis column.
    """


class LegacyEdgeBasisWarning(UserWarning):
    """A legacy per-taxon edge table could not be scaled without its nodes table."""


def _numeric_cell(value: object, column: str) -> float:
    if not isinstance(value, (int, float)):
        raise TidyContractError(f"legacy edges.{column} must be numeric or null, got {value!r}")
    return float(value)


def _check(
    table: pa.Table, expected: pa.Schema, name: str, *, version: str = TIDY_SCHEMA_VERSION
) -> None:
    if table.schema.names != expected.names:
        raise TidyContractError(
            f"tidy '{name}' 컬럼 불일치: got {table.schema.names}, expected {expected.names}"
        )
    for field in expected:
        got = table.schema.field(field.name).type
        if got != field.type:
            raise TidyContractError(
                f"tidy '{name}.{field.name}' 타입 불일치: got {got}, expected {field.type}"
            )
    if name in ("nodes", "edges", "profile") and "schema_version" in table.column_names:
        versions = set(table.column("schema_version").to_pylist())
        if versions and versions != {version}:
            raise TidyContractError(
                f"tidy '{name}.schema_version' 불일치: {versions} != {{{version}}}"
            )


def _directional_community_bounds(
    row: dict[str, object], abundance: float
) -> tuple[float | None, float | None]:
    """Convert a legacy signed per-taxon FVA interval to a row-direction magnitude interval."""
    lo_value, hi_value = row.get("weight_lo"), row.get("weight_hi")
    if lo_value is None or hi_value is None:
        return None, None
    lo, hi = sorted((
        _numeric_cell(lo_value, "weight_lo"),
        _numeric_cell(hi_value, "weight_hi"),
    ))
    if row.get("edge_type") == "secretion":
        magnitude_lo, magnitude_hi = max(0.0, lo), max(0.0, hi)
    else:
        magnitude_lo, magnitude_hi = max(0.0, -hi), max(0.0, -lo)
    return magnitude_lo * abundance, magnitude_hi * abundance


def _upgrade_legacy_edge_basis(
    table: pa.Table,
    member_abundances: dict[str, float | None] | None,
) -> pa.Table:
    """Convert tidy <=1.2 per-taxon edge quantities to the tidy 1.3 community basis.

    Direct rows are scaled by their member endpoint. Cross-feeding is recomputed from the scaled
    direct supply/demand marginals; multiplying an old allocated pairwise value by either the
    donor or recipient abundance would not preserve both marginals. A bare edge table has no
    abundance context, so its quantities become null with a warning instead of being falsely
    restamped as community-basis.
    """
    rows: list[dict[str, object]] = list(table.to_pylist())
    if not rows:
        return table
    if member_abundances is None:
        warnings.warn(
            "legacy edges use per-taxon weights; nodes.abundance is required for the tidy 1.3 "
            "community-basis migration, so weight/weight_lo/weight_hi were set to null",
            LegacyEdgeBasisWarning,
            stacklevel=2,
        )
        for row in rows:
            row["weight"] = None
            row["weight_lo"] = None
            row["weight_hi"] = None
        return pa.Table.from_pylist(rows, schema=EDGES_SCHEMA)

    invalid_abundances: dict[str, float] = {}
    for member, value in member_abundances.items():
        if value is None:
            continue
        abundance = float(value)
        if not math.isfinite(abundance) or abundance < 0.0:
            invalid_abundances[member] = abundance
    if invalid_abundances:
        raise MissingAbundanceError(
            "member abundance must be finite and non-negative to migrate legacy edges to "
            f"community basis: {invalid_abundances}"
        )

    missing: set[str] = set()
    supply: dict[str, dict[str, float]] = {}
    demand: dict[str, dict[str, float]] = {}
    for row in rows:
        edge_type = str(row.get("edge_type"))
        if edge_type == "cross_feeding":
            continue
        member = str(row.get("source_id") if edge_type == "secretion" else row.get("target_id"))
        abundance_value = member_abundances.get(member)
        if abundance_value is None:
            missing.add(member)
            continue
        abundance = float(abundance_value)
        weight_value = row.get("weight")
        weight = (
            None if weight_value is None
            else _numeric_cell(weight_value, "weight") * abundance
        )
        row["weight"] = weight
        row["weight_lo"], row["weight_hi"] = _directional_community_bounds(row, abundance)
        if weight is None:
            continue
        metabolite = str(row.get("metabolite"))
        if edge_type == "secretion":
            supply.setdefault(metabolite, {})[member] = weight
        else:
            demand.setdefault(metabolite, {})[member] = weight
    if missing:
        raise MissingAbundanceError(
            "member abundance missing; cannot migrate legacy edges from per-taxon to community "
            f"basis: {sorted(missing)}"
        )

    for row in rows:
        if row.get("edge_type") != "cross_feeding":
            continue
        metabolite = str(row.get("metabolite"))
        source, target = str(row.get("source_id")), str(row.get("target_id"))
        supplies, demands = supply.get(metabolite, {}), demand.get(metabolite, {})
        total_supply, total_demand = sum(supplies.values()), sum(demands.values())
        if source not in supplies or target not in demands or min(total_supply, total_demand) <= 0:
            row["weight"] = None
        else:
            row["weight"] = (
                min(total_supply, total_demand)
                * supplies[source] / total_supply
                * demands[target] / total_demand
            )
        row["weight_lo"] = None
        row["weight_hi"] = None
    return pa.Table.from_pylist(rows, schema=EDGES_SCHEMA)


def read_legacy_or_upgrade(
    table: pa.Table,
    name: str,
    *,
    member_abundances: dict[str, float | None] | None = None,
) -> pa.Table:
    """F5: parquet 테이블을 현행 스키마 버전으로 승격(단일 read 경로).

    legacy 판정은 **컬럼 존재** 기준(빈 테이블·row 0 도 견고). nodes/profile 에 host 확장 컬럼이
    없으면 주입한다 — `organism_type` 은 'default microbe' 계약(node_type=member → "microbe",
    pool/profile → None). edges 는 v1.2 identifiability 컬럼을 null 로 주입한다(과거 산출물은
    attribution 방법을 기록하지 않았으므로 "모른다"가 정직한 값이다). tidy <=1.2 edge values
    are per-taxon and are semantically migrated only with member abundances; without that context
    they become null with ``LegacyEdgeBasisWarning``. schema_version 은 현행으로 승격한다.
    """
    n = table.num_rows
    original_versions = (
        set(table.column("schema_version").to_pylist())
        if "schema_version" in table.column_names else set()
    )
    if name == "edges":
        for fname, ftype in _EDGE_IDENTIFIABILITY_FIELDS:
            if fname not in table.column_names:
                table = table.append_column(fname, pa.array([None] * n, type=ftype))
    if name in ("nodes", "profile"):
        for fname, ftype in _HOST_EXT_FIELDS:
            if fname in table.column_names:
                continue
            if fname == "organism_type" and name == "nodes" and "node_type" in table.column_names:
                # default microbe: member → 'microbe', environment_pool → None (§ F5 계약)
                vals = [
                    "microbe" if t == "member" else None
                    for t in table.column("node_type").to_pylist()
                ]
                table = table.append_column(fname, pa.array(vals, type=ftype))
            else:
                table = table.append_column(fname, pa.array([None] * n, type=ftype))
    if name == "edges" and original_versions and original_versions != {TIDY_SCHEMA_VERSION}:
        table = _upgrade_legacy_edge_basis(table, member_abundances)
    # schema_version → current (legacy 값·빈 컬럼 포함 모두 승격)
    if "schema_version" in table.column_names:
        cur = set(table.column("schema_version").to_pylist())
        if cur != {TIDY_SCHEMA_VERSION}:
            idx = table.column_names.index("schema_version")
            table = table.set_column(
                idx, "schema_version", pa.array([TIDY_SCHEMA_VERSION] * n, pa.string())
            )
    return table


@dataclass
class TidyBundle:
    """분석 산출 묶음. 단일 reader/writer 진입점.

    matrix 는 optional(baseline 산출), timecourse 는 PART II placeholder(미산출).
    """

    nodes: pa.Table
    edges: pa.Table
    profile: pa.Table
    matrix: pa.Table | None = None

    def validate(self) -> None:
        """계약 검증 (SC-9). 위반 시 TidyContractError."""
        _check(self.nodes, NODES_SCHEMA, "nodes")
        _check(self.edges, EDGES_SCHEMA, "edges")
        _check(self.profile, PROFILE_SCHEMA, "profile")
        bad = set(self.nodes.column("node_type").to_pylist()) - NODE_TYPES
        if bad:
            raise TidyContractError(f"nodes.node_type 미허용 값: {bad}")
        bad_e = set(self.edges.column("edge_type").to_pylist()) - EDGE_TYPES
        if bad_e:
            raise TidyContractError(f"edges.edge_type 미허용 값: {bad_e}")

    def write(self, out_dir: str | Path) -> None:
        """parquet 저장 (pickle 금지, schema §8.6)."""
        self.validate()
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        pq.write_table(self.nodes, d / "nodes.parquet")
        pq.write_table(self.edges, d / "edges.parquet")
        pq.write_table(self.profile, d / "profile.parquet")
        if self.matrix is not None:
            pq.write_table(self.matrix, d / "matrix.parquet")

    @classmethod
    def read(cls, in_dir: str | Path) -> TidyBundle:
        """Read parquet, semantically upgrading legacy per-taxon edges from node abundances."""
        d = Path(in_dir)
        matrix_path = d / "matrix.parquet"
        raw_nodes = pq.read_table(d / "nodes.parquet")
        member_abundances = {
            str(row["node_id"]): row.get("abundance")
            for row in raw_nodes.to_pylist()
            if row.get("node_type") == "member"
        }
        bundle = cls(
            nodes=read_legacy_or_upgrade(raw_nodes, "nodes"),
            edges=read_legacy_or_upgrade(
                pq.read_table(d / "edges.parquet"),
                "edges",
                member_abundances=member_abundances,
            ),
            profile=read_legacy_or_upgrade(pq.read_table(d / "profile.parquet"), "profile"),
            matrix=pq.read_table(matrix_path) if matrix_path.exists() else None,
        )
        bundle.validate()
        return bundle


def empty_bundle() -> TidyBundle:
    """빈(스키마만) 번들 — 테스트·초기화용."""
    return TidyBundle(
        nodes=NODES_SCHEMA.empty_table(),
        edges=EDGES_SCHEMA.empty_table(),
        profile=PROFILE_SCHEMA.empty_table(),
    )
