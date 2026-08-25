"""Staging and atomic publication helpers for rendered figure artifact sets."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from cmig.io.atomic import atomic_write_path


@dataclass(frozen=True)
class RenderArtifacts:
    """The figure and its two reproducibility sidecars."""

    figure: Path
    figure_spec: Path
    provenance: Path


def render_artifacts(figure: str | Path) -> RenderArtifacts:
    """Return the three artifact paths belonging to ``figure``."""
    path = Path(figure)
    return RenderArtifacts(
        figure=path,
        figure_spec=path.with_name(path.name + ".figure_spec.json"),
        provenance=path.with_name(path.name + ".render_provenance.json"),
    )


@contextmanager
def staged_render_path(destination: str | Path) -> Iterator[Path]:
    """Yield a same-name figure path in an isolated staging directory.

    Keeping the final file name (including its format suffix) makes R and matplotlib produce the
    same bytes they produced before staging was introduced. The directory is placed beside the
    destination so failures cannot leave temporary data on another filesystem or in the output
    directory after context cleanup.
    """
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=target.parent,
        prefix=f".{target.name}.render-stage-",
    ) as directory:
        yield Path(directory) / target.name


def publish_render_artifacts(staged_figure: str | Path, destination: str | Path) -> Path:
    """Atomically publish a completed staged figure and both sidecars, one file at a time.

    All three staged files are checked before the first replacement. Each copy is then flushed,
    synced, and replaced through :func:`cmig.io.atomic.atomic_write_path`; a writer, sync, or
    replacement failure therefore cannot expose a partial version of the artifact being written.
    """
    staged = render_artifacts(staged_figure)
    target = render_artifacts(destination)
    pairs = (
        (staged.figure, target.figure),
        (staged.figure_spec, target.figure_spec),
        (staged.provenance, target.provenance),
    )
    missing = [source for source, _ in pairs if not source.is_file()]
    if missing:
        raise FileNotFoundError(f"staged render artifact missing: {missing[0]}")

    for source, output in pairs:
        atomic_write_path(output, partial(shutil.copyfile, source))
    return target.figure
