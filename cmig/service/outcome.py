"""SolveOutcome — 한 solve 의 산출 묶음 값객체 (Option C).

Design Ref: §3 (cmig-engine-service-facade.design). Plan SC: SC-S1·SC-S5.

[HASH-SINGLE] run_hash 는 **manifest.json 에서 read** 한다 — 재계산·재구현 절대 금지.
capability_missing stub 은 result/bundle/run_hash=None 으로 정직하게 비운다(가짜 success 금지).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cmig.core.engine import SolveResult
from cmig.core.manifest import RunHashComponents


@dataclass(frozen=True)
class SolveOutcome:
    """한 solve 의 산출. run_hash 는 manifest 파생(단일 canonical).

    [호출 규율] Optional 필드는 capability_missing stub 수용을 위함 — **소비자는 dereference 전
    `status == "ok"`(또는 `run_hash is not None`) 분기 필수**(타입 미강제, §3.3).
    """

    result: SolveResult | None          # engine 출력 (stub 이면 None)
    bundle: Any | None                  # TidyBundle (stub 이면 None)
    components: RunHashComponents | None  # 11 canonical 구성요소 (stub 이면 None)
    run_hash: str | None                # manifest.json["run_hash"] ([HASH-SINGLE])
    manifest_path: Path | None          # stub 이면 None
    community: Any | None = None        # post-solve FVA/commit 용(소비 후 폐기)
    status: str = "ok"                  # {ok, capability_missing}
    diagnostic: str | None = None       # 구조화 Diagnostic JSON

    @classmethod
    def from_manifest(
        cls,
        result: SolveResult,
        bundle: Any,
        components: RunHashComponents,
        manifest_path: Path,
        *,
        community: Any | None = None,
    ) -> SolveOutcome:
        """성공 solve → manifest 에서 run_hash read (재계산 0)."""
        run_hash = json.loads(Path(manifest_path).read_text())["run_hash"]
        return cls(
            result=result, bundle=bundle, components=components, run_hash=run_hash,
            manifest_path=Path(manifest_path), community=community,
            status="ok", diagnostic=result.diagnostic,
        )

    @classmethod
    def capability_missing(cls, diagnostic: str) -> SolveOutcome:
        """HONEST stub — result/bundle/run_hash 없음, CAPABILITY_MISSING Diagnostic 만."""
        return cls(
            result=None, bundle=None, components=None, run_hash=None,
            manifest_path=None, community=None,
            status="capability_missing", diagnostic=diagnostic,
        )
