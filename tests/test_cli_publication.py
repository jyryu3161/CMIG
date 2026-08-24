"""Direct CLI coverage for publication-oriented command registration and errors."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from cmig.cli import publication
from cmig.cli.main import build_parser, main


def _module(monkeypatch: pytest.MonkeyPatch, name: str, **attributes: Any) -> None:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)


def _install_publication_benchmark_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    class GateBlockedError(Exception):
        pass

    class ModelImportError(Exception):
        pass

    _module(monkeypatch, "pandas")
    _module(monkeypatch, "cmig.core.dfba", DfbaConfig=object)
    _module(monkeypatch, "cmig.core.medium_spec", load_medium=lambda _path: None)
    _module(
        monkeypatch,
        "cmig.core.model_pool",
        taxonomy_from_model_dir=lambda *_args, **_kwargs: None,
    )
    _module(
        monkeypatch,
        "cmig.core.namespace",
        GateBlockedError=GateBlockedError,
        load_namespace_decisions=lambda _path: [],
    )
    _module(monkeypatch, "cmig.core.search", Direction=lambda value: value)
    _module(
        monkeypatch,
        "cmig.io.model_import",
        ModelImportError=ModelImportError,
        load_cobra_model=lambda _path: None,
    )
    _module(
        monkeypatch,
        "cmig.service.publication_benchmark",
        PublicationBenchmarkConfig=object,
        run_publication_benchmark=lambda _config: None,
    )


@pytest.mark.parametrize(
    ("argv", "function"),
    [
        (["model-quality", "--model", "model.xml", "--out", "out"],
         publication.cmd_model_quality),
        (["publication-benchmark", "--model-dir", "models", "--out", "out"],
         publication.cmd_publication_benchmark),
    ],
)
def test_add_publication_parsers_registers_both_public_commands(argv, function) -> None:
    args = build_parser().parse_args(argv)

    assert args.func is function


@pytest.mark.parametrize(
    "argv",
    [
        ["model-quality", "--out", "out"],
        [
            "model-quality",
            "--model", "model.xml",
            "--model-dir", "models",
            "--out", "out",
        ],
        ["publication-benchmark", "--out", "out"],
        [
            "publication-benchmark",
            "--taxonomy", "taxonomy.csv",
            "--model-dir", "models",
            "--out", "out",
        ],
    ],
)
def test_publication_source_arguments_are_required_and_mutually_exclusive(argv) -> None:
    with pytest.raises(SystemExit) as error:
        main(argv)

    assert error.value.code == 2


def test_model_quality_forwards_public_cli_arguments(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    capsys,
) -> None:
    source = tmp_path / "model.xml"
    source.write_text("fixture")
    calls: dict[str, Any] = {}

    class ModelImportError(Exception):
        pass

    def load_model(path):
        calls["loaded"] = path
        return "model"

    def audit(model, **kwargs):
        calls["audit"] = (model, kwargs)
        return SimpleNamespace(solve_status="optimal")

    def write_reports(reports, out):
        calls["write"] = (reports, out)
        return ["model_quality.json", "model_quality.csv"]

    _module(
        monkeypatch,
        "cmig.core.model_pool",
        taxonomy_from_model_dir=lambda *_args, **_kwargs: None,
    )
    _module(monkeypatch, "cmig.core.model_quality", audit_model_quality=audit)
    _module(
        monkeypatch,
        "cmig.io.model_import",
        ModelImportError=ModelImportError,
        load_cobra_model=load_model,
    )
    _module(
        monkeypatch,
        "cmig.io.quality_output",
        write_model_quality_reports=write_reports,
    )
    monkeypatch.setattr(publication, "_emit_model_quality_manifest", lambda *_args: None)
    out = tmp_path / "quality"

    rc = main([
        "model-quality",
        "--model", str(source),
        "--check-blocked-reactions",
        "--out", str(out),
    ])

    assert rc == 0
    assert calls["loaded"] == source
    assert calls["audit"][1] == {
        "source_path": source,
        "solver": "gurobi",
        "check_blocked_reactions": True,
    }
    assert calls["write"][1] == str(out)
    assert "model-quality complete (1 models)" in capsys.readouterr().out


def test_model_quality_reports_missing_model_through_public_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    capsys,
) -> None:
    class ModelImportError(Exception):
        pass

    _module(
        monkeypatch,
        "cmig.core.model_pool",
        taxonomy_from_model_dir=lambda *_args, **_kwargs: None,
    )
    _module(monkeypatch, "cmig.core.model_quality", audit_model_quality=lambda *_args: None)
    _module(
        monkeypatch,
        "cmig.io.model_import",
        ModelImportError=ModelImportError,
        load_cobra_model=lambda _path: None,
    )
    _module(
        monkeypatch,
        "cmig.io.quality_output",
        write_model_quality_reports=lambda *_args: [],
    )
    missing = tmp_path / "missing.xml"

    rc = main([
        "model-quality", "--model", str(missing), "--out", str(tmp_path / "out")
    ])

    assert rc == 2
    assert str(missing) in capsys.readouterr().err


def test_publication_benchmark_reports_missing_taxonomy_through_public_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    capsys,
) -> None:
    _install_publication_benchmark_imports(monkeypatch)
    missing = tmp_path / "taxonomy.csv"

    rc = main([
        "publication-benchmark",
        "--taxonomy", str(missing),
        "--out", str(tmp_path / "out"),
    ])

    assert rc == 2
    assert f"taxonomy file not found: {missing}" in capsys.readouterr().err


def test_publication_benchmark_dependency_error_is_concise(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.setitem(sys.modules, "pandas", None)

    rc = main([
        "publication-benchmark",
        "--model-dir", str(tmp_path),
        "--out", str(tmp_path / "out"),
    ])

    assert rc == 2
    assert "requires the engine and stats stack" in capsys.readouterr().err
