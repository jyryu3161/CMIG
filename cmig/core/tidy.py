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

from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

TIDY_SCHEMA_VERSION = "1.1"        # F5: 1.0→1.1 (host-microbe 확장 컬럼). writer 는 항상 v1.1.

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

EDGES_SCHEMA = pa.schema([
    ("schema_version", pa.string()),
    ("source_id", pa.string()),
    ("target_id", pa.string()),
    ("metabolite", pa.string()),
    ("edge_type", pa.string()),       # {cross_feeding, uptake, secretion}
    ("weight", pa.float64()),         # cross_feeding=min(분비,흡수)
    ("label", pa.string()),           # sign label (uptake|secretion)
])

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


def read_legacy_or_upgrade(table: pa.Table, name: str) -> pa.Table:
    """F5: parquet 테이블을 현행 v1.1 로 승격(단일 read 경로).

    legacy 판정은 **컬럼 존재** 기준(빈 테이블·row 0 도 견고). nodes/profile 에 host 확장 컬럼이
    없으면 주입한다 — `organism_type` 은 'default microbe' 계약(node_type=member → "microbe",
    pool/profile → None). schema_version 은 v1.1 로 승격(legacy 값·빈 컬럼 모두). edges 는
    schema_version bump 만.
    """
    n = table.num_rows
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
    # schema_version → 1.1 (legacy 값·빈 컬럼 포함 모두 승격)
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
        """parquet 읽기 (F5: v1.0 legacy 자동 승격 — read_legacy_or_upgrade 단일 경로)."""
        d = Path(in_dir)
        matrix_path = d / "matrix.parquet"
        bundle = cls(
            nodes=read_legacy_or_upgrade(pq.read_table(d / "nodes.parquet"), "nodes"),
            edges=read_legacy_or_upgrade(pq.read_table(d / "edges.parquet"), "edges"),
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
