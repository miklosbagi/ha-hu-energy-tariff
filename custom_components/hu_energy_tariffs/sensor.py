"""Sensor entities for hu_energy_tariffs.

Every entity is a thin read of one TariffResult field off the
coordinator - all calculation happens in tariff_engine.py/coordinator.py,
never here.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HuEnergyTariffsRuntimeData
from .const import DOMAIN
from .coordinator import HuEnergyTariffsCoordinator
from .models import TariffResult

CURRENCY_HUF = "HUF"
UNIT_HUF_PER_KWH = "HUF/kWh"
UNIT_KWH = "kWh"


@dataclass(frozen=True, kw_only=True)
class HuEnergyTariffsSensorDescription(SensorEntityDescription):
    value_fn: Callable[[TariffResult], float] = lambda result: 0.0


SENSOR_DESCRIPTIONS: tuple[HuEnergyTariffsSensorDescription, ...] = (
    HuEnergyTariffsSensorDescription(
        key="current_price",
        translation_key="current_price",
        native_unit_of_measurement=UNIT_HUF_PER_KWH,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda result: result.current_price,
    ),
    HuEnergyTariffsSensorDescription(
        key="total_consumption",
        translation_key="total_consumption",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UNIT_KWH,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda result: result.total_consumption_kwh,
    ),
    HuEnergyTariffsSensorDescription(
        key="discounted_consumption",
        translation_key="discounted_consumption",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UNIT_KWH,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda result: result.discounted_consumption_kwh,
    ),
    HuEnergyTariffsSensorDescription(
        key="market_consumption",
        translation_key="market_consumption",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UNIT_KWH,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda result: result.market_consumption_kwh,
    ),
    HuEnergyTariffsSensorDescription(
        key="discounted_quota",
        translation_key="discounted_quota",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UNIT_KWH,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda result: result.discounted_quota_kwh,
    ),
    HuEnergyTariffsSensorDescription(
        key="remaining_discounted_quota",
        translation_key="remaining_discounted_quota",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UNIT_KWH,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda result: result.quota_remaining_kwh,
    ),
    HuEnergyTariffsSensorDescription(
        key="variable_cost",
        translation_key="variable_cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_HUF,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda result: result.variable_cost_ft,
    ),
    HuEnergyTariffsSensorDescription(
        key="fixed_cost",
        translation_key="fixed_cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_HUF,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda result: result.fixed_cost_ft,
    ),
    HuEnergyTariffsSensorDescription(
        key="total_cost",
        translation_key="total_cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_HUF,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda result: result.total_cost_ft,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime_data: HuEnergyTariffsRuntimeData = entry.runtime_data
    # Multiple meters (future B/H "controlled" stream) share one site name -
    # disambiguate the device name by meter role only when there's more
    # than one, so the common single-meter (A1) case stays clean.
    multi_meter = len(runtime_data.coordinators) > 1
    entities: list[HuEnergyTariffsSensor] = [
        HuEnergyTariffsSensor(
            coordinator, description, entry.entry_id, runtime_data.site.name, multi_meter
        )
        for coordinator in runtime_data.coordinators
        for description in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class HuEnergyTariffsSensor(CoordinatorEntity[HuEnergyTariffsCoordinator], SensorEntity):
    """A single TariffResult field, exposed as a sensor.

    Persistence lives entirely in the coordinator's Store - this entity
    holds no state of its own beyond what it reads from coordinator.data.
    """

    entity_description: HuEnergyTariffsSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HuEnergyTariffsCoordinator,
        description: HuEnergyTariffsSensorDescription,
        entry_id: str,
        site_name: str,
        multi_meter: bool,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        meter_id = coordinator.meter.id
        self._attr_unique_id = f"{entry_id}_{meter_id}_{description.key}"
        device_name = f"{site_name} ({meter_id})" if multi_meter else site_name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{meter_id}")},
            name=device_name,
            manufacturer="Hungarian Energy Tariffs",
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
