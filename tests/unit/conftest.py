"""Shared pytest fixtures for hu_energy_tariffs unit tests.

None of these tests boot Home Assistant - the tariff engine and the
coordinator's pure reset/rollover logic are exercised directly, per the
SPEC's "headless where practical" requirement.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from custom_components.hu_energy_tariffs.models import Meter, MeterRole, PriceComponents, PricingPeriod
from custom_components.hu_energy_tariffs.tariffs.mvm_a1 import A1Strategy


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def a1_pricing_period() -> PricingPeriod:
    return PricingPeriod(
        valid_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
        valid_to=None,
        provider_id="mvm_next",
        distribution_area_id="eon",
        tariff_plan_id="mvm_a1",
        quota_kwh_per_year=2523,
        fixed_monthly_fee_ft=0.0,
        price_components=PriceComponents(
            energy_charge_discounted=36.9,
            energy_charge_market=70.0,
        ),
    )


@pytest.fixture
def strategy() -> A1Strategy:
    return A1Strategy()


@pytest.fixture
def meter() -> Meter:
    return Meter(id="main", source_entity_id="sensor.test_energy", role=MeterRole.MAIN)
