"""Free float & shareholder concentration.

Two public sources (both parsed from embedded page data, no auth needed):

* ff.klinikpenyesalan.com  - status free float resmi BEI (Peraturan I-A/I-V),
  posisi laporan bulanan registrasi pemegang saham.
* 1pct.klinikpenyesalan.com - kepemilikan >=1% dari KSEI (snapshot bulanan).

BEI counts 1-5% holders as public, so its free float can look healthy for stocks
that are effectively closely held (e.g. BYAN 21% BEI vs 1.5% KSEI). The universe
filter therefore uses ``ff_ksei`` = 100% - total holders >=1%.
"""

import json
import re

import pandas as pd
import requests

from pulse.core.idx import OWNERSHIP_DIR
from pulse.utils.logger import get_logger

log = get_logger(__name__)

FF_URL = "https://ff.klinikpenyesalan.com/"
KSEI_URL = "https://1pct.klinikpenyesalan.com/"
OWNERSHIP_FILE = OWNERSHIP_DIR / "ownership.csv"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Pulse-CLI)"}


def _extract_json_array(text: str, key: str) -> list:
    """Extract the JSON array that follows ``"key":`` using bracket matching."""
    start = text.index("[", text.index(f'"{key}":'))
    depth = 0
    for end in range(start, len(text)):
        if text[end] == "[":
            depth += 1
        elif text[end] == "]":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : end + 1])
    raise ValueError(f"Array {key} tidak lengkap")


def parse_ff_bei(html: str) -> pd.DataFrame:
    raw = re.search(r'id="rawData"[^>]*>(.*?)</script>', html, re.S)
    if not raw:
        raise ValueError("rawData tidak ditemukan di halaman free float BEI")
    df = pd.DataFrame(json.loads(raw.group(1)))
    df = df.rename(
        columns={
            "k": "code",
            "p": "board",
            "j": "shareholders",
            "f": "ff_bei",
            "w": "ff_required",
            "b": "ff_status",
        }
    )
    return df[["code", "board", "shareholders", "ff_bei", "ff_required", "ff_status"]]


def parse_ksei(html: str) -> tuple[pd.DataFrame, str | None]:
    for chunk in re.findall(r"self\.__next_f\.push\((\[1,.*?\])\)</script>", html, re.S):
        payload = json.loads(chunk)[1]
        if '"stockGroups"' not in payload:
            continue
        df = pd.DataFrame(_extract_json_array(payload, "stockGroups"))
        m = re.search(r'"currentDate":"([\d-]+)"', html.replace('\\"', '"'))
        df = df.rename(
            columns={
                "share_code": "code",
                "freeFloat": "ff_ksei",
                "cr1": "top1_pct",
                "holderCount": "holders_1pct",
                "ownershipType": "ownership_type",
            }
        )
        cols = [
            "code",
            "ff_ksei",
            "top1_pct",
            "holders_1pct",
            "ownership_type",
            "sector",
            "industry",
        ]
        return df[cols], (m.group(1) if m else None)
    raise ValueError("stockGroups tidak ditemukan di halaman KSEI")


def fetch_ownership(timeout: int = 60) -> pd.DataFrame:
    """Download both sources, merge, and save to data/ownership/ownership.csv."""
    ff = parse_ff_bei(requests.get(FF_URL, headers=_HEADERS, timeout=timeout).text)
    ksei, snapshot = parse_ksei(requests.get(KSEI_URL, headers=_HEADERS, timeout=timeout).text)
    df = ff.merge(ksei, on="code", how="outer")
    df["ksei_snapshot"] = snapshot
    OWNERSHIP_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OWNERSHIP_FILE, index=False)
    log.info(f"Ownership: {len(ff)} emiten BEI, {len(ksei)} emiten KSEI (snapshot {snapshot})")
    return df


def load_ownership(refresh: bool = False) -> pd.DataFrame:
    """Load cached ownership data, fetching it first if missing or ``refresh``."""
    if refresh or not OWNERSHIP_FILE.exists():
        return fetch_ownership()
    return pd.read_csv(OWNERSHIP_FILE)
