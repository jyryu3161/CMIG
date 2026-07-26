"""Namespace hard gate — exchange 대사체 정합 + 차단 게이트.

Design Ref: §4.8·§6 / glossary §1.B / schema §7 [GATE-BLOCK].
Plan SC: SC-3 (namespace gate 차단 동작).

규칙:
  unresolved + high-confidence  → solve 차단(block)·해소 요구
  low-confidence                → 경고(warn) 후 진행·**자동병합 금지**·audit
  resolved                      → 통과
gate 통과는 MICOM solve·run_hash 산출의 선행조건(precondition)이다.
namespace mapping decisions 는 run_hash 11구성요소 #10 (schema §4.2).
"""

from __future__ import annotations

import enum
import json
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class Confidence(enum.Enum):
    HIGH = "high"
    LOW = "low"


class DecisionStatus(enum.Enum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    WARNED = "warned"   # low-confidence, 경고 후 진행 (자동병합 아님)


@dataclass(frozen=True)
class NamespaceDecision:
    """exchange 대사체 매핑 결정 레코드 (audit trail 단위). schema §7.1."""

    metabolite: str
    source_id: str
    target_id: str | None       # unresolved 이면 None (OD-37)
    confidence: Confidence
    status: DecisionStatus
    rationale: str = ""
    audit_ts: str | None = None  # UTC ISO-8601 ms (OD-38) — gate 평가 시점엔 None 가능


class GateBlockedError(RuntimeError):
    """unresolved high-confidence mapping 존재 → solve 차단 (§4.8)."""

    def __init__(
        self,
        unresolved_high: list[NamespaceDecision],
        *,
        missing_decisions: bool = False,
    ):
        self.unresolved_high = unresolved_high
        self.missing_decisions = missing_decisions
        if missing_decisions:
            super().__init__(
                "namespace gate blocked: 검토된 namespace decision이 없습니다. "
                "`--namespace-decisions`로 검토 결과를 제공하거나, 입력 모델이 이미 BiGG "
                "namespace임을 확인한 경우에만 `--assume-bigg-namespace`를 명시하세요."
            )
            return
        names = ", ".join(sorted(d.metabolite for d in unresolved_high))
        super().__init__(
            f"namespace gate blocked: unresolved high-confidence exchange mapping "
            f"[{names}] — 해소(resolution) 필요 (§4.8). community solve 차단됨."
        )


@dataclass(frozen=True)
class NamespaceGateResult:
    """gate 평가 산출 (in-memory). schema §7.2.

    blocked=True 이면 어떤 MICOM solve 도 호출되지 않는다 ([GATE-BLOCK]).
    """

    blocked: bool
    coverage_pct: float
    unresolved_high: list[NamespaceDecision] = field(default_factory=list)
    warned_low: list[NamespaceDecision] = field(default_factory=list)
    decisions: list[NamespaceDecision] = field(default_factory=list)
    missing_decisions: bool = False

    def raise_if_blocked(self) -> None:
        if self.blocked:
            raise GateBlockedError(
                self.unresolved_high, missing_decisions=self.missing_decisions
            )


def _validate_decisions(decisions: list[NamespaceDecision]) -> None:
    """모순되거나 충돌하는 audit 결정을 solve 전에 거부한다."""
    mappings: dict[tuple[str, str], str] = {}
    for decision in decisions:
        if not decision.metabolite.strip() or not decision.source_id.strip():
            raise ValueError("namespace decision의 metabolite/source_id는 비어 있을 수 없음")
        if decision.status is DecisionStatus.RESOLVED and not decision.target_id:
            raise ValueError(
                f"resolved namespace decision에는 target_id가 필요함: {decision.metabolite}"
            )
        if decision.status is DecisionStatus.UNRESOLVED and decision.target_id is not None:
            raise ValueError(
                f"unresolved namespace decision의 target_id는 null이어야 함: "
                f"{decision.metabolite}"
            )
        if decision.status is not DecisionStatus.RESOLVED:
            continue
        key = (decision.metabolite, decision.source_id)
        target = str(decision.target_id)
        prior = mappings.setdefault(key, target)
        if prior != target:
            raise ValueError(
                f"충돌하는 namespace target: {decision.metabolite} -> {prior}, {target}"
            )


def evaluate_gate(
    decisions: list[NamespaceDecision], *, require_decisions: bool = True
) -> NamespaceGateResult:
    """namespace 결정 목록 → gate 결과.

    - blocked := ∃ (confidence=HIGH ∧ status=UNRESOLVED)
    - warned_low := low-confidence 이며 진행(자동병합 금지)
    - coverage_pct := resolved / total × 100  (OD-40: 분모=평가된 exchange 매핑 수)
    """
    _validate_decisions(decisions)
    missing_decisions = require_decisions and not decisions
    unresolved_high = [
        d for d in decisions
        if d.confidence is Confidence.HIGH and d.status is DecisionStatus.UNRESOLVED
    ]
    warned_low = [d for d in decisions if d.status is DecisionStatus.WARNED]
    resolved = sum(1 for d in decisions if d.status is DecisionStatus.RESOLVED)
    total = len(decisions)
    coverage = 0.0 if total == 0 else (resolved / total) * 100.0
    return NamespaceGateResult(
        blocked=missing_decisions or len(unresolved_high) > 0,
        coverage_pct=coverage,
        unresolved_high=unresolved_high,
        warned_low=warned_low,
        decisions=list(decisions),
        missing_decisions=missing_decisions,
    )


@dataclass(frozen=True)
class AppliedNamespaceMapping:
    """모델 사본에 실제 적용된 단일 metabolite/exchange ID 변경."""

    model_id: str
    source_metabolite_id: str
    target_metabolite_id: str
    source_exchange_id: str
    target_exchange_id: str


_COMPARTMENT_SUFFIXES = ("_lumen", "_blood", "_e", "_m", "_c", "_p")


def _without_namespace(raw: str) -> str:
    """`bigg:ac` 같은 audit ID에서 namespace prefix만 제거한다."""
    return raw.split(":", 1)[1] if ":" in raw else raw


def _bare_metabolite_id(raw: str) -> tuple[str, str]:
    """정확 매핑용 ID를 (bare ID, compartment suffix)로 분리한다."""
    value = _without_namespace(raw.strip())
    if value.startswith("EX_"):
        value = value[3:]
    for suffix in _COMPARTMENT_SUFFIXES:
        if value.endswith(suffix):
            return value[: -len(suffix)], suffix
    return value, ""


def apply_namespace_decisions_to_model(
    model: Any, decisions: list[NamespaceDecision]
) -> list[AppliedNamespaceMapping]:
    """RESOLVED 결정만 Cobra 모델 사본의 exchange와 metabolite ID에 적용한다.

    WARNED 후보는 의도적으로 적용하지 않는다. source matching은 느슨한 소문자 정규화가
    아니라 compartment만 제거한 정확 ID 비교라서 stereochemistry 표기를 보존한다.
    """
    _validate_decisions(decisions)
    resolved = [d for d in decisions if d.status is DecisionStatus.RESOLVED]
    applied: list[AppliedNamespaceMapping] = []
    occupied_metabolites = {str(m.id) for m in model.metabolites}
    occupied_reactions = {str(r.id) for r in model.reactions}

    for decision in resolved:
        source_candidates = {
            _bare_metabolite_id(decision.metabolite)[0],
            _bare_metabolite_id(decision.source_id)[0],
        }
        target_bare, _ = _bare_metabolite_id(str(decision.target_id))
        for exchange in sorted(model.exchanges, key=lambda reaction: str(reaction.id)):
            extracellular = [
                metabolite
                for metabolite in exchange.metabolites
                if str(getattr(metabolite, "compartment", ""))
                in {"e", "m", "lumen", "blood", "extracellular"}
                or _bare_metabolite_id(str(metabolite.id))[1]
                in {"_e", "_m", "_lumen", "_blood"}
            ]
            if len(extracellular) != 1:
                continue
            metabolite = extracellular[0]
            source_bare, suffix = _bare_metabolite_id(str(metabolite.id))
            if source_bare not in source_candidates:
                continue
            target_metabolite_id = f"{target_bare}{suffix}"
            source_metabolite_id = str(metabolite.id)
            source_exchange_id = str(exchange.id)
            target_exchange_id = f"EX_{target_metabolite_id}"
            if target_metabolite_id != source_metabolite_id:
                if target_metabolite_id in occupied_metabolites:
                    raise ValueError(
                        f"namespace metabolite ID 충돌: {source_metabolite_id} -> "
                        f"{target_metabolite_id}"
                    )
                occupied_metabolites.remove(source_metabolite_id)
                occupied_metabolites.add(target_metabolite_id)
                metabolite.id = target_metabolite_id
            if target_exchange_id != source_exchange_id:
                if target_exchange_id in occupied_reactions:
                    raise ValueError(
                        f"namespace exchange ID 충돌: {source_exchange_id} -> "
                        f"{target_exchange_id}"
                    )
                occupied_reactions.remove(source_exchange_id)
                occupied_reactions.add(target_exchange_id)
                exchange.id = target_exchange_id
            if (
                source_metabolite_id != target_metabolite_id
                or source_exchange_id != target_exchange_id
            ):
                applied.append(
                    AppliedNamespaceMapping(
                        model_id=str(model.id),
                        source_metabolite_id=source_metabolite_id,
                        target_metabolite_id=target_metabolite_id,
                        source_exchange_id=source_exchange_id,
                        target_exchange_id=target_exchange_id,
                    )
                )
    model.repair()
    return applied


def _load_cobra_model(path: Path) -> Any:
    import cobra.io

    name = path.name.lower()
    if name.endswith((".xml", ".sbml", ".xml.gz", ".sbml.gz")):
        return cobra.io.read_sbml_model(str(path))
    if name.endswith(".json"):
        return cobra.io.load_json_model(str(path))
    if name.endswith(".mat"):
        return cobra.io.load_matlab_model(str(path))
    raise ValueError(f"namespace mapping 미지원 모델 형식: {path}")


@contextmanager
def mapped_taxonomy(
    taxonomy: Any, decisions: list[NamespaceDecision]
) -> Iterator[tuple[Any, list[AppliedNamespaceMapping]]]:
    """검토 매핑을 임시 SBML 사본에 적용하고 MICOM용 taxonomy를 산출한다."""
    resolved = [d for d in decisions if d.status is DecisionStatus.RESOLVED]
    if not resolved:
        yield taxonomy, []
        return

    import cobra.io

    mapped = taxonomy.copy(deep=True)
    applied: list[AppliedNamespaceMapping] = []
    with tempfile.TemporaryDirectory(prefix="cmig-namespace-") as tmp:
        tmp_path = Path(tmp)
        for index, record in enumerate(mapped.to_dict("records")):
            source_path = Path(str(record["file"]))
            if not source_path.exists():
                raise ValueError(f"taxonomy model 파일 없음: {source_path}")
            model = _load_cobra_model(source_path)
            applied.extend(apply_namespace_decisions_to_model(model, resolved))
            target_path = tmp_path / f"{index:04d}.xml"
            cobra.io.write_sbml_model(model, str(target_path))
            mapped.at[mapped.index[index], "file"] = str(target_path)
        yield mapped, applied


def namespace_decision_key(decision: NamespaceDecision) -> str:
    """run_hash 용 결정적 namespace decision 키.

    audit timestamp 는 재현 입력이 아니라 감사 메타데이터라 제외한다. 같은 수동 매핑 결정은
    실행 시점과 무관하게 같은 run_hash 구성요소가 되어야 한다.
    """
    payload = {
        "metabolite": decision.metabolite,
        "source_id": decision.source_id,
        "target_id": decision.target_id,
        "confidence": decision.confidence.value,
        "status": decision.status.value,
        "rationale": decision.rationale,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def namespace_decision_keys(decisions: list[NamespaceDecision]) -> list[str]:
    """run_hash 구성요소 #10 용 결정적 decision key 목록."""
    return sorted(namespace_decision_key(d) for d in decisions)


def suggest_namespace_decisions(
    source_ids: list[str],
    *,
    known_targets: set[str] | None = None,
    source_namespace: str = "model",
    target_namespace: str = "bigg",
) -> list[NamespaceDecision]:
    """exchange/metabolite id 목록 → namespace decision 초안 생성.

    Exact id match 는 high-confidence resolved 로 제안한다. 대소문자·구획 suffix 정규화로만
    맞는 후보는 low-confidence warned 로 제안해 자동병합을 피하고 사용자 검토를 요구한다.
    후보가 없으면 high-confidence unresolved 로 둔다.
    """
    targets = known_targets or set()
    normalized_targets = {_normalize_metabolite_id(t): t for t in targets}
    out: list[NamespaceDecision] = []
    for sid in sorted(set(source_ids)):
        clean = sid.strip()
        if not clean:
            continue
        normalized = _normalize_metabolite_id(clean)
        exact = clean in targets
        target = clean if exact else normalized_targets.get(normalized)
        confidence = Confidence.HIGH if exact or target is None else Confidence.LOW
        status = (
            DecisionStatus.RESOLVED if exact else
            DecisionStatus.WARNED if target is not None else
            DecisionStatus.UNRESOLVED
        )
        out.append(
            NamespaceDecision(
                metabolite=clean,
                source_id=f"{source_namespace}:{clean}",
                target_id=None if target is None else f"{target_namespace}:{target}",
                confidence=confidence,
                status=status,
                rationale=(
                    "exact id match" if exact else
                    "normalized id candidate; manual review required"
                    if target is not None else
                    "no exact or normalized target id match"
                ),
            )
        )
    return out


# Compartment/exchange suffixes `_normalize_metabolite_id` strips, and the exchange-id prefix it
# drops. Module-level so a caller that must *record* the normalization policy (the host-map
# workflow manifest) reads it from the code rather than restating it — a restated policy would
# drift silently, and then changing the normalizer would not move the hash it is supposed to
# determine.
NORMALIZE_EXCHANGE_PREFIX = "EX_"
NORMALIZE_COMPARTMENT_SUFFIXES: tuple[str, ...] = ("_e", "_m", "_c", "_p", "_lumen", "_blood")

# BiGG encodes stereochemistry as a trailing ``__<single uppercase letter>`` (``lac__D`` vs
# ``lac__L``). Those are *different molecules with different transporters*, so the descriptor is
# part of the metabolite identity and must never be stripped: collapsing them lets a reviewed
# D-isomer interface mapping match L-isomer availability and open the D exchange, fabricating host
# uptake and biomass. A MICOM member suffix (``ac_e__Bacteroides``) is a taxon *name*, so it is
# always longer than one character — that length is the discriminator. The explicit set below is a
# belt-and-braces guard for the descriptors BiGG actually uses.
STEREO_DESCRIPTORS = frozenset({"D", "L", "R", "S"})


def _strip_compartment_suffix(x: str) -> str:
    for suffix in NORMALIZE_COMPARTMENT_SUFFIXES:
        if x.endswith(suffix):
            return x[: -len(suffix)]
    return x


def _normalize_metabolite_id(raw: str) -> str:
    """Namespace 후보 비교용 느슨한 metabolite id 정규화.

    ``EX_`` prefix, compartment suffix, MICOM member(taxon) suffix 를 제거하되 BiGG
    stereochemistry descriptor(``__D``/``__L``/``__R``/``__S``)는 **보존**한다 — 이는 대사체
    정체성의 일부이며, 제거하면 D/L 이성질체가 같은 id 로 붕괴해 잘못된 host exchange 가 열린다.

    Normalized(non-exact) match 는 여전히 후보 제안일 뿐이므로 downstream 에서는 exact match 만
    자동 admit 된다 (host_map.HOST_MAP_INTERFACE_MAP_ADMITS).
    """
    x = raw.strip()
    if x.startswith(NORMALIZE_EXCHANGE_PREFIX):
        x = x[len(NORMALIZE_EXCHANGE_PREFIX):]
    head, separator, tail = x.rpartition("__")
    if separator and head and tail:
        # ``tail`` may still carry a compartment suffix (``D_e`` in ``lac__D_e``), so strip that
        # before deciding whether the token is a taxon name or a stereo descriptor.
        token = _strip_compartment_suffix(tail)
        is_stereo = len(token) <= 1 or token.upper() in STEREO_DESCRIPTORS
        if token and token[0].isupper() and not is_stereo:
            x = head
    return _strip_compartment_suffix(x).lower()


def decisions_to_jsonable(decisions: list[NamespaceDecision]) -> list[dict[str, Any]]:
    """NamespaceDecision 목록을 사람이 편집 가능한 JSON 객체로 변환."""
    return [
        {
            "metabolite": d.metabolite,
            "source_id": d.source_id,
            "target_id": d.target_id,
            "confidence": d.confidence.value,
            "status": d.status.value,
            "rationale": d.rationale,
            **({} if d.audit_ts is None else {"audit_ts": d.audit_ts}),
        }
        for d in decisions
    ]


def _decision_from_obj(obj: dict[str, Any]) -> NamespaceDecision:
    try:
        return NamespaceDecision(
            metabolite=str(obj["metabolite"]),
            source_id=str(obj["source_id"]),
            target_id=None if obj.get("target_id") is None else str(obj["target_id"]),
            confidence=Confidence(str(obj["confidence"])),
            status=DecisionStatus(str(obj["status"])),
            rationale=str(obj.get("rationale", "")),
            audit_ts=None if obj.get("audit_ts") is None else str(obj["audit_ts"]),
        )
    except KeyError as e:
        raise ValueError(f"namespace decision 필수 필드 누락: {e.args[0]}") from e
    except ValueError as e:
        raise ValueError(f"namespace decision 값 오류: {obj}") from e


def load_namespace_decisions(path: str | Path) -> list[NamespaceDecision]:
    """JSON namespace decision 파일 로드.

    형식은 `[{metabolite, source_id, target_id, confidence, status, rationale?}]`.
    confidence={high,low}, status={resolved,unresolved,warned}.
    """
    p = Path(path)
    raw = json.loads(p.read_text())
    if not isinstance(raw, list):
        raise ValueError("namespace decision JSON 은 list 여야 함")
    out = []
    for obj in raw:
        if not isinstance(obj, dict):
            raise ValueError("namespace decision 항목은 object 여야 함")
        out.append(_decision_from_obj(obj))
    return out
