# Provenance — gut medium overlays

Every number in `medium_presets/gut_overlay_*.csv` is traceable from here to a mirrored source file
in `medium_presets/sources/` and from there to a published source. The overlays are generated, never
hand-edited:

```bash
python -m scripts.build_gut_media            # regenerate
python -m scripts.build_gut_media --check    # CI/test: fail if a shipped file is stale
python -m scripts.build_gut_media --report   # per-model coverage + fibre coverage
```

Row-level provenance for all 717 shipped rows — origin, pre-conversion value, factor, scale — is in
`medium_presets/provenance_rows.csv`.

---

## 0. Why these files are called **overlays**, not diets

CMIG applies `--medium` by **merging** onto whatever the community already offers
(`apply_medium_translated(..., exact=False)` in `cmig/core/medium_spec.py`). A CSV therefore does not
*define* the medium; it overlays it, and any metabolite the file does not name keeps MICOM's default
bound. Measured on a MICOM community of `iML1515 + iYO844`, applying a glucose-only spec:

```
medium entries before: 24   after: 24
NOT in the requested spec but still open: 23
   EX_o2_m  = 999999.0   EX_co2_m = 999999.0   EX_fe3_m = 999999.0   EX_h_m   = 999999.0
   EX_mg2_m = 999999.0   EX_ca2_m = 999999.0   EX_h2o_m = 999999.0   EX_k_m   = 999999.0
   EX_na1_m = 999999.0   EX_pi_m  = 1000.0     EX_mn2_m = 1000.0     EX_fe2_m = 1000.0
   EX_zn2_m = 1000.0     EX_ni2_m = 1000.0     EX_cu2_m = 1000.0     EX_sel_m = 1000.0
   EX_cobalt2_m = 1000.0 EX_mobd_m = 1000.0    EX_so4_m = 1000.0     EX_nh4_m = 1000.0
   EX_cl_m  = 1000.0     EX_tungs_m = 1000.0   EX_slnt_m = 1000.0
```

**`EX_o2_m = 999999.0` is disqualifying for a gut simulation.** Any CMIG result produced with a
custom medium that did not explicitly name oxygen was computed with oxygen freely available.
Quantified on `iML1515 + iYO844 + iHN637`, equal abundance, `cooperative_tradeoff(f=0.5)`, Gurobi,
using the legacy `western_diet.csv` (glucose only):

| medium | `EX_o2_m` after apply | community growth (h⁻¹) |
|---|---|---|
| `EX_glc__D_m,20.0` — as shipped | **999999.0** | **1.2677557** |
| the same plus `EX_o2_m,0.001` | 0.001 | **0.6990206751** |

An **81 % overestimate of community growth**, from one missing row.

### How the overlays fix it, inside the CSV format

`uptake_limit = 0` is legal (`MediumSpec` requires `>= 0`) and under merge semantics a zero row is
the *only* way a CSV can say "the environment does not supply this". Verified: applying
`{EX_glc__D_m: 20.0, EX_o2_m: 0.0}` drives `community.reactions.EX_o2_m.lower_bound` to `-0.0` and
removes the entry from `community.medium` (which lists only open uptakes).

So every shipped overlay carries:

1. an explicit **`EX_o2_m` row at MICOM's published 0.001** (§6), and
2. a **background closure block**: every metabolite in the union of the five bundled models' default
   media (37 metabolites) that the diet does not name, emitted at `0.0`.

Measured result — for all seven overlays, the set of uptakes still open after applying the overlay
that the overlay does **not** name is **empty**:

| overlay applied to `iML1515 + iYO844 + iHN637` | still-open-but-unnamed | `EX_o2_m` | community growth (h⁻¹) |
|---|---|---|---|
| `gut_overlay_agora_western.csv` | `[]` | 0.001 | 0.1407235535 |
| `gut_overlay_agora_high_fiber.csv` | `[]` | 0.001 | 0.139280484 |
| `gut_overlay_micom_western.csv` | `[]` | 0.001 | 0.1229627267 |
| `gut_overlay_vmh_high_fat_low_carb.csv` | `[]` | 0.001 | 0.0007845854082 |
| `gut_overlay_vmh_high_fiber.csv` | `[]` | 0.001 | 0.0009282927781 |
| `gut_overlay_vmh_high_fat_low_carb_x100.csv` | `[]` | 0.001 | 0.07187746887 |
| `gut_overlay_vmh_high_fiber_x100.csv` | `[]` | 0.001 | 0.08471492087 |
| *no `--medium`* (MICOM default) | 29 entries incl. `EX_o2_m = 999999.0` | 999999.0 | 0.7847991178 |

Isolating the oxygen term on the AGORA western overlay: 0.1407235535 anoxic vs 0.1558908653 with the
row deleted (O₂ inherited at 999999) — **+10.8 %**. Smaller than the 81 % seen with the glucose-only
preset because this overlay is carbon-rich, but the same defect.

**This still leaves a code-level gap** — see §9. A closure block is pool-specific by construction: it
can only close metabolites that *these five models* leave open. Point CMIG at a different model pool
and a metabolite that pool leaves open but this one does not will silently re-open. Only exact-medium
semantics in the code fix that generally.

---

## 1. Audit of the two pre-existing presets: **not defensible**

```
$ cat medium_presets/western_diet.csv        $ cat medium_presets/high_fiber.csv
exchange_id,uptake_limit                     exchange_id,uptake_limit
EX_glc__D_m,20.0                             EX_glc__D_m,3.0
```

That is the entire file in both cases.

1. **One metabolite.** No fibre, no nitrogen, no micronutrients, no oxygen specification.
   `high_fiber.csv` contains no fibre. The names assert something the contents do not support, which
   is worse than shipping no preset at all.
2. **No provenance.** The old README called them a "seed" for "정성 비교용" and said outright they are
   "정량 식이 모델 아님". No source is cited and none exists.
3. **~134× the published bound.** AGORA Supplementary Table 12 (§2, S-AGORA) publishes D-glucose
   directly in mmol gDW⁻¹ h⁻¹: Western **0.14898579**, high fibre **0.03947368**. Therefore
   `20.0 / 0.14898579 = 134.24×` and `3.0 / 0.03947368 = 76.00×`. The internal ratio is also wrong:
   20/3 = 6.667 against AGORA's 0.14898579/0.03947368 = **3.774**.
4. **`EX_glc__D_m` is absent from `iAF987`** — measured 0/5 → 4/5 coverage. For that member both
   presets are a no-op and CMIG strict mode rejects the run (already reported in round 2).
5. **No background closure** — hence the 81 % oxygen artefact in §0.

Kept (not deleted) because `tests/test_medium_spec.py` uses them as a "changing the medium changes
the answer" smoke fixture. Both READMEs now say they must not be cited as diets.

---

## 2. Sources actually retrieved

Pagination verified against PubMed `esummary` for every journal citation.

| # | Source | DOI / URL | Exact artefact used | Units **as printed** |
|---|---|---|---|---|
| **S-AGORA** | Magnúsdóttir S, Heinken A, Kutt L, *et al.* **Generation of genome-scale metabolic reconstructions for 773 members of the human gut microbiota.** *Nat Biotechnol* 2017;35(1):81–89 | `10.1038/nbt.3703` | **Supplementary Table 12**, supplementary PDF `41587_2017_BFnbt3703_MOESM2_ESM.pdf` (SHA-256 `82ab5d029f57a69c009c3da6be4f6245bc055f8d1cf7540effbc47ff51581fc0`), pages 29–33, 164 metabolite rows. Transcribed to `sources/agora_supp_table12.csv`. **Title as printed: "Uptake rates (mmol gDW⁻¹ h⁻¹) for dietary compounds implemented to simulate Western and high fiber diet."** | **mmol gDW⁻¹ h⁻¹** — already CMIG's unit |
| S3 | Diener C, Gibbons SM, Resendis-Antonio O. **MICOM: Metagenome-Scale Modeling To Infer Metabolic Interactions in the Gut Microbiota.** *mSystems* 2020;5(1):e00606-19 | `10.1128/mSystems.00606-19` | quoted: "To account for uptake in the small intestine, we reduced all import fluxes for metabolites commonly absorbed in the small intestine **by a factor of 10**." Also "~200 g" community biomass, "~2 pg" cell dry weight, fluxes < 1e-6 set to zero | mmol/[gDW·h] |
| S4 | `micom-dev/paper` `data/western_diet.csv`, mirrored as `sources/micom_paper_western_diet.csv` | github.com/micom-dev/paper | 167 rows, columns `reaction, flux, dilution`. `flux` **is** S-AGORA's Western column (rounded); `dilution` is the per-reaction small-intestinal factor `micom.workflows.build_models` multiplies by — 0.1 for 140 rows, 1.0 for 29 (the polysaccharides, not absorbed upstream), **0.001 for `o2`** | mmol gDW⁻¹ h⁻¹ / dimensionless |
| S5 | `micom-dev/media` `data/carveme_skeleton.csv` (126 rows; identical to the published `media/western_diet_gut_carveme.qza`), mirrored as `sources/carveme_skeleton.csv` | github.com/micom-dev/media | **every** number in `gut_overlay_micom_western.csv`, verbatim; the inorganic block of the VMH overlays. Verified to be S-AGORA Table 12 Western × S4 dilution in BiGG ids (glucose 0.14898579 × 0.1 = 0.0148986) | mmol gDW⁻¹ h⁻¹ |
| S6 | `micom-dev/media` recipes `vmh_high_fiber.ipynb`, `vmh_high_fat_low_carb_agora.ipynb`, `agora.ipynb`, `README.md` | github.com/micom-dev/media | the "commonly absorbed" operationalisation (= has an exchange in Recon3D); the 1e-4 VMH truncation floor; the anaerobic-O₂ intent ("deplete oxygen since the lower gut is mostly anaerobic", "a minuscule amount of oxygen") | mmol/[gDW·h] |
| S1 | Noronha A, Modamio J, Jarosz Y, *et al.* **The Virtual Metabolic Human database: integrating human and gut microbiome metabolism with nutrition and disease.** *Nucleic Acids Res* 2019;47(D1):D614–D624 | `10.1093/nar/gky992` | quoted: "The molecular composition of a diet can be downloaded in grams per person (70 kg) per day or as a flux rate (**in millimoles per person per day**)." | mmol person⁻¹ day⁻¹ |
| S2 | VMH diet-designer exports, mirrored from `micom-dev/media` `data/` | vmh.life | `vmh_eu_average.tsv`, `vmh_high_fat_low_carb.tsv`, `vmh_high_fiber.tsv` — 91 rows each, columns `Reaction`, `Flux Value` | mmol person⁻¹ day⁻¹ (S1) |
| S7 | Sender R, Fuchs S, Milo R. **Revised Estimates for the Number of Human and Bacteria Cells in the Body.** *PLoS Biol* 2016;14(8):e1002533 | `10.1371/journal.pbio.1002533` | quoted: "3.8·10¹³ bacteria in the colon"; "an average mass of a gut bacterium of about 5 pg (wet weight, corresponding to a **dry weight of 1–2 pg**)"; "the total **dry weight of bacteria in the body is about 50–100 g**"; colon content 0.4 L | g / pg |
| S8 | Espey MG. **Role of oxygen gradients in shaping redox relationships between the human intestine and its microbiota.** *Free Radic Biol Med* 2013;55:130–140 (PMID 23127782) | `10.1016/j.freeradbiomed.2012.10.554` | intestinal oxygen gradients "plunge to near anoxia at the luminal midpoint" → the basis for the trace-O₂ term | — |
| S9 | Recon3D (`/Users/jaeyongryu/orca/CMIG/data/gems/Recon3D.xml`, BiGG Models) | `bigg.ucsd.edu/static/models/Recon3D.xml.gz` | 1560 exchange reactions → 1560 metabolite ids, mirrored as `sources/recon3d_host_absorbed.txt` | — |
| S10 | Magnúsdóttir S, Heinken A, Fleming RMT, Thiele I. **Reply to "Challenges in modeling the human gut microbiome".** *Nat Biotechnol* 2018;36(8):686–691 (PMID 30080835) | `10.1038/nbt.4212` | cited by S5's README as the origin of the western-diet composition. **확인 필요 (UNVERIFIED)** — paywalled, fetch refused (303 → idp.nature.com). Superseded in practice: the values were traced to S-AGORA Table 12 instead, which *was* retrieved | — |
| S11 | Tramontano M, Andrejev S, Pruteanu M, *et al.* **Nutritional preferences of human gut bacteria reveal their metabolic idiosyncrasies.** *Nat Microbiol* 2018;3(4):514–522 | `10.1038/s41564-018-0123-9` | **retrieved and deliberately not used**: GMM and 15 defined media are *in vitro* recipes in g L⁻¹ for 96 strains; converting to a colonic per-gDW flux needs a further unsourced dilution-rate assumption | g L⁻¹ |
| — | Cummings JH, *et al.* **Short chain fatty acids in human large intestine, portal, hepatic and venous blood.** *Gut* 1987;28(10):1221–1227 | `10.1136/gut.28.10.1221` | retrieved; gives *concentrations* (caecum 131 ± 9 mmol/kg), not production rates, so **not used**. The widely quoted "400–600 mmol SCFA/day" could not be traced to a primary source in this session and was dropped rather than mis-cited | mmol/kg |

### The AGORA transcription is machine-verified

Transcribing 164 rows from a PDF is a data-entry risk, so it is cross-checked rather than trusted.
S4 is MICOM's independently published copy of the same Western column. Of the 164 rows, **162 can be
cross-checked and all agree**; agreement is asserted at 2 % relative tolerance because the two
representations round differently in both directions (MICOM: `1.567e-05` → `1.57e-05`; the PDF prints
`0.00000007` where MICOM carries `7.05e-08`). A single-digit transcription error moves a value by
≥10 % and would be caught. Enforced by
`tests/test_medium_presets_gut.py::test_agora_table12_transcription_matches_micoms_copy`. Row counts
also match the table's own structure: 20 sugar + 24 fiber + 12 fat + 20 protein + 88 "minerals,
vitamins, other" = 164. Only `no3` and `adocbl` have no cross-check (absent from / renamed in S4).

### What ships inside `micom` 0.39.0 (checked directly)

`micom` 0.39.0 bundles exactly **one** medium, `micom/data/artifacts/medium.qza`, a QIIME 2 artifact
whose `data/medium.csv` is four rows:

```
reaction,flux,metabolite
EX_glc__D_m,10.0,glc__D_m
EX_nh4_m,4.362240000000003,nh4_m
EX_o2_m,18.579253333333327,o2_m
EX_pi_m,2.942959999999998,pi_m
```

Artifact provenance: created 2020-01-09 by `q2-micom` 0.1.0 / qiime2 2020.1.0.dev0, action type
`import`. It is a **minimal aerobic medium for the packaged `e_coli_core` test models** — `EX_o2_m` at
18.6 is the opposite of a colon. It is **not** a gut diet.

**CMIG can consume it** after renaming two columns (`reaction`→`exchange_id`, `flux`→`uptake_limit`);
the ids are already `EX_*_m` and the values are already unsigned magnitudes in mmol gDW⁻¹ h⁻¹.
`micom.qiime_formats.load_qiime_medium` reads the artifact directly. All of micom's *real* gut media
live in the separate `micom-dev/media` repository, **not** in the installed package — which is why
they are mirrored into `sources/`.

---

## 3. Units — two derivations, deliberately

### 3.1 AGORA family — no conversion at all

S-AGORA Table 12 is published **in mmol gDW⁻¹ h⁻¹** (the unit is in the table's own title), for both
the Western and the high-fibre arm. The only operation is S3's small-intestinal dilution, taken
per-reaction from S4:

```
v_ex [mmol gDW⁻¹ h⁻¹] = published_table12_value × micom_dilution
```

Worked examples (asserted against the shipped CSVs by
`test_worked_examples_reproduce_shipped_values`):

| metabolite | Table 12 Western | Table 12 high fibre | S4 dilution | shipped western | shipped high fibre |
|---|---|---|---|---|---|
| D-glucose `glc_D` | 0.14898579 | 0.03947368 | 0.1 | `0.014898579` | `0.003947368` |
| Raffinose `raffin` | 0.00470194 | 0.10416667 | 1.0 | `0.00470194` | `0.10416667` |
| L-alanine `ala_L` | 1 | 1 | 0.1 | `0.1` | `0.1` |

No biomass assumption, no hours-per-day assumption, no absorption assumption beyond S3's own. This
family is therefore the **primary** one and the reference for everything else.

### 3.2 VMH family — the conversion, and why it is kept

S1/S2 publish **mmol person⁻¹ day⁻¹**, so a conversion is unavoidable:

```
v_ex [mmol gDW⁻¹ h⁻¹] = D [mmol person⁻¹ day⁻¹] × f_colon / (B_gDW × HOURS_PER_DAY)
```

| constant | value | status |
|---|---|---|
| `HOURS_PER_DAY` | 24 | definition |
| `B_gDW` | **57 gDW** | S7 + **assumption**: 3.8·10¹³ colonic bacteria × 1.5 pg dry weight. **1.5 pg is my choice**, the midpoint of S7's cited 1–2 pg; the range gives 38–76 gDW, i.e. **±33 % on every VMH value**. Cross-checks against S7's independent "50–100 g total bacterial dry weight". |
| `f_colon` | **0.1** if the metabolite has an exchange in Recon3D, else **1.0** | factor of 10 from S3; the operationalisation from S6 + S9 |
| `VMH_TRUNCATION_FLOOR` | 1e-4, substituted for a printed `0` **before** conversion | S6 — the VMH export truncates to four decimals |

Worked examples, `B_gDW × 24 = 1368` (all five reproduce the shipped CSV byte-for-byte):

| metabolite | VMH row | D (mmol person⁻¹ day⁻¹) | Recon3D? | f_colon | arithmetic | shipped |
|---|---|---|---|---|---|---|
| glucose | `EX_glc_D[e]` | 120.210995032636 | yes | 0.1 | 12.0210995032636 ÷ 1368 | `0.008787353438058188` |
| water | `EX_h2o[e]` | 181671.336776337 | yes | 0.1 | 18167.1336776337 ÷ 1368 | `13.280068477802413` |
| ethanol | `EX_etoh[e]` | 22.792195952106 | yes | 0.1 | 2.2792195952106 ÷ 1368 | `0.0016660961953293859` |
| calcium | `EX_ca2[e]` | 33.0201107839713 | **no** | 1.0 | 33.0201107839713 ÷ 1368 | `0.024137507883019955` |
| folate | `EX_fol[e]` | 0.000272645010836998 | yes | 0.1 | 2.72645010836998e-05 ÷ 1368 | `1.993019085065775e-08` |

Calcium is included as an example of the rule **failing**: Recon3D has no `EX_ca2_e`, `EX_cl_e` or
`EX_mg2_e`, so Ca²⁺/Cl⁻/Mg²⁺ are treated as reaching the colon undiluted, which is physiologically
wrong by roughly 10×. Inherited from S3/S6's rule, not introduced here; it is why `EX_cl_m` is the
largest non-water entry in every VMH overlay.

### 3.3 The two derivations cross-check each other — and disagree by 1.5×

| route | glucose bound (mmol gDW⁻¹ h⁻¹) |
|---|---|
| S-AGORA Table 12 Western × 0.1 (published, no conversion) | **0.0148986** |
| VMH EU-average 135.580350130082 mmol person⁻¹ day⁻¹ × 0.1 / (57 × 24) | **0.00991084** |

Ratio **1.503**. Reconciliation: inverting the AGORA number gives the biomass it implies —
`135.58 × 0.1 / 0.0148986 / 24 = 37.92 gDW`, i.e. **3.8·10¹³ cells × 1.0 pg**, exactly the *lower*
end of S7's cited 1–2 pg. So the published AGORA bound and this conversion agree to within the stated
uncertainty of the one assumed constant, and the residual disagreement *is* the 1.5 pg vs 1.0 pg
choice. Caveat, stated because it weakens the agreement: AGORA assigns the same 0.14898579 to eight
different monosaccharides (`fru`, `glc_D`, `gal`, `man`, `mnl`, `fuc_L`, `glcn`, `rmn`), so it is a
lumped sugar pool rather than a per-metabolite glucose figure, and the numerical coincidence could be
partly that.

### 3.4 A units bug in micom's own repository — flagged, not copied

`micom-dev/media` is internally inconsistent about the day→hour step:

* `recipes/vmh_high_fat_low_carb_agora.ipynb` states "Flux is in mmol/human/day. This has to be
  adjusted to 1 hour" and does `medium.flux = medium.flux / 24`.
* `recipes/vmh_high_fiber.ipynb` does **not**. Its shipped artifact
  `media/vmh_high_fiber_agora.qza` therefore carries `etoh = 4.5584391904212`
  (= 22.792195952106 × 0.2, dilution only) and `h2o = 36334.2673552674`, labelled mmol gDW⁻¹ h⁻¹.
  36 334 mmol water gDW⁻¹ h⁻¹ = 654 g gDW⁻¹ h⁻¹ — physically impossible, ~2700× the value here.
  Verified by extracting the `.qza` and comparing against the raw TSV.

Neither micom recipe divides by a biomass at all: dividing only by 24 silently asserts `B = 1 gDW`
for the whole colonic community. `test_no_unconverted_source_value_survives` and
`test_magnitude_band` exist to stop this class of error entering a CMIG overlay.

---

## 4. Order of magnitude, and the sanity check against conventional FBA

The AGORA family needs no defence on scale — it *is* the published scale. The VMH family lands at
glucose 0.0088, i.e. ~1000× below the conventional 10 mmol glucose gDW⁻¹ h⁻¹ for *E. coli*. That gap
was investigated rather than shipped blind:

1. **It reproduces the published standard** to within 1.5× (§3.3).
2. **Compare totals, not single metabolites.** Summing carbon over the shipped overlays (carbon
   counts from the pool's own metabolite formulas):

   | overlay | total carbon influx (mmol C gDW⁻¹ h⁻¹) |
   |---|---|
   | `gut_overlay_agora_western.csv` | 76.61 |
   | `gut_overlay_agora_high_fiber.csv` | 74.54 |
   | `gut_overlay_micom_western.csv` | 61.85 |
   | `gut_overlay_vmh_high_fiber.csv` | 0.814 |
   | `gut_overlay_vmh_high_fiber_x100.csv` | 81.43 |
   | *E. coli* reference (10 mmol glucose) | 60 |

   The AGORA overlays sit at the conventional scale; the VMH overlays at literature scale are ~75×
   below it, and ×100 puts them back on it.
3. **The maintenance floor is the binding constraint** for single-model use. Measured from the SBML,
   `ATPM` lower bounds: iHN637 0.45, iAF987 0.81, iSFV_1184 3.15, iML1515 6.86, iYO844 **9.0 (also
   the upper bound — fixed)**. ~1 mmol C gDW⁻¹ h⁻¹ cannot pay a 6.86 or 9.0 mmol ATP gDW⁻¹ h⁻¹ bill.

---

## 5. `*_x100` — what it is and what it is not

`*_x100.csv` applies **one uniform dimensionless factor of 100 to the dietary rows only**. It
preserves every dietary ratio (so the contrast is untouched) and it explicitly **does not scale** the
`micom_anaerobic_o2` row or the `background_closure` rows — those are environmental boundary
conditions, and rescaling a diet does not make the colon less anoxic. Asserted by
`test_x100_variants_rescale_only_the_dietary_rows` and `test_oxygen_is_a_trace_term`.

It exists only for the VMH family. Measured, single-model `cobra` `optimize()` with the overlay as
the whole medium (`exact=True`):

| medium | iAF987 | iHN637 | iML1515 | iSFV_1184 | iYO844 |
|---|---|---|---|---|---|
| VMH high fibre, literature scale | infeasible | infeasible | infeasible | infeasible | infeasible |
| MICOM's own published gut medium | infeasible | 0.0 | infeasible | 0.0 | infeasible |
| VMH high fibre × 10 | infeasible | 2.2e-4 | infeasible | infeasible | infeasible |
| VMH high fibre × 100 | infeasible | 0.00223 | 0.0350 | 0.1622 | 0.00820 |

**It is an engineering rescale, not a literature value**, and the factor is in the filename so it
cannot be mistaken for one. The AGORA overlays get **no** `_x100`: at their published scale a
3-member community already grows at 0.14 h⁻¹, and ×100 would put it at 5.15 h⁻¹, which is not
biology.

`iAF987` is infeasible on every defined medium in the single-model path for an unrelated reason: its
SBML *forces* uptake — `EX_ac_e` bounds `[-8.88, -6.84]` and `EX_fe3_e` bounds `[-67.37, -49.21]`.
Any medium offering less acetate or Fe³⁺ makes `model.medium = …` raise or the LP infeasible. Not
fixable from a medium file.

---

## 6. Composition of the shipped overlays

| overlay | rows | source of the numbers |
|---|---|---|
| `gut_overlay_agora_western.csv` | 133 | S-AGORA Table 12 Western × S4 dilution, + O₂ + `ni2` + closure |
| `gut_overlay_agora_high_fiber.csv` | 133 | S-AGORA Table 12 high fibre × S4 dilution, + O₂ + `ni2` + closure |
| `gut_overlay_vmh_high_fat_low_carb.csv` (+ `_x100`) | 80 | VMH "High fat, low carb" via §3.2, + inorganic block + O₂ + `ni2` + closure |
| `gut_overlay_vmh_high_fiber.csv` (+ `_x100`) | 80 | VMH "High fiber" via §3.2, same |
| `gut_overlay_micom_western.csv` | 131 | **S5 verbatim** (122 of its 126 rows reach the pool) + O₂ + closure. Keeps S5's `EX_no2_m,0.1`. |

Origins are machine-readable in `provenance_rows.csv`: `agora_table12`, `vmh_diet`, `micom_western`,
`micom_western_inorganic`, `micom_anaerobic_o2`, `assumption_trace_micronutrient`,
`background_closure`.

### The oxygen term

`EX_o2_m = 0.001`, from S4 (`EX_o2_e`, flux 1 × dilution 0.001) and S5 (`o2_m`, flux 0.001), with S6
describing the intent and S8 supplying the physiology. S-AGORA Table 12 has **no oxygen row at all**
— which is precisely how the leak in §0 arises for anyone building a medium straight from it. Left at
a trace rather than hard zero so models with an obligate O₂ sink are not made hard-infeasible.

### The inorganic block (VMH family only, 6 rows) and the judgement calls

VMH's food table lists 91 food-derived metabolites but omits inorganic micronutrients that every
defined bacterial medium contains and does not model the colonic gas phase. Rather than invent
values, **every carbon-free component of S5 the VMH diet does not cover** is imported at S5's own
published flux: `cobalt2 0.1, h 0.1, h2 0.1, h2s 0.1, mobd 0.1, so4 0.1` (O₂ is handled separately).
The carbon-free test is objective and leaves every macronutrient — the whole contrast —
diet-derived.

* **`no2` / `no3` / `tsul` are excluded** from every overlay except the verbatim MICOM one. A
  **modelling choice, not a sourced value**: at S5's 0.1 mmol gDW⁻¹ h⁻¹ nitrite alone is >10× the
  diet's glucose supply and would open an anaerobic-respiration route that outcompetes the
  fermentation these overlays exist to study. `gut_overlay_micom_western.csv` keeps S5's value
  verbatim so the effect can be measured.
* **`EX_ni2_m = 0.1` is an ASSUMPTION with no source.** Ni²⁺ is a urease/[NiFe]-hydrogenase cofactor
  present in every defined bacterial medium; VMH does not track it and Table 12 omits it. The flux is
  the one S5 gives its other trace metals. Measured: without nickel,
  `micom.media.complete_medium` names `EX_ni2_e` as a required addition for iHN637, iML1515 and
  iSFV_1184. Tagged `assumption_trace_micronutrient` so it can be found and removed.
* **Methanol.** Table 12 and S5 both publish `meoh` at 10 mmol gDW⁻¹ h⁻¹ — ~670× their own glucose
  bound, and the single largest carbon term in the AGORA overlays. Transcribed faithfully and
  flagged: it is not a plausible colonic methanol supply, and it is a property of the *published*
  diet, not of this build.

### Fibre coverage — the contrast this pool cannot deliver

AGORA Table 12 marks **24 rows as fibre**. Measured against the five bundled models:

```
1/24 have an exchange in ANY bundled model
    raffin  ->  EX_raffin_m   ['iSFV_1184', 'iYO844']
unreachable: amylopect900, amylose300, arabinan101, arabinogal, arabinoxyl, bglc, cellul,
  dextran40, galmannan, glcmannan, homogal, inulin, kestopt, levan1000, lichn, lmn30, pect,
  pullulan1200, rhamnogalurI, rhamnogalurII, starch1200, xylan, xyluglc
per-model: iAF987=0/24, iHN637=0/24, iML1515=0/24, iSFV_1184=1/24, iYO844=1/24
```

`strch1` (Starch, 0.257 Western / 0.068 high fibre) is also dropped — no bundled model has an
`EX_strch1` exchange. `iYO844` has `EX_starch_e` ("Starch C12H20O10") and `iML1515`/`iSFV_1184` have
`EX_14glucan_e` ("1,4-alpha-D-glucan C36H62O31"), but the degree of polymerisation of AGORA's
`strch1` is not verifiable from anything in this repository, so **no alias was invented**.

**Conclusion: with this model pool the high-fibre overlay is not a fibre-degradation experiment.**
27 of the 133 AGORA rows differ between the two arms, and the surviving differences are:

* mono/disaccharides and pentoses: **0.265×** in high fibre (i.e. the western arm has 3.8× more),
* fats: **0.500×** in high fibre,
* raffinose: **22.15×** in high fibre — the only fibre that reaches the pool,
* protein and the flat "other" block: **identical**.

Carbon accounting makes the consequence explicit:

| overlay | other (flat) | protein | sugar | fat | fibre | total |
|---|---|---|---|---|---|---|
| `gut_overlay_agora_western.csv` | 66.30 | 4.05 | 3.31 | 2.87 | 0.085 | 76.61 |
| `gut_overlay_agora_high_fiber.csv` | 66.30 | 4.05 | 0.88 | 1.44 | 1.875 | 74.54 |

**86.5 % of the carbon comes from AGORA's flat "minerals, vitamins, other" block (0.1 each after
dilution), which is byte-identical in both diets.** The diet-specific part is 6.26 vs 4.19 mmol C
gDW⁻¹ h⁻¹ — 8.2 % and 5.6 % of the total. That is why community growth differs by only 1.0 %
(0.1407 vs 0.1393). It is a property of the *published AGORA diet definition*, not of this build, and
it means **the AGORA pair is a reference medium, not a sensitive contrast**. The VMH pair, which has
no flat placeholder block, gives an 18 % growth difference (0.000785 vs 0.000928 at literature scale,
0.0719 vs 0.0847 at ×100) and is the better choice for a scenario run.

### What was dropped

`--report` prints the full list with values. AGORA family: 40 of 164 rows (the 23 unreachable fibres,
`strch1`, five long-chain/polyunsaturated lipids and sterols, and eleven cofactors/quinones —
`12dgr180`, `2dmmq8`, `3mop`, `lanost`, `mqn7`, `mqn8`, `ncam`, `pime`, `pydx5p`, `q8`, `sheme`).
VMH family: 31 of 91 (fat-soluble and one-carbon vitamins, long-chain/polyunsaturated fatty acids and
sterols, iodine, xylitol, and the fibre `strch1`/`starch1200`/`cellul`).

The pool itself is the deeper limitation: only *E. coli* is a common gut resident. *B. subtilis* is
soil/transient, *Geobacter metallireducens* a sediment metal reducer, *Shigella flexneri* a pathogen.
A defensible medium on an indefensible gut community is still a methods demonstration.

---

## 7. Coverage per bundled model

Entries whose metabolite has an exchange reaction in each model, matched exactly as
`cmig.core.medium_spec.translate_medium_for_model` does (so `EX_glc__D_m` counts against
`iML1515`'s `EX_glc__D_e`). Regenerate with `--report`.

| overlay | rows | min | max | iAF987 | iHN637 | iML1515 | iSFV_1184 | iYO844 |
|---|---|---|---|---|---|---|---|---|
| `western_diet.csv` (legacy) | 1 | 20 | 20 | **0** | 1 | 1 | 1 | 1 |
| `high_fiber.csv` (legacy) | 1 | 3 | 3 | **0** | 1 | 1 | 1 | 1 |
| `gut_overlay_agora_western.csv` | 133 | 0 | 1.0 | 45 | 59 | 120 | 124 | 94 |
| `gut_overlay_agora_high_fiber.csv` | 133 | 0 | 1.0 | 45 | 59 | 120 | 124 | 94 |
| `gut_overlay_vmh_high_fat_low_carb.csv` | 80 | 0 | 11.6 | 40 | 45 | 76 | 75 | 54 |
| `gut_overlay_vmh_high_fat_low_carb_x100.csv` | 80 | 0 | 1159 | 40 | 45 | 76 | 75 | 54 |
| `gut_overlay_vmh_high_fiber.csv` | 80 | 0 | 13.3 | 40 | 45 | 76 | 75 | 54 |
| `gut_overlay_vmh_high_fiber_x100.csv` | 80 | 0 | 1328 | 40 | 45 | 76 | 75 | 54 |
| `gut_overlay_micom_western.csv` | 131 | 0 | 10 | 45 | 60 | 118 | 122 | 97 |

`min = 0` is the background closure block, by design. Every entry reaches at least one bundled model
(`test_every_exchange_exists_in_a_bundled_model`), so the overlays are **scoped to this pool**; the
dropped rows are recoverable from `sources/` for anyone using AGORA models.

### Namespace

All overlays use `EX_<met>_m` only — one suffix per file, one id per metabolite, so the round-5
exit-2 alias refusal can never fire (`test_no_conflicting_namespace_aliases`). The AGORA/VMH→BiGG
bridge is `bigg_id.replace("__","_") == source_id`, which is micom's own bridge (S6), plus one
explicit alias (`H2` → `h2`); the builder raises if the collapse is not injective over the pool's 520
exchange metabolites (it currently is — 0 collisions).

---

## 8. Divergence from the independent Codex derivation

Recorded because two derivations were produced independently and the coordinator asked for the
divergence to be named rather than smoothed over.

| item | this build | Codex | agreement |
|---|---|---|---|
| AGORA supplementary PDF SHA-256 | `82ab5d029f57a69c…51581fc0` | `82ab5d02…81fc0` | **identical artefact** |
| Table 12 rows / pages / units | 164 / pp. 29–33 / mmol gDW⁻¹ h⁻¹ in the title | 164 / pp. 29–33 / units in the title | **identical** |
| Western D-glucose bound | 0.14898579 | 0.14898579 | **identical** |
| legacy `western_diet.csv` ratio | 20.0 / 0.14898579 = **134.24×** | ~134× | **identical** |
| western overlay construction | Table 12 × S4 per-reaction `dilution`, as `micom.workflows.build_models` does | same | **identical method** |
| diet rows reaching the pool | 122 (+11 O₂/`ni2`/closure = 133 shipped) | 122 rows, 122/122 coverage | **identical** |
| high-fibre arm | also built, from Table 12's second column | not reported | this build adds it |
| fibre coverage | 1/24 (`raffin`, in iSFV_1184 + iYO844) | 1/24 (raffinose) | **identical** |
| VMH route | additionally converted; glucose 0.00991 | notes the VMH paper's own warning that its values ignore GI absorption | **1.503× divergence, reconciled in §3.3** |
| background closure / O₂ | closure block + explicit O₂ row in every overlay | flagged the leak | this build implements the fix |
| naming | `gut_overlay_*` | "overlays, not exact colonic media" | **agreed** |

The one substantive divergence is the 1.503× on glucose, and it is **not** a disagreement about
method — it is the value of one assumed constant (`B_gDW`), which is why that constant carries an
explicit ±33 % band and why the AGORA family, which needs no such constant, is the primary one.
Codex's point about the VMH paper warning that its values do not account for GI-tract absorption is
also why `f_colon` (§3.2) exists at all; it is applied here, from S3.

---

## 9. Code finding handed back (this track may not change `cmig/core/medium*.py`)

**A CSV cannot express exact-medium semantics in general — only for a known model pool.**

`apply_medium_checked` → `apply_medium_translated(..., exact=False)` merges. The closure block above
works, but it can only zero metabolites that *these five* models leave open. Consequences:

1. **Pool-dependence.** With a different model pool, any metabolite that pool leaves open and this
   pool does not will silently re-open — including oxygen, if a model exposes `EX_o2_e` with a
   different default. The overlay's guarantee is not portable.
2. **Bookkeeping rows.** 9–14 rows of every shipped overlay exist only to close a default.
3. **`medium_checksum` hashes them**, so two runs that differ only in which pool-specific zeros were
   needed get different `run_hash` values for the same scientific medium.

Smallest sufficient change:

* an `--exact-medium` flag on the subcommands that accept `--medium`, routing to
  `apply_medium_translated(..., exact=True)` — which **already exists** and is already used by
  `strain-growth`'s community-offer path (`_cmd_strain_growth`). No new semantics to design.
* the manifest must record which mode was used, because the two give different answers on identical
  input — exactly the class of defect round 5 closed for `MEDIUM_POLICY`. A
  `medium_application_mode` field alongside `medium_checksum` would do it.
* until that exists, **CMIG's docs must state that `--medium` is an overlay**, because a user reading
  "medium" reasonably expects replacement. `README.md` and `medium_presets/README.md` now say so.

Not implemented here: the brief forbids changes to `cmig/core/medium*.py`, and adding a CLI flag
without the manifest field would create precisely the untracked-semantics problem round 5 was about.

---

## 10. What a reviewer could challenge

1. **`B_gDW = 57`** (VMH family only) — the 1.5 pg/cell midpoint is mine; S7's 1–2 pg range is ±33 %.
   The AGORA family is free of this.
2. **`f_colon` is binary (0.1/1.0) keyed on "Recon3D has an exchange"** — S3/S6's rule, and it
   demonstrably mis-assigns Ca²⁺, Cl⁻, Mg²⁺ (§3.2).
3. **The AGORA table was transcribed from a PDF by hand.** Machine-checked against MICOM's copy at
   2 % on 162/164 rows (§2), but 2 % is the tightest the two roundings support, and `no3` and
   `adocbl` have no cross-check at all.
4. **AGORA's flat "other" block supplies 86.5 % of the carbon** and is identical in both arms, so the
   AGORA contrast can only move community growth ~1 % (§6). Anyone expecting a large diet effect from
   it will be disappointed, correctly.
5. **`meoh = 10`** in the published diets is not plausible colonic biology (§6).
6. **`EX_ni2_m = 0.1`** has no source at all.
7. **The `no2`/`no3`/`tsul` exclusion** is a judgement, not a measurement.
8. **`_x100`** is an engineering factor, not physiology.
9. **The dropped fibre** makes "high fibre" a misleading label for what this pool can metabolise
   (§6) — 1/24 fibre entries reachable, and the fibre that does reach it is raffinose alone.
10. **The background closure is pool-specific** (§9) and is a workaround for missing exact-medium
    semantics, not a substitute for them.
11. **The model pool is not a gut community** (§6).
12. **Uptake bounds are upper limits, not supplies.** FBA says "no more than this"; it does not force
    consumption, and every overlay is a well-mixed steady-state abstraction with no proximal/distal
    or fed/fasted structure.
13. **S10 (`nbt.4212`) was never opened** — paywalled, fetch refused. Its role was superseded by
    retrieving S-AGORA Table 12 directly, but S5's attribution to it remains quoted, not verified.
14. **VMH's own numbers were not re-downloaded** from vmh.life; the TSVs are mirrored from
    `micom-dev/media`. The units statement is from the peer-reviewed VMH paper (S1) but the
    individual food→metabolite conversions inside the VMH designer were **not** re-derived.
    확인 필요 (UNVERIFIED).
