"""Auto rejection limits per BEI press releases 095 and 096 (Oct 2026)."""

from datetime import date

import pytest

from pulse.core.idx.rules import arb_pct, auto_rejection

BEFORE, D19, D20 = date(2026, 10, 16), date(2026, 10, 19), date(2026, 10, 20)


@pytest.mark.parametrize(
    "price,on,ara,arb",
    [
        (6300, BEFORE, 7550, 5375),  # >5.000: ARA 20%, ARB 15% (lama)
        (6300, D19, 7550, 5875),  # ARB 7% -> 5.859 dibulatkan ke atas ke tick 25
        (3000, D20, 3750, 2790),  # 200-5.000: ARA 25%, ARB 7%
        (100, D20, 135, 93),  # 15-200: ARA 35%, ARB 7%
        (12, D20, 16, 11),  # Rp11-14: ARB Rp1 sejak 20 Okt
        (12, D19, 16, 12),  # 19 Okt: 7% dari 12 = 11,16 -> naik ke 12
        (8, D20, 9, 7),  # Rp1-10: Rp1
    ],
)
def test_auto_rejection(price, on, ara, arb):
    assert auto_rejection(price, on) == (ara, arb)


def test_arb_pct_is_about_seven_after_change():
    assert 6.5 < arb_pct(6300, D20) < 7.0
    assert 14.5 < arb_pct(6300, BEFORE) < 15.0
