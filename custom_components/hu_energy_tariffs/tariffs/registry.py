"""Registry mapping tariff plans to their calculation strategy.

Adding a new tariff is: implement a TariffStrategy subclass, decorate it
with @register - done, no changes anywhere else in the engine. Tariff
plans without a registered strategy still exist in the catalog (see
_stubs.py) so their ids are reserved and config_flow can list them as
"coming soon", but they are filtered out of the selectable options by
available_tariff_plans().
"""
from __future__ import annotations

from ..models import TariffPlan
from ..tariff_engine import TariffStrategy

_STRATEGIES: dict[str, type[TariffStrategy]] = {}
_TARIFF_PLANS: dict[str, TariffPlan] = {}


def register(strategy_cls: type[TariffStrategy]) -> type[TariffStrategy]:
    """Class decorator registering a TariffStrategy under its strategy_key."""
    _STRATEGIES[strategy_cls.strategy_key] = strategy_cls
    return strategy_cls


def register_tariff_plan(plan: TariffPlan) -> TariffPlan:
    """Register a TariffPlan catalog entry (metadata only, no strategy)."""
    _TARIFF_PLANS[plan.id] = plan
    return plan


def get_strategy(strategy_key: str) -> TariffStrategy:
    try:
        strategy_cls = _STRATEGIES[strategy_key]
    except KeyError as err:
        raise ValueError(f"No strategy registered for {strategy_key!r}") from err
    return strategy_cls()


def is_registered(strategy_key: str) -> bool:
    return strategy_key in _STRATEGIES


def all_tariff_plans() -> list[TariffPlan]:
    """All catalog entries, including roadmap plans with no strategy yet."""
    return list(_TARIFF_PLANS.values())


def available_tariff_plans() -> list[TariffPlan]:
    """Tariff plans that are actually selectable - have a registered strategy."""
    return [plan for plan in _TARIFF_PLANS.values() if is_registered(plan.strategy_key)]


def get_tariff_plan(plan_id: str) -> TariffPlan:
    try:
        return _TARIFF_PLANS[plan_id]
    except KeyError as err:
        raise ValueError(f"Unknown tariff plan id {plan_id!r}") from err
