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
            "n_exchanges": len(self.exchanges),
            # A-B9: this counts objective TERMS. Kept under the old key for compatibility, but
            # the honest name is emitted alongside it and a >1 count carries a warning.
            "n_biomass": len(self.biomass_reactions),
            "n_objective_terms": len(self.biomass_reactions),
            "objective_reactions": list(self.biomass_reactions),
            # R6-H: the *reactions* are passed, not only their count. Count-only skips every
            # single-term check, so a model whose sole objective term is a transport reaction
            # (RECON1 ships `S6T14g`) or a maintenance reaction (Recon3D ships
            # `BIOMASS_maintenance`) was reviewed here with no objective warning at all.
            "objective_warning": objective_structure_warning(
                len(self.biomass_reactions), self.biomass_reactions
            ),
        }


@dataclass(frozen=True)
class ModelImportReview:
    """사용자가 제공한 GEM 파일의 solve 전 review/audit payload."""

    model: dict[str, Any]
    inferred_origin: str
    namespace: dict[str, Any]
    warnings: list[str]
    next_actions: list[str]


def detect_model_format(path: Path) -> str:
    name = path.name.lower()
    if name.endswith((".xml", ".sbml", ".xml.gz", ".sbml.gz")):
        return "sbml"
    if name.endswith(".json"):
        return "json"
    if name.endswith(".mat"):
        return "mat"
    raise ModelImportError(
        f"미지원 모델 확장자: {path.name} (지원: .xml/.sbml/.xml.gz·.json·.mat)")


def load_cobra_model(path: str | Path) -> Any:
    """Load a supported Cobra model with extension-based format detection."""
    source = Path(path)
    fmt = detect_model_format(source)
    try:
        import cobra.io
    except ImportError as e:
        raise ModelImportError("cobra 미설치 (`uv sync --extra engine`).") from e
    try:
        if fmt == "sbml":
            return cobra.io.read_sbml_model(str(source))
        if fmt == "json":
            return cobra.io.load_json_model(str(source))
        return cobra.io.load_matlab_model(str(source))
    except Exception as e:                       # 파싱 실패 → 명시적 에러
        raise ModelImportError(f"{fmt} 파싱 실패 ({source.name}): {e}") from e


def _biomass_reactions(model: Any) -> list[str]:
    """Reactions carrying a non-zero objective coefficient.

    These are *objective terms*, not necessarily biomass reactions — see
    :func:`objective_structure_warning`. A single-term objective is the usual biomass case; a
    multi-term objective means the reported "growth" is an arbitrary objective value.

    R5-P3 (codex F3): this used to swallow every exception and return ``[]``. COBRA already
    returns an empty mapping when a model has no objective — measured, it does not raise — so the
    catch never served its stated purpose and instead turned a genuine introspection failure into
    the scientific claim "no objective reaction detected; this model cannot report growth". A
    failure to *look* is not a finding about the model, so it propagates.
    """
    from cobra.util.solver import linear_reaction_coefficients

    coeffs = linear_reaction_coefficients(model)
    return sorted(str(r.id) for r in coeffs)


# A biomass reaction is identified by name because SBML carries no machine-readable "this is the
# growth reaction" flag. Every bundled GEM that has one uses a `BIOMASS_*` id, and `growth` covers
# the other common convention. This is a *hint*, so failing it produces a warning, never a refusal.
_BIOMASS_NAME_HINTS: tuple[str, ...] = ("biomass", "growth")

# Round 6 (track H): a *maintenance* objective is biomass-named but is NOT growth, and it is what
# Recon3D actually ships. `BIOMASS_maintenance` ("Biomass maintenance reaction without replication
# precursors") optimizes to 755.003 on Recon3D — a maintenance turnover rate, not a growth rate —
# and the round-5 checks below passed it in silence because "biomass" is in its name. Checked
# BEFORE the biomass hints, and before the `growth` hint in particular, since the conventional
# spelling of the concept ("non-growth associated maintenance") contains that word.
_MAINTENANCE_NAME_HINTS: tuple[str, ...] = (
    "maintenance", "atpm", "non-growth", "non growth", "nongrowth", "ngam",
)

# Boundary reactions cannot be recognised from an id alone when only ids are available (cobra's
# `reaction.boundary` needs the object). These BiGG prefixes are the exchange/demand/sink
# convention; like the biomass hints this is a *hint* that produces a warning, never a refusal.
_BOUNDARY_ID_PREFIXES: tuple[str, ...] = ("EX_", "DM_", "SK_", "sink_", "demand_")


def _objective_reaction_text(reaction: object) -> str:
    """id + name of an objective term, accepting a cobra Reaction or a bare reaction id.

    Several call sites only ever hold ids (``ModelSummary.biomass_reactions``,
    ``ModelQualityReport.objective_reactions``), and before round 6 they could not use the
    single-term checks at all: passing a ``str`` made every ``getattr`` miss, so the id was
    reported back as ``'?'``. Accepting ids means the audit commands get the checks too.
    """
    if isinstance(reaction, str):
        return reaction.lower()
    return f"{getattr(reaction, 'id', '')} {getattr(reaction, 'name', '') or ''}".lower()


def _objective_reaction_id(reaction: object) -> str:
    if isinstance(reaction, str):
        return reaction
    return str(getattr(reaction, "id", "?"))


def _looks_like_biomass(reaction: object) -> bool:
    text = _objective_reaction_text(reaction)
    return any(hint in text for hint in _BIOMASS_NAME_HINTS)


def _looks_like_maintenance(reaction: object) -> bool:
    text = _objective_reaction_text(reaction)
    return any(hint in text for hint in _MAINTENANCE_NAME_HINTS)


def _looks_like_boundary(reaction: object) -> bool:
    if getattr(reaction, "boundary", False):
        return True
    return _objective_reaction_id(reaction).startswith(_BOUNDARY_ID_PREFIXES)


def objective_structure_warning(
    n_objective_terms: int, objective_reactions: object = None
) -> str | None:
    """Warn when an objective is not a single biomass-like reaction (A-B9).

    iAF987 ships with a 283-term linear objective, so its optimum is not a growth rate at all —
    yet it was counted as "283 biomass reactions", passed the has-biomass check silently, and was
    reported and plotted under the label "Growth rate". A multi-term objective is legal and
    sometimes intended; it just cannot be read as growth without saying so.

    Round 5 (blocker 3): counting terms is not sufficient. A **one-term** objective on a demand or
    exchange reaction is also not growth, and it slipped through silently — `strain-growth`
    reported a `DM_ac` flux of 10.0 as growth with `status: ok` and no warning at all. Pass
    ``objective_reactions`` (the cobra reactions carrying a non-zero objective coefficient, or
    just their ids) to get the single-term checks too; omitting it preserves the original
    count-only behaviour.

    Round 6 (track H): the round-5 checks still passed a **maintenance** objective in silence,
    which is the case that actually ships. Recon3D's default objective is `BIOMASS_maintenance`,
    it optimizes to 755.003, and every check above admitted it because "biomass" is in its name —
    so a maintenance turnover rate was available to be reported as growth by `model-quality`,
    `host-benchmark` and `host-generic` with no caveat anywhere. Maintenance is therefore tested
    for first.
    """
    if n_objective_terms == 0:
        return "no objective reaction detected; this model cannot report growth"
    if n_objective_terms > 1:
        return (
            f"objective has {n_objective_terms} terms; not a single biomass reaction — "
            "reported growth is an objective value, not a growth rate"
        )
    reactions = list(objective_reactions or [])
    if len(reactions) != 1:
        return None
    reaction = reactions[0]
    reaction_id = _objective_reaction_id(reaction)
    # Maintenance before biomass: `BIOMASS_maintenance` satisfies the biomass hint but describes
    # turnover without replication, so its optimum is not a growth rate at any scale.
    if _looks_like_maintenance(reaction):
        return (
            f"objective reaction {reaction_id} is a MAINTENANCE objective (turnover without "
            "replication); its optimum is a maintenance/ATP demand rate, NOT a growth rate — "
            "set the model's growth/biomass reaction explicitly to ask a growth question"
        )
    # Name next: `DM_biomass_c` / `EX_biomass_e` as the objective is a documented modelling
    # pattern (a demand on a biomass pseudo-metabolite) and IS growth, so the boundary check must
    # not veto it. What it catches is a boundary reaction with no biomass identity at all.
    if _looks_like_biomass(reaction):
        return None
    if _looks_like_boundary(reaction):
        return (
            f"objective is the boundary reaction {reaction_id} "
            "(exchange/demand/sink) with no biomass identity; a boundary flux is a transport "
            "rate, NOT a growth rate — reported growth is an objective value"
        )
    return (
        f"objective reaction {reaction_id} is not identifiable as a biomass "
        "reaction; reported growth is an objective value, not a confirmed growth rate"
    )


def import_model(path: str | Path) -> ModelSummary:
    """GEM 파일 → ModelSummary. 포맷 자동 감지 + cobra.io 위임."""
    p = Path(path)
    if not p.exists():
        raise ModelImportError(f"모델 파일 없음: {p}")
    fmt = detect_model_format(p)
    model = load_cobra_model(p)
    exchanges = sorted(str(r.id) for r in model.exchanges)
    try:
        biomass_reactions = _biomass_reactions(model)
    except Exception as e:                       # noqa: BLE001 - optlang/cobra expose open sets
        raise ModelImportError(
            f"objective 검사 실패 ({p.name}): {type(e).__name__}: {e}. "
            "이 모델의 objective 구조를 읽을 수 없어 growth 보고 가능 여부를 판단할 수 없습니다."
        ) from e
    return ModelSummary(
        model_id=str(model.id) or p.stem,
        source_format=fmt,
        source_path=str(p),
        n_reactions=len(model.reactions),
        n_metabolites=len(model.metabolites),
        n_genes=len(model.genes),
        exchanges=exchanges,
        biomass_reactions=biomass_reactions,
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
