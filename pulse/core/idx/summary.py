"""IDX daily trading summary (Ringkasan Saham).

idx.co.id protects its JSON API with Cloudflare bot detection, so Pulse does not
scrape it. Instead, download the daily Excel file from
https://www.idx.co.id/id/data-pasar/ringkasan-perdagangan/ringkasan-saham/
(updated ~17:00 WIB on trading days) and drop it into ``data/idx/``.
"""

import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from pulse.core.idx import IDX_DIR
from pulse.utils.logger import get_logger

log = get_logger(__name__)

HISTORY_FILE = IDX_DIR / "history.csv.gz"

COLUMN_MAP = {
    "Kode Saham": "code",
    "Nama Perusahaan": "name",
    "Remarks": "remarks",
    "Sebelumnya": "prev_close",
    "Open Price": "open",
    "Tanggal Perdagangan Terakhir": "last_trade_date",
    "First Trade": "first_trade",
    "Tertinggi": "high",
    "Terendah": "low",
    "Penutupan": "close",
    "Selisih": "change",
    "Volume": "volume",
    "Nilai": "value",
    "Frekuensi": "frequency",
    "Index Individual": "index_individual",
    "Offer": "offer",
    "Offer Volume": "offer_volume",
    "Bid": "bid",
    "Bid Volume": "bid_volume",
    "Listed Shares": "listed_shares",
    "Tradeble Shares": "tradable_shares",
    "Weight For Index": "weight_for_index",
    "Foreign Sell": "foreign_sell",
    "Foreign Buy": "foreign_buy",
    "Non Regular Volume": "nonreg_volume",
    "Non Regular Value": "nonreg_value",
    "Non Regular Frequency": "nonreg_frequency",
}

_FILE_DATE = re.compile(r"(\d{8})")


def parse_summary_file(path: Path) -> pd.DataFrame:
    """Parse one 'Ringkasan Saham-YYYYMMDD.xlsx' file into a normalized DataFrame."""
    df = pd.read_excel(path).rename(columns=COLUMN_MAP)
    missing = {"code", "close", "listed_shares"} - set(df.columns)
    if missing:
        raise ValueError(f"{path.name}: kolom tidak ditemukan {sorted(missing)}")

    m = _FILE_DATE.search(path.stem)
    if m:
        trade_date = datetime.strptime(m.group(1), "%Y%m%d").date()
    else:
        trade_date = pd.to_datetime(df["last_trade_date"], format="%d %b %Y").max().date()

    df = df.drop(columns=["No"], errors="ignore")
    df.insert(0, "date", pd.Timestamp(trade_date))
    df["code"] = df["code"].str.strip().str.upper()
    df["market_cap"] = df["close"] * df["listed_shares"]
    df["foreign_net"] = df["foreign_buy"] - df["foreign_sell"]
    return df


def summary_files() -> list[Path]:
    """All IDX summary Excel files in data/idx, oldest first."""
    return sorted(IDX_DIR.glob("Ringkasan Saham-*.xlsx"))


def latest_summary() -> pd.DataFrame | None:
    """Parse the most recent summary file, or None if no file exists."""
    files = summary_files()
    if not files:
        log.warning(f"Belum ada file Ringkasan Saham di {IDX_DIR}")
        return None
    return parse_summary_file(files[-1])


def update_history() -> pd.DataFrame:
    """Merge every summary file into data/idx/history.csv.gz (idempotent)."""
    frames = []
    if HISTORY_FILE.exists():
        frames.append(pd.read_csv(HISTORY_FILE, parse_dates=["date"]))
    known = set(frames[0]["date"].dt.date) if frames else set()

    for path in summary_files():
        df = parse_summary_file(path)
        if df["date"].iloc[0].date() not in known:
            frames.append(df)
            log.info(f"Menambahkan {path.name}")

    if not frames:
        return pd.DataFrame()
    hist = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(["date", "code"], keep="last")
        .sort_values(["date", "code"])
    )
    hist.to_csv(HISTORY_FILE, index=False)
    return hist


def foreign_flow(ticker: str, days: int = 20) -> pd.DataFrame:
    """Daily foreign buy/sell/net for a ticker from the accumulated history."""
    if not HISTORY_FILE.exists():
        return pd.DataFrame()
    hist = pd.read_csv(HISTORY_FILE, parse_dates=["date"])
    rows = hist[hist["code"] == ticker.upper()].tail(days)
    return rows[["date", "close", "value", "foreign_buy", "foreign_sell", "foreign_net"]]


def history_dates() -> list[date]:
    """Trading dates available in the accumulated history."""
    if not HISTORY_FILE.exists():
        return []
    return sorted(
        pd.read_csv(HISTORY_FILE, usecols=["date"], parse_dates=["date"])["date"].dt.date.unique()
    )
