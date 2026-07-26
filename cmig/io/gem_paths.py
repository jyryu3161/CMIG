"""Resolution order for the large external human GEMs (Recon3D / RECON1).

These SBML files are 15-29 MB and are distributed under a non-commercial licence, so they are
gitignored and fetched on demand by ``scripts/download_human_gems.py`` into ``data/gems/`` --
see ``data/gems/README.md``. Before round 6 the only places CMIG looked were
``$CMIG_RECON3D_PATH``, ``fixtures/Recon3D.xml`` and ``./Recon3D.xml``, so a model sitting in the
tracked download location was invisible and ``tests/test_recon3d_host.py`` skipped for the
project's entire life. ``data/gems/`` is now part of the order, and the search is one function so
the CLI defaults and the tests cannot disagree about where a model lives.

Nothing here copies or downloads: it returns the first existing path, or ``None``.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Repo root when running from a source checkout (``<root>/cmig/io/gem_paths.py``). In an
#: installed wheel this points into site-packages and simply yields no existing candidate.
REPO_ROOT = Path(__file__).resolve().parents[2]
#: Tracked download destination of ``scripts/download_human_gems.py``.
GEM_DATA_DIR = REPO_ROOT / "data" / "gems"
#: Overrides the directory searched at step 2, for a shared read-only GEM store.
GEM_DIR_ENV = "CMIG_GEM_DIR"
#: Per-model environment overrides, checked first.
GEM_PATH_ENV = {"Recon3D": "CMIG_RECON3D_PATH", "RECON1": "CMIG_RECON1_PATH"}


def human_gem_candidates(model_id: str) -> list[Path]:
    """Every path searched for ``model_id``, in the order they are consulted."""
    candidates: list[Path] = []
    env_var = GEM_PATH_ENV.get(model_id)
    explicit = os.environ.get(env_var) if env_var else None
    if explicit:
        candidates.append(Path(explicit).expanduser())
    shared_dir = os.environ.get(GEM_DIR_ENV)
    if shared_dir:
        candidates.append(Path(shared_dir).expanduser() / f"{model_id}.xml")
    candidates.extend([
        GEM_DATA_DIR / f"{model_id}.xml",
        REPO_ROOT / "fixtures" / f"{model_id}.xml",
        REPO_ROOT / f"{model_id}.xml",
    ])
    return candidates


def resolve_human_gem(model_id: str) -> Path | None:
    """First existing candidate for ``model_id``, or ``None`` if the model is not present."""
    for candidate in human_gem_candidates(model_id):
        if candidate.exists():
            return candidate
    return None


def default_human_gem_path(model_id: str) -> str:
    """A CLI ``--model`` default: the resolved path, else the tracked download location.

    Returning the tracked location rather than a bare filename makes the failure message name
    where the file is *supposed* to be, which is also what the download script writes.
    """
    resolved = resolve_human_gem(model_id)
    return str(resolved if resolved is not None else GEM_DATA_DIR / f"{model_id}.xml")
