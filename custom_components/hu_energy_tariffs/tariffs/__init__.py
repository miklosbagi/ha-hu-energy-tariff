"""Tariff strategy implementations and the roadmap catalog.

Importing this package registers all known TariffPlan catalog entries
and every implemented TariffStrategy (currently: A1 only).
"""
from . import _stubs, mvm_a1  # noqa: F401  (import for registration side effects)
from .registry import (
    all_tariff_plans,
    available_tariff_plans,
    get_strategy,
    get_tariff_plan,
    is_registered,
    register,
    register_tariff_plan,
)

__all__ = [
    "all_tariff_plans",
    "available_tariff_plans",
    "get_strategy",
    "get_tariff_plan",
    "is_registered",
    "register",
    "register_tariff_plan",
]
