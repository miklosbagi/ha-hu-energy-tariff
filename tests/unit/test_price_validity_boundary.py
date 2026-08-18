"""Price change at a valid_from boundary: the engine must select the
pricing period whose window contains the timestamp, never applying a
newer price to consumption that happened before the change."""
from __future__ import annotations

from datetime import datetime, timezone

from custom_components.hu_energy_tariffs.models import (
    Meter,
    MeterRole,
    PriceComponents,
    PricingPeriod,
    TariffSiteConfig,
)


def _period(valid_from: datetime, valid_to: datetime | None, price: float) -> PricingPeriod:
    return PricingPeriod(
        valid_from=valid_from,
        valid_to=valid_to,
        provider_id="mvm_next",
        distribution_area_id="eon",
        tariff_plan_id="mvm_a1",
        quota_kwh_per_year=2523,
        fixed_monthly_fee_ft=0.0,
        price_components=PriceComponents(
            energy_charge_discounted=price, energy_charge_market=price * 2
        ),
    )


def test_price_validity_boundary():
    change_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
    old_period = _period(datetime(2020, 1, 1, tzinfo=timezone.utc), change_at, 30.0)
    new_period = _period(change_at, None, 40.0)

    meter = Meter(id="main", source_entity_id="sensor.test", role=MeterRole.MAIN)
    site = TariffSiteConfig(
        name="test",
        meters=(meter,),
        provider_id="mvm_next",
        distribution_area_id="eon",
        tariff_plan_id="mvm_a1",
        pricing_periods=(old_period, new_period),
    )

    before = datetime(2026, 5, 31, 23, 59, tzinfo=timezone.utc)
    after = datetime(2026, 6, 2, tzinfo=timezone.utc)

    assert site.pricing_period_for(before) is old_period
    assert site.pricing_period_for(change_at) is new_period
    assert site.pricing_period_for(after) is new_period
