"""Phase 0.4 — Model Import (SBML/JSON/MAT → ModelSummary). Plan SC: SC-MI1~MI5."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("cobra")
pytest.importorskip("micom")

import cobra  # noqa: E402
import micom  # noqa: E402

from cmig.core.model_pool import (  # noqa: E402
    diagnose_model_pool,
    discover_model_files,
    member_id_from_path,
    taxonomy_from_model_dir,
)
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
    """User-provided GEM review: import summary + namespace coverage + next actions."""
    summary = import_model(_SBML)
    review = build_import_review(summary, known_targets={"glc__D"})
    assert review.inferred_origin == "user_provided_gem"
    assert review.namespace["n_decisions"] > 0
    assert "decisions" in review.namespace
    assert review.next_actions


def test_infer_model_origin_from_path():
    summary = ModelSummary(
        model_id="Recon3D",
        source_format="sbml",
        source_path="/models/Recon3D.xml",
        n_reactions=1,
        n_metabolites=1,
        n_genes=0,
        exchanges=[],
        biomass_reactions=[],
    )
    assert infer_model_origin(summary) == "human_gem"


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


def test_model_pool_from_directory(tmp_path):
    """User model folder -> deterministic MICOM taxonomy pool."""
    (tmp_path / "A model.xml").write_text("<sbml/>")
    (tmp_path / "B-model.sbml").write_text("<sbml/>")
    (tmp_path / "notes.txt").write_text("ignore")
    files = discover_model_files(tmp_path)
    assert len(files) == 2
    assert member_id_from_path(tmp_path / "A model.xml") == "A_model"
    taxonomy = taxonomy_from_model_dir(tmp_path)
    assert list(taxonomy["id"]) == ["A_model", "B_model"]
    assert all(Path(p).is_absolute() for p in taxonomy["file"])


def test_model_pool_collision_ids_get_stable_digest_suffix(tmp_path):
    """Punctuation-only filename collisions should not depend on discovery tie numbering."""
    (tmp_path / "a-b.xml").write_text("<sbml/>")
    (tmp_path / "a.b.xml").write_text("<sbml/>")
    taxonomy = taxonomy_from_model_dir(tmp_path)
    ids = list(taxonomy["id"])
    assert len(ids) == len(set(ids)) == 2
    assert all(x.startswith("a_b_") for x in ids)
    assert ids == list(taxonomy_from_model_dir(tmp_path)["id"])


def test_model_pool_recursive_same_basename_gets_unique_path_digest(tmp_path):
    """Recursive pools commonly use strain folders with the same model basename."""
    (tmp_path / "strainA").mkdir()
    (tmp_path / "strainB").mkdir()
    (tmp_path / "strainA" / "model.xml").write_text("<sbml/>")
    (tmp_path / "strainB" / "model.xml").write_text("<sbml/>")
    taxonomy = taxonomy_from_model_dir(tmp_path, recursive=True)
    ids = list(taxonomy["id"])
    assert len(ids) == len(set(ids)) == 2
    assert all(x.startswith("model_") for x in ids)
    assert ids == list(taxonomy_from_model_dir(tmp_path, recursive=True)["id"])


def test_model_pool_diagnostics_detect_target_and_biomass():
    import pandas as pd

    taxonomy = pd.DataFrame([{"id": "ecoli", "file": _SBML}])
    diag = diagnose_model_pool(taxonomy, "ac")
    assert len(diag) == 1
    assert diag[0].readable is True
    assert diag[0].has_target_exchange is True
    assert diag[0].n_biomass == 1
    assert "EX_ac_e" in diag[0].matching_exchanges
