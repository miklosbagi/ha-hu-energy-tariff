"""Aug 1 tariff-year transition: verify the boundary date and that the
coordinator rolls over accumulated state at the correct instant, without
touching the underlying cumulative source-meter tracking fields.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from custom_components.hu_energy_tariffs.models import TariffSiteConfig

from tests.unit.factories import make_bare_coordinator, make_state


def test_tariff_year_bounds_before_and_after_aug1(strategy):
    before = datetime(2026, 7, 31, 23, 59, tzinfo=timezone.utc)
    after = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)

    start_before, end_before = strategy.tariff_year_bounds(before)
    start_after, end_after = strategy.tariff_year_bounds(after)

    assert start_before == date(2025, 8, 1)
    assert end_before == date(2026, 8, 1)
    assert start_after == date(2026, 8, 1)
    assert end_after == date(2027, 8, 1)


def test_coordinator_rolls_over_on_aug1(meter):
    site = TariffSiteConfig(
        name="test",
        meters=(meter,),
        provider_id="mvm_next",
        distribution_area_id="eon",
        tariff_plan_id="mvm_a1",
        pricing_periods=(),
    )
    coordinator = make_bare_coordinator(meter=meter, site=site)
    coordinator._state = make_state(  # noqa: SLF001
        tariff_year_start=date(2025, 8, 1),
        last_valid_source_kwh=5000.0,
        accumulated_discounted_kwh=1000.0,
        accumulated_market_kwh=200.0,
        accumulated_variable_cost_ft=50000.0,
        accumulated_fixed_cost_ft=3000.0,
    )

    coordinator._maybe_roll_tariff_year(datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc))  # noqa: SLF001

    state = coordinator._state  # noqa: SLF001
    assert state.tariff_year_start == date(2026, 8, 1)
    assert state.accumulated_discounted_kwh == 0.0
    assert state.accumulated_market_kwh == 0.0
    assert state.accumulated_variable_cost_ft == 0.0
    assert state.accumulated_fixed_cost_ft == 0.0
    # The underlying cumulative meter reading is untouched by rollover.
    assert state.last_valid_source_kwh == 5000.0
