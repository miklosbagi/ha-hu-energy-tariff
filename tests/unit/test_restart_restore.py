"""After a Home Assistant restart, PersistedMeterState round-trips
through its dict representation exactly, so the coordinator can resume
from where it left off (see also test_no_double_count.py)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from custom_components.hu_energy_tariffs.models import PersistedMeterState


def test_persisted_state_round_trip():
    original = PersistedMeterState(
        schema_version=1,
        meter_id="main",
        tariff_year_start=date(2025, 8, 1),
        source_baseline_kwh=100.0,
        last_valid_source_kwh=456.789,
        accumulated_discounted_kwh=200.0,
        accumulated_market_kwh=50.0,
        accumulated_variable_cost_ft=12345.0,
        accumulated_fixed_cost_ft=678.0,
        fixed_fee_last_accrued_date=date(2026, 3, 1),
        last_processed_timestamp=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
        consecutive_invalid_reads=0,
    )

    restored = PersistedMeterState.from_dict(original.to_dict())

    assert restored == original
