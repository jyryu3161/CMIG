# Release checklist

1. Update `CHANGELOG.md`, `CITATION.cff`, `.zenodo.json`, and the version in `pyproject.toml`.
2. Run `uv lock --check` and sync every supported extra.
3. Run `uv run ruff check .`, `uv run mypy cmig`, and `uv run pytest`.
4. Run `uv run cmig golden verify` with the licensed solver environment.
5. Re-run the command in `docs/PUBLICATION_VALIDATION.md` and archive its benchmark manifest.
6. Run `uv build`, then `uv run python scripts/audit_distribution.py dist/*`; install the wheel in
   a clean environment and repeat the CLI smoke tests.
7. Confirm no external GEM, `.run`, credentials, local R library, review notes, or private metadata
   appear in either distribution.
8. Create an annotated signed tag `vX.Y.Z`; publish GitHub release notes from the changelog.
9. Upload wheel and sdist, then archive the release through Zenodo. Add the minted DOI to
   `CITATION.cff` only after Zenodo has assigned it.
