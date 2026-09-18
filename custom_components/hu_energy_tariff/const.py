"""Constants and static reference catalogs for hu_energy_tariff.

Adding a new provider or distribution area is a data change here, never
a code change elsewhere in the integration. Tariff plans (including
Prio 1/2 roadmap ones) live in the tariffs/registry.py catalog instead,
since they carry a strategy_key that needs to line up with the engine's
strategy registry.
"""
from __future__ import annotations

from homeassistant.const import Platform

from .models import DistributionArea, Provider

DOMAIN = "hu_energy_tariff"

PLATFORMS: list[Platform] = [Platform.SENSOR]

# --- Config-entry data keys -------------------------------------------------

CONF_SOURCE_ENTITY_ID = "source_entity_id"
CONF_PROVIDER_ID = "provider_id"
CONF_DISTRIBUTION_AREA_ID = "distribution_area_id"
CONF_TARIFF_PLAN_ID = "tariff_plan_id"
CONF_PRICING_PERIODS = "pricing_periods"

# Set when the user accepted the config-flow backfill offer (see
# backfill.py) - tells coordinator.py's first-ever setup to seed initial
# state from Home Assistant's recorded history instead of a zero
# baseline. Never set on reload/restart; only meaningful the one time a
# config entry is first created.
CONF_BACKFILL_ENABLED = "backfill_enabled"

# Fields collected by the (currently A1-only) tariff_energy_prices step -
# mirrors a Hungarian bill's "Villamosenergia ár" group. Net (VAT-excl.)
# Ft/kWh - PriceComponents.effective_gross_price() applies VAT once, on
# the sum of all net components below, so these must never hold an
# already-gross figure.
CONF_QUOTA_KWH_PER_YEAR = "quota_kwh_per_year"
CONF_DISCOUNTED_PRICE_FT_PER_KWH = "discounted_price_ft_per_kwh"
CONF_MARKET_PRICE_FT_PER_KWH = "market_price_ft_per_kwh"

# Fields collected by the tariff_network_fees step - mirrors a bill's
# "Rendszerhasználati díjak" group. All three (transmission_charge,
# distribution_charge, fixed_monthly_fee_ft) are net (VAT-excl.), same
# rule as the energy fields above - tariffs/mvm_a1.py applies VAT to
# fixed_monthly_fee_ft explicitly in _accrue_fixed_fee(), rather than
# treating it as a silent gross exception to the "everything on this
# screen is net" rule the UI states.
CONF_TRANSMISSION_CHARGE_FT_PER_KWH = "transmission_charge_ft_per_kwh"
CONF_DISTRIBUTION_CHARGE_FT_PER_KWH = "distribution_charge_ft_per_kwh"
CONF_FIXED_MONTHLY_FEE_FT = "fixed_monthly_fee_ft"

# --- Defaults ----------------------------------------------------------------
# NOTE: these are starting points, not a live feed - see the "Automating
# tariff price updates" section of README.md for the official sources
# and the (not yet built) maintainer-side tooling to keep these current.
# The integration itself never fetches prices at runtime - users always
# confirm/override these against their actual contract (ideally by
# transcribing the matching line straight off their own bill).
#
# Sourced from MVM's official residential price sheet "VILLAMOSENERGIA-
# DÍJAK AZ EGYETEMES SZOLGÁLTATÁSBAN LAKOSSÁGI ÜGYFELEKNEK 2022. AUGUSZTUS
# 1-JÉTŐL" (doc ref VE_Lakossági_Árak_2025/1 - still the effective sheet,
# no revision published since; legal basis: 4/2011 NFM rendelet, 259/2022
# Korm. rendelet, 20/2022 + 10/2024 MEKH rendelet). All Ft/kWh figures
# below are NET (VAT-excluded) "Villamosenergia-ár" / "Elosztási és
# átviteli díjak" rows from that sheet - PriceComponents.
# effective_gross_price() applies VAT once, on top of the sum of these,
# so these must stay net or the computed price ends up double-VATed.

DEFAULT_A1_QUOTA_KWH = 2523

# The discounted A1 energy rate genuinely differs by DSO area (see
# DEFAULT_A1_DISCOUNTED_ENERGY_PRICE_BY_AREA_FT_PER_KWH below, keyed by
# DISTRIBUTION_AREAS id) - config_flow.py prefills the area-specific
# figure once a distribution area is chosen. This flat constant is only
# a fallback for an unrecognized/missing area id.
DEFAULT_A1_DISCOUNTED_ENERGY_PRICE_FT_PER_KWH = 4.390

# Unlike the discounted rate, A1's market-price energy tier is the same
# 31.800 Ft/kWh net across every DSO area in the official sheet.
DEFAULT_A1_MARKET_ENERGY_PRICE_FT_PER_KWH = 31.800

# "Elosztói forgalmi díj" (distribution) and "Átvételi forgalmi díj"
# (transmission), Ft/kWh net - sourced from MVM Hálózat's official
# "Az elosztók által alkalmazható rendszerhasználati díjak" table
# (RHD_2026_01_01, effective 2026-01-01: https://mvmhalozat.hu/aram/
# oldalak/1456), low-voltage residential ("Kisfeszültségű I."/"IV.")
# row - cross-confirmed against a real A1 bill. Both uniform across
# DSO areas: the transmission fee nationally (MAVIR operates the one
# national grid), and per this table the distribution fee too, for
# low-voltage residential specifically (unlike the raw energy price,
# which does vary by DSO - see the per-area dict below).
DEFAULT_A1_DISTRIBUTION_CHARGE_FT_PER_KWH = 20.010
DEFAULT_A1_TRANSMISSION_CHARGE_FT_PER_KWH = 3.390

# "Elosztói alapdíj", net, per connection point/month - same source as
# above (1,446 Ft/connection/year / 12 = 120.5), also uniform across
# DSO areas for A1.
DEFAULT_A1_FIXED_MONTHLY_FEE_FT = 120.5

DEFAULT_VAT_RATE = 0.27

# Per-DSO-area A1 discounted energy net Ft/kWh price, keyed by
# DISTRIBUTION_AREAS id. E.ON and OPUS share a price in the official
# sheet (billed under the same "E.ON Dél-dunántúli, Észak-dunántúli
# Áramhálózati Zrt.-k és az OPUS TITÁSZ Zrt." heading) despite being
# separate catalog entries here.
DEFAULT_A1_DISCOUNTED_ENERGY_PRICE_BY_AREA_FT_PER_KWH: dict[str, float] = {
    "eon": 4.390,
    "opus": 4.390,
    "elmu": 5.110,
    "mvm_emasz": 4.940,
    "e2": 5.250,  # MVM Démász
}

# Official current A1 price sheet, listed per DSO area - lets a user
# cross-check the defaults above (or their own bill) against the source.
A1_OFFICIAL_PRICE_SHEET_URL = "https://www.mvmnext.hu/aram/pages/aloldal.jsp?id=791"

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
    # id kept as "e2" for config-entry compatibility with existing
    # installs; label corrected to match the official price sheet
    # ("MVM Démász Áramhálózati Kft.") rather than the stale "Édász" name.
    "e2": DistributionArea(id="e2", name="MVM Démász"),
    "elmu": DistributionArea(id="elmu", name="ELMŰ (Budapest)"),
}
