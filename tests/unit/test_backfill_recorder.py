"""async_fetch_daily_deltas: the one HA-coupled piece of backfill.py.

Mocks homeassistant.components.recorder.statistics.statistics_during_period
directly rather than seeding a real Recorder database - this is testing
*our* parsing/aggregation of its return value (skip None/non-positive
changes, convert epoch seconds to a local date using Home Assistant's
own configured timezone), not re-deriving HA core's own
statistics-bucketing algorithm, which HA core already tests itself. A
real end-to-end pass against a genuine Recorder is covered by the e2e
rig instead (see docs/DESIGN.md's three-layer testing strategy).

All tests pin hass.config.time_zone to UTC explicitly - the default test
hass fixture defaults to US/Pacific, and this module's date-recovery
logic is timezone-sensitive by design (see backfill.py's own comment on
why dt_util.as_local, not a bare .astimezone(), is used).
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest

from custom_components.hu_energy_tariff.backfill import async_fetch_daily_deltas

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

ENTITY_ID = "sensor.test_energy"


def _ts(d: date) -> float:
    return datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp()


async def test_recorder_not_loaded_returns_none(hass):
    assert "recorder" not in hass.config.components
    result = await async_fetch_daily_deltas(hass, ENTITY_ID, date(2026, 8, 1), date(2026, 8, 3))
    assert result is None


async def test_no_statistics_for_entity_returns_none(hass):
    await hass.config.async_set_time_zone("UTC")
    hass.config.components.add("recorder")
    with patch(
        "homeassistant.components.recorder.statistics.statistics_during_period",
        return_value={},
    ):
        result = await async_fetch_daily_deltas(
            hass, ENTITY_ID, date(2026, 8, 1), date(2026, 8, 3)
        )
    assert result is None


async def test_parses_daily_change_rows_into_a_date_keyed_mapping(hass):
    await hass.config.async_set_time_zone("UTC")
    hass.config.components.add("recorder")
    fake_rows = {
        ENTITY_ID: [
            {"start": _ts(date(2026, 8, 1)), "change": 5.5},
            {"start": _ts(date(2026, 8, 2)), "change": 3.2},
        ]
    }
    with patch(
        "homeassistant.components.recorder.statistics.statistics_during_period",
        return_value=fake_rows,
    ):
        result = await async_fetch_daily_deltas(
            hass, ENTITY_ID, date(2026, 8, 1), date(2026, 8, 3)
        )
    assert result == {date(2026, 8, 1): 5.5, date(2026, 8, 2): 3.2}


async def test_skips_rows_with_no_change_or_non_positive_change(hass):
    """A row with change=None (no data that day) or change<=0 (a meter
    reset Recorder's own reset-aware "sum" already absorbed) must not
    show up as a negative or phantom delta - skip it, let replay_deltas'
    gap-filling (0.0 for a missing day) take over instead."""
    await hass.config.async_set_time_zone("UTC")
    hass.config.components.add("recorder")
    fake_rows = {
        ENTITY_ID: [
            {"start": _ts(date(2026, 8, 1)), "change": None},
            {"start": _ts(date(2026, 8, 2)), "change": 0.0},
            {"start": _ts(date(2026, 8, 3)), "change": -1.5},
            {"start": _ts(date(2026, 8, 4)), "change": 2.0},
        ]
    }
    with patch(
        "homeassistant.components.recorder.statistics.statistics_during_period",
        return_value=fake_rows,
    ):
        result = await async_fetch_daily_deltas(
            hass, ENTITY_ID, date(2026, 8, 1), date(2026, 8, 5)
        )
    assert result == {date(2026, 8, 4): 2.0}


async def test_all_rows_filtered_out_returns_none(hass):
    await hass.config.async_set_time_zone("UTC")
    hass.config.components.add("recorder")
    fake_rows = {ENTITY_ID: [{"start": _ts(date(2026, 8, 1)), "change": None}]}
    with patch(
        "homeassistant.components.recorder.statistics.statistics_during_period",
        return_value=fake_rows,
    ):
        result = await async_fetch_daily_deltas(
            hass, ENTITY_ID, date(2026, 8, 1), date(2026, 8, 2)
        )
    assert result is None


async def test_non_utc_timezone_still_recovers_the_right_local_date(hass):
    """The regression this module's own comment calls out: a UTC
    midnight timestamp must map to the *configured* local day, not
    whatever the host OS's timezone happens to be. Budapest is UTC+2 in
    August, so 2026-08-01T00:00:00Z is already 2026-08-01 local - a
    timestamp a few hours before local midnight is the sharper case."""
    await hass.config.async_set_time_zone("Europe/Budapest")
    hass.config.components.add("recorder")
    # 2026-08-01T22:00:00Z = 2026-08-02T00:00:00+02:00 local.
    ts = datetime(2026, 8, 1, 22, tzinfo=UTC).timestamp()
    fake_rows = {ENTITY_ID: [{"start": ts, "change": 4.0}]}
    with patch(
        "homeassistant.components.recorder.statistics.statistics_during_period",
        return_value=fake_rows,
    ):
        result = await async_fetch_daily_deltas(
            hass, ENTITY_ID, date(2026, 8, 1), date(2026, 8, 3)
        )
    assert result == {date(2026, 8, 2): 4.0}
