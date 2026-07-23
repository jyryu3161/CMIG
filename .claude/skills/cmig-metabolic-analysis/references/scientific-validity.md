# CMIG scientific-validity guardrails (중요한 지점)

CMIG encodes the scientific choices that make a metabolic result defensible as
**explicit, mostly mandatory** CLI flags. This file explains *why* each one
exists and how to set it. Read it before any host-microbe run, any weighted
ranking, any dFBA interpretation, or any publication run. The unifying rule:
**a run that skipped a guardrail is not a result — it is a number that looks
like one.** Report the choice you made, don't route around it.

## 1. Host-microbe biomass basis — mandatory, no default

**Why.** Microbial fluxes and host-specific fluxes live on different biomass
scales. A microbial exchange in mmol · gDW⁻¹ · h⁻¹ and a host flux cannot be
compared or transferred without knowing the gram-dry-weight (gDW) basis each is
expressed on. If you skip this, the coupling silently compares incommensurable
quantities.

**What CMIG requires.** `host-microbe-bigg` and `host-search-bigg` have **no
biomass default**. You must pass all of:

- `--microbial-biomass-gdw <positive>` — study microbial dry mass in gDW.
- `--host-biomass-gdw <positive>` — host dry-mass basis represented by the host
  fluxes in gDW.
- `--biomass-basis-kind measured|literature|validation`.
- `--biomass-basis-source "<measurement record, Methods section, or citation>"`.

**The `validation` trap.** `--biomass-basis-kind validation` exists only so
software tests can run without a real basis. It makes CMIG stamp the result
**"biomass basis is validation-only; result is not publication-ready"** in the
run `warnings` and sets `publication_ready` false. Never present a `validation`
run as a scientific finding. For real work use `measured` (you have the dry
masses) or `literature` (you cite them), and put the actual source in
`--biomass-basis-source`.

## 2. Interface maps are computational suggestions, not ground truth

**Why.** CMIG matches host and microbial metabolites using metabolite
annotations and normalized BiGG identifiers. That is a good first pass, but
annotation matches are *guesses* — wrong or missing annotations produce wrong
edges, and a wrong edge is a fabricated interaction.

**What to do.** For a publication host-microbe run:

1. Generate a candidate map: `uv run cmig host-map ...`.
2. Have a human review it — confirm each mapped metabolite pair is real, drop
   spurious matches, add known ones the annotations missed.
3. Pass the reviewed file back with `--interface-map reviewed_map.json`.

Do not treat the auto-generated mapping as final, and say in the result whether
the map was reviewed.

## 3. Never add quantities with different units (weighted ranking)

**Why.** Ranking combinations by a host objective *plus* a target transfer
means adding two quantities that generally have different units and magnitudes.
Adding them raw is meaningless and lets the larger-magnitude term dominate for
non-scientific reasons.

**What CMIG requires.** `host-search-bigg --metric weighted` refuses to run
unless you supply positive, finite:

- `--host-weight`, `--target-weight` — relative importance, and
- `--host-reference`, `--target-reference` — reference scales that
  nondimensionalize each term.

The score becomes `host_weight · host_objective / host_reference +
target_weight · target_transfer / target_reference`, which is dimensionless. If
you cannot justify reference scales, **do not invent them** — rank by
`--metric target_transfer` or `--metric objective_value` instead, which use a
single well-defined quantity.

## 4. Solver provenance — approximate ≠ exact

**Why.** The solver determines whether a reported flux is an exact optimum or a
QP approximation. Reporting an approximate number as if it were exact
misrepresents precision.

**The matrix** (`uv run cmig solvers` shows availability):

- `gurobi` — canonical **full-flux** workflow. Required for community FVA and
  for the host / search product workflows. Default for publication runs.
- `osqp` — **QP-only approximate** provenance for supported community solves.
  Useful when Gurobi is unavailable, but every number it produces is
  approximate.

Always report which solver produced a result. CMIG records solver choice and
flux provenance in the run outputs so cached or published results stay
interpretable — surface it, don't bury it.

## 5. dFBA endpoints require a sensitivity audit

**Why.** A well-mixed dFBA trajectory is a numerical integration. Its endpoint
can shift with the integration step `--dt` and the uptake half-saturation
constant `--km`. A single coarse-step run can report an endpoint that a finer
step would contradict.

**What to do.** Before interpreting or reporting a dFBA endpoint, run
`cmig dfba-sensitivity` across a range of `--dts` and `--kms`. It returns every
run plus integration mass-balance residuals, so you can confirm the endpoint is
stable rather than a step-size artifact. Also: `--initial` values are **strict**
— they must exist in the model; a typo'd exchange id is an error, not a silent
skip.

## 6. Knockout screens must not silently sample a subset

**Why.** If a gene-KO screen quietly evaluated only some genes, its "top
knockouts" ranking is misleading — you cannot tell whether the real best target
was simply never tested.

**What CMIG does.** In `gene-ko-search`:

- `--max-genes 0` evaluates **every** target (prefer this for a complete
  screen).
- If `--max-genes` truncates, CMIG writes an explicit `warnings` entry and
  records `n_genes_total`, so truncation is never invisible.
- `--gene-selection id|random` with `--seed` makes any truncated subset
  reproducible.

If you cap the screen, surface the warning and the evaluated-of-total count in
your summary; don't present a capped screen as exhaustive.

## 7. Know what a tool does *not* do

- **`spatial-preview` is a medium-design tool.** It previews 2D
  source/sink/diffusion layouts to help design a run. It does **not** solve FBA
  on each grid cell and is not spatial community dFBA. Never describe its output
  as spatial simulation results.
- **`abundance-impact` is sensitivity, not causality.** It rescales one member's
  abundance under the same model set and medium and recomputes the community. It
  quantifies how outputs respond to that ratio — it is not evidence of ecological
  causation.
- **CMIG does not fetch models.** It never downloads or auto-selects AGORA / VMH
  / Recon / Human-GEM / BiGG catalogues. Users provide local SBML/JSON/MAT GEMs.
  If a request assumes auto-download, correct it.

## 8. Reproducibility is part of validity

A result you cannot reproduce is not defensible. CMIG supports this directly:

- Every analysis run emits a **manifest** and, where applicable, a **run hash**.
- `cmig inspect-run --format json` reads them back in a stable schema.
- `cmig golden verify` is the MICOM-version regression gate — run it when the
  environment changes to confirm results still match the golden fixture.
- `cmig publication-benchmark` bundles the quality audit, a community solve,
  search, optional dFBA sensitivity, and optional host coupling into a single
  checksummed manifest with a `publication_ready` flag.

When you report a run, include its `status`, `run_hash`, and the solver — those
three are what let someone else trust and reproduce it.
