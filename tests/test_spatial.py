from __future__ import annotations

import pytest

from cmig.core.spatial import SpatialPreviewConfig, run_spatial_preview, spatial_rows


def test_spatial_preview_source_sink_gradient_is_stable():
    result = run_spatial_preview(
        SpatialPreviewConfig(width=12, height=8, steps=20, dt=0.2, diffusion=0.3)
    )
    assert result.status == "completed"
    final = result.final.values
    assert len(final) == 8 and len(final[0]) == 12
    assert all(value >= 0.0 for row in final for value in row)
    assert final[4][0] == pytest.approx(10.0)
    assert final[4][-1] == pytest.approx(0.0)
    assert final[4][1] > final[4][-2]


def test_spatial_preview_rows_include_stored_frames():
    result = run_spatial_preview(
        SpatialPreviewConfig(width=4, height=3, steps=5, store_every=2)
    )
    rows = spatial_rows(result)
    steps = {row["step"] for row in rows}
    assert steps == {0, 2, 4, 5}
    assert len(rows) == 4 * 3 * 4


def test_spatial_preview_rejects_unstable_inputs():
    with pytest.raises(ValueError, match="width and height"):
        run_spatial_preview(SpatialPreviewConfig(width=2, height=8))


def test_spatial_preview_rejects_overlapping_source_sink():
    with pytest.raises(ValueError, match="source_edge and sink_edge overlap"):
        run_spatial_preview(
            SpatialPreviewConfig(source_edge="right", sink_edge="right")
        )
    with pytest.raises(ValueError, match="source_edge and sink_edge overlap"):
        run_spatial_preview(
            SpatialPreviewConfig(source_edge="left", sink_edge="top")
        )
