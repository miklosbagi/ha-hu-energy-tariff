"""Sensor entity descriptions: each value_fn must read the correct
TariffResult field, and every SPEC-required entity must be present.
Pure - no Home Assistant boot required.
"""
from __future__ import annotations

from datetime import datetime, timezone

from custom_components.hu_energy_tariffs.models import TariffResult
from custom_components.hu_energy_tariffs.sensor import SENSOR_DESCRIPTIONS

EXPECTED_KEYS = {
    "current_price",
    "total_consumption",
    "discounted_consumption",
    "market_consumption",
    "discounted_quota",
    "remaining_discounted_quota",
    "variable_cost",
    "fixed_cost",
    "total_cost",
}


def _sample_result() -> TariffResult:
    return TariffResult(
        timestamp=datetime.now(timezone.utc),
        current_price=36.9,
        total_consumption_kwh=5.0,
        discounted_consumption_kwh=5.0,
        market_consumption_kwh=0.0,
        discounted_quota_kwh=100.0,
        quota_used_kwh=5.0,
        quota_remaining_kwh=95.0,
        variable_cost_ft=184.5,
        fixed_cost_ft=10.0,
        total_cost_ft=194.5,
    )


def test_all_spec_required_entities_present():
    keys = {description.key for description in SENSOR_DESCRIPTIONS}
    assert keys == EXPECTED_KEYS


def test_value_fn_reads_matching_field():
    result = _sample_result()
    by_key = {d.key: d.value_fn(result) for d in SENSOR_DESCRIPTIONS}

    assert by_key["current_price"] == result.current_price
    assert by_key["total_consumption"] == result.total_consumption_kwh
    assert by_key["discounted_consumption"] == result.discounted_consumption_kwh
    assert by_key["market_consumption"] == result.market_consumption_kwh
    assert by_key["discounted_quota"] == result.discounted_quota_kwh
    assert by_key["remaining_discounted_quota"] == result.quota_remaining_kwh
    assert by_key["variable_cost"] == result.variable_cost_ft
    assert by_key["fixed_cost"] == result.fixed_cost_ft
    assert by_key["total_cost"] == result.total_cost_ft


def test_current_price_has_no_monetary_device_class():
    # HA's Energy Dashboard current-price picker expects a bare numeric
    # HUF/kWh sensor, not device_class=monetary (that's reserved for
    # total_cost/variable_cost/fixed_cost, which are absolute amounts).
    description = next(d for d in SENSOR_DESCRIPTIONS if d.key == "current_price")
    assert description.device_class is None
    assert description.native_unit_of_measurement == "HUF/kWh"


def test_cost_entities_are_monetary():
    from homeassistant.components.sensor import SensorDeviceClass

    for key in ("variable_cost", "fixed_cost", "total_cost"):
        description = next(d for d in SENSOR_DESCRIPTIONS if d.key == key)
        assert description.device_class == SensorDeviceClass.MONETARY
        assert description.native_unit_of_measurement == "HUF"
