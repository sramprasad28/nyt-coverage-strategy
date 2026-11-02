import time
from urllib.parse import quote

from app.config import iter_months, require_env
from app.db import connect, loaded_months, store_month, store_popular, utcnow
from app.http_client import APIError, get_json_retry
from app.parse_nyt import article_from_doc, popular_from_result, unwrap_doc

POPULAR_LISTS = []
for _period in (1, 7, 30):
    POPULAR_LISTS.append(("viewed", _period, f"mostpopular/v2/viewed/{_period}.json"))
    POPULAR_LISTS.append(("emailed", _period, f"mostpopular/v2/emailed/{_period}.json"))
    POPULAR_LISTS.append(("shared", _period, f"mostpopular/v2/shared/{_period}.json"))
    POPULAR_LISTS.append(("shared_facebook", _period, f"mostpopular/v2/shared/{_period}/facebook.json"))


def nyt_url(path, key):
    return f"https://api.nytimes.com/svc/{path}?api-key={quote(key)}"


def archive_docs(payload):
    response = payload.get("response") if isinstance(payload, dict) else None
    docs = None
    if isinstance(response, dict):
        docs = response.get("docs")
    if docs is None and isinstance(payload, dict):
        docs = payload.get("docs")
    if not isinstance(docs, list):
        keys = list(payload)[:20] if isinstance(payload, dict) else type(payload).__name__
        raise RuntimeError(f"Unexpected archive response shape. Keys: {keys}")
    return docs


def popular_results(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        keys = list(payload)[:20] if isinstance(payload, dict) else type(payload).__name__
        raise RuntimeError(f"Unexpected Most Popular response shape. Keys: {keys}")
    return payload["results"]


def fetch_archive(connection, key):
    have = loaded_months(connection)
    described = False
    for year, month in iter_months():
        if (year, month) in have:
            print(f"skip archive {year}-{month:02d}")
            continue
        print(f"fetch archive {year}-{month:02d}")
        try:
            payload = get_json_retry(nyt_url(f"archive/v1/{year}/{month}.json", key))
        except APIError as error:
            if error.status in (401, 403):
                raise SystemExit(f"NYT API rejected the key while fetching the archive (HTTP {error.status}).") from None
            if error.status == 404:
                print(f"skip archive {year}-{month:02d}: not available")
                continue
            print(f"skip archive {year}-{month:02d}: HTTP {error.status}")
            continue
        docs = archive_docs(payload)
        if docs and not described:
            sample = unwrap_doc(docs[0]) or {}
            print("archive fields:", ", ".join(sorted(sample.keys())))
            described = True
        articles = []
        skipped = 0
        for doc in docs:
            article = article_from_doc(doc, year, month)
            if article is None:
                skipped += 1
                continue
            articles.append(article)
        stored = store_month(connection, year, month, articles)
        print(f"stored {stored} articles for {year}-{month:02d} ({skipped} skipped)", flush=True)
        time.sleep(13)


def fetch_popular(connection, key):
    rows = []
    described = False
    failures = []
    for list_name, period, path in POPULAR_LISTS:
        print(f"fetch most popular {list_name} {period}")
        try:
            payload = get_json_retry(nyt_url(path, key))
        except APIError as error:
            if error.status == 404:
                print(f"skip {list_name} {period}: not available")
                continue
            if error.status in (401, 403):
                raise
            failures.append(f"{list_name} {period}: HTTP {error.status}")
            print(f"skip {list_name} {period}: HTTP {error.status}")
            continue
        results = popular_results(payload)
        if results and not described:
            print("most popular fields:", ", ".join(sorted(results[0].keys())))
            described = True
        kept = 0
        for rank, result in enumerate(results, start=1):
            row = popular_from_result(result, list_name, period, rank)
            if row is None:
                continue
            rows.append(row)
            kept += 1
        print(f"kept {kept} from {list_name} {period}", flush=True)
        time.sleep(13)
    if not rows:
        detail = "; ".join(failures) or "no rows"
        raise SystemExit(f"Most Popular returned no articles. {detail}")
    stored = store_popular(connection, rows, utcnow())
    print(f"stored {stored} Most Popular rows")
    if failures:
        print("lists skipped:", "; ".join(failures))


def main():
    key = require_env("NYT_API_KEY")
    connection = connect()
    try:
        fetch_archive(connection, key)
        fetch_popular(connection, key)
    finally:
        connection.close()
    print("NYT ingest complete")


if __name__ == "__main__":
    main()
