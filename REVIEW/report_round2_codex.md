# CMIG round-2 independent functional re-evaluation — R2-B / Codex

Date: 2026-07-25 (Asia/Seoul)  
Working tree: current shared working tree on `main`, base commit
`d3e90d73325236bdc8501785defda2a4b84b7b97`  
Evaluator output roots: `runs/r2codex/`, `REVIEW/scratch_r2codex/`  
Source/tests edited by this evaluator: none

I read `REVIEW/ROUND2_BRIEF.md` first and did not read any other round-2
report. All CMIG commands used `./.venv/bin/cmig`; all Python commands used
`./.venv/bin/python`. I did not install or synchronize the environment.

## Executive conclusion

| Scenario | Verdict | End to end? | Strongest positive evidence | Blocking gap |
|---|---|---:|---|---|
| S1 — best SCFA-producing combination | **PARTIAL** | Yes, for three small models and all three scoring modes | Exhaustive pair search evaluated 3/3 candidates; `carbon_equivalent` declares `mmol C gDW^-1 h^-1`, uses model-derived carbon numbers, and returns a single jointly feasible flux vector. Missing targets, non-optimal candidates, ties, and zero-score degeneracy all generated warnings. | The tested pools still had non-optimal candidates, so the reported winner was only the best evaluable candidate. Unevaluable rows still receive numeric ranks and appear in `top_ranked`; the single-target path is worse and can call a failed zero-flux candidate “best” while reporting top-level `ok`. The `scfa` preset also includes lactate and succinate, so it is broader than the conventional core SCFAs. |
| S2 — microbe–microbe interaction | **PARTIAL** | Yes for steady-state solve, strain growth, abundance sweep, and single-model dFBA | A real three-member solve produced 96 edges, including 16 allocated cross-feeding edges; strain growth and four abundance points completed; dFBA produced a six-point time course and exact integration residuals of 0. | Pairwise cross-feeding rows are proportional shared-pool allocations but the artifact has no `identifiable` or `allocation_method` field. The same-medium fix fails on actual `_m` versus `_e` exchange namespaces: strict mode made all three single legs fail while top-level status stayed `optimal`; permissive mode claimed the media matched although the requested exchange was absent from every single model. dFBA is single-model only and allowed growth on untracked default nutrients. |
| S3 — microbial perturbation to host-objective effect | **NOT SUPPORTED** | No supported integrated path | Direct coupling itself works: a validation-only synthetic ethanol host received 3.4041441969 mmol gDW-host^-1 h^-1 and reached objective 9.2124325907. The KO screen separately found that reaction `ETOHt` changes target-max ethanol flux from 9.6197351769 to 0. | `gene-ko-search` emits no modified model and no host fields; `host-microbe-bigg` accepts no gene/reaction/inhibition perturbation or baseline comparison. Only ad hoc Python model editing connected them. The manually knocked-out host run became infeasible, correctly making 0 “not a result,” so there was no supported numeric host delta \(Y\). |

Overall, CMIG is useful as a **screening and exploratory analysis tool**, but
the three requested scientific claims are not all supported. S1 now has a
meaningful absolute score option, but ranking/status semantics still need
repair. S2 exposes useful analyses but does not yet support controlled causal
interaction claims. S3 lacks the required perturbation-to-host workflow.

The generated figures are **not publication-ready for Nature Genetics / Claude
Science**. Vector SVGs are present and the palette is generally readable, but
the files omit units and panel letters, TIFFs are raw uncompressed RGBA, and
several layouts are visibly defective or semantically incomplete.

## Recent-fix verification

| Required fix | Result | Evidence |
|---|---|---|
| Solver failure degrades gracefully, no raw traceback | **PASS in tested paths** | Five focused solver-guard tests passed. A real target LP returned `infeasible` and a real host LP returned `infeasible`; both commands exited 0, wrote diagnostics, and showed no traceback. The host run's top-level status was `failed`. |
| Unevaluable candidates are not ranked as zeros | **FAIL / incomplete** | Multi-target scores are blank/`null`, not numeric zero, which is good; however the two unevaluable candidates still received ranks 2 and 3 and were included in `top_ranked`. In single-target repro `regression_single_status`, a failed candidate received rank 1, target flux 0, was printed as “best,” and the run reported `ok`. |
| Top-level status reflects worst sub-status | **FAIL across workflows** | Multi-target search correctly reported `degraded`; host coupling correctly reported `failed` when host was infeasible. But single-target search reported `ok` over a failed rank, and strict `strain-growth` reported `optimal` while all three single legs were `failed`. Static inspection also found `abundance-impact` uses “any row optimal” rather than the worst row. |
| `strain-growth` applies the same medium to both legs | **FAIL scientifically; partial mechanically** | The same `MediumSpec` object is passed to both legs. On real models, the community accepts `EX_glc__D_m`, while each single model uses an `_e` namespace. Strict mode fails all single legs. With `--allow-unknown-medium`, all three rows say the exchange was absent, yet `single_medium_applied=true`, `single_medium_equals_community_medium=true`, and warnings are empty. This is not a controlled effective-medium comparison. |

## Evidence log

Wall time is `/usr/bin/time -p` real time. Every command below exited with the
shown code. Helper reads that only displayed an existing JSON/CSV are not
treated as new simulations.

### Discovery and environment

| ID | Exact command | Exit | Wall | Observed |
|---|---|---:|---:|---|
| D1 | `./.venv/bin/cmig workflows --format json` (timed as `/usr/bin/time -p ./.venv/bin/cmig workflows --format json`) | 0 | 0.04 s | Workflow map listed `search`, `strain-growth`, `abundance-impact`, `dfba`, `gene-ko-search`, `host-microbe-bigg`, `host-search-bigg`, and `inspect-run`. |
| D2 | `./.venv/bin/python -c "import cobra,micom,sys; import gurobipy; print('python',sys.version.split()[0]); print('cobra',cobra.__version__); print('micom',micom.__version__); print('gurobi',gurobipy.gurobi.version())"` | 0 | 1.1 s tool wall | Python 3.12.11, cobra 0.31.1, micom 0.39.0, Gurobi 12.0.3. Runtime output confirmed the academic license expires 2027-05-27. |
| D3 | `find models models_human medium_presets -maxdepth 2 -type f -print` | 1 | <0.1 s | Five microbial models and two medium CSVs were present; `models_human` did not exist. |

The three-model evaluation pool was iHN637 (785 reactions), iYO844 (1,250),
and iAF987 (1,285). Exchange inspection found:

- iHN637: acetate, butyrate, D-lactate, and L-lactate exchanges; no propionate
  or succinate exchange.
- iYO844: acetate, L-lactate, propionate, and succinate exchanges; no
  butyrate or D-lactate exchange.
- iAF987: acetate, butyrate, and propionate exchanges; no lactate or succinate
  exchange.

All six preset targets had a readable carbon formula somewhere in the pool.

### S1 — SCFA combination search

| ID | Exact command | Exit | Wall | Key observed result | Artifact |
|---|---|---:|---:|---|---|
| S1.1 | `./.venv/bin/cmig search --model-dir REVIEW/scratch_r2codex/models_small --target-preset scfa --multi-metric carbon_equivalent --min-size 2 --max-size 2 --strategy exhaustive --top-k 10 --medium medium_presets/high_fiber.csv --out runs/r2codex/s1_scfa_carbon` | 0 | 123.91 s | Evaluated 3/3, but ranked 1. iHN637+iYO844: score 28.9631129237 mmol C gDW^-1 h^-1, acetate 14.4815564618, community growth 0.3563316461; every other SCFA flux was 0. iAF987+iHN637 failed medium application; iAF987+iYO844 target LP was infeasible. | `runs/r2codex/s1_scfa_carbon/` |
| S1.1i | `./.venv/bin/cmig inspect-run --run-dir runs/r2codex/s1_scfa_carbon --format json` | 0 | 0.04 s | `status=degraded`, `status_source=summary`; only three artifacts (taxonomy, rankings, summary). | Same |
| S1.2 | `./.venv/bin/cmig search --model-dir REVIEW/scratch_r2codex/models_small --target-preset scfa --multi-metric carbon_equivalent --min-size 2 --max-size 2 --strategy exhaustive --top-k 10 --out runs/r2codex/s1_scfa_carbon_default` | 0 | 151.73 s | Evaluated 3/3, ranked 2. Winner iHN637+iYO844: 24.2239185513 mmol C gDW^-1 h^-1, acetate 12.1119592757, growth 0.2969975376. iAF987+iHN637: 10.2354913420, missing succinate; iAF987+iYO844 infeasible. | `runs/r2codex/s1_scfa_carbon_default/` |
| S1.2i | `./.venv/bin/cmig inspect-run --run-dir runs/r2codex/s1_scfa_carbon_default --format json` | 0 | 0.04 s | `status=degraded`. | Same |
| S1.3 | `./.venv/bin/cmig search --model-dir REVIEW/scratch_r2codex/models_best_pair --target-preset scfa --multi-metric normalized_weighted --min-size 2 --max-size 2 --strategy exhaustive --top-k 10 --out runs/r2codex/s1_scfa_normalized_one` | 0 | 45.26 s | One candidate; acetate flux 12.1119592750 but normalized score 0 because every capability range had zero width. Both the candidate-relative warning and the all-zero/arbitrary-ranking warning were emitted. | `runs/r2codex/s1_scfa_normalized_one/` |
| S1.3i | `./.venv/bin/cmig inspect-run --run-dir runs/r2codex/s1_scfa_normalized_one --format json` | 0 | 0.04 s | `status=ok`. | Same |
| S1.4 | `./.venv/bin/cmig search --model-dir REVIEW/scratch_r2codex/models_best_pair --target-preset scfa --multi-metric raw_sum --min-size 2 --max-size 2 --strategy exhaustive --top-k 10 --out runs/r2codex/s1_scfa_raw_one` | 0 | 44.94 s | Same candidate and joint flux vector; score 12.1119592750 mmol gDW^-1 h^-1. It ignores carbon-number differences; here only acetate was nonzero, so `carbon_equivalent` was approximately twice the raw molar score (minor solver-level numerical variation). | `runs/r2codex/s1_scfa_raw_one/` |
| S1.4i | `./.venv/bin/cmig inspect-run --run-dir runs/r2codex/s1_scfa_raw_one --format json` | 0 | 0.04 s | `status=ok`. | Same |
| S1.5 | `./.venv/bin/cmig search --taxonomy REVIEW/scratch_r2codex/tie_taxonomy.csv --target ac --min-size 1 --max-size 1 --strategy exhaustive --top-k 10 --out runs/r2codex/s1_tie_repro2` | 0 | 7.06 s | Two identical models tied at score 12.148; warning: “top-2 candidates tied … rank 1 is the first tie … not a unique optimum.” | `runs/r2codex/s1_tie_repro2/` |
| S1.5i | `./.venv/bin/cmig inspect-run --run-dir runs/r2codex/s1_tie_repro2 --format json` | 0 | 0.04 s | `status=ok`; SVG and TIFF search figures were present. | Same |
| S1.6 | `./.venv/bin/cmig search --model-dir REVIEW/scratch_r2codex/models_iaf --target ac --min-size 1 --max-size 1 --strategy exhaustive --top-k 10 --medium medium_presets/high_fiber.csv --out runs/r2codex/regression_single_status` | 0 | 4.74 s | Sole candidate failed because `EX_glc__D_m` was absent; CLI still printed `best: iAF987 flux=0 growth=0`. JSON assigned rank 1, score `null`, candidate status `failed`, but top-level status `ok`. | `runs/r2codex/regression_single_status/` |
| S1.6i | `./.venv/bin/cmig inspect-run --run-dir runs/r2codex/regression_single_status --format json` | 0 | 0.04 s | Incorrectly returned `status=ok`, `status_source=summary`. | Same |

#### S1 interpretation

`carbon_equivalent` is the best of the three metrics for a “total carbon in
secreted acids” question. The output records carbon counts
ac=2, but=4, lac__D=3, lac__L=3, ppa=3, succ=4, their source metabolites, the
unit, and `solution_semantics=joint_weighted_lp_single_flux_vector`. This is a
real physical flux sum and is comparable across runs with the same model
normalization, medium, growth fraction, targets, and weights.

It is not automatically “total SCFA molecules.” `raw_sum` answers that molar
sum but weights C2 and C4 acids equally. `normalized_weighted` is explicitly
candidate-set-relative and can collapse a real nonzero producer to score 0, as
observed. The all-zero warning worked, although its wording was factually wrong
for S1.3: it said no candidate achieved a nonzero target flux even though
acetate flux was 12.1119592750; the zero was the normalized score.

The best observed pair was consistently iHN637+iYO844, but it cannot be called
the global best of this tested pool without qualification because one pair was
not evaluable. Exclusions were not silent: diagnostics, warnings, blank scores,
and degraded status were present. However, assigning ranks 2/3 to those rows
and putting them in `top_ranked` contradicts the warning that they are excluded
from ranking.

The preset itself also needs scientific naming review. Acetate, propionate, and
butyrate are core SCFAs; lactate is a hydroxy acid and succinate is a
dicarboxylate. A broader “fermentation acids” preset is reasonable, but calling
all six “SCFA” can change the biological question.

### S2 — interaction, strain growth, abundance, dFBA

| ID | Exact command | Exit | Wall | Key observed result | Artifact |
|---|---|---:|---:|---|---|
| S2.1 | `./.venv/bin/cmig solve --taxonomy REVIEW/scratch_r2codex/small_taxonomy.csv --medium medium_presets/high_fiber.csv --allow-unknown-medium --assume-bigg-namespace --solver gurobi --tradeoff-f 0.5 --targets scfa --out runs/r2codex/s2_community_solve` | 0 | 18.77 s | Community growth 0.4447987331. `edges.parquet`: 96 edges, 16 `cross_feeding`. Largest were iYO844→iAF987 h2o 7.2796734407 and acetate 6.5218170447; iHN637→iAF987 acetate 0.3181829553. `target_summary.json` was empty. | `runs/r2codex/s2_community_solve/` |
| S2.1i | `./.venv/bin/cmig inspect-run --run-dir runs/r2codex/s2_community_solve --format json` | 0 | 0.04 s | `status=ok` derived from the manifest; full-flux Gurobi solve recorded. | Same |
| S2.2 | `./.venv/bin/cmig strain-growth --model-dir REVIEW/scratch_r2codex/models_small --medium medium_presets/high_fiber.csv --allow-unknown-medium --tradeoff-f 0.5 --out runs/r2codex/s2_strain_growth` | 0 | 22.30 s | Community growth 0.4447987331. Alone→community member growth: iAF987 0.0473224351→0.0371633428; iHN637 0.2244545421→0.6459983577; iYO844 0.1179663893→0.6512344988. Every row diagnosed absent `EX_glc__D_m`, yet all said `single_medium_applied=true`; summary claimed media equal and had no warning. | `runs/r2codex/s2_strain_growth/` |
| S2.2i | `./.venv/bin/cmig inspect-run --run-dir runs/r2codex/s2_strain_growth --format json` | 0 | 0.04 s | `status=optimal`. | Same |
| S2.3 | `./.venv/bin/cmig strain-growth --model-dir REVIEW/scratch_r2codex/models_small --medium medium_presets/high_fiber.csv --tradeoff-f 0.5 --out runs/r2codex/regression_strain_strict_status` | 0 | 22.04 s | Community remained optimal at 0.4447987331; all three single legs failed, single growth was `null`, and `single_medium_equals_community_medium=false`. Warning correctly said the difference was not attributable to interaction. | `runs/r2codex/regression_strain_strict_status/` |
| S2.3i | `./.venv/bin/cmig inspect-run --run-dir runs/r2codex/regression_strain_strict_status --format json` | 0 | 0.04 s | Incorrectly returned top-level `status=optimal` despite all three failed single sub-statuses. | Same |
| S2.4 | `./.venv/bin/cmig abundance-impact --model-dir REVIEW/scratch_r2codex/models_small --member iHN637 --fractions 0.1,0.33,0.6,0.9 --target ac --medium medium_presets/high_fiber.csv --allow-unknown-medium --tradeoff-f 0.5 --out runs/r2codex/s2_abundance` | 0 | 70.01 s | All four solves optimal. At fractions 0.1/0.33/0.6/0.9: community growth 0.4356937730/0.4446395704/0.3993228052/0.2348261303; community acetate 0.4534511789/0/11.7818779237/0; target-member acetate 1.0243604117/0.3318046799/23.5950272931/0.2746234146. | `runs/r2codex/s2_abundance/` |
| S2.4i | `./.venv/bin/cmig inspect-run --run-dir runs/r2codex/s2_abundance --format json` | 0 | 0.04 s | `status=ok`. | Same |
| S2.5 | `./.venv/bin/cmig dfba --model models/iHN637.xml --solver gurobi --t-end 1.0 --dt 0.2 --initial-biomass 0.05 --out runs/r2codex/s2_dfba` | 0 | 2.24 s | `completed`, 6 time points. Biomass 0.05→0.0622765802; growth rate 0.2244545421; acetate 0→0.5084478501; tracked glucose stayed exactly 10.0. Balance audit: max biomass residual 0, max concentration residual 0, concentrations nonnegative. | `runs/r2codex/s2_dfba/` |
| S2.5i | `./.venv/bin/cmig inspect-run --run-dir runs/r2codex/s2_dfba --format json` | 0 | 0.04 s | `status=completed`. | Same |

#### S2 interpretation

The interaction edge weights are not observations of a donor-to-recipient
transfer. Source inspection shows `allocate_cross_feeding` distributes
`min(total secretion,total uptake)` proportionally over all compatible donors
and consumers. The method is mass-conserving and deterministic, but the actual
Parquet schema contains only `source_id,target_id,metabolite,edge_type,weight,label`.
Neither `identifiable=false` nor
`allocation_method=proportional_shared_pool` is exported. A scientist opening
the artifact can therefore mistake inferred edges for identified transfers.

The permissive strain comparison is not controlled: applying an unknown
community exchange to a single model changes nothing and leaves its model
default medium intact. The strict run is honest about comparability, but its
top-level status is wrong and its plot converts missing single growth to a
zero-height bar.

The abundance sweep is useful sensitivity output, but the large discontinuous
acetate changes (0, 11.7819, 0 across adjacent tested fractions) have no FVA or
alternative-optimum uncertainty. It should not be interpreted as a smooth
causal response without robustness analysis.

The dFBA integrator is internally consistent, but only the listed exchanges
receive dynamic lower bounds. Other model exchanges retain default uptake. The
observed growth with exactly zero glucose consumption proves this run was not a
closed glucose experiment. It is also a single-model dFBA command, not a
microbe–microbe dynamic community workflow.

### S3 — host coupling plus microbial perturbation

No Human-GEM/Recon3D file was present. I generated scratch-only synthetic host
SBML files from the repository fixture. The successful host adds a synthetic
ethanol oxidation reaction so that an observed iHN637 secretion can be tested;
it is explicitly validation-only and not biological evidence.

| ID | Exact command | Exit | Wall | Key observed result | Artifact |
|---|---|---:|---:|---|---|
| S3.1 | `./.venv/bin/python -c "from cobra.io import write_sbml_model; from cmig.synthetic_host import build_host_model; write_sbml_model(build_host_model(),'REVIEW/scratch_r2codex/synthetic_host.xml')"` | 0 | 1.07 s | Generated the repository synthetic host in allowed scratch. | `REVIEW/scratch_r2codex/synthetic_host.xml` |
| S3.2 | `./.venv/bin/cmig host-microbe-bigg --host REVIEW/scratch_r2codex/synthetic_host.xml --model-dir REVIEW/scratch_r2codex/models_ihn --microbial-biomass-gdw 1.0 --host-biomass-gdw 1.0 --biomass-basis-kind validation --biomass-basis-source synthetic_validation --host-medium REVIEW/scratch_r2codex/host_medium.csv --interface-map REVIEW/scratch_r2codex/host_interface.json --tradeoff-f 0.5 --out runs/r2codex/s3_host_baseline` | 0 | 3.15 s | Community optimal, growth 0.1122272711, but produced no acetate/butyrate. Host was infeasible, objective 0 explicitly “not a result,” top-level failed. | `runs/r2codex/s3_host_baseline/` |
| S3.2i | `./.venv/bin/cmig inspect-run --run-dir runs/r2codex/s3_host_baseline --format json` | 0 | 0.04 s | `status=failed`. | Same |
| S3.2b | `./.venv/bin/python -c "from cobra import Metabolite,Reaction; from cobra.io import write_sbml_model; from cmig.synthetic_host import build_host_model; m=build_host_model(); el=Metabolite('etoh_lumen',compartment='lumen',formula='C2H6O'); ec=Metabolite('etoh_c',compartment='c',formula='C2H6O'); ex=Reaction('EX_etoh_lumen',lower_bound=-10,upper_bound=0); ex.add_metabolites({el:-1}); tr=Reaction('ETOHtr',lower_bound=0,upper_bound=1000); tr.add_metabolites({el:-1,ec:1}); ox=Reaction('ETOH_OX',lower_bound=0,upper_bound=1000); ox.add_metabolites({ec:-1,m.metabolites.o2_c:-3,m.metabolites.atp_c:3,m.metabolites.co2_c:2}); m.add_reactions([ex,tr,ox]); write_sbml_model(m,'REVIEW/scratch_r2codex/synthetic_host_etoh.xml')"` | 0 | 1.08 s | Generated the validation-only ethanol-dependent scratch host used below; this is a test fixture, not a human model. | `REVIEW/scratch_r2codex/synthetic_host_etoh.xml` |
| S3.3 | `./.venv/bin/cmig host-microbe-bigg --host REVIEW/scratch_r2codex/synthetic_host_etoh.xml --model-dir REVIEW/scratch_r2codex/models_ihn --microbial-biomass-gdw 1.0 --host-biomass-gdw 1.0 --biomass-basis-kind validation --biomass-basis-source synthetic_validation --host-medium REVIEW/scratch_r2codex/host_medium.csv --interface-map REVIEW/scratch_r2codex/host_interface_etoh.json --tradeoff-f 0.5 --out runs/r2codex/s3_host_coupled` | 0 | 3.21 s | Community growth 0.1122272711; ethanol secretion/host transfer 3.4041441969; host objective 9.2124325907, viable and optimal; top-level ok. Transfer FVA interval [3.4041441969, 3.4041441969], so point-identifiable in this toy. | `runs/r2codex/s3_host_coupled/` |
| S3.3i | `./.venv/bin/cmig inspect-run --run-dir runs/r2codex/s3_host_coupled --format json` | 0 | 0.04 s | `status=ok`; warnings clearly say validation-only and member contribution is not causal/uniquely identifiable. | Same |
| S3.4 | `./.venv/bin/cmig gene-ko-search --model-dir REVIEW/scratch_r2codex/models_ihn --members iHN637 --member iHN637 --target etoh --ko-level gene --genes CLJU_RS12245,CLJU_RS05830 --direction max_secretion --growth-fraction 0.1 --top-k 10 --out runs/r2codex/s3_gene_ko` | 0 | 10.46 s | Baseline target-max ethanol 9.6197351769. Both single-gene KOs changed it only at numerical-noise scale (0 and -9.41e-14). No host output. | `runs/r2codex/s3_gene_ko/` |
| S3.4i | `./.venv/bin/cmig inspect-run --run-dir runs/r2codex/s3_gene_ko --format json` | 0 | 0.04 s | `status=ok`. | Same |
| S3.5 | `./.venv/bin/cmig gene-ko-search --model-dir REVIEW/scratch_r2codex/models_ihn --members iHN637 --member iHN637 --target etoh --ko-level reaction --reactions ETOHt --direction max_secretion --growth-fraction 0.1 --top-k 10 --out runs/r2codex/s3_reaction_ko` | 0 | 7.57 s | `ETOHt` KO target-max ethanol 9.6197351769→0; community growth changed only -8.04e-13. Still no host output or modified SBML. | `runs/r2codex/s3_reaction_ko/` |
| S3.5i | `./.venv/bin/cmig inspect-run --run-dir runs/r2codex/s3_reaction_ko --format json` | 0 | 0.04 s | `status=ok`. | Same |
| S3.6 | `./.venv/bin/python -c "from cobra.io import read_sbml_model,write_sbml_model; m=read_sbml_model('models/iHN637.xml'); m.reactions.get_by_id('ETOHt').knock_out(); write_sbml_model(m,'REVIEW/scratch_r2codex/models_ihn_etoh_ko/iHN637_ETOHt_KO.xml')"` | 0 | 2.25 s | Ad hoc, unsupported bridge: generated a KO SBML manually. | Scratch model |
| S3.7 | `./.venv/bin/cmig host-microbe-bigg --host REVIEW/scratch_r2codex/synthetic_host_etoh.xml --model-dir REVIEW/scratch_r2codex/models_ihn_etoh_ko --microbial-biomass-gdw 1.0 --host-biomass-gdw 1.0 --biomass-basis-kind validation --biomass-basis-source synthetic_validation --host-medium REVIEW/scratch_r2codex/host_medium.csv --interface-map REVIEW/scratch_r2codex/host_interface_etoh.json --tradeoff-f 0.5 --out runs/r2codex/s3_host_etoh_ko_manual` | 0 | 3.13 s | KO community remained optimal at growth 0.1122272711 but rerouted to acetate 4.8058506308, produced no mapped ethanol, and made the ethanol-dependent host infeasible. Objective 0 was correctly labelled “not a result.” | `runs/r2codex/s3_host_etoh_ko_manual/` |
| S3.7i | `./.venv/bin/cmig inspect-run --run-dir runs/r2codex/s3_host_etoh_ko_manual --format json` | 0 | 0.04 s | `status=failed`. | Same |

The successful baseline proves direct coupling can calculate a host objective.
The KO screen proves a microbial reaction can be perturbed. They are separate
products. A supported workflow must preserve the exact same host objective,
media, biomass scale, interface map, and solver across baseline and perturbation,
then report a delta only when both host solves are valid. CMIG does not currently
orchestrate or validate that comparison.

## Figure assessment

I inspected the produced TIFF pixels visually, parsed the SVG XML, and queried
TIFF headers with PIL:

`/usr/bin/time -p ./.venv/bin/python REVIEW/scratch_r2codex/audit_figures.py`

Exit 0, wall 0.05 s. Ten representative SVG/TIFF pairs were inspected across
search, strain growth, abundance, dFBA, host interaction, and KO output.

| Criterion | Observed from actual files | Assessment |
|---|---|---|
| Vector output | All ten inspected figure types had SVG output. SVGs had valid `viewBox` values. Search/host SVGs retained text nodes; Matplotlib SVGs converted text to vector paths (`text_nodes=0`) but preserved labels as XML comments. | **Pass for vector availability**, though path-converted text is harder to edit and less accessible. Multi-target SCFA runs produced no figures at all—only taxonomy, rankings, and summary. |
| Raster resolution | Every inspected TIFF reported exactly 300×300 dpi. Dimensions ranged from 1,950×1,440 to 2,460×2,160 pixels. | **Borderline**: 300 dpi is acceptable for continuous-tone raster, but line art commonly needs 600 dpi. |
| TIFF mode/compression | Every TIFF was RGBA with `compression=raw`; sizes ranged 8,813,006 to 21,254,606 bytes. | **Fail**: transparent-alpha RGBA plus no compression is not a sane journal-delivery default. Prefer RGB/CMYK as required and LZW/ZIP; provide 600-dpi line-art TIFF where raster is needed. |
| Palette/accessibility | Common colors were blue `#3182bd/#2b8cbe`, green `#2ca25f/#31a354`, orange `#e6550d/#d95f0e`, purple `#756bb1`, and gray. Contrast on white was generally readable. | **Partial**: close to a colorblind-conscious qualitative palette, but not a documented Okabe–Ito set. Abundance traces reuse identical markers, and interaction edge colors lack a legend, so meaning depends on color alone. |
| Typography | SVG XML used Arial for custom and host figures; Matplotlib configuration requested Arial. Host labels were 10 px, axes about 10–11 px, titles 14 px; custom search title was 22 px. | **Partial/fail**: broadly consistent sans serif, but not normalized to journal column size. The search TIFF visibly overlaps title and subtitle. Path-converted text reduces editability. |
| Legends | Strain, abundance, dFBA, and KO plots had legends. Search bar plot did not need one. | **Fail for interaction figures**: circle and bubble plots do not explain node colors, edge colors, width, direction, inferred versus identified edges, or units. |
| Axis labels and units | Labels included “Growth rate,” “Exchange flux,” “Time,” “Concentration,” “Flux,” and “Transfer flux,” but none included physical units. Search used `Target exchange flux (EX_ac_m)` without `mmol gDW^-1 h^-1`. | **Fail**. Units are mandatory for a scientific figure. |
| Panel letters | XML audit found no A/B/C/... panel letters in any inspected SVG. Abundance and dFBA each contain three stacked panels. | **Fail**. |
| Data-ink/layout | Abundance and dFBA plots were clean and readable at screening scale. Interaction circle used large empty regions. Search TIFF had title/subtitle collision. The gene-KO plot for ~1e-13 effects displayed a large gray bar across a 1e-13 axis and let the legend dominate the data area. | **Fail for publication**. Near-zero KO values need clamping/categorical display; layouts need manual composition. |
| Statistical communication | No uncertainty, replicate count, FVA interval, or alternative-optimum range was shown on the abundance/search plots. | **Fail for claims requiring uncertainty**. |

**Publication-readiness call: NOT READY.** These are useful automated
screening figures. They need unit-aware labels, panel lettering, accessible
legends, uncertainty/robustness display, journal-size typography, compressed
RGB/CMYK TIFF export, and manual layout QA before submission.

## Bugs and defects

### B1 — single-target failed candidate is “best”; top-level status is `ok`

Repro:

```bash
./.venv/bin/cmig search --model-dir REVIEW/scratch_r2codex/models_iaf --target ac --min-size 1 --max-size 1 --strategy exhaustive --top-k 10 --medium medium_presets/high_fiber.csv --out runs/r2codex/regression_single_status
./.venv/bin/cmig inspect-run --run-dir runs/r2codex/regression_single_status --format json
```

Observed: exit 0; candidate status `failed`, score `null`, diagnostic says
`EX_glc__D_m` absent, but rank=1, CLI prints flux 0 as best, summary and
inspection status are `ok`.

Expected: no best producer, no numeric rank, run status `failed` when none are
evaluable (or `degraded` when only some fail), and a nonzero process exit if
the command contract treats “no evaluable candidate” as failure.

Cause: `cmig/core/search_product.py::search_model_pool` ranks all rows, and
`cmig/cli/main.py::_write_search_outputs` hard-codes `"status": "ok"` (current
line 3163). `_cmd_search` prints `result.ranks[0]` without checking status.

### B2 — multi-target “excluded” rows still have ranks and live in `top_ranked`

Repro: S1.1 or S1.2.

Observed: warning says iAF987 combinations are “excluded from ranking,” but
CSV assigns ranks 2/3 and JSON places them in `top_ranked`. Their scores are
properly blank/`null`, not zero.

Expected: rank only `status=optimal` rows; place failures in a separate
`unevaluated_candidates` collection/table with no rank.

Cause: `cmig/core/search_product.py::rank_multi_target` sorts all rows and
enumerates ranks over all of them; `_write_multi_target_outputs` writes the
full list as rankings/top-ranked.

### B3 — normalized all-zero warning incorrectly says target flux is zero

Repro: S1.3.

Observed: acetate flux was 12.1119592750 but score was zero because a
one-candidate min-max range has zero width. Warning said no candidate achieved
a nonzero target flux.

Expected: “all evaluable candidates have zero/degenerate score” and explicit
zero-width normalization detail; do not deny an observed nonzero flux.

Cause: `cmig/core/search_product.py::_ranking_degeneracy_warnings` receives
scores but its message says “target flux.”

### B4 — strain-growth medium equality is false or falsely asserted

Repro:

```bash
./.venv/bin/cmig strain-growth --model-dir REVIEW/scratch_r2codex/models_small --medium medium_presets/high_fiber.csv --tradeoff-f 0.5 --out runs/r2codex/regression_strain_strict_status
./.venv/bin/cmig strain-growth --model-dir REVIEW/scratch_r2codex/models_small --medium medium_presets/high_fiber.csv --allow-unknown-medium --tradeoff-f 0.5 --out runs/r2codex/s2_strain_growth
```

Observed strict: community optimal, all three single legs failed because
`EX_glc__D_m` is not a single-model exchange. Observed permissive: all three
diagnosed that same absence but were solved on their defaults; summary claimed
media equal and emitted no warning.

Expected: canonicalize community `_m` medium keys to each model's exchange
namespace (normally `_e`), close/set a controlled effective medium on both
legs, and compare the resulting metabolite-level uptake maps. Unknown entries
must make `media_equal=false` even in permissive mode.

Cause: `cmig/cli/main.py::_cmd_strain_growth` treats a non-raising call as
`single_medium_applied=true`; `cmig/core/medium_spec.py::apply_medium_checked`
only updates exactly matching keys and leaves all default medium entries in
place.

### B5 — strain-growth top status ignores failed single legs and plot turns missing into zero

Repro: S2.3.

Observed: three `single_status=failed` rows, but summary/inspect status
`optimal`. `single_growth=null` is rendered as 0 because
`_write_strain_growth_figures` uses `value or 0.0`.

Expected: worst-substatus run status (`failed` here); missing/failed bars shown
as missing with a hatch/marker and legend, never as measured zero.

Cause: `cmig/cli/main.py::_write_strain_growth_outputs` copies only the
community status; `_write_strain_growth_figures` coerces `None` to zero.

### B6 — cross-feeding inference is documented only in source, not in artifacts

Repro: inspect `runs/r2codex/s2_community_solve/edges.parquet`.

Observed schema:
`schema_version,source_id,target_id,metabolite,edge_type,weight,label`.
Sixteen cross-feeding rows appeared as direct donor→recipient edges.

Expected: at minimum `identifiable=false`,
`allocation_method=proportional_shared_pool`, and a field distinguishing an
inferred allocation from a measured/uniquely solved transfer. Figures and GUI
must expose the same caveat.

Cause: `cmig/core/interactions.py::build_tidy` knows the allocation is
non-identifiable, but `cmig/core/tidy.py::EDGES_SCHEMA` has nowhere to store it.

### B7 — dFBA permits growth on untracked default nutrients

Repro: S2.5.

Observed: biomass grew 24.55% and acetate accumulated to 0.5084478501 while
tracked glucose stayed exactly 10.0.

Expected: close untracked uptake by default or require an explicit background
medium; report every external nutrient that can support growth. A “glucose
dFBA” should not silently grow on other default substrates.

Cause: `cmig/core/dfba.py::simulate_dfba` changes lower bounds only for
`managed_exchanges`; all other exchange bounds remain at model defaults.

### B8 — abundance top status is “any success,” not worst status

Static/current-code defect:
`cmig/cli/main.py::_write_abundance_impact_outputs` sets status to `ok` when
**any** row is optimal. A mixed optimal/failed sweep would therefore violate
the worst-substatus requirement.

Expected: `ok` only if all requested points are valid, `degraded` for a mixed
set, and `failed` if none are valid; failed points remain unplotted or visibly
marked.

### B9 — figure export/layout regressions

Observed:

- `cmig/cli/main.py::_save_screening_figure` saves raw RGBA TIFF at 300 dpi
  without compression.
- `_write_search_tiff` title and subtitle visibly overlap.
- `_write_gene_ko_figures` categorizes ~1e-13 as neutral but still plots the
  raw near-zero number, creating a visually huge bar on an auto-scaled
  1e-13 axis.
- All multi-panel figures lack panel letters and all quantitative axes lack
  units.
- Multi-target SCFA search does not emit the search figures advertised by the
  generic workflow map.

Expected: journal export profile, units from artifact metadata, panel letters,
near-zero clamping, and per-file visual regression tests.

## Prioritized proposals

### P0 — result integrity and the missing S3 workflow

1. **Never rank or bless unevaluable candidates.**  
   Files/functions:
   `cmig/core/search_product.py::search_model_pool`,
   `rank_multi_target`, `_ranking_degeneracy_warnings`;
   `cmig/cli/main.py::_cmd_search`, `_write_search_outputs`,
   `_write_multi_target_outputs`, `_write_strain_growth_outputs`,
   `_write_abundance_impact_outputs`, `_resolve_run_status`.
   
   Create a shared `derive_run_status(substatuses)` and a shared ranking
   partition (`ranked`, `unevaluated`). Assign ranks only to finite, optimal
   rows. Return a failure code or at least `status=failed` when there is no
   evaluable result. Add real-model integration tests for the two reproductions
   above, not only mocked writer tests.

2. **Add an integrated microbial-perturbation→host comparison command.**  
   Files/functions:
   new `cmig/cli/main.py::_cmd_host_perturb_bigg`;
   new
   `cmig/core/host_coupling.py::run_bigg_host_microbe_perturbation`;
   extend `cmig/core/host_impact.py` with a baseline/perturbed result.
   
   Accept member suppression/abundance, gene KO, reaction KO, and a bounded
   inhibition value. Run baseline and perturbation with identical taxonomy
   except the declared perturbation, identical media, mapping, biomass basis,
   objective, solver, and tradeoff. Emit both sub-statuses, host objectives,
   `delta_host_objective` only when both are optimal, microbial secretion
   deltas, transfer FVA intervals, and provenance. Do not encode an infeasible
   objective as zero.

### P1 — scientific comparability and identifiability

3. **Implement effective-medium canonicalization and equality auditing.**  
   Files/functions:
   `cmig/core/medium_spec.py::apply_medium_checked` plus a new
   `canonical_medium_for_model`;
   `cmig/cli/main.py::_cmd_strain_growth`.
   
   Normalize `_m`/`_e` through metabolite identity, close unlisted uptake when
   a controlled medium is requested, export applied metabolite-level maps for
   community and every single model, and define equality from those maps—not
   from whether an API call raised.

4. **Make inferred cross-feeding explicit in the data contract.**  
   Files/functions:
   `cmig/core/tidy.py::EDGES_SCHEMA` (schema bump/migration),
   `cmig/core/interactions.py::build_tidy`,
   `cmig/gui/graph_data.py`,
   interaction renderers.
   
   Add `identifiable`, `inference_method`, `allocation_basis`, and ideally
   donor/recipient capacity intervals. Label graph edges as “inferred shared
   pool allocation,” with an artifact-level methods note.

5. **Close or declare dFBA background uptake; add community dFBA if S2 is a goal.**  
   Files/functions:
   `cmig/core/dfba.py::simulate_dfba`,
   `cmig/cli/main.py::_cmd_dfba`.
   
   Default to closing all untracked uptake, or require a background medium and
   audit all open exchanges. Add a MICOM/community dynamic mode before
   advertising dFBA as microbe–microbe dynamics.

6. **Tighten S1's biological contract and robustness.**  
   Files/functions:
   `cmig/core/targets.py::SCFA/preset_targets`,
   `cmig/core/search.py::joint_target_solve`,
   `cmig/core/search_product.py::search_model_pool_multi`.
   
   Split a core SCFA preset (acetate/propionate/butyrate, optionally
   valerate/isobutyrate when supported) from a broader fermentation-acids
   preset. Add multi-target FVA/alternative-optimum intervals and warn when
   product composition is not unique. Record the growth-fraction and full
   effective medium in the summary.

### P2 — output clarity and publication export

7. **Create a publication figure profile.**  
   Files/functions:
   `cmig/cli/main.py::_save_screening_figure`, `_write_search_tiff`,
   `_write_dfba_figure`, `_write_strain_growth_figures`,
   `_write_abundance_impact_figures`, `_write_gene_ko_figures`;
   `cmig/core/interaction_figures.py`.
   
   Add physical units, A/B/C panel letters, documented Okabe–Ito colors with
   redundant shape/line encodings, explanatory interaction legends, 600-dpi
   line-art TIFF, LZW/ZIP compression, RGB/CMYK mode, column-width typography,
   and layout visual regression tests. Clamp neutral KO deltas to visual zero
   and use a categorical “no measurable change” view when the range is below
   tolerance.

8. **Make multi-target artifacts match workflow discovery.**  
   File/function:
   `cmig/cli/main.py::_write_multi_target_outputs`.
   
   Generate an SCFA composition plot, total-score plot with units, and
   candidate-status panel; or change `workflows` so it does not promise search
   figures for the multi-target path.

9. **Export medium and robustness provenance for abundance sweeps.**  
   Files/functions:
   `cmig/cli/main.py::_cmd_abundance_impact`,
   `_write_abundance_impact_outputs`.
   
   Record medium source/checksum/unknown exchanges, requested versus achieved
   abundance, worst status, target FVA, and alternative-optimum diagnostics at
   every fraction.

## Test-suite evidence

| Exact command | Exit | Wall | Result |
|---|---:|---:|---|
| `./.venv/bin/python -m pytest -q tests/test_engine_solver_guard.py tests/test_run_status_reporting.py tests/test_search_multi_target_metrics.py tests/test_strain_growth_medium_basis.py` | 0 | 1.96 s | 37/37 focused tests passed: solver guard 5, status reporting 10, multi-target metrics 17, strain medium basis 5. |
| `./.venv/bin/python -m pytest -q` | 0 | 105.84 s | 535 tests collected; 533 passed and 2 skipped. Six OSQP pending-deprecation warnings, four expected infeasible-solver warnings, and one UMAP warning were shown. |

The passing suite is important but does not override the real-artifact
reproductions. In particular, focused medium tests verify that the same
`MediumSpec` is passed, not that `_m` and `_e` models receive the same effective
uptake bounds. Status tests do not cover the hard-coded single-search and
strain-growth summary statuses identified above.

## What I could not test, and why

1. **Real human host quantitative validity:** `models_human/` and Recon3D were
   absent. I could not validate mapping coverage, runtime, host objective
   choice, or quantitative host effects on a real Human-GEM/Recon3D model.
2. **Publication-grade host biomass scaling:** no measured microbial/host gDW
   basis and citation were supplied. All host runs used
   `biomass-basis-kind=validation` and are explicitly non-publication.
3. **A supported drug-inhibition/KO-to-host delta:** the command does not
   exist. I quantified an ad hoc manual bridge only to prove the gap; it is not
   a supported CMIG workflow.
4. **Community dFBA:** the public `dfba` command accepts one SBML model, not a
   microbial community. Therefore dynamic cross-feeding/competition could not
   be tested.
5. **All five microbial models / larger combinations:** exhaustive
   multi-target solves were already 123.91–151.73 s for three pair candidates.
   I followed the brief's instruction to prefer iHN637/iYO844/iAF987 and did
   not claim coverage of iSFV_1184 or iML1515.
6. **Full-pool normalized/raw rankings:** `carbon_equivalent` was run across
   all three pairs; normalized and raw metrics were exercised on the observed
   best pair to verify units and degeneracy behavior. I did not spend another
   several minutes duplicating the full-pool two-pass solve for metrics whose
   relative/chemical semantics were already directly exposed.
7. **True external solver outage/license failure:** the live license was
   valid. Graceful failure was verified through five focused guard tests and
   real infeasible LP paths, not by disabling the shared Gurobi license.
8. **Experimental biological accuracy:** no measured SCFA, cross-feeding,
   abundance-response, dFBA, or host-response benchmark dataset was supplied.
   This report assesses functional support and scientific interpretability,
   not predictive validation against experiments.
