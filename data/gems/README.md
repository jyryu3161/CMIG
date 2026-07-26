# External human GEMs (host models)

These are the human genome-scale reconstructions CMIG uses as the **host** in host–microbe
coupling. They are research inputs, not CMIG-authored code.

The SBML files themselves are **not in source control** — they are 15–29 MB, and BiGG distributes
them under a custom UCSD **non-commercial** licence (see below), so CMIG must not redistribute
them inside a wheel or sdist. `GEM_SOURCES.json` in this directory plus
`scripts/download_human_gems.py` are the tracked provenance record.

```bash
python scripts/download_human_gems.py                    # fetch + checksum-verify both models
python scripts/download_human_gems.py --verify --counts   # re-verify bytes AND reaction counts
```

CMIG then finds them without any configuration. The resolution order
(`cmig/io/gem_paths.py::human_gem_candidates`) is:

1. `$CMIG_RECON3D_PATH` / `$CMIG_RECON1_PATH`
2. `$CMIG_GEM_DIR/<id>.xml` — for a shared read-only GEM store
3. **`data/gems/<id>.xml`** — this directory, where the download script writes
4. `fixtures/<id>.xml`
5. `./<id>.xml`

Step 3 is what makes `tests/test_recon3d_host.py` run instead of skip.

## What is here

| BiGG id | reactions | metabolites | genes | boundary rxns | publication |
|---|---|---|---|---|---|
| `Recon3D` | 10600 | 5835 | 2248 | 1806 (1560 `EX_`, 101 sinks, 145 demands) | Brunk et al. 2018 |
| `RECON1` | 3741 | 2766 | 1905 | 430 (404 `EX_`) | Duarte et al. 2007 |

Counts measured with cobra 0.31.1; re-checkable with `--verify --counts`.

**Recon3D** — Brunk E, Sahoo S, Zielinski DC, … Thiele I, Palsson BO. *Recon3D enables a
three-dimensional view of gene variation in human metabolism.* Nature Biotechnology.
2018;36(3):272-281. doi:[10.1038/nbt.4072](https://doi.org/10.1038/nbt.4072) · PMID 29457794

**RECON1** — Duarte NC, Becker SA, Jamshidi N, Thiele I, Mo ML, Vo TD, Srivas R, Palsson BØ.
*Global reconstruction of the human metabolic network based on genomic and bibliomic data.* PNAS.
2007;104(6):1777-1782. doi:[10.1073/pnas.0610772104](https://doi.org/10.1073/pnas.0610772104) ·
PMID 17267599

Both PMIDs were read from BiGG's own API (`/api/v2/models/<id>` → `reference_id`) and the
bibliographic details cross-checked against PubMed and Crossref on 2026-07-26.

## ⚠ Never inherit the shipped default objective

This is the most important thing on this page. **Neither model's shipped objective is growth.**

| model | shipped objective | Gurobi optimum | what it actually is |
|---|---|---|---|
| `Recon3D` | `BIOMASS_maintenance` | **755.0032155506631** | biomass *maintenance without replication precursors* — a maintenance/ATP turnover rate |
| `RECON1` | `S6T14g` | **0.0** | Galactose/N-acetylglucosamine 6-O-sulfotransferase, Golgi — a **transport** reaction |

`755.003` is **not a growth rate** and must never be labelled one. `0.0` for RECON1 is **not
evidence of non-viability** — it is the optimum of a sulfotransferase.

Choose the objective explicitly, per question:

* **growth / biomass question, Recon3D** → `--host-objective BIOMASS_reaction`
  ("Generic Human Biomass Reaction", 41 metabolites, bounds (0, 1000))
* **maintenance / ATP question, Recon3D** → `--host-objective BIOMASS_maintenance`, and label the
  result *maintenance*, never growth
* **growth question, RECON1** → not answerable as distributed. RECON1 has **zero** reactions whose
  id or name contains "biomass" or "growth"; a biomass reaction must be supplied by the user.

CMIG now warns on both of these itself: `summarize_host_model().objective_warning`,
`model-quality`, `host-generic` and `host-benchmark` all emit an explicit
"MAINTENANCE objective … NOT a growth rate" / "not identifiable as a biomass reaction" note.

## ⚠ Recon3D is not isolated by closing `EX_` reactions

Recon3D has 246 boundary reactions that cobra classifies as **sinks/demands rather than
exchanges**, and 95 of them sit at `lower_bound = -1000`, i.e. they can inject mass with no
medium and no microbes. Measured: with only `EX_*` uptake closed, the coupled
`BIOMASS_reaction` optimum was **bit-identical (368.01024754644214) with and without any
microbial availability** — the host was growing on `SK_*` sinks. `cmig` host coupling now closes
every boundary uptake and reports how many non-exchange boundary reactions it closed.

Consequence for interpretation: an objective value from this model is only attributable to a
declared input if the sinks are closed. Check the run's warnings for
`non-exchange boundary reactions`.

## ⚠ Physiological scale

Recon3D's boundary bounds are ±1000 mmol gDW⁻¹ h⁻¹ with no physiological calibration, so an
unconstrained optimum (755, 684, 368 …) is an LP artefact, not a human growth rate (a real human
cell is ~1e-2 h⁻¹). Any number from this model must be reported with the medium that produced it,
and a medium that is not sourced from a diet or serum measurement must be declared as an
assumption.

## Licence — read before redistributing or publishing

BiGG Models is **not** under an open-source or Creative Commons licence. From
<http://bigg.ucsd.edu/license> (retrieved 2026-07-26):

> Copyright © 2019 The Regents of the University of California — All Rights Reserved
>
> Permission to use, copy, modify and distribute any part of BiGG Models for educational, research
> and non-profit purposes, without fee, and without a written agreement is hereby granted, provided
> that the above copyright notice, this paragraph and the following three paragraphs appear in all
> copies.
>
> Those desiring to incorporate BiGG Models into commercial products or use for commercial purposes
> should contact the Technology Transfer & Intellectual Property Services, University of California,
> San Diego, 9500 Gilman Drive, Mail Code 0910, La Jolla, CA 92093-0910, Ph: (858) 534-5815,
> FAX: (858) 534-7345, e-mail: invent@ucsd.edu.

CMIG is Apache-2.0; that does **not** apply to these files.

Cite the resource in addition to each reconstruction's own paper — BiGG asks for:

> King ZA, Lu JS, Dräger A, Miller PC, Federowicz S, Lerman JA, Ebrahim A, Palsson BO, Lewis NE.
> BiGG Models: A platform for integrating, standardizing, and sharing genome-scale models (2016)
> Nucleic Acids Research 44(D1):D515-D522. doi:10.1093/nar/gkv1049

Note: `bigg.ucsd.edu` serves **plain HTTP only**; an `https://` request is refused at the TCP
level rather than downgraded.
