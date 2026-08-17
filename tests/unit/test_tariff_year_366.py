"""366-day tariff year: the Aug-Jul window includes a Feb 29."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from custom_components.hu_energy_tariffs.tariffs.mvm_a1 import _tariff_year_end_exclusive


def test_366_day_tariff_year(strategy):
    start = date(2027, 8, 1)  # window's Feb (2028) is a leap year
    end_exclusive = _tariff_year_end_exclusive(start)
    assert (end_exclusive - start).days == 366

    last_day = datetime(2028, 7, 31, 23, 59, tzinfo=timezone.utc)
    eligible = strategy._eligible_quota_kwh(last_day, 2523.0, start)  # noqa: SLF001
    assert eligible == pytest.approx(2523.0, rel=1e-6)
