# Archive Index — 2026-05

Completed PDCA features archived in May 2026.

| Feature | Status | Match Rate | SC | Tests | Archived | Documents |
|---------|--------|-----------:|----|------:|----------|-----------|
| **cmig-community-core** | Baseline Complete (MVP-0~2) | 98.25% | 9/9 Met | 95 pass | 2026-05-31 | [plan](cmig-community-core/cmig-community-core.plan.md) · [design](cmig-community-core/cmig-community-core.design.md) · [analysis](cmig-community-core/cmig-community-core.analysis.md) · [report](cmig-community-core/cmig-community-core.report.md) |

## cmig-community-core — Summary

- **Scope**: PART I Implementation Baseline (MVP-0~2) — community metabolic interaction GUI delegating community FBA to MICOM 0.39.0 (exact-pinned, public API only); CMIG owns namespace gate / sign normalization / tidy data contract / cross-feeding+delta / sandbox / sweep / statistics / R publication figures / cardinality MILP.
- **Architecture**: Option C (Pragmatic) — headless `core/` + EngineService facade + 4 SC-driven seams (SolverBackend, MICOM EngineWrapper, Store, RenderClient).
- **Result**: 9/9 Success Criteria Met, Match Rate 98.25%, 95 tests pass, ruff/mypy-strict clean, Critical·Important 0. Adversarial multi-dimension review (24-agent) raised 21 / confirmed 15 (3C·6I·6M); Act #2 resolved all Critical+Important with 7 regression tests.
- **Verified for real**: MICOM community solve (gurobi 12.0.3 / osqp / hybrid), ggplot2 SVG/TIFF render (svglite/ragg, X11-free), cobra cardinality MILP.
- **Carried-over (non-blocking)**: Minor 6 (deferred), G-7 (Qt GUI render needs display env), G-3 (AN-SINGLE FVA = MVP-0 detail).
