"""Model Import — user-provided SBML/JSON/MAT GEM → ModelSummary.

Design Ref: §5 MemberModel / §11 Model Manager / cmig-model-import.design. Plan SC: SC-MI1~MI5.

cobra.io 위임(자체 파서 미구현). 확장자로 포맷 자동 감지(.xml/.sbml/.xml.gz·.json·.mat).
exchange/biomass 탐지 + reaction/metabolite/gene 카운트 → Model Manager 패널·facade 소비.
미지원 확장자/파싱 실패 → 명시적 에러(silent 위장 금지).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ModelImportError(RuntimeError):
    """모델 import 실패(미지원 포맷·파싱 오류·cobra 부재)."""


@dataclass(frozen=True)
class ModelSummary:
    """import 된 GEM 요약 (Model Manager 표시·facade 소비)."""

    model_id: str
    source_format: str               # sbml | json | mat
    source_path: str
    n_reactions: int
    n_metabolites: int
    n_genes: int
    exchanges: list[str]
    biomass_reactions: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id, "source_format": self.source_format,
            "source_path": self.source_path, "n_reactions": self.n_reactions,
            "n_metabolites": self.n_metabolites, "n_genes": self.n_genes,
            "n_exchanges": len(self.exchanges), "n_biomass": len(self.biomass_reactions),
        }


@dataclass(frozen=True)
class ModelImportReview:
    """사용자가 제공한 GEM 파일의 solve 전 review/audit payload."""

    model: dict[str, Any]
    inferred_origin: str
    namespace: dict[str, Any]
    warnings: list[str]
    next_actions: list[str]


def _detect_format(path: Path) -> str:
    name = path.name.lower()
    if name.endswith((".xml", ".sbml", ".xml.gz", ".sbml.gz")):
        return "sbml"
    if name.endswith(".json"):
        return "json"
    if name.endswith(".mat"):
        return "mat"
    raise ModelImportError(
        f"미지원 모델 확장자: {path.name} (지원: .xml/.sbml/.xml.gz·.json·.mat)")


def _load_cobra_model(path: Path, fmt: str) -> Any:
    try:
        import cobra.io
    except ImportError as e:
        raise ModelImportError("cobra 미설치 (`uv sync --extra engine`).") from e
    try:
        if fmt == "sbml":
            return cobra.io.read_sbml_model(str(path))
        if fmt == "json":
            return cobra.io.load_json_model(str(path))
        return cobra.io.load_matlab_model(str(path))
    except Exception as e:                       # 파싱 실패 → 명시적 에러
        raise ModelImportError(f"{fmt} 파싱 실패 ({path.name}): {e}") from e


def _biomass_reactions(model: Any) -> list[str]:
    """objective(목적계수≠0) reaction = biomass 후보."""
    from cobra.util.solver import linear_reaction_coefficients
    try:
        coeffs = linear_reaction_coefficients(model)
        return sorted(str(r.id) for r in coeffs)
    except Exception:                            # objective 미설정 등 → 빈 목록(강제 추정 금지)
        return []


def import_model(path: str | Path) -> ModelSummary:
    """GEM 파일 → ModelSummary. 포맷 자동 감지 + cobra.io 위임."""
    p = Path(path)
    if not p.exists():
        raise ModelImportError(f"모델 파일 없음: {p}")
    fmt = _detect_format(p)
    model = _load_cobra_model(p, fmt)
    exchanges = sorted(str(r.id) for r in model.exchanges)
    return ModelSummary(
        model_id=str(model.id) or p.stem,
        source_format=fmt,
        source_path=str(p),
        n_reactions=len(model.reactions),
        n_metabolites=len(model.metabolites),
        n_genes=len(model.genes),
        exchanges=exchanges,
        biomass_reactions=_biomass_reactions(model),
    )


def exchange_metabolite_ids(summary: ModelSummary) -> list[str]:
    """ModelSummary exchange ids에서 namespace 후보 metabolite id 추출.

    `EX_ac_e` → `ac`, `EX_glc__D_m` → `glc__D`처럼 흔한 exchange prefix/suffix를 제거한다.
    """
    out: list[str] = []
    suffixes = ("_e", "_m", "_lumen", "_blood")
    for ex in summary.exchanges:
        name = ex[3:] if ex.startswith("EX_") else ex
        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        out.append(name)
    return sorted(set(out))


def infer_model_origin(summary: ModelSummary) -> str:
    """파일명/model_id 힌트로 Human-GEM/Recon 계열 여부만 보수적으로 추정."""
    blob = f"{summary.model_id} {Path(summary.source_path).name}".lower()
    if "human" in blob or "recon" in blob:
        return "human_gem"
    return "user_provided_gem"


def build_import_review(
    summary: ModelSummary,
    *,
    known_targets: set[str] | None = None,
    source_namespace: str = "model",
    target_namespace: str = "bigg",
) -> ModelImportReview:
    """ModelSummary → namespace 후보·coverage·다음 조치가 포함된 review payload."""
    from cmig.core.namespace import (
        DecisionStatus,
        decisions_to_jsonable,
        evaluate_gate,
        suggest_namespace_decisions,
    )

    decisions = suggest_namespace_decisions(
        exchange_metabolite_ids(summary),
        known_targets=known_targets,
        source_namespace=source_namespace,
        target_namespace=target_namespace,
    )
    gate = evaluate_gate(decisions)
    unresolved = [d.metabolite for d in decisions if d.status is DecisionStatus.UNRESOLVED]
    warned = [d.metabolite for d in decisions if d.status is DecisionStatus.WARNED]
    warnings: list[str] = []
    if unresolved:
        warnings.append(
            f"{len(unresolved)} unresolved high-confidence namespace mappings block solve"
        )
    if warned:
        warnings.append(f"{len(warned)} low-confidence normalized candidates require review")
    if not summary.biomass_reactions:
        warnings.append("biomass/objective reaction not detected")
    origin = infer_model_origin(summary)
    next_actions = [
        "review namespace_decisions.json and resolve high-confidence unresolved mappings",
        "confirm biomass/objective reaction before community assembly",
        "save reviewed decisions and pass them to cmig solve --namespace-decisions",
    ]
    return ModelImportReview(
        model=summary.as_dict(),
        inferred_origin=origin,
        namespace={
            "coverage_pct": gate.coverage_pct,
            "blocked": gate.blocked,
            "n_decisions": len(decisions),
            "n_unresolved_high": len(gate.unresolved_high),
            "n_warned_low": len(gate.warned_low),
            "decisions": decisions_to_jsonable(decisions),
        },
        warnings=warnings,
        next_actions=next_actions,
    )
