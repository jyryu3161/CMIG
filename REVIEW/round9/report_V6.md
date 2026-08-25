# Round-9 V6 report — second-solver reproduction

## Verdict

OSQP is **not a second-solver reproduction of the current real-community result**.
The small committed three-member MICOM fixture still agrees with Gurobi within the
documented QP-approximation tolerance, and the single-model LP/dFBA paths agree at
machine precision. In contrast, the round-8 tutorial community exits 0 under OSQP
while reporting zero member growth and a large, mass-inconsistent flux state. No
tolerance relaxation is defensible.

The tutorial's Gurobi baseline is also stale independently of OSQP: the documented
command now gives `0.16452546330430004 h^-1`, not the tutorial's printed
`0.1502 h^-1`. The current value is `0.01432546330430004 h^-1`
(`9.537592080093235%`)
higher. Basis: commands `T-G` and `A` below, Gurobi 12.0.3, MICOM 0.39.0, CMIG
0.1.0; the historical number is at `docs/cmig_hands_on_tutorial.html:108`.

A reader of published Gurobi community numbers should therefore conclude:

- the committed solve fixture proves only that its very small fixture agrees across
  solvers;
- the real bundled-model tutorial result has **not** been reproduced on OSQP;
- the OSQP tutorial artifacts must not be used as a corroborating result, because
  their growth, profile, and community-basis edges are materially wrong and mutually
  inconsistent;
- the tutorial's printed Gurobi number must be re-run/corrected separately before it
  is quoted.

The bundled models are a methods-demo pool, not a gut community. Nothing here is a
claim about human gut biology.

## Environment, commands, and comparison rule

All measured values in this report use environment `E` unless a source-code-only
capability finding is explicitly identified:

```text
E0: UV_CACHE_DIR=/tmp/cmig-round9-V6-uv-cache uv run --no-sync cmig version
    -> cmig 0.1.0

E1: UV_CACHE_DIR=/tmp/cmig-round9-V6-uv-cache uv run --no-sync cmig solvers
    -> gurobi LP=True QP=True MILP=True available=True
       highs  LP=True QP=False MILP=True available=True
       osqp   LP=True QP=True MILP=False available=True

E2: UV_CACHE_DIR=/tmp/cmig-round9-V6-uv-cache uv run --no-sync python - <<'PY'
    from importlib.metadata import version
    for package in ('cmig','micom','cobra','optlang','gurobipy','osqp','highspy',
                    'numpy','pandas','scipy','pyarrow'):
        print(package, version(package))
    import gurobipy as gp
    print('gurobi_engine', '.'.join(map(str, gp.gurobi.version())))
    PY
    -> micom 0.39.0; cobra 0.31.1; optlang 1.9.0;
       gurobipy/Gurobi engine 12.0.3; osqp 1.1.1; highspy 1.14.0;
       numpy 2.4.6; pandas 2.3.3; scipy 1.17.1; pyarrow 24.0.0
```

The comparison reference is the repository's dual-golden rule:

- `cmig/golden_fixture.py::CROSS_SOLVER_DECIMALS = 4`;
- `tests/test_engine_golden.py::ATOL = 1e-4`;
- `cmig/core/golden.py::tables_close`, which accepts a numeric quantity when
  `abs(OSQP - Gurobi) <= 1e-4 + 1e-5 * abs(Gurobi)`.

I applied that rule to like-for-like quantities throughout. I did not alter or
recommend altering it. Row-key disagreement is not papered over: it is reported as
not comparable/material rather than coerced to zero.

The exact tutorial taxonomy was generated in scratch space as follows. It is the
round-8 tutorial's `iYO844 + iHN637 + iSFV_1184`, equal-abundance community:

```bash
UV_CACHE_DIR=/tmp/cmig-round9-V6-uv-cache uv run --no-sync python - <<'PY'
from pathlib import Path
import pandas as pd
root = Path.cwd()
rows = [
    {"id": "iYO844", "file": str((root / "models/iYO844.xml").resolve()), "abundance": 1/3},
    {"id": "iHN637", "file": str((root / "models/iHN637.xml").resolve()), "abundance": 1/3},
    {"id": "iSFV_1184", "file": str((root / "models/iSFV_1184.xml").resolve()), "abundance": 1/3},
]
pd.DataFrame(rows).to_csv("/tmp/cmig-round9-v6/tutorial_taxonomy.csv", index=False)
pd.DataFrame(rows[:2]).assign(abundance=0.5).to_csv(
    "/tmp/cmig-round9-v6/pair_taxonomy.csv", index=False
)
PY
```

Run IDs used as the basis for every measured table below:

```bash
# T-G / T-O — current round-8 tutorial scenario
UV_CACHE_DIR=/tmp/cmig-round9-V6-uv-cache uv run --no-sync cmig solve \
  --taxonomy /tmp/cmig-round9-v6/tutorial_taxonomy.csv \
  --medium medium_presets/gut_overlay_agora_western.csv \
  --allow-unknown-medium --assume-bigg-namespace --solver gurobi \
  --out /tmp/cmig-round9-v6/tutorial_gurobi

UV_CACHE_DIR=/tmp/cmig-round9-V6-uv-cache uv run --no-sync cmig solve \
  --taxonomy /tmp/cmig-round9-v6/tutorial_taxonomy.csv \
  --medium medium_presets/gut_overlay_agora_western.csv \
  --allow-unknown-medium --assume-bigg-namespace --solver osqp \
  --out /tmp/cmig-round9-v6/tutorial_osqp

# F-G / F-O — committed dual-solver solve fixture
UV_CACHE_DIR=/tmp/cmig-round9-V6-uv-cache uv run --no-sync cmig solve-fixture \
  --solver gurobi --out /tmp/cmig-round9-v6/fixture_gurobi
UV_CACHE_DIR=/tmp/cmig-round9-V6-uv-cache uv run --no-sync cmig solve-fixture \
  --solver osqp --out /tmp/cmig-round9-v6/fixture_osqp

# S-G / S-O — single-model FBA and pFBA
UV_CACHE_DIR=/tmp/cmig-round9-V6-uv-cache uv run --no-sync cmig single \
  --model models/iYO844.xml --solver gurobi --method both \
  --assume-bigg-namespace --out /tmp/cmig-round9-v6/single_gurobi
UV_CACHE_DIR=/tmp/cmig-round9-V6-uv-cache uv run --no-sync cmig single \
  --model models/iYO844.xml --solver osqp --method both \
  --assume-bigg-namespace --out /tmp/cmig-round9-v6/single_osqp

# D-G / D-O — user dFBA smoke comparison
UV_CACHE_DIR=/tmp/cmig-round9-V6-uv-cache uv run --no-sync cmig dfba \
  --model models/iYO844.xml --solver gurobi --t-end 0.2 --dt 0.1 \
  --out /tmp/cmig-round9-v6/dfba_gurobi
UV_CACHE_DIR=/tmp/cmig-round9-V6-uv-cache uv run --no-sync cmig dfba \
  --model models/iYO844.xml --solver osqp --t-end 0.2 --dt 0.1 \
  --out /tmp/cmig-round9-v6/dfba_osqp

# DS-G / DS-O — controlled, interpretable one-point dFBA sensitivity comparison
INITIAL='EX_glc__D_e=10,EX_o2_e=20,EX_ac_e=0,EX_nh4_e=100,EX_pi_e=100,EX_k_e=100,EX_so4_e=100,EX_mg2_e=100,EX_fe3_e=100,EX_ca2_e=100'
UV_CACHE_DIR=/tmp/cmig-round9-V6-uv-cache uv run --no-sync cmig dfba-sensitivity \
  --model models/iYO844.xml --solver gurobi --t-end 0.2 --dts 0.1 --kms 0.01 \
  --initial "$INITIAL" --close-untracked-uptake \
  --out /tmp/cmig-round9-v6/sensitivity_gurobi
UV_CACHE_DIR=/tmp/cmig-round9-V6-uv-cache uv run --no-sync cmig dfba-sensitivity \
  --model models/iYO844.xml --solver osqp --t-end 0.2 --dts 0.1 --kms 0.01 \
  --initial "$INITIAL" --close-untracked-uptake \
  --out /tmp/cmig-round9-v6/sensitivity_osqp

# SW — solver-selectable fixture sweep
UV_CACHE_DIR=/tmp/cmig-round9-V6-uv-cache uv run --no-sync cmig sweep-fixture \
  --tradeoff-fs 0.5 --solvers gurobi,osqp \
  --out /tmp/cmig-round9-v6/sweep_fixture_both
```

Artifact comparisons (`A`) read the paired JSON/CSV/Parquet outputs with pandas
and PyArrow, outer-joined stable keys, calculated `OSQP - Gurobi`, and applied the
rule above. Community growth was reconstructed as
`sum(nodes.growth * nodes.abundance)` over member nodes. Edge reconciliation used
only `secretion`/`uptake` edges, signed secretion positive and uptake negative;
`cross_feeding` was excluded as required by tidy schema 1.3.

The consolidated reproducible form of comparison command `A` is:

```bash
UV_CACHE_DIR=/tmp/cmig-round9-V6-uv-cache uv run --no-sync python - <<'PY'
from pathlib import Path
import json
import pandas as pd
import pyarrow.parquet as pq

B = Path("/tmp/cmig-round9-v6")
ATOL, RTOL = 1e-4, 1e-5

def parquet(run, name):
    return pq.read_table(B / run / f"{name}.parquet").to_pandas()

def growth(run):
    nodes = parquet(run, "nodes")
    members = nodes[nodes.node_type == "member"]
    return float((members.growth * members.abundance).sum())

def compare(g_run, o_run, name, keys, column):
    g = parquet(g_run, name)[keys + [column]].rename(columns={column: "gurobi"})
    o = parquet(o_run, name)[keys + [column]].rename(columns={column: "osqp"})
    joined = g.merge(o, on=keys, how="outer", indicator=True)
    both = joined[joined._merge == "both"].dropna(subset=["gurobi", "osqp"]).copy()
    both["abs_delta"] = (both.osqp - both.gurobi).abs()
    both["tolerance"] = ATOL + RTOL * both.gurobi.abs()
    both["within"] = both.abs_delta <= both.tolerance
    print(g_run, name, {
        "gurobi_rows": len(g), "osqp_rows": len(o), "common_finite": len(both),
        "gurobi_only": int((joined._merge == "left_only").sum()),
        "osqp_only": int((joined._merge == "right_only").sum()),
        "within": int(both.within.sum()), "outside": int((~both.within).sum()),
        "max_abs_delta": float(both.abs_delta.max()),
    })
    return both

for prefix in ("fixture", "tutorial"):
    print(prefix, "growth", growth(f"{prefix}_gurobi"), growth(f"{prefix}_osqp"))
    compare(f"{prefix}_gurobi", f"{prefix}_osqp", "nodes", ["node_id"], "growth")
    compare(f"{prefix}_gurobi", f"{prefix}_osqp", "profile", ["metabolite"], "net_flux")
    compare(
        f"{prefix}_gurobi", f"{prefix}_osqp", "edges",
        ["source_id", "target_id", "metabolite", "edge_type"], "weight",
    )

tg, to = growth("tutorial_gurobi"), growth("tutorial_osqp")
print("tutorial growth delta/tolerance", to - tg, ATOL + RTOL * abs(tg))
print("tutorial documented delta/percent", tg - 0.1502, (tg - 0.1502) / 0.1502 * 100)
for metabolite in ("ac", "arab__D"):
    values = []
    for solver in ("gurobi", "osqp"):
        profile = parquet(f"tutorial_{solver}", "profile")
        values.append(float(profile.loc[profile.metabolite == metabolite, "net_flux"].iloc[0]))
    print("tutorial profile", metabolite, values, "delta", values[1] - values[0])

for solver in ("gurobi", "osqp"):
    profile = parquet(f"tutorial_{solver}", "profile")[["metabolite", "net_flux"]]
    edges = parquet(f"tutorial_{solver}", "edges")
    non_cross = edges[edges.edge_type.isin(["secretion", "uptake"])].copy()
    non_cross["signed"] = non_cross.weight.where(
        non_cross.edge_type == "secretion", -non_cross.weight
    )
    edge_sum = non_cross.groupby("metabolite", as_index=False).signed.sum().rename(
        columns={"signed": "edge_sum"}
    )
    joined = profile.merge(edge_sum, on="metabolite", how="outer").fillna(0.0)
    joined["abs_residual"] = (joined.edge_sum - joined.net_flux).abs()
    joined["within"] = joined.abs_residual <= ATOL + RTOL * joined.net_flux.abs()
    acetate = joined[joined.metabolite == "ac"].iloc[0]
    print("edge reconciliation", solver, {
        "union": len(joined), "within": int(joined.within.sum()),
        "outside": int((~joined.within).sum()),
        "max_abs_residual": float(joined.abs_residual.max()),
        "acetate_profile": float(acetate.net_flux),
        "acetate_edge_sum": float(acetate.edge_sum),
        "acetate_residual": float(acetate.edge_sum - acetate.net_flux),
        "edge_rows": len(edges), "cross_feeding": int((edges.edge_type == "cross_feeding").sum()),
    })

for solver in ("gurobi", "osqp"):
    summary = json.loads((B / f"single_{solver}" / "single_summary.json").read_text())
    print("single objectives", solver, summary["methods"])
g = pd.read_csv(B / "single_gurobi" / "single_fluxes.csv").rename(columns={"flux": "gurobi"})
o = pd.read_csv(B / "single_osqp" / "single_fluxes.csv").rename(columns={"flux": "osqp"})
s = g.merge(o, on=["method", "reaction_id"])
s["abs_delta"] = (s.osqp - s.gurobi).abs()
s["outside"] = s.abs_delta > ATOL + RTOL * s.gurobi.abs()
print("single reaction fluxes", s.groupby("method").agg(
    rows=("outside", "size"), outside=("outside", "sum"), max_abs=("abs_delta", "max")
))
g = pd.read_csv(B / "single_gurobi" / "exchange_summary.csv").rename(columns={"flux": "gurobi"})
o = pd.read_csv(B / "single_osqp" / "exchange_summary.csv").rename(columns={"flux": "osqp"})
x = g.merge(o, on="reaction_id")
print("single exchange rows/max", len(x), float((x.osqp - x.gurobi).abs().max()))

g = parquet("dfba_gurobi", "timecourse")[["t", "series", "value"]].rename(
    columns={"value": "gurobi"}
)
o = parquet("dfba_osqp", "timecourse")[["t", "series", "value"]].rename(
    columns={"value": "osqp"}
)
d = g.merge(o, on=["t", "series"], how="outer", indicator=True)
both = d[d._merge == "both"].copy()
both["abs_delta"] = (both.osqp - both.gurobi).abs()
both["within"] = both.abs_delta <= ATOL + RTOL * both.gurobi.abs()
print("dfba timecourse", len(g), len(o), len(both), int(both.within.sum()),
      float(both.abs_delta.max()))
for solver in ("gurobi", "osqp"):
    summary = json.loads((B / f"dfba_{solver}" / "dfba_summary.json").read_text())
    print("dfba summary", solver, summary["final_biomass"],
          summary["final_growth_rate"], summary["final_concentrations"],
          summary["n_untracked_uptake"])
    sensitivity = json.loads(
        (B / f"sensitivity_{solver}" / "dfba_sensitivity.json").read_text()
    )
    print("sensitivity", solver, sensitivity["acceptance"], sensitivity["rows"])

for solver in ("gurobi", "osqp"):
    fresh = json.loads((B / f"fixture_{solver}" / "manifest.json").read_text())
    frozen = json.loads(
        (Path("fixtures/community_3_member/expected") / solver / "config.json").read_text()
    )
    print("fixture hash", solver, fresh["run_hash"], fresh["float_decimals"],
          frozen["run_hash"], frozen["golden_decimals"],
          fresh["components"]["abundance"], frozen["components"]["abundance"])
PY
```

## OSQP-capable surface inventory

This inventory comes from `E1`, parser introspection of
`cmig.cli.main::build_parser`, and the named code guards. “Selectable” means the
CLI exposes an OSQP choice; it does not mean the current result is scientifically
valid.

| Surface | CLI solver surface | Current OSQP status and code-level reason |
|---|---|---|
| `solve-fixture`, `solve` | `{gurobi,osqp}` | Selectable. `cmig.core.engine::ALLOWED_CMIG_SOLVERS` contains exactly these two. `_solver_split` records OSQP as `growth_solver=osqp`, `flux_solver=None`, `qp_only_approximate`. |
| `solve --fva`, `solve-fixture --fva`, `sweep --fva` | Base command accepts OSQP | Cannot run the FVA part. `cmig.core.fva::community_fva` explicitly rejects OSQP because repeated re-optimization degrades to `time_limit`; reproduction `R-FVA` is below. |
| `sweep-fixture`, `sweep` | free-form comma list in `--solvers` | OSQP reaches the same community engine and is selectable in practice (`SW`). The parser does not validate the list; `highs` parses but the community-engine guard rejects it. |
| `single` | `{gurobi,osqp}` | Selectable. `cmig.core.single_model::_require_lp` uses the capability matrix; `set_model_solver` handles the OSQP optlang hybrid. For these single-model LP operations, OSQP selectability depends on both OSQP and HiGHS being importable. |
| `dfba`, `dfba-sensitivity` | `{gurobi,osqp}` | Selectable. Both use the single-model LP helper at each step; OSQP therefore follows the OSQP/HiGHS hybrid LP path, not the MICOM community QP-only path. |
| `sandbox-fixture` | `{gurobi,osqp}` | Selectable utility; it wraps the fixture community solve. Both preview runs completed in E. |
| `pair` | `{gurobi}` | Cannot run. Parser gate only; `R-P` records the exact refusal. |
| `minimal-medium` | `{gurobi}` | Cannot run. In addition to the parser gate, `minimal_medium_cardinality` requires MILP and raises `MILPUnavailableError` when `capability.milp` is false; E1 reports OSQP `MILP=False`. |
| Host stack: `host-fixture`, `host-generic`, `host-benchmark`, `host-microbe-bigg`, `host-ko-impact`, `host-search-bigg` | `{gurobi}` | Cannot run from the CLI: every parser pins `choices=["gurobi"]`. `host-map` is solver-independent and performs no solve. |
| Search stack: `search`, `search-fixture`, `search-advanced-fixture` | `{gurobi}` | Cannot run, including random/exhaustive/GA modes. GA changes consortium enumeration, but every fitness evaluation still enters the Gurobi-pinned community/target solve. |
| `strain-growth`, `abundance-impact`, `gene-ko-search` | `{gurobi}` | Cannot run. Each parser is Gurobi-only; these surfaces perform repeated community solves (and optional target/FVA work). |
| `dfba-fixture` | `{gurobi}` | Cannot select OSQP even though the user `dfba` command can; this is an explicit parser restriction. |
| `model-quality`, `publication-benchmark` | `{gurobi}` | Cannot run on OSQP from the CLI. The integrated publication benchmark also contains Gurobi-only community/search/host children. |
| Community dFBA (`cmig.core.dfba_community::run_community_dfba`) | no CLI surface | Cannot run. The library guard rejects any solver other than Gurobi because integration requires a full member-level pFBA flux vector; OSQP community provenance is QP-only approximate. |
| `delta`, `host-map`, `render-figure`, `spatial-preview`, `stats-demo`, `stats-sweep`, `namespace-suggest`, `model-review`, inspection/version/workflow commands | no solver selector | Solver-independent post-processing, preflight, or non-FBA work. These do not constitute a second-solver reproduction. |

The matrix's `highs` row is therefore a backend capability statement, not a usable
community-analysis choice. No singular `--solver` option accepts `highs` in the
current parser.

## Numerical reproduction results

### 1. Dual-golden fixture: reproduced within tolerance

Basis: `F-G`, `F-O`, `A`, and environment E.

| Quantity | Gurobi | OSQP | absolute delta | Classification |
|---|---:|---:|---:|---|
| Community growth | 0.43696075348421687 | 0.43696075348421537 | 1.4988010832439613e-15 | within tolerance |
| Maximum member-growth delta (3 members) | — | — | 1.223266062944095e-6 | all 3 within tolerance |
| Maximum profile `net_flux` delta (8 rows) | — | — | 5.3290705182007514e-14 | all 8 within tolerance |
| Maximum community-basis edge-weight delta (24 keyed rows) | — | — | 1.1247895201904612e-5 | all 24 within tolerance |

`cmig golden verify` also exited 0 in environment E and confirmed both committed
MICOM versions and stored hashes. The focused `tests/test_engine_golden.py` run
re-solved both variants and passed.

This is genuine agreement, but its scope is only the bundled test-taxonomy fixture.

### 2. Round-8 tutorial community: material deviation and invalid OSQP artifacts

Basis: `T-G`, `T-O`, `A`, and environment E. Both runs used the same taxonomy,
medium, `tradeoff_f=0.5`, merge semantics, and namespace policy. Both recorded the
same four unapplied overlay rows (`EX_2obut_m`, `EX_4hbz_m`, `EX_n2_m`,
`EX_oxa_m`). OSQP nevertheless exited 0 and carried no solver-failure diagnostic.

| Quantity | Gurobi | OSQP | OSQP − Gurobi | Reference tolerance | Classification |
|---|---:|---:|---:|---:|---|
| Community growth (h^-1) | 0.16452546330430004 | 0.0 | -0.16452546330430004 | 0.00010164525463304301 | material |
| `iHN637` growth | 0.20740609501944907 | 0.0 | -0.20740609501944907 | 0.0001020740609501945 | material |
| `iSFV_1184` growth | 0.20616457211873437 | 0.0 | -0.20616457211873437 | 0.00010206164572118735 | material |
| `iYO844` growth | 0.08000572277471674 | 0.0 | -0.08000572277471674 | 0.00010080005722774717 | material |
| Acetate profile `net_flux` | 1.2005021369387077 | 0.317869956243944 | -0.8826321806947637 | 0.00011200502136938708 | material |
| `arab__D` profile `net_flux` | -0.1 | 905.0117031505916 | 905.1117031505917 | 0.000101 | material |

The keyed structures also diverged (same command/version basis):

- profile: Gurobi wrote 109 rows, OSQP 72; only 16 metabolite keys were common,
  and all 16 common `net_flux` values were outside tolerance. There were 93
  Gurobi-only and 56 OSQP-only profile keys;
- community-basis edges: Gurobi wrote 240 rows (40 cross-feeding), OSQP 116
  (2 cross-feeding); only 21 full edge keys were common, and none of those 21
  weights was within tolerance. The largest common-key delta was
  33.133035219353815 mmol gDW_community^-1 h^-1;
- signed non-cross edge reconstruction: all 117 Gurobi profile/edge metabolite
  keys reconciled within the reference rule (maximum residual
  1.5543122344752192e-15). Only 1 of 161 OSQP union keys reconciled; 160 failed,
  with maximum residual 1533.8919593145802;
- acetate is a concrete internal inconsistency: Gurobi's signed community-edge
  sum and profile are both 1.2005021369387077. OSQP's acetate profile is
  0.317869956243944 but its signed community-edge sum is only
  0.09071578070725364, a residual of -0.22715417553669034.

These are not alternate-optimum-scale differences. The OSQP run is a materially
different and internally inconsistent state that is currently mislabeled as a
successful solve. Published Gurobi profile or cross-feeding conclusions from this
scenario receive no support from OSQP.

### 3. `pair` and `minimal-medium`: exact OSQP refusals

Basis: commands `R-P`/`R-M`, environment E. Both exit 2 before a solve.

```bash
# R-P
UV_CACHE_DIR=/tmp/cmig-round9-V6-uv-cache uv run --no-sync cmig pair \
  --taxonomy /tmp/cmig-round9-v6/pair_taxonomy.csv --solver osqp \
  --out /tmp/cmig-round9-v6/pair_osqp
```

```text
cmig pair: error: argument --solver: invalid choice: 'osqp' (choose from gurobi)
```

```bash
# R-M
UV_CACHE_DIR=/tmp/cmig-round9-V6-uv-cache uv run --no-sync cmig minimal-medium \
  --model models/iYO844.xml --solver osqp --min-growth 0.01 \
  --assume-bigg-namespace --out /tmp/cmig-round9-v6/minimal_osqp
```

```text
cmig minimal-medium: error: argument --solver: invalid choice: 'osqp' (choose from gurobi)
```

The minimal-medium refusal is scientifically necessary for OSQP because it lacks
MILP capability. The pair refusal is the current CLI support policy.

### 4. `single`: outward result reproduced; internal routing not comparable

Basis: `S-G`, `S-O`, `A`, and environment E.

| Quantity | Gurobi | OSQP | absolute delta | Classification |
|---|---:|---:|---:|---|
| FBA growth objective | 0.11796638932239924 | 0.11796638932239903 | 2.0816681711721685e-16 | within tolerance |
| pFBA growth objective | 0.11796638932239924 | 0.11796638932239903 | 2.0816681711721685e-16 | within tolerance |
| Exchange summary | 229 keyed rows | 229 keyed rows | maximum 0.0 | all within tolerance |

The full internal reaction vector is not a solver-independent publication
quantity here. Of 2500 method/reaction rows, 32 exceeded the cross-solver numeric
tolerance: 28 FBA rows (maximum absolute delta 0.053816) and 4 pFBA rows (maximum
0.679484). Growth and all exchange fluxes were unchanged, so these are alternate
internal pathway allocations, not a changed external phenotype. They are classified
**not comparable**, not used to claim a material growth/profile deviation.

### 5. Single-model dFBA: solver numerics reproduce

Basis: `D-G`, `D-O`, `DS-G`, `DS-O`, `A`, and environment E.

The short `dfba` runs had identical 15-row timecourse structure. All 15 values were
within tolerance; the maximum absolute delta was 2.498001805406602e-16. Final
biomass was 0.010237018390721117 (Gurobi) versus 0.010237018390721116 (OSQP), and
final growth was 0.1178151617636744 versus 0.11781516176367424. The three final
tracked concentrations were byte-value equal in the summaries: acetate 0.0,
glucose 9.996583388321687, and oxygen 19.98852988943833.

Those two smoke runs each warned that 7 default-medium uptake substrates were
untracked, so their substrate/Km experiment is not scientifically interpretable.
That warning is preserved rather than omitted from the verdict.

The controlled one-point `dfba-sensitivity` runs closed untracked uptake, tracked
all listed nutrients, exited 0, and recorded `acceptance.interpretable=true` with
no untracked uptake. Their final biomass differed only at approximately 1e-18, all
listed final concentrations agreed, and both balance residuals were 0.0. This is a
valid within-tolerance reproduction of the single-model dynamic path for that one
short grid point; it is not a broad biological sensitivity study.

### 6. Sweep, sandbox, and community FVA boundaries

Basis: `SW`, `F-G`, `F-O`, environment E. The two-row solver fixture sweep completed
and reproduced the same fixture growth comparison as section 1. Both sandbox
preview variants also completed; this verifies selectability but adds no independent
scientific result.

Community FVA remains intentionally unavailable on OSQP. Exact reproduction
(`R-FVA`, environment E), exit 2:

```bash
UV_CACHE_DIR=/tmp/cmig-round9-V6-uv-cache uv run --no-sync cmig solve-fixture \
  --solver osqp --fva --out /tmp/cmig-round9-v6/fixture_osqp_fva
```

```text
FVA 미지원: community FVA 는 osqp 미지원 — osqp 는 QP-only approximate(§4.2)이며 FVA 반복 재최적화에서 time_limit 으로 퇴화한다. --solver gurobi 를 사용하라.
```

## Honest status table

All classifications below refer to environment E and the commands/bases named in
the result sections.

| Analysis | OSQP status | What a reader should conclude |
|---|---|---|
| Committed three-member solve fixture | **Reproduced within tolerance** | Numeric fixture agreement is real but narrow. |
| Round-8 tutorial three-member AGORA Western solve | **Deviates materially** | OSQP growth is zero versus Gurobi 0.16452546330430004; profile and edges are also materially different and internally inconsistent. Do not cite OSQP as corroboration. |
| Tutorial's printed Gurobi baseline | **Not reproduced by current Gurobi** | Current Gurobi is 0.16452546330430004 versus printed 0.1502; correct/rerun the tutorial independently of OSQP. |
| Community profile and community-basis edge weights, tutorial | **Deviates materially** | Common keys fail tolerance and OSQP edge sums fail the documented profile identity. Published Gurobi flux/edge claims remain Gurobi-only. |
| `pair` | **Cannot run** | Parser accepts only Gurobi; exact exit-2 refusal recorded. |
| `single` objective/exchange phenotype | **Reproduced within tolerance** | Growth and all 229 exchange rows agree. Internal alternate-path reaction vectors are not comparable. |
| `minimal-medium` | **Cannot run** | Parser is Gurobi-only and OSQP lacks MILP. |
| User `dfba` | **Reproduced within tolerance numerically** | Short trajectory agrees, but the particular smoke run is scientifically uninterpretable because of untracked uptake. |
| Controlled `dfba-sensitivity` point | **Reproduced within tolerance** | Interpretable short point agrees; no claim beyond this point/grid. |
| `sweep-fixture` | **Reproduced within tolerance** | It wraps the agreeing solve fixture. A real OSQP sweep inherits the real-community defect. |
| `sandbox-fixture` | **Reproduced within tolerance as a utility** | Selectability works on the fixture; not an independent biological analysis. |
| Community FVA on `solve`/fixture/sweep | **Cannot run** | Explicit OSQP capability rejection, exit 2. |
| Host stack | **Cannot run** | Every solver-taking host CLI is Gurobi-only. |
| Search, including GA | **Cannot run** | Search parsers are Gurobi-only; GA does not change the solver restriction. |
| Strain growth, abundance impact, gene KO search | **Cannot run** | Parsers are Gurobi-only. |
| `dfba-fixture` | **Cannot run** | Parser is Gurobi-only although user dFBA supports OSQP. |
| Model quality / publication benchmark | **Cannot run** | Parsers are Gurobi-only. |
| Library community dFBA | **Cannot run** | Explicit Gurobi-only guard; no CLI surface. |

## Integration notes and actual defects

### Defect 1 — real community OSQP path silently publishes an invalid success

Minimal reproduction is `T-O` above. It exits 0, labels the solve optimal, and
writes artifacts, but all three member growth values are zero, profile magnitudes
reach values orders of magnitude beyond the Gurobi state, and 160 of 161 signed
edge/profile union keys fail the already-generous cross-solver reference rule.
There is no solver warning or failure diagnostic. This conflicts with the advertised
OSQP-capable `solve` surface and is the highest-priority integration finding.

Suggested coordinator follow-up: until the root cause is fixed, fail closed on an
OSQP community solution that violates member-growth/profile/edge consistency rather
than publishing it as optimal. Do not loosen the tolerance.

### Defect 2 — fresh OSQP solve fixture does not emit its frozen run hash

Basis: `F-O`, `cmig golden verify`, and artifact comparison `A`, environment E.

- committed OSQP published hash: `a422eb89d019f917f7fc334db8e9a2eff7d89ce49031ccbf215df7bd404d3d9d`;
- fresh `cmig solve-fixture --solver osqp`: `c491a6a8ffd303e9a6a95146a1331c09a15d19aea474398714ace8c192cb4eed`;
- fresh Gurobi fixture still emits its committed
  `29844e29103603324d118cc9a8b9ae4fa2a79070418860cfc2ed70095cef29ab`.

The cause is visible in code/data: `EngineService.solve_fixture` calls
`_run_hash_components(result)` with the default 6 decimals, while the frozen OSQP
variant is defined at 4 decimals. Fresh components therefore contain abundance
`0.333333`; the stored OSQP components contain `0.3333`. `cmig golden verify` still
passes because it recomputes each stored config from its own stored components and
precision; it does not execute the CLI and compare a fresh manifest to the frozen
variant.

This is unexpected frozen-hash drift. Per the common brief, I stopped at recording
it: no re-bless, fixture edit, hash change, or code fix was made.

### Defect 3 — tutorial Gurobi output is stale

Basis: `T-G`, `A`, environment E, compared with
`docs/cmig_hands_on_tutorial.html:108`. The live documented command gives
0.16452546330430004 h^-1, while the tutorial prints 0.1502 h^-1 and a different
run-hash prefix. The coordinator should not mechanically replace the number until
the intended taxonomy CSV/model checksums and post-round-8 medium semantics are
confirmed, but the current printed number is not reproducible as written.

## Verification log

All commands used the required cache and no-sync prefix in environment E.

| Command | Result |
|---|---|
| `cmig version` | exit 0; CMIG 0.1.0 |
| `cmig solvers` | exit 0; Gurobi, HiGHS, and OSQP available with the E1 matrix |
| `cmig golden verify` | exit 0; both stored MICOM versions and stored hashes reported OK |
| `cmig golden verify-envelope` | exit 0; 17 workflow kinds plus float-normalization probe OK |
| `ruff check .` | exit 0; all checks passed |
| `mypy cmig` | exit 0; no issues in 78 source files |
| `pytest -q tests/test_engine_golden.py tests/test_solver_and_cli.py tests/test_single_model.py tests/test_dfba.py tests/test_community_fva.py tests/test_sweep.py` | exit 0; 63 passed; 5 expected dependency/solver warnings |
| `T-G`, `T-O` | both exit 0; material OSQP defect described above |
| `F-G`, `F-O` | both exit 0; numeric artifacts within tolerance; fresh OSQP hash defect described above |
| `S-G`, `S-O` | both exit 0 |
| `D-G`, `D-O`, `DS-G`, `DS-O`, `SW` | all exit 0 |
| `R-P`, `R-M`, `R-FVA` | expected exit 2 refusals, quoted above |

No Qt/GUI command was needed for this report-only solver track, so the known
QtWebEngine sandbox SIGTRAP was not encountered.

## Proposed CHANGELOG entries

This track changes no behavior, so it has no direct “Fixed” entry. If the
coordinator records verification/known-limitations findings in `[Unreleased]`, I
propose:

- **Known limitation — OSQP real-community solve is not publication-safe.** The
  dual-solver fixture agrees within the documented tolerance, but the bundled
  three-member AGORA Western tutorial exits successfully with zero OSQP member
  growth and mass-inconsistent profile/edge artifacts; real community results
  remain Gurobi-only pending a fail-closed fix.
- **Known reproducibility defect — OSQP fixture CLI hash.** A fresh
  `solve-fixture --solver osqp` hashes at the default 6-decimal path and does not
  emit the frozen 4-decimal OSQP run hash, although `golden verify` passes its
  stored-config-only check.
- **Documentation correction required.** The hands-on tutorial's printed Gurobi
  growth 0.1502 is not reproduced by its current documented command, which gives
  0.16452546330430004 in CMIG 0.1.0 / MICOM 0.39.0 / Gurobi 12.0.3.

If fixes land later, their CHANGELOG entries should describe the actual validation
and acceptance behavior rather than claim that this report itself fixed them.

## Proposals deliberately not implemented

- No `cmig/**`, tests, documentation, fixture, dependency, or golden file was
  edited; V6 owns only this report.
- No tolerance was loosened and no material delta was relabeled as approximation
  noise.
- No OSQP community result was re-blessed.
- No CLI choice was added or removed, including `highs`, `pair`, host, search,
  minimal-medium, or community-dFBA surfaces.
- No report number was substituted into the hands-on tutorial.
- No scratch outputs under `/tmp/cmig-round9-v6/` are proposed for commit.
- No Git command was run and nothing was pushed.
