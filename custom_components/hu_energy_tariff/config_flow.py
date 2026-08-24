"""Config and options flow for hu_energy_tariff."""
from __future__ import annotations

import dataclasses
from typing import Any

import homeassistant.util.dt as dt_util
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from . import tariffs  # noqa: F401  (import for registration side effects)
from .const import (
    A1_OFFICIAL_PRICE_SHEET_URL,
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
    DEFAULT_A1_DISCOUNTED_ENERGY_PRICE_BY_AREA_FT_PER_KWH,
    DEFAULT_A1_DISCOUNTED_ENERGY_PRICE_FT_PER_KWH,
    DEFAULT_A1_DISTRIBUTION_CHARGE_FT_PER_KWH,
    DEFAULT_A1_FIXED_MONTHLY_FEE_FT,
    DEFAULT_A1_MARKET_ENERGY_PRICE_FT_PER_KWH,
    DEFAULT_A1_QUOTA_KWH,
    DEFAULT_A1_TRANSMISSION_CHARGE_FT_PER_KWH,
    DISTRIBUTION_AREAS,
    DOMAIN,
    PROVIDERS,
)
from .models import PriceComponents, PricingPeriod
from .tariffs.registry import available_tariff_plans

DEFAULT_NAME = "Hungarian Energy Tariffs"

# Section keys for the combined pricing step - the resulting user_input
# comes back nested under these (e.g. user_input[SECTION_ELECTRICITY_PRICE]),
# not flat, so _flatten_pricing_input() below un-nests it before it's
# handed to _build_pricing_period().
SECTION_ELECTRICITY_PRICE = "electricity_price"
SECTION_NETWORK_FEES = "network_fees"


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


def _only_option_id(options: list[selector.SelectOptionDict]) -> str | None:
    """If there's exactly one choice, there's nothing to ask - the picker
    step for it gets skipped entirely and this becomes the value. Adding
    a second provider or tariff plan later automatically brings the
    picker step back, with no code change needed here."""
    return options[0]["value"] if len(options) == 1 else None


def _area_default_discounted_energy_price(distribution_area_id: str | None) -> float:
    """A1's discounted energy rate genuinely differs by DSO area - look
    up the official per-area figure, falling back to the flat default
    only for an unrecognized/missing area id."""
    return DEFAULT_A1_DISCOUNTED_ENERGY_PRICE_BY_AREA_FT_PER_KWH.get(
        distribution_area_id, DEFAULT_A1_DISCOUNTED_ENERGY_PRICE_FT_PER_KWH
    )


def _pricing_schema(defaults: dict[str, dict[str, Any]]) -> vol.Schema:
    """One screen, two clearly labeled sections - mirrors a Hungarian
    bill's own two groups (Villamosenergia ár / Rendszerhasználati díjak)
    so users can transcribe each line directly. `defaults` is keyed by
    section (SECTION_ELECTRICITY_PRICE / SECTION_NETWORK_FEES)."""
    energy_defaults = defaults.get(SECTION_ELECTRICITY_PRICE, {})
    fees_defaults = defaults.get(SECTION_NETWORK_FEES, {})
    return vol.Schema(
        {
            vol.Required(SECTION_ELECTRICITY_PRICE): section(
                vol.Schema(
                    {
                        vol.Required(
                            CONF_QUOTA_KWH_PER_YEAR,
                            default=energy_defaults.get(
                                CONF_QUOTA_KWH_PER_YEAR, DEFAULT_A1_QUOTA_KWH
                            ),
                        ): vol.Coerce(float),
                        vol.Required(
                            CONF_DISCOUNTED_PRICE_FT_PER_KWH,
                            default=energy_defaults.get(
                                CONF_DISCOUNTED_PRICE_FT_PER_KWH,
                                DEFAULT_A1_DISCOUNTED_ENERGY_PRICE_FT_PER_KWH,
                            ),
                        ): vol.Coerce(float),
                        vol.Required(
                            CONF_MARKET_PRICE_FT_PER_KWH,
                            default=energy_defaults.get(
                                CONF_MARKET_PRICE_FT_PER_KWH,
                                DEFAULT_A1_MARKET_ENERGY_PRICE_FT_PER_KWH,
                            ),
                        ): vol.Coerce(float),
                    }
                ),
                {"collapsed": False},
            ),
            vol.Required(SECTION_NETWORK_FEES): section(
                vol.Schema(
                    {
                        vol.Required(
                            CONF_DISTRIBUTION_CHARGE_FT_PER_KWH,
                            default=fees_defaults.get(
                                CONF_DISTRIBUTION_CHARGE_FT_PER_KWH,
                                DEFAULT_A1_DISTRIBUTION_CHARGE_FT_PER_KWH,
                            ),
                        ): vol.Coerce(float),
                        vol.Required(
                            CONF_TRANSMISSION_CHARGE_FT_PER_KWH,
                            default=fees_defaults.get(
                                CONF_TRANSMISSION_CHARGE_FT_PER_KWH,
                                DEFAULT_A1_TRANSMISSION_CHARGE_FT_PER_KWH,
                            ),
                        ): vol.Coerce(float),
                        vol.Required(
                            CONF_FIXED_MONTHLY_FEE_FT,
                            default=fees_defaults.get(
                                CONF_FIXED_MONTHLY_FEE_FT, DEFAULT_A1_FIXED_MONTHLY_FEE_FT
                            ),
                        ): vol.Coerce(float),
                    }
                ),
                {"collapsed": False},
            ),
        }
    )


def _flatten_pricing_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """section() nests submitted values under their section key - un-nest
    back to the flat shape _build_pricing_period() expects."""
    return {
        **user_input[SECTION_ELECTRICITY_PRICE],
        **user_input[SECTION_NETWORK_FEES],
    }


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
            transmission_charge=user_input[CONF_TRANSMISSION_CHARGE_FT_PER_KWH],
            distribution_charge=user_input[CONF_DISTRIBUTION_CHARGE_FT_PER_KWH],
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
                self._data[CONF_DISTRIBUTION_AREA_ID] = user_input[CONF_DISTRIBUTION_AREA_ID]
                return await self._async_resolve_provider()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_SOURCE_ENTITY_ID): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="energy")
                ),
                vol.Required(CONF_DISTRIBUTION_AREA_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_distribution_area_options())
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={"price_sheet_url": A1_OFFICIAL_PRICE_SHEET_URL},
        )

    async def _async_resolve_provider(self) -> ConfigFlowResult:
        auto_id = _only_option_id(_provider_options())
        if auto_id is not None:
            self._data[CONF_PROVIDER_ID] = auto_id
            return await self._async_resolve_tariff()
        return await self.async_step_provider()

    async def async_step_provider(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data[CONF_PROVIDER_ID] = user_input[CONF_PROVIDER_ID]
            return await self._async_resolve_tariff()

        schema = vol.Schema(
            {
                vol.Required(CONF_PROVIDER_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_provider_options())
                )
            }
        )
        return self.async_show_form(step_id="provider", data_schema=schema)

    async def _async_resolve_tariff(self) -> ConfigFlowResult:
        auto_id = _only_option_id(_tariff_plan_options())
        if auto_id is not None:
            self._data[CONF_TARIFF_PLAN_ID] = auto_id
            return await self.async_step_pricing()
        return await self.async_step_tariff()

    async def async_step_tariff(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data[CONF_TARIFF_PLAN_ID] = user_input[CONF_TARIFF_PLAN_ID]
            return await self.async_step_pricing()

        schema = vol.Schema(
            {
                vol.Required(CONF_TARIFF_PLAN_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_tariff_plan_options())
                )
            }
        )
        return self.async_show_form(step_id="tariff", data_schema=schema)

    async def async_step_pricing(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Electricity price + network usage fees, one screen, two sections."""
        if user_input is not None:
            period = _build_pricing_period(
                provider_id=self._data[CONF_PROVIDER_ID],
                distribution_area_id=self._data[CONF_DISTRIBUTION_AREA_ID],
                tariff_plan_id=self._data[CONF_TARIFF_PLAN_ID],
                user_input=_flatten_pricing_input(user_input),
            )
            self._data[CONF_PRICING_PERIODS] = [period.to_dict()]
            return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)

        defaults = {
            SECTION_ELECTRICITY_PRICE: {
                CONF_DISCOUNTED_PRICE_FT_PER_KWH: _area_default_discounted_energy_price(
                    self._data.get(CONF_DISTRIBUTION_AREA_ID)
                )
            }
        }
        return self.async_show_form(
            step_id="pricing",
            data_schema=_pricing_schema(defaults),
            description_placeholders={"price_sheet_url": A1_OFFICIAL_PRICE_SHEET_URL},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> HuEnergyTariffsOptionsFlow:
        return HuEnergyTariffsOptionsFlow(config_entry)


class HuEnergyTariffsOptionsFlow(OptionsFlow):
    """Options flow: re-run distribution area/tariff/pricing, preserving
    price history by opening a new PricingPeriod rather than mutating in
    place. Provider/tariff picker steps are skipped the same way as in
    the initial config flow whenever there's only one option.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._data: dict[str, Any] = dict(config_entry.data)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self.async_step_distribution_area()

    async def async_step_distribution_area(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data[CONF_DISTRIBUTION_AREA_ID] = user_input[CONF_DISTRIBUTION_AREA_ID]
            return await self._async_resolve_provider()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DISTRIBUTION_AREA_ID, default=self._data.get(CONF_DISTRIBUTION_AREA_ID)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_distribution_area_options())
                )
            }
        )
        return self.async_show_form(
            step_id="distribution_area",
            data_schema=schema,
            description_placeholders={"price_sheet_url": A1_OFFICIAL_PRICE_SHEET_URL},
        )

    async def _async_resolve_provider(self) -> ConfigFlowResult:
        auto_id = _only_option_id(_provider_options())
        if auto_id is not None:
            self._data[CONF_PROVIDER_ID] = auto_id
            return await self._async_resolve_tariff()
        return await self.async_step_provider()

    async def async_step_provider(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data[CONF_PROVIDER_ID] = user_input[CONF_PROVIDER_ID]
            return await self._async_resolve_tariff()

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

    async def _async_resolve_tariff(self) -> ConfigFlowResult:
        auto_id = _only_option_id(_tariff_plan_options())
        if auto_id is not None:
            self._data[CONF_TARIFF_PLAN_ID] = auto_id
            return await self.async_step_pricing()
        return await self.async_step_tariff()

    async def async_step_tariff(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data[CONF_TARIFF_PLAN_ID] = user_input[CONF_TARIFF_PLAN_ID]
            return await self.async_step_pricing()

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

    def _last_period(self) -> PricingPeriod | None:
        existing_periods = [
            PricingPeriod.from_dict(p) for p in self._data.get(CONF_PRICING_PERIODS, [])
        ]
        return existing_periods[-1] if existing_periods else None

    async def async_step_pricing(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Electricity price + network usage fees, one screen, two sections."""
        last_period = self._last_period()

        if user_input is not None:
            existing_periods = [
                PricingPeriod.from_dict(p) for p in self._data.get(CONF_PRICING_PERIODS, [])
            ]
            new_period = _build_pricing_period(
                provider_id=self._data[CONF_PROVIDER_ID],
                distribution_area_id=self._data[CONF_DISTRIBUTION_AREA_ID],
                tariff_plan_id=self._data[CONF_TARIFF_PLAN_ID],
                user_input=_flatten_pricing_input(user_input),
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

        if last_period is not None:
            defaults: dict[str, dict[str, Any]] = {
                SECTION_ELECTRICITY_PRICE: {
                    CONF_QUOTA_KWH_PER_YEAR: last_period.quota_kwh_per_year,
                    CONF_DISCOUNTED_PRICE_FT_PER_KWH: (
                        last_period.price_components.energy_charge_discounted
                    ),
                    CONF_MARKET_PRICE_FT_PER_KWH: last_period.price_components.energy_charge_market,
                },
                SECTION_NETWORK_FEES: {
                    CONF_DISTRIBUTION_CHARGE_FT_PER_KWH: (
                        last_period.price_components.distribution_charge
                    ),
                    CONF_TRANSMISSION_CHARGE_FT_PER_KWH: (
                        last_period.price_components.transmission_charge
                    ),
                    CONF_FIXED_MONTHLY_FEE_FT: last_period.fixed_monthly_fee_ft,
                },
            }
        else:
            defaults = {
                SECTION_ELECTRICITY_PRICE: {
                    CONF_DISCOUNTED_PRICE_FT_PER_KWH: _area_default_discounted_energy_price(
                        self._data.get(CONF_DISTRIBUTION_AREA_ID)
                    )
                }
            }
        return self.async_show_form(
            step_id="pricing",
            data_schema=_pricing_schema(defaults),
            description_placeholders={"price_sheet_url": A1_OFFICIAL_PRICE_SHEET_URL},
        )
