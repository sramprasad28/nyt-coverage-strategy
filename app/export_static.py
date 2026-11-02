import json
import shutil
from pathlib import Path

from app.analytics import build_dashboard
from app.db import connect

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app" / "static"
TARGET = ROOT / "docs"


def main():
    connection = connect()
    try:
        payload = build_dashboard(connection)
    finally:
        connection.close()
    if not payload["status"]["nyt_ready"]:
        raise SystemExit("The archive and Most Popular lists are not loaded yet. Run the ingest first.")

    if TARGET.exists():
        shutil.rmtree(TARGET)
    (TARGET / "static").mkdir(parents=True)
    shutil.copy(SOURCE / "index.html", TARGET / "index.html")
    for name in ("styles.css", "app.js"):
        shutil.copy(SOURCE / name, TARGET / "static" / name)
    (TARGET / "static" / "dashboard.json").write_text(json.dumps(payload), encoding="utf-8")
    (TARGET / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Wrote {TARGET}")


if __name__ == "__main__":
    main()
