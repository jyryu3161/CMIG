"""SC-2 sign-test contract — §4.7 canonical cases. Plan SC: SC-2."""

import pytest

from cmig.core.sign import Label, Scope, convert, cross_feeding_weight


@pytest.mark.parametrize(
    "raw, scope, ui, label",
    [
        # §4.7 canonical: 환경 exchange
        (-10.0, Scope.ENVIRONMENT, 10.0, Label.UPTAKE),
        (8.0, Scope.ENVIRONMENT, 8.0, Label.SECRETION),
        # §4.7 canonical: 멤버↔pool (OD-43: '분비'=secretion 통일)
        (-5.0, Scope.MEMBER_POOL, 5.0, Label.UPTAKE),
        (3.0, Scope.MEMBER_POOL, 3.0, Label.SECRETION),
    ],
)
def test_canonical_cases(raw, scope, ui, label):
    r = convert(raw, scope)
    assert r.ui_flux == ui
    assert r.label is label
    assert r.ui_flux >= 0.0  # ui_flux 는 항상 magnitude


def test_zero_flux_has_no_label():
    r = convert(0.0, Scope.ENVIRONMENT)
    assert r.ui_flux == 0.0
    assert r.label is None  # 무흐름 → 소비자가 drop


def test_eps_threshold_treats_small_as_zero():
    r = convert(1e-9, Scope.ENVIRONMENT, eps=1e-6)
    assert r.label is None


def test_cross_feeding_weight_is_min():
    # 분비 8, 흡수 5 → weight = min = 5
    assert cross_feeding_weight(secretor_raw=8.0, consumer_raw=-5.0) == 5.0
    # 분비 3, 흡수 9 → weight = min = 3
    assert cross_feeding_weight(secretor_raw=3.0, consumer_raw=-9.0) == 3.0


def test_cross_feeding_requires_secretor_positive_consumer_negative():
    assert cross_feeding_weight(secretor_raw=-1.0, consumer_raw=-5.0) is None  # 둘 다 흡수
    assert cross_feeding_weight(secretor_raw=8.0, consumer_raw=2.0) is None     # 둘 다 분비
