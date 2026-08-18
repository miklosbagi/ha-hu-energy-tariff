"""Test-only helpers for constructing model/coordinator fixtures without
needing a running Home Assistant instance.
"""
from __future__ import annotations

from datetime import date

from custom_components.hu_energy_tariffs.coordinator import HuEnergyTariffsCoordinator
from custom_components.hu_energy_tariffs.models import Meter, PersistedMeterState, TariffSiteConfig
from custom_components.hu_energy_tariffs.tariffs.mvm_a1 import A1Strategy


def make_state(
    *,
    tariff_year_start: date,
    last_valid_source_kwh: float = 0.0,
    source_baseline_kwh: float = 0.0,
    accumulated_discounted_kwh: float = 0.0,
    accumulated_market_kwh: float = 0.0,
    accumulated_variable_cost_ft: float = 0.0,
    accumulated_fixed_cost_ft: float = 0.0,
    fixed_fee_last_accrued_date: date | None = None,
) -> PersistedMeterState:
    return PersistedMeterState(
        schema_version=1,
        meter_id="main",
        tariff_year_start=tariff_year_start,
        source_baseline_kwh=source_baseline_kwh,
        last_valid_source_kwh=last_valid_source_kwh,
        accumulated_discounted_kwh=accumulated_discounted_kwh,
        accumulated_market_kwh=accumulated_market_kwh,
        accumulated_variable_cost_ft=accumulated_variable_cost_ft,
        accumulated_fixed_cost_ft=accumulated_fixed_cost_ft,
        fixed_fee_last_accrued_date=fixed_fee_last_accrued_date or tariff_year_start,
    )


def make_bare_coordinator(*, meter: Meter, site: TariffSiteConfig) -> HuEnergyTariffsCoordinator:
    """Construct a coordinator without running __init__ (which requires a
    real HomeAssistant instance) - used to unit test the pure
    reset-detection / rollover logic in isolation.
    """
    coordinator = HuEnergyTariffsCoordinator.__new__(HuEnergyTariffsCoordinator)
    coordinator._site = site  # noqa: SLF001
    coordinator._meter = meter  # noqa: SLF001
    coordinator._strategy = A1Strategy()  # noqa: SLF001
    coordinator._state = None  # noqa: SLF001
    return coordinator
