# CMIG Publication Validation

This document records the publication-preflight benchmark added on 2026-07-10. Runtime outputs
are intentionally written under `.run/` and are not distributed in the source package. Re-run the
commands below on the target analysis machine and archive the resulting directory with a paper.

## Validation inputs

- Microbial pool: the five bundled GEM files `iAF987`, `iHN637`, `iML1515`, `iSFV_1184`, and
  `iYO844`. Their joint semantic/file fingerprint in this run was
  `sha256:4cee02be171dcd7cf85b578638522ce4d308277cad4ccbe5eed110636d6d2aaa`.
- Host scale model: Human-GEM v1.19.0, downloaded from the versioned
  [Human-GEM repository](https://github.com/SysBioChalmers/Human-GEM/tree/v1.19.0). The local SBML
  checksum was `sha256:5aa161fbd52e79051dc445d87965db0716219d95ef1a6f0a8c5bd51fd60e075c`.
  Cite the archived release [doi:10.5281/zenodo.12523225](https://doi.org/10.5281/zenodo.12523225)
  and the Human-GEM publication appropriate to the model version.
- Runtime: CMIG 0.1.0, MICOM 0.39.0, COBRApy 0.31.1, Gurobi 12.0.3, optlang 1.9.0,
  pandas 2.3.3, and PyArrow 24.0.0.

External host models are not redistributed by CMIG. The benchmark manifest records their path,
version metadata, URL, DOI, and SHA-256 checksum.

## Integrated benchmark

Generate and review the host interface suggestions first:

```bash
uv run cmig host-map \
  --host fixtures/Human-GEM-v1.19.0.xml \
  --model-dir models \
  --out .run/publication-validation/human-gem-map
```

Human-GEM uses `MAR...` reaction IDs. CMIG therefore indexes extracellular metabolite
`bigg.metabolite` annotations, while using reaction-level BiGG annotations only when metabolite
annotations are absent. The measured map contained 204 annotation matches among 520 secretable
microbial exchange candidates. The generated map is a review draft, not an automatic authorization.

After reviewing `host_interface_map.json`, run the integrated package:

```bash
export MICROBIAL_BIOMASS_GDW="<study microbial dry mass in gDW>"
export HOST_BIOMASS_GDW="<host dry-mass basis represented by the host model in gDW>"
export BIOMASS_BASIS_SOURCE="<measurement record, Methods section, or literature citation>"

uv run cmig publication-benchmark \
  --model-dir models \
  --assume-bigg-namespace \
  --search-target ac \
  --search-min-size 2 \
  --search-max-size 2 \
  --dfba-model models/iML1515.xml \
  --dfba-t-end 2 \
  --dfba-dts 0.2,0.1,0.05 \
  --dfba-kms 0.005,0.01,0.02 \
  --host fixtures/Human-GEM-v1.19.0.xml \
  --host-name Human-GEM \
  --host-version v1.19.0 \
  --host-source-url https://github.com/SysBioChalmers/Human-GEM/tree/v1.19.0 \
  --host-doi 10.5281/zenodo.12523225 \
  --host-interface-map .run/publication-validation/human-gem-map/host_interface_map.json \
  --microbial-biomass-gdw "$MICROBIAL_BIOMASS_GDW" \
  --host-biomass-gdw "$HOST_BIOMASS_GDW" \
  --biomass-basis-kind measured \
  --biomass-basis-source "$BIOMASS_BASIS_SOURCE" \
  --keep-host-uptake \
  --out .run/publication-validation/integrated
```

The command refuses reviewed host coupling when either biomass value, its basis kind, or its source
is absent. Use `literature` instead of `measured` only with a traceable citation. The `validation`
kind is reserved for engineering tests and forces `publication_ready: false`.

## Engineering acceptance results

The previously recorded unit-basis host coupling run was an engineering validation, not a
study-specific quantitative result. Its hash is intentionally no longer presented as a
publication-ready benchmark. A paper must archive the new manifest generated with the study values
and provenance above; any input, configuration, solver, dependency, or biomass-source change
produces a different hash.

| Check | Result |
|---|---|
| Five microbial GEM objective solves | all optimal; objectives 0.0473–0.894 |
| Five-member MICOM community | optimal; equal-abundance growth 0.908268 |
| Pairwise acetate search | 9 optimal pairs; one physically infeasible pair under growth/sign constraints |
| Best acetate pair | `iHN637+iSFV_1184`, target flux 27.7485 |
| iML1515 dFBA `dt×Km` grid | 9/9 completed; concentration and biomass update residuals 0 |
| dFBA time-step sensitivity | `dt=0.2` was about 9.5% below the `dt=0.05` final-biomass reference |
| Human-GEM scale | 12,971 reactions, 8,455 metabolites, 2,887 genes; optimal objective 124.868 |
| Human-GEM solve time | 1.3 s for the generic host LP in the measured environment |
| Real host interface map | 204 annotation matches of 520 candidates |
| Structural 5-GEM→Human-GEM validation | community and host both optimal; acetate, ethanol, and Fe²⁺ mapped; `4hbald` unmatched; not a study-scaled transfer estimate |

The structural host validation did **not** report a point microbial transfer. Acetate, ethanol, and
Fe²⁺ objective-fixed FVA ranges included zero. Thus it establishes feasible coupling capacity, not
uniquely identifiable or study-scaled uptake. CMIG stores intervals and leaves `microbe_to_host`
empty in this case.

## Output contract

`publication_benchmark.json` is the final commit marker. It contains:

- checks and `overall_passed`;
- separate `computational_checks_passed` and `publication_ready` flags;
- a benchmark hash over scientific inputs and dependency versions;
- individual model, host, and dFBA source checksums;
- wall-clock timings;
- SHA-256 checksums for every generated artifact;
- explicit limitations;
- the numeric biomass bases, `basis_kind`, and their measurement/citation source.

Subdirectories contain lossless JSON and flat CSV outputs for model quality, community solve,
consortium search, dFBA sensitivity, host quality/mapping, and optional reviewed host coupling.

## Interpretation limits

- These are constraint-based predictions, conditional on model reconstruction, objective, medium,
  abundance, and solver configuration.
- A deterministic parameter grid is not a biological replicate. CMIG blocks sweep p-values unless
  an independent replicate column is supplied and explicitly confirmed.
- Member transfer contributions use an abundance-weighted proportional allocation and are not
  causal or uniquely identifiable.
- An annotation match is a mapping candidate. It must be reviewed before quantitative coupling.
