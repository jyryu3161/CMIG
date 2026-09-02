# CMIG — Community Metabolic Interaction GUI

[![CI](https://github.com/jyryu3161/CMIG/actions/workflows/ci.yml/badge.svg)](https://github.com/jyryu3161/CMIG/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](pyproject.toml)

CMIG is a desktop and command-line platform for **metabolic interaction analysis
in microbial communities**. Community flux balance analysis is delegated to
[MICOM](https://github.com/micom-dev/micom); CMIG provides the layer around it
that turns a solve into a result you can defend — model-pool search, host-microbe
coupling, medium diagnostics, dynamic simulation, and a reproducibility record
for every run.

---

## What CMIG does

| | |
| --- | --- |
| **Prepare models** | Import and audit user GEMs, check identifier namespaces, fetch selected AGORA2 reconstructions with recorded provenance, and diagnose a medium that cannot support the pool |
| **Simulate communities** | MICOM community FBA on a defined medium, monoculture-vs-coculture comparison, per-strain growth, abundance sweeps |
| **Design consortia** | Rank model-pool combinations by production of a target metabolite (exhaustive, random, or genetic-algorithm search), and rank gene or reaction knockouts |
| **Couple host and microbes** | Map microbial secretion onto a host GEM through a reviewed interface map, and measure a knockout's effect on the host |
| **Simulate dynamics** | Well-mixed dFBA for one model or a community, with a dt/Km sensitivity audit and a spatial medium preview |
| **Report** | Tidy Parquet outputs, publication figures (R with a matplotlib fallback), and a submission preflight bundle |

Run `cmig workflows --format text` for the full catalogue of all 34 analyses.

## Design principles

These are what the implementation is organised around, and each is enforced by a
gate in continuous integration rather than by convention.

- **Every run is reproducible.** Each analysis writes a manifest with a
  `run_hash` over its declared inputs, checksums of models and media, solver and
  dependency versions, and a digest of the artifacts it produced.
  `cmig inspect-run` reads any run back; a frozen golden hash and a
  serialization gate fail the build if that contract silently changes.
- **A failed analysis is never dressed as a result.** Non-viable communities,
  infeasible solves, unevaluable candidates and uninterpretable dynamics are
  quarantined and named, not ranked or averaged. Exit code 3 means "artifacts
  were written but the science did not succeed".
- **The environment is explicit.** A medium either *merges* onto a model's
  defaults or *replaces* them, the manifest records which, and the boundary
  isolation that makes "replaces" true is measured rather than assumed.
- **CMIG curates no data.** It reads the GEMs you give it. Its only network
  commands fetch user-selected AGORA2 reconstructions on demand, from the
  publisher's own server, and record exactly what was retrieved and how it was
  transformed.

## Installation

Requires Python 3.10+, [`uv`](https://docs.astral.sh/uv/), and a Gurobi 12
license for the full solver workflow.

```bash
git clone https://github.com/jyryu3161/CMIG.git
cd CMIG
uv sync --extra engine --extra gui --extra render --extra stats
uv run cmig version && uv run cmig solvers
```

## Quick start

```bash
uv run cmig gui                                    # graphical interface

uv run cmig solve --taxonomy tax.csv \
  --medium medium_presets/gut_overlay_agora_western.csv \
  --exact-medium --assume-bigg-namespace --out runs/solve

uv run cmig inspect-run --run-dir runs/solve       # read the run back
```

Full installation options, the GUI tour, worked command examples and the
developer workflow are in **[docs/USAGE.md](docs/USAGE.md)**.

## Documentation

| Document | Contents |
| --- | --- |
| [docs/USAGE.md](docs/USAGE.md) | Installation, GUI, CLI, medium semantics, development |
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | Reference manual: full workflow catalogue, automation contract, output schemas, scope and limitations |
| [docs/cmig_hands_on_tutorial.html](docs/cmig_hands_on_tutorial.html) | Tutorial with real commands, real outputs and GUI screenshots |
| [docs/PUBLICATION_VALIDATION.md](docs/PUBLICATION_VALIDATION.md) | Validation protocol to re-run before publishing results |
| [CHANGELOG.md](CHANGELOG.md) | Release history, including breaking contract changes |

## Citation

If you use CMIG, please cite the software (see [CITATION.cff](CITATION.cff)) and
the model and data resources your analysis used. MICOM, Gurobi and any model
collection you load each carry their own citation requirements; the manifest of
every run records the versions and sources involved.

## License

CMIG's own code and documentation are Apache-2.0 ([LICENSE](LICENSE),
[NOTICE](NOTICE)). External GEMs, solvers, dependencies and generated research
outputs keep their own terms — see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The validation models under
`models/` are not Apache-licensed and are excluded from distributions.
