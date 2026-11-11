"""Build the standalone "Pulse Swing" package from pulse/core/idx.

    python scripts/build_release.py 1.2 [output_dir]

Writes <output_dir>/Pulse-Swing-Release (default: next to this repo) and
Pulse_Swing_v<version>.zip. Broker flow (Stockbit) and the claude.ai artifact export are
left out; everything else is the same code with package paths rewritten.
"""

import shutil
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "pulse" / "core" / "idx"
MODULES = [
    "__init__", "__main__", "benchmark", "dashboard", "factors", "fundamentals", "hsc",
    "ingest", "ownership", "prices", "rules", "summary", "swing", "universe",
]  # fmt: skip
DATA_FILES = [
    "hsc.json",
    "idx/ihsg_constituents.csv",
    "idx/ihsg_official.csv",
    "universe/bigcap.json",
]
EMPTY_DIRS = ["cache/prices", "fundamentals", "idx", "ownership", "reports", "universe/snapshots"]

LOG_PY = '''"""Simple logging for Pulse Swing."""
import logging


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
        logger.addHandler(h)
        logger.setLevel(level)
        logger.propagate = False
    return logger
'''


def cut(text: str, start: str, end: str) -> str:
    """Remove text from `start` up to (not including) `end`; both must exist."""
    a = text.index(start)
    return text[:a] + text[text.index(end, a) :]


def swap(text: str, old: str, new: str) -> str:
    assert old in text, old[:70]
    return text.replace(old, new)


def module(name: str) -> str:
    s = (SRC / f"{name}.py").read_text(encoding="utf-8")
    s = s.replace("pulse.core.idx", "pulse_swing").replace("pulse.utils.logger", "pulse_swing.log")
    if name == "__init__":
        s = swap(s, "parents[3]", "parents[1]")
    if name == "dashboard":
        s = swap(s, "import DATA_DIR, brokerflow, factors,", "import DATA_DIR, factors,")
        s = swap(
            s,
            "bf = brokerflow.load(str(price_date)) or {}",
            "bf = {}  # broker flow tidak disertakan di versi ini",
        )
    if name == "__main__":
        s = swap(
            s,
            "python -m pulse_swing broker             # broker flow 70 big cap (token Stockbit milik pengguna)\n",
            "",
        )
        s = swap(
            s,
            "python -m pulse_swing artifact-export   # salin dashboard lokal -> data/reports/artifact/*.json\n",
            "",
        )
        s = cut(s, "def _broker() -> str:", "def _monthly_lock()")
        s = cut(s, '    elif cmd == "artifact-export":', '    elif cmd == "dashboard":')
        s = swap(s, '    elif cmd == "broker":\n        print(_broker())\n', "")
        s = swap(
            s, "        _monthly_lock()\n        print(_broker())\n", "        _monthly_lock()\n"
        )
    assert "brokerflow" not in s and "artifact" not in s and "pulse.core" not in s, name
    return s


def template() -> str:
    s = (SRC / "dashboard_template.html").read_text(encoding="utf-8")
    a = s.index('  ["broker", "Broker 20h"')
    s = s[:a] + s[s.index("\n", a) + 1 :]
    a = s.index("  <b>Broker:</b>")
    s = s[:a] + "  " + s[s.index("<b>ARB</b>", a) :]
    assert "Stockbit" not in s
    return s


def build(version: str, out_root: Path) -> Path:
    rel = out_root / "Pulse-Swing-Release"
    pkg = rel / "pulse_swing"
    if pkg.exists():
        shutil.rmtree(pkg)
    pkg.mkdir(parents=True)
    for name in MODULES:
        (pkg / f"{name}.py").write_text(module(name), encoding="utf-8", newline="\n")
    (pkg / "log.py").write_text(LOG_PY, encoding="utf-8", newline="\n")
    (pkg / "dashboard_template.html").write_text(template(), encoding="utf-8", newline="\n")

    js = (REPO / "scripts" / "idx_browser_extract.js").read_text(encoding="utf-8")
    js = swap(js, "`python -m pulse.core.idx daily` picks", "`run_daily.bat` picks")
    js = swap(
        js,
        "Move the downloaded file to Pulse-CLI/data/fundamentals/ and run update_dashboard.bat",
        "Run run_daily.bat (it takes the file from your Downloads folder)",
    )
    (rel / "scripts").mkdir(exist_ok=True)
    (rel / "scripts" / "idx_browser_extract.js").write_text(js, encoding="utf-8", newline="\n")

    for d in EMPTY_DIRS:
        (rel / "data" / d).mkdir(parents=True, exist_ok=True)
    for f in DATA_FILES:
        shutil.copyfile(REPO / "data" / f, rel / "data" / f)
    for snap in sorted((REPO / "data" / "universe" / "snapshots").glob("bigcap_*.json")):
        shutil.copyfile(snap, rel / "data" / "universe" / "snapshots" / snap.name)

    for f in (
        "README.md",
        "LICENSE",
        "requirements.txt",
        "setup.bat",
        "first_run.bat",
        "run_daily.bat",
    ):
        assert (rel / f).exists(), f"{f} belum ada di {rel}"
    assert f"v{version}" in (rel / "README.md").read_text(encoding="utf-8"), (
        "README belum v" + version
    )

    zpath = out_root / f"Pulse_Swing_v{version}.zip"
    assert not zpath.exists(), f"{zpath.name} sudah ada; hapus atau naikkan versi"
    keep_data = {rel / "data" / f for f in DATA_FILES} | set(
        (rel / "data" / "universe" / "snapshots").glob("bigcap_*.json")
    )
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for d in EMPTY_DIRS:
            z.writestr(f"data/{d}/", "")
        for p in sorted(rel.rglob("*")):
            if p.is_dir() or "__pycache__" in p.parts or ".venv" in p.parts:
                continue
            if (rel / "data") in p.parents and p not in keep_data:
                continue  # data pengguna (harga, ringkasan, dashboard) tidak ikut
            z.write(p, p.relative_to(rel).as_posix())
    return zpath


if __name__ == "__main__":
    ver = sys.argv[1]
    root = Path(sys.argv[2]) if len(sys.argv) > 2 else REPO.parent
    print(build(ver, root))
