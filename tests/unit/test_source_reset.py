"""A cumulative source meter reset (drop to ~0) must not be interpreted
as negative consumption."""
from __future__ import annotations

from datetime import date

from custom_components.hu_energy_tariffs.models import TariffSiteConfig

from tests.unit.factories import make_bare_coordinator, make_state


def test_meter_reset_does_not_produce_negative_consumption(meter):
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
        tariff_year_start=date(2025, 8, 1), last_valid_source_kwh=500.0
    )

    delta = coordinator._resolve_delta(0.2)  # noqa: SLF001

    assert delta is None
    assert coordinator._state.last_valid_source_kwh == 0.2  # noqa: SLF001
