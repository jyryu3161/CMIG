# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). CMIG uses
semantic versioning for public releases.

## [Unreleased]

### Fixed — consortium search correctness

- Reject invalid abundances and requested/effective MICOM membership mismatches.
- Separate secretion/uptake domains from epsilon utility bounds, including mixed
  minimization objectives; unify non-viable growth checks across target solvers.
- Match normalized reported scores to the actual unclipped affine LP objective.
- Replace name-biased GA parent/survival ties with seeded choices; version the
  changed semantics as `consortium_search_v2` / `set_ga_v2` in search provenance.
- Build `.sbml` and uppercase-format sources through disposable canonical model
  caches; preserve source files. Publish complete search runs with locks/staging
  and rollback instead of mixing partial outputs with earlier runs.

### Added — recoverable and inspectable search

- Shared search requests/service, model/solver preflight, cancellation/progress,
  strict-JSON checkpoints, identity-checked resume, isolated deterministic solver
  workers, per-call timeouts, phase timings and all-evaluation ledgers.
- GA diversity histories, opt-in partial restart/local mutation/common-member
  crossover, equal-budget multi-seed synthetic/GEM benchmark harness and CI gates.
- Budgeted multi-target GA/random with fixed fitness scales; feasible-solution
  front/crowding selection, objective extremes, independent epsilon slices and a
  complete **sampled** archive separate from displayed top-k.
- Member/community growth floors, same-optimum member growth/abundance reporting,
  and optional checkpointed top-candidate leave-one-out, monoculture, medium and
  abundance sensitivity analyses. Additional validation solves have a separate budget.
- GUI controls for medium, seed, budget, workers, direction, multi-target metric,
  reference scales, growth floors, timeout, validation, checkpoint/resume and cancel.

Existing solve goldens and core release version are unchanged; changed search
results must be distinguished by the new search/GA policy fields. Approximate
search, sampled Pareto fronts and local abundance trials do not certify global optima.

## [0.3.0] - 2026-09-02

Round 10: a four-track code review of the 0.2.0 tree, an AGORA2 model fetcher, and the medium
diagnosis that fetcher turned out to need.

**Reproducibility migration.** `cmig_core_version` is component #9 of the frozen 11-component
solve hash, so the version bump moves it by construction. The fixture goldens were re-captured
under core 0.3.0 and every pinned hash migrated: gurobi `0721dcc0…` → `31d5647d…`, osqp
`fbac47cf…` → `b8ca28e3…`. The workflow envelope is pinned to synthetic constants rather than the
live version and did not move (18 kinds unchanged). A `run_hash` published under 0.2.0 is not
comparable with one published under 0.3.0; the manifest records the core version for exactly this
reason.

### Changed — documentation

- **README rewritten as a front page.** It now states what CMIG does, the design
  principles each CI gate enforces, installation and a three-line quick start, and delegates
  everything else. Usage moved to the new **`docs/USAGE.md`** (requirements, installation
  variants, GUI tour, CLI examples, exit codes, medium semantics, reading a run back, a worked
  butyrate-consortium example, and the developer workflow); `docs/USER_GUIDE.md` remains the
  reference manual.
- **Documented commands are now machine-verified.** `tests/test_docs_commands.py` parses every
  `uv run cmig …` line out of the README and the usage guide and checks it against the real
  parser, and checks that every relative link resolves. This caught a long-standing README
  example: `host-microbe-bigg` was shown with a `--target` and an `--assume-bigg-namespace` the
  command has never had, and without the mandatory provenanced biomass basis.
- `docs/USAGE.md` and `docs/USER_GUIDE.md` are included in the sdist, so the shipped README's
  links resolve.

### Fixed — a medium that no model could grow on, reported as a producer ranking

Follow-up to the AGORA2 fetcher: a 20-strain AGORA2 pool on CMIG's shipped AGORA gut overlay
solved at **exactly zero growth for every strain**, and `cmig search` ranked them anyway. Two
independent causes, both fixed.

- **Boundary-isolation policy v1 closed AGORA's biomass pseudo-reactions.** AGORA/AGORA2 encode
  replication and translation cost as boundary reactions that create a placeholder metabolite
  from nothing (`--> dnarep_c`, `--> proteinsynth_c`, `--> rnatrans_c`) whose formula is the
  explicit no-composition marker `X`. The supply detector counted them as mass sources, so
  `--exact-medium` shut them and **every AGORA reconstruction became non-viable whatever the
  diet contained**. Policy **`boundary_reactions_v2`** leaves a *non-exchange* supplier of a
  formula-`X` metabolite open — it adds no atoms, so the mass-isolation invariant does not reach
  it — and records each one in `BoundaryIsolation.pseudo_supply_open`. A *missing* formula is
  deliberately still treated as mass (unknown is not zero), and an exchange is never reclassified
  (`EX_biomass_e` also carries `X`; granting it uptake would feed a model its own product).
  `boundary_isolation_policy` is a non-hashed provenance marker: results move, `run_hash` does
  not, and the marker dates the manifest. Measured effect on the AGORA2 pool: 0/20 → 6/20 strains
  grow on the diet alone.
- **`cmig search` ranked communities that cannot grow.** With µ\* ≈ 0 the growth floor
  `f · µ\*` is vacuous, so the target LP returns `optimal` with a positive flux at zero growth —
  a "best butyrate producer" that does not grow. Such a candidate now gets status `non_viable`,
  is quarantined into `search_unevaluated.csv`, and raises a run-level warning naming the medium
  (not the target) as the cause.

### Added — `cmig medium-gap`

Answers "why can this pool not grow on this diet, and what do I add". Applies the medium exactly,
then solves a cardinality-minimal MILP for the smallest set of *additional* boundary reactions
reaching `--min-growth`, re-solves to verify it, and leave-one-out checks which are essential.
`--oxygen-mode anaerobic` by default, so an anaerobe is never "fixed" by being made to breathe;
the objective's own products are excluded from the candidate set. Writes `medium_gap.json`,
`medium_gap.csv` and `medium_gap_supplemented.csv` — the base diet plus the supplement union,
every added row marked `row_role: gap_supplement` so it is never mistaken for published diet.
Supplements that are sinks or demands inside the model are reported separately, because a diet
file cannot supply them. On the AGORA2 pool: 6 sufficient, 13 needing 1-6 additions (quinones,
siroheme, a diacylglycerol, a few dipeptides), 1 with no supplement of any size.

### Added — AGORA2 model fetcher

- **`cmig agora2-list` / `cmig agora2-fetch`** (`cmig/io/agora2.py`) — the first CMIG commands
  that reach the network, and only ever the publisher's own file server (any other URL is
  refused). They fetch **user-selected** AGORA2 reconstructions on demand and write an
  `agora2_manifest.json` recording the source URL, the bytes as served (`source_sha256`), the
  bytes on disk, and every transformation applied. CMIG still curates and redistributes no
  catalogue.
  - Selection is conjunctive: `--strain`/`--strain-file`, `--genus`, `--match`/`--exclude-match`,
    `--one-per-genus`, `--sample N --seed S`, `--limit`, `--all`, plus `--dry-run`. `--all` and
    any fetch above 8 GB require `--yes`; the whole catalogue is ~70 GB as individual files, so
    the message points at the publisher's 2.0 GB archive instead.
  - **Encoding repair (on by default).** The published SBML declares UTF-8 but carries stray
    Latin-1 bytes in species names, so libsbml rejects the document outright and cobra reports
    "No SBML model detected in file". Measured: 3 of a 20-model pool, 5-9 bytes each. Only the
    offending bytes are transcoded, and each is recorded.
  - **VMH → BiGG namespace conversion (`--namespace bigg`, default).** Two conventions differ:
    compartments (`EX_but(e)`, `but[e]`) and isomer separators (`glc_D`, `ala_L`, `26dap_M`).
    Both are rewritten, collision-checked and fail-closed; no metabolite-identity mapping is
    involved. Unconverted AGORA2 models score **0 % on CMIG's namespace gate and are blocked**,
    and converting only the compartment half fails quietly: over the 645 exchange metabolites of
    a 20-strain pool, matches against the 144 BiGG ids in CMIG's gut media rise 93 → 122 once
    the isomer separator is rewritten too — the 29 recovered include D-glucose and every amino
    acid, without which a defined medium leaves the community at zero growth. `--namespace vmh`
    keeps the published ids and says plainly that the gate will block them.
  - **`--format json`** re-serialises through cobra JSON: measured 14.0 MB → 1.16 MB and
    1.72 s → 0.26 s per load, which dominates a combination search that rebuilds the community
    once per candidate.
  - The manifest records that individual reconstructions are the 2023-03-23 annotated set (the
    2024-07-04 "fixed" rebuild is archive-only), the AGORA2 citation, and that CMIG asserts no
    licence for the reconstructions.

Round-10 codebase review (2026-09-02): four parallel read-only reviews (CLI, analysis core,
engine/host/dynamics/provenance, io/service/render/GUI), every confirmed finding fixed and pinned
by a regression test (`tests/test_round10_review_fixes.py` plus targeted additions).

### Fixed (scientific results)

- **Host coupling dropped stereo-descriptor metabolites.** `solve_bigg_host` published
  `lumen_uptake`/`lumen_uptake_ranges` under the normalized spelling (`lac__d`) while
  `host_impact` joined them against the raw MICOM ids (`lac__D`), so every `__D`/`__L`
  metabolite (`lac__D`, `glc__D`, the L-amino acids) was reported as **unused secretion** with a
  zero transfer in `microbe_to_host.csv`, `interaction_edges.csv`, `member_contribution.csv`
  and `host-ko-impact --target`. Results are now keyed by the caller's raw id, and
  `host_impact` also accepts either spelling.
- **Community dFBA read each member's pool flux under a guessed key** (`EX_glc__D_m` ->
  `glc__D`) and defaulted to 0.0 on a miss, so a member whose exchange is not literally
  `EX_<met>_e` grew on a pool that never depleted while `member_exchange_fluxes` said 0 — with
  `acceptance.interpretable: true`. The key is now derived from the member reaction MICOM
  actually connected (`global_id`), and a missing report raises instead of defaulting.
- **dFBA emergency clamp froze on solver noise**: a depleted exchange at bound `-0.0` reading
  `-1e-12` counted as required mass (`0/1e-15 = 0` scale), zeroing growth for the rest of the
  run. Only fluxes below the tolerance count (single-model and community integrators).
- **Multi-target Pareto search silently dropped a consortium** whose epsilon sweep solved at no
  level without raising: it appeared in neither the ranking nor `unevaluated` while
  `n_candidates_evaluated` counted it. It is now a disclosed `failed` evaluation.
- **`single_model.solve_single_model`**: pFBA raised `cobra.exceptions.Infeasible` where FBA
  returned a status, and a non-optimal FBA recomputed a fabricated objective from stale primals
  (10.0 for a biomass lower bound of 10). Both now return `objective: nan` with the status and a
  diagnostic.
- **`publication-benchmark`** judged its dFBA leg by completion and residuals only, so a bundle
  could be `publication_ready: true` beside a `dfba_sensitivity.json` saying
  `interpretable: false`. The verdict is now the writer's `sensitivity_acceptance`
  (`checks.dfba_interpretable`); the protocol document says how to track every consumed substrate.
- `core.sweep.run_sweep` recorded NaN/inf metrics as `ok`; they are now `failed` rows with a
  diagnostic (the GUI sweep and `sweep-fixture` both go through it).
- `host-ko-impact`: a raised arm carried `community_growth: 0.0` beside NaN host values; it is
  NaN now.
- `strain-growth --single-medium model_default --medium X` applied X to the alone leg anyway,
  contradicting `--help` and its own warning; native bounds are kept.
- `dfba`: a tracked substrate with a positive initial amount whose exchange cannot import
  (`vmax == 0`) is now named in the warnings instead of silently staying constant.
- `core.fva`: licence/time-limit/API errors were re-raised as `FVAInfeasibleError`; only
  `OptimizationError` is an infeasibility, everything else is `FVAUnavailableError`.

### Fixed (exit codes, provenance, outputs)

- `strain-growth` and `gene-ko-search` declared `--allow-failed-run` but always exited 0; a
  failed run (all alone legs failed / every knockout arm failed) now exits 3 like every other
  analysis, and `gene-ko-search` writes the same `failed` tier to its manifest as to its summary.
- `dfba` manifest `summary.n_steps` was always 0 (`DfbaResult` has `timecourse`, not `rows`).
- `render-figure --panel` ignored `--width/--height/--dpi` unless `--title` was also given.
- `search-advanced-fixture` recorded `strategy: mro_mip_greedy` while ranking exhaustively; the
  summary now names the strategy that ran.
- Every taxonomy CSV read goes through the guarded reader (an empty/truncated CSV is exit 2,
  not a pandas traceback) and CSV-relative `file` paths resolve against the CSV in
  `search`, `gene-ko-search`, `strain-growth`, `abundance-impact` and the three host commands,
  as `solve`/`pair`/`sweep` already did.
- `pair`, `strain-growth` and the namespace mapper loaded members with `read_sbml_model`;
  `.json`/`.mat` pools (admitted by `--model-dir`) now load through the format-detecting loader.
- Atomic publication: `host_exchange_map.csv`, `host_interface_map.json`,
  `host_map_summary.json`, multi-target `search_summary.json`, `model_quality.{json,csv}`,
  `dfba_sensitivity.{json,csv}`, `publication_benchmark.json`, interaction CSV/JSON artifacts,
  fixture goldens and the workflow manifest all use `cmig.io.atomic` (bytes unchanged; envelope
  gate green). `dfba` maps an output `OSError` to exit 1 like `dfba-community`.
- `cmig.io.atomic` publishes files with the process umask (0644 under 022) instead of
  `mkstemp`'s 0600, and keeps an existing file's mode on re-publication; group members could
  read `manifest.json` but not the parquet/figures beside it.
- `write_solve_output` stages beside the *resolved* run directory, so a symlinked `--out` onto
  another filesystem no longer fails with EXDEV after the solve.
- matplotlib fallback in `render-figure` goes through `figure_style` (hashsalt, no date), so
  R-less renders are byte-reproducible as the provenance sidecar claims; Rscript invocations have
  a 600 s timeout mapped to `RenderError`.
- GUI: `JobRunner` treats `SystemExit` from an in-process CLI as a failed job instead of leaving
  it `RUNNING` forever; double-clicking a Search/Sweep/KO run in the Project Explorer no longer
  wipes the community run on screen (status names the kind and `inspect-run`); the Community
  Builder refuses members that match no model file; the Profile tab shows the `--targets`
  readout; figure panels prefer the SVG and fall back to the TIFF.
- `model_import`: fallback model id for `foo.xml.gz` is `foo`, not `foo.xml`.

### Changed

- `edges.parquet` docs: `weight_lo`/`weight_hi` are reserved (null in every published run;
  `--fva` fills `profile.fva_lo/fva_hi` only).
- Parser: `--allow-unknown-medium` and the namespace gate group are added through the shared
  helpers everywhere (help text unified).
- Removed dead code: `sign.cross_feeding_weight` (semantics rejected by
  `allocate_cross_feeding`), `manifest.sha256_checksum`, GUI `_float_value`,
  `ModelManagerPanel.as_summary_dict`, the unused `welcome` i18n key, `host._interface_of`;
  `DEFAULT_BIGG_COUPLING_EXCLUDE` has one definition; `NOISE_FLOOR` is imported rather than
  restated as `1e-6` in metrics/delta/sandbox/single_model.
- `solve_generic_host` labels its attribution `single_fba_point` (it is one LP vertex, not
  objective-fixed FVA).

## [0.2.0] - 2026-08-25

Everything below shipped between 0.1.0 (2026-07-10) and this release —
rounds 5–9 of parallel-worktree development. Entries are grouped by round;
BREAKING items are flagged inline (workflow-manifest schema 1.2, tidy schema
1.3 community-basis edge weights).

### Added (round 9)

- **`cmig dfba-community`** — the well-mixed community dFBA prototype gets its CLI: per-member
  biomass over a shared pool, MM uptake rebinding, adaptive non-negative integration; exit 0 only
  when `acceptance.interpretable` is true (3 for non-interpretable/solver failure;
  `--allow-failed-run` softens the exit, never the recorded verdict); Gurobi-only. New additive
  workflow kind `community_dfba` (envelope now 18 kinds; initial biomasses/concentrations and
  member vmax are hashed inputs, telemetry/events/acceptance are not); deliberately not cross-run
  byte-comparable because raw timing telemetry is a required output.
- **`cmig render-figure --panel network|heatmap|chord`** — the shipped-but-unreachable Figure
  Composer R panels are now a CLI surface (repeatable, order-preserving; R-only with an explicit
  refusal to substitute matplotlib; svg/tiff). Render publication is atomic end-to-end: R,
  matplotlib-fallback, and panel paths stage the full figure/spec/provenance set and publish each
  file atomically — a failed render leaves the previous public set untouched (profile-path bytes
  proven unchanged).
- **Stats 5b/5c core**: frozen validated `StatsConfig` with deterministic provenance; the orphaned
  PCA/UMAP/KMeans layer becomes a seeded, fail-closed `run_embedding_pipeline` (embeddings whose
  interpretability gates fail are never returned, with stable reasons); volcano data preparation
  with validated effects/p-values. CLI wiring proposed for a later round.
- **GUI medium tools (spec §11)**: preset picker with `row_role`-aware display, clipboard CSV
  paste validated by the real loader, community Check Growth through `cmig solve` (explicit
  namespace policy and merge/exact toggle), before/after profile comparison via the Compare
  overlay, and a `cmig minimal-medium` hook. The nutrients-only view filters in memory only and
  refuses to run in merge mode (it would reopen undeclared model-default suppliers).
- Cross-run artifact determinism measured by double console runs: `pair`, `delta`, `single`, and
  `minimal_medium` promoted to the deterministic-artifact set (byte-identical digests recorded);
  relocation caveat documented for their path-bearing summaries.

### Fixed (round 9)

- **Missing member abundance now fails target-share calculation closed**:
  `community_contributions` raises `MissingAbundanceError` instead of assuming factor 1.0,
  aligning abundance-impact shares with the tidy-1.3 policy; failed sweep points publish null
  cells plus a diagnostic, and an abundance-impact sweep in which every point failed now exits 3
  instead of 0 (partial failures still exit 0 with per-row disclosure).
- **The scalar multi-target `pareto` column is real N-dimensional frontier membership** for any
  target count (was: computed only for exactly two targets, silent `False` above); both pareto
  surfaces share one dominance implementation while keeping their distinct solve semantics.
- **Mass-inconsistent community solves fail closed** (round-9 solver audit, defect 1): `cmig
  solve`/`solve-fixture` now verify the documented edge↔profile identity on the produced bundle
  and exit 3 with a named worst offender instead of reporting `optimal` — the audit measured a
  real OSQP state with zero member growth and residuals up to ~1.5e3 publishing as success.
  Artifacts are kept for forensics; OSQP diagnostics point to `--solver gurobi`.
- **Fresh `solve-fixture --solver osqp` emits its frozen golden hash again** (audit defect 2):
  the fixture path now hashes components and the manifest at the frozen variant decimals
  (osqp=4) instead of the default 6; Gurobi output is byte-unchanged, both pinned by regression.
- The hands-on tutorial now prints its exact taxonomy (abundances are run-hash inputs); the
  round-9 solver audit showed the document was not reproducible without them.

### Verified (round 9)

- **Second-solver reproduction audit** (`REVIEW/round9/report_V6.md`): the dual-golden fixture,
  single-model objective/exchange phenotype, and a controlled dFBA point reproduce on OSQP within
  the documented tolerance; the real bundled-pool community does NOT (now failing closed, above);
  every Gurobi-only surface is inventoried with its code-level reason. Real community results
  remain Gurobi-only for publication.

### Changed (round 8) — BREAKING

- **Tidy schema 1.3 / `edges.parquet.weight` basis.** `weight` is now the unsigned
  relative-abundance-weighted **community** contribution (`mmol gDW_community^-1 h^-1`), not a
  per-taxon rate; direct and allocated cross-feeding rows share the basis, and
  `weight_lo`/`weight_hi` are direction-aware magnitude intervals in the same basis (cross-feeding
  intervals stay null — pairwise transfers are not identifiable). This closes the long-standing
  ranking-inversion known-open item (measured: an abundance-0.1 member out-ranked the true
  supplier 8.44×; ranks now match community contribution and the signed direct-edge sum equals
  `profile.net_flux`). **Do not multiply a ≥1.3 weight by abundance again.** A missing member
  abundance now fails the tidy build (`MissingAbundanceError`) instead of assuming factor 1.0;
  zero abundance stays a valid zero. Legacy ≤1.2 bundles are semantically migrated on read; a bare
  legacy edge table yields nulls with `LegacyEdgeBasisWarning`. Solve goldens re-captured on
  Gurobi and OSQP (answer digests moved; the frozen 11-component input `run_hash` did not). The
  manifest's `edge_attribution` fields, figure captions, GUI contribution charts, and docs now
  state the community basis, sourced from `cmig.core.tidy` constants.

### Added (round 8)

- **`cmig pair` / `cmig delta` / `cmig single` / `cmig minimal-medium`** — the previously
  library-only baseline analyses as first-class workflows (run directories, additive workflow
  kinds, `inspect-run`, exit 0/2/3, the shared `--medium`/`--exact-medium`/
  `--allow-unknown-medium` contract, workflow-map entries). `growth_feasible`, single-model
  KO/FVA/exchange, `minimal_medium_cardinality`, and `analyze_pair` now share one translated
  medium pipeline; pair interaction deltas hold the effective metabolite-level offer fixed across
  the community and each monoculture leg, so a mono-vs-co difference can no longer be a native-
  medium artifact (the old mixed contract could report amensalism where the controlled comparison
  shows neutralism). Missing co-culture growth is NaN, never a fabricated zero.
- **Well-mixed community dFBA prototype** (`cmig.core.dfba_community.run_community_dfba`):
  build-once MICOM community, per-member biomass + shared pools, MM uptake rebinding, adaptive
  non-negative integration with structured events and `acceptance.interpretable` gating. A
  1-member community reproduces the single-model integrator at machine precision (max
  |Δbiomass| 2.2e-14 gDW/L through glucose depletion); producer/consumer cross-feeding dependence
  validated against a stalled consumer-only control. Gurobi-only; death/washout explicitly not
  modeled; new `community_dfba_timecourse` long-format kind with atomic Parquet publication.
- **Real GUI sweep + profile overlays**: the Sweep tab drives the actual `cmig sweep` axes
  (mediums, abundance variants, member sets, bounds variants, tradeoff-fs, solvers) with the
  fixture sweep as an explicit smoke option; External Profile gains a Qt-native flux heatmap and
  baseline/variant delta overlays fed by Compare/Sandbox results (missing values stay blank with a
  note, never zero-filled).
- **Gut-overlay `row_role` marker** (`nutrient`/`pool_closure`) on all seven generated overlays:
  the bundled-pool closure block is now mechanically strippable for exact-medium/other-pool use
  while all 717 exchange bounds and the safe default-merge behavior stay byte-identical
  (`medium_checksum` unchanged for every file).
- **Atomic publication everywhere**: matplotlib figure writers (shared TIFF path, interaction and
  screening/spatial SVG/TIFF including failure banners), sweep/golden-fixture/tidy/matrix Parquet
  writers, plus best-effort parent-directory fsync on POSIX after every atomic replace. Artifact
  bytes unchanged (figure hashes equal the round-7 recorded values).

### Added (round 7)

- **`--exact-medium` CLI mode** on all nine medium-bearing subcommands (`solve`, `search`,
  `strain-growth`, `abundance-impact`, `gene-ko-search`, `host-microbe-bigg`, `host-ko-impact`,
  `host-search-bigg`, `sweep`), routing to the existing
  `apply_medium_translated(..., exact=True)` boundary-isolation path. The default without the flag
  remains the documented merge-onto-model-default overlay, byte-identically. Workflow manifests now
  hash `medium_application_mode` beside the medium checksum under **manifest schema 1.2** — the
  single intended round-7 run-hash drift, re-blessed via the documented envelope procedure;
  `inspect-run` still reads 1.1 manifests. `cmig workflows` now covers every non-fixture analysis
  command, enforced by a parser-derived coverage test.
- **Evidence-backed host interface classification** (`cmig/core/host_types.py`): lumen/blood sides
  are now classified from reviewed-map overrides, id suffixes, annotations, side-bearing
  reaction/metabolite names, explicit compartments, and boundary topology — each with a recorded
  evidence trail. Real GEMs get honest partial results (Recon3D: 25 lumen + 31 blood classified,
  1,504 explicitly unclassified, `quantitative_coupling_ready` stays `False`; RECON1: honest zero).
  Reviewed interface maps optionally carry `{"host_exchange", "interface"}` values — legacy string
  maps keep their exact meaning — and side-aware coupling opens microbial availability only on
  lumen entries and `host_medium` only on blood entries. `host-map` artifacts record
  `interface`/`interface_evidence` and side counts; `host-generic` reports the
  `interface_classification` audit. The `host.py`↔`host_coupling.py` `__getattr__` cycle is gone.
- **First-class GUI Graph tab and Profile charts**: the tested `InteractionGraphView` + namespace
  `GateBadge` are mounted as a Graph tab fed by Open Run; the External Profile view adds a signed
  diverging net-exchange chart with FVA whiskers and an abundance-weighted stacked member
  contribution chart (Qt-native, no new dependency; the known-open `edges.weight` artifact value is
  untouched and the display basis is stated on the chart). Real Korean GUI localization replaces
  the previous identical-strings catalogue; English is the single default and `--lang ko` opts in.
- **Atomic Parquet publication** (`cmig/io/atomic.py`): binary/Parquet writes now stage in the
  destination directory, fsync, and `os.replace`, so a crash cannot leave a partial artifact;
  adopted by every `cmig/io` Parquet writer with byte-identical output.
- **Randomized test order**: `pytest-randomly` is installed and the full suite passes under
  shuffled order (verified with multiple recorded seeds); mypy is pinned (`mypy==2.1.0`) and the
  whole package is now mypy-clean under strict settings.
- **One matplotlib publication policy** (`cmig/render/figure_style.py`): the duplicated figure
  constants/helpers in `cmig/cli/main.py` and `cmig/core/interaction_figures.py` were consolidated
  with byte-identical figure output, proven by SHA-256 on all eight representative artifacts.

### Documentation (round 7)

- `docs/PUBLICATION_VALIDATION.md` rebuilt for the post-round-6 boundary-isolation contract with
  every claim labelled (`VERIFIED AGAINST CODE` / `VERIFIED AGAINST
  REVIEW/SCENARIO_RESULTS_ROUND6.md` / `TO RE-RUN AT RELEASE`); the workflow tutorial now covers
  the live 35-command surface including the GA controls; `RELEASE_CHECKLIST.md` gained the missing
  `cmig golden verify-envelope` gate; skill docs replaced rotting line-number citations with symbol
  references; `docs/release-drafts/` holds the 0.2.0 changelog draft, version-alignment plan, and
  the Human-GEM fixture decision memo.

### Added

- **Literature-grounded gut medium overlays** (`medium_presets/gut_overlay_*.csv`, 7 files) with a
  tracked provenance document (`medium_presets/PROVENANCE_gut_media.md`), row-level provenance
  (`medium_presets/provenance_rows.csv`), mirrored source data (`medium_presets/sources/`) and a
  deterministic builder (`scripts/build_gut_media.py`, `--check`/`--report`). The reference pair comes
  from AGORA Supplementary Table 12 (doi:10.1038/nbt.3703), which publishes the Western and high-fibre
  diets directly in mmol gDW⁻¹ h⁻¹ so no unit conversion is needed; a second pair converts VMH
  diet-designer exports from mmol person⁻¹ day⁻¹ via `v = D · f_colon / (B_gDW · 24)` with every
  constant sourced or explicitly labelled an assumption, and agrees with the AGORA bound to 1.5×.
- **Medium overlays now close the background, including oxygen.** `--medium` merges onto MICOM's
  default, so any metabolite a file did not name kept a permissive bound — `EX_o2_m = 999999.0`, an
  aerobic colon. Measured on a 3-member community, the legacy glucose-only preset gives community
  growth 1.2678 h⁻¹ with the inherited oxygen and 0.6990 h⁻¹ with `EX_o2_m = 0.001`: an **81 %
  overestimate**. Every shipped overlay now names oxygen at MICOM's published 0.001 and carries a
  background-closure block (`uptake_limit = 0`) for every metabolite the model pool would otherwise
  leave open; measured, nothing remains open that the overlay does not name. `--medium` is documented
  as an overlay in `README.md`. The general fix landed in round 7: `--exact-medium` in the CLI plus
  the `medium_application_mode` manifest field (see the round-7 entries below).
- **Fibre coverage of the bundled model pool measured and documented**: only 1 of AGORA's 24 fibre
  entries (raffinose) has an exchange in any bundled model, so a "high fibre" run on this pool is not
  a fibre-degradation experiment. `tests/test_medium_presets_gut.py` (18 tests, each mutation-verified)
  re-derives every shipped number from the mirrored sources and checks aliasing, per-model coverage,
  background closure, the anaerobic-O₂ term, the magnitude band and the PDF transcription.
  The pre-existing `western_diet.csv` / `high_fiber.csv` are single-row glucose files with no cited
  source, 134× and 76× the published AGORA bounds; retained only as a smoke fixture and documented as
  not citable as diets.
- Claude Code agent skill `cmig-metabolic-analysis` (`.claude/skills/`) that routes requests to the
  correct `cmig` workflow and enforces the scientific-validity guardrails, plus a
  `.claude-plugin/marketplace.json` making it installable following the anthropics/life-sciences
  marketplace pattern.

### Documentation

- **Skill/README guardrails synced with the round-5 hardening.** The skill layer predated the
  round-5 scientific fixes and named none of their vocabulary, so following it faithfully could
  still produce a wrong conclusion. Added, in `.claude/skills/cmig-metabolic-analysis/` and
  mirrored in `README.md`:
  - **Multi-target search.** `--targets` / `--target-preset scfa` / `--multi-metric` /
    `--target-directions` were entirely undocumented. A "total SCFA" question answered with the
    default `normalized_weighted` scalarisation collapses onto a single-metabolite specialist:
    measured over the 5 bundled models, all 9 ranked candidates returned `ac=0, but=0, ppa=0,
    succ=0`, and rank 1 (`iHN637+iSFV_1184`) was reported as `lac__D=17.44, ac=0` — while
    `--multi-metric pareto` shows that same pair reaching `ac=27.75`. All three metrics were run
    over the identical pool; the same pair is reported as `lac__D=17.44` (`normalized_weighted`),
    `ac=8.19 + succ=10.41` (`carbon_equivalent`), or `ac=27.75` (`pareto` rank 1) — so
    `normalized_weighted` claims lactate and no succinate while `carbon_equivalent` claims
    succinate and no lactate, about one community on one medium. **`carbon_equivalent` is not an
    escape from the collapse**: it returned `but=0, lac__D=0, lac__L=0, ppa=0` for all 9 of its
    ranked candidates. The docs now state that the vertex collapse is a property of linear
    scalarisation rather than of the weighting, so only `pareto` answers a "best overall"
    question. The `pareto` **mode** (an N-dimensional epsilon-constraint frontier, any number of
    targets) is distinguished from the `pareto` **column** on a scalarised ranking (computed only
    for exactly 2 targets; `False` elsewhere means "not evaluated", not "dominated").
  - **`edges.parquet.weight` is a per-taxon flux.** Comparing raw edge magnitudes inverts member
    rankings; measured on a 2-member solve, acetate edges were `3.876` (abundance 0.1) vs `0.459`
    (abundance 0.9) while the community contributions were `0.388` vs `0.413`. Documented the
    reconstruction (exclude `cross_feeding`, sign by direction, multiply by abundance → equals
    `profile.net_flux`) and pointed at the `edges.weight basis:` line `inspect-run` prints.
  - **Custom-medium invalidation.** Pre-fix runs that used `--medium` must be re-run, the
    `run_hash` will not reveal it, and `provenance.medium_policy` is the discriminator. Documented
    the real cost of `--allow-unknown-medium` (exit 0, `status: degraded`, dropped nutrients, and a
    `medium_checksum` still covering the full requested medium) and the namespace-alias input error.
  - **dFBA interpretability.** `--close-untracked-uptake` was undocumented, so the previous advice
    sent users to audit `--dt`/`--km` on an experiment where Km is not rate-limiting. On
    `models/iML1515.xml` the naive recipe reports `status: completed` and a biomass number with
    `n_untracked_uptake: 14`.
  - **Exit-code contract** (`0` / `2` input error / `3` failed science) and `--allow-failed-run`,
    which no skill or README text mentioned.
  - **Two fingerprints:** `run_hash` certifies the inputs, `result_digest` certifies the answer;
    `artifact_integrity`; `cmig golden verify-envelope`; and the honest scope note that `cmig solve`
    emits no `result_digest`. Also documented `result_digest.cross_run_comparable` — digests are
    comparable *between* runs only for `host_map`, so cross-run comparison elsewhere manufactures
    false alarms.
  - **`inspect-run`'s payload (`schema_version 1.2`)**: documented `status_source` and all ten of
    its values, `degraded` as a tier, and `result_digest_absent_reason` with its four values. Stated
    that **`unknown` is a real answer, not a tool failure** — a recognised summary recording no
    run-level outcome now reports `status: unknown` / `status_source: no_status_signal` instead of a
    fabricated `ok` — and that `acceptance.interpretable: false` is a **veto** that overrides a
    rosier `manifest.status` and owns `status_source` when it wins, so the two can legitimately
    disagree. Also flagged that the status vocabulary is **not closed**: `infeasible` and `stalled`
    still reach `status` verbatim because the legacy alias table maps only `optimal`/`completed`, so
    a gate matching just the four tiers will miss them.
  - **`cmig host-ko-impact`** — a shipped workflow (GUI `Host / Knockout Impact`) that the skill's
    routing table and per-command reference both omitted.
  - `strain-growth --single-medium` (`model_default` reports native capability, not an interaction
    effect), `abundance-impact --fva`, `--accept-unreviewed-map` and the D/L stereoisomer hazard it
    waives, `--keep-host-uptake`, and the `search_unevaluated.csv` partition.
- **Preflight step added** to the skill (`uv run cmig version && uv run cmig solvers`): a
  genome-scale analysis can run 15+ minutes, and an environment missing the `engine` extra fails
  only once it reaches the solve. Documented the subtler case it also catches — `uv run` resolves the
  **nearest** project root, so running it from a git worktree or sibling checkout (each carrying its
  own `pyproject.toml`) resolves a *different* project and provisions a fresh minimal `.venv` with no
  `engine` extra; `cmig workflows` still succeeds there while every analysis command fails with
  `… 는 엔진 stack 필요`, and that message names a fix that would sync the wrong project. Measured:
  from the synced checkout `uv run` gives `…/CMIG/.venv` with `micom 0.39.0`; from a worktree of the
  same repo it creates `…/CMIG-wt-*/.venv` with 14 packages and no micom. `uv run cmig …` remains the
  documented invocation, matching the examples `cmig workflows` emits.
- Documented that `cmig solvers` lists `highs` although no command's `--solver` accepts it, and that
  the bundled `models/` pool is not a gut community (only *E. coli* is a common gut resident), so
  results over it are a methods demonstration rather than gut biology.
- Corrected stale multi-target artifact claims: multi-target `search` writes `pool_taxonomy.csv`,
  `search_plot.tiff` and conditionally `search_unevaluated.csv`, and does **not** write
  `search_member_matrix.csv` or `search_scatter.svg`.
- **Corrected over-confident guardrails found by independent verification.** Each had asserted more
  than the code supports:
  - `--close-untracked-uptake` **must be paired with a complete `--initial`**, and
    `dfba-sensitivity` accepts `--initial`. The previously prescribed example failed on the model it
    named: exit 3, 4/4 rows stalled at `final_biomass 0.01` (the initial value — no dynamics), after
    closing 22 exchanges. Supplying all 14 nutrients from a plain run's `untracked_uptake` gives
    exit 0, `interpretable: True`, 4/4 completed, and a real step-size signal (0.0536 at dt 0.1 vs
    0.0503 at dt 0.2). Both forms are now shown.
  - `--allow-failed-run` is **not universal.** It is rejected by `dfba`, `model-quality`,
    `publication-benchmark`, `spatial-preview` and `model-review` as an argparse error — which exits
    **2**, the same code documented for a bad medium spec, so the docs now warn against debugging
    the wrong thing.
  - `--robustness-fva` is **silently inert in multi-target mode** (`cli/main.py:4151` returns to the
    multi-target path before the flag is read; no columns, no warning, exit 0). It had been
    prescribed *in that mode* as the remedy for the scalarisation collapse. Documented as a current
    limitation, with `--multi-metric pareto` as the available route.
  - `publication-benchmark` exposes **33 options** (previously undocumented) and accepts **no
    `--close-untracked-uptake`**, so `publication_ready` cannot certify the dFBA guardrail; a
    load-bearing dFBA endpoint must come from a separate `dfba-sensitivity` run.
  - Recon3D loads in **~6–7 s**, not the ~30–60 s previously stated as "verified".
  - The edge→`net_flux` reconstruction is **not exact for every metabolite**: 23/25 agreed to
    <1e-9 while `mobd` and `btn` were off by ~1e-8 near the 1e-6 noise floor, and 19 of 44 edge
    metabolites had no profile row at all.
  - `per_target_capability_not_simultaneous` lives in **`flux_basis`**, not `diagnostic`.
  - `inspect-run` exits **2** on an unusable directory (missing `--run-dir`, corrupt
    `manifest.json`), not only 3 on `artifact_integrity: mismatch`.
  - `status: degraded` is the **normal** search outcome when any candidate is unevaluable.
  - Added `host_ko_impact.csv`, `gene-ko-search --rank-by {effect,remaining}` (which sets the whole
    KO ordering), `host-search-bigg --include-currency-metabolites`, and
    `strain-growth`'s `medium_metabolites_unavailable_to_member`.
- Integrated publication benchmark with model quality, community, search, dFBA sensitivity, host
  scale/mapping/coupling, checksums, acceptance checks, and artifact manifests.
- Annotation-aware host interface mapping and objective-fixed FVA transfer intervals.
- Cross-platform CI quality matrix and distribution-content audit.
- Apache-2.0 licensing, citation/Zenodo metadata, release checklist, and checksummed external-model
  source records.
- A pinned R 4.3.2/Bioconductor 3.18 `renv.lock` and per-figure runtime/input/script/output
  provenance sidecars.
- Mandatory host/microbial gDW basis kind and measurement/citation provenance; GUI and publication
  commands no longer prefill an equal-mass assumption.

### Fixed

- **The host-coupling path was over-constrained relative to every other path: `--allow-unknown-medium`
  now exists on `host-microbe-bigg`, `host-search-bigg`, `host-ko-impact` and `gene-ko-search`.**
  `core/host_coupling.run_bigg_host_microbe` hard-coded `apply_medium_checked(..., strict=True)` and
  no host command exposed a way to relax it, so a medium that `solve` / `search` / `strain-growth` /
  `abundance-impact` / `sweep` all run with a documented degradation was **fatal** on the four
  remaining commands. Measured on the shipped `medium_presets/gut_overlay_vmh_high_fiber_x100.csv`
  against `iML1515 + iYO844 + iHN637`: `cmig solve --allow-unknown-medium` returns growth
  `0.0847149208736683` while `cmig host-microbe-bigg --microbe-medium <the same file>` exited 2 with
  `medium exchange has no counterpart in the target model … ['EX_n2_m']` — **one row of eighty**,
  requesting `uptake_limit = 0.0` for a metabolite the pool has no exchange for at all. After the
  fix the same run completes: `community_growth = 0.0847149208736683` (identical to the standalone
  solve), `host_status = optimal`, `host_objective = 0.0`, `status: degraded`, `EX_n2_m` named in
  `warnings` and in `summary.unapplied_medium_exchanges`. Strict remains the default; nothing is
  filtered silently.
- **A partially applied medium is answer-determining and now moves the `run_hash`.**
  `_host_medium_component` built the `medium` component without `allow_unknown_medium`, so two host
  runs applying *different* media — the whole file, or the file minus the rows the community cannot
  honour — would have minted the same fingerprint. Round 5 had already put the flag inside that
  component; this builder was the one that dropped it.
- **`--host-medium` entries the host has no exchange for were dropped in silence.**
  `solve_bigg_host`'s `add_availability` returned `(None, flux)` and nothing recorded it, so a
  half-applied host background was published with every artifact reporting a complete run.
  Unmatched *microbial* availability was already disclosed; the host's own medium was not. It is
  now refused by default and named in `warnings` under `--allow-unknown-medium`.
- **A failed community solve inside the host path named its status but not its cause.** Round 6's
  scenario published `host_status=solver_failed` with two generic warnings while the engine's own
  diagnostic ("pFBA flux stage failed: OptimizationError: could not get community growth rate.")
  lived only on the inner `HostSolveResult`, which no host command writes out. The diagnostic now
  travels into the run warnings and into the manifest's `diagnostic`, and the medium refusal names
  the offending ids *and* `--allow-unknown-medium`. A reader can now tell an infeasible community
  from a rejected medium without re-running anything — the round-6 open question
  ("the host path is over-constrained relative to the standalone path") was two different pools
  compared as if they were one, and the message was what made that invisible.
- **`gene-ko-search` could not be given a medium at all.** It was listed as merely missing
  `--allow-unknown-medium`, but `search_model_pool` has accepted `medium_spec`/`strict_medium`
  since round 5 and this command passed neither, so a knockout screen silently ran on MICOM's
  permissive default while its sibling `search` honoured `--medium` — and its manifest recorded
  `medium_checksum: micom_default_medium` regardless. It now takes `--medium`, applies it
  identically to the baseline and to every knockout arm, and records it.
- **GUI parity**: the Host tab already offered both media, so it inherited the identical hard stop.
  It now carries an "Allow unknown medium" control that both its runs append to their argv.

### Changed

- **BREAKING (scientific): isolation is now computed against `model.boundary`, not
  `model.exchanges` or `model.medium`.** CMIG closed what it *enumerated*, and every enumeration it
  used is a strict subset of what can supply mass. `cobra` exposes three views and only one is
  complete: `model.boundary == exchanges ∪ sinks ∪ demands`. Measured on Recon3D (cobra 0.31.1):

  ```
  boundary 1806 = exchanges 1560 + sinks 101 + demands 145
  boundary able to supply mass: 1655, of which 95 are NOT in model.exchanges, each at lb = -1000
  ```

  This was one defect in five places, rediscovered in three separate review rounds. All five now
  route through one primitive, `cmig/core/boundary.py`, whose invariant is *after isolation, no
  boundary reaction may supply mass except the explicitly declared ones, at their declared bounds*
  — asserted generically (`boundary_isolation_violations`) across Recon3D, RECON1, iML1515, iYO844
  and iHN637 by driving the production paths.

  **Published numbers move. Measured on Recon3D with `BIOMASS_reaction` as the host objective and
  the bundled 3-member pool (`iML1515+iYO844+iHN637`, `cooperative_tradeoff f=0.5`, Gurobi):**

  | | host `BIOMASS_reaction` | illegal suppliers | supplying at the optimum |
  |---|---|---|---|
  | before (closed `host.exchanges`) | `368.0102475464423` | 95 | 1 `EX_`, 33 `SK_`/`DM_` |
  | before, microbial availability **ZEROED** | `368.01024754644214` | 95 | — |
  | after (closes `model.boundary`) | `0.0` | **0** | 0 |

  The two "before" values differ by ~2 ULP, not bit-identically — an earlier report overstated
  that — but the substance stands: **the published host objective was independent of the
  microbiome.** `0.0` is the correct answer, because this pool delivers only acetate, ethanol and
  currency metabolites to a generic human cell model.

  `apply_medium_translated(exact=True)` was likewise not exact: it assigned `model.medium`, and
  cobra's own setter computes `exchange_rxns = frozenset(self.exchanges)` and turns off only those.
  It now isolates the whole boundary, so `exact` means exact for the first time. `minimal_medium`
  inherited the same defect and could return a **zero-component** "minimal medium" that passed its
  own re-solve validation; it now refuses (`MILPInfeasibleError`) rather than certifying an empty
  nutrient set, and records any `forced_supply` it could not close. `dfba
  --close-untracked-uptake` could be fed by a sink with `untracked_uptake: {}` and `warnings: []`;
  it now closes and reports against the boundary, restoring the round-2 D5 guarantee.

  A merged medium (`--medium` without exact semantics) is still an *overlay* on MICOM's permissive
  default: measured on the shipped `medium_presets/western_diet.csv`, `EX_o2_m` stayed at
  `999999.0` and community growth came out `1.2677557` against `0.6990206751` with oxygen closed —
  an **81 % overestimate from one absent row**. That mode is unchanged by default, but it is no
  longer silent: `medium_application_mode` and `n_undeclared_boundary_suppliers` are recorded in
  the solve manifest's non-hashed provenance, and `search` states the count in its warnings.

  **Non-hashed provenance marker:** `boundary_isolation_policy`, value `boundary_reactions_v1` (the
  prior era is `exchange_view_v0` and has no key at all). It is stamped by the *writer* on both
  solve and workflow manifests, and `cmig inspect-run` shows it — verified end-to-end. The marker
  set now lives in one mapping (`workflow_manifest.NON_HASHED_PROVENANCE_MARKERS`) that
  `_compact_manifest` also reads, because that whitelist had already swallowed one marker
  (`host_isolation_policy` reached `manifest.json` and `inspect-run` returned `None` for it).

  **Frozen hashes are unmoved:** gurobi `29844e2910360332…cef29ab`, osqp `a422eb89d019f917…404d3d9d`;
  `golden verify-envelope` 13/13.

  **Action required:** any run that reported a host objective, a "defined medium" result, a minimal
  medium, or a `--close-untracked-uptake` dFBA on a model with sinks or demands is suspect. Human
  GEMs (Recon3D, Human-GEM, RECON1-class) ship them; the bundled microbial GEMs do not, so runs
  confined to `models/` are unaffected. A manifest with no `boundary_isolation_policy` key is from
  the old era.

- **BREAKING (scientific): host-coupling id resolution is case-preserving.** `run_bigg_host_microbe`
  built a host exchange id from the **raw** metabolite id and `solve_bigg_host` from the
  **lowercased** one. Measured: `matched_exchanges {'lac__D': 'EX_lac__D_e'}` was published while
  the LP opened `EX_lac__d_e`, which does not exist — host biomass `0.0`, `warnings: []`. BiGG
  metabolite ids are case-sensitive, so both sides now call one resolver
  (`host_coupling.host_exchange_resolver`) and the reported map and the applied bounds agree by
  construction. With a reviewed map the same input now gives `5.0`.

- **BREAKING (scientific): a MAINTENANCE objective is no longer reported as growth.** Round 5's
  objective-structure guard admitted `BIOMASS_maintenance` in silence, because the id contains the
  word "biomass" — and that is what Recon3D actually **ships as its default objective**, optimizing
  to `755.0032155506631`. A maintenance turnover rate was therefore free to be published as a growth
  rate by `model-quality`, `host-generic` and `host-benchmark` with no caveat anywhere. Maintenance
  hints (`maintenance`, `atpm`, `non-growth`/`nongrowth`/`ngam`) are now tested **before** the
  biomass hints — deliberately, since the conventional spelling of the concept ("non-growth
  associated maintenance") contains the word `growth`.

  The guard also reached only one of its call sites in the round-5 shape: `model_quality.py`,
  `model_pool.py` and `ModelSummary.as_dict()` all still passed the **count** alone, which skips
  every single-term check. Measured, `model-quality` — the one command whose entire job is to vet a
  GEM before publication — audited RECON1 (objective `S6T14g`, a Golgi sulfotransferase, optimum
  `0.0`) and emitted an **empty** objective warning; passing ids would not have helped either,
  because `getattr(str, 'id', '?')` rendered the message as "objective reaction ?". All three sites
  now pass the reactions or ids, and `objective_structure_warning` accepts either. `model_quality`'s
  `run_hash` reproduces `57283fa9b1393cfa…` bit-for-bit, so no hash moved.

  `HostModelSummary` now carries `objective_warning`, `n_boundary_reactions` and
  `n_nonexchange_boundary_uptake`, and `host-generic` / `host-benchmark` publish all three, so a
  generic GEM discloses its 95 sink/demand suppliers *before* anyone couples anything to it. The
  limitation is deliberate and worth writing down: the check is lexical, so a reduced-precursor
  biomass reaction named without the word "maintenance" is not caught, and structure does not
  separate the cases either (Recon3D's maintenance objective has 37 metabolites against growth's
  41). Of the three biomass/growth-named reactions Recon3D ships, two warn and one correctly does
  not; RECON1 ships none.

  **Non-hashed provenance marker:** `host_isolation_policy`, value `all_boundary_uptake_v2` (prior
  era `model_exchanges_only_v1`). It dates *the host-coupling answer*, where
  `boundary_isolation_policy` dates *the shared primitive*; both are members of
  `workflow_manifest.NON_HASHED_PROVENANCE_MARKERS`, so both are stamped by the writers and both
  reach `cmig inspect-run` — verified end-to-end on a workflow manifest (top level) and a solve
  manifest (inside `provenance`).

- Tracked provenance for the human GEMs: `data/gems/GEM_SOURCES.json` (retrieval date, `.xml` and
  `.xml.gz` SHA-256 and byte counts, server `Last-Modified`, structural counts, and the shipped
  default objective **with its warning**), `data/gems/README.md`, and
  `scripts/download_human_gems.py` with `--verify` / `--verify --counts`. The model bytes stay
  gitignored: BiGG is **not** under a named open licence but a custom UCSD non-commercial licence
  (`http://bigg.ucsd.edu/license`), and `bigg.ucsd.edu` serves plain HTTP only — an `https://`
  request is refused at the TCP level, so any code using `https://bigg.ucsd.edu/...` fails outright.
  `data/gems` is also now part of the human-GEM resolution order (`cmig/io/gem_paths.py`), shared by
  the CLI `--model` defaults and the tests so they cannot disagree; `tests/test_recon3d_host.py`,
  which had skipped for the project's entire life because the order never looked where the download
  lands, now runs. Its old assertion `biomass > 1.0` **passed on the maintenance optimum**, so it
  now pins the value and requires the maintenance verdict beside it.

- Round 5's objective-structure guard now reaches the host-coupling commands. `--host-objective` is
  optional, so `host-microbe-bigg`, `host-search-bigg` and `host-ko-impact` published
  `host_objective` computed on whatever the SBML shipped, with no caveat anywhere (RECON1's default
  objective is `S6T14g`, a Golgi sulfotransferase whose optimum is `0.0`). The guard is called once
  in `run_bigg_host_microbe`, which all three commands go through, and its verdict travels as
  `objective_warning` plus a `warnings` entry.

- `solve_host` refuses a model whose exchange interface it cannot classify. It implements the
  `_lumen`/`_blood` contract by closing the lumen; Recon3D exposes 1560 `EX_*` reactions in neither
  interface, so the closure matched none of them and the LP ran with the whole boundary open —
  and because Recon3D has `ATPM` it passed the maintenance check and returned `viable=True` off a
  phantom-fed objective. It now returns `host_interface_absent` and names `solve_generic_host` /
  `solve_bigg_host` as the right entry points for a generic GEM.

- **BREAKING (scientific): `--medium` now actually applies.** `apply_medium_checked` gated on
  `model.medium`, which lists only *currently open* uptakes, so a closed exchange could never be
  opened — roughly 90% of nutrients (acetate, butyrate, lactate, succinate, glycerol) were
  unreachable. Under `--allow-unknown-medium` they were dropped silently while the manifest still
  recorded the requested `medium_checksum` and minted a distinct `run_hash`, publishing a run as
  being on a medium it never used. Every consumer (`solve`, `search` and all multi-target
  variants, `host-microbe-bigg`, `abundance-impact`, and the GUI via `EngineService`) now shares
  the one metabolite-keyed path that `strain-growth` already used.

  **This changes published numbers without changing `run_hash`.** Measured on identical inputs:
  `solve --medium` growth `0.881561` → `1.125065` and `search --medium` target flux `18.13` →
  `13.64`, both under a byte-identical hash. The discontinuity cannot be encoded in a hash
  component (`cmig_core_version` is frozen), so runs are now stamped with a **non-hashed**
  `medium_policy` marker — `provenance.medium_policy` in a solve manifest and a top-level
  `medium_policy` in a workflow manifest — whose value moved from `open_uptakes_exact_key_v1` to
  `exchange_reactions_by_metabolite_v2`.

  **Action required:** any run produced before this change with `--medium` is suspect; its
  `medium_checksum` describes a medium that was only partially applied, or not applied at all.
  Re-run it. A manifest with no `medium_policy` key is from the old era.

- A medium file that gives two namespace aliases of one metabolite (`EX_ac_e` and `EX_ac_m`)
  different uptake limits is now refused as an input error (exit 2). Previously the last row
  silently won, so reordering identical CSV rows changed community growth `1.125065` → `0.954612`
  while `medium_checksum` — which sorts, and hashes both rows — stayed byte-identical. Aliases
  that request the *same* limit are merged and are unaffected.


- Cross-feeding allocation now conserves shared-pool supply and demand.
- Multi-target search returns one jointly feasible flux vector.
- Namespace review is mandatory unless the BiGG assumption is explicit.
- Run manifests now capture analysis settings, dependency versions, individual model checksums, and
  applied namespace mappings.
- Model-directory discovery now distinguishes COBRA JSON models from adjacent provenance and
  analysis JSON files.
- Weighted host ranking now requires explicit reference scales and combines only dimensionless
  normalized quantities; single-metric target transfer is the default.
- Deterministic sweep conditions no longer generate p-values without confirmed independent
  replicate IDs.

### Added

- `manifest.json` for every workflow kind now carries a **`result_digest`**: a sha256 over the
  artifact bytes the run produced, with a per-artifact breakdown. `run_hash` certifies the
  *inputs*; `result_digest` certifies the *answer*. Neither implies the other, and the gap between
  them was exploitable — three changes to `build_host_map` (capping reported entries, capping the
  host index, dropping currency metabolites) each rewrote the real interface map on real GEMs
  (67 entries → 22, → 62, and 144 → 73 on a larger host) while `run_hash`, `map_spec` and the
  matching-behaviour digest stayed bit-identical. `cmig inspect-run` recomputes the digest from the
  files on disk and reports a mismatch loudly, which also catches an artifact edited, truncated or
  deleted after the run. **`result_digest` is outside the input hash**, so no published `run_hash`
  moves because of it. `cross_run_comparable` marks the kinds whose artifacts have been *measured*
  byte-deterministic (currently `host_map`), so a digest difference between two runs of those kinds
  is a finding rather than noise.

### Fixed

- **The `strain-growth` figure turned "never measured" into a measured zero.** `single` and
  `community` bar heights were built with `_optional_float(...) or 0.0`, so a member whose
  alone-solve raised (`single_growth: null`, `single_status: "failed"`) was drawn as a zero-height
  "Single model" bar beside a real "Community" bar — which reads as obligate syntrophy, a
  biological conclusion invented by a plotting default. Every other layer of the command was
  already honest (blank CSV cell, `null` in JSON, degraded summary tier, a run-level warning naming
  the member, an em dash in the GUI table); only `strain_growth_plot.svg`/`.tiff` — the artifacts
  that go in a manuscript — fabricated. An unmeasured leg is now NaN (no bar drawn), each omitted
  bar is labelled "not evaluable" in place, and the title states `N of M members not evaluable`.
  A genuinely measured zero is still drawn as zero.
- **`sweep` certified an all-failed grid as `status: "ok"`, and exited 0.** The summary carried a
  hard-coded literal and the manifest derived `"ok" if rows else "failed"` — but a failed condition
  *stays* in `rows` by `core/sweep.py`'s no-drop contract, so the `failed` branch was reachable only
  for an empty grid. Reproduced with an ordinary medium file and no flags: every condition
  `status: failed` with `value: NaN` in `sweep.parquet`, while the summary, the manifest,
  `inspect-run` and `$?` all said ok with no warning printed. The run-level tier is now derived from
  the per-condition statuses (all failed → `failed`, some failed → `degraded`), the failed
  condition ids are named in `warnings` and printed, `sweep_summary.json` gains `n_ok`/`n_failed`,
  and **`sweep` now exits 3 when every condition failed** (`--allow-failed-run` waives the exit
  code, never the recorded status). `run_hash` is unchanged — none of these fields is hashed.
- **`host-search-bigg` ranked and plotted a non-optimal host LP as an evaluated result.**
  `evaluation_status` was the literal `"ok"` in the success branch, but
  `core/host_coupling.solve_bigg_host` *returns* `HostSolveResult(False, status, 0.0, …)` for a
  non-optimal host LP rather than raising — so that branch was taken, `host_objective` became a
  fabricated `0.0`, and the candidate was ranked with `n_candidates_failed: 0`, painted in the
  "evaluated ok" colour and exited 0, while the same row's `warnings` cell read "the reported host
  objective is not a result". `evaluation_status` is now derived from the community and host solve
  statuses (matching the sibling `host-microbe-bigg`), an unevaluable candidate publishes NaN rather
  than `0.0` in every scientific field and moves to the `unevaluated` block, and the ranking figure
  states `N of M candidates not evaluable (excluded)`.
- **`inspect-run` claimed to certify artifact bytes it did not check.** `result_digest` only digests
  the artifacts the *manifest* declares, and no workflow declared its publication figures — so a
  `gene_ko_plot.svg` overwritten with `<svg>FABRICATED FIGURE</svg>` still printed
  "certifies the ARTIFACT BYTES — verified", with the tampered file listed under `artifacts:` in the
  same output. Meanwhile each summary JSON's own `artifacts` field *did* list the figures, so the two
  lists in one run directory disagreed. Every workflow writer now returns the artifact list it
  actually wrote and the manifest declares exactly that list, so the two agree by construction and
  the figures are covered by `result_digest`. `run_hash` is unchanged (`artifacts` is not a hash
  component); `result_digest` values move for every kind that writes a figure.
- **A detected `result_digest` mismatch did not reach `status`, `$?` or `--format json`.** The
  mismatch was reported loudly on stderr — but only in the text branch, while the payload said
  `status: "ok"` beside `result_digest.match: false` and the command exited 0. Any gate written
  against `status` or `$?` (as `SKILL.md`'s mandated verification step is) accepted a run whose
  artifacts are not the artifacts its manifest fingerprinted. `inspect-run` now reports
  `artifact_integrity: verified | mismatch | not_recorded`, reports `status: failed` with
  `status_source: result_digest_mismatch` on a mismatch (the manifest's own status stays readable
  under `manifest.status`), emits the stderr block in **both** output formats, and **exits 3**. A
  failed *solve* still exits 0 here — `inspect-run` reports on a run, it does not re-judge it.
  `inspect-run`'s payload `schema_version` moves 1.0 → 1.1.
- `inspect-run` dropped the signals the manifest already recorded. `_compact_manifest` whitelisted
  12 keys, so the `medium_unapplied` diagnostic naming dropped nutrients, the `medium_policy` marker
  created for the `--medium` discontinuity above, `provenance`, `warnings` and the summary *values*
  (only the key names were listed) were all invisible to the tool's own inspection command. All five
  are now surfaced.
- `provenance.medium_policy` in a solve manifest is now stamped writer-last, so a caller passing its
  own `medium_policy` key cannot silently overwrite it — the adjacent comment claimed as much, but
  the dict ordering said otherwise.
- A gene knockout whose solve *raised* was published as the screen's strongest result. The
  exception handler wrote `score: 0.0` and `score_delta: -baseline.score` — a finite,
  large-magnitude, entirely plausible effect size that was never measured — and the writer
  numbered every row it was given, so the failure reached `gene_ko_rankings.csv` as rank 1 and was
  printed as "rank 1 (largest effect)". An unevaluated knockout now carries NaN in every
  scientific field (blank in CSV, null in JSON), takes `rank 0` = "no rank", is published under
  `unevaluated` rather than `top_ranked`, and the rank-1 headline is suppressed when nothing was
  evaluable. `gene_ko_summary.json`'s `status` is derived from the rows instead of being the
  literal `"ok"` it always was. This aligns the gene-KO artifacts with the convention the four
  search paths already used, so one rule — "is `rank` nonzero?" — answers "was this row measured?"
  everywhere.
- **Breaking for published `host_map`, `host_microbe_bigg`, `host_search_bigg`, `host_ko_impact`
  and `publication_benchmark` run_hashes** (five kinds — see the two entries below for which change
  moves which). Re-derive any published run_hash of these kinds against this release.
- The host-map matching policy recorded in `map_spec` described the matcher instead of deriving
  from it: `match_order`, `secretion_criterion`, `annotation_requires_unique_target` and
  `annotation_sources` were inert literals no code path read, guarded only by a hand-bumped
  `HOST_MAP_MATCH_POLICY_VERSION`. Changing one comparison in `build_host_map` took the
  auto-admitted interface map from 67 entries to 11 while `run_hash` stayed bit-identical, and the
  manifest's own `summary.interface_map_checksum` moved underneath it. `map_spec` now carries
  `match_behavior`, a digest of what the matcher and the id normalizer actually do to a frozen
  probe fixture (`cmig.core.host_map_probe`), and the four constants above now drive the matcher
  rather than merely describing it. **This narrows the gap; it does not close it.** The probe
  measures one small synthetic instance, so a change keyed on *scale* (a cap) or on *real BiGG
  vocabulary* (a currency-metabolite filter) can still leave `match_behavior` unmoved — that is
  what `result_digest` above is for. What is guaranteed: any change to the matching *rules the
  probe exercises* moves the `host_map` hash, and any change to the produced artifacts moves
  `result_digest`. Moves `host_map` and `publication_benchmark`. The produced interface maps are
  unchanged by this release; only the fingerprint over them is.
- `host_spec` hashed the *path* used to reach each file alongside the checksum that already pinned
  its bytes, so the same host model reached by an absolute path — or from a different working
  directory — fingerprinted as a different run. Only the file name is hashed now. Moves all five
  kinds that record `host_spec`: `host_microbe_bigg`, `host_search_bigg`, `host_ko_impact`,
  `host_map`, `publication_benchmark`.
- The osqp golden fixture no longer reproduced its own published hash. It stored components
  pre-rounded at 6 decimals while recording `golden_decimals: 4`, so `a422eb89…` was an artifact
  no code path re-derived; nothing in the suite re-derived a golden from its own stored
  components, and `golden verify` compared only `micom_version`, so it had been invisible. The
  three stored abundances are corrected to 4 decimals, which makes the fixture self-consistent
  **without moving the published hash** — `a422eb89…` still verifies, and now genuinely
  reproduces. `golden verify` compares run_hashes as well as versions, and
  `test_each_shipped_golden_re_derives_its_own_run_hash_at_its_own_decimals` asserts the invariant
  for every declared solver variant rather than for gurobi alone (the blind spot that let this
  through: every hash pin in the suite was gurobi-only). The gurobi golden `29844e29…` is
  unaffected and re-derives exactly.
- **The id normalizer destroyed D/L stereochemistry, and the manifest recorded that as policy.**
  `_normalize_metabolite_id` stripped any trailing `__<Uppercase>` token as a MICOM taxon suffix,
  but BiGG writes stereoisomers exactly that way, so `lac__D_e` and `lac__L_e` both normalized to
  `lac` — as did `glc__D`, the most common carbon source in the bundled models. Because
  `solve_bigg_host` normalizes both the reviewed interface-map keys and the microbial
  availability, a reviewed D-isomer mapping matched L-isomer availability and opened the D
  exchange: the host took up, and grew on, a molecule it cannot transport. The descriptor is now
  preserved (`lac__D_e` → `lac__d`, `lac__L_e` → `lac__l`) while genuine taxon suffixes are still
  stripped (`EX_ac_m__Escherichia_coli` → `ac`), the discriminator being token length rather than
  case. **Breaking for published `host_map` and `publication_benchmark` run_hashes:**
  `map_spec.id_normalization.uppercase_stereoisomer_suffix_folded` was `true` and is now `false`,
  and it is measured off the live normalizer rather than restated, so it cannot go stale again.
  The matching-behaviour digest moved with it
  (`sha256:70782b1b…` → `sha256:36059e16…`). Re-derive any published run_hash of these two kinds.
- Envelope-golden component fixtures are now **built by the same builders real runs use**
  (`medium_component`, `host_spec_component`, `host_map_policy`, `bundle_component`) instead of
  being transcribed as literals. A transcribed literal made the drift gate certify a *copy* of the
  contract: the `host_spec` change above moved five kinds' published hashes and the gate stayed
  silent, because its `host_spec` fixture was a hand-written dict no builder ever touched.
- The `publication_benchmark` bundle refused to carry a workflow-scope `manifest.json` as its
  `community_solve` child hash, and solve manifests now state `manifest_scope: "solve"` instead of
  leaving a reader to infer scope from a missing key (outside the hash; no solve run_hash moves).
- The workflow-envelope drift gate now also fails when a component fixture is edited without
  re-blessing; previously a changed fixture value left the golden pinning a shape the code no
  longer produced while the gate still reported every kind OK.
- Anaerobic minimal-medium validation and essential-component labeling.
- Host microbial/host biomass scaling and non-identifiable transfer claims.
- Solver `None` results now become per-candidate diagnostics instead of aborting a search.

## [0.1.0] - 2026-07-10

- Initial research software release baseline.
