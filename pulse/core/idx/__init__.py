"""IDX big-cap data layer and swing analysis.

Modules:
    summary    - Ringkasan Saham harian IDX (file Excel unduhan idx.co.id)
    ownership  - Free float resmi BEI & kepemilikan >=1% KSEI
    hsc        - Daftar High Shareholding Concentration (HSC)
    universe   - Universe big cap (market cap, free float riil, likuiditas, non-HSC)
    prices     - Panel harga OHLCV (Yahoo Finance) dengan cache lokal
    benchmark  - IHSG ex-HSC
    swing      - Screener & backtest swing 2-8 minggu
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = BASE_DIR / "data"
IDX_DIR = DATA_DIR / "idx"
OWNERSHIP_DIR = DATA_DIR / "ownership"
UNIVERSE_DIR = DATA_DIR / "universe"
PRICE_CACHE_DIR = DATA_DIR / "cache" / "prices"
