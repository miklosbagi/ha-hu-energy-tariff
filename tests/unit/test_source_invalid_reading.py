"""A non-numeric or malformed source reading must be treated as invalid,
not as a consumption delta - while a well-formed reading in any
supported unit parses to the correct kWh value."""
from __future__ import annotations

from homeassistant.core import State

from custom_components.hu_energy_tariffs.coordinator import HuEnergyTariffsCoordinator


def test_parse_state_non_numeric_returns_none():
    state = State("sensor.test_energy", "not-a-number")
    assert HuEnergyTariffsCoordinator._parse_state_to_kwh(state) is None  # noqa: SLF001


def test_parse_state_valid_numeric_reading():
    state = State("sensor.test_energy", "12.5", attributes={"unit_of_measurement": "kWh"})
    assert HuEnergyTariffsCoordinator._parse_state_to_kwh(state) == 12.5  # noqa: SLF001


def test_parse_state_normalizes_unit():
    state = State("sensor.test_energy", "12500", attributes={"unit_of_measurement": "Wh"})
    assert HuEnergyTariffsCoordinator._parse_state_to_kwh(state) == 12.5  # noqa: SLF001


def test_parse_state_unsupported_unit_returns_none():
    state = State("sensor.test_energy", "12.5", attributes={"unit_of_measurement": "GWh"})
    assert HuEnergyTariffsCoordinator._parse_state_to_kwh(state) is None  # noqa: SLF001
