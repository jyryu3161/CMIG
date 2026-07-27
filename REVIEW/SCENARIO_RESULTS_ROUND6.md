# Round-6 gut-medium scenario results

All numbers below were observed by running CMIG at `round6/integration` (`ac1adf3`)
with a licensed Gurobi. 34 run directories under `runs/`. Nothing here is estimated.

**Read the limitations section before quoting any of this.** The bundled pool is not a
gut community, and the "high fibre" arm does not vary fibre.

## 1. Community growth per medium

3-member pool `iHN637 + iML1515 + iYO844`, equal abundance, `tradeoff_f = 0.5`.
Growth is abundance-weighted; acetate is `profile.parquet` `net_flux`.

| medium | growth (h⁻¹) | acetate (mmol gDW⁻¹ h⁻¹) |
|---|---:|---:|
| `gut_overlay_agora_western` | 0.140724 | 4.066 |
| `gut_overlay_agora_high_fiber` | 0.139280 | 2.992 |
| `gut_overlay_micom_western` | 0.122963 | 2.258 |
| `gut_overlay_vmh_high_fiber_x100` | 0.084715 | 2.070 |
| `gut_overlay_vmh_high_fat_low_carb_x100` | 0.071877 | 5.208 |
| `gut_overlay_vmh_high_fiber` (unscaled) | 0.000928 | — |
| `gut_overlay_vmh_high_fat_low_carb` (unscaled) | 0.000785 | — |

Two things to take from this table.

**The AGORA contrast is 1.0 %, the VMH contrast is 17.9 %** — matching track M's
prediction from the composition alone, before any solve. AGORA western vs high-fibre
is 0.140724 vs 0.139280; VMH high-fibre vs high-fat-low-carb (×100) is 0.084715 vs
0.071877. The AGORA near-flatness is a property of the diet *definition* — 86.5 % of
its carbon sits in a "minerals, vitamins, other" block that is byte-identical in both
arms — not a biological finding. **Use VMH for contrast, AGORA as a reference point.**

**The unscaled VMH overlays barely grow at all** (≈0.0009 h⁻¹). The ×100 rescale is
not cosmetic; it is required for the VMH family to be usable at this pool size, and
that rescale is a documented assumption, not data.

## 2. Oxygen sensitivity — the important result is not what it looks like

Same medium, the `EX_o2_m` row deleted so oxygen returns to the MICOM default of
999999:

| medium | O₂ closed | O₂ open | growth inflation |
|---|---:|---:|---:|
| `agora_western` | 0.140724 | 0.155891 | **1.11×** |
| `vmh_high_fiber_x100` | 0.084715 | 0.084633 | 1.00× |
| `vmh_high_fat_low_carb_x100` | 0.071877 | 0.071840 | 1.00× |

On growth alone the leak looks minor here — and that is the trap. Compare acetate:

| medium | acetate, O₂ closed | acetate, O₂ open | change |
|---|---:|---:|---:|
| `agora_western` | 4.066 | 2.751 | **−32 %** |
| `vmh_high_fiber_x100` | 2.070 | 1.937 | −6 % |
| `vmh_high_fat_low_carb_x100` | 5.208 | 1.674 | **−68 %** |

**Closing oxygen barely moves growth but changes acetate output by up to 3×.** That is
biologically exactly what you would expect — with oxygen available the organisms
respire instead of fermenting, so short-chain fatty-acid output collapses — and it is
why the leak mattered so much: SCFA production is the question a gut study is usually
asking. A study reading growth rates would have seen almost nothing wrong. A study
reading SCFA would have been wrong by a factor of three.

Note the magnitude depends on how nutrient-limited the medium is. On the *old*
single-row glucose preset, track M measured an **81 %** growth overestimate from the
same leak. On these multi-nutrient overlays the carbon source is limiting, so the
growth effect shrinks to 0–11 % while the product profile still shifts sharply.

## 3. SCFA production — the medium changes the *ranking*, not just the magnitudes

`cmig search --target-preset scfa --multi-metric pareto`, rank-1 point of the
non-dominated front:

| medium | rank-1 consortium | acetate | front size |
|---|---|---:|---:|
| `agora_western` | **iML1515 + iYO844** | 6.832 | 10 |
| `agora_high_fiber` | **iML1515 + iYO844** | 6.398 | 10 |
| `micom_western` | **iHN637 + iML1515 + iYO844** | 8.603 | 10 |
| `vmh_high_fiber_x100` | **iHN637 + iML1515 + iYO844** | 21.617 | 10 |
| `vmh_high_fat_low_carb_x100` | **iHN637 + iML1515 + iYO844** | 11.483 | 7 |

**This is the scientifically interesting result of the round.** On the AGORA media the
best SCFA consortium is the 2-member `iML1515 + iYO844`; on the MICOM and VMH media it
is the 3-member consortium including `iHN637`. The medium does not merely rescale the
answer — it changes which combination wins. Any study that reports a "best
combination" without stating its medium is reporting an artifact of an unstated choice.

The front size also varies: the high-fat-low-carb medium supports only 7 non-dominated
points against 10 elsewhere, i.e. a narrower set of genuine trade-offs.

Within a medium, the front behaves as round 6 established: rank 1 is an acetate
specialist and lower-ranked points trade acetate for lactate/succinate (e.g.
`vmh_high_fiber_x100` rank 2: `ac 18.431, lac__D 0.721, lac__L 0.721, succ 0.542`).
Asking the same question with the default `normalized_weighted` metric would have
returned a single vertex and hidden the trade-off entirely.

## 4. Host scenario — a null, reported as a null

`cmig host-microbe-bigg` with Recon3D as host, `--host-objective BIOMASS_reaction`,
on three media. **All three failed, and failed honestly:**

```
community_growth=0  host_objective=0  host_status=solver_failed
analysis failed: artifacts were written to runs/host_vmh_hf_x100 but the scientific
solve did not succeed (exit 3); pass --allow-failed-run to exit 0 anyway
status: failed
warnings: ['biomass basis is validation-only; result is not publication-ready',
           'microbial community solve was not optimal (status=solver_failed)']
```

No number was published. Exit code 3, `status: failed`, the cause named, and the
override offered explicitly. This is the round-5/6 honesty machinery doing precisely
its job — before those rounds this path published `host_objective = 368` with
`status: ok` for a result the microbes provably did not affect.

**An open question this raises, and it is a real one:** the *standalone* community
solve on the same media succeeds (0.0847 h⁻¹ for `vmh_high_fiber_x100`), while the
community solve *inside* the host-coupling path returns 0. So the host path is
over-constrained relative to the standalone path on these closed-background overlays.
That needs investigation before the host scenario can be run on these media. It is
recorded here as a finding, not worked around.

Independently, track H measured that with a properly closed background the bundled
pool's effect on Recon3D growth is **−1.4e−13 — machine zero**, because the pool
delivers only acetate, ethanol and Fe²⁺ to a generic human cell model. So even were
the coupling to solve, the expected result on this pool is a null.

## 5. Limitations — these bound every number above

- **The bundled 5-member pool is not a gut community.** Only *E. coli* (`iML1515`) is a
  common gut resident. *B. subtilis* (`iYO844`) is soil/transient, *C. ljungdahlii*
  (`iHN637`) an acetogen, *Geobacter* (`iAF987`) a sediment metal-reducer, *Shigella*
  (`iSFV_1184`) a pathogen. Everything above is a methods demonstration on real
  genome-scale models. It is not gut biology, and the consortium rankings in §3 should
  not be read as claims about human gut communities.
- **The "high fibre" arm does not vary fibre.** Only **1 of 24** AGORA fibre entries
  (raffinose) has an exchange in any bundled model. What the AGORA contrast actually
  varies is sugars (0.265×) and fats (0.500×), with protein and the flat block
  identical. Calling it a fibre experiment would be false.
- **Recon3D is a generic single-cell human model**, not a gut epithelium, so host runs
  are `validation` basis and are labelled not-publication-ready by the tool itself.
- **The ×100 VMH rescale is an assumption**, as is the 1.5 pg/cell bacterial dry weight
  underlying the unit conversion (Sender et al. 2016 gives 1–2 pg; AGORA's own numbers
  imply 1.0 pg). The derivation carries a ±33 % band for that constant.
- Nothing here has been reproduced on a second solver. Gurobi only.

## 6. What a researcher should take from this

1. **State your medium.** It changes which consortium wins, not just by how much.
2. **Close oxygen explicitly** for a colonic simulation, and check your product
   profile rather than growth — growth can look fine while SCFA output is 3× wrong.
3. **Ask multi-metabolite questions with `--multi-metric pareto`.** The linear metrics
   collapse onto one vertex regardless of weighting.
4. **A real gut result needs a real gut pool** — AGORA-class residents, not these five.
   The mechanism is now demonstrated to work on a real human GEM; the biology is not.
