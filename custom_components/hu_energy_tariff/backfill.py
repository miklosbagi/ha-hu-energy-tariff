"""Optional seeding of initial tariff-year state from Home Assistant's
own recorded history, instead of the zero baseline a fresh setup would
otherwise start from.

Deliberately split into two pieces:
- `async_fetch_daily_deltas` is the only HA-coupled part (talks to the
  Recorder). It degrades to `None` - never raises - whenever there's
  nothing to backfill from: Recorder not loaded, or no statistics for
  this entity in the requested window. Both are normal, expected
  situations, not errors.
- `replay_deltas` is a plain function with no `hass` dependency: it
  feeds historical per-day deltas through the exact same
  `TariffStrategy.calculate()` used for live events, one simulated day
  at a time, threading state through. No new pricing/quota/fee logic
  lives here - a backfilled day is priced identically to how it would
  have been if the integration had been running that whole time.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta

from homeassistant.core import HomeAssistant

from .models import PersistedMeterState, PricingPeriod
from .tariff_engine import TariffStrategy

_LOGGER = logging.getLogger(__name__)


def backfill_start_date(*, tariff_year_start: date, today: date) -> date:
    """The earliest date backfill is ever allowed to reach.

    The later of the current tariff year's start (1 Aug) or 1 January of
    the current calendar year - installing any time Jan-Jul only reaches
    back to that Jan 1 (not the previous Aug); installing any time
    Aug-Dec reaches back to that Aug 1 (Jan 1 hasn't happened yet in the
    current tariff year, so it doesn't bind). Caps how far backfill ever
    reaches at roughly 12 months using a boundary every user already
    understands, while never crossing into a different tariff year's
    quota cycle - a deliberate scope limit, not the most history
    technically available.
    """
    calendar_year_start = date(today.year, 1, 1)
    return max(tariff_year_start, calendar_year_start)


async def async_fetch_daily_deltas(
    hass: HomeAssistant,
    entity_id: str,
    start: date,
    end: date,
) -> dict[date, float] | None:
    """Fetch real per-day consumption deltas for `entity_id` over
    [start, end) (end exclusive - normally "today", not yet complete).

    Returns a sparse mapping (only days Recorder actually has data for -
    callers should treat missing days as 0, not as missing entirely) or
    None if there's nothing usable to backfill from at all.
    """
    if "recorder" not in hass.config.components:
        _LOGGER.debug(
            "Recorder not loaded - skipping history backfill for %s", entity_id
        )
        return None

    # Imported lazily: recorder is an optional HA component (not every
    # installation runs it), so importing at module level would make a
    # missing recorder integration an ImportError instead of the
    # graceful "nothing to backfill from" this function already handles
    # via the component-loaded check above.
    import homeassistant.util.dt as dt_util
    from homeassistant.components.recorder.statistics import statistics_during_period

    start_dt = dt_util.start_of_local_day(start)
    end_dt = dt_util.start_of_local_day(end)

    def _query() -> dict[str, list]:
        return statistics_during_period(
            hass,
            start_dt,
            end_dt,
            {entity_id},
            "day",
            None,
            {"change"},
        )

    stats = await hass.async_add_executor_job(_query)
    rows = stats.get(entity_id)
    if not rows:
        _LOGGER.debug(
            "No recorded history for %s between %s and %s - skipping backfill",
            entity_id,
            start,
            end,
        )
        return None

    deltas: dict[date, float] = {}
    for row in rows:
        change = row.get("change")
        if change is None or change <= 0:
            continue
        # dt_util.as_local, not a bare .astimezone() - the query above
        # was already bucketed by Home Assistant's own configured
        # timezone (dt_util.start_of_local_day()), so the row's "day"
        # must be recovered using that same timezone, not whatever the
        # host OS happens to be set to (they're not always the same -
        # confirmed live while writing this module's own tests).
        row_date = dt_util.as_local(datetime.fromtimestamp(row["start"], tz=UTC)).date()
        deltas[row_date] = change

    return deltas or None


def replay_deltas(
    *,
    strategy: TariffStrategy,
    pricing_periods: tuple[PricingPeriod, ...],
    start: date,
    end: date,
    daily_deltas: dict[date, float],
    initial_state: PersistedMeterState,
) -> PersistedMeterState:
    """Replay [start, end) day by day through `strategy.calculate()`,
    exactly as if each day's real delta had arrived as a live event.

    Walks every calendar day in the range, not just the days present in
    `daily_deltas` - a day Recorder has no data for still needs to
    accrue that day's fixed fee (which runs regardless of consumption),
    so a gap is treated as a real 0 kWh day, not skipped outright.
    `initial_state.fixed_fee_last_accrued_date` must already be `start`
    (the caller's responsibility) so the first simulated day's fee
    accrual loop begins in the right place.
    """
    state = initial_state
    one_day = timedelta(days=1)
    day = start
    while day < end:
        # "now" = the instant this day is fully elapsed, matching how
        # the fixed-fee accrual loop (`_accrue_fixed_fee`) already
        # advances one day at a time via `current_date < now.date()`.
        now = datetime.combine(day + one_day, time.min, tzinfo=UTC)
        _, state = strategy.calculate(
            now=now,
            delta_kwh=daily_deltas.get(day, 0.0),
            pricing_periods=pricing_periods,
            state=state,
        )
        day += one_day
    return state
