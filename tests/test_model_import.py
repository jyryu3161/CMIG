"""Phase 0.4 — Model Import (SBML/JSON/MAT → ModelSummary). Plan SC: SC-MI1~MI5."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("cobra")
pytest.importorskip("micom")

import cobra  # noqa: E402
import micom  # noqa: E402

from cmig.io.model_import import (  # noqa: E402
    ModelImportError,
    ModelSummary,
    build_import_review,
    import_model,
    infer_model_origin,
)

_SBML = os.path.join(os.path.dirname(micom.__file__), "data", "e_coli_core.xml.gz")


def test_import_sbml_e_coli():
    """SC-MI1: SBML import — 95 rxns·72 mets·137 genes·20 exchanges·biomass 탐지."""
    s = import_model(_SBML)
    assert isinstance(s, ModelSummary)
    assert s.model_id == "e_coli_core" and s.source_format == "sbml"
    assert s.n_reactions == 95 and s.n_metabolites == 72 and s.n_genes == 137
    assert len(s.exchanges) == 20
    assert s.biomass_reactions == ["BIOMASS_Ecoli_core_w_GAM"]


def test_import_json_roundtrip(tmp_path):
    """SC-MI2: JSON 포맷 import — SBML 과 동일 카운트."""
    model = cobra.io.read_sbml_model(_SBML)
    jpath = tmp_path / "model.json"
    cobra.io.save_json_model(model, str(jpath))
    s = import_model(jpath)
    assert s.source_format == "json"
    assert s.n_reactions == 95 and s.n_metabolites == 72


def test_summary_as_dict():
    """SC-MI3: as_dict (Model Manager 표시용)."""
    d = import_model(_SBML).as_dict()
    assert d["n_exchanges"] == 20 and d["n_biomass"] == 1 and d["source_format"] == "sbml"


def test_import_review_namespace_payload():
    """AGORA/VMH review UX: import summary + namespace coverage + next actions."""
    summary = import_model(_SBML)
    review = build_import_review(summary, known_targets={"glc__D"})
    assert review.inferred_origin == "generic_gem"
    assert review.namespace["n_decisions"] > 0
    assert "decisions" in review.namespace
    assert review.next_actions


def test_infer_model_origin_from_path():
    summary = ModelSummary(
        model_id="AGORA_member",
        source_format="sbml",
        source_path="/models/VMH_AGORA.xml",
        n_reactions=1,
        n_metabolites=1,
        n_genes=0,
        exchanges=[],
        biomass_reactions=[],
    )
    assert infer_model_origin(summary) == "agora"


def test_unsupported_extension(tmp_path):
    """SC-MI4: 미지원 확장자(존재 파일) → ModelImportError(정직)."""
    bad = tmp_path / "model.foo"
    bad.write_text("garbage")
    with pytest.raises(ModelImportError, match="미지원 모델 확장자"):
        import_model(bad)


def test_missing_file():
    """SC-MI5: 파일 부재 → ModelImportError."""
    with pytest.raises(ModelImportError, match="없음"):
        import_model("/tmp/cmig_nonexistent_model.xml")


def test_parse_failure_explicit(tmp_path):
    """SC-MI4: 손상 SBML → 명시적 파싱 에러(silent 위장 금지)."""
    corrupt = tmp_path / "corrupt.xml"
    corrupt.write_text("<not valid sbml>")
    with pytest.raises(ModelImportError):
        import_model(corrupt)
