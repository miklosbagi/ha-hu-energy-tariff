"""Config and options flow for hu_energy_tariffs."""
from __future__ import annotations

import dataclasses
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector
import homeassistant.util.dt as dt_util

from . import tariffs  # noqa: F401  (import for registration side effects)
from .const import (
    CONF_DISCOUNTED_PRICE_FT_PER_KWH,
    CONF_DISTRIBUTION_AREA_ID,
    CONF_FIXED_MONTHLY_FEE_FT,
    CONF_MARKET_PRICE_FT_PER_KWH,
    CONF_PRICING_PERIODS,
    CONF_PROVIDER_ID,
    CONF_QUOTA_KWH_PER_YEAR,
    CONF_SOURCE_ENTITY_ID,
    CONF_TARIFF_PLAN_ID,
    DEFAULT_A1_DISCOUNTED_PRICE_FT_PER_KWH,
    DEFAULT_A1_FIXED_MONTHLY_FEE_FT,
    DEFAULT_A1_MARKET_PRICE_FT_PER_KWH,
    DEFAULT_A1_QUOTA_KWH,
    DISTRIBUTION_AREAS,
    DOMAIN,
    PROVIDERS,
)
from .models import PriceComponents, PricingPeriod
from .tariffs.registry import available_tariff_plans

DEFAULT_NAME = "Hungarian Energy Tariffs"


def _provider_options() -> list[selector.SelectOptionDict]:
    return [selector.SelectOptionDict(value=p.id, label=p.name) for p in PROVIDERS.values()]


def _distribution_area_options() -> list[selector.SelectOptionDict]:
    return [
        selector.SelectOptionDict(value=a.id, label=a.name) for a in DISTRIBUTION_AREAS.values()
    ]


def _tariff_plan_options() -> list[selector.SelectOptionDict]:
    return [
        selector.SelectOptionDict(value=p.id, label=f"{p.code} - {p.name}")
        for p in available_tariff_plans()
    ]


def _tariff_params_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_QUOTA_KWH_PER_YEAR,
                default=defaults.get(CONF_QUOTA_KWH_PER_YEAR, DEFAULT_A1_QUOTA_KWH),
            ): vol.Coerce(float),
            vol.Required(
                CONF_DISCOUNTED_PRICE_FT_PER_KWH,
                default=defaults.get(
                    CONF_DISCOUNTED_PRICE_FT_PER_KWH, DEFAULT_A1_DISCOUNTED_PRICE_FT_PER_KWH
                ),
            ): vol.Coerce(float),
            vol.Required(
                CONF_MARKET_PRICE_FT_PER_KWH,
                default=defaults.get(
                    CONF_MARKET_PRICE_FT_PER_KWH, DEFAULT_A1_MARKET_PRICE_FT_PER_KWH
                ),
            ): vol.Coerce(float),
            vol.Required(
                CONF_FIXED_MONTHLY_FEE_FT,
                default=defaults.get(
                    CONF_FIXED_MONTHLY_FEE_FT, DEFAULT_A1_FIXED_MONTHLY_FEE_FT
                ),
            ): vol.Coerce(float),
        }
    )


def _build_pricing_period(
    *, provider_id: str, distribution_area_id: str, tariff_plan_id: str, user_input: dict[str, Any]
) -> PricingPeriod:
    return PricingPeriod(
        valid_from=dt_util.utcnow(),
        valid_to=None,
        provider_id=provider_id,
        distribution_area_id=distribution_area_id,
        tariff_plan_id=tariff_plan_id,
        quota_kwh_per_year=user_input[CONF_QUOTA_KWH_PER_YEAR],
        fixed_monthly_fee_ft=user_input[CONF_FIXED_MONTHLY_FEE_FT],
        price_components=PriceComponents(
            energy_charge_discounted=user_input[CONF_DISCOUNTED_PRICE_FT_PER_KWH],
            energy_charge_market=user_input[CONF_MARKET_PRICE_FT_PER_KWH],
        ),
    )


class HuEnergyTariffsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hungarian Energy Tariffs."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            entity_id = user_input[CONF_SOURCE_ENTITY_ID]
            state = self.hass.states.get(entity_id)
            if state is None:
                errors["base"] = "source_entity_not_found"
            elif state.attributes.get("device_class") != "energy":
                errors["base"] = "source_entity_not_energy"
            elif state.attributes.get("state_class") not in ("total", "total_increasing"):
                errors["base"] = "source_entity_not_total_increasing"
            else:
                self._data[CONF_NAME] = user_input[CONF_NAME]
                self._data[CONF_SOURCE_ENTITY_ID] = entity_id
                return await self.async_step_provider()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_SOURCE_ENTITY_ID): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="energy")
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_provider(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data[CONF_PROVIDER_ID] = user_input[CONF_PROVIDER_ID]
            return await self.async_step_distribution_area()

        schema = vol.Schema(
            {
                vol.Required(CONF_PROVIDER_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_provider_options())
                )
            }
        )
        return self.async_show_form(step_id="provider", data_schema=schema)

    async def async_step_distribution_area(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data[CONF_DISTRIBUTION_AREA_ID] = user_input[CONF_DISTRIBUTION_AREA_ID]
            return await self.async_step_tariff()

        schema = vol.Schema(
            {
                vol.Required(CONF_DISTRIBUTION_AREA_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_distribution_area_options())
                )
            }
        )
        return self.async_show_form(step_id="distribution_area", data_schema=schema)

    async def async_step_tariff(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data[CONF_TARIFF_PLAN_ID] = user_input[CONF_TARIFF_PLAN_ID]
            return await self.async_step_tariff_params()

        schema = vol.Schema(
            {
                vol.Required(CONF_TARIFF_PLAN_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_tariff_plan_options())
                )
            }
        )
        return self.async_show_form(step_id="tariff", data_schema=schema)

    async def async_step_tariff_params(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            period = _build_pricing_period(
                provider_id=self._data[CONF_PROVIDER_ID],
                distribution_area_id=self._data[CONF_DISTRIBUTION_AREA_ID],
                tariff_plan_id=self._data[CONF_TARIFF_PLAN_ID],
                user_input=user_input,
            )
            self._data[CONF_PRICING_PERIODS] = [period.to_dict()]
            return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)

        return self.async_show_form(
            step_id="tariff_params", data_schema=_tariff_params_schema({})
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> HuEnergyTariffsOptionsFlow:
        return HuEnergyTariffsOptionsFlow(config_entry)


class HuEnergyTariffsOptionsFlow(OptionsFlow):
    """Options flow: re-run provider/area/tariff/params, preserving price
    history by opening a new PricingPeriod rather than mutating in place.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._data: dict[str, Any] = dict(config_entry.data)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self.async_step_provider()

    async def async_step_provider(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data[CONF_PROVIDER_ID] = user_input[CONF_PROVIDER_ID]
            return await self.async_step_distribution_area()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PROVIDER_ID, default=self._data.get(CONF_PROVIDER_ID)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_provider_options())
                )
            }
        )
        return self.async_show_form(step_id="provider", data_schema=schema)

    async def async_step_distribution_area(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data[CONF_DISTRIBUTION_AREA_ID] = user_input[CONF_DISTRIBUTION_AREA_ID]
            return await self.async_step_tariff()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DISTRIBUTION_AREA_ID, default=self._data.get(CONF_DISTRIBUTION_AREA_ID)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_distribution_area_options())
                )
            }
        )
        return self.async_show_form(step_id="distribution_area", data_schema=schema)

    async def async_step_tariff(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data[CONF_TARIFF_PLAN_ID] = user_input[CONF_TARIFF_PLAN_ID]
            return await self.async_step_tariff_params()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_TARIFF_PLAN_ID, default=self._data.get(CONF_TARIFF_PLAN_ID)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_tariff_plan_options())
                )
            }
        )
        return self.async_show_form(step_id="tariff", data_schema=schema)

    async def async_step_tariff_params(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        existing_periods = [
            PricingPeriod.from_dict(p) for p in self._data.get(CONF_PRICING_PERIODS, [])
        ]
        last_period = existing_periods[-1] if existing_periods else None

        if user_input is not None:
            new_period = _build_pricing_period(
                provider_id=self._data[CONF_PROVIDER_ID],
                distribution_area_id=self._data[CONF_DISTRIBUTION_AREA_ID],
                tariff_plan_id=self._data[CONF_TARIFF_PLAN_ID],
                user_input=user_input,
            )
            if last_period is not None:
                # Close the currently open-ended period rather than
                # mutating it, so already-accumulated cost is never
                # retroactively recalculated with the new prices.
                existing_periods[-1] = dataclasses.replace(
                    last_period, valid_to=new_period.valid_from
                )
            existing_periods.append(new_period)
            self._data[CONF_PRICING_PERIODS] = [p.to_dict() for p in existing_periods]
            return self.async_create_entry(title="", data=self._data)

        defaults: dict[str, Any] = {}
        if last_period is not None:
            defaults = {
                CONF_QUOTA_KWH_PER_YEAR: last_period.quota_kwh_per_year,
                CONF_DISCOUNTED_PRICE_FT_PER_KWH: last_period.price_components.energy_charge_discounted,
                CONF_MARKET_PRICE_FT_PER_KWH: last_period.price_components.energy_charge_market,
                CONF_FIXED_MONTHLY_FEE_FT: last_period.fixed_monthly_fee_ft,
            }
        return self.async_show_form(
            step_id="tariff_params", data_schema=_tariff_params_schema(defaults)
        )
