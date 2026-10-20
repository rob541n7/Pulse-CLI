"""IDX trading rules that change over time: auto rejection (ARA / ARB).

Sources (idx.co.id > Berita > Siaran Pers):
- PR 095/BEI.SPR/10-2026 (Kep-00157/BEI/10-2026): ARB asymmetric 7% from 19 Oct 2026
- PR 096/BEI.SPR/10-2026 (Kep-00158/BEI/10-2026): price Rp11-14 ARB Rp1 from 20 Oct 2026
Both valid until 31 Dec 2026, then re-evaluated. Applies to Papan Utama, Pengembangan and
Ekonomi Baru; Papan Akselerasi and Pemantauan Khusus keep their own limits.
"""

import math
from dataclasses import dataclass
from datetime import date

from pulse.core.idx.swing import tick_size


@dataclass(frozen=True)
class Band:
    lo: float  # harga acuan minimum (inklusif)
    hi: float  # harga acuan maksimum (inklusif)
    ara: float | int  # persen (0.35) atau rupiah tetap (int)
    arb: float | int


# (berlaku mulai, daftar band) - urut dari terlama
SCHEDULE: list[tuple[date, list[Band]]] = [
    (
        date(2026, 1, 1),
        [  # sebelum 19 Okt 2026 (kolom "Saat Ini" di PR 095)
            Band(1, 10, 1, 1),
            Band(11, 200, 0.35, 0.15),
            Band(201, 5000, 0.25, 0.15),
            Band(5001, math.inf, 0.20, 0.15),
        ],
    ),
    (
        date(2026, 10, 19),
        [  # PR 095: ARB 7%
            Band(1, 10, 1, 1),
            Band(11, 200, 0.35, 0.07),
            Band(201, 5000, 0.25, 0.07),
            Band(5001, math.inf, 0.20, 0.07),
        ],
    ),
    (
        date(2026, 10, 20),
        [  # PR 096: Rp11-14 ARB Rp1
            Band(1, 10, 1, 1),
            Band(11, 14, 0.35, 1),
            Band(15, 200, 0.35, 0.07),
            Band(201, 5000, 0.25, 0.07),
            Band(5001, math.inf, 0.20, 0.07),
        ],
    ),
]
VALID_UNTIL = date(2026, 12, 31)


def bands_on(on: date) -> list[Band]:
    current = SCHEDULE[0][1]
    for start, bands in SCHEDULE:
        if on >= start:
            current = bands
    return current


def auto_rejection(ref_price: float, on: date) -> tuple[float, float]:
    """(ARA price, ARB price) for a reference (previous close) price on a trading date.

    Percent limits are rounded to the IDX tick inward (ARA down, ARB up), minimum price Rp1.
    """
    band = next(b for b in bands_on(on) if b.lo <= ref_price <= b.hi)

    def limit(rule, sign):
        if isinstance(rule, int):
            return ref_price + sign * rule
        raw = ref_price * (1 + sign * rule)
        t = tick_size(raw)
        return (math.floor(raw / t) if sign > 0 else math.ceil(raw / t)) * t

    return float(limit(band.ara, +1)), float(max(1, limit(band.arb, -1)))


def arb_pct(ref_price: float, on: date) -> float:
    """ARB distance as a positive percent of the reference price."""
    _, arb = auto_rejection(ref_price, on)
    return (1 - arb / ref_price) * 100
