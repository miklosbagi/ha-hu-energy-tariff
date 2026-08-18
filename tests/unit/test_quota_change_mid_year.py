"""A mid-tariff-year change to the annual discounted quota (or the fixed
monthly fee) - made via the options flow, e.g. 2523 -> 3000 kWh - must
only affect days on/after the change. It must NOT retroactively apply
the new rate to days that already elapsed under the old one, even
though those days are still within the same, ongoing tariff year.

This directly exercises the bug found by reasoning through what happens
when a user edits quota/prices without pushing a new integration
version: A1Strategy._eligible_quota_kwh must sum each PricingPeriod's
own prorated share, weighted only by the days it was actually active -
not apply whichever period is active "now" across the whole elapsed
span.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from custom_components.hu_energy_tariffs.models import PriceComponents, PricingPeriod

from tests.unit.factories import make_state


def _period(
    valid_from: datetime, valid_to: datetime | None, quota_kwh_per_year: float
) -> PricingPeriod:
    return PricingPeriod(
        valid_from=valid_from,
        valid_to=valid_to,
        provider_id="mvm_next",
        distribution_area_id="eon",
        tariff_plan_id="mvm_a1",
        quota_kwh_per_year=quota_kwh_per_year,
        fixed_monthly_fee_ft=0.0,
        price_components=PriceComponents(energy_charge_discounted=36.9, energy_charge_market=70.0),
    )


def test_quota_change_mid_year_only_applies_from_the_change_forward(strategy):
    tariff_year_start = date(2026, 8, 1)
    change_at = datetime(2026, 11, 9, tzinfo=timezone.utc)  # 100 days into the tariff year
    now = datetime(2026, 11, 9, tzinfo=timezone.utc) + timedelta(days=50)  # 50 days after the change

    old_period = _period(
        datetime(2020, 1, 1, tzinfo=timezone.utc), change_at, quota_kwh_per_year=2523.0
    )
    new_period = _period(change_at, None, quota_kwh_per_year=3000.0)

    eligible = strategy._eligible_quota_kwh(  # noqa: SLF001
        now, (old_period, new_period), tariff_year_start
    )

    _, end_exclusive = strategy.tariff_year_bounds(now)
    days_in_year = (end_exclusive - tariff_year_start).days
    days_under_old_rate = (change_at.date() - tariff_year_start).days
    days_under_new_rate = (now.date() - change_at.date()).days + 1

    expected_correct = (
        old_period.quota_kwh_per_year * days_under_old_rate / days_in_year
        + new_period.quota_kwh_per_year * days_under_new_rate / days_in_year
    )
    # The bug this test guards against: naively applying the *new*
    # period's quota across the *entire* elapsed span (as if 3000/year
    # had been in effect since Aug 1), rather than only from change_at.
    buggy_value = new_period.quota_kwh_per_year * (
        days_under_old_rate + days_under_new_rate
    ) / days_in_year

    assert eligible == pytest.approx(expected_correct)
    assert eligible < buggy_value - 1.0  # meaningfully different, not a rounding artifact


def test_quota_change_mid_year_does_not_alter_already_billed_history(strategy):
    """Consumption already accumulated/billed before the quota change
    must be untouched by the change - only the *forward* eligible_quota
    (and therefore future pricing) shifts."""
    tariff_year_start = date(2026, 8, 1)
    change_at = datetime(2026, 11, 9, tzinfo=timezone.utc)

    old_period = _period(
        datetime(2020, 1, 1, tzinfo=timezone.utc), change_at, quota_kwh_per_year=2523.0
    )
    new_period = _period(change_at, None, quota_kwh_per_year=3000.0)

    # Consumption already processed and billed under the old period.
    state = make_state(
        tariff_year_start=tariff_year_start,
        last_valid_source_kwh=500.0,
        accumulated_discounted_kwh=400.0,
        accumulated_market_kwh=10.0,
        accumulated_variable_cost_ft=12345.0,
    )
    billed_discounted_before = state.accumulated_discounted_kwh
    billed_market_before = state.accumulated_market_kwh
    billed_cost_before = state.accumulated_variable_cost_ft

    # A zero-delta recalculation right after the quota change (e.g. the
    # options flow's own reload, or the next coordinator tick with no
    # new consumption yet) must not rewrite what was already billed.
    result, new_state = strategy.calculate(
        now=change_at, delta_kwh=0.0, pricing_periods=(old_period, new_period), state=state
    )

    assert new_state.accumulated_discounted_kwh == billed_discounted_before
    assert new_state.accumulated_market_kwh == billed_market_before
    assert new_state.accumulated_variable_cost_ft == billed_cost_before
    assert result.discounted_consumption_kwh == billed_discounted_before
    assert result.variable_cost_ft == billed_cost_before


def test_periods_from_a_previous_tariff_year_do_not_leak_into_this_years_quota(strategy):
    """pricing_periods accumulates every period ever configured, across
    every tariff year - a period wholly inside a *previous* tariff year
    must contribute nothing to this year's eligible_quota."""
    tariff_year_start = date(2026, 8, 1)
    now = datetime(2026, 9, 10, tzinfo=timezone.utc)  # 41 days into this tariff year

    last_years_period = _period(
        datetime(2025, 8, 1, tzinfo=timezone.utc),
        datetime(2026, 8, 1, tzinfo=timezone.utc),
        quota_kwh_per_year=2523.0,
    )
    this_years_period = _period(
        datetime(2026, 8, 1, tzinfo=timezone.utc), None, quota_kwh_per_year=2523.0
    )

    eligible_with_history = strategy._eligible_quota_kwh(  # noqa: SLF001
        now, (last_years_period, this_years_period), tariff_year_start
    )
    eligible_without_history = strategy._eligible_quota_kwh(  # noqa: SLF001
        now, (this_years_period,), tariff_year_start
    )

    assert eligible_with_history == pytest.approx(eligible_without_history)


def test_period_with_no_quota_is_skipped(strategy):
    """A period with quota_kwh_per_year=None (e.g. a future non-quota
    tariff sharing the same pricing-period machinery) contributes
    nothing rather than raising."""
    tariff_year_start = date(2026, 8, 1)
    now = datetime(2026, 9, 10, tzinfo=timezone.utc)

    no_quota_period = PricingPeriod(
        valid_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
        valid_to=None,
        provider_id="mvm_next",
        distribution_area_id="eon",
        tariff_plan_id="mvm_a1",
        quota_kwh_per_year=None,
        fixed_monthly_fee_ft=0.0,
        price_components=PriceComponents(energy_charge_discounted=36.9, energy_charge_market=70.0),
    )

    eligible = strategy._eligible_quota_kwh(now, (no_quota_period,), tariff_year_start)  # noqa: SLF001
    assert eligible == 0.0


def test_fixed_fee_change_mid_gap_only_applies_from_the_change_forward(strategy):
    """Same reasoning as the quota case, but for the fixed monthly fee:
    if several days elapse between coordinator ticks and the fee changed
    partway through that gap, each day must accrue at the fee that was
    actually active *on that day*."""
    tariff_year_start = date(2026, 3, 1)
    change_at = datetime(2026, 3, 4, tzinfo=timezone.utc)  # fee changes after 3 days

    old_period = PricingPeriod(
        valid_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
        valid_to=change_at,
        provider_id="mvm_next",
        distribution_area_id="eon",
        tariff_plan_id="mvm_a1",
        quota_kwh_per_year=2523,
        fixed_monthly_fee_ft=3100.0,  # 100 Ft/day in March
        price_components=PriceComponents(energy_charge_discounted=36.9, energy_charge_market=70.0),
    )
    new_period = PricingPeriod(
        valid_from=change_at,
        valid_to=None,
        provider_id="mvm_next",
        distribution_area_id="eon",
        tariff_plan_id="mvm_a1",
        quota_kwh_per_year=2523,
        fixed_monthly_fee_ft=6200.0,  # 200 Ft/day in March
        price_components=PriceComponents(energy_charge_discounted=36.9, energy_charge_market=70.0),
    )

    state = make_state(
        tariff_year_start=tariff_year_start, fixed_fee_last_accrued_date=date(2026, 3, 1)
    )
    now = datetime(2026, 3, 7, tzinfo=timezone.utc)  # 6 full days elapsed since last accrual

    result, _ = strategy.calculate(
        now=now, delta_kwh=0.0, pricing_periods=(old_period, new_period), state=state
    )

    # 3 days (Mar 1-3) at 100 Ft/day under the old fee, 3 days (Mar 4-6)
    # at 200 Ft/day under the new one - not 6 days at either rate alone.
    assert result.fixed_cost_ft == pytest.approx(3 * 100.0 + 3 * 200.0)
