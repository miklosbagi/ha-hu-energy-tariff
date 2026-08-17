"""A1: consumption fully within the discounted quota is priced entirely
at the discounted rate."""
from __future__ import annotations

from datetime import date

from tests.unit.factories import make_state


def test_quota_within(now, a1_pricing_period, strategy):
    state = make_state(tariff_year_start=date(2025, 8, 1), last_valid_source_kwh=100.0)

    result, new_state = strategy.calculate(
        now=now, delta_kwh=5.0, pricing_period=a1_pricing_period, state=state
    )

    assert result.discounted_consumption_kwh == 5.0
    assert result.market_consumption_kwh == 0.0
    assert new_state.accumulated_market_kwh == 0.0

    expected_price = a1_pricing_period.price_components.effective_gross_price(discounted=True)
    assert result.variable_cost_ft == 5.0 * expected_price
    assert result.current_price == expected_price
