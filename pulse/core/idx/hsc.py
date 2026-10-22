"""High Shareholding Concentration (HSC) list published by BEI."""

import json
from functools import lru_cache

from pulse.core.idx import DATA_DIR

HSC_FILE = DATA_DIR / "hsc.json"


@lru_cache(maxsize=1)
def load_hsc() -> tuple[str, frozenset[str]]:
    """Return (as_of, tickers) from data/hsc.json."""
    with open(HSC_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data["as_of"], frozenset(t.upper() for t in data["tickers"])


def is_hsc(ticker: str) -> bool:
    """Check whether a ticker is on the HSC list."""
    return ticker.upper() in load_hsc()[1]
