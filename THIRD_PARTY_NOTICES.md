# Third-party notices

The Apache-2.0 license in `LICENSE` applies to CMIG-authored source code and documentation. It does
not relicense external GEM data, solvers, Python/R dependencies, or generated research outputs.

## BiGG model data

Files currently stored under `models/` use model identifiers and data distributed through
[BiGG Models](https://bigg.ucsd.edu/models). BiGG is copyright The Regents of the University of
California and permits educational, research, and non-profit use subject to its own notice and
conditions. Commercial users must obtain permission from UC San Diego. The authoritative terms are
on the [BiGG website](https://bigg.ucsd.edu/); they override this summary.

The GEM files are excluded from CMIG wheels and source distributions. Their per-file source URLs and
SHA-256 checksums are recorded in `models/MODEL_SOURCES.json`. When publishing results, cite both the
specific model reconstruction and the BiGG Models resource:

> King ZA, et al. BiGG Models: A platform for integrating, standardizing and sharing genome-scale
> models. Nucleic Acids Research 44(D1), D515-D522 (2016). doi:10.1093/nar/gkv1049.

## Human-GEM / Recon models

Human host models are never bundled. `docs/PUBLICATION_VALIDATION.md` documents the versioned
Human-GEM v1.19.0 validation input, its checksum, source, and Zenodo DOI. Users are responsible for
the model's own license and citation requirements.

## Runtime dependencies

- MICOM is used through its public Python API and is distributed separately under Apache-2.0.
- COBRApy and its transitive solver interfaces are installed as separate dependencies under their
  respective licenses.
- Gurobi is proprietary and is not bundled. Users must supply a valid license.
- R and optional R plotting packages run in a separate process. Their licenses remain independent;
  CMIG exchanges CSV and image files with that process. Exact R package versions are enumerated in
  `cmig/render_r/renv.lock`, which is also checksummed in every R render provenance record.
- Cytoscape.js is included as a vendored browser asset under its upstream license; retain its
  embedded header and attribution when redistributing the GUI package.

This file is an engineering notice, not legal advice. Verify all upstream terms for the exact
versions and intended distribution context.
