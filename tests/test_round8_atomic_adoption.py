"""Round-8 regressions for the remaining atomic figure and Parquet writers."""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from cmig import golden_fixture
from cmig.core import interaction_figures
from cmig.core.sweep import SweepRow, write_sweep_parquet
from cmig.core.tidy import empty_bundle
from cmig.io import atomic
from cmig.render.figure_style import save_figure_atomic, save_publication_tiff


def _assert_no_temp_litter(target: Path) -> None:
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


class _FakeFigure:
    def __init__(self, data: bytes, *, fail: bool = False) -> None:
        self.data = data
        self.fail = fail
        self.formats: list[str] = []

    def savefig(self, destination: Path, *, format: str, **_kwargs: object) -> None:
        self.formats.append(format)
        destination.write_bytes(self.data)
        if self.fail:
            raise OSError("injected writer failure")


@pytest.mark.parametrize("failure", ["writer", "fsync", "replace"])
def test_atomic_svg_failure_preserves_previous_figure(tmp_path: Path, failure: str) -> None:
    target = tmp_path / "figure.svg"
    previous = b"<svg>previous</svg>"
    target.write_bytes(previous)
    figure = _FakeFigure(b"<svg>partial-or-new</svg>", fail=failure == "writer")

    with ExitStack() as stack:
        if failure in {"fsync", "replace"}:
            stack.enter_context(
                patch(
                    f"cmig.io.atomic.os.{failure}",
                    side_effect=OSError(f"injected {failure} failure"),
                )
            )
        with pytest.raises(OSError, match=f"injected {failure} failure"):
            save_figure_atomic(figure, target, format="svg")

    assert figure.formats == ["svg"]
    assert target.read_bytes() == previous
    _assert_no_temp_litter(target)


@pytest.mark.parametrize("failure", ["writer", "fsync", "replace"])
def test_atomic_tiff_failure_preserves_previous_figure(tmp_path: Path, failure: str) -> None:
    image_module = pytest.importorskip("PIL.Image")
    target = tmp_path / "figure.tiff"
    previous = b"previous tiff bytes"
    target.write_bytes(previous)

    staged = tmp_path / "staged.tiff"
    image_module.new("RGB", (2, 2), (255, 255, 255)).save(
        staged,
        format="tiff",
        compression="tiff_lzw",
        dpi=(600, 600),
    )
    figure = _FakeFigure(staged.read_bytes(), fail=failure == "writer")

    with ExitStack() as stack:
        if failure in {"fsync", "replace"}:
            stack.enter_context(
                patch(
                    f"cmig.io.atomic.os.{failure}",
                    side_effect=OSError(f"injected {failure} failure"),
                )
            )
        with pytest.raises(OSError, match=f"injected {failure} failure"):
            save_publication_tiff(figure, target)

    assert figure.formats == ["tiff"]
    assert target.read_bytes() == previous
    _assert_no_temp_litter(target)


def test_interaction_svg_and_tiff_route_through_atomic_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, Path]] = []

    def save_svg(_figure: object, path: Path, **kwargs: object) -> Path:
        assert kwargs["format"] == "svg"
        calls.append(("svg", path))
        return path

    def save_tiff(_figure: object, path: Path) -> None:
        calls.append(("tiff", path))

    monkeypatch.setattr(interaction_figures, "_save_figure_atomic", save_svg)
    monkeypatch.setattr(interaction_figures, "_save_publication_tiff", save_tiff)

    interaction_figures._save_svg_and_tiff(object(), tmp_path / "interaction.svg")

    assert calls == [
        ("svg", tmp_path / "interaction.svg"),
        ("tiff", tmp_path / "interaction.tiff"),
    ]


def _sweep_rows() -> list[SweepRow]:
    return [
        SweepRow(
            condition_id="cond-0000",
            axis_values={"tradeoff_f": 0.5},
            metric="growth",
            value=1.25,
            run_hash="run-hash",
            status="ok",
            diagnostic=None,
            cache_hit=False,
        )
    ]


def _inject_parquet_failure(stack: ExitStack, failure: str) -> None:
    if failure == "writer":

        def fail_after_partial_write(_table: object, handle: object) -> None:
            handle.write(b"partial parquet")  # type: ignore[attr-defined]
            raise OSError("injected writer failure")

        stack.enter_context(
            patch("pyarrow.parquet.write_table", side_effect=fail_after_partial_write)
        )
    else:
        stack.enter_context(
            patch(
                f"cmig.io.atomic.os.{failure}",
                side_effect=OSError(f"injected {failure} failure"),
            )
        )


@pytest.mark.parametrize("failure", ["writer", "fsync", "replace"])
def test_sweep_parquet_failure_preserves_previous_artifact(
    tmp_path: Path, failure: str
) -> None:
    target = tmp_path / "sweep.parquet"
    original = pa.table({"value": [7]})
    pq.write_table(original, target)
    previous = target.read_bytes()

    with ExitStack() as stack:
        _inject_parquet_failure(stack, failure)
        with pytest.raises(OSError, match=f"injected {failure} failure"):
            write_sweep_parquet(_sweep_rows(), target)

    assert target.read_bytes() == previous
    assert pq.read_table(target).equals(original)
    _assert_no_temp_litter(target)


@pytest.mark.parametrize("artifact", ["nodes.parquet", "edges.parquet", "profile.parquet"])
@pytest.mark.parametrize("failure", ["writer", "fsync", "replace"])
def test_golden_capture_parquet_failure_preserves_previous_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    artifact: str,
) -> None:
    target = tmp_path / "expected" / "gurobi" / artifact
    target.parent.mkdir(parents=True)
    original = pa.table({"value": [11]})
    pq.write_table(original, target)
    previous = target.read_bytes()
    bundle = empty_bundle()
    monkeypatch.setattr(golden_fixture, "SOLVER_VARIANTS", ("gurobi",))
    monkeypatch.setattr(golden_fixture, "solve", lambda _solver: (object(), bundle))
    real_writer = golden_fixture.atomic_write_parquet

    def fail_selected(path: str | Path, table: object) -> Path:
        if Path(path).name != artifact:
            return real_writer(path, table)
        with ExitStack() as stack:
            _inject_parquet_failure(stack, failure)
            return real_writer(path, table)

    monkeypatch.setattr(golden_fixture, "atomic_write_parquet", fail_selected)
    with pytest.raises(OSError, match=f"injected {failure} failure"):
        golden_fixture.capture(tmp_path)

    assert target.read_bytes() == previous
    assert pq.read_table(target).equals(original)
    _assert_no_temp_litter(target)


def test_all_atomic_writer_shapes_request_parent_directory_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    synced: list[Path] = []
    monkeypatch.setattr(atomic, "_sync_directory_best_effort", synced.append)

    atomic.atomic_write_bytes(tmp_path / "binary", b"bytes")
    atomic.atomic_write_text(tmp_path / "text", "text")
    atomic.atomic_write_path(tmp_path / "path", lambda path: path.write_bytes(b"path"))

    assert synced == [tmp_path, tmp_path, tmp_path]


@pytest.mark.parametrize("operation", ["open", "fsync"])
def test_unsupported_directory_sync_is_best_effort(tmp_path: Path, operation: str) -> None:
    with patch(
        f"cmig.io.atomic.os.{operation}",
        side_effect=OSError(f"directory {operation} unsupported"),
    ):
        atomic._sync_directory_best_effort(tmp_path)
