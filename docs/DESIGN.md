# Design decisions

This document explains *why* the codebase is structured the way it is - the constraints and trade-offs behind each decision, so a future change can be judged against the same reasoning rather than guessed at. For *what* each entity/file does, read the code and its docstrings; this document intentionally doesn't restate that.

## The core problem this structure solves

The [spec](../README.md) is explicit that only one tariff (A1) ships first, but the engine must support several structurally different tariffs later - some flat-rate, some time-of-use, some seasonal, some requiring an entirely separate meter - **without a core redesign**. Every decision below traces back to that one constraint: don't hard-code A1's shape into anything that isn't A1-specific.

## Object model: five separable concepts, not one flat record

The original ChatGPT-authored spec sketched a single flat `TariffDefinition(provider=..., valid_from=..., quota=..., prices=...)`. That's workable for A1 alone, but it conflates five things that actually vary independently in the real world:

- **Provider** (`Provider`) - the universal service provider, e.g. MVM Next. A change of national energy-market structure (new entrants, provider mergers) shouldn't touch tariff logic at all.
- **Distribution area** (`DistributionArea`) - the DSO territory (E.ON, MVM/ÉMÁSZ, OPUS, E2). Distribution-usage-charge components differ by DSO even under the same nationally-regulated tariff scheme.
- **Tariff plan** (`TariffPlan`) - the scheme identity (A1, A2, B Alap, ...) - pure metadata, no calculation logic. Its `strategy_key` is a level of indirection: it says *which* strategy calculates this plan, not that the plan *is* a strategy, so several plans could later share one strategy family if the regulator ever restructures the codes.
- **Pricing period** (`PricingPeriod`) - a validity-scoped snapshot of prices/quota. Prices change over time; a site accumulates a *list* of these, never a single mutable "current price".
- **Meter** (`Meter`) - a metering point feeding one calculation stream. Most tariffs need exactly one; B/H need two (a main meter and a separately-billed "controlled" meter).

Keeping these separable means: adding a DSO is a one-line catalog entry (`const.py`), not a code change. Adding a provider is the same. A regulator price change is a new `PricingPeriod`, never an edit to an existing one (see "Price validity is append-only" below). None of this required anticipating exactly how A2/B/H work - it only required not assuming there's exactly one of each.

**Where the ids live vs. where the data lives**: a config entry stores only `provider_id`/`distribution_area_id`/`tariff_plan_id` strings plus its own `meters`/`pricing_periods` records - it never copies `Provider`/`DistributionArea`/`TariffPlan` catalog data into itself. This means fixing a typo in a DSO's display name, or adding a new DSO, never requires migrating existing config entries.

## The tariff engine is a strategy registry, not a branch tree

`tariff_engine.py` defines one abstract contract (`TariffStrategy.calculate()` and `.tariff_year_bounds()`); `tariffs/registry.py` maps a `strategy_key` to a concrete implementation class. Nothing outside `tariffs/*.py` ever asks "which tariff is this?" - the coordinator calls `strategy.calculate(...)` polymorphically, exactly the shape the spec asked for ("do not design the core as `if tariff == "A1": ... elif ...`").

Two consequences worth calling out:

1. **Strategies are pure and stateless between calls.** `calculate()` takes an explicit `state: PersistedMeterState` in and returns a new one out - it never reads Home Assistant, the clock (beyond the `now` argument), or any global. This is what makes `A1Strategy` unit-testable with plain constructed fixtures and no Home Assistant boot at all (see "Testing strategy" below), and it's a constraint every future strategy (A2/B/H) inherits for free.
2. **Unit normalization and meter-reset detection live in the coordinator, not the strategy.** These are meter-agnostic concerns - a Wh vs. kWh source, or a meter that resets, has nothing to do with which tariff is active. Putting reset detection inside `A1Strategy` would have meant reimplementing (and re-testing) it inside every future strategy too.

`tariffs/_stubs.py` exists specifically so the Prio 1/2 tariff ids (`mvm_a2`, `mvm_b_alap`, `mvm_h`, `mvm_b_komfort`, `mvm_b_geo`) are reserved in the catalog now, even with no implementation behind them. `config_flow.py`'s tariff picker filters to `available_tariff_plans()` (catalog entries *with* a registered strategy), so the UI never offers a plan it can't actually calculate - but the id, code, and display name are already fixed, so implementing A2 later never means renegotiating what to call it.

## Coordinator / sensor / config_flow: one direction of dependency

- **`coordinator.py`** owns all state: it tracks the source entity, does delta/reset detection, calls the strategy, persists the result, and republishes it to listeners. It is the only place that touches `Store` and the only place that touches the source entity's raw state.
- **`sensor.py`** is deliberately inert: each entity is a `value_fn` reading one field off `coordinator.data`. No entity computes anything. This means adding a tenth diagnostic entity later is a one-line addition to `SENSOR_DESCRIPTIONS`, never a coordinator change.
- **`config_flow.py`** only ever builds a `TariffSiteConfig`/`PricingPeriod` and hands it to a config entry - it has no calculation logic and doesn't touch the coordinator directly.

This one-directional flow (config → entry data → coordinator → entities) is what let `sensor.py`'s device-naming bug (an early version leaked the internal `f"{DOMAIN}_{entry_id}_{meter_id}"` coordinator name into the user-visible device name) get fixed in one file without touching the coordinator or config flow at all.

## Persistence: one `Store` per meter, replaced wholesale

`PersistedMeterState` is deliberately *not* mutated field-by-field across the codebase - `A1Strategy.calculate()` builds and returns a whole new instance each time, and `coordinator.py` swaps `self._state` to point at it. Two reasons:

1. It matches how `Store.async_save()` actually works (serialize the whole object), so there's no risk of a partial write reflecting only some of a tick's changes.
2. It makes the restart/no-double-count invariant easy to reason about and test: `coordinator.async_setup()` loads a `PersistedMeterState` from `Store` (or builds a fresh baseline if none exists), and the very next real state-change event computes its delta against the *loaded* `last_valid_source_kwh` - never against zero. `tests/unit/test_no_double_count.py` and `tests/unit/test_integration_setup.py::test_reload_does_not_double_count` both assert this directly, the latter against a real (test) Home Assistant instance actually reloading the config entry.

Storage is keyed per meter (`f"{DOMAIN}_{entry_id}_meter_{meter.id}"`), not per config entry, specifically so a future second ("controlled") meter gets its own storage file automatically - adding it is additive, never a migration of the first meter's state.

## Meter-reset detection is a heuristic, not a certainty - so it's explicit and tunable

A cumulative source sensor can legitimately reset (meter replaced, integration re-paired), or it can report a bad/transient value, or the user can point the config at a different entity entirely. These look similar (the reading drops) but need different handling - a real reset should re-baseline without penalizing the user; a bad reading should be ignored until confirmed.

`coordinator.py::_resolve_delta` encodes this as: a drop to *near zero* is treated as a reset (re-baseline immediately, since a genuinely reset meter reads ~0); any other drop, or an implausibly large jump, is held as "suspect" and only accepted as a new baseline after `SUSPECT_READING_CONFIRMATIONS_REQUIRED` (default 2) consecutive consistent readings. All thresholds (`RESET_NEAR_ZERO_ABS_KWH`, `RESET_NEAR_ZERO_RELATIVE`, `IMPLAUSIBLE_JUMP_CEILING_KWH`, `SUSPECT_READING_CONFIRMATIONS_REQUIRED`) are named constants in `const.py`, not inline literals - there's no principled way to derive these from first principles, so they're written to be easy to retune once real-world meter behavior disagrees with the defaults, without touching the detection logic itself.

## Price validity is append-only, never edited in place

`PricingPeriod.valid_from`/`valid_to` exist because the spec requires that a price change never retroactively recalculates already-accumulated cost. The config/options flow enforces this structurally: editing prices in the options flow (`config_flow.py::HuEnergyTariffsOptionsFlow.async_step_tariff_params`) doesn't mutate the existing period - it closes it (`valid_to = now`) and appends a new one. `TariffSiteConfig.pricing_period_for(timestamp)` (via `models.select_pricing_period`) always selects by containment, so a coordinator tick during last month's price never sees this month's number and vice versa. `tests/unit/test_price_validity_boundary.py` and `test_config_flow.py::test_options_flow_opens_new_pricing_period_preserving_history` both assert the boundary behavior directly.

Users can already edit the discounted quota, both prices, and the fixed fee at any time through this options flow - no new integration release needed. It's a config change, not a code change.

## Quota and fixed-fee proration must be piecewise across pricing periods

Append-only pricing periods (above) keep *cost* honest across a price edit, but they don't automatically keep the A1 *quota proration formula* honest too - that turned out to need its own fix. `A1Strategy._eligible_quota_kwh` computes how much of the annual discounted quota is available as of "now" by prorating over elapsed days since the tariff year started (1 Aug). The first version of this formula used only the *currently active* period's `quota_kwh_per_year`, applied across the *entire* elapsed span. That's wrong the moment more than one `PricingPeriod` has existed within the same tariff year: editing the quota from 2523 to 3000 kWh mid-year would immediately grant extra discount headroom computed *as if 3000/year had applied since August 1st* - even though the days before the edit actually accrued (and were billed) under 2523. Past cost wasn't rewritten, but future pricing was being computed off a quota figure that implicitly took past days back for a rate they were never under.

The fix: `_eligible_quota_kwh` sums each `PricingPeriod`'s own prorated share, weighted only by the days *that period* was active within the tariff year so far - `Σ period.quota_kwh_per_year × days_active_in_this_period / days_in_tariff_year`. This reduces to exactly the original single-period formula when only one period has ever been configured (the common case), and correctly splits the proration across a boundary otherwise. The same reasoning applies to `_accrue_fixed_fee`'s daily loop: each day accrues at whichever period was active *on that day*, not at today's active period for the whole gap since the last coordinator tick. Because of this, `TariffStrategy.calculate()` takes the site's full `pricing_periods` tuple rather than a single pre-selected period - the strategy still picks one active period for pricing *this* delta (via `select_pricing_period`), but needs the whole history for the proration sum. `tests/unit/test_quota_change_mid_year.py` covers this directly, including a regression guard that asserts the corrected value differs meaningfully from the naive (buggy) one, plus that periods from a *previous* tariff year - which accumulate in the list forever - don't leak into the current year's sum.

## Multi-meter extension: designed for, not built

B Alap/B Komfort/H all bill a "controlled" consumption stream through a physically separate meter, alongside the normal one. Rather than guess at B's exact rules now, the data model was shaped so adding this later is additive:

- `TariffSiteConfig.meters` is a tuple from day one, even though A1 only ever populates one `Meter(role=MAIN)`.
- The coordinator is instantiated in a loop over `site.meters` in `__init__.py`, already - a second meter means a second coordinator instance, not a coordinator rewrite.
- Storage is per-meter (see above), so it doesn't need a schema migration when meter #2 appears.
- `sensor.py` already disambiguates entities and device names by `meter.id` when there's more than one meter, even though today there's only ever one.

The decision *not* made: HA "subentries" (a newer core concept for entries-within-an-entry) were considered and rejected for this use case - a controlled-tariff meter shares the same site/provider/DSO contract as the main meter, so modeling it as one config entry with two `Meter` records is simpler than two independently-lifecycled entries a user would have to keep in sync by hand.

## Testing strategy: three layers, each proving something different

1. **Headless engine tests** (`tests/unit/test_quota_*.py`, `test_tariff_year_*.py`, `test_fixed_monthly_fee.py`, `test_unit_normalization.py`, `test_price_validity_boundary.py`) call `A1Strategy.calculate()` and pure model functions directly, with hand-built fixtures - no Home Assistant import beyond `homeassistant.core.State`/`Enum` types that don't require a running instance. This is what the spec asks for explicitly ("tariff-engine tests should be possible without booting the complete Home Assistant entity layer wherever practical") and it's what keeps the core quota/proration/boundary-split math trivially reviewable in isolation.
2. **HA-boot integration tests** (`test_config_flow.py`, `test_integration_setup.py`, `test_sensor_descriptions.py`) use `pytest-homeassistant-custom-component`'s lightweight test `hass` fixture to drive the real config flow, `async_setup_entry`, live state-change handling, and entity creation - proving the *wiring*, not just the math. This layer is what caught two real bugs during development that the headless tests structurally couldn't: A1 missing from the tariff-plan catalog (so it was unselectable), and the device name leaking an internal id into the user-visible entity names.
3. **Docker-compose e2e smoke test** (`tests/e2e/`) boots the actual `homeassistant/home-assistant` container image with this integration volume-mounted, and asserts the frontend comes up with no import/setup traceback for the domain. This is the only layer that would catch a `manifest.json` or packaging mistake that only breaks on a real HA install, as opposed to the test-harness's approximation of one.

Coverage (`pyproject.toml`'s `[tool.coverage.*]`, enforced in CI) targets 80% as a floor, not a goal in itself - it's a proxy for "the HA-boot layer actually exercises `config_flow.py`/`sensor.py`/`coordinator.py`/`__init__.py`", which the headless layer structurally cannot, by design.

## Versioning and release automation

See [RELEASING.md](RELEASING.md) for the label-driven tag/release mechanism and why release notes still need a human/agent pass after the automated tag.
