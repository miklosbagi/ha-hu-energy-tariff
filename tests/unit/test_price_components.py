"""PriceComponents.effective_gross_price() must apply VAT exactly once,
on the sum of all net components - never on an already-gross figure.
Regression test for a real bug: an earlier revision of const.py's A1
defaults held gross (VAT-included) numbers in these fields, which this
function then grossed up a second time, overcharging every computed
price by ~27%.

Reference numbers are MVM's official A1 residential price sheet
(net energy + net "Elosztási és átviteli díjak" -> gross Ft/kWh),
see const.py's DEFAULT_A1_* comments for the source.
"""
from __future__ import annotations

import pytest

from custom_components.hu_energy_tariff.models import PriceComponents


@pytest.mark.parametrize(
    ("discounted_net", "market_net", "distribution_net", "discounted", "expected_gross"),
    [
        (4.390, 31.800, 23.400, True, 35.293),  # E.ON / OPUS
        (4.390, 31.800, 23.400, False, 70.104),
        (5.250, 31.800, 23.400, True, 36.386),  # MVM Démász
        (5.110, 31.800, 23.400, True, 36.208),  # ELMŰ
        (4.940, 31.800, 23.400, True, 35.992),  # MVM Émász
    ],
)
def test_effective_gross_price_applies_vat_once(
    discounted_net, market_net, distribution_net, discounted, expected_gross
):
    price_components = PriceComponents(
        energy_charge_discounted=discounted_net,
        energy_charge_market=market_net,
        distribution_charge=distribution_net,
    )
    assert price_components.effective_gross_price(discounted=discounted) == pytest.approx(
        expected_gross, abs=1e-3
    )
