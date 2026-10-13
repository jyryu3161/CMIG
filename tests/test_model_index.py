from __future__ import annotations

import json
from pathlib import Path

import pytest
from gui_project_helpers import textbook_sbml

from cmig.io import model_index as mi
from cmig.io import project as proj


@pytest.fixture(scope="module")
def textbook(tmp_path_factory) -> Path:
    return textbook_sbml(tmp_path_factory.mktemp("src") / "textbook.xml")


def test_index_from_model_content(textbook: Path) -> None:
    from cmig.io.model_import import load_cobra_model

    body = mi.index_from_model(load_cobra_model(textbook))
    reactions = {r["id"]: r for r in body["reactions"]}
    assert len(reactions) == 95
    pgi = reactions["PGI"]
    assert pgi["metabolites"] == {"g6p_c": -1.0, "f6p_c": 1.0}
    assert pgi["lower"] == -1000.0 and pgi["upper"] == 1000.0
    assert "b4025" in pgi["gpr"]
    mets = {m["id"]: m for m in body["metabolites"]}
    assert mets["glc__D_e"]["compartment"] == "e" and mets["glc__D_e"]["formula"] == "C6H12O6"
    genes = {g["id"]: g for g in body["genes"]}
    assert "PGI" in genes["b4025"]["reactions"]
    assert "EX_glc__D_e" in body["exchanges"]
    assert body["objective"] == [{"id": "Biomass_Ecoli_core", "coef": 1.0}]
    json.dumps(body, allow_nan=False)  # strict JSON, no NaN/Infinity


def test_write_and_load_round_trip(tmp_path: Path, textbook: Path) -> None:
    path = mi.build_index_file(tmp_path, textbook, "sha1", "textbook")
    assert path == tmp_path / "models" / ".index" / "sha1.json"
    loaded = mi.load_index(tmp_path, "sha1")
    assert loaded is not None and loaded["model_id"] == "textbook"
    assert loaded["schema_version"] == mi.INDEX_SCHEMA_VERSION


def test_corrupt_or_foreign_index_is_rejected(tmp_path: Path) -> None:
    path = mi.index_path(tmp_path, "abc")
    path.parent.mkdir(parents=True)
    path.write_text("{broken")
    assert mi.load_index(tmp_path, "abc") is None
    path.write_text(json.dumps({"schema_version": 1, "sha256": "other", "model_id": "m",
                                "reactions": [], "metabolites": [], "genes": [],
                                "exchanges": [], "objective": []}))
    assert mi.load_index(tmp_path, "abc") is None  # another file's index
    path.write_text(json.dumps({"schema_version": 99, "sha256": "abc"}))
    assert mi.load_index(tmp_path, "abc") is None
    assert mi.load_index(tmp_path, "missing") is None


def test_search_rows(tmp_path: Path, textbook: Path) -> None:
    mi.build_index_file(tmp_path, textbook, "s", "textbook")
    rows = mi.search_rows(mi.load_index(tmp_path, "s") or {})
    assert ("reaction", "PGI", "glucose-6-phosphate isomerase") in rows
    assert ("metabolite", "glc__D_e", "D-Glucose") in rows
    assert any(kind == "gene" and key == "b4025" for kind, key, _name in rows)


def test_adding_a_model_writes_its_index_from_the_same_read(
    tmp_path: Path, textbook: Path, monkeypatch
) -> None:
    import cmig.io.model_import as model_import

    reads: list[str] = []
    original = model_import.load_cobra_model

    def counting(path):  # type: ignore[no-untyped-def]
        reads.append(str(path))
        return original(path)

    monkeypatch.setattr(model_import, "load_cobra_model", counting)
    project = proj.create_project(tmp_path / "p")
    entry = proj.add_model_file(project, textbook)
    assert len(reads) == 1, "the check and the index share one read"
    loaded = mi.load_index(project.root, entry.sha256)
    assert loaded is not None and loaded["model_id"] == entry.id


def test_index_write_failure_does_not_fail_the_import(
    tmp_path: Path, textbook: Path, monkeypatch
) -> None:
    def refuse(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise OSError("read-only")

    monkeypatch.setattr(mi, "write_index", refuse)
    project = proj.create_project(tmp_path / "p")
    entry = proj.add_model_file(project, textbook)
    assert entry.status in ("ok", "warning")
    assert mi.load_index(project.root, entry.sha256) is None
