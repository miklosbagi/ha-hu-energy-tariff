"""Config and options flow tests.

The pure helper tests need no Home Assistant boot. The flow walk-through
tests use pytest-homeassistant-custom-component's lightweight test `hass`
fixture to drive the real config_flow.py/options flow end to end,
including the price-history-preserving PricingPeriod behaviour on
reconfigure.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hu_energy_tariffs.config_flow import (
    _build_pricing_period,
    _distribution_area_options,
    _provider_options,
    _tariff_params_schema,
    _tariff_plan_options,
)
from custom_components.hu_energy_tariffs.const import (
    CONF_DISCOUNTED_PRICE_FT_PER_KWH,
    CONF_DISTRIBUTION_AREA_ID,
    CONF_FIXED_MONTHLY_FEE_FT,
    CONF_MARKET_PRICE_FT_PER_KWH,
    CONF_PRICING_PERIODS,
    CONF_PROVIDER_ID,
    CONF_QUOTA_KWH_PER_YEAR,
    CONF_SOURCE_ENTITY_ID,
    CONF_TARIFF_PLAN_ID,
    DOMAIN,
)
from custom_components.hu_energy_tariffs.models import PriceComponents, PricingPeriod

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def test_provider_options_include_mvm_next():
    assert {o["value"] for o in _provider_options()} == {"mvm_next"}


def test_distribution_area_options_cover_known_areas():
    assert {o["value"] for o in _distribution_area_options()} == {
        "eon",
        "mvm_emasz",
        "opus",
        "e2",
    }


def test_tariff_plan_options_only_lists_registered_strategies():
    # A2/B/H are reserved in the catalog but have no strategy yet.
    assert {o["value"] for o in _tariff_plan_options()} == {"mvm_a1"}


def test_tariff_params_schema_uses_supplied_defaults():
    schema = _tariff_params_schema({CONF_QUOTA_KWH_PER_YEAR: 1234})
    defaults = {
        key.schema: key.default() for key in schema.schema if hasattr(key, "default")
    }
    assert defaults[CONF_QUOTA_KWH_PER_YEAR] == 1234


def test_build_pricing_period_from_form_input():
    period = _build_pricing_period(
        provider_id="mvm_next",
        distribution_area_id="eon",
        tariff_plan_id="mvm_a1",
        user_input={
            CONF_QUOTA_KWH_PER_YEAR: 2523,
            CONF_DISCOUNTED_PRICE_FT_PER_KWH: 36.9,
            CONF_MARKET_PRICE_FT_PER_KWH: 70.0,
            CONF_FIXED_MONTHLY_FEE_FT: 500.0,
        },
    )
    assert isinstance(period, PricingPeriod)
    assert period.quota_kwh_per_year == 2523
    assert period.price_components.energy_charge_discounted == 36.9
    assert period.valid_to is None


async def test_full_config_flow_creates_entry(hass):
    hass.states.async_set(
        "sensor.test_energy",
        "100.0",
        {"device_class": "energy", "state_class": "total_increasing", "unit_of_measurement": "kWh"},
    )
    await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Test Home", "source_entity_id": "sensor.test_energy"},
    )
    assert result["step_id"] == "provider"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"provider_id": "mvm_next"}
    )
    assert result["step_id"] == "distribution_area"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"distribution_area_id": "eon"}
    )
    assert result["step_id"] == "tariff"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"tariff_plan_id": "mvm_a1"}
    )
    assert result["step_id"] == "tariff_params"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "quota_kwh_per_year": 2523,
            "discounted_price_ft_per_kwh": 36.9,
            "market_price_ft_per_kwh": 70.0,
            "fixed_monthly_fee_ft": 0.0,
        },
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "Test Home"
    assert len(result["data"][CONF_PRICING_PERIODS]) == 1


async def test_user_step_rejects_non_energy_entity(hass):
    hass.states.async_set("sensor.not_energy", "100.0")
    await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Test Home", "source_entity_id": "sensor.not_energy"},
    )
    assert result["step_id"] == "user"
    assert result["errors"]["base"] == "source_entity_not_energy"


async def test_options_flow_opens_new_pricing_period_preserving_history(hass):
    original_period = PricingPeriod(
        valid_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
        valid_to=None,
        provider_id="mvm_next",
        distribution_area_id="eon",
        tariff_plan_id="mvm_a1",
        quota_kwh_per_year=2523,
        fixed_monthly_fee_ft=0.0,
        price_components=PriceComponents(
            energy_charge_discounted=36.9, energy_charge_market=70.0
        ),
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test Home",
        data={
            CONF_SOURCE_ENTITY_ID: "sensor.test_energy",
            CONF_PROVIDER_ID: "mvm_next",
            CONF_DISTRIBUTION_AREA_ID: "eon",
            CONF_TARIFF_PLAN_ID: "mvm_a1",
            CONF_PRICING_PERIODS: [original_period.to_dict()],
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"provider_id": "mvm_next"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"distribution_area_id": "eon"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"tariff_plan_id": "mvm_a1"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "quota_kwh_per_year": 2523,
            "discounted_price_ft_per_kwh": 45.0,
            "market_price_ft_per_kwh": 80.0,
            "fixed_monthly_fee_ft": 500.0,
        },
    )
    assert result["type"] == "create_entry"

    periods = [PricingPeriod.from_dict(p) for p in result["data"][CONF_PRICING_PERIODS]]
    assert len(periods) == 2
    assert periods[0].valid_to is not None  # old period closed, not deleted
    assert periods[1].valid_to is None  # new period open-ended
    assert periods[1].price_components.energy_charge_discounted == 45.0
