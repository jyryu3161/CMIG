# COMETS-Inspired dFBA And Spatial Dynamics Notes For CMIG

Source reviewed: local `COMETS.pdf` (146 pages). The relevant sections are
`Dynamic Flux Balance Analysis`, `Spatial structure and dynamics`, `Biomass
propagation`, `Nutrient propagation`, and the output/logging descriptions.

## Useful Concepts From COMETS

1. **dFBA loop**
   - Extracellular metabolite concentrations and biomass are dynamic variables.
   - At each time step, uptake bounds are derived from local extracellular
     concentration.
   - FBA is solved for each model.
   - Biomass and extracellular metabolites are advanced with the inferred
     growth and exchange fluxes.
   - This maps directly to CMIG's existing `cmig.core.dfba.simulate_dfba`.

2. **Uptake mapping**
   - COMETS supports linear, Monod/Michaelis-Menten, and pseudo-Monod exchange
     styles.
   - CMIG currently implements Michaelis-Menten uptake. This is a good default
     because it avoids adding a nonlinear ODE dependency while covering the most
     common concentration-to-uptake relationship.

3. **Spatial decomposition**
   - COMETS treats a 2D layout as grid boxes where each box is locally
     well-mixed.
   - Biomass and metabolites move between neighboring boxes by diffusion or more
     complex propagation models.
   - Full spatial community dFBA would require solving FBA at grid points and
     tracking biomass/media fields over time. That is a separate engine-scale
     feature, not a small extension.

4. **Source/sink and layout design**
   - COMETS workflows commonly use fixed media sources, sinks, refresh zones,
     and gradients.
   - This is useful to CMIG even without full spatial dFBA, because users can
     inspect plausible nutrient gradients before choosing medium/diet
     conditions or spatial hypotheses.

5. **Outputs**
   - Useful outputs are timecourse biomass, media concentration, exchange flux,
     and spatial images.
   - CMIG should keep these as machine-readable CSV/Parquet plus SVG/TIFF
     figures, matching the rest of the platform.

## CMIG Implementation Added

1. **User-model well-mixed dFBA CLI**
   - Command: `cmig dfba`
   - Inputs: user SBML model, initial exchange concentrations, time horizon,
     time step, biomass, optional vmax.
   - Outputs: `dfba_summary.json`, `timecourse.parquet`,
     `dfba_timecourse.csv`, `dfba_timecourse.svg`, `dfba_timecourse.tiff`.

2. **Lightweight spatial medium preview**
   - Command: `cmig spatial-preview`
   - Pure Python grid diffusion/source-sink preview, no COMETS Java dependency
     and no NumPy/SciPy requirement in the core module.
   - Outputs: `spatial_summary.json`, `spatial_frames.csv`,
     `spatial_heatmap.svg`, `spatial_heatmap.tiff`.

3. **GUI Dynamics tab**
   - Adds a focused `Dynamics` tab for:
     - running single-model dFBA from a user SBML model,
     - previewing spatial medium gradients,
     - loading generated figures and final readouts.
   - Jobs are submitted through the existing non-blocking `JobRunner`.

## Deliberately Not Implemented

- Full COMETS replacement.
- Spatial community dFBA with one FBA solve per grid cell.
- Biomass pushing, cooperative diffusion, extracellular enzyme kinetics,
  evolutionary mutation modules, or demographic/growth noise.
- Automatic model catalogue import.

These are outside CMIG's current scope and would add substantial engine
complexity. The current implementation keeps the dependency footprint small and
adds product-visible value without pretending to match COMETS.

## Next Practical Extensions

1. Add optional linear and pseudo-Monod uptake styles to `DfbaConfig`.
2. Add multi-substrate dFBA presets for common microbial media.
3. Add a community dFBA prototype only for well-mixed MICOM communities, before
   considering spatial grid FBA.
4. Add spatial preview barriers or region masks if users need agar/soil-like
   layout design.
