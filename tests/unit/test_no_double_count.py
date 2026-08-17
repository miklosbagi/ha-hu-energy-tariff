"""After restart, the first delta must be computed against the restored
last_valid_source_kwh, never against zero - otherwise consumption that
happened before the restart would be double counted."""
from __future__ import annotations

from datetime import date

from custom_components.hu_energy_tariffs.models import PersistedMeterState, TariffSiteConfig

from tests.unit.factories import make_bare_coordinator


def test_first_post_restart_delta_uses_restored_baseline(meter):
    site = TariffSiteConfig(
        name="test",
        meters=(meter,),
        provider_id="mvm_next",
        distribution_area_id="eon",
        tariff_plan_id="mvm_a1",
        pricing_periods=(),
    )
    coordinator = make_bare_coordinator(meter=meter, site=site)
    # Simulates a Store load after restart - the meter had already
    # reached 1000.0 kWh before Home Assistant restarted.
    coordinator._state = PersistedMeterState.from_dict(  # noqa: SLF001
        PersistedMeterState(
            schema_version=1,
            meter_id="main",
            tariff_year_start=date(2025, 8, 1),
            source_baseline_kwh=0.0,
            last_valid_source_kwh=1000.0,
        ).to_dict()
    )

    delta = coordinator._resolve_delta(1005.0)  # noqa: SLF001

    # Not 1005.0 - that would double count the 1000 kWh from before restart.
    assert delta == 5.0
