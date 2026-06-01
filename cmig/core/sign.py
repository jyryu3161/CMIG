"""Sign normalization — 부호 정규화 단일 진입점 (single entry point).

Design Ref: §4.3·§4.7 / glossary §1.A / schema §8.1 [SIGN-1·SIGN-2].
Plan SC: SC-2 (sign-test CI).

부호 규약 (강제):
  `+` (raw_flux > 0) = 환경/pool 으로 **분비(secretion)**
  `−` (raw_flux < 0) = 환경/pool 에서 **흡수(uptake)**
`ui_flux` 는 부호 정규화된 **크기(magnitude)** 이므로 항상 ≥ 0.

모든 raw_flux → (ui_flux, label) 변환은 이 모듈만 경유한다(우회 금지).
OD-43 (Resolved): 멤버↔pool '분비' 도 환경과 동일하게 `secretion` enum 으로 통일.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

# Noise floor (TC-17·baseline Minor): |raw| ≤ NOISE_FLOOR 는 수치 잡음 → 무흐름(label=None).
# sign 분류의 단일 기준값 — metrics 등 모든 소비자가 이 상수를 공유(독립 하드코딩 금지·drift 제거).
NOISE_FLOOR = 1e-6


class Scope(enum.Enum):
    """부호 해석 맥락. 규칙은 동일(부호 기반); scope 는 산출 메타데이터다 (§4.3)."""

    ENVIRONMENT = "environment"      # 환경 exchange (net = 환경 exchange)
    MEMBER_POOL = "member_pool"      # 멤버 ↔ 공유 pool (멤버 기여)


class Label(enum.Enum):
    """flux 방향 라벨 (OD-43: 환경·멤버↔pool 공통 enum)."""

    UPTAKE = "uptake"        # 흡수 (raw < 0)
    SECRETION = "secretion"  # 분비 (raw > 0)


@dataclass(frozen=True)
class SignedFlux:
    """sign 정규화 결과. ui_flux 는 항상 ≥ 0 (magnitude)."""

    ui_flux: float
    label: Label | None   # |raw| ≤ eps (무흐름)이면 None — 소비자는 drop
    scope: Scope
    raw_flux: float


def convert(raw_flux: float, scope: Scope, eps: float = NOISE_FLOOR) -> SignedFlux:
    """raw_flux → (ui_flux, label). 부호 규약(§4.3)의 유일한 구현.

    raw > eps  → secretion (분비),  ui_flux = raw
    raw < -eps → uptake    (흡수),  ui_flux = -raw
    |raw| ≤ eps → label=None, ui_flux=0  (무흐름)

    eps 기본 = NOISE_FLOOR(1e-6) — 0 근방 수치 잡음을 secretion/uptake 로 오분류하지 않음
    (baseline Minor·과학적 정정). golden sign_expected 는 이 정정으로 재캡처(의도된 diff).
    """
    if raw_flux > eps:
        return SignedFlux(ui_flux=raw_flux, label=Label.SECRETION, scope=scope, raw_flux=raw_flux)
    if raw_flux < -eps:
        return SignedFlux(ui_flux=-raw_flux, label=Label.UPTAKE, scope=scope, raw_flux=raw_flux)
    return SignedFlux(ui_flux=0.0, label=None, scope=scope, raw_flux=raw_flux)


def classify(raw_flux: float, eps: float = NOISE_FLOOR) -> Label | None:
    """raw_flux → Label|None (분류 단일 진입점). metrics 등이 inline 재구현 대신 경유 (TC-16)."""
    return convert(raw_flux, Scope.ENVIRONMENT, eps).label


def cross_feeding_weight(
    secretor_raw: float, consumer_raw: float, eps: float = NOISE_FLOOR
) -> float | None:
    """cross-feeding m→m′ edge weight = min(|분비량|, |흡수량|).

    Design Ref: §4.3 — m 분비(raw>0) ∧ m′ 흡수(raw<0) 일 때만 유효.
    판정은 raw_flux 부호 기준(ui_flux 는 항상 ≥0 이므로 부호 판정 불가).
    조건 미충족이면 None (cross-feeding edge 없음).
    """
    if not (secretor_raw > eps and consumer_raw < -eps):
        return None
    return min(secretor_raw, -consumer_raw)
