"""End-to-end integration setup test against a real (test) Home Assistant
core instance: async_setup_entry, the coordinator's live state-change
handling, entity creation/naming, unload, and - critically - that a
reload (simulating a restart) does not double-count consumption that
was already processed. This is the strongest evidence for the SPEC's
"no double counting after restart" requirement, complementing the pure
tests/unit/test_no_double_count.py unit test.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hu_energy_tariffs.const import (
    CONF_DISTRIBUTION_AREA_ID,
    CONF_PRICING_PERIODS,
    CONF_PROVIDER_ID,
    CONF_SOURCE_ENTITY_ID,
    CONF_TARIFF_PLAN_ID,
    DOMAIN,
)
from custom_components.hu_energy_tariffs.models import PriceComponents, PricingPeriod

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def _set_source(hass, value: str) -> None:
    hass.states.async_set(
        "sensor.test_energy",
        value,
        {"device_class": "energy", "state_class": "total_increasing", "unit_of_measurement": "kWh"},
    )


def _make_entry() -> MockConfigEntry:
    period = PricingPeriod(
        valid_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
        valid_to=None,
        provider_id="mvm_next",
        distribution_area_id="eon",
        tariff_plan_id="mvm_a1",
        quota_kwh_per_year=2523,
        fixed_monthly_fee_ft=1000.0,
        price_components=PriceComponents(energy_charge_discounted=36.9, energy_charge_market=70.0),
    )
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test Home",
        data={
            CONF_SOURCE_ENTITY_ID: "sensor.test_energy",
            CONF_PROVIDER_ID: "mvm_next",
            CONF_DISTRIBUTION_AREA_ID: "eon",
            CONF_TARIFF_PLAN_ID: "mvm_a1",
            CONF_PRICING_PERIODS: [period.to_dict()],
        },
    )


async def test_setup_creates_entities_with_clean_names(hass):
    _set_source(hass, "100.0")
    await hass.async_block_till_done()

    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    current_price = hass.states.get("sensor.test_home_current_price")
    assert current_price is not None
    assert current_price.attributes["friendly_name"] == "Test Home Current price"
    # VAT-inclusive discounted price: 36.9 * 1.27.
    assert float(current_price.state) == pytest.approx(46.863)

    total_cost = hass.states.get("sensor.test_home_total_cost")
    assert total_cost is not None
    assert total_cost.attributes["unit_of_measurement"] == "HUF"


async def test_consumption_delta_updates_entities(hass):
    _set_source(hass, "100.0")
    await hass.async_block_till_done()
    entry = _make_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    _set_source(hass, "105.0")
    await hass.async_block_till_done()

    assert float(hass.states.get("sensor.test_home_total_consumption").state) == pytest.approx(5.0)
    assert float(hass.states.get("sensor.test_home_discounted_consumption").state) == pytest.approx(5.0)


async def test_reload_does_not_double_count(hass):
    _set_source(hass, "100.0")
    await hass.async_block_till_done()
    entry = _make_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    _set_source(hass, "105.0")
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.test_home_total_consumption").state) == pytest.approx(5.0)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    # Simulate a restart: reload with the source sensor unchanged.
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.test_home_total_consumption").state) == pytest.approx(5.0)

    # A real new delta after "restart" must still be counted correctly.
    _set_source(hass, "110.0")
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.test_home_total_consumption").state) == pytest.approx(10.0)


async def test_meter_reset_does_not_go_negative(hass):
    _set_source(hass, "500.0")
    await hass.async_block_till_done()
    entry = _make_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Meter reset to near-zero.
    _set_source(hass, "0.3")
    await hass.async_block_till_done()

    total_consumption = hass.states.get("sensor.test_home_total_consumption")
    assert float(total_consumption.state) == pytest.approx(0.0)
