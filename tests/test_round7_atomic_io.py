"""Round-7 T3 regressions for atomic binary and Parquet publication."""

from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from cmig.core.manifest import RunHashComponents
from cmig.core.tidy import empty_bundle
from cmig.io.atomic import atomic_write_bytes, atomic_write_parquet
from cmig.io.solve_output import write_solve_output


def _components() -> RunHashComponents:
    return RunHashComponents(
        model_checksum="sha256:model",
        medium_checksum="sha256:medium",
        member_set=[],
        abundance={},
        bounds={},
        tradeoff_f=0.5,
        solver_setting={},
        micom_version="test",
        cmig_core_version="test",
        namespace_mapping_decisions=[],
        flux_normalization_method="pfba",
    )


def test_atomic_write_bytes_replaces_complete_file(tmp_path):
    target = tmp_path / "artifact.bin"

    assert atomic_write_bytes(target, b"new bytes") == target
    assert target.read_bytes() == b"new bytes"
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("failure", ["fsync", "replace"])
def test_atomic_write_parquet_failure_preserves_previous_file(tmp_path, failure):
    """A failure before the atomic swap cannot expose a partial Parquet file."""
    target = tmp_path / "artifact.parquet"
    original = pa.table({"value": [1, 2, 3]})
    replacement = pa.table({"value": [4, 5, 6]})
    pq.write_table(original, target)
    previous_bytes = target.read_bytes()

    with patch(f"cmig.io.atomic.os.{failure}", side_effect=OSError("injected failure")):
        with pytest.raises(OSError, match="injected failure"):
            atomic_write_parquet(target, replacement)

    assert target.read_bytes() == previous_bytes
    assert pq.read_table(target).equals(original)
    assert [path.name for path in tmp_path.iterdir()] == ["artifact.parquet"]


def test_atomic_write_parquet_writer_failure_cleans_partial_tempfile(tmp_path):
    target = tmp_path / "artifact.parquet"
    original = pa.table({"value": [1]})
    pq.write_table(original, target)
    previous_bytes = target.read_bytes()

    def fail_after_partial_write(_table, handle):
        handle.write(b"partial parquet")
        raise OSError("disk full")

    with patch("pyarrow.parquet.write_table", side_effect=fail_after_partial_write):
        with pytest.raises(OSError, match="disk full"):
            atomic_write_parquet(target, pa.table({"value": [2]}))

    assert target.read_bytes() == previous_bytes
    assert [path.name for path in tmp_path.iterdir()] == ["artifact.parquet"]


def test_atomic_parquet_bytes_match_direct_pyarrow_output(tmp_path):
    """Changing the publication path must not change the artifact bytes."""
    table = pa.table({"name": ["a", "b"], "value": [1.25, None]})
    direct = tmp_path / "direct.parquet"
    atomic = tmp_path / "atomic.parquet"

    pq.write_table(table, direct)
    atomic_write_parquet(atomic, table)

    assert atomic.read_bytes() == direct.read_bytes()


def test_solve_output_routes_every_parquet_through_atomic_writer(tmp_path, monkeypatch):
    import cmig.io.solve_output as solve_output

    bundle = empty_bundle()
    bundle.matrix = pa.table({"value": [1]})
    written: list[str] = []
    real_writer = solve_output.atomic_write_parquet

    def recording_writer(path, table):
        written.append(path.name)
        return real_writer(path, table)

    monkeypatch.setattr(solve_output, "atomic_write_parquet", recording_writer)
    write_solve_output(bundle, _components(), tmp_path / "run")

    assert written == [
        "nodes.parquet",
        "edges.parquet",
        "profile.parquet",
        "matrix.parquet",
    ]
