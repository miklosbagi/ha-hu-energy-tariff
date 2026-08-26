"""Pure backfill logic - no Home Assistant boot needed. See
test_backfill_recorder.py for the Recorder-coupled async_fetch_daily_deltas
tests."""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from custom_components.hu_energy_tariff.backfill import backfill_start_date, replay_deltas
from custom_components.hu_energy_tariff.models import PriceComponents, PricingPeriod
from tests.unit.factories import make_state


class TestBackfillStartDate:
    def test_caps_at_tariff_year_start_when_installing_aug_to_dec(self):
        # 15 Nov falls in the 1 Aug 2026 - 31 Jul 2027 tariff year; 1 Jan
        # 2026 belongs to a *different*, earlier tariff year and must
        # not bind.
        result = backfill_start_date(
            tariff_year_start=date(2026, 8, 1), today=date(2026, 11, 15)
        )
        assert result == date(2026, 8, 1)

    def test_caps_at_calendar_year_start_when_installing_jan_to_jul(self):
        # 15 Mar falls in the 1 Aug 2025 - 31 Jul 2026 tariff year; the
        # calendar-year cap (1 Jan 2026) is later/tighter, so it wins.
        result = backfill_start_date(
            tariff_year_start=date(2025, 8, 1), today=date(2026, 3, 15)
        )
        assert result == date(2026, 1, 1)

    def test_installing_exactly_on_tariff_year_start(self):
        result = backfill_start_date(
            tariff_year_start=date(2026, 8, 1), today=date(2026, 8, 1)
        )
        assert result == date(2026, 8, 1)


def _period(valid_from: date) -> PricingPeriod:
    return PricingPeriod(
        valid_from=datetime.combine(valid_from, time.min, tzinfo=UTC),
        valid_to=None,
        provider_id="mvm_next",
        distribution_area_id="eon",
        tariff_plan_id="mvm_a1",
        quota_kwh_per_year=2523,
        fixed_monthly_fee_ft=3100.0,  # 100.0 Ft/day net in August (31 days)
        price_components=PriceComponents(energy_charge_discounted=36.9, energy_charge_market=70.0),
    )


class TestReplayDeltas:
    def test_matches_a_manual_sequence_of_live_calculate_calls(self, strategy):
        """The whole point of replay_deltas is that a backfilled day is
        priced identically to a live one - assert that directly, rather
        than hand-computing expected totals."""
        start = date(2026, 8, 1)
        end = date(2026, 8, 4)  # 3 days: Aug 1, 2 (gap, no data), 3
        period = _period(start)
        daily_deltas = {date(2026, 8, 1): 10.0, date(2026, 8, 3): 5.0}

        seed = make_state(tariff_year_start=start, fixed_fee_last_accrued_date=start)
        result = replay_deltas(
            strategy=strategy,
            pricing_periods=(period,),
            start=start,
            end=end,
            daily_deltas=daily_deltas,
            initial_state=seed,
        )

        # Manually replay the exact same days (a gap day counts as a
        # real 0 kWh delta, same as replay_deltas does internally).
        expected_state = make_state(tariff_year_start=start, fixed_fee_last_accrued_date=start)
        one_day = timedelta(days=1)
        for day, delta in [
            (date(2026, 8, 1), 10.0),
            (date(2026, 8, 2), 0.0),
            (date(2026, 8, 3), 5.0),
        ]:
            now = datetime.combine(day + one_day, time.min, tzinfo=UTC)
            _, expected_state = strategy.calculate(
                now=now, delta_kwh=delta, pricing_periods=(period,), state=expected_state
            )

        assert result.accumulated_discounted_kwh == expected_state.accumulated_discounted_kwh
        assert result.accumulated_market_kwh == expected_state.accumulated_market_kwh
        assert result.accumulated_variable_cost_ft == expected_state.accumulated_variable_cost_ft
        assert result.accumulated_fixed_cost_ft == expected_state.accumulated_fixed_cost_ft
        assert result.fixed_fee_last_accrued_date == expected_state.fixed_fee_last_accrued_date
        # Total historical consumption landed somewhere (split across
        # discounted/market), never silently dropped.
        assert result.accumulated_discounted_kwh + result.accumulated_market_kwh == 15.0

    def test_gap_day_still_accrues_the_fixed_fee(self, strategy):
        """A day Recorder has no data for is a real 0 kWh day, not a
        skipped one - the fixed fee accrues regardless of consumption."""
        start = date(2026, 8, 1)
        end = date(2026, 8, 3)  # 2 days, no consumption data at all
        period = _period(start)

        seed = make_state(tariff_year_start=start, fixed_fee_last_accrued_date=start)
        result = replay_deltas(
            strategy=strategy,
            pricing_periods=(period,),
            start=start,
            end=end,
            daily_deltas={},
            initial_state=seed,
        )

        assert result.accumulated_discounted_kwh == 0.0
        assert result.accumulated_market_kwh == 0.0
        # 2 days * 100.0 Ft/day net * 1.27 VAT = 254.0 Ft gross.
        assert result.accumulated_fixed_cost_ft == 254.0
        assert result.fixed_fee_last_accrued_date == end

    def test_deltas_outside_the_range_are_ignored(self, strategy):
        start = date(2026, 8, 2)
        end = date(2026, 8, 3)
        period = _period(date(2026, 8, 1))

        seed = make_state(tariff_year_start=date(2026, 8, 1), fixed_fee_last_accrued_date=start)
        result = replay_deltas(
            strategy=strategy,
            pricing_periods=(period,),
            start=start,
            end=end,
            daily_deltas={date(2026, 8, 1): 999.0, date(2026, 8, 2): 3.0},
            initial_state=seed,
        )

        assert result.accumulated_discounted_kwh + result.accumulated_market_kwh == 3.0
