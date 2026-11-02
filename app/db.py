import sqlite3
from datetime import datetime, timezone

from app.config import db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    canonical_url TEXT PRIMARY KEY,
    url TEXT,
    uri TEXT,
    pub_date TEXT,
    pub_year INTEGER,
    pub_month INTEGER,
    headline TEXT,
    abstract TEXT,
    section_name TEXT,
    news_desk TEXT,
    subsection_name TEXT,
    type_of_material TEXT,
    document_type TEXT,
    byline TEXT,
    word_count INTEGER
);

CREATE TABLE IF NOT EXISTS article_tags (
    canonical_url TEXT,
    tag_type TEXT,
    tag_value TEXT
);

CREATE TABLE IF NOT EXISTS archive_months (
    year INTEGER,
    month INTEGER,
    article_count INTEGER,
    fetched_at TEXT,
    PRIMARY KEY (year, month)
);

CREATE TABLE IF NOT EXISTS popular (
    list_name TEXT,
    period INTEGER,
    rank INTEGER,
    canonical_url TEXT,
    title TEXT,
    section TEXT,
    published_date TEXT,
    views INTEGER,
    share_count INTEGER,
    snapshot_at TEXT
);

CREATE TABLE IF NOT EXISTS fallback_tags (
    canonical_url TEXT,
    tag_type TEXT,
    tag_value TEXT
);

CREATE TABLE IF NOT EXISTS ingest_runs (
    source TEXT PRIMARY KEY,
    finished_at TEXT,
    detail TEXT
);

CREATE INDEX IF NOT EXISTS idx_tags_type_value ON article_tags(tag_type, tag_value);
CREATE INDEX IF NOT EXISTS idx_tags_url ON article_tags(canonical_url);
CREATE INDEX IF NOT EXISTS idx_popular_url ON popular(canonical_url);
CREATE INDEX IF NOT EXISTS idx_fallback_url ON fallback_tags(canonical_url);
"""


def utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(SCHEMA)
    return connection


def _merge_articles(articles):
    merged = {}
    for article in articles:
        url = article.get("canonical_url")
        if not url:
            continue
        existing = merged.get(url)
        if existing is None:
            merged[url] = {
                **article,
                "tags": list(article.get("tags") or []),
            }
            continue
        seen = set(existing["tags"])
        for tag in article.get("tags") or []:
            if tag not in seen:
                existing["tags"].append(tag)
                seen.add(tag)
    return list(merged.values())


def store_month(connection, year, month, articles):
    articles = _merge_articles(articles)
    with connection:
        connection.execute(
            """
            DELETE FROM article_tags
            WHERE canonical_url IN (
                SELECT canonical_url FROM articles WHERE pub_year = ? AND pub_month = ?
            )
            """,
            (year, month),
        )
        connection.execute(
            "DELETE FROM articles WHERE pub_year = ? AND pub_month = ?",
            (year, month),
        )
        connection.executemany(
            """
            INSERT OR REPLACE INTO articles (
                canonical_url, url, uri, pub_date, pub_year, pub_month, headline,
                abstract, section_name, news_desk, subsection_name, type_of_material,
                document_type, byline, word_count
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                (
                    article["canonical_url"],
                    article.get("url"),
                    article.get("uri"),
                    article.get("pub_date"),
                    year,
                    month,
                    article.get("headline"),
                    article.get("abstract"),
                    article.get("section_name"),
                    article.get("news_desk"),
                    article.get("subsection_name"),
                    article.get("type_of_material"),
                    article.get("document_type"),
                    article.get("byline"),
                    article.get("word_count"),
                )
                for article in articles
            ],
        )
        connection.executemany(
            "INSERT INTO article_tags (canonical_url, tag_type, tag_value) VALUES (?,?,?)",
            [
                (article["canonical_url"], tag_type, tag_value)
                for article in articles
                for tag_type, tag_value in article.get("tags") or []
            ],
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO archive_months (year, month, article_count, fetched_at)
            VALUES (?,?,?,?)
            """,
            (year, month, len(articles), utcnow()),
        )
    return len(articles)


def loaded_months(connection):
    rows = connection.execute("SELECT year, month FROM archive_months").fetchall()
    return {(row["year"], row["month"]) for row in rows}


def store_popular(connection, rows, snapshot_at=None):
    snapshot_at = snapshot_at or utcnow()
    usable = [row for row in rows if row.get("canonical_url")]
    lists = {(row["list_name"], row["period"]) for row in usable}
    with connection:
        for list_name, period in lists:
            connection.execute(
                "DELETE FROM popular WHERE list_name = ? AND period = ?",
                (list_name, period),
            )
        connection.executemany(
            """
            INSERT INTO popular (
                list_name, period, rank, canonical_url, title, section,
                published_date, views, share_count, snapshot_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            [
                (
                    row["list_name"],
                    row["period"],
                    row["rank"],
                    row["canonical_url"],
                    row.get("title"),
                    row.get("section"),
                    row.get("published_date"),
                    row.get("views"),
                    row.get("share_count"),
                    snapshot_at,
                )
                for row in rows
                if row.get("canonical_url")
            ],
        )
        connection.executemany(
            "INSERT INTO fallback_tags (canonical_url, tag_type, tag_value) VALUES (?,?,?)",
            [
                (row["canonical_url"], tag_type, tag_value)
                for row in rows
                if row.get("canonical_url")
                for tag_type, tag_value in row.get("tags") or []
            ],
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO ingest_runs (source, finished_at, detail)
            VALUES ('nyt_popular', ?, ?)
            """,
            (snapshot_at, f"{len(rows)} rows"),
        )
    return len(rows)
