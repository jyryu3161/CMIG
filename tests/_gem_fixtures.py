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

Round-6 integration: the search order itself is **not defined here.** The concurrent human-GEM track
put it in :mod:`cmig.io.gem_paths`, where the CLI ``--model`` defaults for ``host-generic`` and
``host-benchmark`` read it too, so the tests and the shipped commands cannot disagree about where a
model lives. Two independent orders would be the same divergence class this round spent its time
removing. This module is now a thin adapter: it keeps the ``<id>.xml`` key style these tests were
written against and *derives* :data:`HUMAN_GEM_SEARCH` from the production order, so the assertion
named above now protects the CLI default as well as the tests.
"""

from __future__ import annotations

from pathlib import Path

from cmig.io.gem_paths import (
    GEM_DIR_ENV,
    REPO_ROOT,
    human_gem_candidates,
    resolve_human_gem,
)

ROOT = Path(__file__).resolve().parents[1]

#: Re-exported from :mod:`cmig.io.gem_paths` so the tests name the same env var the CLI honours.
__all__ = [
    "BUNDLED_MICROBIAL_GEMS", "GEM_DIR_ENV", "GEM_PATH_ENV", "HUMAN_GEM_SEARCH", "ROOT",
    "bundled_model_path", "human_gem_path", "human_gem_skip_reason",
]

#: Per-model env vars (pre-existing; ``cmig host-benchmark`` also honours ``CMIG_RECON3D_PATH``).
GEM_PATH_ENV = {"Recon3D.xml": "CMIG_RECON3D_PATH", "RECON1.xml": "CMIG_RECON1_PATH"}


def _repo_relative_search() -> tuple[str, ...]:
    """The repo-relative part of :func:`cmig.io.gem_paths.human_gem_candidates`, as directories.

    Derived rather than restated: if the production order loses ``data/gems``, this tuple loses it
    too and the assertion fails. Env-var candidates point outside the repo and drop out here, which
    is why only the repo-relative entries are read.
    """
    order: list[str] = []
    for candidate in human_gem_candidates("Recon3D"):
        try:
            relative = candidate.parent.relative_to(REPO_ROOT)
        except ValueError:
            continue
        name = relative.as_posix()
        if name not in order:
            order.append(name)
    return tuple(order)


#: Repo-relative search order for a human GEM, applied after the env vars. ``data/gems`` is where
#: the download script puts them and is the entry whose removal silently re-skipped nine tests.
HUMAN_GEM_SEARCH: tuple[str, ...] = _repo_relative_search()

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
    """Resolve a human GEM, or ``None`` when it is genuinely not on this machine.

    Delegates to the production resolver so a test and a shipped ``--model`` default can never
    disagree about which file they mean.
    """
    return resolve_human_gem(name[: -len(".xml")] if name.endswith(".xml") else name)


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
