# CMIG development rules

Follow explicit user instructions first. The root specification (`CMIG_명세서_v3.0.md`) and accepted decisions define intended scientific contracts; current docs, code, tests and CI describe implemented behavior. Historical PDCA plans and reviews are supporting evidence. Report disagreements with sources instead of silently changing scientific semantics.

## Architecture

`cmig/core` contains headless scientific algorithms **and** engine/solver adapters; `cmig/service` coordinates jobs and use cases; `cmig/io` handles input, provenance and atomic outputs; `cmig/cli` and `cmig/gui` present workflows; `cmig/render` and `cmig/render_r` make figures. Keep optional dependencies lazy and GUI work responsive. An architectural mismatch warrants review, not an unrequested relocation.

## Scientific and data invariants

- Delegate community construction and cooperative tradeoff to the supported MICOM integration. Keep `micom==0.39.0`; flag undocumented internal coupling for review. See `pyproject.toml`, `docs/USAGE.md`, and `tests/test_engine_golden.py`.
- Preserve namespace gates, exchange signs (`+` secretion, `−` uptake), member versus environment flux bases, explicit medium merge/replace choices and isolation at every uptake boundary. Reject unmatched inputs explicitly. See `docs/01-plan/schema.md`, `tests/test_namespace_gate.py`, `tests/test_sign.py`, and medium/isolation tests.
- Preserve requested and effective membership, finite positive abundances, growth floors, jointly feasible target vectors, required fixed normalization and recorded GA seed, budget and policy. Exact membership count alone does not prove participation or optimality. See `tests/test_search_policy_v2.py` and `tests/test_search_execution.py`.
- Keep failed, nonviable, unevaluable and cancelled outcomes distinct from valid zero and success. Never rank invalid outcomes as best; retain failure ledgers, warnings, exit semantics and the difference between scientific and artifact success. See `tests/test_search_ga.py` and `tests/test_search_service.py`.
- Retain run hashes, dependency/model/medium provenance, result digests, atomic publication and checkpoint compatibility. Do not use pickle. Preview data remains ephemeral until Apply/Save; do not edit source GEMs or publish scratch data. See `tests/test_workflow_manifest.py`, `tests/test_run_transaction.py` and `docs/PUBLICATION_VALIDATION.md`.
- Label Gurobi full flux and OSQP approximation accurately. Preserve host objective, biomass and isolation meaning, and dFBA and statistical independence caveats. Unit tests alone do not establish publication validity.

## Workflow

Use `uv run --no-sync` in an already synchronized environment. Run Ruff, `mypy cmig`, release/version and envelope gates, and meaningful behavior tests for changes. Licensed solver, GUI and publication checks have separate prerequisites described in `docs/HARNESS.md`. Do not relax golden tolerances or turn absent tests/skips into a pass.

For harness phases, `plan` and `review` use `gpt-6-astra`; `implement` uses `gpt-6-sol`. Steps declare exact read files, owned write paths, executable acceptance checks, deadlines and report ownership. Preserve pre-existing edits and scope. The runner remains on the current branch and does not commit or push unless explicitly configured. Existing task authorization covers routine implementation; ask only for genuinely unresolved choices.

The `.claude/skills/cmig-metabolic-analysis` skill supports metabolic-analysis users. It is not a second source of development rules.
