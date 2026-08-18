"""The Hungarian Energy Tariffs integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import tariffs  # noqa: F401  (import for registration side effects)
from .const import (
    CONF_DISTRIBUTION_AREA_ID,
    CONF_PRICING_PERIODS,
    CONF_PROVIDER_ID,
    CONF_SOURCE_ENTITY_ID,
    CONF_TARIFF_PLAN_ID,
    PLATFORMS,
)
from .coordinator import HuEnergyTariffsCoordinator
from .models import Meter, MeterRole, PricingPeriod, TariffSiteConfig
from .tariffs.registry import get_strategy, get_tariff_plan

_LOGGER = logging.getLogger(__name__)


class HuEnergyTariffsRuntimeData:
    """Runtime data attached to the config entry."""

    def __init__(
        self, site: TariffSiteConfig, coordinators: list[HuEnergyTariffsCoordinator]
    ) -> None:
        self.site = site
        self.coordinators = coordinators


def _build_site_config(entry: ConfigEntry) -> TariffSiteConfig:
    data = entry.data
    meter = Meter(id="main", source_entity_id=data[CONF_SOURCE_ENTITY_ID], role=MeterRole.MAIN)
    pricing_periods = tuple(
        PricingPeriod.from_dict(period) for period in data[CONF_PRICING_PERIODS]
    )
    return TariffSiteConfig(
        name=entry.title,
        meters=(meter,),
        provider_id=data[CONF_PROVIDER_ID],
        distribution_area_id=data[CONF_DISTRIBUTION_AREA_ID],
        tariff_plan_id=data[CONF_TARIFF_PLAN_ID],
        pricing_periods=pricing_periods,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    site = _build_site_config(entry)
    tariff_plan = get_tariff_plan(site.tariff_plan_id)
    strategy = get_strategy(tariff_plan.strategy_key)

    coordinators: list[HuEnergyTariffsCoordinator] = []
    for meter in site.meters:
        coordinator = HuEnergyTariffsCoordinator(
            hass, entry_id=entry.entry_id, site=site, meter=meter, strategy=strategy
        )
        await coordinator.async_setup()
        coordinators.append(coordinator)

    entry.runtime_data = HuEnergyTariffsRuntimeData(site=site, coordinators=coordinators)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime_data: HuEnergyTariffsRuntimeData = entry.runtime_data
        for coordinator in runtime_data.coordinators:
            await coordinator.async_unload()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
