"""Wh/kWh/MWh source values normalize to a common kWh basis."""
from __future__ import annotations

import pytest

from custom_components.hu_energy_tariffs.models import to_kwh


@pytest.mark.parametrize(
    ("value", "unit", "expected_kwh"),
    [
        (1000.0, "Wh", 1.0),
        (1.0, "kWh", 1.0),
        (1.0, "MWh", 1000.0),
        (2500.0, "Wh", 2.5),
    ],
)
def test_to_kwh(value, unit, expected_kwh):
    assert to_kwh(value, unit) == pytest.approx(expected_kwh)


def test_to_kwh_unknown_unit_raises():
    with pytest.raises(ValueError):
        to_kwh(1.0, "GWh")
