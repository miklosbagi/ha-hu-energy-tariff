"""A1: consumption fully above the currently available discounted quota
is priced entirely at market rate."""
from __future__ import annotations

from datetime import date

from tests.unit.factories import make_state


def test_quota_exceeded(now, a1_pricing_period, strategy):
    state = make_state(
        tariff_year_start=date(2025, 8, 1),
        last_valid_source_kwh=5000.0,
        # Already at/above the full annual quota for this tariff year.
        accumulated_discounted_kwh=2523.0,
    )

    result, new_state = strategy.calculate(
        now=now, delta_kwh=10.0, pricing_period=a1_pricing_period, state=state
    )

    assert result.discounted_consumption_kwh == 2523.0
    assert result.market_consumption_kwh == 10.0
    assert new_state.accumulated_discounted_kwh == 2523.0

    expected_price = a1_pricing_period.price_components.effective_gross_price(discounted=False)
    assert result.current_price == expected_price
