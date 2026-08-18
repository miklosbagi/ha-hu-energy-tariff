"""Source sensor unavailable/unknown states must not be treated as a
zero or negative reading - they are parsed as "no reading" instead."""
from __future__ import annotations

from homeassistant.core import State

from custom_components.hu_energy_tariffs.coordinator import HuEnergyTariffsCoordinator


def test_parse_state_unavailable_returns_none():
    state = State("sensor.test_energy", "unavailable")
    assert HuEnergyTariffsCoordinator._parse_state_to_kwh(state) is None  # noqa: SLF001


def test_parse_state_unknown_returns_none():
    state = State("sensor.test_energy", "unknown")
    assert HuEnergyTariffsCoordinator._parse_state_to_kwh(state) is None  # noqa: SLF001


def test_parse_state_none_returns_none():
    assert HuEnergyTariffsCoordinator._parse_state_to_kwh(None) is None  # noqa: SLF001
