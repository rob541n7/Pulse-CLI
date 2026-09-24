"""Daily OHLCV panel for many IDX tickers, cached locally.

Yahoo Finance close/volume matched the official IDX summary for 100/100 big caps
(23 Sep 2026). Differences only appear in Open when IDX records 0 (no pre-opening
match) - Yahoo fills it with the first trade.
"""

from datetime import date, datetime, time, timedelta, timezone

import pandas as pd
import yfinance as yf

from pulse.core.idx import PRICE_CACHE_DIR
from pulse.utils.logger import get_logger

log = get_logger(__name__)

WIB = timezone(timedelta(hours=7))  # tanpa DST; hindari ketergantungan tzdata di Windows
MARKET_CLOSE = time(16, 15)  # data dianggap final setelah jam ini
FIELDS = ("open", "high", "low", "close", "volume")


def last_complete_session(now: datetime | None = None) -> date:
    """Latest date whose daily bar is final (today only after market close, WIB)."""
    now = now or datetime.now(WIB)
    d = now.date()
    if now.time() < MARKET_CLOSE:
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _cache_file(name: str):
    return PRICE_CACHE_DIR / f"{name}.pkl"


def fetch_panel(
    tickers: list[str],
    start: str = "2023-01-01",
    name: str = "panel",
    refresh: bool = False,
) -> dict[str, pd.DataFrame]:
    """Return {field: DataFrame(date x ticker)} for IDX tickers (without .JK).

    Index symbols starting with '^' are passed through unchanged.
    Bars after the last complete session are dropped so intraday data never leaks in.
    """
    cutoff = pd.Timestamp(last_complete_session())
    path = _cache_file(name)
    if not refresh and path.exists():
        panel = pd.read_pickle(path)
        cached = set(panel["close"].columns)
        if panel["close"].index.max() >= cutoff and set(tickers) <= cached:
            return {f: panel[f][tickers] for f in FIELDS}

    symbols = [t if t.startswith("^") else f"{t}.JK" for t in tickers]
    log.info(f"Mengunduh harga {len(symbols)} ticker dari Yahoo Finance...")
    raw = yf.download(symbols, start=start, auto_adjust=False, progress=False, threads=True)
    panel = {}
    for f in FIELDS:
        df = raw[f.capitalize()].copy()
        df.columns = [c.removesuffix(".JK") for c in df.columns]
        panel[f] = df.loc[:cutoff].reindex(columns=tickers)

    PRICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pd.to_pickle(panel, path)
    return panel
