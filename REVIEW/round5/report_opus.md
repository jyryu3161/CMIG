# Track P3 — I/O, exception handling & logging, security — Independent Reviewer (Claude Opus 5)

Worktree `/Users/jaeyongryu/orca/CMIG-wt-io` @ `review/p3-io-exc`.
`git status --porcelain` is empty — **no file under `cmig/` or `tests/` was modified.**
All evidence below was produced by running code in that worktree with
`PYTHONPATH=/Users/jaeyongryu/orca/CMIG-wt-io` and
`/Users/jaeyongryu/orca/CMIG/.venv/bin/python`; `import cmig` resolved to
`/Users/jaeyongryu/orca/CMIG-wt-io/cmig/__init__.py` (verified).

Scratch scripts used are under `.../scratchpad/round5/p3/work/`
(`roundtrip.py`, `gpr.py`, `atomic.py`, `prec.py`, `licence.py`, `stale.py`,
`midwrite.py`, `rv.py`, `rvc.py`, `f2.py`, `f3.py`).

---

## 1. Summary

| Category | Verdict |
|---|---|
| 3.1 SBML round-trip | **PASS** — no scientific loss on `iYO844` (1250 rxn / 990 met / 844 gene). Only redundant pure-AND parentheses are normalised; KO semantics identical. |
| 3.2 Atomic writes | **FAIL** — `write_solve_output` is properly atomic; **every other** artifact write (57 sites) is a direct truncating write. Confirmed data loss by injection. |
| 3.3 Large models | Measured; nothing pathological found (see §6). |
| 3.4 CSV/Excel precision | **PASS with caveat** — `.12g` costs <=2.8e-12 relative, ~6 orders below solver tolerance. Not scientifically material. |
| 3.5 Malformed input | **PASS** — all 7 malformed inputs give a clean message + exit 2, no traceback. CJK filenames work. |
| 4.1 Exception census | 34/34 enumerated. 27 justified / 5 should-narrow / **2 fabricate a scientific value**. |
| 4.2 Solver missing/unlicensed | **PARTIAL** — structured, no traceback, solver named; but capability probe cannot see an invalid licence and the message never says what to install. |
| 4.3 Traceback exposure | **PASS** — no user-facing path dumps a traceback. |
| 4.4 Log file | **FAIL** — there is **no logging subsystem at all** (0 `logging` imports), no `--verbose`/`--debug`, no timestamp in any manifest. |
| 6 Security | **PASS** — no `eval`/`exec`/`compile` on user input, no `pickle`/`marshal`/`yaml.load`, no `shell=True`, no archive extraction, no reachable injection into the R subprocess or the Qt webview. |

**Counts: P0 = 3 / P1 = 1 / P2 = 8.**

Most dangerous: **F1**, `cmig/cli/main.py:2462` + `cmig/cli/main.py:4954` — a failed
solve is plotted in the published abundance-impact figure as a genuine
`community_growth = 0.0` data point.

Baseline test suite: `tests/test_render.py::test_render_client_passes_project_rlib`
fails **before any change of mine** (cause identified, see F12); everything up to it passes.

---

## 2. Findings

### F1 [P0] `abundance-impact` plots a failed solve as a real zero-growth measurement

- `cmig/cli/main.py:2462-2479` (the `except Exception` that fabricates the row)
- `cmig/cli/main.py:4949-4968` (the figure writer that consumes it)

**What is wrong.** When one abundance fraction fails to solve, the handler appends a row
with `community_growth: 0.0`, `target_member_exchange: 0.0`,
`community_target_exchange: 0.0`, `target_influence_share: 0.0` and `status: "failed"`.
`_write_abundance_impact_figures` then builds its series with

```python
valid_rows = sorted((row for row in rows
                     if _optional_float(row.get("target_abundance")) is not None), ...)
community_growth = [_optional_float(row.get("community_growth")) or 0.0 for row in valid_rows]
```

The filter is on `target_abundance`, **never on `status`**. So the fabricated `0.0` is
plotted as an ordinary point on the growth-vs-abundance curve, with the same marker and
colour as measured points. The `or 0.0` idiom additionally collapses legitimate `None`
and non-finite values to `0.0`. The CSV does carry a `status` column and is honest; the
**figure**, which is the publication artifact, is not.

**Repro** (`work/f3.py`) — four fractions, the one at 0.5 failed:

```
x (abundance)     : [0.1, 0.3, 0.5, 0.7]
community_growth  : [0.3, 0.28, 0.0, 0.26]
status            : ['optimal', 'optimal', 'failed', 'optimal']
n rows plotted: 4 | n actually solved: 3
figures written: ['abundance_impact_plot.svg', 'abundance_impact_plot.tiff']
```

**Observed vs expected.** Observed: a curve that dips to zero growth at abundance 0.5,
indistinguishable from a real collapse — a reader concludes the community cannot grow at
that abundance. Expected: the point is omitted (gap in the line) or drawn as an explicit
"not evaluated" marker, exactly as `_ko_effect_category` already does for the KO figure.

**Minimal patch**

```diff
--- a/cmig/cli/main.py
+++ b/cmig/cli/main.py
@@
-    valid_rows = sorted(
-        (row for row in rows if _optional_float(row.get("target_abundance")) is not None),
+    # A failed solve contributes no measurement; plotting its placeholder 0.0 draws a
+    # zero-growth point that was never computed.
+    valid_rows = sorted(
+        (row for row in rows
+         if _optional_float(row.get("target_abundance")) is not None
+         and str(row.get("status")) == "optimal"),
         key=lambda row: float(row["target_abundance"]),
     )
+    n_dropped = len(rows) - len(valid_rows)
```

and render `n_dropped` in the axis title (e.g. `f"{n_dropped} of {len(rows)} points not
evaluable"`) so the omission is visible rather than silent.

---

### F2 [P0] Gene-KO failure branch fabricates a finite effect size and gives it a rank

- `cmig/cli/main.py:1847-1860`

**What is wrong.** `_evaluate_ko_target` has **two** failure paths for the same semantic
event ("this knockout could not be evaluated"), and they disagree:

- `main.py:1815-1832` — knockout left no evaluable consortium -> `score_delta = float("nan")`
  (added by a previous round as fix *P0-B*).
- `main.py:1847-1860` — any exception -> `score_delta = -baseline.score`,
  `target_flux_delta = -baseline.target_flux`,
  `community_growth_delta = -baseline.community_growth`.

The second path writes a **finite, large-magnitude, plausible** effect size that was never
measured. `_write_gene_ko_search_outputs` (`main.py:2560`) then numbers every row it is
given — `for rank, row in enumerate(rows, start=1)` — so a failed knockout receives a rank
and a `score_delta` cell in `gene_ko_rankings.csv`.

**Repro** (`work/f2.py`), baseline score 12.148:

```
row returned by the except-branch:
  evaluation_status          'failed'
  score_delta                -12.148
  target_flux_delta          -12.148
  community_growth_delta     -0.1122
  diagnostic                 'MICOM community build failed: solver out of memory'
score_delta is finite?           True
score_delta == -baseline.score?  True
=> written to gene_ko_rankings.csv as: -12.148
Sort tier for this row: (1, 0, -12.148, 'iHN637:b0008')
```

**Observed vs expected.** Observed: `gene_ko_rankings.csv` contains a ranked row whose
`score_delta = -12.148` — numerically the single largest suppression in the screen — for a
gene that was never knocked out. Expected: `NaN`, matching the sibling branch 25 lines
above, so it is excluded from the finite-delta consumers.

**Mitigations that limit but do not remove the harm** (verified by reading and running):
`_ko_sort_key` (`main.py:1904`) puts `evaluation_status != "ok"` in a later tier, so it
cannot outrank a real result; `_ranking_degeneracy_warnings` (`search_product.py:124`)
filters on `status == "optimal"`; `_ko_effect_category` (`main.py:5186`) colours it
"failed". The fabricated number therefore reaches the **CSV and the JSON summary only** —
but that is the table a reader plots.

**Minimal patch**

```diff
--- a/cmig/cli/main.py
+++ b/cmig/cli/main.py
@@
     except Exception as e:
         return {
             "gene": ko_id,
             "member": member_id,
             "evaluation_status": "failed",
-            "score": 0.0,
-            "score_delta": -baseline.score,
-            "target_flux": 0.0,
-            "target_flux_delta": -baseline.target_flux,
-            "community_growth": 0.0,
-            "community_growth_delta": -baseline.community_growth,
+            # Same contract as the "no evaluable consortium" branch above: a knockout that
+            # was never evaluated has no effect size. A finite delta here is indistinguishable
+            # from a measured one in gene_ko_rankings.csv.
+            "score": float("nan"),
+            "score_delta": float("nan"),
+            "target_flux": float("nan"),
+            "target_flux_delta": float("nan"),
+            "community_growth": float("nan"),
+            "community_growth_delta": float("nan"),
             "status": "failed",
             "diagnostic": str(e),
         }
```

`_finite_csv` already renders `NaN` as an empty cell, so the CSV degrades correctly.

---

### F3 [P0] A stale artifact from a previous run survives and contradicts the current run

- `cmig/cli/main.py:4002-4006` (`search_unevaluated.csv`), `4530-4534` (multi-target),
  `2966-2970` (`host_search_unevaluated.csv`), `3969-3970` (`pool_diagnostics.csv`)

**What is wrong.** These artifacts are written **conditionally** (`if result.unevaluated:`).
Nothing ever deletes them when the condition is false on a later run into the same `--out`
directory. `cmig/io/solve_output.py:241-244` performs exactly this cleanup for the solve
path (`for stale in KNOWN_SOLVE_ARTIFACTS - set(artifacts): stale_path.unlink()`), so the
hazard is already recognised in-repo — the workflow path simply lacks the guard.

**Repro** (`work/stale.py`), same `--out` directory twice:

```
run1 target=succ  -> ... 'search_unevaluated.csv'   run_hash c31c0a670487f114
run2 target=ac    -> ... 'search_unevaluated.csv'   run_hash 9a8fc8048e414922

>>> STALE search_unevaluated.csv from run1 still present after run2? True
    its content (belongs to target=succ, but manifest says target=ac):
      members,status,diagnostic
      iHN637,missing,"{""code"": ""capability_missing"" ...
    manifest.json target: {'direction': 'max_secretion', 'mode': 'single_target',
                           'target': 'ac', 'target_exchange': 'EX_ac_m'}
    summary.json artifacts: [... no search_unevaluated.csv ...]
```

In run 2 `iHN637` is **rank 1, the best acetate producer** (`best: iHN637 flux=12.15`).
The surviving file states it could not be evaluated.

`inspect-run` does not flag the contradiction — it lists the stale file under the on-disk
`artifacts` key while `manifest.artifacts` omits it, and reports no warning:

```
"artifacts": [ ..., "search_unevaluated.csv" ]     <- on disk, includes the stale file
"manifest": { "artifacts": ["pool_taxonomy.csv","search_rankings.csv","search_summary.json"] }
```

The same class affects the solve path for **non-**`KNOWN_SOLVE_ARTIFACTS` files
(`work/rvc.py`, case C3): a `figure.svg` from a previous `cmig render-figure` survives into
the next `write_solve_output` run untouched, while `target_summary.json` and
`matrix.parquet` (both in the KNOWN set) are correctly removed.

**Observed vs expected.** Observed: a run directory that asserts the current run's best
performer was unevaluable. Expected: the artifact is removed, or the run refuses to write
into a non-empty directory without `--force`.

**Minimal patch** — mirror the solve path. Declare the full optional set once and sweep it:

```diff
--- a/cmig/cli/main.py
+++ b/cmig/cli/main.py
@@
+# Artifacts a workflow emits only under some conditions. A re-run into the same --out must
+# not leave the previous run's copy behind (cf. io/solve_output.KNOWN_SOLVE_ARTIFACTS).
+OPTIONAL_WORKFLOW_ARTIFACTS = frozenset({
+    "search_unevaluated.csv", "host_search_unevaluated.csv", "pool_diagnostics.csv",
+})
+
+
+def _clear_stale_optional_artifacts(out: Path, written: set[str]) -> None:
+    for name in OPTIONAL_WORKFLOW_ARTIFACTS - written:
+        stale = out / name
+        if stale.exists():
+            stale.unlink()
```

and call `_clear_stale_optional_artifacts(out, set(summary["artifacts"]))` immediately
before `_emit_workflow_manifest` in each `_write_*_outputs`.

---

### F4 [P1] Every artifact write outside `write_solve_output` is non-atomic; a mid-write failure destroys the previous file

- `cmig/core/workflow_manifest.py:296-301` (confirmed by injection)
- same pattern at 57 further sites, e.g. `cmig/cli/main.py:3996`, `4072`, `2540`, `2620`,
  `3026`, `cmig/render/client.py:109`, `cmig/render/provenance.py`

**What is wrong.** `write_workflow_manifest` does
`(out / "manifest.json").write_text(...)` straight onto the destination.
`write_text` truncates first, so any failure during the write leaves a truncated file and
the previous manifest is gone. `cmig/io/solve_output.py:158-247` shows the correct pattern
already exists in this codebase (`tempfile.TemporaryDirectory` + `os.replace`, with
`manifest.json` as the commit marker).

**Repro** (`work/atomic.py`) — write a good manifest, then fail one third of the way
through the next write:

```
PASS 1 wrote manifest.json bytes = 1306 run_hash = c7c3e557b440ab0c
PASS 2 raised: [Errno 28] No space left on device
after failed write, manifest.json bytes = 435
previous manifest SURVIVED? False
still valid JSON? False -> JSONDecodeError Expecting value: line 33 column 33 (char 434)
```

**Observed vs expected.** Observed: the run's only reproducibility record is destroyed and
replaced by unparseable JSON; `inspect-run` on that directory can no longer recover the
`run_hash`. Expected: the failed write leaves the previous manifest intact.

By contrast `write_solve_output` behaves correctly under the same class of failure
(`work/rvc.py`, case C2): it leaves the directory **without** `manifest.json`, which is the
documented "incomplete run" signal.

**Minimal patch**

```diff
--- a/cmig/core/workflow_manifest.py
+++ b/cmig/core/workflow_manifest.py
@@
+import os
+import tempfile
@@
     out = Path(out_dir)
     out.mkdir(parents=True, exist_ok=True)
-    (out / "manifest.json").write_text(
-        json.dumps(
-            manifest.to_payload(), indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False
-        )
-        + "\n"
-    )
+    payload = json.dumps(
+        manifest.to_payload(), indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False
+    ) + "\n"
+    # A failed write must not destroy the previous run's manifest (cf. io.solve_output).
+    fd, tmp = tempfile.mkstemp(dir=out, prefix=".manifest.", suffix=".tmp")
+    try:
+        with os.fdopen(fd, "w") as handle:
+            handle.write(payload)
+            handle.flush()
+            os.fsync(handle.fileno())
+        os.replace(tmp, out / "manifest.json")
+    except BaseException:
+        Path(tmp).unlink(missing_ok=True)
+        raise
     return manifest.run_hash
```

The same `write_text -> tmp+os.replace` substitution applies to the other 57 sites; a shared
`cmig/io/atomic.py::atomic_write_text(path, data)` helper would cover them uniformly.

---

### F5 [P2] `manifest.artifacts` is a hardcoded, unverified list that under-declares the run

- `cmig/core/workflow_manifest.py:236` (`"artifacts": sorted(self.artifacts)`), callers e.g.
  `cmig/cli/main.py:3732`

**What is wrong.** The artifact list is a literal passed by each command and is never
checked against the filesystem. Two consequences, both observed:

*Under-declaration, in a normal successful run* (`work/searchout`, real `cmig search`):

```
manifest.artifacts : ['pool_taxonomy.csv', 'search_rankings.csv', 'search_summary.json']
actually on disk   : 10 files
on-disk-but-undeclared: ['pool_diagnostics.csv', 'search_member_matrix.csv',
                         'search_plot.svg', 'search_plot.tiff', 'search_scatter.svg',
                         'search_scatter.tiff', 'search_unevaluated.csv']
```

`search_summary.json` carries the accurate 10-entry list, so the two disagree. This is
precisely why the F3 contamination goes unnoticed — the manifest never claimed to
enumerate the directory.

*Over-declaration* (`work/rv.py`, RV-A): a manifest can declare artifacts that were never
written while still recording `status: "ok"`:

```
declared artifacts : ['NEVER_WRITTEN.csv', 'figure.svg', 'sweep.parquet']
actually on disk   : ['manifest.json']
status recorded    : ok
```

**Minimal patch** — verify at write time and record only what exists:

```diff
--- a/cmig/core/workflow_manifest.py
+++ b/cmig/core/workflow_manifest.py
@@ def write_workflow_manifest(
+    declared = set(artifacts or [])
+    missing = sorted(name for name in declared if not (Path(out_dir) / name).exists())
+    if missing:
+        raise WorkflowManifestError(
+            f"manifest for {kind!r} declares artifacts that were not written: {missing}"
+        )
```

and have each command pass the same list it puts in its `summary["artifacts"]`.

---

### F6 [P2] There is no logging subsystem, no debug flag, and no timestamp in any manifest

- whole package

**What is wrong.** `grep -rn "import logging\|getLogger" cmig/ --include='*.py'` returns
**0 matches**. There is no log file, no log directory, and no `--verbose`/`--debug`/`--log`
option (`grep -n '"--verbose"\|"--debug"\|"--log"' cmig/cli/main.py` -> 0 matches). All
diagnostics go to stdout/stderr via `print` and are lost when the terminal closes.

Against the brief's reproducibility checklist, the workflow `manifest.json` is the de-facto
record. Measured on a real `cmig search` run, its top-level keys are:

```
['artifacts', 'components', 'diagnostic', 'env_lock', 'float_decimals', 'hash_components',
 'manifest_schema_version', 'manifest_scope', 'platform', 'run_hash', 'status', 'summary',
 'warnings', 'workflow_kind']
```

| Required | Present? |
|---|---|
| model filename + hash | **Yes** — `components.model_checksum` (bytes + taxonomy metadata) |
| solver + version | **Yes** — `components.solver_setting`, `dependency_versions.gurobipy` |
| answer-determining parameters | **Yes** — enforced by `WORKFLOW_HASH_COMPONENTS` arity assertions |
| CMIG version | **Yes** — `components.cmig_core_version` |
| exit status | **Yes** — `status` (ok/degraded/failed) |
| **timestamp** | **No** — `manifest has timestamp? False` |

So the single genuine gap in the manifest is the timestamp: two runs of the same directory
cannot be ordered, and a stale directory cannot be dated.

**Minimal patch** — add it outside the hash, exactly as `env_lock` is handled
(`workflow_manifest.py`, `to_payload`):

```diff
     def to_payload(self) -> dict[str, Any]:
         return {
             "manifest_schema_version": WORKFLOW_MANIFEST_SCHEMA_VERSION,
+            # Outside the hash, like env_lock: identical inputs must still hash identically.
+            "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
```

---

### F7 [P2] The solver capability probe cannot see an invalid or size-limited licence

- `cmig/core/solver.py:53-55` (`_importable`) and `:58-67` (`GurobiBackend.capability`)

**What is wrong.** `_importable` is `importlib.util.find_spec(module) is not None`. It
answers "is the package installed", not "can it solve". The pip-installed Gurobi ships a
size-limited licence (2000 variables) that cannot solve any genome-scale model, and an
expired academic licence also imports cleanly. `cmig solvers` therefore prints
`available True` for a Gurobi that will fail on the first real solve:

```
Solver capability matrix (§5.1):
  solver    LP  QP  MILP  available
  gurobi   True True  True       True
```

**Repro.** Reading is definitive for the mechanism. Empirically, forcing
`optlang.available_solvers["GUROBI"] = False` does **not** change the matrix
(`work/nosolver.py`), confirming the probe consults only `find_spec` and never optlang or
the licence:

```
=== capability_matrix() with GUROBI=False ===
  gurobi SolverCapability(name='gurobi', lp=True, qp=True, milp=True, available=True, ...)
```

**Observed vs expected.** Observed: a pre-flight capability check that a researcher would
reasonably trust reports a solver as usable when it is not. Expected: `available` reflects
whether a trivial model can actually be optimised.

**Minimal patch**

```diff
 class GurobiBackend:
     def capability(self) -> SolverCapability:
+        # find_spec only proves the package is installed. A size-limited or expired licence
+        # imports cleanly and then fails on the first genome-scale solve.
+        available = _importable("gurobipy")
+        if available:
+            try:
+                import gurobipy
+                env = gurobipy.Env(params={"OutputFlag": 0})
+                env.dispose()
+            except Exception:
+                available = False
         return SolverCapability(
-            name="gurobi", lp=True, qp=True, milp=True, available=_importable("gurobipy")
+            name="gurobi", lp=True, qp=True, milp=True, available=available
         )
```

---

### F8 [P2] Solver-failure diagnostic never says what to install or how to fix the licence

- `cmig/core/engine.py:183-197`

**What is wrong.** The failure is structured and traceback-free (good), but it only
forwards the backend's exception text. **Repro** (`work/licence.py`), injecting a realistic
Gurobi licence error:

```
status          : solver_failed
growth_solver   : gurobi
diagnostic      : {"code": "solver_error", "detail": {"causes": [
                   {"code": "solver_error", "message": "pFBA flux stage failed: ...
                    Model too large for size-limited license; ..."}, ...]}}
  contains 'gurobi': True     (only because the exception text happens to say so)
  contains 'licen' : True     (ditto)
  contains 'install': False
  contains 'uv sync': False
```

The configured solver *is* recorded independently in `SolveResult.growth_solver`, so the
solver is always identifiable. What is missing is the remedial instruction the brief asks
for. Compare `cmig/io/model_import.py:79`, which does this correctly:
`"cobra 미설치 (`uv sync --extra engine`)."`

**Minimal patch**

```diff
         except Exception as retry_error:  # noqa: BLE001
             causes.append((
                 DiagnosticCode.SOLVER_ERROR,
                 f"non-parsimonious retry failed: {type(retry_error).__name__}: {retry_error}",
             ))
+            causes.append((
+                DiagnosticCode.SOLVER_ERROR,
+                f"solver {cmig_solver!r} could not solve this model. Check the solver is "
+                f"installed and licensed: `cmig solvers`. For gurobi, a size-limited or "
+                f"expired licence imports cleanly but cannot solve genome-scale models "
+                f"(https://www.gurobi.com/academia/). Reinstall with "
+                f"`uv sync --extra engine`.",
+            ))
             return None, "none", [], causes
```

(`_flux_solution` needs `cmig_solver` threaded in; it is already available at the call site
`engine.py:206`.)

---

### F9 [P2] CSV export is not bit-exact — but the loss is not scientifically material

- `cmig/cli/main.py:4445-4446` — `return "" if not math.isfinite(value) else f"{value:.12g}"`

**What is wrong.** `.12g` keeps 12 significant digits; float64 needs 17 for exact
round-trip. **Measured** (`work/prec.py`):

```
value                      _finite_csv (.12g)   reparsed             bit-equal  rel_err
0.12345678901234568        0.123456789012       0.123456789012       False      2.800e-12
12.345678901234567         12.3456789012        12.3456789012        False      2.800e-12
1234.5678901234567         1234.56789012        1234.56789012        False      2.800e-12
0.3333333333333333         0.333333333333       0.333333333333       False      9.999e-13
1e-07 / 3.7e-07 / 6.022e23                                           True       0.000e+00
WORST relative error from _finite_csv: 2.800e-12
```

**Observed vs expected.** Observed: not bit-identical. Expected (by the brief): bit-identical.
**I am deliberately not tagging this P0.** The worst relative error is 2.8e-12, roughly six
orders of magnitude below any LP solver's feasibility/optimality tolerance (1e-6...1e-9), and
`run_hash` canonicalisation already rounds to 6 decimals
(`manifest.DEFAULT_FLOAT_DECIMALS = 6`, `golden.DEFAULT_DECIMALS = 6`), so the CSV is
strictly more precise than the reproducibility contract. No published number changes.

**Minimal patch** (only if exact round-trip is a stated requirement):

```diff
-    return "" if not math.isfinite(value) else f"{value:.12g}"
+    return "" if not math.isfinite(value) else repr(value)   # shortest exact round-trip
```

Column alignment was checked separately and is correct: all writers are `csv.DictWriter`
with an explicit `fieldnames`, so a missing key becomes an empty cell and commas/newlines/CJK
in a value are quoted by the `csv` module rather than shifting columns.

---

### F10 [P2] Figure-data CSV uses absolute-decimal rounding, zeroing sub-micromolar fluxes

- `cmig/render/client.py:194-209` (`_CSV_DECIMALS = 6`, `f"{v:.{_CSV_DECIMALS}f}"`)
- `cmig/render/composer.py:75-81` (same `f"{v:.6f}"`)

**What is wrong.** `.6f` is six *decimal places*, not six significant figures, so every
`|flux| < 5e-7` becomes exactly `0.000000` in the CSV handed to R. **Measured**
(`work/prec.py`):

```
render/client _csv_cell (.6f):
  3.7e-07    -> '0.000000'
  1e-08      -> '0.000000'
  5e-07      -> '0.000000'
  1.4999e-06 -> '0.000001'
  123.456789012 -> '123.456789'
```

The colour is driven by the separately-written `label` column, so a metabolite still shows
as "secretion" while its bar is drawn with zero length. Values in that range are at or
below solver noise, so this is presentational rather than a wrong result.

**Minimal patch**

```diff
-_CSV_DECIMALS = 6
+_CSV_SIGFIGS = 9
@@
-    return f"{v:.{_CSV_DECIMALS}f}"
+    return f"{v:.{_CSV_SIGFIGS}g}"   # significant figures: preserves small fluxes
```

---

### F11 [P2] `taxonomy_model_checksum` folds unrelated taxonomy columns into the run hash

- `cmig/io/solve_output.py:42-73`

**What is wrong.** Every column except `file` is copied into `taxonomy_metadata` and hashed.
Adding a descriptive column that does not affect the science changes `model_checksum` and
therefore `run_hash`, so two identical analyses appear non-reproducible.
**Measured** (`work/rv.py`, RV-B):

```
base                              : sha256:fc9085e67ec40160e
B1 + unrelated 'note' column      : sha256:1df114024e924fdd3 | SAME as base? False
B2 columns reordered              : sha256:fc9085e67ec40160e | SAME as base? True
B3 relative path + base_dir       : sha256:fc9085e67ec40160e | SAME as base? True
B4 row order swapped              : sha256:fc9085e67ec40160e | SAME as base? True
B6 abundance .5/.5 vs .9/.1       : differ? True
```

B2/B3/B4 are all **correct** (order- and path-invariant), and B6 correctly separates
different abundances. Only B1 is questionable, and it errs on the conservative side
(over-sensitive, never colliding). Recorded as a documentation/UX item, not a defect:
the docstring says "solve-relevant taxonomy metadata" but the implementation hashes *all*
metadata. Fix by restricting to a declared allow-list, or by aligning the docstring.

---

### F12 [P2] Two artifact-honesty nits and one pre-existing test failure

**(a) `gene_ko_summary.json` always reports `"status": "ok"`** —
`cmig/cli/main.py:2574`. `payload = {"status": "ok", ...}` is a literal and is never
reassigned before `(out / "gene_ko_summary.json").write_text(...)` at `main.py:2620`, even
when every knockout failed. Harm is limited because `_resolve_run_status`
(`main.py:2468`-ff) gives the workflow manifest's derived tier precedence over the summary's
status, so `inspect-run` still reports `degraded`/`failed` correctly; a user opening the
JSON directly sees `ok`. Patch: `"status": _worst_status(*["ok" if r.get("evaluation_status")
== "ok" else "degraded" for r in rows] or ["failed"])`.

**(b) `graph.html` builds legend markup with `innerHTML`** —
`cmig/gui/assets/graph.html:55-56`:
``legend.innerHTML = (payload.legend || []).map(l => `<div><b>${l.symbol}</b> ${l.meaning}</div>`)``.
**This is currently NOT exploitable**: `graph_payload` (`cmig/gui/graph_data.py:131`) sets
`"legend": SIGN_LEGEND`, a module constant — no user or model-derived string reaches it.
The adjacent gate text correctly uses `textContent` (`graph.html:61`). Injection into
`runJavaScript(f"window.setGraph({json.dumps(payload)});")` (`graph_view.py:102`) is also
safe because `json.dumps` defaults to `ensure_ascii=True`, escaping U+2028/U+2029 and all
non-ASCII. Recorded only as a latent hardening item: switch to `textContent` so a future
change that puts a metabolite name in the legend does not become DOM XSS.

**(c) `tests/test_render.py::test_render_client_passes_project_rlib` fails on a clean tree.**
Not caused by this review (`git status --porcelain` empty). Cause identified: the test
monkeypatches `subprocess.run` globally, and `write_render_provenance`
(`cmig/render/provenance.py:66`) calls `platform.platform()`, which on macOS shells out to
`uname -p`; that call hits the fake and dies with
`ValueError: '--out' is not in list`. Test-only defect — the patch should be scoped to
`cmig.render.client.subprocess.run`. Everything before it in the suite passes.

---

## 3. Reverse-validation results

Three most important functions in scope, three adversarial input combinations each,
all actually executed.

### `write_solve_output` (`cmig/io/solve_output.py:132`) — `work/rvc.py`

| # | Adversarial input | Result |
|---|---|---|
| C1 | `bundle.write()` emits `matrix.parquet` but `bundle.matrix is None` | `matrix.parquet` **silently dropped** (artifact list is derived from `bundle.matrix`, not from disk). **Not reachable** with the real `TidyBundle` — `tidy.py:178-180` writes it under the identical condition. Latent coupling only. |
| C2 | `bundle.matrix` set but `write()` omits the file | `FileNotFoundError` at `os.replace`; directory left **without `manifest.json`** and with mixed parquets. **Correct by design** — the manifest is the documented commit marker, so the incomplete run is detectable. |
| C3 | Stale artifact not in `KNOWN_SOLVE_ARTIFACTS` (e.g. `figure.svg`) | **Survives** into the next run. `target_summary.json` and `matrix.parquet` (in the KNOWN set) are correctly removed. Feeds **F3**. |

**Verdict: robust.** This is the reference implementation the rest of the codebase should copy.

### `write_workflow_manifest` (`cmig/core/workflow_manifest.py:277`) — `work/rv.py`, `work/atomic.py`

| # | Adversarial input | Result |
|---|---|---|
| A1 | Declare 3 artifacts, write none | Manifest records all 3 with `status: "ok"`. **Reproduced -> F5.** |
| A2 | Fail one third of the way through a rewrite | Previous manifest destroyed, replaced by invalid JSON. **Reproduced -> F4.** |
| A3 | Omit a determining component / pass an out-of-contract extra | `WorkflowManifestError` with the exact missing/extra names. **Correct** — the arity assertions and vocabulary check hold. |

### `_evaluate_ko_target` / KO CSV export (`cmig/cli/main.py:1793`, `2560`) — `work/f2.py`

| # | Adversarial input | Result |
|---|---|---|
| K1 | Exception raised inside the evaluation | `score_delta = -baseline.score` (finite, fabricated). **Reproduced -> F2.** |
| K2 | Knockout leaves no evaluable consortium | `score_delta = NaN` — **correct**, and inconsistent with K1. |
| K3 | Failed row ranked against a real one | Sort key `(1, 0, -12.148, ...)` vs `(0, 0, -1.148, ...)` — failed row correctly demoted to the second tier, but still enumerated with a rank number in the CSV. |

Additional adversarial pass on `_write_abundance_impact_figures` (`work/f3.py`) produced
**F1**, the highest-severity finding in this track.

---

## 4. Checked and found CORRECT (do not re-review)

**SBML round-trip** (`work/roundtrip.py`, `models/iYO844.xml`, cobra 0.31.1) — write->reload
diff over the full model:

```
n_rxn 1250 | n_met 990 | n_gene 844 | n_groups 0 | n_comp 2   — all EQUAL
objective '1.0*BIOMASS_BS_10 - 1.0*BIOMASS_BS_10_reverse_8788b' — EQUAL, direction 'max' EQUAL
bound mismatches: 0
annotation mismatches: rxn=0 met=0 gene=0
metabolite formula mismatches=0  charge mismatches=0
subsystem mismatches: 0   gene name mismatches: 0
GPR rule mismatches: 2
   ('ACCOAC', '(BSU29200 and BSU29210) and BSU24350 ...', 'BSU29200 and BSU29210 and BSU24350 ...')
   ('PDH',    '(BSU14580 and BSU14590) and BSU14600 ...', 'BSU14580 and BSU14590 and BSU14600 ...')
```

The only difference is redundant parentheses around a pure-AND group — `and` is
associative, so this is a cosmetic normalisation, **not** data loss. Verified directly
(`work/gpr.py`): mixed AND/OR nesting is preserved exactly and knockout semantics are
identical across the round-trip.

```
R1 '(g1 or g2) and g3'          -> identical   True
R2 'g1 and (g2 or g3)'          -> identical   True
R3 '(g1 and g2) or (g3 and g4)' -> identical   True
R4 '((g1 or g2) and g3) or g4'  -> identical   True
R5 '(g1 and g2) and g3'         -> 'g1 and g2 and g3'   (semantically equal)
orig      after KO g1: R1 open, R2 (0,0), R3 open, R4 open, R5 (0,0)
roundtrip after KO g1: R1 open, R2 (0,0), R3 open, R4 open, R5 (0,0)   — IDENTICAL
```

This matters because `_evaluate_ko_target` writes each knocked-out model to SBML
(`main.py:1809`) and MICOM re-reads it; the KO is carried as reaction bounds, which survive
exactly.

**Malformed input** — 7 inputs through `model-review` and `namespace-suggest`. Every case
gave a single clear Korean+English sentence, **no traceback**, and **exit 2**:

```
model-review empty.xml         -> exit=2   "sbml 파싱 실패 (empty.xml): ..."
model-review truncated.xml     -> exit=2
model-review notsbml.xml       -> exit=2   (valid XML, not SBML)
model-review wrongtype.json    -> exit=2   "json 파싱 실패 (wrongtype.json): 'metabolites'"
model-review nocol.csv         -> exit=2   (unsupported extension)
model-review missing_file.xml  -> exit=2   "모델 파일 없음"
namespace-suggest {empty,truncated,notsbml}.xml -> exit=2 each
```

**CJK filenames** — `한글모델_테스트.xml` (a copy of `iHN637`) imports and reviews
successfully, `exit=0`, correct counts and 95 namespace decisions. No mojibake, no
encoding error. CJK **output** paths were exercised throughout without issue.

**Security — exhaustive, all negative:**
- `eval` / `exec` / `compile` / `__import__` / `literal_eval` on user input: **none**. The
  only `compile(` hits are `re.compile` (`cmig/core/targets.py:49`,
  `scripts/audit_distribution.py:48`) and the only `exec(` hit is Qt's
  `app.exec()` (`cmig/gui/__main__.py:45`).
- `pickle` / `marshal` / `yaml.load` / `read_pickle` / `to_pickle` / `joblib`: **none**.
  The four matches are comments reading "pickle 금지" (parquet is used instead).
- `subprocess`: two call sites, `cmig/render/client.py:124` and
  `cmig/render/composer.py:129`. Both use a **list argv**, `shell=False` (default),
  `check=False`, and captured output. No `os.system`, no `popen`, **no `shell=True` anywhere**.
- **R injection**: user data reaches R only as `--data <path>` pointing at a CSV written by
  `csv.DictWriter` in a `tempfile.TemporaryDirectory`. `--title` is the one user string
  passed as an argv element; because there is no shell it cannot break out, and `figure.R`
  consumes it as a value. The R scripts are repo-owned files addressed by absolute path
  (`R_SCRIPT = .../render_r/figure.R`). No user data becomes R code.
- **Archive extraction / path traversal**: `tarfile`/`zipfile` appear only in
  `scripts/audit_distribution.py`, which inspects (`namelist`/`getmembers`) a
  locally-built distribution and never extracts. No `extractall`, no `shutil.unpack_archive`
  anywhere in `cmig/`.
- **Qt webview**: covered in F12(b) — not exploitable.

**Exception-handling designs that are right and should not be "fixed":**
`cmig/io/solve_output.py:158-247` (atomic publish with commit marker);
`cmig/core/engine.py:183-197` (pFBA->FBA degradation recorded in
`flux_normalization_method`, so `run_hash` differs and the manifest cannot claim "pfba"
for a run that fell back); `cmig/core/sweep.py:158` and `cmig/cli/main.py:6237` (failed
conditions stored with `value=None`, not `0.0`); `cmig/core/model_pool.py:180`
(unreadable model -> all counts `None`, `readable=False`); `cmig/cli/main.py:4355`
(provenance failure never fabricates a hash and never discards a finished analysis);
`cmig/cli/main.py:1318` (`ranked_rows` filters on `evaluation_status == "ok"` before
ranking — the pattern F2 should adopt).

---

## 5. Full `except Exception` census — 34/34 sites

`grep -rn "except Exception" cmig/ | wc -l` -> **34**. No bare `except:` and no
`except BaseException` anywhere in `cmig/`. Every site below was read in context.

**Totals: 27 justified / 5 should narrow / 2 swallow or fabricate a scientific value.**

### A. Justified (27)

| # | Site | Why justified |
|---|---|---|
| 1 | `core/fva.py:85` | Translates to `FVAInfeasibleError`, re-raises. |
| 2 | `core/fva.py:144` | Same, community FVA. |
| 3 | `io/model_import.py:86` | Translates to `ModelImportError` with format + filename. |
| 4 | `core/sandbox.py:151` | Restores bounds, then **re-raises**. Cleanup only. |
| 5 | `core/engine.py:183` | Records `SOLVER_ERROR` cause, degrades pFBA->FBA; degradation is recorded in `flux_normalization_method` and enters `run_hash`. |
| 6 | `core/engine.py:190` | Records cause, returns `None` -> `solver_failed`. No value invented. |
| 7 | `core/engine.py:224` | Solution readout failure -> `solver_failed_result`. |
| 8 | `core/sweep.py:158` | Caches and records `value=None`, `status="failed"`. |
| 9 | `service/jobrunner.py:134` | `JobStatus.FAILED` + structured `Diagnostic`. |
| 10 | `cli/main.py:6237` | Per-condition failure -> `value=None`, `status="failed"`; `GateBlockedError`/`OSError` deliberately re-raised first. |
| 11 | `cli/main.py:4355` | Provenance failure warns and returns `None`; never fabricates a `run_hash`, never discards the result. |
| 12 | `cli/main.py:3280` | dFBA: message to stderr, exit 1 (input errors already split to exit 2). |
| 13 | `cli/main.py:5643` | `namespace-suggest`: message, exit 2. |
| 14 | `cli/main.py:5675` | `model-review`: message, exit 2. |
| 15 | `cli/main.py:6374` | `sandbox-fixture`: message, exit 2. |
| 16 | `core/model_pool.py:180` | Unreadable model -> counts `None`, `readable=False`, `error=str(e)`. |
| 17 | `gui/app.py:486` | Sandbox failure -> status bar text, return. GUI must not die. |
| 18 | `gui/app.py:512` | Import failure -> status bar, `return False`. |
| 19 | `gui/app.py:548` | Run load failure -> status bar, return. |
| 20 | `gui/app.py:1321` | Scenario compare failure -> status bar, return. |
| 21 | `core/search_product.py:243` | `PoolRank(score=-inf, status="failed")`; `-inf` sorts last and callers split on `status`. |
| 22 | `core/search_product.py:592` | `_ComboEval(status="failed")`; consumers filter on `status == "optimal"` (`search_product.py:124`, `:331`). |
| 23 | `core/search_product.py:659` | Same, joint-LP pass. |
| 24 | `core/search_product.py:705` | Same, Pareto pass. |
| 25 | `cli/main.py:2429` | FVA is an explicit diagnostic add-on; sets `fva_status="failed: <Type>"` and leaves `lo`/`hi` as `None`. |
| 26 | `cli/main.py:2259` | Sets `single_status="failed"`, `single_medium_applied=False`, `row_equal=False` — all conservative directions. |
| 27 | `cli/main.py:1301` | Fabricates `0.0`s **but** `main.py:1318` filters `evaluation_status == "ok"` before ranking, so no zero reaches the ranking. |

### B. Should narrow the exception (5) — behaviour acceptable, type too broad

| # | Site | Note |
|---|---|---|
| 28 | `core/medium.py:71` | `_is_blocked` returns `True` (exclude) on **any** exception from `get_by_id`. Excluding is the safe direction and the medium is checksummed, but a genuine cobra internal error is indistinguishable from "id absent". -> `except KeyError`. |
| 29 | `core/host_map.py:50` | Falls back to an `EX_`-prefix scan when `model.exchanges` is unavailable. -> `except AttributeError`. |
| 30 | `io/model_import.py:101` | Objective read failure -> `[]`, which makes `objective_structure_warning(0)` emit *"no objective reaction detected; this model cannot report growth"*. Honest and explicitly non-inferring, but the bare catch also hides real optlang errors. |
| 31 | `cli/main.py:3776` | Unreadable model -> `continue` to the next candidate during carbon-number resolution. Safe because `_resolve_target_carbon_numbers` raises `ValueError` if no source is found. -> `except (OSError, cobra.io.sbml.CobraSBMLError)`. |
| 32 | `cli/main.py:1537` | Host-KO arm failure -> `HostArm` with `host_objective=NaN`, `target_transfer=NaN` (**correct**, NaN not 0), but `community_growth=0.0` alongside `run_status="failed"`. Prefer NaN there too for consistency with the NaN fields in the same object. |

### C. Continues with a fabricated scientific value (2) — **P0**

| # | Site | Finding |
|---|---|---|
| 33 | `cli/main.py:1847` | `score_delta = -baseline.score`, `target_flux_delta = -baseline.target_flux`, `community_growth_delta = -baseline.community_growth` — finite fabricated effect sizes that receive a rank in `gene_ko_rankings.csv`. -> **F2** |
| 34 | `cli/main.py:2462` | `community_growth = 0.0` and four more zeroed fields; consumed unfiltered by `_write_abundance_impact_figures` and plotted as a measurement. -> **F1** |

---

## 6. Could not verify / out of scope

- **Large-model timing and peak memory (brief 3.3).** Load of `iYO844` (1250 rxn) plus a
  complete two-member `cmig search` — exhaustive over 3 combinations, 4 figures and 10
  artifacts — took **19.7 s wall / 19.17 s user** end to end. I did **not** isolate a
  peak-RSS number for `iML1515` (the largest bundled model, 2712 rxn), so I am not reporting
  a memory figure. I read every write path in scope for O(n^2) string building and repeated
  `deepcopy` and found none: parquet goes through `pq.write_table`, CSVs stream through
  `csv.DictWriter` row by row, and the only model copy is the deliberate per-knockout
  `base_models[member_id].copy()` at `main.py:1802`, which is required for isolation.
  **Missing evidence:** a `tracemalloc`/`resource.getrusage` measurement on `iML1515` and a
  solve-output write with >10^4 rows.
- **Excel export.** The brief names "CSV / Excel export"; there is no Excel writer in the
  codebase (`to_excel`/`openpyxl`/`xlsxwriter` -> 0 matches). CSV only, covered in F9.
- **Gurobi licence probe (F7) end-to-end.** I confirmed by reading and by the optlang
  experiment that `capability()` consults only `find_spec`, and I injected a realistic
  licence exception at the solve boundary to capture the user-facing message (F8). I did
  **not** install a genuinely size-limited licence. **Missing evidence:** a run under a real
  2000-variable licence confirming `cmig solvers` still prints `available True`.
- **CPLEX.** The brief asks about CPLEX; it is not a supported CMIG solver
  (`ALLOWED_CMIG_SOLVERS = {"gurobi", "osqp"}`, `engine.py:40`) and optlang reports
  `CPLEX: False` in this environment. Nothing to simulate.
- **GUI dialog surfaces (brief 4.3).** I verified the four `gui/app.py` handlers route to
  `statusBar()`/status labels rather than dumping tracebacks, but I did not drive the Qt
  event loop under `QT_QPA_PLATFORM=offscreen` to confirm no `QMessageBox` elsewhere shows
  raw text. **Missing evidence:** an offscreen GUI run triggering each error path.
- **`taxonomy_model_checksum` with a duplicate member id** silently produces a checksum
  (`work/rv.py`, B5) rather than rejecting. I did not trace whether taxonomy validation
  upstream rejects duplicate ids, so I am **not** reporting this as a defect —
  `확인 필요 (UNVERIFIED)`. **Missing evidence:** whether any caller can reach
  `taxonomy_model_checksum` with a duplicated `id`.
- **Scientific internals** of `search`, `engine`, `host_coupling` — explicitly another
  track's scope; I touched them only where an I/O or exception path crossed into them.
