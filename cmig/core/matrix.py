"""AN-PAIR matrix — 배지별 member 지표 long-format 테이블 (Roadmap Phase 1.2).

Design Ref: §10 AN-PAIR / cmig-an-pair.design. Plan SC: SC-AP4.

TidyBundle.matrix(현재 항상 None)의 실 스키마. long-format(medium×member×metric) — numeric value
+ categorical label(interaction type). pickle 금지(parquet). schema_version 단일 계약.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

MATRIX_SCHEMA_VERSION = "1.0"

MATRIX_SCHEMA = pa.schema([
    ("schema_version", pa.string()),   # 첫 컬럼·단일 계약
    ("medium_id", pa.string()),
    ("member_id", pa.string()),        # member id 또는 "__pair__"(community-level)
    ("metric", pa.string()),           # mono_growth|co_growth|growth_delta|mro|mip|interaction
    ("value", pa.float64()),           # nullable (interaction 행은 null)
    ("label", pa.string()),            # nullable (interaction type 등 categorical)
])


def build_matrix(rows: list[dict[str, Any]]) -> pa.Table:
    """long-format 행 리스트 → MATRIX_SCHEMA 테이블 (schema_version 강제 주입)."""
    return pa.Table.from_pylist(
        [{"schema_version": MATRIX_SCHEMA_VERSION, **r} for r in rows],
        schema=MATRIX_SCHEMA,
    )


def write_matrix(table: pa.Table, path: str | Path) -> Path:
    """matrix.parquet 저장."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, p)
    return p


def read_matrix(path: str | Path) -> pa.Table:
    return pq.read_table(path)
