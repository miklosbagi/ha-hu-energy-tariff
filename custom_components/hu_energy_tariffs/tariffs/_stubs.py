"""Roadmap tariff plan catalog entries (Prio 1 / Prio 2 - see README).

These reserve stable TariffPlan ids for tariffs that are planned but not
yet implemented. They register no TariffStrategy, so config_flow filters
them out of the selectable options (available_tariff_plans()) until a
real strategy module registers against their id - at that point they
become selectable with zero changes to the engine or coordinator.
"""
from __future__ import annotations

from ..models import TariffPlan
from .registry import register_tariff_plan

register_tariff_plan(
    TariffPlan(
        id="mvm_a2",
        code="A2",
        name="A2 (time-of-use)",
        name_hu="A2 (idős zónás)",
        requires_separate_meter=False,
        strategy_key="mvm_a2",
    )
)

register_tariff_plan(
    TariffPlan(
        id="mvm_b_alap",
        code="B",
        name="B Alap (controlled, 8h/day)",
        name_hu="B Alap (vezérelt, napi 8 óra)",
        requires_separate_meter=True,
        strategy_key="mvm_b_alap",
    )
)

register_tariff_plan(
    TariffPlan(
        id="mvm_h",
        code="H",
        name="H (heat pump, seasonal)",
        name_hu="H (hőszivattyú, szezonális)",
        requires_separate_meter=True,
        strategy_key="mvm_h",
    )
)

register_tariff_plan(
    TariffPlan(
        id="mvm_b_komfort",
        code="B",
        name="B Komfort (controlled, 12h/day)",
        name_hu="B Komfort (vezérelt, napi 12 óra)",
        requires_separate_meter=True,
        strategy_key="mvm_b_komfort",
    )
)

register_tariff_plan(
    TariffPlan(
        id="mvm_b_geo",
        code="B",
        name="B GEO (legacy heat pump)",
        name_hu="B GEO (korábbi hőszivattyús konstrukció)",
        requires_separate_meter=True,
        strategy_key="mvm_b_geo",
    )
)
