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

# Fields collected by the (currently A1-only) tariff_energy_prices step -
# mirrors a Hungarian bill's "Villamosenergia ár" group. Net (VAT-excl.)
# Ft/kWh - PriceComponents.effective_gross_price() applies VAT once, on
# the sum of all net components below, so these must never hold an
# already-gross figure.
CONF_QUOTA_KWH_PER_YEAR = "quota_kwh_per_year"
CONF_DISCOUNTED_PRICE_FT_PER_KWH = "discounted_price_ft_per_kwh"
CONF_MARKET_PRICE_FT_PER_KWH = "market_price_ft_per_kwh"

# Fields collected by the tariff_network_fees step - mirrors a bill's
# "Rendszerhasználati díjak" group. transmission_charge/distribution_charge
# are net (VAT-excl.) Ft/kWh, same rule as above; fixed_monthly_fee_ft is
# gross (VAT-incl.) Ft/month, applied as-is with no further VAT math (see
# tariffs/mvm_a1.py::_accrue_fixed_fee) - matches a bill's "Elosztói
# alapdíj" line, which is already shown gross.
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

# "Elosztási és átviteli díjak" (Ft/kWh, net) - the official sheet
# publishes this as one combined figure covering both a bill's
# "Elosztói forgalmi díj" (distribution) and "Átvételi forgalmi díj"
# (transmission) line items; there's no official public split between
# the two. Defaulting the whole combined figure into distribution_charge
# and leaving transmission_charge at 0 keeps the *total* correct out of
# the box - override both from your bill's exact two line items if you
# want the fields to mirror it precisely. Uniform across DSO areas.
DEFAULT_A1_DISTRIBUTION_CHARGE_FT_PER_KWH = 23.400
DEFAULT_A1_TRANSMISSION_CHARGE_FT_PER_KWH = 0.0

# "Elosztói alapdíj", gross, per connection point/month - also uniform
# across DSO areas for A1 in the official sheet.
DEFAULT_A1_FIXED_MONTHLY_FEE_FT = 153.035

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
