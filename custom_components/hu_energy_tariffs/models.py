"""Data models for the Hungarian Energy Tariffs integration.

Kept independent from Home Assistant's entity layer so the tariff
calculation logic can be unit tested without booting HA. Provider,
DistributionArea, TariffPlan, PricingPeriod and Meter are separable,
first-class concepts (not string fields on one flat record) so that a
future change to provider/DSO/tariff structure - or a tariff needing a
second, separately-metered stream - does not require redesigning this
module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class MeterRole(StrEnum):
    """Role a metering point plays within a tariff site."""

    MAIN = "main"
    CONTROLLED = "controlled"


class EnergyUnit(StrEnum):
    """Units a source energy sensor may report in."""

    WH = "Wh"
    KWH = "kWh"
    MWH = "MWh"


_UNIT_TO_KWH_FACTOR: dict[str, float] = {
    EnergyUnit.WH: 0.001,
    EnergyUnit.KWH: 1.0,
    EnergyUnit.MWH: 1000.0,
}


def to_kwh(value: float, unit: str) -> float:
    """Normalize an energy value in Wh/kWh/MWh to kWh."""
    try:
        factor = _UNIT_TO_KWH_FACTOR[unit]
    except KeyError as err:
        raise ValueError(f"Unsupported energy unit: {unit!r}") from err
    return value * factor


@dataclass(frozen=True, slots=True)
class Provider:
    """A universal service provider, e.g. MVM Next."""

    id: str
    name: str
    name_hu: str


@dataclass(frozen=True, slots=True)
class DistributionArea:
    """A distribution system operator (DSO) territory, e.g. E.ON."""

    id: str
    name: str


@dataclass(frozen=True, slots=True)
class TariffPlan:
    """Metadata describing a regulated tariff scheme.

    Carries no calculation logic itself. `strategy_key` points into the
    tariff-engine registry (see tariffs/registry.py), decoupling "which
    plan" from "which strategy calculates it".
    """

    id: str
    code: str
    name: str
    name_hu: str
    requires_separate_meter: bool
    strategy_key: str


@dataclass(frozen=True, slots=True)
class PriceComponents:
    """Component-level Ft/kWh pricing.

    The A1 MVP configures `energy_charge_discounted` / `energy_charge_market`
    as simplified all-in gross values (the other components default to 0),
    per the spec's allowance for a simplified first implementation. The
    shape already supports component-level pricing later without changes
    to this class - only config_flow defaults/UI would need to grow.
    """

    energy_charge_discounted: float
    energy_charge_market: float
    transmission_charge: float = 0.0
    distribution_charge: float = 0.0
    other_regulated_charge: float = 0.0
    vat_rate: float = 0.27

    def effective_gross_price(self, *, discounted: bool) -> float:
        """Gross Ft/kWh price applicable to the next unit of energy."""
        energy_charge = (
            self.energy_charge_discounted if discounted else self.energy_charge_market
        )
        net_total = (
            energy_charge
            + self.transmission_charge
            + self.distribution_charge
            + self.other_regulated_charge
        )
        return net_total * (1 + self.vat_rate)


@dataclass(frozen=True, slots=True)
class PricingPeriod:
    """A validity-scoped set of tariff prices/quota.

    A site may hold several of these over time; the engine always
    selects the one whose [valid_from, valid_to) window contains the
    calculation timestamp, so historical accumulated costs are never
    recalculated using newer prices - a price update applies from its
    validity boundary forward only.
    """

    valid_from: datetime
    provider_id: str
    distribution_area_id: str
    tariff_plan_id: str
    price_components: PriceComponents
    fixed_monthly_fee_ft: float
    quota_kwh_per_year: float | None = None
    valid_to: datetime | None = None

    def covers(self, timestamp: datetime) -> bool:
        if timestamp < self.valid_from:
            return False
        if self.valid_to is not None and timestamp >= self.valid_to:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "valid_from": self.valid_from.isoformat(),
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "provider_id": self.provider_id,
            "distribution_area_id": self.distribution_area_id,
            "tariff_plan_id": self.tariff_plan_id,
            "quota_kwh_per_year": self.quota_kwh_per_year,
            "fixed_monthly_fee_ft": self.fixed_monthly_fee_ft,
            "price_components": {
                "energy_charge_discounted": self.price_components.energy_charge_discounted,
                "energy_charge_market": self.price_components.energy_charge_market,
                "transmission_charge": self.price_components.transmission_charge,
                "distribution_charge": self.price_components.distribution_charge,
                "other_regulated_charge": self.price_components.other_regulated_charge,
                "vat_rate": self.price_components.vat_rate,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> PricingPeriod:
        return cls(
            valid_from=datetime.fromisoformat(data["valid_from"]),
            valid_to=(
                datetime.fromisoformat(data["valid_to"]) if data.get("valid_to") else None
            ),
            provider_id=data["provider_id"],
            distribution_area_id=data["distribution_area_id"],
            tariff_plan_id=data["tariff_plan_id"],
            quota_kwh_per_year=data.get("quota_kwh_per_year"),
            fixed_monthly_fee_ft=data["fixed_monthly_fee_ft"],
            price_components=PriceComponents(**data["price_components"]),
        )


@dataclass(frozen=True, slots=True)
class Meter:
    """A metering point feeding one tariff calculation stream."""

    id: str
    source_entity_id: str
    role: MeterRole = MeterRole.MAIN
    unit: str | None = None


@dataclass(frozen=True, slots=True)
class TariffSiteConfig:
    """Resolved config-entry payload.

    Stores only ids into the static Provider/DistributionArea/TariffPlan
    catalogs - never duplicates catalog data - so catalog updates never
    require migrating existing config entries. `meters` is a tuple from
    day one even though the A1 MVP only ever populates one: this is the
    concrete mechanism that lets a future tariff (B/H) add a second,
    separately-metered "controlled" stream with no data-shape migration.
    """

    name: str
    meters: tuple[Meter, ...]
    provider_id: str
    distribution_area_id: str
    tariff_plan_id: str
    pricing_periods: tuple[PricingPeriod, ...]

    def pricing_period_for(self, timestamp: datetime) -> PricingPeriod:
        candidates = [p for p in self.pricing_periods if p.covers(timestamp)]
        if candidates:
            return max(candidates, key=lambda p: p.valid_from)
        # Normal case: `timestamp` is beyond the last configured
        # valid_to (or there's a gap) - fall back to the most recent
        # period rather than raising, so a coordinator tick never fails
        # outright because of a config edit race.
        return max(self.pricing_periods, key=lambda p: p.valid_from)


@dataclass(frozen=True, slots=True)
class TariffResult:
    """Engine output for one calculation tick.

    All consumption/cost fields are cumulative within the current
    tariff year; sensors read these fields directly as their state.
    """

    timestamp: datetime
    current_price: float
    total_consumption_kwh: float
    discounted_consumption_kwh: float
    market_consumption_kwh: float
    discounted_quota_kwh: float
    quota_used_kwh: float
    quota_remaining_kwh: float
    variable_cost_ft: float
    fixed_cost_ft: float
    total_cost_ft: float


@dataclass(slots=True)
class PersistedMeterState:
    """Mutable, `Store`-persisted per-meter accumulator.

    Replaced wholesale (not mutated field-by-field in place) by
    TariffStrategy.calculate() on each update, so it plays well with
    Store serialization and avoids partial-mutation bugs.
    """

    schema_version: int
    meter_id: str
    tariff_year_start: date
    source_baseline_kwh: float
    last_valid_source_kwh: float
    accumulated_discounted_kwh: float = 0.0
    accumulated_market_kwh: float = 0.0
    accumulated_variable_cost_ft: float = 0.0
    accumulated_fixed_cost_ft: float = 0.0
    fixed_fee_last_accrued_date: date | None = None
    last_processed_timestamp: datetime | None = None
    consecutive_invalid_reads: int = 0
    pending_suspect_reading_kwh: float | None = None
    pending_suspect_reading_count: int = 0

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "meter_id": self.meter_id,
            "tariff_year_start": self.tariff_year_start.isoformat(),
            "source_baseline_kwh": self.source_baseline_kwh,
            "last_valid_source_kwh": self.last_valid_source_kwh,
            "accumulated_discounted_kwh": self.accumulated_discounted_kwh,
            "accumulated_market_kwh": self.accumulated_market_kwh,
            "accumulated_variable_cost_ft": self.accumulated_variable_cost_ft,
            "accumulated_fixed_cost_ft": self.accumulated_fixed_cost_ft,
            "fixed_fee_last_accrued_date": (
                self.fixed_fee_last_accrued_date.isoformat()
                if self.fixed_fee_last_accrued_date
                else None
            ),
            "last_processed_timestamp": (
                self.last_processed_timestamp.isoformat()
                if self.last_processed_timestamp
                else None
            ),
            "consecutive_invalid_reads": self.consecutive_invalid_reads,
            "pending_suspect_reading_kwh": self.pending_suspect_reading_kwh,
            "pending_suspect_reading_count": self.pending_suspect_reading_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PersistedMeterState:
        return cls(
            schema_version=data["schema_version"],
            meter_id=data["meter_id"],
            tariff_year_start=date.fromisoformat(data["tariff_year_start"]),
            source_baseline_kwh=data["source_baseline_kwh"],
            last_valid_source_kwh=data["last_valid_source_kwh"],
            accumulated_discounted_kwh=data.get("accumulated_discounted_kwh", 0.0),
            accumulated_market_kwh=data.get("accumulated_market_kwh", 0.0),
            accumulated_variable_cost_ft=data.get("accumulated_variable_cost_ft", 0.0),
            accumulated_fixed_cost_ft=data.get("accumulated_fixed_cost_ft", 0.0),
            fixed_fee_last_accrued_date=(
                date.fromisoformat(data["fixed_fee_last_accrued_date"])
                if data.get("fixed_fee_last_accrued_date")
                else None
            ),
            last_processed_timestamp=(
                datetime.fromisoformat(data["last_processed_timestamp"])
                if data.get("last_processed_timestamp")
                else None
            ),
            consecutive_invalid_reads=data.get("consecutive_invalid_reads", 0),
            pending_suspect_reading_kwh=data.get("pending_suspect_reading_kwh"),
            pending_suspect_reading_count=data.get("pending_suspect_reading_count", 0),
        )
