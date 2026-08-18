"""Constants and static reference catalogs for hu_energy_tariffs.

Adding a new provider or distribution area is a data change here, never
a code change elsewhere in the integration. Tariff plans (including
Prio 1/2 roadmap ones) live in the tariffs/registry.py catalog instead,
since they carry a strategy_key that needs to line up with the engine's
strategy registry.
"""
from __future__ import annotations

from homeassistant.const import Platform

from .models import DistributionArea, Provider

DOMAIN = "hu_energy_tariffs"

PLATFORMS: list[Platform] = [Platform.SENSOR]

# --- Config-entry data keys -------------------------------------------------

CONF_SOURCE_ENTITY_ID = "source_entity_id"
CONF_PROVIDER_ID = "provider_id"
CONF_DISTRIBUTION_AREA_ID = "distribution_area_id"
CONF_TARIFF_PLAN_ID = "tariff_plan_id"
CONF_PRICING_PERIODS = "pricing_periods"

# Fields collected by the (currently A1-only) tariff_params flow step.
CONF_QUOTA_KWH_PER_YEAR = "quota_kwh_per_year"
CONF_DISCOUNTED_PRICE_FT_PER_KWH = "discounted_price_ft_per_kwh"
CONF_MARKET_PRICE_FT_PER_KWH = "market_price_ft_per_kwh"
CONF_FIXED_MONTHLY_FEE_FT = "fixed_monthly_fee_ft"

# --- Defaults ----------------------------------------------------------------
# NOTE: these are starting points, not live regulated prices - see the
# "Automating tariff price updates" section of README.md for the official
# sources and the (not yet built) maintainer-side tooling to keep these
# current. The integration itself never fetches prices at runtime - users
# always confirm/override these against their actual contract.

DEFAULT_A1_QUOTA_KWH = 2523
DEFAULT_A1_DISCOUNTED_PRICE_FT_PER_KWH = 36.9
DEFAULT_A1_MARKET_PRICE_FT_PER_KWH = 70.0
DEFAULT_A1_FIXED_MONTHLY_FEE_FT = 0.0
DEFAULT_VAT_RATE = 0.27

# --- Coordinator reset / suspect-reading heuristics --------------------------
# See coordinator.py::_resolve_delta. Named here (not inline) so they're
# easy to retune without touching detection logic.

RESET_NEAR_ZERO_ABS_KWH = 1.0
RESET_NEAR_ZERO_RELATIVE = 0.01  # 1% of the prior reading
IMPLAUSIBLE_JUMP_CEILING_KWH = 5000.0
SUSPECT_READING_CONFIRMATIONS_REQUIRED = 2

# --- Static reference catalogs ------------------------------------------------

PROVIDERS: dict[str, Provider] = {
    "mvm_next": Provider(id="mvm_next", name="MVM Next", name_hu="MVM Next"),
}

DISTRIBUTION_AREAS: dict[str, DistributionArea] = {
    "eon": DistributionArea(id="eon", name="E.ON"),
    "mvm_emasz": DistributionArea(id="mvm_emasz", name="MVM (ÉMÁSZ)"),
    "opus": DistributionArea(id="opus", name="OPUS"),
    "e2": DistributionArea(id="e2", name="E2 (Démász/Édász)"),
}
