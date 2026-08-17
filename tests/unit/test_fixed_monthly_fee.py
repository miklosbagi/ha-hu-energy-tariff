"""Fixed monthly fee accrues daily, pro-rata, rather than as a lump sum
on a single day of the month - so total_cost moves smoothly."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from custom_components.hu_energy_tariffs.models import PriceComponents, PricingPeriod

from tests.unit.factories import make_state


def _pricing_period(fixed_monthly_fee_ft: float) -> PricingPeriod:
    return PricingPeriod(
        valid_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
        valid_to=None,
        provider_id="mvm_next",
        distribution_area_id="eon",
        tariff_plan_id="mvm_a1",
        quota_kwh_per_year=2523,
        fixed_monthly_fee_ft=fixed_monthly_fee_ft,
        price_components=PriceComponents(energy_charge_discounted=36.9, energy_charge_market=70.0),
    )


def test_fixed_fee_accrues_pro_rata_daily(strategy):
    tariff_year_start = date(2026, 3, 1)  # March has 31 days
    pricing_period = _pricing_period(fixed_monthly_fee_ft=3100.0)  # 100 Ft/day in March
    state = make_state(
        tariff_year_start=tariff_year_start,
        fixed_fee_last_accrued_date=date(2026, 3, 1),
    )

    now = datetime(2026, 3, 6, 12, 0, tzinfo=timezone.utc)  # 5 full days elapsed
    result, new_state = strategy.calculate(
        now=now, delta_kwh=0.0, pricing_period=pricing_period, state=state
    )

    assert result.fixed_cost_ft == pytest.approx(500.0)
    assert new_state.fixed_fee_last_accrued_date == date(2026, 3, 6)


def test_fixed_fee_accrual_is_idempotent_within_the_same_day(strategy):
    pricing_period = _pricing_period(fixed_monthly_fee_ft=3100.0)
    state = make_state(
        tariff_year_start=date(2026, 3, 1), fixed_fee_last_accrued_date=date(2026, 3, 6)
    )

    now = datetime(2026, 3, 6, 18, 0, tzinfo=timezone.utc)
    result, _ = strategy.calculate(
        now=now, delta_kwh=0.0, pricing_period=pricing_period, state=state
    )

    assert result.fixed_cost_ft == pytest.approx(0.0)
