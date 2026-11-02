import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_START = (2026, 1)
ARCHIVE_END = (2026, 10)
WINDOW_LABEL = "January–October 2026"


def load_env():
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


def require_env(name):
    load_env()
    value = os.environ.get(name, "").strip()
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    if not value:
        raise SystemExit(f"{name} is not set.")
    return value


def db_path():
    override = os.environ.get("STRATEGY_DB")
    if override:
        return Path(override)
    return ROOT / "data" / "strategy.sqlite"


def iter_months():
    year, month = ARCHIVE_START
    end_year, end_month = ARCHIVE_END
    while (year, month) <= (end_year, end_month):
        yield year, month
        month += 1
        if month == 13:
            month = 1
            year += 1


def month_count():
    return sum(1 for _ in iter_months())
