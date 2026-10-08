"""Daily OHLCV panel for many IDX tickers, cached locally.

Yahoo Finance close/volume matched the official IDX summary for 100/100 big caps
(23 Sep 2026). Differences only appear in Open when IDX records 0 (no pre-opening
match) - Yahoo fills it with the first trade.

Yahoo rate-limits large requests (HTTP 429), so the cache is updated incrementally:
only the last few days are re-downloaded for cached tickers, new tickers get full
history, requests go out in chunks with pauses and retries, and an empty or failed
download never overwrites a good cache.
"""

import time as _time
from datetime import date, datetime, time, timedelta, timezone

import pandas as pd
import yfinance as yf

from pulse.core.idx import PRICE_CACHE_DIR
from pulse.utils.logger import get_logger

log = get_logger(__name__)

WIB = timezone(timedelta(hours=7))  # tanpa DST; hindari ketergantungan tzdata di Windows
MARKET_CLOSE = time(16, 15)  # data dianggap final setelah jam ini
FIELDS = ("open", "high", "low", "close", "volume")

CHUNK_SIZE = 150  # ticker per request ke Yahoo
CHUNK_PAUSE_S = 2.0  # jeda antar request
RETRY_WAITS_S = (10, 30, 90)  # jeda sebelum mencoba ulang request yang ditolak / kosong
OVERLAP_DAYS = 10  # hari terakhir yang diunduh ulang (koreksi data Yahoo, split)


class PriceDownloadError(RuntimeError):
    """Yahoo returned no usable data (often HTTP 429 rate limiting)."""


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


def _is_valid(panel: dict | None) -> bool:
    return bool(panel) and len(panel["close"]) > 0 and panel["close"].notna().any().any()


def _load_cache(name: str) -> dict | None:
    path = _cache_file(name)
    if not path.exists():
        return None
    try:
        panel = pd.read_pickle(path)
    except Exception as e:  # noqa: BLE001
        log.warning(f"Cache harga {path.name} tidak terbaca ({e}), diabaikan")
        return None
    return panel if _is_valid(panel) else None


def _save_cache(name: str, panel: dict) -> None:
    PRICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_file(name)
    tmp = path.with_suffix(".tmp")
    pd.to_pickle(panel, tmp)
    tmp.replace(path)  # atomik: cache lama tidak pernah setengah tertulis


def _symbol(t: str) -> str:
    return t if t.startswith("^") else f"{t}.JK"


def _download_chunk(symbols: list[str], start: str) -> dict[str, pd.DataFrame]:
    """One Yahoo request with retries. Raises PriceDownloadError if it stays empty."""
    for attempt in range(len(RETRY_WAITS_S) + 1):
        try:
            raw = yf.download(symbols, start=start, auto_adjust=False, progress=False, threads=True)
        except Exception as e:  # noqa: BLE001
            log.warning(f"Yahoo error: {e}")
            raw = None
        if raw is not None and not raw.empty and raw["Close"].notna().any().any():
            out = {}
            for f in FIELDS:
                df = raw[f.capitalize()]
                if isinstance(df, pd.Series):  # satu ticker -> Series
                    df = df.to_frame(symbols[0])
                df = df.copy()
                df.columns = [str(c).removesuffix(".JK") for c in df.columns]
                out[f] = df
            return out
        if attempt < len(RETRY_WAITS_S):
            wait = RETRY_WAITS_S[attempt]
            log.warning(
                f"Yahoo menolak/ kosong (kemungkinan rate limit). Coba lagi dalam {wait} dtk..."
            )
            _time.sleep(wait)
    raise PriceDownloadError(
        "Yahoo Finance tidak mengembalikan data (kemungkinan dibatasi / HTTP 429). "
        "Tunggu 15-60 menit lalu jalankan lagi."
    )


def _download(tickers: list[str], start: str) -> dict[str, pd.DataFrame]:
    parts: dict[str, list] = {f: [] for f in FIELDS}
    chunks = [tickers[i : i + CHUNK_SIZE] for i in range(0, len(tickers), CHUNK_SIZE)]
    log.info(f"Mengunduh {len(tickers)} ticker dari {start} ({len(chunks)} request)...")
    for i, chunk in enumerate(chunks):
        got = _download_chunk([_symbol(t) for t in chunk], start)
        for f in FIELDS:
            parts[f].append(got[f])
        if i < len(chunks) - 1:
            _time.sleep(CHUNK_PAUSE_S)
    return {f: pd.concat(parts[f], axis=1) for f in FIELDS}


def _merge(old: dict | None, new: dict) -> dict:
    if old is None:
        return new
    merged = {}
    for f in FIELDS:
        df = new[f].combine_first(old[f])  # data baru menang di tanggal yang tumpang tindih
        merged[f] = df.loc[:, ~df.columns.duplicated()].sort_index()
    return merged


def fetch_panel(
    tickers: list[str],
    start: str = "2023-01-01",
    name: str = "panel",
    refresh: bool = False,
    full: bool = False,
) -> dict[str, pd.DataFrame]:
    """Return {field: DataFrame(date x ticker)} for IDX tickers (without .JK).

    Index symbols starting with '^' are passed through unchanged. Bars after the last
    complete session are dropped so intraday data never leaks in.

    refresh: re-download the last OVERLAP_DAYS even if the cache looks current.
    full:    ignore the cache and download everything from ``start``.
    """
    cutoff = pd.Timestamp(last_complete_session())
    cache = None if full else _load_cache(name)

    # Kolom yang sudah pernah dicoba (termasuk saham delisting tanpa data) tidak diunduh penuh lagi
    cached_cols = set() if cache is None else set(cache["close"].columns)
    missing = [t for t in tickers if t not in cached_cols]
    stale = cache is not None and (refresh or cache["close"].index.max() < cutoff)

    if cache is not None and not missing and not stale:
        return {f: cache[f].reindex(columns=tickers).loc[:cutoff] for f in FIELDS}

    try:
        new = None
        if stale:
            recent = (cache["close"].index.max() - timedelta(days=OVERLAP_DAYS)).date()
            have = [t for t in tickers if t in cached_cols]
            new = _download(have, str(max(recent, pd.Timestamp(start).date())))
        if missing:
            got = _download(missing, start)
            new = got if new is None else _merge(new, got)
    except PriceDownloadError:
        if cache is None:
            raise
        log.warning(
            f"Update harga gagal; memakai cache s/d {cache['close'].index.max().date()} "
            "(jalankan lagi nanti)"
        )
        return {f: cache[f].reindex(columns=tickers).loc[:cutoff] for f in FIELDS}

    panel = _merge(cache, new)
    cols = list(dict.fromkeys([*panel["close"].columns, *tickers]))
    panel = {f: df.reindex(columns=cols).loc[:cutoff] for f, df in panel.items()}
    if not _is_valid(panel):
        raise PriceDownloadError("Hasil unduhan kosong; cache tidak diubah.")
    _save_cache(name, panel)
    return {f: panel[f].reindex(columns=tickers) for f in FIELDS}
