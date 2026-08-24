# Release checklist

Follow the same dependency order as `.github/workflows/ci.yml`: quality first, package inspection
second, then licensed solver/publication checks.

1. Finalize the release section in `CHANGELOG.md`; align `pyproject.toml`,
   `cmig/__init__.py`, `CITATION.cff`, `.zenodo.json`, and
   `.claude-plugin/marketplace.json`. Regenerate `uv.lock` after the project-version change.
2. Run `uv lock --check`, then `uv sync --all-extras --group dev` from the release checkout.
3. Run the license-free quality gates:

   ```bash
   uv run ruff check .
   uv run mypy cmig
   uv run cmig golden verify-envelope
   uv run pytest -q \
     tests/test_sign.py \
     tests/test_namespace_gate.py \
     tests/test_run_hash.py \
     tests/test_stats.py \
     tests/test_model_quality.py \
     tests/test_workflow_manifest.py \
     tests/test_workflow_envelope_golden.py
   ```

4. Build and inspect the distributions, matching the CI package job:

   ```bash
   uv build
   uv run python scripts/audit_distribution.py dist/*
   ```

5. In the licensed Gurobi environment, run the solver gates in CI order:

   ```bash
   uv run cmig golden verify
   QT_QPA_PLATFORM=offscreen uv run pytest -q
   uv run pytest -q tests/test_publication_benchmark.py
   ```

6. Execute every release rerun in `docs/PUBLICATION_VALIDATION.md`. Archive the command log,
   exit codes, reviewed interface map, benchmark directory, separate closed-uptake dFBA audit,
   manifests, `run_hash` values, and `result_digest` values.
7. Install the wheel in a clean environment and repeat the CLI smoke tests. Confirm no external
   GEM, `.run`, credentials, local R library, review notes, or private metadata appears in either
   distribution.
8. Create an annotated signed tag `vX.Y.Z`; publish GitHub release notes from the finalized
   changelog.
9. Upload the wheel and sdist, then archive the release through Zenodo. Add the minted DOI to
   `CITATION.cff` only after Zenodo assigns it.
