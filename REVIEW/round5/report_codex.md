# P3 — Codex gpt-5.6-sol

All commands were run from `/Users/jaeyongryu/orca/CMIG-wt-io` with:

```bash
export PYTHONPATH=/Users/jaeyongryu/orca/CMIG-wt-io
export CMIG_PY=/Users/jaeyongryu/orca/CMIG/.venv/bin/python
```

## 1. Summary

Verdict:

- I/O: **FAIL** — SBML semantics round-trip correctly, and the ordinary dFBA/model-quality CSVs retain binary64 values, but reproducibility hashes collide for distinct answer-determining inputs, renderer CSV adapters change values, and most artifact families are not failure-atomic.
- Exception handling / logging: **FAIL** — four broad handlers substitute scientific defaults; two product workflows publish failed evaluations as zeros and exit 0; an expired Gurobi licence produces a raw traceback; no durable application log exists.
- Security: **PARTIAL** — no first-party dynamic evaluation, unsafe deserialisation, `shell=True`, archive extraction, or R command injection reproduced. `FileSystemStore.record_run()` does permit path traversal through an unchecked `run_hash`.

Confirmed findings: **6 P0, 3 P1, 4 P2**.

The advertised “34 `except Exception` sites” has drifted: this checkout has **33**, enumerated and classified below.

Test gate:

```text
pytest -q tests/
728 passed, 2 skipped, 1 failed (731 collected)
```

The single failure was `tests/test_render.py::test_render_client_passes_project_rlib`: the worktree code supplied `/Users/jaeyongryu/orca/CMIG-wt-io/.Rlib`, while the test requires a path ending `/CMIG/.Rlib`. Neither directory exists. This is recorded in section 5 rather than counted as a product finding because an actual R render succeeded and recorded the exact R/package versions.

## 2. Findings

### F1 [P0] Distinct scientific inputs and distinct solver answers receive the same reproducibility hash

- file:line: `cmig/core/manifest.py:40,60-79`; `cmig/core/workflow_manifest.py:150-175`; `cmig/core/medium_spec.py:19,254-262`
- What is wrong: all answer-determining floats are rounded to six decimal places before both serialization and hashing. The manifest therefore discards the true values, not merely solver-output noise. I confirmed collisions for solve bounds, abundances, tradeoff fractions, workflow growth fractions, target weights, solver tolerances, and medium uptake limits. A real Gurobi model with objective upper bounds `1e-7` and `4e-7` returned different objectives, but both `RunHashComponents` instances serialized the bound as `0.0` and received the same hash. This directly contradicts the manifest’s reproducibility claim and demonstrates that the prior “changing `--growth-fraction` changes the hash” fix does not hold below six decimals.
- Repro:

```python
from cobra import Model, Reaction
from cmig.core.manifest import RunHashComponents, compute_run_hash
for upper in (1e-7, 4e-7):
    m=Model("x"); r=Reaction("R"); r.bounds=(0,upper); m.add_reactions([r]); m.objective="R"
    c=RunHashComponents("m","med",["a"],{"a":1.0},{"R":[0.0,upper]},.5,{},"x","x",[],"pfba"); print(upper,m.optimize().objective_value,compute_run_hash(c))
```

Observed:

```text
1e-07 1e-07 1ae1edb08fb97b8035f0bc15cda884dfcaa1149a2a6ebe8c3dc56b379146560d
4e-07 4e-07 1ae1edb08fb97b8035f0bc15cda884dfcaa1149a2a6ebe8c3dc56b379146560d
```

Additional observed collisions:

```text
workflow growth_fraction 0.5000001 vs 0.5000004 -> both recorded 0.5, same hash
workflow target weight 1e-7 vs 4e-7          -> both recorded 0.0, same hash
workflow solver tolerance 1.1e-7 vs 4.4e-7  -> both recorded 0.0, same hash
solve abundance 1e-7 vs 4e-7                -> both recorded 0.0, same hash
medium uptake 1e-7 vs 4e-7                  -> same medium checksum
```

- Observed vs expected: observed different solver results and different input files can share a hash whose manifest components are identical. Expected every answer-determining binary64 input to be represented losslessly; rounding belongs only in output/golden comparison, never input identity.
- Minimal patch:

```diff
--- a/cmig/core/manifest.py
+++ b/cmig/core/manifest.py
@@
-DEFAULT_FLOAT_DECIMALS = 6
+DEFAULT_FLOAT_DECIMALS = 17
```

```diff
--- a/cmig/core/medium_spec.py
+++ b/cmig/core/medium_spec.py
@@
-        {k: round(float(v), _DECIMALS) for k, v in sorted(spec.uptake.items())},
+        {k: float(v) for k, v in sorted(spec.uptake.items())},
```

Bump both manifest schema versions and regenerate the frozen hashes. A stronger patch is a separate lossless input canonicalizer (`float.hex()` or JSON’s round-trip representation) while retaining six-decimal normalization only for golden output comparisons.

### F2 [P0] Both publication renderer adapters silently round data to six decimals before plotting

- file:line: `cmig/render/client.py:195-209`; `cmig/render/composer.py:75-81`
- What is wrong: `_write_csv()` rounds `net_flux` and `ui_flux`, and `_write_panel_csv()` rounds heatmap values and network/chord weights. These temporary CSVs are the actual data supplied to R. Thus a figure and its provenance hash describe altered values rather than the in-memory results. This affects the R renderer only; the matplotlib fallback uses the original floats, so the same requested figure can differ by renderer.
- Repro:

```python
import csv, tempfile
from pathlib import Path
from cmig.render.client import _write_csv
with tempfile.TemporaryDirectory(dir=Path.cwd()) as d:
    p=Path(d)/"x.csv"; _write_csv([{"metabolite":"한글,\n줄","net_flux":4.9e-7,"ui_flux":4.9e-7,"label":"secretion"}],p)
    print(next(csv.DictReader(p.open(newline=""))))
```

Observed:

```text
{'metabolite': '한글,\n줄', 'net_flux': '0.000000', 'ui_flux': '0.000000', 'label': 'secretion'}
```

The three reverse probes `1.2345678901234567`, `4.9e-7`, and `-4.9e-7` became respectively `1.234568`, `0.000000`, and `-0.000000` in profile, network, chord, and heatmap CSVs; all 12 binary64 round-trip comparisons were false.

- Observed vs expected: observed the R inputs change, including non-zero values becoming zero. Expected round-trip-identical numeric values and deterministic formatting via `repr()`/`.17g`.
- Minimal patch:

```diff
--- a/cmig/render/client.py
+++ b/cmig/render/client.py
@@
-    return f"{v:.{_CSV_DECIMALS}f}"
+    return repr(v)
--- a/cmig/render/composer.py
+++ b/cmig/render/composer.py
@@
-    return "" if not math.isfinite(v) else f"{v:.6f}"
+    return "" if not math.isfinite(v) else repr(v)
```

### F3 [P0] Objective-inspection failures are misreported as a real zero-objective model

- file:line: `cmig/io/model_import.py:90-102`
- What is wrong: `_biomass_reactions()` catches every `Exception` and returns `[]`. COBRA returns an empty mapping normally when no objective exists, so the catch is unnecessary for that case. Runtime/API failures are converted into the scientific claims `n_objective_terms=0`, `n_biomass=0`, and “no objective reaction detected,” with no indication that objective inspection failed.
- Repro:

```python
from cobra.io import read_sbml_model
from unittest.mock import patch
from cmig.io.model_import import _biomass_reactions, objective_structure_warning
m=read_sbml_model("models/iYO844.xml")
for e in (RuntimeError("solver"), ValueError("bad objective"), AttributeError("API drift")):
    with patch("cobra.util.solver.linear_reaction_coefficients",side_effect=e): print(type(e).__name__,_biomass_reactions(m),objective_structure_warning(0))
```

Observed:

```text
actual objective: ['BIOMASS_BS_10']
RuntimeError [] no objective reaction detected; this model cannot report growth
ValueError [] no objective reaction detected; this model cannot report growth
AttributeError [] no objective reaction detected; this model cannot report growth
```

- Observed vs expected: observed an introspection failure becomes a false zero count. Expected an actionable `ModelImportError` and no scientific summary.
- Minimal patch:

```diff
--- a/cmig/io/model_import.py
+++ b/cmig/io/model_import.py
@@
 def _biomass_reactions(model: Any) -> list[str]:
     from cobra.util.solver import linear_reaction_coefficients
-    try:
-        coeffs = linear_reaction_coefficients(model)
-        return sorted(str(r.id) for r in coeffs)
-    except Exception:
-        return []
+    coeffs = linear_reaction_coefficients(model)
+    return sorted(str(r.id) for r in coeffs)
```

Wrap the call at the import/review boundary with a message such as `objective inspection failed for <model>`.

### F4 [P0] Any reaction lookup error silently removes a required nutrient from minimal medium

- file:line: `cmig/core/medium.py:67-72,86-105`
- What is wrong: `_is_blocked()` treats every lookup exception as “blocked/missing.” A transient backend error, I/O error, or programming/API error therefore silently excludes the exchange. On real `iYO844`, the healthy path adds `EX_h2o_e: 999999.0`; injecting any of three unrelated errors caused `_apply_min_medium_invariants()` to omit water and return only proton and phosphate exchanges.
- Repro:

```python
from cobra.io import read_sbml_model
from cmig.core.medium import _apply_min_medium_invariants, DEFAULT_U_BASE
m=read_sbml_model("models/iYO844.xml"); ok=_apply_min_medium_invariants(m,{},oxygen_mode="aerobic",u_base=DEFAULT_U_BASE,exclude_blocked=True)
# Wrap m.reactions.get_by_id to raise RuntimeError/OSError/TypeError only for EX_h2o_e.
print(ok["EX_h2o_e"])  # 999999.0; each injected-error result omitted EX_h2o_e
```

Observed for all three injections:

```text
RuntimeError normal_h2o 999999.0 fault_h2o None keys ['EX_h_e', 'EX_pi_e']
OSError     normal_h2o 999999.0 fault_h2o None keys ['EX_h_e', 'EX_pi_e']
TypeError   normal_h2o 999999.0 fault_h2o None keys ['EX_h_e', 'EX_pi_e']
```

- Observed vs expected: observed unrelated failures become a scientifically different medium. Expected only a genuine absent reaction (`KeyError`) to be treated as unavailable; all other errors must abort.
- Minimal patch:

```diff
--- a/cmig/core/medium.py
+++ b/cmig/core/medium.py
@@
-    except Exception:
+    except KeyError:
         return True
```

### F5 [P0] A failed gene-KO evaluation is published as a complete knockout effect, ranked first, and exits 0

- file:line: `cmig/cli/main.py:1782-1860,2054-2144,2523-2632`
- What is wrong: `_evaluate_ko_target()` catches every exception and substitutes `score=0`, `target_flux=0`, and `community_growth=0`, then computes deltas as the negatives of the baseline. Failed rows are still sent to the ranking CSV, summary, and plots. If the requested screen has one target, the CLI prints it as “rank 1 (largest effect),” `gene_ko_summary.json` says `"status": "ok"`, and the command returns 0. The row has a failed-status column, but the headline, numeric values, plot, top-level summary, and process exit all present the failed computation as a real maximal suppression.
- Repro:

```python
# One-member iYO844 taxonomy; patch search_model_pool so baseline is
# score=2.5/target_flux=3.5/growth=4.5, then raise RuntimeError for the KO.
rc=main(["gene-ko-search","--taxonomy",tax,"--members","a","--member","a",
         "--genes","BSU00090","--target","ac","--out",out])
print(rc, Path(out,"gene_ko_rankings.csv").read_text(), json.load(open(Path(out,"gene_ko_summary.json")))["status"])
```

Observed:

```text
rank 1 (largest effect): a:BSU00090 delta=-2.5 remaining=0
RC 0
CSV: score=0, score_delta=-2.5, target_flux=0, target_flux_delta=-3.5,
     community_growth=0, community_growth_delta=-4.5, status=failed
gene_ko_summary.json status: ok
manifest status: degraded
gene_ko_plot.svg and gene_ko_plot.tiff: both written
```

- Observed vs expected: observed an exception is indistinguishable numerically from total biological suppression and is announced as rank 1/success. Expected null numerics, exclusion from ranking/plots, failed summary, and non-zero exit unless `--allow-failed-run`.
- Minimal patch:

```diff
--- a/cmig/cli/main.py
+++ b/cmig/cli/main.py
@@
     except Exception as e:
         return {
@@
-            "score": 0.0,
-            "score_delta": -baseline.score,
-            "target_flux": 0.0,
-            "target_flux_delta": -baseline.target_flux,
-            "community_growth": 0.0,
-            "community_growth_delta": -baseline.community_growth,
+            "score": float("nan"),
+            "score_delta": float("nan"),
+            "target_flux": float("nan"),
+            "target_flux_delta": float("nan"),
+            "community_growth": float("nan"),
+            "community_growth_delta": float("nan"),
```

Partition failed rows into `gene_ko_unevaluated.csv`, derive the JSON status from the worst row, and return `_exit_code_for_status(...)`.

### F6 [P0] Failed abundance-sweep points become zero-valued dose-response points, figures, manifests, and exit 0

- file:line: `cmig/cli/main.py:2358-2520,2462-2479,2773-2911,4941-4994`
- What is wrong: the per-fraction handler substitutes zero for growth, target exchange, both share metrics, and contribution. The figure function filters only on presence of `target_abundance`, not `status`, and uses `... or 0.0`, so it connects successful points to fabricated zero points. Even when every sweep point fails, the command writes CSV/JSON/SVG/TIFF plus a workflow manifest and returns 0; the parser’s `--allow-failed-run` flag is ignored.
- Repro:

```python
from unittest.mock import patch
with patch("cmig.core.engine.MicomEngine.build_community",return_value=object()), \
     patch("cmig.core.engine.MicomEngine.cooperative_tradeoff",side_effect=RuntimeError("injected solver fault")):
    rc=main(["abundance-impact","--taxonomy",tax,"--member","a","--fractions","0.25,0.5","--out",out])
print(rc, Path(out,"abundance_impact.csv").read_text())
```

Observed:

```text
RC 0
both rows: status=failed but community_growth=0, target_member_exchange=0,
community_target_exchange=0, target_influence_share=0, target_secretion_share=0
summary status=failed; manifest written; SVG and TIFF written
```

A capture of the actual matplotlib line data for one optimal then one failed row was:

```text
growth lines [[2.0, 0.0], [1.0, 0.0]]
flux lines   [[0.8, 0.0], [1.2, 0.0]]
share line   [[0.5, 0.0]]
```

- Observed vs expected: observed failures are drawn as real zero responses and a failed analysis exits successfully. Expected `None`/blank numeric fields, failed rows excluded from curves, a visible failure annotation if a figure is retained, and exit 3 by default.
- Minimal patch:

```diff
--- a/cmig/cli/main.py
+++ b/cmig/cli/main.py
@@
-                    "community_growth": 0.0,
+                    "community_growth": None,
@@
-                    "target_member_exchange": 0.0,
-                    "community_target_exchange": 0.0,
-                    "target_influence_share": 0.0,
-                    "target_secretion_share": 0.0,
-                    "target_member_contribution": 0.0,
+                    "target_member_exchange": None,
+                    "community_target_exchange": None,
+                    "target_influence_share": None,
+                    "target_secretion_share": None,
+                    "target_member_contribution": None,
@@
-        (row for row in rows if _optional_float(row.get("target_abundance")) is not None),
+        (row for row in rows if row.get("status") == "optimal"),
@@
-    return 0
+    return _exit_code_for_status(summary_status, args)
```

### F7 [P1] `write_solve_output()` destroys the previous committed run if publication fails between replacements

- file:line: `cmig/io/solve_output.py:132-248`
- What is wrong: artifacts are staged, but publication first unlinks the old commit marker and then replaces files one by one. There is no rollback. An exception or process failure leaves a mixed old/new directory, possibly a partially written destination, with the valid old manifest deleted. This is not transactionally atomic.
- Repro:

```python
old={p.name:p.read_bytes() for p in out.iterdir()}
def fail(src,dst):
    if next(counter)==2: Path(dst).write_bytes(b"PARTIAL"); raise OSError("injected")
    return real_replace(src,dst)
with patch("cmig.io.solve_output.os.replace",fail): write_solve_output(new_bundle,c,out)
```

Observed for failures at replacement 1, 2, and 4:

```text
fail 1: nodes changed; profile/edges old; manifest missing
fail 2: nodes changed; edges changed/partial; profile old; manifest missing
fail 4: artifacts published; manifest changed/partial
```

- Observed vs expected: observed the previous run does not survive. Expected either the complete old generation or the complete new generation, never a mixture.
- Minimal patch: publish a complete sibling generation and atomically switch a single pointer/directory name. If retaining the current layout, at least back up every destination and roll all replacements back on exception:

```diff
--- a/cmig/io/solve_output.py
+++ b/cmig/io/solve_output.py
@@
-        if manifest_path.exists():
-            manifest_path.unlink()
-        for artifact in artifacts:
-            os.replace(tmp / artifact, out / artifact)
-        os.replace(tmp / "manifest.json", manifest_path)
+        publish_generation_atomically(
+            tmp, out, artifacts + ["manifest.json"]
+        )  # directory generation swap; restore old generation on any exception
```

### F8 [P1] Most other user-visible artifacts overwrite in place and truncate the previous file on failure

- file:line:
  - `cmig/core/tidy.py:172-181`; `cmig/core/workflow_manifest.py:277-301`
  - `cmig/core/dfba.py:446`; `cmig/core/sweep.py:192-217`; `cmig/core/matrix.py:41`; `cmig/core/interaction_figures.py:193,250,325,366-377`
  - `cmig/io/dfba_output.py:28-74`; `cmig/io/quality_output.py:47-65`
  - `cmig/render/client.py:99-171`; `cmig/render/composer.py:102-141`; `cmig/render/provenance.py:49-112`
  - `cmig/service/publication_benchmark.py:90-100,178-412`
  - `cmig/cli/main.py:710-718,998-1072,1653-1738,2523-2632,2651-2769,2773-2911,2914-3030,3032-3192,3954-4072,4485-4645,4751-5512,6313-6355`
- What is wrong: these writers call `Path.write_text`, `open(..., "w")`, `DataFrame.to_csv`, `pq.write_table`, `savefig`, or the R device directly on the final destination. Re-running into an existing output directory can destroy a good JSON/CSV/parquet/figure/sidecar and leave inconsistent artifact families. `publication_benchmark` is especially risky: it mutates subdirectories before writing its final manifest, so a failed rerun can leave the previous success manifest beside changed artifacts.
- Repro:

```python
p.write_text("ORIGINAL")
def partial(self,data,*a,**k):
    self.open("w").write("PARTIAL"); raise OSError("injected write failure")
with patch.object(Path,"write_text",partial):
    write_workflow_manifest(out,"dfba",valid_components)
print(p.read_text())
```

Observed failure-injection results:

```text
workflow manifest: ORIGINAL -> PARTIAL
generic CLI JSON:  ORIGINAL -> PARTIAL
Tidy nodes parquet: valid previous file -> bytes "PARTIAL"
dFBA CSV: previous complete table -> header only
model-quality CSV: previous complete table -> header only
RenderClient: old figure -> PARTIAL_FIG; old figure_spec also overwritten
FigureComposer: old panel -> PARTIAL_PANEL; old figure_spec also overwritten
render provenance: OLD_PROV -> PARTIAL
```

- Observed vs expected: observed every injected writer destroyed its previous destination. Expected write/fsync to a same-directory temporary file followed by `os.replace`, and directory-level staging where artifacts must agree.
- Minimal patch:

```diff
+def atomic_write_text(path: Path, text: str) -> None:
+    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as f:
+        f.write(text); f.flush(); os.fsync(f.fileno()); tmp = Path(f.name)
+    os.replace(tmp, path)
```

Use analogous temp-path helpers for CSV/parquet/figures, and make each multi-file workflow publish from one staged generation.

### F9 [P1] An expired Gurobi licence crashes both CLI and service; the capability probe only checks importability

- file:line: `cmig/core/solver.py:57-66`; `cmig/service/engine_service.py:90-144`; `cmig/cli/main.py:605-680`
- What is wrong: `GurobiBackend.capability()` reports availability solely from `find_spec("gurobipy")`, so an expired/unavailable licence is reported as available. `EngineService.solve_community()` does not normalize errors from community construction. The CLI has a generic `ImportError` branch for a missing package, but it does not name Gurobi or tell the user which solver package/licence to install; a `GurobiError` is uncaught and produces a full traceback.
- Repro:

```python
from unittest.mock import patch
import gurobipy
with patch("cmig.service.engine_service.EngineService.solve_community",
           side_effect=gurobipy.GurobiError(10009,"License expired")):
    main(["solve","--taxonomy",tax,"--assume-bigg-namespace","--out",out])
```

Observed:

```text
missing gurobipy: rc=2, "solve 는 엔진 stack 필요: uv sync --extra engine"
expired licence: rc=1, raw traceback ending "gurobipy._exception.GurobiError: License expired"
service layer: propagated ImportError and GurobiError unchanged
capability with importable=True: gurobi available=True (licence was never probed)
```

CPLEX is not a supported execution path: CLI validation returned rc 2 with `invalid choice: 'cplex'`, and service/backend validation raised a clear `ValueError` listing supported solvers. Therefore no CPLEX import/licence probe is reachable.

- Observed vs expected: observed a crash and non-actionable missing-package message. Expected `solver 'gurobi' unavailable: install gurobipy and configure a valid Gurobi licence`, no traceback by default, and a structured service failure.
- Minimal patch:

```diff
--- a/cmig/service/engine_service.py
+++ b/cmig/service/engine_service.py
@@
-            community = self._engine.build_community(effective_taxonomy, cmig_solver=solver)
+            try:
+                community = self._engine.build_community(effective_taxonomy, cmig_solver=solver)
+            except ImportError as e:
+                raise EngineUnavailableError(
+                    f"solver {solver!r} is not installed; install its Python package"
+                ) from e
+            except gurobipy.GurobiError as e:
+                raise EngineUnavailableError(
+                    f"solver 'gurobi' licence unavailable: {e}"
+                ) from e
```

Catch `EngineUnavailableError` at the CLI boundary. Make `capability()` perform a lazy licence/environment probe and retain the diagnostic.

### F10 [P2] Empty/truncated CSV and malformed parquet inputs dump raw tracebacks

- file:line: `cmig/cli/main.py:605-628`; `cmig/cli/main.py:1099-1107`; `cmig/core/tidy.py:184-194`
- What is wrong: `solve` executes `pd.read_csv()` outside its protected block. `render-figure` catches only `OSError`, while corrupt parquet raises `pyarrow.ArrowInvalid` and a wrong schema raises `TidyContractError`. These are default user-facing paths, not verbose/debug mode.
- Repro:

```bash
: > empty.csv
$CMIG_PY -m cmig.cli.main solve --taxonomy empty.csv --assume-bigg-namespace --out out
# Also put empty bytes in nodes/edges/profile.parquet and run:
$CMIG_PY -m cmig.cli.main render-figure --run-dir bad --renderer matplotlib --out x.svg
```

Observed:

```text
empty taxonomy CSV: rc=1, pandas EmptyDataError traceback
truncated quoted CSV: rc=1, pandas ParserError traceback
empty parquet: rc=1, pyarrow parquet traceback
wrong parquet schema: rc=1, TidyContractError traceback
```

- Observed vs expected: observed raw implementation tracebacks. Expected one actionable line and rc 2.
- Minimal patch:

```diff
--- a/cmig/cli/main.py
+++ b/cmig/cli/main.py
@@
-    taxonomy = pd.read_csv(tax_path)
+    try:
+        taxonomy = pd.read_csv(tax_path)
+    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as e:
+        print(f"invalid taxonomy CSV {tax_path}: {e}", file=sys.stderr)
+        return 2
@@
-    except OSError as e:
+    except (OSError, pyarrow.ArrowException, TidyContractError) as e:
```

### F11 [P2] `inspect-run` silently accepts empty, truncated, and wrong-type manifests with exit 0

- file:line: `cmig/cli/main.py:401-468,517-524`
- What is wrong: `_load_json_object()` returns `None` for a missing file, read error, JSON syntax error, and a valid JSON value of the wrong type. `inspect-run` cannot distinguish those states and reports an existing corrupt manifest as an unknown run with successful exit status.
- Repro:

```bash
mkdir bad
printf '[]' > bad/manifest.json   # also tested "{" and empty bytes
$CMIG_PY -m cmig.cli.main inspect-run --run-dir bad --format json
```

Observed for all three inputs:

```text
rc=0
"kind": "unknown", "status": "unknown", "manifest": {}, "artifacts": ["manifest.json"]
stderr empty
```

- Observed vs expected: observed a silent “unknown” result and success. Expected `invalid manifest.json: expected JSON object` or JSON parse detail and rc 2.
- Minimal patch:

```diff
--- a/cmig/cli/main.py
+++ b/cmig/cli/main.py
@@
 def _load_json_object(path: Path) -> dict[str, Any] | None:
@@
-    except (OSError, json.JSONDecodeError):
-        return None
-    return loaded if isinstance(loaded, dict) else None
+    except (OSError, json.JSONDecodeError) as e:
+        raise ValueError(f"invalid JSON object {path}: {e}") from e
+    if not isinstance(loaded, dict):
+        raise ValueError(f"invalid JSON object {path}: got {type(loaded).__name__}")
+    return loaded
```

Catch that `ValueError` in `_cmd_inspect_run()` and return 2.

### F12 [P2] There is no durable application log, and manifests omit timestamp and process exit status

- file:line: `cmig/cli/main.py:7185-7191`; `cmig/core/workflow_manifest.py:219-243`; `cmig/io/solve_output.py:190-233`
- What is wrong: exhaustive search found no logging configuration, file handler, logger call, traceback logger, or log-path option under `cmig/`. A successful `version` command created no files. The workflow manifest has model checksum, solver settings, dependency/CMIG versions, parameters, and status, but no timestamp or process exit code. The solve manifest likewise lacks timestamp/exit code. Failures that occur before manifest publication leave no durable record at all.
- Repro:

```python
with tempfile.TemporaryDirectory(dir=Path.cwd()) as d:
    p=subprocess.run([PY,"-m","cmig.cli.main","version"],cwd=d)
    print(p.returncode,list(Path(d).rglob("*")))
print(sorted(build_workflow_manifest("dfba",components).to_payload()))
```

Observed:

```text
VERSION_RC 0 FILES_CREATED []
manifest has model hash=True, solver=True, CMIG version=True
manifest has timestamp=False, exit status=False
```

- Observed vs expected: observed no log location and incomplete run chronology. Expected a documented per-user log with timestamp, model filename/hash, solver/version, all determining parameters, CMIG version, and exit status; or an explicit statement that manifests replace logs plus equivalent fields.
- Minimal patch: wrap `main()` with a JSON-lines audit logger (platform user-state directory, restrictive permissions), record start/end/exit, and add `created_at_utc` plus `exit_status` to both manifest schemas. Never put credentials/licence contents in the log.

### F13 [P2] `FileSystemStore.record_run()` accepts path-traversing and absolute `run_hash` values

- file:line: `cmig/service/store.py:56-83`
- What is wrong: `run_dir = self.root / run_hash` trusts the caller even though the contract says a run hash is canonical SHA-256. `../escaped` creates a directory outside the store root and records that path in SQLite. The current internal caller supplies computed hashes, limiting exposure, but the service API itself does not enforce the invariant.
- Repro:

```python
s=FileSystemStore(root)
s.record_run("../escaped", SolveResult(1.0,{}, {}, {}, {}, "optimal","full","gurobi","gurobi"))
print((root.parent/"escaped").exists())
print(s.cache_lookup_by_run_hash("../escaped")["run_dir"])
```

Observed:

```text
TRAVERSAL_CREATED True
ROOT_CONTAINS False
DB_RUN_DIR .../store/../escaped
ABSOLUTE_CREATED True; OUTSIDE_ROOT True
```

- Observed vs expected: observed directory creation outside `root`. Expected rejection unless the value is exactly a 64-character lowercase hexadecimal SHA-256.
- Minimal patch:

```diff
--- a/cmig/service/store.py
+++ b/cmig/service/store.py
@@
 import sqlite3
+import re
@@
     def record_run(...):
+        if re.fullmatch(r"[0-9a-f]{64}", run_hash) is None:
+            raise ValueError("run_hash must be a 64-character lowercase SHA-256")
         run_dir = self.root / run_hash
```

### Exhaustive `except Exception` census (33 sites)

| site | classification | reason |
|---|---|---|
| `cmig/cli/main.py:1301` `_cmd_host_search_bigg` | justified (and why) | Per-candidate isolation; row is explicitly failed and partitioned into `unevaluated`, never ranking. |
| `cmig/cli/main.py:1537` `_cmd_host_ko_impact` | justified (and why) | Per-arm isolation; numerics are NaN, arm/run status is failed, and deltas require valid arms. |
| `cmig/cli/main.py:1847` `_evaluate_ko_target` | swallows a real error | F5: fabricates zeros/deltas, ranks and plots them, summary says ok, exit 0. |
| `cmig/cli/main.py:2259` `_cmd_strain_growth` | justified (and why) | Per-member failure uses `single_growth=None`, explicit failed status, and degrades the comparison/control claim. |
| `cmig/cli/main.py:2429` `_cmd_abundance_impact` FVA add-on | justified (and why) | Optional FVA failure is explicitly labeled in `fva_status`; no interval is fabricated. |
| `cmig/cli/main.py:2462` `_cmd_abundance_impact` solve | swallows a real error | F6: fabricates zero scientific points, plots them, and exits 0. |
| `cmig/cli/main.py:3280` `_cmd_dfba` | justified (and why) | Top-level CLI boundary; prints diagnosis and returns non-zero, no default result. |
| `cmig/cli/main.py:3776` `_resolve_target_carbon_numbers` | should narrow the exception | Only parser/model-read errors should skip a model; programming/runtime errors are hidden while later models may supply a formula. |
| `cmig/cli/main.py:4355` `_emit_workflow_manifest` | justified (and why) | Provenance must not destroy completed analysis; failure is loudly warned and no hash is fabricated. |
| `cmig/cli/main.py:5643` `_cmd_namespace_suggest` | justified (and why) | User-command boundary; returns rc 2 with the original message and no default result. |
| `cmig/cli/main.py:5675` `_cmd_model_review` | justified (and why) | User-command boundary; returns rc 2 with the original message and no default result. |
| `cmig/cli/main.py:6237` `_cmd_sweep` | justified (and why) | Per-condition batch isolation; value is `None`, status failed, diagnostic structured. |
| `cmig/cli/main.py:6374` `_cmd_sandbox_fixture` | justified (and why) | User-command boundary; returns rc 2 and does not commit a default result. |
| `cmig/core/engine.py:183` `_delegate_cooperative_tradeoff` | justified (and why) | Solver backends expose open exception sets; records typed diagnostic and explicitly retries without pFBA. |
| `cmig/core/engine.py:190` `_delegate_cooperative_tradeoff` | justified (and why) | Retry failure returns structured `solver_failed`, not a scientific optimum. |
| `cmig/core/engine.py:224` `cooperative_tradeoff` | justified (and why) | Solution-readout boundary; returns structured `solver_failed` with cause. |
| `cmig/core/fva.py:85` `flux_variability` | should narrow the exception | Converts programming/runtime errors into the false diagnosis “FVA infeasible.” |
| `cmig/core/fva.py:144` `community_fva` | should narrow the exception | Same misclassification at community boundary. |
| `cmig/core/host_map.py:50` `_iter_exchanges` | should narrow the exception | Compatibility fallback should catch the absent-accessor error, not every model/runtime error. |
| `cmig/core/medium.py:71` `_is_blocked` | swallows a real error | F4: any failure becomes a blocked nutrient and changes the medium. |
| `cmig/core/model_pool.py:180` `diagnose_model_pool` | justified (and why) | Per-file audit boundary; records `readable=False`, warning, and original error. |
| `cmig/core/sandbox.py:151` `apply_bounds` | justified (and why) | Cleanup guard restores already changed bounds and re-raises the original exception. |
| `cmig/core/search_product.py:243` `_evaluate_members` | justified (and why) | Per-consortium isolation; explicit failed status and downstream partition exclude it from ranking. |
| `cmig/core/search_product.py:592` `_evaluate_members_multi` | justified (and why) | Same status-closed per-combination isolation. |
| `cmig/core/search_product.py:659` `_evaluate_members_multi_joint` | justified (and why) | Same status-closed per-combination isolation. |
| `cmig/core/search_product.py:705` `_pareto_points_for_members` | justified (and why) | Same status-closed per-combination isolation. |
| `cmig/core/sweep.py:158` `run_sweep` | justified (and why) | Batch isolation; caches `None` with failed status and structured diagnostic. |
| `cmig/gui/app.py:486` `_run_sandbox` | justified (and why) | GUI boundary; displays failure and does not show a result. |
| `cmig/gui/app.py:512` `import_model_file` | justified (and why) | GUI boundary; displays import failure and returns `False`. |
| `cmig/gui/app.py:548` `load_run_dir` | justified (and why) | GUI boundary; displays run-read failure and stops. |
| `cmig/gui/app.py:1321` `run_scenario_compare` | justified (and why) | GUI boundary; displays comparison failure and does not publish a delta. |
| `cmig/io/model_import.py:86` `load_cobra_model` | justified (and why) | External COBRA parsers expose varied exception types; all are wrapped in actionable `ModelImportError`. |
| `cmig/io/model_import.py:101` `_biomass_reactions` | swallows a real error | F3: any inspection failure becomes the false scientific value zero objective terms. |
| `cmig/service/jobrunner.py:134` `_run` | justified (and why) | Asynchronous task boundary; records failed status and structured diagnostic. |

## 3. Reverse-validation results

The mandatory reverse validation was run against four high-impact functions (three inputs each):

1. `cmig.core.manifest.compute_run_hash`

   - bounds `1e-7` vs `4e-7`: different Gurobi objectives, same hash.
   - abundance `1e-7` vs `4e-7`: both canonicalized to `0.0`, same hash.
   - tradeoff `0.5000001` vs `0.5000004`: both canonicalized to `0.5`, same hash.

   All reproduced F1.

2. `cmig.io.solve_output.write_solve_output`

   - injected failure on replacement 1: changed nodes, missing manifest.
   - injected failure on replacement 2: changed nodes, partial edges, missing manifest.
   - injected failure on replacement 4: new artifacts with partial/changed manifest.

   All reproduced F7.

3. `cmig.io.model_import._biomass_reactions`

   - injected `RuntimeError`, `ValueError`, and `AttributeError`.
   - real iYO844 has objective `BIOMASS_BS_10`; all three returned `[]` and the misleading no-objective warning.

   All reproduced F3.

4. `cmig.render.client._csv_cell` / `cmig.render.composer._csv_cell`

   - `1.2345678901234567` became `1.234568`.
   - `4.9e-7` became `0.000000`.
   - `-4.9e-7` became `-0.000000`.

   Profile, network, chord, and heatmap paths all reproduced F2.

Malformed-reader reverse matrix:

| input | command/path | observed |
|---|---|---|
| empty SBML | `model-review` | rc 2, actionable SBML parse error, no traceback |
| truncated SBML | `model-review` | rc 2, actionable SBML parse error |
| valid XML, not SBML | `model-review` | rc 2, actionable SBML parse error |
| JSON wrong type (`[]`) | `model-review` | rc 2, `Object has no .reactions attribute` |
| Korean model filename | `model-review` on symlink `한국어 모델.xml` | rc 0; 1250 reactions, 990 metabolites, 844 genes |
| taxonomy missing `file` column | `solve` | rc 2, explicit missing-column error |
| empty/truncated taxonomy | `solve` | rc 1 plus raw traceback (F10) |
| bounds JSON wrong type/truncated | `solve` | rc 2 and actionable message |
| empty/wrong-schema parquet | `render-figure` | rc 1 plus raw traceback (F10) |
| empty/truncated/wrong-type manifest | `inspect-run` | rc 0, silent unknown run (F11) |

## 4. Checked and found CORRECT

### SBML round-trip

`models/iYO844.xml` was loaded, written to `roundtrip_한국어.xml`, and reloaded through COBRApy, which is the same writer used by the two CMIG KO-temporary-model paths (`cmig/cli/main.py:1523` and `:1809`). No user-facing model-export command exists in `model_import.py`; sandbox export writes result metadata, not SBML.

Observed:

```text
reactions 1250 -> 1250
metabolites 990 -> 990
genes 844 -> 844
bounds changed: 0
reaction annotations changed: 0
metabolite annotations changed: 0
gene annotations changed: 0
model annotation: equal
objective coefficients: equal
compartments: equal
groups: 0 -> 0
```

Two literal GPR strings changed only by removal of redundant same-operator parentheses:

```text
ACCOAC: "(A and B) and C and D and E" -> "A and B and C and D and E"
PDH:    "(A and B) and C and D"       -> "A and B and C and D"
```

Gene sets were identical. Wild type and knockout semantic probes were exact:

```text
wildtype: 0.11796638932239958 == 0.11796638932239958; bound diff 0
BSU29200 KO: 0.0 == 0.0; bound diff 0
BSU14580 KO: 0.11380639028893193 == 0.11380639028893193; bound diff 0
```

Thus no SBML scientific field was lost in the offered path.

### CSV precision and alignment outside the renderer adapters

- `write_dfba_sensitivity`: all seven tested scalar float fields round-tripped bit-identically.
- `write_model_quality_reports`: objective, timing, coverage, and balance floats round-tripped bit-identically.
- Commas, embedded newlines, missing optional fields, and CJK strings remained in the correct columns.
- The defect is limited to the renderer adapters in F2.

### Performance

Largest bundled file: `models/iML1515.xml`, 11,412,293 bytes.

```text
load: 3.046580 s
counts: 2712 reactions, 1877 metabolites, 1516 genes
maximum resident set size: 521,240,576 bytes (497.09 MiB)
```

A synthetic solve-output bundle with 5,000 nodes, 20,000 edges, and 10,000 profile rows:

```text
35,000 rows
write_solve_output: 0.033776 s
artifact bytes: 770,707
maximum resident set size: 123,125,760 bytes (117.42 MiB)
```

No O(n²) string construction or repeated full-model deepcopy was observed in these scoped load/write paths. KO workflows do intentionally copy one model per perturbation; their model-write paths are unique temporary files, so they cannot destroy a previous user artifact.

### Security

Exhaustive scans confirmed:

- no first-party `eval`, Python `exec`/`compile` on user input, `shell=True`, `pickle`, `marshal`, `read_pickle`, `to_pickle`, `yaml.load`, or unsafe YAML loader;
- `exec()` matches are Qt event-loop methods, and `compile()` matches are static regular expressions;
- the vendored `cytoscape.min.js` contains internal `Function("return this")()` from its library bundle, but first-party `graph.html` contains no dynamic evaluator and user model labels enter Cytoscape data, not the constant legend’s `innerHTML`;
- no archive extraction exists. A crafted wheel member `../escape` was rejected with `unsafe archive path`;
- both R invocations use an argument list with `shell=False` (default), and R scripts only read CSV/arguments. A title and metabolite containing `x'); system('touch <marker>'); #` rendered successfully while the marker remained absent:

```text
RENDER_OK True 4457
MARKER_EXISTS False
```

The R input CSV correctly quoted comma/newline/CJK/code-like text. No R code injection reproduced.

SQLite queries in `FileSystemStore` are parameterized; only the filesystem path construction has F13.

### Solver handling that was correct

- CPLEX is rejected by argparse/service validation as unsupported, with no traceback.
- Gurobi pFBA/retry/readout exceptions inside `MicomEngine.cooperative_tradeoff()` are converted into structured `solver_failed` results; F9 is specifically the earlier community-construction/licence boundary.

## 5. Could not verify / out of scope, and why

- Excel export: no Excel reader/writer or CLI export path exists in the scoped code, so only CSV was testable.
- SBML groups preservation on a non-empty real group set: iYO844 has zero groups. The round-trip compared the group collection and found `0 -> 0`; no bundled requested fixture with non-empty groups was specified. This does not affect the confirmed fields above.
- GUI dialog traceback exposure was inspected and its four broad boundaries display concise messages, but full interactive desktop UX was not manually exercised; Qt’s automated suite did run under the full test gate.
- R project library isolation: `_RLIB` resolves to `/Users/jaeyongryu/orca/CMIG-wt-io/.Rlib`, which does not exist, causing the one test failure. Actual R rendering succeeded from system libraries and the provenance recorded R 4.3.2 plus `ggplot2 3.5.2`, `ragg 1.2.7`, `svglite 2.2.1`, and `systemfonts 1.2.3`, exactly matching the lock entries. Therefore I did not claim a wrong figure, but the gate is not green in the mandated worktree configuration.
- I did not test process-kill/power-loss durability beyond injected exceptions. F7/F8 already fail the weaker exception-atomicity requirement.
- No files under `cmig/` or `tests/` were modified, and no main-repository path was written.
