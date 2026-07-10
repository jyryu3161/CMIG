"""Integrated publication benchmark package."""

from __future__ import annotations

import json
import os

import pytest

cobra = pytest.importorskip("cobra")
micom = pytest.importorskip("micom")

from cmig.core.dfba import DfbaConfig  # noqa: E402
from cmig.service.publication_benchmark import (  # noqa: E402
    PublicationBenchmarkConfig,
    run_publication_benchmark,
)
from cmig.synthetic_host import build_host_model  # noqa: E402
from cmig.synthetic_pair import build_pair_taxonomy  # noqa: E402


def test_publication_benchmark_writes_auditable_integrated_package(tmp_path):
    taxonomy = build_pair_taxonomy(tmp_path / "microbes")
    dfba_model = tmp_path / "ecoli.xml"
    core_model = cobra.io.read_sbml_model(
        os.path.join(os.path.dirname(micom.__file__), "data", "e_coli_core.xml.gz")
    )
    cobra.io.write_sbml_model(core_model, str(dfba_model))
    host_model = tmp_path / "host.xml"
    cobra.io.write_sbml_model(build_host_model(), str(host_model))
    out = tmp_path / "benchmark"

    manifest_path = run_publication_benchmark(
        PublicationBenchmarkConfig(
            taxonomy=taxonomy,
            taxonomy_base_dir=tmp_path,
            out_dir=out,
            namespace_policy="assume_bigg",
            search_target="but",
            search_min_size=2,
            search_max_size=2,
            dfba_model=dfba_model,
            dfba_config=DfbaConfig(
                t_end=0.2,
                dt=0.1,
                initial_concentrations={"EX_glc__D_e": 10.0},
            ),
            dfba_dts=[0.1, 0.05],
            dfba_kms=[0.01],
            host_model=host_model,
            host_source={"name": "synthetic test host", "version": "1"},
            host_interface_map={"but": "EX_but_lumen"},
            microbial_biomass_gdw=1.0,
            host_biomass_gdw=1.0,
            biomass_basis_kind="measured",
            biomass_basis_source="synthetic fixture dry-mass definition",
            keep_host_uptake=True,
        )
    )

    payload = json.loads(manifest_path.read_text())
    assert payload["overall_passed"] is True
    assert payload["publication_ready"] is True
    assert payload["computational_checks_passed"] is True
    assert all(payload["checks"].values())
    assert len(payload["benchmark_hash"]) == 64
    assert "model_quality/model_quality.json" in payload["artifacts"]
    assert "community/manifest.json" in payload["artifacts"]
    assert "search/search_benchmark.json" in payload["artifacts"]
    assert "dfba/dfba_sensitivity.json" in payload["artifacts"]
    assert "host/host_benchmark.json" in payload["artifacts"]
    assert "host/host_map_benchmark.json" in payload["artifacts"]
    assert "host/host_coupling_benchmark.json" in payload["artifacts"]


def test_publication_benchmark_rejects_unprovenanced_host_scaling(tmp_path):
    taxonomy = build_pair_taxonomy(tmp_path / "microbes")
    with pytest.raises(ValueError, match="explicit biomass values and provenance"):
        run_publication_benchmark(
            PublicationBenchmarkConfig(
                taxonomy=taxonomy,
                taxonomy_base_dir=tmp_path,
                out_dir=tmp_path / "out",
                namespace_policy="assume_bigg",
                host_model=tmp_path / "host.xml",
                host_interface_map={"but": "EX_but_lumen"},
            )
        )


def test_publication_benchmark_cli_requires_namespace_policy(tmp_path, capsys):
    taxonomy = build_pair_taxonomy(tmp_path / "microbes")
    tax_path = tmp_path / "taxonomy.csv"
    taxonomy.to_csv(tax_path, index=False)
    from cmig.cli.main import main

    rc = main([
        "publication-benchmark", "--taxonomy", str(tax_path),
        "--search-target", "but", "--out", str(tmp_path / "out"),
    ])
    assert rc == 2
    assert "namespace gate blocked" in capsys.readouterr().err
