"""C6 — Medium 입력/preset. Design Ref(foundations): §4. Plan SC: SC-F3·F4.

사용자가 배지(diet)를 지정해 community solve 입력으로 쓸 수 있는 기반.
- MediumSpec: {exchange_id: uptake_limit} where uptake_limit >= 0 (흡수 허용 magnitude, 부호 없음).
- apply_medium: **MICOM public API `community.medium`** (양수 dict) 에 설정 — 자체 bound 조작 금지.
- medium_checksum: 결정적 해시 → run_hash medium_checksum 구성요소(§4.2)에 반영(재현성).
csv(`exchange_id,uptake_limit`) / json 입력 (pyyaml 비의존).
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

_DECIMALS = 6


@dataclass(frozen=True)
class MediumSpec:
    """배지 사양 — exchange 별 흡수 허용량(uptake_limit >= 0)."""

    uptake: dict[str, float]

    def validate(self) -> None:
        for ex, v in self.uptake.items():
            if not isinstance(ex, str) or not ex:
                raise ValueError(f"빈 exchange_id (medium): {ex!r}")
            if not math.isfinite(v) or v < 0:
                raise ValueError(f"uptake_limit 은 유한·≥0 이어야 함 ({ex}={v}) [§4]")


def load_medium(path: str | Path) -> MediumSpec:
    """csv(exchange_id,uptake_limit) 또는 json({exchange_id: uptake_limit}) → MediumSpec."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"medium 파일 없음: {p}")
    uptake: dict[str, float] = {}
    if p.suffix == ".json":
        # AF-2: 중복 키 fail-fast (object_pairs_hook — CSV 경로와 대칭).
        def _no_dup(pairs: list[tuple[str, object]]) -> dict[str, object]:
            d: dict[str, object] = {}
            for k, v in pairs:
                if k in d:
                    raise ValueError(f"medium json 중복 exchange_id: {k}")
                d[k] = v
            return d

        raw = json.loads(p.read_text(), object_pairs_hook=_no_dup)
        if not isinstance(raw, dict):
            raise ValueError("medium json 은 {exchange_id: uptake_limit} 객체여야 함")
        for k, v in raw.items():
            if isinstance(v, bool):       # AF-3: bool→float silent 강제 차단(float(True)=1.0)
                raise ValueError(f"uptake_limit 은 숫자여야 함(bool 불가): {k}={v}")
            uptake[str(k)] = float(v)
    elif p.suffix == ".csv":
        with open(p, newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None or "exchange_id" not in reader.fieldnames \
                    or "uptake_limit" not in reader.fieldnames:
                raise ValueError("medium csv 헤더는 exchange_id,uptake_limit 필요")
            for row in reader:
                ex = (row["exchange_id"] or "").strip()
                if not ex:
                    continue
                if ex in uptake:
                    raise ValueError(f"medium csv 중복 exchange_id: {ex}")
                uptake[ex] = float(row["uptake_limit"])
    else:
        raise ValueError(f"미지원 medium 확장자: {p.suffix} (.csv/.json)")
    spec = MediumSpec(uptake=uptake)
    spec.validate()
    return spec


def apply_medium(community: object, spec: MediumSpec) -> dict[str, float]:
    """community.medium(MICOM public API)에 spec 적용. 원래 medium 반환(undo).

    spec 의 exchange 중 community 가 아는 medium 키만 설정한다. 미지 exchange 는 기본적으로
    fail-fast 이며, 호출자가 `strict=False` 를 선택한 경우에만 무시한다.
    uptake_limit 은 그대로 MICOM medium 양수값으로 사용(부호 변환 불요).
    """
    return apply_medium_checked(community, spec, strict=True)[0]


def unknown_medium_exchanges(community: object, spec: MediumSpec) -> list[str]:
    """medium spec 중 community.medium 에 없는 exchange 목록."""
    spec.validate()
    known = set(dict(community.medium))  # type: ignore[attr-defined]
    return sorted(ex for ex in spec.uptake if ex not in known)


def apply_medium_checked(
    community: object, spec: MediumSpec, *, strict: bool = True
) -> tuple[dict[str, float], list[str]]:
    """community.medium 에 spec 적용 + 미적용 exchange 목록 반환.

    strict=True 이면 미지 exchange 를 ValueError 로 차단한다. strict=False 는 CLI의
    `--allow-unknown-medium` 같은 명시 옵션에서만 사용하며, 반환된 unknown 목록을 diagnostic에
    기록해야 한다.
    """
    spec.validate()
    current = dict(community.medium)  # type: ignore[attr-defined]
    original = dict(current)
    known = set(current)
    unknown = sorted(ex for ex in spec.uptake if ex not in known)
    if strict and unknown:
        raise ValueError(f"medium exchange 가 community 에 없음: {unknown}")
    applied = {ex: v for ex, v in spec.uptake.items() if ex in known}
    new_medium = dict(current)
    new_medium.update(applied)
    community.medium = new_medium  # type: ignore[attr-defined]
    return original, unknown


def medium_checksum(spec: MediumSpec | None) -> str:
    """결정적 medium 체크섬 (run_hash 구성요소). None → default sentinel(하위호환)."""
    if spec is None:
        return "micom_default_medium"
    payload = json.dumps(
        {k: round(float(v), _DECIMALS) for k, v in sorted(spec.uptake.items())},
        sort_keys=True, ensure_ascii=True, allow_nan=False,
    )
    return "medium:" + hashlib.sha256(payload.encode()).hexdigest()
