"""Shared resolution of the genome-scale models the round-6 tests run against.

Two classes of model, deliberately kept apart:

* **bundled microbial GEMs** live in ``models/`` and are tracked, so a test that needs one must
  never skip. They are the floor of coverage.
* **human GEMs** (``Recon3D.xml``, ``RECON1.xml``) are large binaries and are gitignored, so they
  are resolved through a search order and their tests skip when genuinely absent.

Round 6 (P2): reverting the ``data/gems`` entry from that search order turned a passing suite into
``9 passed, 9 skipped, exit 0`` — green. **A re-skip is loss of coverage, not detection.**
:data:`HUMAN_GEM_SEARCH` is therefore asserted directly by
``test_round6_boundary_regressions.test_human_gem_search_order_includes_data_gems``, so removing
the entry fails a test instead of quietly disabling nine of them.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Directory env var, checked first. Points at a directory holding the human GEMs; the review
#: worktrees share one read-only copy in the main repo rather than duplicating 41 MB per worktree.
GEM_DIR_ENV = "CMIG_GEM_DIR"

#: Per-model env vars (pre-existing; ``cmig host-benchmark`` also honours ``CMIG_RECON3D_PATH``).
GEM_PATH_ENV = {"Recon3D.xml": "CMIG_RECON3D_PATH", "RECON1.xml": "CMIG_RECON1_PATH"}

#: Repo-relative search order for a human GEM, applied after the env vars. ``data/gems`` is where
#: the download script puts them and is the entry whose removal silently re-skipped nine tests.
HUMAN_GEM_SEARCH: tuple[str, ...] = ("data/gems", "fixtures", ".")

#: Bundled microbial GEMs — tracked, so always present.
BUNDLED_MICROBIAL_GEMS: tuple[str, ...] = (
    "iAF987.xml", "iHN637.xml", "iML1515.xml", "iSFV_1184.xml", "iYO844.xml",
)


def bundled_model_path(name: str) -> Path:
    path = ROOT / "models" / name
    if not path.exists():
        raise FileNotFoundError(
            f"bundled microbial GEM missing from the repository: {path}. These are tracked; a "
            "test that needs one must fail rather than skip."
        )
    return path


def human_gem_path(name: str) -> Path | None:
    """Resolve a human GEM, or ``None`` when it is genuinely not on this machine."""
    env_var = GEM_PATH_ENV.get(name)
    if env_var:
        configured = os.environ.get(env_var)
        if configured:
            candidate = Path(configured).expanduser()
            return candidate if candidate.exists() else None
    gem_dir = os.environ.get(GEM_DIR_ENV)
    if gem_dir:
        candidate = Path(gem_dir).expanduser() / name
        if candidate.exists():
            return candidate
    for relative in HUMAN_GEM_SEARCH:
        candidate = ROOT / relative / name
        if candidate.exists():
            return candidate
    return None


def human_gem_skip_reason(name: str) -> str:
    """A skip reason that names every location searched, so the skip is diagnosable."""
    searched = [
        f"${GEM_PATH_ENV[name]}" if name in GEM_PATH_ENV else "",
        f"${GEM_DIR_ENV}/{name}",
        *[f"{relative}/{name}" for relative in HUMAN_GEM_SEARCH],
    ]
    return (
        f"{name} not found; searched " + ", ".join(item for item in searched if item)
        + f" (download from BiGG: http://bigg.ucsd.edu/static/models/{name}.gz)"
    )
