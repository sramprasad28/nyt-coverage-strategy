import json
import os
import tempfile
import threading
import urllib.request
from pathlib import Path

from app.analytics import _focus_card, build_dashboard
from app.config import iter_months, month_count
from app.db import connect, store_month, store_popular
from app.parse_nyt import article_from_doc, popular_from_result
from app.server import Handler
from app.urls import canonical_url
from http.server import ThreadingHTTPServer


def article(slug, subject, region, material):
    url = f"https://nytimes.com/2026/01/01/{slug}.html"
    return {
        "canonical_url": url,
        "url": url,
        "uri": slug,
        "pub_date": "2026-01-01T00:00:00+0000",
        "headline": slug,
        "abstract": "",
        "section_name": "World",
        "news_desk": "Foreign",
        "subsection_name": "",
        "type_of_material": material,
        "document_type": "article",
        "byline": "",
        "word_count": 100,
        "tags": [("subject", subject), ("glocations", region)],
    }


def url_for(slug):
    return f"https://nytimes.com/2026/01/01/{slug}.html"


def populate_demo(connection):
    groups = [
        (20, "Artificial Intelligence", "United States", "News", "ai-us"),
        (20, "Artificial Intelligence", "Kenya", "Interactive Feature", "ai-ke"),
        (30, "Elections", "China", "News", "el-cn"),
        (15, "Weather", "United States", "News", "we-us"),
        (15, "Weather", "France", "Op-Ed", "we-fr"),
    ]
    articles = []
    for count, subject, region, material, prefix in groups:
        for index in range(count):
            articles.append(article(f"{prefix}-{index}", subject, region, material))
    store_month(connection, 2026, 1, articles)
    with connection:
        for year, month in iter_months():
            if (year, month) == (2026, 1):
                continue
            connection.execute(
                "INSERT OR REPLACE INTO archive_months (year, month, article_count, fetched_at) VALUES (?,?,0,'test')",
                (year, month),
            )
    slugs = [f"ai-us-{index}" for index in range(5)]
    slugs += [f"ai-ke-{index}" for index in range(3)]
    slugs += [f"el-cn-{index}" for index in range(2)]
    rows = []
    for rank, slug in enumerate(slugs, start=1):
        rows.append(
            {
                "list_name": "viewed",
                "period": 30,
                "rank": rank,
                "canonical_url": url_for(slug),
                "title": "",
                "section": "World",
                "published_date": "2026-01-01",
                "views": 1000 - rank,
                "share_count": None,
                "tags": [],
            }
        )
    rows.append(
        {
            "list_name": "viewed",
            "period": 1,
            "rank": 1,
            "canonical_url": url_for("ai-us-0"),
            "title": "",
            "section": "World",
            "published_date": "2026-01-01",
            "views": 5000,
            "share_count": None,
            "tags": [],
        }
    )
    store_popular(connection, rows)


def check_parsers():
    assert month_count() == 10
    assert canonical_url("https://www.nytimes.com/2026/10/01/world/foo.html?smid=tw") == "https://nytimes.com/2026/10/01/world/foo.html"
    assert canonical_url("http://nytimes.com/2026/10/01/world/foo.html/") == "https://nytimes.com/2026/10/01/world/foo.html"
    assert canonical_url("https://WWW.NYTIMES.COM/") == "https://nytimes.com"
    assert canonical_url("") is None
    parsed = article_from_doc(
        {
            "web_url": "https://www.nytimes.com/2026/10/01/technology/ai.html?smid=tw",
            "headline": {"main": "AI story"},
            "section_name": "Technology",
            "news_desk": "Business",
            "type_of_material": "News",
            "word_count": "800",
            "keywords": [
                {"name": "subject", "value": "Artificial Intelligence"},
                {"name": "glocations", "value": "Kenya"},
            ],
        },
        2026,
        10,
    )
    assert parsed["canonical_url"] == "https://nytimes.com/2026/10/01/technology/ai.html"
    assert parsed["headline"] == "AI story"
    assert ("subject", "Artificial Intelligence") in parsed["tags"]
    popular = popular_from_result(
        {
            "url": "https://www.nytimes.com/2026/10/01/technology/ai.html",
            "title": "AI story",
            "geo_facet": "Kenya",
            "des_facet": ["Artificial Intelligence"],
            "views": "1000",
        },
        "viewed",
        1,
        1,
    )
    assert popular["views"] == 1000
    assert ("glocations", "Kenya") in popular["tags"]
    cautious = _focus_card(
        "Format",
        [{
            "tag": "News",
            "lift": 1.05,
            "popular_pct": 70,
            "archive_pct": 68,
            "popular_articles": 7,
            "archive_articles": 68,
        }],
        10,
        "format",
        "",
    )
    assert "Keep the current format mix" in cautious["body"]


def check_dashboard(connection):
    empty = build_dashboard(connection)
    assert empty["section1"]["ready"] is False
    assert empty["recommendations"]["ready"] is False
    populate_demo(connection)
    payload = build_dashboard(connection)
    section1 = payload["section1"]
    assert section1["ready"] is True
    assert section1["archive_articles"] == 100
    assert section1["popular_articles"] == 10
    assert section1["matched_articles"] == 10
    assert section1["partial"] is False
    assert section1["topics"][0]["tag"] == "Artificial Intelligence"
    assert section1["topics"][0]["lift"] == 2.0
    assert section1["regions"][0]["tag"] == "United States"
    assert section1["formats"][0]["tag"] == "Interactive Feature"
    assert section1["stories"][0]["title"] == "ai-us-0"
    assert section1["stories"][0]["views"] == 5000
    cards = payload["recommendations"]["cards"]
    assert [card["area"] for card in cards] == ["Topical", "Regional", "Format"]
    assert "Put more reporting weight on Artificial Intelligence" in cards[0]["body"]
    assert "incomplete" not in cards[0]["body"]
    assert "Give United States more reporting weight" in cards[1]["body"]
    assert "United States" in cards[1]["body"]
    assert "Prefer Interactive Feature" in cards[2]["body"]
    return payload


def check_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/dashboard") as response:
            payload = json.load(response)
        assert payload["recommendations"]["ready"] is True
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as response:
            html = response.read().decode("utf-8")
        assert "What's popular with NYT readers" in html
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/static/app.js") as response:
            assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()


def main():
    check_parsers()
    previous = os.environ.get("STRATEGY_DB")
    with tempfile.TemporaryDirectory() as directory:
        os.environ["STRATEGY_DB"] = str(Path(directory) / "strategy.sqlite")
        connection = connect()
        try:
            check_dashboard(connection)
        finally:
            connection.close()
        check_server()
    if previous is None:
        os.environ.pop("STRATEGY_DB", None)
    else:
        os.environ["STRATEGY_DB"] = previous
    print("ok")


if __name__ == "__main__":
    main()
