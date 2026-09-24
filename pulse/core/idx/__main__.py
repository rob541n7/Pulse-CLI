"""Batch entry point, e.g. for a scheduled task after 17:00 WIB.

python -m pulse.core.idx update          # gabungkan file Excel IDX baru ke histori
python -m pulse.core.idx ownership       # ambil ulang free float BEI & KSEI (bulanan)
python -m pulse.core.idx universe [70]   # bangun ulang universe big cap
python -m pulse.core.idx ihsgx           # IHSG vs IHSG ex-HSC
python -m pulse.core.idx swing [TICKER]  # screener swing / analisa satu saham
python -m pulse.core.idx backtest [--nofilter]
python -m pulse.core.idx dashboard [--open]  # bangun data/reports/dashboard.html
python -m pulse.core.idx daily [--open]  # update + ihsgx + swing + dashboard
"""

import sys

from pulse.core.idx import swing
from pulse.core.idx.benchmark import build_ihsg_ex_hsc, format_benchmark
from pulse.core.idx.dashboard import build_dashboard
from pulse.core.idx.ownership import fetch_ownership
from pulse.core.idx.summary import update_history
from pulse.core.idx.universe import UniverseRules, build_universe, format_universe


def _swing(args: list[str]) -> str:
    params = swing.SwingParams(market_filter="--nofilter" not in args)
    ind, bench, mcap = swing.load_market(params)
    if args and args[0] == "backtest":
        return swing.format_backtest(swing.backtest(ind, mcap, bench, params))
    snap = swing.screen(ind, swing.current_universe(), params)
    tickers = [a for a in args if not a.startswith("-")]
    return swing.format_ticker(tickers[0].upper(), snap) if tickers else swing.format_screen(snap)


def main(argv: list[str]) -> None:
    cmd, args = (argv[0], argv[1:]) if argv else ("daily", [])
    if cmd in ("update", "daily"):
        hist = update_history()
        if len(hist):
            print(
                f"Histori IDX: {hist.date.nunique()} hari bursa, terakhir {hist.date.max().date()}"
            )
    if cmd == "ownership":
        df = fetch_ownership()
        print(f"Ownership tersimpan: {len(df)} emiten")
    elif cmd == "universe":
        size = int(args[0]) if args else 70
        print(format_universe(build_universe(UniverseRules(size=size), refresh_ownership=True)))
    elif cmd == "ihsgx":
        print(format_benchmark(build_ihsg_ex_hsc(refresh=True)))
    elif cmd == "swing":
        print(_swing(args))
    elif cmd == "backtest":
        print(_swing(["backtest", *args]))
    elif cmd == "dashboard":
        print(f"Dashboard: {build_dashboard(open_browser='--open' in args)}")
    elif cmd == "daily":
        print(format_benchmark(build_ihsg_ex_hsc(refresh=True)))
        print()
        print(_swing([]))
        print(f"\nDashboard: {build_dashboard(open_browser='--open' in args, update=False)}")
    elif cmd != "update":
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
