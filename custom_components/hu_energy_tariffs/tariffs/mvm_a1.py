"""A1: residential flat-rate tariff with a prorated annual discount quota.

Discounted quota: 2523 kWh / tariff year / metering point (default,
configurable). Tariff year: 1 Aug - 31 Jul. The eligible quota at any
point in time is prorated by elapsed days within the tariff year, so a
single consumption delta that crosses the remaining-quota boundary is
split between discounted and market price rather than priced as a whole
at one rate (see the spec's 2.0 kWh delta / 0.7 kWh remaining example,
reproduced in tests/unit/test_quota_boundary_split.py).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from ..models import PersistedMeterState, PricingPeriod, TariffPlan, TariffResult, select_pricing_period
from ..tariff_engine import TariffStrategy
from .registry import register, register_tariff_plan

register_tariff_plan(
    TariffPlan(
        id="mvm_a1",
        code="A1",
        name="A1 (flat rate, discounted quota)",
        name_hu="A1 (egyzónás, kedvezményes kerettel)",
        requires_separate_meter=False,
        strategy_key="mvm_a1",
    )
)


def _tariff_year_start_for(when: date) -> date:
    """1 Aug of the tariff year containing `when`."""
    if when.month >= 8:
        return date(when.year, 8, 1)
    return date(when.year - 1, 8, 1)


def _tariff_year_end_exclusive(start: date) -> date:
    """1 Aug of the following year (exclusive upper bound).

    Naturally yields a 365- or 366-day window depending on whether the
    second calendar year (which contains February) is a leap year.
    """
    return date(start.year + 1, 8, 1)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return (next_month - date(year, month, 1)).days


@register
class A1Strategy(TariffStrategy):
    strategy_key = "mvm_a1"

    def tariff_year_bounds(self, now: datetime) -> tuple[date, date]:
        start = _tariff_year_start_for(now.date())
        return start, _tariff_year_end_exclusive(start)

    def _eligible_quota_kwh(
        self,
        now: datetime,
        pricing_periods: tuple[PricingPeriod, ...],
        tariff_year_start: date,
    ) -> float:
        """Sum each pricing period's own prorated share of the annual
        quota, weighted only by the days (within the current tariff
        year, through today) that period was actually active.

        Must NOT simply apply the currently-active period's
        quota_kwh_per_year across the whole elapsed span: if the annual
        quota changes mid-tariff-year (e.g. 2523 -> 3000 kWh via the
        options flow), only days on/after the change should accrue at
        the new rate - days before it already accrued at the old rate,
        and that accrual must not change retroactively. Reduces exactly
        to the single-period elapsed-days formula when only one period
        has ever been configured.
        """
        _, end_exclusive = self.tariff_year_bounds(now)
        days_in_tariff_year = (end_exclusive - tariff_year_start).days
        range_end = now.date()

        total = 0.0
        for period in pricing_periods:
            if period.quota_kwh_per_year is None:
                continue
            period_start = max(period.valid_from.date(), tariff_year_start)
            period_end_exclusive = (
                period.valid_to.date() if period.valid_to else range_end + timedelta(days=1)
            )
            period_last_day = min(period_end_exclusive - timedelta(days=1), range_end)
            if period_last_day < period_start:
                continue
            days_active = (period_last_day - period_start).days + 1
            total += period.quota_kwh_per_year * days_active / days_in_tariff_year
        return total

    def calculate(
        self,
        *,
        now: datetime,
        delta_kwh: float,
        pricing_periods: tuple[PricingPeriod, ...],
        state: PersistedMeterState,
    ) -> tuple[TariffResult, PersistedMeterState]:
        active_period = select_pricing_period(pricing_periods, now)
        eligible_quota = self._eligible_quota_kwh(now, pricing_periods, state.tariff_year_start)

        remaining_quota = max(0.0, eligible_quota - state.accumulated_discounted_kwh)
        discounted_delta = max(0.0, min(delta_kwh, remaining_quota))
        market_delta = max(0.0, delta_kwh - discounted_delta)

        price_components = active_period.price_components
        discounted_price = price_components.effective_gross_price(discounted=True)
        market_price = price_components.effective_gross_price(discounted=False)

        variable_cost_delta = (
            discounted_delta * discounted_price + market_delta * market_price
        )

        new_accumulated_discounted = state.accumulated_discounted_kwh + discounted_delta
        new_accumulated_market = state.accumulated_market_kwh + market_delta
        new_variable_cost = state.accumulated_variable_cost_ft + variable_cost_delta

        new_fixed_cost, new_fee_accrued_date = self._accrue_fixed_fee(
            now, pricing_periods, state
        )

        remaining_quota_after = max(0.0, eligible_quota - new_accumulated_discounted)
        # Price applicable to the *next* increment of consumption - this
        # is what's exposed as the Energy Dashboard current-price entity.
        current_price = discounted_price if remaining_quota_after > 0 else market_price

        total_consumption = new_accumulated_discounted + new_accumulated_market
        total_cost = new_variable_cost + new_fixed_cost

        result = TariffResult(
            timestamp=now,
            current_price=current_price,
            total_consumption_kwh=total_consumption,
            discounted_consumption_kwh=new_accumulated_discounted,
            market_consumption_kwh=new_accumulated_market,
            discounted_quota_kwh=eligible_quota,
            quota_used_kwh=new_accumulated_discounted,
            quota_remaining_kwh=remaining_quota_after,
            variable_cost_ft=new_variable_cost,
            fixed_cost_ft=new_fixed_cost,
            total_cost_ft=total_cost,
        )

        new_state = PersistedMeterState(
            schema_version=state.schema_version,
            meter_id=state.meter_id,
            tariff_year_start=state.tariff_year_start,
            source_baseline_kwh=state.source_baseline_kwh,
            last_valid_source_kwh=state.last_valid_source_kwh,
            accumulated_discounted_kwh=new_accumulated_discounted,
            accumulated_market_kwh=new_accumulated_market,
            accumulated_variable_cost_ft=new_variable_cost,
            accumulated_fixed_cost_ft=new_fixed_cost,
            fixed_fee_last_accrued_date=new_fee_accrued_date,
            last_processed_timestamp=now,
            consecutive_invalid_reads=0,
            pending_suspect_reading_kwh=None,
            pending_suspect_reading_count=0,
        )

        return result, new_state

    @staticmethod
    def _accrue_fixed_fee(
        now: datetime, pricing_periods: tuple[PricingPeriod, ...], state: PersistedMeterState
    ) -> tuple[float, date]:
        """Accrue the fixed monthly fee daily, pro-rata, for a smoothly
        moving cost figure rather than a once-a-month jump. A day is only
        accrued once it has fully elapsed, so this is idempotent when
        called more than once on the same day.

        Each day is accrued at whichever period was active *on that day*
        (not today's active period applied across the whole gap) - same
        reasoning as the quota proration above: a fee change must not
        retroactively apply to days before it took effect.
        """
        last_accrued = state.fixed_fee_last_accrued_date or state.tariff_year_start
        accumulated = state.accumulated_fixed_cost_ft
        current_date = last_accrued
        one_day = timedelta(days=1)
        while current_date < now.date():
            day_period = select_pricing_period(
                pricing_periods, datetime.combine(current_date, time.min, tzinfo=now.tzinfo)
            )
            days_in_month = _days_in_month(current_date.year, current_date.month)
            accumulated += day_period.fixed_monthly_fee_ft / days_in_month
            current_date = current_date + one_day
        return accumulated, current_date
