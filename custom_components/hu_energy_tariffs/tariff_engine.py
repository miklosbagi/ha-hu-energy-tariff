"""Tariff calculation strategy interface.

Concrete tariff behaviour lives in tariffs/*.py subclasses of
TariffStrategy, registered via tariffs.registry.register. Nothing in
this module, or in coordinator.py, branches on which tariff is active -
each strategy fully describes its own behaviour, so adding A2/H/B later
never means editing an if/elif chain here.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import ClassVar

from .models import PersistedMeterState, PricingPeriod, TariffResult


class TariffStrategy(ABC):
    """Base class for a single tariff's calculation behaviour.

    A strategy receives an already unit-normalized, already
    reset-checked consumption delta - unit normalization and meter-reset
    detection are meter-agnostic concerns handled by the coordinator,
    not tariff-specific ones. This keeps strategies stateless between
    calls (all state flows through the explicit `state` in/out
    parameter) and trivially unit-testable without any Home Assistant
    test harness.
    """

    strategy_key: ClassVar[str]

    @abstractmethod
    def calculate(
        self,
        *,
        now: datetime,
        delta_kwh: float,
        pricing_periods: tuple[PricingPeriod, ...],
        state: PersistedMeterState,
    ) -> tuple[TariffResult, PersistedMeterState]:
        """Consume one delta and return the new result plus the state to persist.

        Receives *every* configured PricingPeriod, not just the one
        active `now` - a quota (or fixed-fee) formula that prorates over
        elapsed days must weigh each period by only the days it was
        actually active, or a mid-tariff-year quota/price edit would
        retroactively apply the new rate to days it was never in effect
        for. Which single period's price applies to *this* delta is still
        a strategy-level decision (see `models.select_pricing_period`).
        """

    @abstractmethod
    def tariff_year_bounds(self, now: datetime) -> tuple[date, date]:
        """Return (start, end_exclusive) of the tariff period containing `now`.

        Used by the coordinator to detect when accumulated per-tariff-year
        state (not the underlying cumulative meter reading) must roll over.
        """
