"""A1: a single delta that crosses the remaining-quota boundary is split
between discounted and market price, per the spec's worked example
(2.0 kWh delta, 0.7 kWh remaining quota -> 0.7 discounted + 1.3 market).
"""
from __future__ import annotations

from datetime import date

import pytest

from tests.unit.factories import make_state


def test_quota_boundary_split(now, a1_pricing_period, strategy):
    tariff_year_start = date(2025, 8, 1)
    eligible_quota = strategy._eligible_quota_kwh(  # noqa: SLF001
        now, (a1_pricing_period,), tariff_year_start
    )
    state = make_state(
        tariff_year_start=tariff_year_start,
        last_valid_source_kwh=1000.0,
        accumulated_discounted_kwh=eligible_quota - 0.7,
    )

    result, new_state = strategy.calculate(
        now=now, delta_kwh=2.0, pricing_periods=(a1_pricing_period,), state=state
    )

    discounted_added = new_state.accumulated_discounted_kwh - state.accumulated_discounted_kwh
    market_added = new_state.accumulated_market_kwh - state.accumulated_market_kwh

    assert discounted_added == pytest.approx(0.7)
    assert market_added == pytest.approx(1.3)

    discounted_price = a1_pricing_period.price_components.effective_gross_price(discounted=True)
    market_price = a1_pricing_period.price_components.effective_gross_price(discounted=False)
    expected_cost = 0.7 * discounted_price + 1.3 * market_price
    assert result.variable_cost_ft == pytest.approx(expected_cost)
