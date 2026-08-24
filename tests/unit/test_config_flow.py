"""Config and options flow tests.

The pure helper tests need no Home Assistant boot. The flow walk-through
tests use pytest-homeassistant-custom-component's lightweight test `hass`
fixture to drive the real config_flow.py/options flow end to end,
including the price-history-preserving PricingPeriod behaviour on
reconfigure and the provider/tariff auto-skip logic.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hu_energy_tariff.config_flow import (
    SECTION_ELECTRICITY_PRICE,
    SECTION_NETWORK_FEES,
    _area_default_discounted_energy_price,
    _build_pricing_period,
    _distribution_area_options,
    _flatten_pricing_input,
    _only_option_id,
    _pricing_schema,
    _provider_options,
    _tariff_plan_options,
)
from custom_components.hu_energy_tariff.const import (
    CONF_DISCOUNTED_PRICE_FT_PER_KWH,
    CONF_DISTRIBUTION_AREA_ID,
    CONF_DISTRIBUTION_CHARGE_FT_PER_KWH,
    CONF_FIXED_MONTHLY_FEE_FT,
    CONF_MARKET_PRICE_FT_PER_KWH,
    CONF_PRICING_PERIODS,
    CONF_PROVIDER_ID,
    CONF_QUOTA_KWH_PER_YEAR,
    CONF_SOURCE_ENTITY_ID,
    CONF_TARIFF_PLAN_ID,
    CONF_TRANSMISSION_CHARGE_FT_PER_KWH,
    DEFAULT_A1_DISCOUNTED_ENERGY_PRICE_FT_PER_KWH,
    DOMAIN,
)
from custom_components.hu_energy_tariff.models import PriceComponents, PricingPeriod

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def test_provider_options_include_mvm_next():
    assert {o["value"] for o in _provider_options()} == {"mvm_next"}


def test_distribution_area_options_cover_known_areas():
    assert {o["value"] for o in _distribution_area_options()} == {
        "eon",
        "mvm_emasz",
        "opus",
        "e2",
        "elmu",
    }


def test_area_default_discounted_energy_price_differs_by_area():
    assert _area_default_discounted_energy_price(
        "eon"
    ) == _area_default_discounted_energy_price("opus")
    assert _area_default_discounted_energy_price(
        "elmu"
    ) != _area_default_discounted_energy_price("eon")


def test_area_default_discounted_energy_price_falls_back_for_unknown_area():
    assert _area_default_discounted_energy_price("not_a_real_area") == (
        DEFAULT_A1_DISCOUNTED_ENERGY_PRICE_FT_PER_KWH
    )
    assert _area_default_discounted_energy_price(None) == (
        DEFAULT_A1_DISCOUNTED_ENERGY_PRICE_FT_PER_KWH
    )


def test_tariff_plan_options_only_lists_registered_strategies():
    # A2/B/H are reserved in the catalog but have no strategy yet.
    assert {o["value"] for o in _tariff_plan_options()} == {"mvm_a1"}


def test_only_option_id_returns_none_for_multiple_options():
    assert _only_option_id(_distribution_area_options()) is None


def test_only_option_id_returns_the_single_value():
    assert _only_option_id(_provider_options()) == "mvm_next"
    assert _only_option_id(_tariff_plan_options()) == "mvm_a1"


def test_pricing_schema_uses_supplied_defaults():
    schema = _pricing_schema(
        {
            SECTION_ELECTRICITY_PRICE: {CONF_QUOTA_KWH_PER_YEAR: 1234},
            SECTION_NETWORK_FEES: {CONF_FIXED_MONTHLY_FEE_FT: 999.0},
        }
    )
    # Defaults live inside each section's own nested schema, not on the
    # outer section key (which has no default of its own).
    energy_section = schema.schema[SECTION_ELECTRICITY_PRICE]
    fees_section = schema.schema[SECTION_NETWORK_FEES]
    energy_defaults = {
        key.schema: key.default() for key in energy_section.schema.schema if hasattr(key, "default")
    }
    fees_defaults = {
        key.schema: key.default() for key in fees_section.schema.schema if hasattr(key, "default")
    }
    assert energy_defaults[CONF_QUOTA_KWH_PER_YEAR] == 1234
    assert fees_defaults[CONF_FIXED_MONTHLY_FEE_FT] == 999.0


def test_flatten_pricing_input_merges_both_sections():
    flat = _flatten_pricing_input(
        {
            SECTION_ELECTRICITY_PRICE: {CONF_QUOTA_KWH_PER_YEAR: 2523},
            SECTION_NETWORK_FEES: {CONF_FIXED_MONTHLY_FEE_FT: 120.5},
        }
    )
    assert flat == {
        CONF_QUOTA_KWH_PER_YEAR: 2523,
        CONF_FIXED_MONTHLY_FEE_FT: 120.5,
    }


def test_build_pricing_period_from_form_input():
    period = _build_pricing_period(
        provider_id="mvm_next",
        distribution_area_id="eon",
        tariff_plan_id="mvm_a1",
        user_input={
            CONF_QUOTA_KWH_PER_YEAR: 2523,
            CONF_DISCOUNTED_PRICE_FT_PER_KWH: 4.39,
            CONF_MARKET_PRICE_FT_PER_KWH: 31.8,
            CONF_DISTRIBUTION_CHARGE_FT_PER_KWH: 23.4,
            CONF_TRANSMISSION_CHARGE_FT_PER_KWH: 0.0,
            CONF_FIXED_MONTHLY_FEE_FT: 120.5,
        },
    )
    assert isinstance(period, PricingPeriod)
    assert period.quota_kwh_per_year == 2523
    assert period.price_components.energy_charge_discounted == 4.39
    assert period.price_components.distribution_charge == 23.4
    assert period.valid_to is None


async def test_full_config_flow_creates_entry(hass):
    """Provider and tariff steps are auto-skipped (single option each) -
    the flow goes straight from `user` (name/sensor/area, all one screen)
    to `pricing` (one screen, two sections)."""
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
        {
            "name": "Test Home",
            "source_entity_id": "sensor.test_energy",
            "distribution_area_id": "eon",
        },
    )
    assert result["step_id"] == "pricing"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            SECTION_ELECTRICITY_PRICE: {
                "quota_kwh_per_year": 2523,
                "discounted_price_ft_per_kwh": 4.39,
                "market_price_ft_per_kwh": 31.8,
            },
            SECTION_NETWORK_FEES: {
                "distribution_charge_ft_per_kwh": 23.4,
                "transmission_charge_ft_per_kwh": 0.0,
                "fixed_monthly_fee_ft": 120.5,
            },
        },
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "Test Home"
    assert result["data"][CONF_PROVIDER_ID] == "mvm_next"
    assert result["data"][CONF_TARIFF_PLAN_ID] == "mvm_a1"
    assert result["data"][CONF_DISTRIBUTION_AREA_ID] == "eon"
    periods = result["data"][CONF_PRICING_PERIODS]
    assert len(periods) == 1
    period = PricingPeriod.from_dict(periods[0])
    assert period.price_components.energy_charge_discounted == 4.39
    assert period.price_components.distribution_charge == 23.4
    assert period.fixed_monthly_fee_ft == 120.5


async def test_user_step_rejects_non_energy_entity(hass):
    hass.states.async_set("sensor.not_energy", "100.0")
    await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Test Home",
            "source_entity_id": "sensor.not_energy",
            "distribution_area_id": "eon",
        },
    )
    assert result["step_id"] == "user"
    assert result["errors"]["base"] == "source_entity_not_energy"


async def test_options_flow_opens_new_pricing_period_preserving_history(hass):
    """Options flow starts at distribution_area (provider/tariff are
    auto-skipped), then goes straight to the combined pricing step."""
    original_period = PricingPeriod(
        valid_from=datetime(2020, 1, 1, tzinfo=UTC),
        valid_to=None,
        provider_id="mvm_next",
        distribution_area_id="eon",
        tariff_plan_id="mvm_a1",
        quota_kwh_per_year=2523,
        fixed_monthly_fee_ft=120.5,
        price_components=PriceComponents(
            energy_charge_discounted=4.39,
            energy_charge_market=31.8,
            distribution_charge=23.4,
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
    assert result["step_id"] == "distribution_area"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"distribution_area_id": "eon"}
    )
    assert result["step_id"] == "pricing"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            SECTION_ELECTRICITY_PRICE: {
                "quota_kwh_per_year": 2523,
                "discounted_price_ft_per_kwh": 5.0,
                "market_price_ft_per_kwh": 35.0,
            },
            SECTION_NETWORK_FEES: {
                "distribution_charge_ft_per_kwh": 23.4,
                "transmission_charge_ft_per_kwh": 0.0,
                "fixed_monthly_fee_ft": 200.0,
            },
        },
    )
    assert result["type"] == "create_entry"

    periods = [PricingPeriod.from_dict(p) for p in result["data"][CONF_PRICING_PERIODS]]
    assert len(periods) == 2
    assert periods[0].valid_to is not None  # old period closed, not deleted
    assert periods[1].valid_to is None  # new period open-ended
    assert periods[1].price_components.energy_charge_discounted == 5.0
    assert periods[1].fixed_monthly_fee_ft == 200.0
