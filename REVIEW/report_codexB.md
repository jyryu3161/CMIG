# Independent Evaluator B — CMIG functional test

Test date: 2026-07-25 (Asia/Seoul)  
Workspace: `/Users/jaeyongryu/orca/CMIG`  
Executable policy followed: only `./.venv/bin/cmig` and `./.venv/bin/python`; no install, `uv`, or source edits.

The decisive final runs used CMIG 0.1.0, cobra 0.31.1, MICOM 0.39.0, Gurobi 12.0.3, PySide6 6.11.1, and Git HEAD `d3e90d73325236bdc8501785defda2a4b84b7b97`. The worktree was dirty before/during evaluation and another process changed files under `cmig/` while tests were running. I did not edit `cmig/`, `tests/`, or tracked source. I reran the decisive S1 and S3 workflows after changes stopped; the final source hashes relevant to those reruns were:

- `cmig/cli/main.py`: `135efc8350bfd3b2faf629d569cc6341452f2375a0fa7934aad31a970c4b1858`
- `cmig/core/search.py`: `47ed16746d30ea2835890338d368c9a184a3430234defe469a8ed3bd905cbd14`
- `cmig/core/search_product.py`: `6d7b94f734715cb7c96790d2ae70deceb255570b17e27279511262f480cd34d5`
- `cmig/core/host_coupling.py`: `7ed16fbb6a78fae31df16928a57a0ca4f1d145d72aa13d356f9fe0bb6fb9b82a`

## 1. Verdict table

| Scenario | Verdict | Ran end to end? | Strongest observed evidence | Specific blocking gap |
|---|---|---:|---|---|
| S1 — best microbial combination for SCFA | **PARTIAL** | Yes | Final `--target-preset scfa --multi-metric carbon_equivalent` run evaluated 4/4 combinations in 269.15 s. It ranked `iHN637+iYO844` first at 24.2239185513 mmol C gDW^-1 h^-1 (12.1119592757 acetate; the other joint SCFA fluxes were 0). | Run status was `degraded`: only 3/4 combinations were rankable. `iAF987+iYO844` was excluded as infeasible even though independent capability solves showed lactate-L 2.352088833, propionate 1.210133703, and succinate 2.292684017. Per-target secretion-domain constraints can therefore prevent a total-SCFA ranking. Four combinations also took 269.15 s, and the multi-target workflow is exhaustive-only with a 100-candidate hard limit. The fixture's exact three-way tie was not labeled as a tie. |
| S2 — microbe–microbe interaction simulation | **PARTIAL** | Yes | Real three-GEM `cmig solve` completed in 18.39 s with run hash `6e508c3cf5b590bf376ada0e7fbe6511b20c14d4fab407c1d3ede916a94105fd`, growth 0.385468472, and 16 `cross_feeding` edges. `strain-growth` quantified single versus community growth. The synthetic pair API classified mutualism and emitted an acetate edge `producer -> consumer`, weight 25.0. | `cmig solve`'s donor→recipient edges are proportional allocations from a shared pool, not identified transfers, but that method/identifiability is not stored in `edges.parquet` or the manifest. `analyze_pair` (mutualism/MRO/MIP) has no CLI workflow. `cmig dfba` is single-model, not community dFBA. Thus a reviewer cannot treat all emitted pairwise edges as measured causal feeding links. |
| S3 — host–microbe plus microbial inhibition/KO → host effect | **PARTIAL** | Yes, but only with a manual bridge | Synthetic baseline coupling gave community growth 12.5, butyrate transfer 6.25, and host objective 30.25. `gene-ko-search` found `consumer:AC2BUT` reduced maximal butyrate 15→0 and community growth 25→10. After manually applying that KO to a scratch model and rerunning host coupling, host objective fell 30.25→19.0 (Δ = -11.25) and coupling switched from butyrate 6.25 to acetate 10.0. | There is no clean command that propagates a `gene-ko-search` perturbation into `host-microbe-bigg` and reports host-objective delta. I had to edit a scratch GEM with cobra, rerun coupling, and subtract summaries manually. No human GEM ships with CMIG, so all successful host numbers here use a synthetic toy host and `biomass-basis-kind validation`; CMIG correctly marks them not publication-ready. |

Overall: all three scientific capabilities exist in meaningful form, but none is fully publication-defensible through a single supported workflow in the tested state.

## 2. Evidence log

Wall time is the `real` value from `/usr/bin/time -p`. Exit codes are process exit codes. All output paths are under `runs/codexB/` or `REVIEW/scratch_codexB/`.

### Environment and command discovery

Command:

```bash
/usr/bin/time -p ./.venv/bin/cmig workflows --format json
```

Exit 0; 0.05 s. The map exposed `search`, `solve`, `strain-growth`, `abundance-impact`, `gene-ko-search`, `host-map`, `host-microbe-bigg`, `host-search-bigg`, `dfba`, and `inspect-run`.

Command:

```bash
/usr/bin/time -p ./.venv/bin/cmig solvers
```

Exit 0; 0.07 s. Gurobi, HiGHS, and OSQP were available; Gurobi reported LP/QP/MILP support.

The final `search --help` exposed:

- `--target-preset scfa` = `ac,but,lac__D,lac__L,ppa,succ`
- `--multi-metric carbon_equivalent` with score unit mmol C gDW^-1 h^-1
- `normalized_weighted`, `carbon_equivalent`, and `raw_sum` multi-target metrics

### S1 — SCFA combination ranking

#### Final carbon-equivalent SCFA run

Exact command:

```bash
/usr/bin/time -p ./.venv/bin/cmig search --model-dir REVIEW/scratch_codexB/small_models --target-preset scfa --multi-metric carbon_equivalent --growth-fraction 0.5 --min-size 2 --max-size 3 --strategy exhaustive --top-k 10 --out runs/codexB/s1_scfa_carbon_final
```

Exit 0; 269.15 s. Artifact: `runs/codexB/s1_scfa_carbon_final/search_summary.json`.

Exact verification:

```bash
/usr/bin/time -p ./.venv/bin/cmig inspect-run --run-dir runs/codexB/s1_scfa_carbon_final --format json
```

Exit 0; 0.07 s. `kind=model_pool_search`, `status=degraded`, `run_hash=null`.

Observed summary:

- Pool members: 3; candidate combinations: 4; evaluated: 4; ranked: 3.
- Carbon weights: acetate 2, butyrate 4, D/L-lactate 3, propionate 3, succinate 4.
- Rank 1: `iHN637+iYO844`, score 24.223918551322633 mmol C gDW^-1 h^-1, community growth 0.2969975376023387, acetate 12.111959275661317, every other joint SCFA flux 0.
- Rank 2: `iAF987+iHN637+iYO844`, score 14.488014895763722, growth 0.3824949831726635, acetate 7.244007447881861.
- Rank 3: `iAF987+iHN637`, score 10.235491342019518, growth 0.15393480977736823, acetate 5.117745671009759; missing exchange `succ` contributed 0.
- Unranked: `iAF987+iYO844`, status `infeasible`, diagnostic `target LP returned no solution object (solver_status=infeasible)`. Its independent capability fluxes were lactate-L 2.3520888329367153, propionate 1.2101337031672135, and succinate 2.292684017244986, but `flux_basis=per_target_capability_not_simultaneous`.
- The four-candidate wall time is about 67.3 s/candidate as an observed average. This is not a tractable basis for broad exhaustive model pools.
- No SVG/TIFF search figure was produced for this multi-target run; only taxonomy, rankings CSV, and summary JSON were emitted.

#### Tie/degeneracy fixture

Exact command:

```bash
/usr/bin/time -p ./.venv/bin/cmig search-fixture --solver gurobi --metabolite ac --growth-fraction 0.5 --top-k 10 --out runs/codexB/s1_search_fixture_final
```

Exit 0; 2.12 s.

Exact verification:

```bash
/usr/bin/time -p ./.venv/bin/cmig inspect-run --run-dir runs/codexB/s1_search_fixture_final --format json
```

Exit 0; 0.04 s; `status=optimal`, `run_hash=null`.

All three pairs had exactly the same target flux/score, 13.358851988170102, and community growth 0.4369607534842137. The output contained no `warnings`, tie group, or shared-rank field; list order alone made one pair appear first.

### S2 — microbe–microbe interactions

#### Real `cmig solve`

The namespace guard correctly rejected an unreviewed run:

```bash
/usr/bin/time -p ./.venv/bin/cmig solve --taxonomy runs/codexB/s1_scfa_carbon_final/pool_taxonomy.csv --solver gurobi --tradeoff-f 0.5 --targets scfa --out runs/codexB/s2_solve_real_small
```

Exit 2; 0.32 s. Observed message required `--namespace-decisions` or explicit `--assume-bigg-namespace`.

After explicitly confirming the bundled models' BiGG namespace:

```bash
/usr/bin/time -p ./.venv/bin/cmig solve --taxonomy runs/codexB/s1_scfa_carbon_final/pool_taxonomy.csv --assume-bigg-namespace --solver gurobi --tradeoff-f 0.5 --targets scfa --out runs/codexB/s2_solve_real_small_bigg
```

Exit 0; 18.39 s.

Verification:

```bash
/usr/bin/time -p ./.venv/bin/cmig inspect-run --run-dir runs/codexB/s2_solve_real_small_bigg --format json
```

Exit 0; 0.04 s; `status=ok`, full Gurobi flux provenance, run hash `6e508c3cf5b590bf376ada0e7fbe6511b20c14d4fab407c1d3ede916a94105fd`.

Observed values:

- Community growth 0.38546847170621545.
- Member growth: iAF987 0.0371688641; iHN637 0.5588540893; iYO844 0.5603824617.
- Edge counts: 59 uptake, 21 secretion, 16 cross-feeding.
- Sum of allocated cross-feeding edge weights: 15.914670224655136.
- Largest non-currency SCFA transfer: iYO844→iAF987 acetate 3.428638; iHN637→iAF987 acetate 0.272539.
- Other inferred links included iHN637→iYO844 isoleucine 0.212753, iYO844→iHN637 leucine 0.188770, and iHN637→iYO844 lysine 0.182288.
- Community net acetate was uptake, -1.0462741499919241, despite acetate secretion by individual members.
- The manifest records Gurobi/pFBA and namespace assumption, but not `proportional_shared_pool` or `identifiable=false` for pairwise cross-feeding edges.

#### Fixture solve with SCFA FVA

```bash
/usr/bin/time -p ./.venv/bin/cmig solve-fixture --solver gurobi --targets scfa --fva --out runs/codexB/s2_solve_fixture
```

Exit 0; 1.69 s. Final verification returned `status=ok`, run hash `29844e29103603324d118cc9a8b9ae4fa2a79070418860cfc2ed70095cef29ab`.

Observed acetate net secretion was 5.152535273457313; acetate FVA was [0.0, 13.35885198817012]. The three fixture member growth rates were 0.436964, 0.436959, and 0.436959.

#### Per-strain growth

```bash
/usr/bin/time -p ./.venv/bin/cmig strain-growth --model-dir REVIEW/scratch_codexB/small_models --solver gurobi --tradeoff-f 0.5 --out runs/codexB/s2_strain_growth
```

Exit 0; 21.91 s.

Verification:

```bash
/usr/bin/time -p ./.venv/bin/cmig inspect-run --run-dir runs/codexB/s2_strain_growth --format json
```

Exit 0; 0.06 s; `status=optimal`, `run_hash=null`.

Observed single→community member growth:

- iAF987: 0.047322435050338334 → 0.037168864104649854.
- iHN637: 0.2244545421198858 → 0.5588540893482161.
- iYO844: 0.11796638932239924 → 0.5603824616657803.

The summary explicitly stated `single_medium_equals_community_medium=true`.

#### Abundance sensitivity

```bash
/usr/bin/time -p ./.venv/bin/cmig abundance-impact --model-dir REVIEW/scratch_codexB/small_models --member iHN637 --fractions 0.1,0.33,0.6,0.9 --target ac --solver gurobi --tradeoff-f 0.5 --out runs/codexB/s2_abundance_iHN637_ac
```

Exit 0; 71.11 s.

Final verification returned `status=ok` in 0.04 s. Observed community acetate exchange changed non-monotonically:

- iHN637 fraction 0.10: +0.0554371626; influence share 0.0611171465.
- Fraction 0.33: -0.9003595893; influence share 0.0262565587.
- Fraction 0.60: +7.4009567795; influence share 0.5305837271.
- Fraction 0.90: 0.0; influence share 0.0298359209.

This is correctly interpretable only as sensitivity, not causality.

#### Pair interaction API and explicit cross-feeding edge

The codebase has no `cmig pair` command, so I exercised the public Python modules.

```bash
/usr/bin/time -p ./.venv/bin/python -c 'import json; from dataclasses import asdict; from pathlib import Path; from cmig.synthetic_pair import build_pair_taxonomy; from cmig.core.pair import analyze_pair,pair_matrix_rows; from cmig.core.matrix import build_matrix,write_matrix; root=Path("REVIEW/scratch_codexB/s2_pair_api"); tax=build_pair_taxonomy(root); result=analyze_pair(tax,solver="gurobi",tradeoff_f=0.5); write_matrix(build_matrix(pair_matrix_rows(result)),root/"pair_matrix.parquet"); print(json.dumps(asdict(result),indent=2,sort_keys=True)); print("matrix_path",root/"pair_matrix.parquet")'
```

Exit 0; 1.11 s.

Observed: `interaction=mutualism`, `mip=1`, `mro_score=0.0`; producer growth 10.0 alone and 12.5 in co-culture; consumer growth 5.0 alone and 12.5 in co-culture. Co-culture exchange was producer acetate +25.0, consumer acetate -25.0, and consumer butyrate +12.5.

```bash
/usr/bin/time -p ./.venv/bin/python -c 'import json,pandas as pd,pyarrow.parquet as pq; from pathlib import Path; from cmig.core.engine import MicomEngine; from cmig.core.interactions import build_tidy,CROSS_FEEDING_ALLOCATION_METHOD; root=Path("REVIEW/scratch_codexB/s2_pair_api"); tax=pd.DataFrame({"id":["producer","consumer"],"file":[str(root/"producer.xml"),str(root/"consumer.xml")],"abundance":[0.5,0.5]}); eng=MicomEngine(); com=eng.build_community(tax,cmig_solver="gurobi"); sol=eng.cooperative_tradeoff(com,0.5,cmig_solver="gurobi"); tidy=build_tidy(sol); pq.write_table(tidy.nodes,root/"nodes.parquet"); pq.write_table(tidy.edges,root/"edges.parquet"); pq.write_table(tidy.profile,root/"profile.parquet"); edges=tidy.edges.to_pandas(); print("status",sol.status); print("community_growth",sol.objective); print("allocation",CROSS_FEEDING_ALLOCATION_METHOD); print(edges[edges.edge_type.eq("cross_feeding")].to_string(index=False)); print("edge_counts",json.dumps(edges.edge_type.value_counts().to_dict(),sort_keys=True))'
```

Exit 0; 1.11 s. It emitted one direct `producer -> consumer` acetate edge of weight 25.0 and reported allocation method `proportional_shared_pool`.

#### dFBA and sensitivity

```bash
/usr/bin/time -p ./.venv/bin/cmig dfba --model models/iHN637.xml --solver gurobi --t-end 1 --dt 0.2 --initial-biomass 0.05 --km 0.01 --out runs/codexB/s2_dfba_iHN637
```

Exit 0; 2.21 s. Verification was `status=completed`.

Observed at t=1 h:

- Biomass 0.05→0.062276580239045747.
- Growth rate 0.2244545421198858 h^-1.
- Acetate 0→0.5084478501156893.
- Glucose stayed exactly 10.0 and D-lactate 0.0.
- Reported integration residuals were 0 for the managed variables.

Sensitivity command:

```bash
/usr/bin/time -p ./.venv/bin/cmig dfba-sensitivity --model models/iHN637.xml --solver gurobi --t-end 1 --dts 0.2,0.1 --kms 0.01,0.02 --initial-biomass 0.05 --out runs/codexB/s2_dfba_sensitivity_iHN637
```

Exit 0; 2.11 s. Verification returned `kind=dfba_sensitivity`, `status=ok`.

All four runs completed with zero reported balance residuals. Final biomass was 0.062426859621117915 at dt=0.1 and 0.062276580239045747 at dt=0.2; relative coarse-step error was 0.002407287231557806. Changing Km 0.01→0.02 had no effect because the tracked glucose was not consumed.

### S3 — host coupling and perturbation

#### Synthetic host fixture

```bash
/usr/bin/time -p ./.venv/bin/cmig host-fixture --solver gurobi --maintenance-flux 1.0 --out runs/codexB/s3_host_fixture
```

Exit 0; 3.33 s. Verification returned `status=optimal`. Observed host biomass was 35.0 with acetate uptake 8.0 and butyrate uptake 4.0. The summary scope was explicitly `synthetic_toy_host_not_human_gem_quantitative`.

The reusable synthetic host SBML was created only in the assigned scratch path:

```bash
/usr/bin/time -p ./.venv/bin/python -c 'import cobra; from cmig.synthetic_host import build_host_model; p="REVIEW/scratch_codexB/synthetic_host.xml"; cobra.io.write_sbml_model(build_host_model(),p); m=cobra.io.read_sbml_model(p); print(p,len(m.reactions),len(m.metabolites),m.objective.expression)'
```

Exit 0; 1.06 s. It had 12 reactions and 9 metabolites.

#### Interface mapping

Real small-model map:

```bash
/usr/bin/time -p ./.venv/bin/cmig host-map --host REVIEW/scratch_codexB/synthetic_host.xml --model-dir REVIEW/scratch_codexB/small_models --out runs/codexB/s3_host_map
```

Exit 0; 4.05 s. Of 307 possible microbial secretions, 2 normalized matches were found (`ac_e -> EX_ac_lumen`, `but_e -> EX_but_lumen`) and 305 were unmatched.

Synthetic pair map:

```bash
/usr/bin/time -p ./.venv/bin/cmig host-map --host REVIEW/scratch_codexB/synthetic_host.xml --model-dir REVIEW/scratch_codexB/s2_pair_api --out runs/codexB/s3_host_map_pair
```

Exit 0; 1.06 s. Verification returned `status=ok`. It found 2 normalized matches and 1 unmatched secretion (glucose). Both maps warned that normalized matches require manual review.

#### Successful baseline coupling

```bash
/usr/bin/time -p ./.venv/bin/cmig host-microbe-bigg --host REVIEW/scratch_codexB/synthetic_host.xml --model-dir REVIEW/scratch_codexB/s2_pair_api --solver gurobi --tradeoff-f 0.5 --microbial-biomass-gdw 1.0 --host-biomass-gdw 1.0 --biomass-basis-kind validation --biomass-basis-source 'synthetic fixture, evaluator B' --interface-map runs/codexB/s3_host_map_pair/host_interface_map.json --out runs/codexB/s3_host_microbe_pair_final
```

Exit 0; 1.62 s.

Verification:

```bash
/usr/bin/time -p ./.venv/bin/cmig inspect-run --run-dir runs/codexB/s3_host_microbe_pair_final --format json
```

Exit 0; 0.04 s; `status=ok`, `run_hash=null`.

Observed:

- Community growth 12.5.
- Net microbial butyrate secretion 6.25 mmol gDW_microbiome^-1 h^-1.
- Host butyrate uptake 6.25 mmol gDW_host^-1 h^-1.
- Host objective 30.25; host status optimal and viable.
- Butyrate FVA interval [6.25, 6.25].
- Warning: validation-only biomass basis, not publication-ready.
- Member transfer contribution was labeled `abundance_weighted_proportional_allocation`, `identifiable=false`.

#### Combination removal as a host-effect proxy

```bash
/usr/bin/time -p ./.venv/bin/cmig host-search-bigg --host REVIEW/scratch_codexB/synthetic_host.xml --model-dir REVIEW/scratch_codexB/s2_pair_api --solver gurobi --min-size 1 --max-size 2 --top-k 10 --target but --metric objective_value --tradeoff-f 0.5 --microbial-biomass-gdw 1.0 --host-biomass-gdw 1.0 --biomass-basis-kind validation --biomass-basis-source 'synthetic fixture, evaluator B' --interface-map runs/codexB/s3_host_map_pair/host_interface_map.json --out runs/codexB/s3_host_search_pair_final
```

Exit 0; 1.40 s. Verification returned `status=ok`.

All 3 combinations were evaluated:

- Consumer+producer: host objective 30.25; butyrate transfer 6.25.
- Producer only: host objective 19.0; butyrate transfer 0.
- Consumer only: host objective 11.5; butyrate transfer 2.5.

This supports member-removal comparison, but the output is a combination ranking rather than an explicit baseline→perturbation delta.

#### Reaction KO and manual host propagation

```bash
/usr/bin/time -p ./.venv/bin/cmig gene-ko-search --model-dir REVIEW/scratch_codexB/s2_pair_api --members producer,consumer --member consumer --target but --direction max_secretion --growth-fraction 0.5 --solver gurobi --ko-level reaction --reactions AC2BUT --jobs 1 --top-k 10 --out runs/codexB/s3_reaction_ko_pair_final
```

Exit 0; 1.38 s. Verification returned `status=ok`.

Observed baseline: butyrate 15.0, community growth 25.0. `consumer:AC2BUT` KO: butyrate 0, community growth 10.0; both deltas -15.0.

Because no host-aware KO command exists, I manually applied the same KO to a scratch model:

```bash
/usr/bin/time -p ./.venv/bin/python -c 'import cobra; src="REVIEW/scratch_codexB/s2_pair_api/consumer.xml"; dst="REVIEW/scratch_codexB/s3_pair_ko_models/consumer.xml"; m=cobra.io.read_sbml_model(src); r=m.reactions.get_by_id("AC2BUT"); before=r.bounds; r.bounds=(0,0); cobra.io.write_sbml_model(m,dst); check=cobra.io.read_sbml_model(dst); print("AC2BUT",before,"->",check.reactions.get_by_id("AC2BUT").bounds,"written",dst)'
```

Exit 0; 1.04 s; bounds changed `(0, 1000) -> (0, 0)`.

KO host coupling:

```bash
/usr/bin/time -p ./.venv/bin/cmig host-microbe-bigg --host REVIEW/scratch_codexB/synthetic_host.xml --model-dir REVIEW/scratch_codexB/s3_pair_ko_models --solver gurobi --tradeoff-f 0.5 --microbial-biomass-gdw 1.0 --host-biomass-gdw 1.0 --biomass-basis-kind validation --biomass-basis-source 'synthetic fixture, evaluator B' --interface-map runs/codexB/s3_host_map_pair/host_interface_map.json --out runs/codexB/s3_host_microbe_pair_AC2BUT_KO_final
```

Exit 0; 1.59 s. Verification returned `status=ok`.

Observed baseline→KO comparison:

- Community growth 12.5→5.0; Δ = -7.5.
- Host objective 30.25→19.0; Δ = -11.25.
- Transfer changed from butyrate 6.25 to acetate 10.0.

Those deltas are real outputs from two separate runs, but CMIG did not calculate or connect them.

#### Failed real-model coupling and process status

```bash
/usr/bin/time -p ./.venv/bin/cmig host-microbe-bigg --host REVIEW/scratch_codexB/synthetic_host.xml --model-dir REVIEW/scratch_codexB/small_models --solver gurobi --tradeoff-f 0.5 --microbial-biomass-gdw 1.0 --host-biomass-gdw 1.0 --biomass-basis-kind validation --biomass-basis-source 'synthetic fixture, evaluator B' --interface-map runs/codexB/s3_host_map/host_interface_map.json --out runs/codexB/s3_host_microbe_real_unmatched_final
```

Process exit 0; 19.07 s. It printed “coupling complete” but `host_status=infeasible`, host objective 0, and no matched net community secretion.

```bash
/usr/bin/time -p ./.venv/bin/cmig inspect-run --run-dir runs/codexB/s3_host_microbe_real_unmatched_final --format json
```

Exit 0; 0.04 s; correctly reported run `status=failed`.

## 3. Figure assessment

### Figure generation commands

```bash
/usr/bin/time -p ./.venv/bin/cmig render-figure --run-dir runs/codexB/s2_solve_fixture --out REVIEW/scratch_codexB/profile_nature.svg --renderer auto --format svg --title 'SCFA exchange profile' --journal-preset nature
```

Exit 0; 1.20 s; R/ggplot2 SVG.

```bash
/usr/bin/time -p ./.venv/bin/cmig render-figure --run-dir runs/codexB/s2_solve_fixture --out REVIEW/scratch_codexB/profile_nature.pdf --renderer auto --format pdf --title 'SCFA exchange profile' --journal-preset nature
```

Exit 0; 1.46 s. R failed with `unknown family 'Arial'`; the CLI fell back to Matplotlib and created the PDF.

```bash
/usr/bin/time -p ./.venv/bin/cmig render-figure --run-dir runs/codexB/s2_solve_fixture --out REVIEW/scratch_codexB/profile_nature.tiff --renderer auto --format tiff --title 'SCFA exchange profile' --journal-preset nature
```

Exit 0; 1.24 s; R/ggplot2 TIFF.

The invalid-preset test:

```bash
/usr/bin/time -p ./.venv/bin/cmig render-figure --run-dir runs/codexB/s2_solve_fixture --out REVIEW/scratch_codexB/profile_invalid_preset.svg --renderer matplotlib --format svg --journal-preset definitely_not_a_journal
```

Exit 0; 0.75 s. This should have been rejected, but it rendered successfully.

### Actual-file inspection

I parsed the XML of 10 produced SVGs: the profile, strain-growth, abundance-impact, dFBA, interaction circle/heatmap/bubble/member contribution, KO, and host-search plots. I also opened representative TIFFs visually and queried every TIFF with PIL.

| Criterion | Result | Actual observation |
|---|---|---|
| Colorblind-safe palette | **PARTIAL/FAIL** | The heatmap uses viridis and is safe. Other files use `#D62728/#1F77B4`, `#2B8CBE/#31A354`, and host/KO colors `#3182BD/#E6550D/#2CA25F`. These are not the Okabe–Ito palette; several plots rely on hue alone and include green/orange or blue/green distinctions without redundant encodings. |
| Vector output | **PASS with caveats** | SVG exists for every automatically plotted workflow inspected. SVG dimensions were valid, e.g. profile 432×288 pt, strain growth 518.4×244.8 pt, interaction circle 590.4×518.4 pt. The PDF was one 432×288 pt vector page, but it was a Matplotlib fallback with an embedded Type 3 DejaVuSans subset and no tagging. |
| Raster resolution/mode/compression | **PARTIAL** | R profile TIFF: 3600×2400 px, RGB, 600×600 dpi, LZW — good. All automatic screening/interaction TIFFs inspected were RGBA, 300×300 dpi, uncompressed (`compression_tag=1`). Examples: strain growth 2160×1020 px/8.4 MB; abundance 2160×2220 px/18 MB; dFBA 2220×2160 px/18 MB; circle 2460×2160 px/20 MB; KO 2340×1020 px/9.1 MB. 300 dpi is the lower bound for color raster but weak for line art; raw RGBA is needlessly large. |
| Journal preset behavior | **FAIL** | Every `nature` sidecar recorded width 6.0 in, height 4.0 in, dpi 600. The code's Nature preset table specifies 3.5×3.0 in at 300 dpi. An arbitrary invalid preset was accepted and stored unchanged. The option is metadata only in this command path. |
| Typography | **PARTIAL** | R SVG uses Arial 10 px body, 11 px axes, 12 px title; host interaction SVG uses Arial 10/14 px. These are legible. Most CLI Matplotlib SVGs contain zero `<text>` elements and convert Arial glyphs to paths (`ArialMT-*`), reducing editability/accessibility. The PDF path fell back because the R PDF device could not use Arial. |
| Multi-panel composition and panel letters | **FAIL** | Abundance-impact and dFBA are genuine three-axis figures, but none has A/B/C labels. Across all 10 SVGs, no panel letters A/B/C/D were present. Host interaction outputs are four separate files rather than a composed multi-panel figure. |
| Axis labels with units | **FAIL** | Labels include `Growth`, `Growth rate`, `Exchange flux`, `Transfer flux`, `Flux`, `Time`, `Concentration`, and `net exchange flux`, but omit h^-1, h, mmol gDW^-1 h^-1, mmol C gDW^-1 h^-1, or concentration units. The profile legend title is the generic word `label`. |
| Informative legend | **PARTIAL/FAIL** | Strain-growth and abundance legends identify series. The interaction circle has no legend for node colors, edge colors, or line width. The heatmap color bar says only `Flux`. The single-KO legend is overlaid on a large bar and includes categories not present in the one-row data. |
| Data-ink ratio / chartjunk | **PARTIAL** | The simple bar/line plots are clean but visibly default-Matplotlib. The interaction circle has large empty space and crossing arrows, with no scale legend. The one-row KO plot is dominated by one orange rectangle and an overlaid four-item legend. The profile titled “SCFA” actually plots the full external profile, including h, h2o, co2, oxygen, glucose, ammonium, and phosphate. |
| Clipping/legibility | **PASS for inspected samples** | I did not observe clipped labels in the opened profile, abundance, circle, heatmap, or KO TIFFs. Font sizes were legible at the generated dimensions. |

**Publication-readiness call: NOT publication-ready for Nature Genetics/Claude Science without manual redesign.** The core data are exportable and vector-capable, and the R TIFF path can meet 600 dpi/LZW. However, absent units, absent panel letters, unvalidated/ignored journal presets, inconsistent palettes, missing network legends, non-identifiability not shown graphically, outlined SVG text, and uncompressed 300 dpi RGBA line-art TIFFs are material deficiencies.

## 4. Bugs / defects found

### D1 — total-SCFA search can exclude a real producer

Repro: the final S1 carbon-equivalent command above.

Observed: `iAF987+iYO844` independently produced lactate-L 2.352088833, propionate 1.210133703, and succinate 2.292684017, yet the candidate was excluded as `infeasible`, leaving run status `degraded`.

Expected: total/net SCFA ranking should remain feasible when a consortium cannot secrete, or must consume, one member of the SCFA set. That target should contribute zero or a negative net term according to clearly documented semantics; it should not necessarily disqualify the entire combination.

Likely locus: `cmig/core/search.py::joint_target_solve` applies a sign-domain constraint to every present target, and `cmig/core/search_product.py::_evaluate_members_multi` treats any non-optimal per-target capability solve as consortium failure.

### D2 — `render-figure --journal-preset` is ignored and unvalidated

Repro:

```bash
./.venv/bin/cmig render-figure --run-dir runs/codexB/s2_solve_fixture --out REVIEW/scratch_codexB/profile_invalid_preset.svg --renderer matplotlib --format svg --journal-preset definitely_not_a_journal
```

Observed: exit 0, successful figure, and sidecar with invalid preset plus default 6×4 in/600 dpi. `nature` also stayed 6×4/600 instead of the declared 3.5×3.0/300.

Expected: reject unknown presets and apply the selected preset dimensions/dpi.

Likely locus: `cmig/cli/main.py::_cmd_render_figure` and `cmig/render/client.py::FigureSpec.validate`.

### D3 — exact ties are presented as an ordered winner in `search-fixture`

Repro: `s1_search_fixture_final`.

Observed: all three pairs scored exactly 13.358851988170102, but there was no warning, tied-rank field, or degeneracy indicator.

Expected: explicit three-way tie and no implication that alphabetical/list order is a unique optimum.

Likely locus: `cmig/cli/main.py::_cmd_search_fixture`; the newer product search has `_ranking_degeneracy_warnings`, but the fixture output bypasses it.

### D4 — analysis failure returns process exit 0

Repro: `s3_host_microbe_real_unmatched_final`.

Observed: host LP infeasible, top-level run status `failed`, host objective 0, but the command exited 0 and printed “coupling complete.”

Expected: either nonzero process exit for an analysis-failed run, or an explicit CLI policy/flag that distinguishes “workflow artifacts written” from “scientific solve succeeded.”

Likely locus: `cmig/cli/main.py::_cmd_host_microbe_bigg`.

### D5 — default dFBA can grow without consuming the managed carbon substrate

Repro: `s2_dfba_iHN637`.

Observed: biomass increased 0.05→0.06227658 and acetate increased 0→0.50844785 while managed glucose stayed exactly 10.0. The sensitivity endpoint was independent of Km. Residuals are zero only for the managed variables.

Expected: either close or explicitly account for untracked uptake reactions, or prominently warn that growth is supported by other unconstrained/default-medium substrates and the tracked glucose/Km experiment is not interpretable.

Likely locus: `cmig/core/dfba.py::simulate_dfba` and CLI default setup in `cmig/cli/main.py::_dfba_initial_concentrations`.

### D6 — pairwise cross-feeding edges omit their non-identifiable allocation provenance

Repro: inspect `runs/codexB/s2_solve_real_small_bigg/edges.parquet` and `manifest.json`.

Observed: 16 direct strain→strain `cross_feeding` edges are emitted. Source code uses `proportional_shared_pool`, but neither the edge schema nor manifest records the method or `identifiable=false`.

Expected: every allocated edge should carry allocation method and identifiability, and figures should label the network as an inferred shared-pool allocation.

Likely locus: `cmig/core/interactions.py::build_tidy` and the edge schema in `cmig/core/tidy.py`.

### D7 — host KO and host impact are disconnected workflows

Repro: `gene-ko-search` produced the AC2BUT KO; no resulting artifact is accepted directly by `host-microbe-bigg`. The manual scratch-model bridge was required to observe host Δ=-11.25.

Expected: a supported host-aware gene/reaction KO workflow that uses identical media, abundance, interface map, biomass basis, and host objective for baseline and perturbation and emits host-objective delta.

Likely locus: CLI orchestration around `cmig/cli/main.py::_cmd_gene_ko_search`, `cmig/core/host_coupling.py::run_bigg_host_microbe`, and `cmig/core/host_impact.py::host_impact`.

### D8 — figure format defects

Repros are the render commands and generated automatic figures above.

Observed:

- R PDF failed on Arial and silently changed renderer.
- Automatic TIFFs are uncompressed RGBA at 300 dpi.
- Multi-panel plots lack panel letters.
- Axes lack physical units.
- Most screening SVG labels are outlined paths, not `<text>`.
- The circle/bubble figures lack legends for encodings.

Expected: deterministic publication preset, selectable text, LZW RGB TIFF at appropriate 300/600 dpi, panel letters, units, and explanatory legends.

Likely loci: `cmig/render_r/figure.R`, `cmig/cli/main.py::_load_matplotlib_pyplot`, `_save_screening_figure`, `_write_dfba_figure`, `_write_abundance_impact_figures`, and `cmig/core/interaction_figures.py`.

### Transient issue not counted as a final defect

An early `inspect-run` on the abundance run exited 1 in 0.07 s with `NameError: _resolve_run_status is not defined`. The source file changed during execution; after the function appeared, the identical verification command exited 0 and returned `status=ok`. Because it was not reproducible against the final observed tree, I do not count it as a final CMIG defect. It is evidence that this evaluation occurred on a concurrently mutating worktree.

## 5. Prioritized improvement proposals

### P0

1. **Make total-SCFA scoring rank every biologically feasible consortium.** Change `cmig/core/search.py::joint_target_solve` so a consortium that uptakes one SCFA is not made infeasible merely by a per-target secretion-domain constraint. Define and expose one of two defensible semantics: net carbon-equivalent SCFA flux (allow negative individual terms) or nonnegative produced flux via explicit auxiliary variables. Update `cmig/core/search_product.py::_evaluate_members_multi` and add a regression for the observed `iAF987+iYO844` case.

2. **Add a host-aware perturbation workflow.** Extend `cmig/cli/main.py::_cmd_gene_ko_search` or add `host-gene-ko-search` so each gene/reaction/member inhibition is coupled through `cmig/core/host_coupling.py::run_bigg_host_microbe`. Use `cmig/core/host_impact.py::host_impact` plus a host-specific delta structure to emit baseline host objective, perturbed objective, Δ, viability, transfer changes, identical-condition provenance, and failure status.

3. **Make automation failure-safe.** In `cmig/cli/main.py::_cmd_host_microbe_bigg` and `_cmd_host_search_bigg`, return a nonzero code when the community or host solve is non-optimal, unless an explicit `--allow-nonoptimal-result` flag is supplied. Preserve artifacts, but do not print an unqualified “complete.”

### P1

1. **Expose pair analysis as a first-class CLI workflow.** Add `cmig pair` around `cmig/core/pair.py::analyze_pair` and `pair_matrix_rows`; emit mono/co growth, interaction class, MRO, MIP, exchange tables, manifest, run hash, and `inspect-run` support.

2. **Make inferred edges honest in the artifacts.** Extend `cmig/core/interactions.py::build_tidy` and `cmig/core/tidy.py::EDGES_SCHEMA` with `allocation_method`, `identifiable`, supply, and demand fields. Add the method to the solve manifest and label figures “shared-pool proportional allocation.”

3. **Make dFBA medium accounting explicit.** In `cmig/core/dfba.py::simulate_dfba`, either close unlisted extracellular uptake reactions by default or include their extracellular pools in the state. Warn when biomass grows while the nominal managed carbon substrate has zero uptake. Extend `audit_dfba_balance` beyond managed variables.

4. **Actually apply journal presets.** In `cmig/cli/main.py::_cmd_render_figure`, resolve `cmig/render/composer.py::JOURNAL_PRESETS` before constructing `FigureSpec`, and reject unknown values in `cmig/render/client.py::FigureSpec.validate`.

5. **Upgrade figure output defaults.** In `cmig/cli/main.py::_save_screening_figure` and `cmig/core/interaction_figures.py::_save_svg_and_tiff`, use RGB LZW TIFF and 600 dpi for line art; set `svg.fonttype="none"` in `cmig/cli/main.py::_load_matplotlib_pyplot`; add units and A/B/C labels in `_write_dfba_figure` and `_write_abundance_impact_figures`.

6. **Use a single colorblind-safe design system.** Replace `PROFILE_LABEL_COLORS`, `_KO_EFFECT_COLORS`, `EDGE_COLORS`, and local palettes with Okabe–Ito (or a validated equivalent), and add marker/line-style redundancy. Add node/edge/width legends in `cmig/core/interaction_figures.py::_render_circle` and `_render_bubble`.

7. **Emit hashes/manifests for all product workflows.** `inspect-run` returned `run_hash=null` for search, strain-growth, abundance-impact, dFBA, gene KO, and host runs. Add checksummed manifests in `_write_multi_target_outputs`, `_write_gene_ko_search_outputs`, `_write_host_microbe_bigg_outputs`, and analogous writers.

### P2

1. **Reduce multi-target runtime.** In `cmig/core/search_product.py::_evaluate_members_multi` and `search_model_pool_multi`, compute community maximum growth once per candidate, pass it to each `target_max_solve`, and avoid rebuilding the same MICOM community for capability and joint passes. The observed four-candidate run took 269.15 s.

2. **Propagate tie metadata everywhere.** Reuse `cmig/core/search_product.py::_ranking_degeneracy_warnings` in `cmig/cli/main.py::_cmd_search_fixture`, and add shared rank/tie-group columns to rankings.

3. **Add multi-target figures.** Extend `cmig/cli/main.py::_write_multi_target_outputs` to produce a carbon-contribution heatmap/stacked plot with units and, for two targets, a Pareto plot. The tested SCFA run produced no figure.

4. **Fix the R vector font path.** Use Cairo PDF or a device-safe generic family in `cmig/render_r/figure.R`; do not select Arial merely because `systemfonts` can enumerate it. Record renderer fallback prominently in the figure sidecar and CLI status.

5. **Compose the host panels.** Add a Nature-width multi-panel exporter with A/B/C/D labels using the existing interaction circle, heatmap, bubble, and contribution data, rather than four unrelated standalone files.

## 6. What I could not test and why

- **Real human host biology:** no Recon, Human1, or other human GEM ships in `models/`. Network/model downloading and installation were prohibited. Therefore I could not validate human-cell objective choice, host medium, measured biomass scaling, or real interface coverage.
- **Publication-valid host coupling:** the only runnable host was synthetic and used `biomass-basis-kind validation`. The interface maps were generated candidates, not independently curated biological maps. I did not misrepresent these outputs as human or publication-ready.
- **Exhaustive real gene KO:** the selected synthetic model has no GPR genes, so I used an explicit reaction KO. An all-gene screen on the larger real models would not answer the missing host-propagation question and would materially expand runtime. The command's reaction-KO path itself was exercised end to end.
- **Large-pool combinatorial scaling:** only three small GEMs were used. The measured 269.15 s for four SCFA candidates already demonstrated poor scaling; multi-target search refuses more than 100 candidates rather than offering GA/random approximation.
- **Community dFBA:** CMIG exposes only single-model `dfba`. There was no community-dFBA command to test.
- **GUI usability:** the scientific CLI/API paths and generated artifacts were the requested focus. I did not launch the GUI; this does not affect the numerical verdicts above.
- **Stable single-revision replay of every early run:** another process modified source during this evaluation. I reran the decisive S1 carbon search, S3 gene KO, host search, and baseline/KO host couplings after modifications stopped and recorded final source hashes. Earlier S2 numeric outputs were generated after their relevant engine files' final modification times, except for the transient `inspect-run` status helper issue described above.
- **Local dataviz skill:** the brief referenced a local `dataviz` skill, but no such skill was present in the checkout or configured skill roots. I applied the explicit figure criteria from the test brief directly and inspected the actual XML/raster/PDF files.
