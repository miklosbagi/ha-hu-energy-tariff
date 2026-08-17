"""Coordinator: source-sensor tracking, meter-reset detection, persistence.

One coordinator instance per configured Meter. Reset detection and unit
normalization live here (meter-agnostic concerns) rather than in the
tariff strategy (a tariff-specific concern) - see tariff_engine.py.
"""
from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import homeassistant.util.dt as dt_util

from .const import (
    DOMAIN,
    IMPLAUSIBLE_JUMP_CEILING_KWH,
    RESET_NEAR_ZERO_ABS_KWH,
    RESET_NEAR_ZERO_RELATIVE,
    SUSPECT_READING_CONFIRMATIONS_REQUIRED,
)
from .models import Meter, PersistedMeterState, TariffResult, TariffSiteConfig, to_kwh
from .tariff_engine import TariffStrategy

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1


class HuEnergyTariffsCoordinator(DataUpdateCoordinator[TariffResult]):
    """Tracks one meter's source sensor and drives its tariff strategy.

    Event-driven off the source entity's state changes rather than
    interval polling - DataUpdateCoordinator is still used as the base
    class for its listener fan-out to entities, but update_interval is
    never set and _async_update_data is never implemented.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        entry_id: str,
        site: TariffSiteConfig,
        meter: Meter,
        strategy: TariffStrategy,
    ) -> None:
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_{entry_id}_{meter.id}")
        self._site = site
        self._meter = meter
        self._strategy = strategy
        self._store: Store = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}_meter_{meter.id}"
        )
        self._state: PersistedMeterState | None = None
        self._unsub_state_change = None

    @property
    def meter(self) -> Meter:
        return self._meter

    async def async_setup(self) -> None:
        """Load persisted state (or initialize it) and start tracking."""
        stored = await self._store.async_load()
        now = dt_util.utcnow()

        if stored is not None:
            self._state = PersistedMeterState.from_dict(stored)
        else:
            initial_reading = self._read_current_source_kwh()
            tariff_year_start, _ = self._strategy.tariff_year_bounds(now)
            self._state = PersistedMeterState(
                schema_version=STORAGE_VERSION,
                meter_id=self._meter.id,
                tariff_year_start=tariff_year_start,
                source_baseline_kwh=initial_reading or 0.0,
                last_valid_source_kwh=initial_reading or 0.0,
                fixed_fee_last_accrued_date=tariff_year_start,
            )
            await self._save_state()

        self._unsub_state_change = async_track_state_change_event(
            self.hass, [self._meter.source_entity_id], self._handle_source_event
        )

        # Seed initial data so entities have a value before the first
        # source-sensor state change fires.
        self.async_set_updated_data(self._peek_result(now))

    async def async_unload(self) -> None:
        if self._unsub_state_change is not None:
            self._unsub_state_change()
            self._unsub_state_change = None

    def _read_current_source_kwh(self) -> float | None:
        return self._parse_state_to_kwh(self.hass.states.get(self._meter.source_entity_id))

    @staticmethod
    def _parse_state_to_kwh(state: State | None) -> float | None:
        if state is None or state.state in (None, "unknown", "unavailable", ""):
            return None
        try:
            raw_value = float(state.state)
        except (TypeError, ValueError):
            return None
        unit = state.attributes.get("unit_of_measurement", "kWh")
        try:
            return to_kwh(raw_value, unit)
        except ValueError:
            _LOGGER.warning("Unsupported unit_of_measurement %r on source sensor", unit)
            return None

    @callback
    def _handle_source_event(self, event: Event[EventStateChangedData]) -> None:
        self.hass.async_create_task(self._async_process_event(event))

    async def _async_process_event(self, event: Event[EventStateChangedData]) -> None:
        if self._state is None:
            return
        new_ha_state = event.data["new_state"]
        now = dt_util.utcnow()

        reading_kwh = self._parse_state_to_kwh(new_ha_state)
        if reading_kwh is None:
            self._state.consecutive_invalid_reads += 1
            _LOGGER.debug(
                "%s: invalid/unavailable source reading (%s consecutive)",
                self._meter.source_entity_id,
                self._state.consecutive_invalid_reads,
            )
            await self._save_state()
            return

        accepted_delta = self._resolve_delta(reading_kwh)
        if accepted_delta is None:
            await self._save_state()
            return

        self._maybe_roll_tariff_year(now)

        result, new_state = self._strategy.calculate(
            now=now,
            delta_kwh=accepted_delta,
            pricing_periods=self._site.pricing_periods,
            state=self._state,
        )
        # calculate() intentionally never sees the raw source reading -
        # stamp it back onto the persisted state here.
        new_state.last_valid_source_kwh = reading_kwh
        self._state = new_state
        await self._save_state()
        self.async_set_updated_data(result)

    def _resolve_delta(self, reading_kwh: float) -> float | None:
        """Apply reset/suspect-reading detection to a new raw reading.

        Returns an accepted consumption delta, or None if the reading
        was held for confirmation or treated as a meter reset (nothing
        to add as consumption either way).
        """
        state = self._state
        assert state is not None
        raw_delta = reading_kwh - state.last_valid_source_kwh

        if 0 <= raw_delta <= IMPLAUSIBLE_JUMP_CEILING_KWH:
            state.pending_suspect_reading_kwh = None
            state.pending_suspect_reading_count = 0
            state.consecutive_invalid_reads = 0
            return raw_delta

        near_zero_threshold = max(
            RESET_NEAR_ZERO_ABS_KWH, state.last_valid_source_kwh * RESET_NEAR_ZERO_RELATIVE
        )

        if raw_delta < 0 and reading_kwh <= near_zero_threshold:
            _LOGGER.warning(
                "%s: meter reset detected (was %.3f kWh, now %.3f kWh) - "
                "re-baselining without counting negative consumption",
                self._meter.source_entity_id,
                state.last_valid_source_kwh,
                reading_kwh,
            )
            state.last_valid_source_kwh = reading_kwh
            state.pending_suspect_reading_kwh = None
            state.pending_suspect_reading_count = 0
            return None

        # Suspect reading: a large drop that isn't near-zero (possible
        # entity replacement / bad value), or an implausibly large jump
        # (possible unit change). Require N consecutive consistent
        # readings before accepting it as a new baseline.
        if (
            state.pending_suspect_reading_kwh is not None
            and abs(reading_kwh - state.pending_suspect_reading_kwh) <= near_zero_threshold
        ):
            state.pending_suspect_reading_count += 1
        else:
            state.pending_suspect_reading_kwh = reading_kwh
            state.pending_suspect_reading_count = 1

        _LOGGER.warning(
            "%s: suspect reading %.3f kWh (prior %.3f kWh, raw delta %.3f kWh) - "
            "confirmation %s/%s",
            self._meter.source_entity_id,
            reading_kwh,
            state.last_valid_source_kwh,
            raw_delta,
            state.pending_suspect_reading_count,
            SUSPECT_READING_CONFIRMATIONS_REQUIRED,
        )

        if state.pending_suspect_reading_count >= SUSPECT_READING_CONFIRMATIONS_REQUIRED:
            _LOGGER.warning(
                "%s: accepting suspect reading as new baseline after %s "
                "confirmations - resetting baseline without counting the "
                "jump as consumption",
                self._meter.source_entity_id,
                state.pending_suspect_reading_count,
            )
            state.last_valid_source_kwh = reading_kwh
            state.pending_suspect_reading_kwh = None
            state.pending_suspect_reading_count = 0
        return None

    def _maybe_roll_tariff_year(self, now: datetime) -> None:
        state = self._state
        assert state is not None
        start, _end_exclusive = self._strategy.tariff_year_bounds(now)
        if state.tariff_year_start == start:
            return
        _LOGGER.info(
            "%s: rolling over to new tariff year starting %s",
            self._meter.source_entity_id,
            start,
        )
        state.tariff_year_start = start
        state.accumulated_discounted_kwh = 0.0
        state.accumulated_market_kwh = 0.0
        state.accumulated_variable_cost_ft = 0.0
        state.accumulated_fixed_cost_ft = 0.0
        state.fixed_fee_last_accrued_date = start

    def _peek_result(self, now: datetime) -> TariffResult:
        """A zero-delta calculation used only to seed initial entity
        values before the first real source-sensor event arrives. The
        returned (discarded) state is never persisted - the next real
        event recomputes fee accrual from the true last-accrued date."""
        assert self._state is not None
        result, _discarded_state = self._strategy.calculate(
            now=now, delta_kwh=0.0, pricing_periods=self._site.pricing_periods, state=self._state
        )
        return result

    async def _save_state(self) -> None:
        assert self._state is not None
        await self._store.async_save(self._state.to_dict())
