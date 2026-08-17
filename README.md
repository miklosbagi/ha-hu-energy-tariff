# Hungarian Energy Tariffs / Magyar Energia Tarifák

A Home Assistant custom integration that calculates current electricity prices, discounted-quota usage, and estimated costs for **Hungarian residential electricity tariffs**, using any existing Home Assistant grid-import energy sensor — meter/vendor agnostic, wired into the native **Energy Dashboard**.

Egy Home Assistant egyéni integráció, amely a magyarországi lakossági villamosenergia-tarifák (MVM, A1, A2, B, H) aktuális egységárát, a kedvezményes keret felhasználását és a becsült költségeket számolja ki bármely meglévő hálózati energiafogyasztás-mérő szenzor alapján, az Energy Dashboardba illesztve.

Keywords: Home Assistant, Hungary, Hungarian, MVM, MVM Next, ESZ, A1, A2, H tarifa, 2523 kWh, rezsicsökkentés, electricity tariff, electricity cost, Energy Dashboard.

## Features

- **Provider / Distribution area / Tariff / Pricing period / Meter** modeled as separable, first-class concepts — not hard-coded assumptions — so adding a new provider, DSO, or tariff scheme is a data change, not a redesign.
- **A1 tariff** (MVM/ESZ residential, flat-rate with a prorated annual discounted quota) implemented end-to-end.
- Correct **2523 kWh/tariff-year** discounted-quota proration by elapsed days (1 Aug – 31 Jul tariff year, handling both 365- and 366-day years).
- A single consumption delta that crosses the remaining-quota boundary is **split** between discounted and market price, never priced as a whole at one rate.
- Survives Home Assistant restarts and source-meter resets without double-counting.
- Price validity periods: a price change never retroactively recalculates already-accumulated cost.
- Exposes a `current_price` entity usable directly as the Energy Dashboard's grid-consumption current-price source, plus its own `total_cost` calculation (Hungarian tariff rules don't always equal `current_price × every dashboard increment`).
- Hungarian and English UI.

## Roadmap

| Prio | Tariff | Mechanism | Meters | Status |
|---|---|---|---|---|
| 0 | A1 | Quota-based, all-day flat price | 1 (main) | **Implemented** |
| 1 | A2 | Time-of-use (peak/low) + quota | 1 (main) | Reserved in catalog, not implemented |
| 1 | B Alap | Controlled "night", 8h/day, separate meter, special price, consumption limit | 2 (main + controlled) | Reserved in catalog, not implemented |
| 1 | H | Seasonal, heat pumps, separate meter | 2 | Reserved in catalog, not implemented |
| 2 | B Komfort | Controlled 12h/day | 2 | Reserved in catalog, not implemented |
| 2 | B GEO | Legacy heat pump construction, special cases | 2 | Reserved in catalog, not implemented |

Adding a tariff from this list is: implement a `TariffStrategy` subclass under `custom_components/hu_energy_tariffs/tariffs/`, register it — no changes to the config flow, coordinator, or entity layer. See `tariff_engine.py` and `tariffs/registry.py`.

### Automating tariff price updates

Regulated Hungarian electricity prices (the discounted-quota tariffs' unit prices, the 2523 kWh quota itself, VAT) are set by ministerial/MEKH decree and published by the universal service provider, not something this integration should ever fetch live — the SPEC deliberately rules out the integration scraping provider websites at runtime, since users configure their own actual contracted prices in the config UI regardless of what any default suggests.

What's worth automating instead is keeping the **defaults** in `const.py` current, as a maintainer-side task: a periodic script/GitHub Action that checks the official sources below for changes and opens a PR bumping `DEFAULT_A1_*` (and future A2/B/H defaults) — a human still reviews and merges. This is a backlog item, not yet built.

Official sources to track:
- [MVM Next – Lakossági egyetemes szolgáltatói egységárak](https://www.mvmnext.hu/aram/pages/aloldal.jsp?id=18223) (official residential unit price tables, per DSO)
- [MVM Next – Árak, árszabások](https://www.mvmnext.hu/aram/pages/aloldal.jsp?id=862) (tariff overview index)
- [4/2011. (I. 31.) NFM rendelet](https://net.jogtar.hu/jogszabaly?docid=a1100004.nfm) — the ministerial decree setting universal-service electricity pricing (legal basis for the discounted/market split and the 2523 kWh quota)
- [MEKH](https://mekh.hu/) — Magyar Energetikai és Közmű-szabályozási Hivatal, for system-usage-fee decrees (e.g. 10/2024) referenced by the distribution-charge components

## Installation

### HACS

1. HACS → Integrations → ⋮ → Custom repositories → add this repository URL, category "Integration".
2. Install "Hungarian Energy Tariffs", restart Home Assistant.

### Manual / docker-compose

Home Assistant custom integrations don't care how HA itself is deployed — copy or volume-mount this repository's `custom_components/hu_energy_tariffs/` directory into your HA config directory's `custom_components/` folder (e.g. the volume you already mount as `/config` in your `docker-compose.yml`), then restart Home Assistant.

## Configuration

Settings → Devices & Services → Add Integration → "Hungarian Energy Tariffs":

1. Pick a name and your existing grid-import energy sensor (must have `device_class: energy`, `state_class: total` or `total_increasing`).
2. Pick a provider (currently: MVM Next).
3. Pick a distribution area (E.ON, MVM/ÉMÁSZ, OPUS, E2/Démász-Édász).
4. Pick a tariff (currently: A1).
5. Set the tariff parameters (annual discounted quota, discounted/market gross Ft/kWh prices, fixed monthly fee) — defaults are pre-filled but you should confirm them against your actual contract/DSO tariff sheet.

Edit prices later via the integration's **Configure** (options) flow — this opens a new price validity period rather than overwriting the old one, so already-accumulated cost stays correct.

### Energy Dashboard wiring

Settings → Dashboards → Energy → Electricity grid → Grid consumption → "Use an entity with current price" → select this integration's `current_price` entity. Use `total_cost` if you want the integration's own cost tracking rather than the dashboard's built-in price × consumption calculation.

## Entities

`current_price` (Ft/kWh), `total_consumption`, `discounted_consumption`, `market_consumption`, `discounted_quota`, `remaining_discounted_quota`, `variable_cost`, `fixed_cost`, `total_cost` (Ft).

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

**Unit tests** (headless — no Home Assistant boot required for the tariff-engine logic):

```bash
pytest tests/unit
```

**End-to-end smoke test** (boots a real Home Assistant container via docker-compose, requires Docker):

```bash
pytest tests/e2e
```

The tariff calculation engine (`models.py`, `tariff_engine.py`, `tariffs/`) is intentionally independent of the Home Assistant entity layer, so it can be tested in isolation.

## License

MIT — see [LICENSE](LICENSE).
