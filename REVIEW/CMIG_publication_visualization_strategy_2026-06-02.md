# CMIG Publication-Grade Interaction Visualization Strategy

Date: 2026-06-02

This plan targets CellChat-level interpretability and figure quality without copying
CellChat's ligand-receptor semantics. CMIG figures should expose metabolic interaction
strength, direction, member contribution, host use, and condition changes from the same
underlying interaction tables.

## Reference Principles

- CellChat emphasizes clear, attractive, interpretable communication visualizations:
  aggregated networks, pathway-level views, individual interaction views, heatmaps,
  chord diagrams, bubble plots, and contribution plots.
- CMIG should map those principles onto metabolic community data:
  - Cell group -> microbe, host, or metabolite class
  - Ligand-receptor pair -> metabolite-mediated exchange or host uptake event
  - Signaling pathway -> metabolite family or target readout group
  - Communication probability/weight -> flux, normalized transfer, or condition delta

## CMIG Figure Grammar

Core entities:

- `source`: microbial member, microbiome aggregate, host, or environment pool
- `target`: microbial member, host, or metabolite node
- `mediator`: BiGG metabolite id
- `edge_type`: secretion, uptake, cross_feeding, host_uptake, unused_secretion
- `weight`: flux magnitude or normalized transfer score
- `condition`: medium, diet, model combination, or intervention

Visual encodings:

- Edge width: interaction strength after optional normalization.
- Edge color: source group for CellChat-like circle/chord plots; edge type for mechanistic
  plots.
- Node size: abundance, growth contribution, total outgoing flux, total incoming flux, or
  host objective impact.
- Node grouping: microbe, host, metabolite class, environment.
- Hidden defaults: currency metabolites (`h`, `h2o`, `co2`) hidden in summary figures unless
  explicitly requested.

## Required Figure Families

1. Circle network
   - Circular layout with stable ordering.
   - Edge width scaled to transfer strength.
   - Node size scaled by outgoing/incoming total, abundance, or growth.
   - Variants: aggregate all metabolites, selected target metabolite, selected metabolite class.

2. Aggregate heatmap
   - Source x target matrix.
   - Values: total transfer flux, count of transferred metabolites, target production, or
     condition delta.
   - This is the primary dense comparison view for more than three species.

3. Chord-style transfer diagram
   - Sectors: members and host, optionally metabolite classes.
   - Chords: aggregated metabolite transfer.
   - Best for final publication panels with many edges.

4. Bubble plot
   - x-axis: source member or condition.
   - y-axis: metabolite or target readout.
   - Bubble size: flux/transfer.
   - Bubble color: used by host, unused, condition delta, or robustness class.

5. Contribution plot
   - Ranked bar plot for a selected target metabolite or host uptake.
   - Shows each member's fraction of total production/transfer.

6. Multi-condition comparison
   - Paired circle or heatmap panels for condition A/B.
   - Delta heatmap and top changed interactions table.

## Data Contracts To Add

Add these artifacts for all model-pool and host-microbe runs:

- `interaction_edges.csv`
  - source, target, metabolite, edge_type, flux, normalized_flux, condition, used_by_host
- `interaction_matrix.csv`
  - source, target, measure, value, condition
- `member_contribution.csv`
  - member, metabolite, secretion_flux, transfer_flux, contribution_fraction
- `figure_manifest.json`
  - figure type, filters, scaling, palette, hidden metabolites, layout seed, software versions

## GUI Plan

Extend the Host and Search views with a `Figure Mode` segmented control:

- Network
- Circle
- Heatmap
- Bubble
- Contribution

Shared controls:

- Target metabolite or metabolite class
- Top-N edges
- Normalize by abundance/growth
- Show/hide currency metabolites
- Show unused secretion
- Export SVG/PDF/PNG/TIFF

## Implementation Order

1. Extract a reusable interaction table builder from host-microbe and search outputs.
2. Add deterministic circle layout payload for Cytoscape.
3. Add heatmap and contribution static exports through the R FigureComposer.
4. Add bubble plot renderer.
5. Add chord-style renderer using the existing R/circlize boundary.
6. Add GUI figure mode controls and export buttons.
7. Generate fixture and real-model examples into `temp_figures/` for visual QA.

## Quality Gates

- Vector output for journal use: SVG and PDF.
- Raster output: TIFF/PNG at 300 or 600 dpi.
- All figures include a sidecar `figure_spec.json`.
- Text must remain readable at single-column and double-column sizes.
- Colorblind-safe palettes for final presets.
- Currency metabolites hidden by default but recoverable by user option.
- Dense graphs must offer top-N filtering and aggregate modes.
- Figure payloads must be reproducible from saved artifacts without re-solving.

## Non-Goals

- Do not copy CellChat's biological ligand-receptor interpretation.
- Do not require single-cell transcriptomics inputs.
- Do not make metabolite full names mandatory in figures.
- Do not add Recon/Human-GEM automatic model download or curation.
