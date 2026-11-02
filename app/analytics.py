from app.config import WINDOW_LABEL, month_count

PERFORMING_LISTS = ("viewed", "shared", "emailed", "shared_facebook")
LIST_LABELS = {
    "viewed": "Most viewed",
    "emailed": "Most emailed",
    "shared": "Most shared",
    "shared_facebook": "Shared on Facebook",
}
LIST_WEIGHTS = {
    ("viewed", 1): 5,
    ("viewed", 7): 3,
    ("viewed", 30): 2,
    ("shared", 1): 4,
    ("shared", 7): 2,
    ("shared", 30): 1,
    ("shared_facebook", 1): 2,
    ("shared_facebook", 7): 1,
    ("shared_facebook", 30): 1,
    ("emailed", 1): 3,
    ("emailed", 7): 2,
    ("emailed", 30): 1,
}
MIN_POPULAR = 2
MIN_ARCHIVE = 20
LIFT_BAR = 1.2


def minimum_popular(popular_n):
    return max(MIN_POPULAR, round(0.04 * popular_n))


def attention(row):
    return row["popular_articles"] * max(row["lift"] - 1, 0)


def usable_tag(tag):
    lowered = tag.lower()
    if lowered.startswith("internal-") or lowered.startswith("content type:"):
        return False
    return True


def pct(part, whole):
    if not whole:
        return 0
    value = round(100.0 * part / whole, 1)
    if value == int(value):
        return int(value)
    return value


def fmt_lift(value):
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{text}×"


def period_label(period):
    return "1 day" if int(period) == 1 else f"{int(period)} days"


def join_names(names):
    names = [name for name in names if name]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def _pop_clause():
    quoted = ", ".join(f"'{name}'" for name in PERFORMING_LISTS)
    return f"""
        SELECT DISTINCT canonical_url
        FROM popular
        WHERE canonical_url != ''
          AND list_name IN ({quoted})
    """


def _ranked_tags(connection, tag_type):
    rows = connection.execute(
        f"""
        WITH pop AS (
            {_pop_clause()}
        ),
        pop_tags AS (
            SELECT a.canonical_url, a.tag_value
            FROM article_tags a
            JOIN pop ON pop.canonical_url = a.canonical_url
            WHERE a.tag_type = ?
            UNION
            SELECT f.canonical_url, f.tag_value
            FROM fallback_tags f
            JOIN pop ON pop.canonical_url = f.canonical_url
            WHERE f.tag_type = ?
              AND NOT EXISTS (
                SELECT 1 FROM article_tags a
                WHERE a.canonical_url = f.canonical_url AND a.tag_type = ?
              )
        ),
        archive_counts AS (
            SELECT tag_value, COUNT(DISTINCT canonical_url) AS archive_articles
            FROM article_tags
            WHERE tag_type = ?
              AND canonical_url IN (SELECT canonical_url FROM articles WHERE pub_year = 2026)
            GROUP BY tag_value
        ),
        pop_counts AS (
            SELECT tag_value, COUNT(DISTINCT canonical_url) AS popular_articles
            FROM pop_tags
            GROUP BY tag_value
        )
        SELECT c.tag_value, c.popular_articles, a.archive_articles
        FROM pop_counts c
        JOIN archive_counts a ON a.tag_value = c.tag_value
        """,
        (tag_type, tag_type, tag_type, tag_type),
    ).fetchall()
    return rows


def _ranked_field(connection, column):
    if column not in {"type_of_material", "news_desk"}:
        raise ValueError(column)
    rows = connection.execute(
        f"""
        WITH pop AS (
            {_pop_clause()}
        )
        SELECT a.{column} AS tag_value,
               COUNT(DISTINCT a.canonical_url) AS popular_articles,
               (
                 SELECT COUNT(*) FROM articles b
                 WHERE b.{column} = a.{column} AND b.{column} != ''
                   AND b.pub_year = 2026
               ) AS archive_articles
        FROM articles a
        JOIN pop ON pop.canonical_url = a.canonical_url
        WHERE a.{column} IS NOT NULL AND a.{column} != ''
        GROUP BY a.{column}
        """
    ).fetchall()
    return rows


def _ranked_sections(connection):
    quoted = ", ".join(f"'{name}'" for name in PERFORMING_LISTS)
    return connection.execute(
        f"""
        WITH pop AS (
            SELECT DISTINCT canonical_url, section
            FROM popular
            WHERE canonical_url != ''
              AND section IS NOT NULL
              AND section != ''
              AND list_name IN ({quoted})
        )
        SELECT section AS tag_value,
               COUNT(DISTINCT canonical_url) AS popular_articles,
               (
                 SELECT COUNT(*) FROM articles
                 WHERE section_name = pop.section AND pub_year = 2026
               ) AS archive_articles
        FROM pop
        GROUP BY section
        """
    ).fetchall()


def _enrich(rows, pop_n, archive_n, min_popular=MIN_POPULAR):
    ranked = []
    for row in rows:
        tag = (row["tag_value"] or "").strip()
        popular_articles = row["popular_articles"]
        archive_articles = row["archive_articles"]
        if not tag or not usable_tag(tag):
            continue
        if popular_articles < min_popular or archive_articles < MIN_ARCHIVE:
            continue
        if not pop_n or not archive_n:
            continue
        lift = (popular_articles / pop_n) / (archive_articles / archive_n)
        ranked.append(
            {
                "tag": tag,
                "popular_articles": popular_articles,
                "archive_articles": archive_articles,
                "popular_pct": pct(popular_articles, pop_n),
                "archive_pct": pct(archive_articles, archive_n),
                "lift": round(lift, 2),
            }
        )
    ranked.sort(key=lambda item: (-attention(item), -item["lift"], item["tag"]))
    return ranked


def _counts(connection):
    archive_n = connection.execute("SELECT COUNT(*) AS n FROM articles WHERE pub_year = 2026").fetchone()["n"]
    popular_n = connection.execute(
        f"""
        SELECT COUNT(*) AS n FROM (
            {_pop_clause()}
        )
        """
    ).fetchone()["n"]
    matched_n = connection.execute(
        f"""
        WITH pop AS (
            {_pop_clause()}
        )
        SELECT COUNT(*) AS n
        FROM pop
        JOIN articles a ON a.canonical_url = pop.canonical_url
        """
    ).fetchone()["n"]
    months = connection.execute("SELECT COUNT(*) AS n FROM archive_months WHERE year = 2026").fetchone()["n"]
    return archive_n, popular_n, matched_n, months


def section_status(connection):
    archive_n, popular_n, matched_n, months = _counts(connection)
    return {
        "archive_articles": archive_n,
        "popular_articles": popular_n,
        "matched_articles": matched_n,
        "months_loaded": months,
        "months_expected": month_count(),
        "nyt_ready": archive_n > 0 and popular_n > 0,
        "window": WINDOW_LABEL,
    }


def _stories(connection):
    rows = connection.execute(
        """
        SELECT list_name, period, rank, canonical_url, title, section, views, share_count
        FROM popular
        WHERE canonical_url != ''
        """
    ).fetchall()
    by_url = {}
    for row in rows:
        item = by_url.setdefault(
            row["canonical_url"],
            {
                "url": row["canonical_url"],
                "title": row["title"] or "",
                "section": row["section"] or "",
                "score": 0,
                "appearances": [],
                "views": None,
                "views_label": None,
            },
        )
        weight = LIST_WEIGHTS.get((row["list_name"], row["period"]), 1)
        item["score"] += weight * max(1, 21 - int(row["rank"]))
        label = LIST_LABELS.get(row["list_name"], row["list_name"])
        item["appearances"].append(f"{label}, {period_label(row['period'])} (#{row['rank']})")
        if row["views"] is not None and (item["views"] is None or row["views"] > item["views"]):
            item["views"] = row["views"]
            item["views_label"] = f"Views, {period_label(row['period'])}"
        if not item["title"] and row["title"]:
            item["title"] = row["title"]
        if not item["section"] and row["section"]:
            item["section"] = row["section"]
    urls = list(by_url)
    if not urls:
        return []
    placeholders = ",".join("?" for _ in urls)
    for row in connection.execute(
        f"""
        SELECT canonical_url, headline, section_name, news_desk, type_of_material
        FROM articles
        WHERE canonical_url IN ({placeholders})
        """,
        urls,
    ):
        item = by_url[row["canonical_url"]]
        if row["headline"]:
            item["title"] = row["headline"]
        item["section"] = row["section_name"] or item["section"]
        item["desk"] = row["news_desk"] or ""
        item["format"] = row["type_of_material"] or ""
    topics = {url: [] for url in urls}
    regions = {url: [] for url in urls}
    for row in connection.execute(
        f"""
        SELECT canonical_url, tag_type, tag_value
        FROM article_tags
        WHERE canonical_url IN ({placeholders})
          AND tag_type IN ('subject', 'glocations')
        UNION
        SELECT canonical_url, tag_type, tag_value
        FROM fallback_tags
        WHERE canonical_url IN ({placeholders})
          AND tag_type IN ('subject', 'glocations')
        """,
        [*urls, *urls],
    ):
        if not usable_tag(row["tag_value"]):
            continue
        bucket = topics if row["tag_type"] == "subject" else regions
        if row["tag_value"] not in bucket[row["canonical_url"]]:
            bucket[row["canonical_url"]].append(row["tag_value"])
    stories = []
    for url, item in by_url.items():
        item.setdefault("format", "")
        item.setdefault("desk", "")
        item["topics"] = topics.get(url, [])[:4]
        item["regions"] = regions.get(url, [])[:3]
        item["appearances"] = sorted(item["appearances"])
        if not item["title"]:
            item["title"] = url
        stories.append(item)
    stories.sort(key=lambda story: (-story["score"], story["title"]))
    return stories[:15]


def build_section1(connection):
    status = section_status(connection)
    if status["archive_articles"] == 0:
        return {
            "ready": False,
            "message": "The New York Times archive and Most Popular lists are not loaded yet.",
        }
    if status["popular_articles"] == 0:
        return {
            "ready": False,
            "message": "The archive is loaded. The Most Popular lists are not loaded yet.",
            "archive_articles": status["archive_articles"],
        }
    archive_n = status["archive_articles"]
    popular_n = status["popular_articles"]
    support = minimum_popular(popular_n)
    material = _enrich(
        _ranked_field(connection, "type_of_material"),
        popular_n,
        archive_n,
        support,
    )
    material_coverage = status["matched_articles"] / popular_n if popular_n else 0
    if material_coverage >= 0.5 and material:
        formats = material
        format_axis = "format"
    else:
        formats = _enrich(_ranked_sections(connection), popular_n, archive_n, support)
        format_axis = "section"
    return {
        "ready": True,
        "window": WINDOW_LABEL,
        "archive_articles": archive_n,
        "popular_articles": popular_n,
        "matched_articles": status["matched_articles"],
        "months_loaded": status["months_loaded"],
        "months_expected": status["months_expected"],
        "partial": status["months_loaded"] < status["months_expected"],
        "format_axis": format_axis,
        "minimum_popular": support,
        "topics": _enrich(_ranked_tags(connection, "subject"), popular_n, archive_n, support),
        "regions": _enrich(_ranked_tags(connection, "glocations"), popular_n, archive_n, support),
        "formats": formats,
        "desks": _enrich(_ranked_field(connection, "news_desk"), popular_n, archive_n, support)
        if material_coverage >= 0.5
        else [],
        "stories": _stories(connection),
    }



def _partial_sentence(section1):
    if section1.get("partial"):
        loaded = section1.get("months_loaded", 0)
        expected = section1.get("months_expected", 0)
        return f" The archive currently has {loaded} of {expected} months, so these base rates can still move."
    return ""


def _focus_card(area, rows, popular_n, noun, partial):
    if not rows:
        return {
            "area": area,
            "title": f"No {noun} call yet",
            "body": (
                f"No {noun} tag appears on at least {MIN_POPULAR} Most Popular articles "
                f"and {MIN_ARCHIVE} archive articles. The current lists are too thin to single out a {noun} bet."
            ),
        }
    best = rows[0]
    others = [row["tag"] for row in rows[1:4] if row["lift"] >= LIFT_BAR]
    if best["lift"] < LIFT_BAR:
        closer = {
            "Topical": "That gap is too small to rebuild the 2027 topic slate around.",
            "Regional": "That gap is too small to rebuild the 2027 regional slate around.",
            "Format": "Keep the current format mix and put the 2027 bet on topic and region instead.",
            "Section": "That gap is too small to rebuild the 2027 section mix around.",
        }[area]
        body = (
            f"The strongest {noun} is {best['tag']}, at {fmt_lift(best['lift'])} the archive rate "
            f"({best['popular_pct']}% of current Most Popular articles, {best['archive_pct']}% of the archive). "
            f"{closer}"
        )
    else:
        verb = {
            "Topical": f"Put more reporting weight on {best['tag']}.",
            "Regional": f"Give {best['tag']} more reporting weight in 2027.",
            "Format": f"Prefer {best['tag']} where the reporting can support it.",
            "Section": f"Give the {best['tag']} section more weight in 2027.",
        }[area]
        body = (
            f"{verb} It appears on {best['popular_articles']} of {popular_n} articles on the current "
            f"Most Popular lists ({best['popular_pct']}%), against {best['archive_pct']}% of the {WINDOW_LABEL} "
            f"archive, which is {fmt_lift(best['lift'])} the archive rate."
        )
        if others:
            body += f" Also above the archive rate: {join_names(others)}."
    body += partial
    return {"area": area, "title": best["tag"], "body": body}



def build_recommendations(section1):
    if not section1.get("ready"):
        return {
            "ready": False,
            "message": "Recommendations need both the archive and the Most Popular lists.",
        }
    partial = _partial_sentence(section1)
    popular_n = section1["popular_articles"]
    format_area = "Section" if section1.get("format_axis") == "section" else "Format"
    format_noun = "section" if format_area == "Section" else "format"
    cards = [
        _focus_card("Topical", section1.get("topics") or [], popular_n, "subject", partial),
        _focus_card("Regional", section1.get("regions") or [], popular_n, "region", partial),
        _focus_card(format_area, section1.get("formats") or [], popular_n, format_noun, partial),
    ]
    return {"ready": True, "cards": cards}


TOPIC_LISTS = (
    ("viewed", "Most viewed"),
    ("emailed", "Most emailed"),
    ("shared", "Most shared"),
    ("shared_facebook", "Most shared on Facebook"),
)


def _pct(part, whole):
    if not whole:
        return 0.0
    return round(100.0 * part / whole, 1)


def _tag_counts(connection, tag_type, list_name=None):
    filters = [
        "f.tag_type = ?",
        "lower(f.tag_value) NOT LIKE 'internal-%'",
        "lower(f.tag_value) NOT LIKE 'content type:%'",
    ]
    params = [tag_type]
    if list_name is not None:
        filters.append("p.list_name = ?")
        params.append(list_name)
    where = " AND ".join(filters)
    return connection.execute(
        f"""
        SELECT f.tag_value AS tag, COUNT(DISTINCT p.canonical_url) AS articles
        FROM popular p
        JOIN fallback_tags f
          ON f.canonical_url = p.canonical_url
        WHERE {where}
        GROUP BY f.tag_value
        ORDER BY articles DESC, f.tag_value
        """,
        params,
    ).fetchall()


def _topic_counts(connection, list_name=None):
    return _tag_counts(connection, "subject", list_name)


def _section_counts(connection, list_name=None):
    filters = ["p.section IS NOT NULL", "p.section != ''"]
    params = []
    if list_name is not None:
        filters.append("p.list_name = ?")
        params.append(list_name)
    where = " AND ".join(filters)
    return connection.execute(
        f"""
        SELECT p.section AS tag, COUNT(DISTINCT p.canonical_url) AS articles
        FROM popular p
        WHERE {where}
        GROUP BY p.section
        ORDER BY articles DESC, p.section
        """,
        params,
    ).fetchall()


def _most_shared_article(connection, tag):
    row = connection.execute(
        """
        SELECT p.title, p.published_date, p.period, p.rank, p.canonical_url
        FROM popular p
        JOIN fallback_tags f
          ON f.canonical_url = p.canonical_url
         AND f.tag_type = 'subject'
        WHERE p.list_name = 'shared'
          AND f.tag_value = ?
        ORDER BY p.rank ASC, p.period ASC, p.published_date DESC
        LIMIT 1
        """,
        (tag,),
    ).fetchone()
    if row is None:
        return None
    return {
        "title": row["title"],
        "published_date": row["published_date"],
        "rank": row["rank"],
        "period": row["period"],
        "url": row["canonical_url"],
    }


def _archive_2026_counts(connection, tags, tag_type="subject"):
    if not tags:
        return {}
    placeholders = ",".join("?" for _ in tags)
    rows = connection.execute(
        f"""
        SELECT t.tag_value AS tag, COUNT(DISTINCT a.canonical_url) AS n
        FROM articles a
        JOIN article_tags t
          ON t.canonical_url = a.canonical_url
         AND t.tag_type = ?
        WHERE a.pub_year = 2026
          AND t.tag_value IN ({placeholders})
        GROUP BY t.tag_value
        """,
        (tag_type, *tuple(tags)),
    ).fetchall()
    return {row["tag"]: row["n"] for row in rows}


def _archive_2026_sections(connection, names):
    if not names:
        return {}
    placeholders = ",".join("?" for _ in names)
    rows = connection.execute(
        f"""
        SELECT section_name AS tag, COUNT(DISTINCT canonical_url) AS n
        FROM articles
        WHERE pub_year = 2026
          AND section_name IN ({placeholders})
        GROUP BY section_name
        """,
        tuple(names),
    ).fetchall()
    return {row["tag"]: row["n"] for row in rows}


def _popular_denominators(connection):
    denominators = {
        "aggregate": connection.execute(
            "SELECT COUNT(DISTINCT canonical_url) AS n FROM popular"
        ).fetchone()["n"]
    }
    for list_name, _label in TOPIC_LISTS:
        denominators[list_name] = connection.execute(
            "SELECT COUNT(DISTINCT canonical_url) AS n FROM popular WHERE list_name = ?",
            (list_name,),
        ).fetchone()["n"]
    return denominators


def _investment_rows(names, by_mode, archive_counts, archive_total, denominators):
    rows = []
    for name in names:
        archive_articles = archive_counts.get(name, 0)
        scores = {}
        for mode, _label in INVEST_MODES:
            articles = by_mode[mode].get(name, 0)
            scores[mode] = {
                "articles": articles,
                "pct": _pct(articles, denominators[mode]),
            }
        rows.append(
            {
                "topic": name,
                "archive_articles": archive_articles,
                "archive_pct": _pct(archive_articles, archive_total),
                "scores": scores,
            }
        )
    rows.sort(key=lambda row: (-row["archive_articles"], row["topic"]))
    return rows


def _mode_maps(count_fn):
    by_mode = {"aggregate": {row["tag"]: row["articles"] for row in count_fn(None)}}
    for list_name, _label in TOPIC_LISTS:
        by_mode[list_name] = {row["tag"]: row["articles"] for row in count_fn(list_name)}
    return by_mode


INVEST_MODES = (
    ("aggregate", "Most popular"),
    ("emailed", "Emailed"),
    ("viewed", "Viewed"),
    ("shared", "Shared"),
    ("shared_facebook", "Facebook"),
)


def build_topic_board(connection):
    if connection.execute("SELECT COUNT(*) AS n FROM popular").fetchone()["n"] == 0:
        return {"ready": False}
    archive_n, popular_n, _matched, _months = _counts(connection)
    support = minimum_popular(popular_n)
    topics = [
        row["tag"]
        for row in _enrich(
            _ranked_tags(connection, "subject"),
            popular_n,
            archive_n,
            support,
        )
    ]
    shared_cache = {}
    lists = {}
    for list_name, _label in TOPIC_LISTS:
        counts = {row["tag"]: row["articles"] for row in _topic_counts(connection, list_name)}
        ranked = []
        for tag in topics:
            if tag not in shared_cache:
                shared_cache[tag] = _most_shared_article(connection, tag)
            ranked.append(
                {
                    "topic": tag,
                    "articles": counts.get(tag, 0),
                    "most_shared": shared_cache[tag],
                }
            )
        ranked.sort(key=lambda row: (-row["articles"], row["topic"]))
        lists[list_name] = {
            "articles": connection.execute(
                "SELECT COUNT(DISTINCT canonical_url) AS n FROM popular WHERE list_name = ?",
                (list_name,),
            ).fetchone()["n"],
            "topics": ranked,
        }
    aggregate_rows = _topic_counts(connection)
    by_mode = {"aggregate": {row["tag"]: row["articles"] for row in aggregate_rows}}
    denominators = {
        "aggregate": connection.execute(
            "SELECT COUNT(DISTINCT canonical_url) AS n FROM popular"
        ).fetchone()["n"]
    }
    for list_name, _label in TOPIC_LISTS:
        by_mode[list_name] = {
            row["tag"]: row["articles"] for row in _topic_counts(connection, list_name)
        }
        denominators[list_name] = lists[list_name]["articles"]
    archive_total = connection.execute(
        "SELECT COUNT(DISTINCT canonical_url) AS n FROM articles WHERE pub_year = 2026"
    ).fetchone()["n"]
    archive_counts = _archive_2026_counts(connection, topics)
    investment_topics = []
    for topic in topics:
        archive_articles = archive_counts.get(topic, 0)
        scores = {}
        for mode, _label in INVEST_MODES:
            articles = by_mode[mode].get(topic, 0)
            scores[mode] = {
                "articles": articles,
                "pct": _pct(articles, denominators[mode]),
            }
        investment_topics.append(
            {
                "topic": topic,
                "archive_articles": archive_articles,
                "archive_pct": _pct(archive_articles, archive_total),
                "scores": scores,
            }
        )
    investment_topics.sort(key=lambda row: (-row["archive_articles"], row["topic"]))
    unpaid_topics = _unpaid_topics(connection, archive_total)
    facebook_same = all(
        row["scores"]["shared"]["articles"] == row["scores"]["shared_facebook"]["articles"]
        for row in investment_topics
    ) and denominators["shared"] == denominators["shared_facebook"]
    return {
        "ready": True,
        "lists": lists,
        "facebook_matches_shared": facebook_same,
        "investment": {
            "archive_articles": archive_total,
            "modes": {
                mode: {"label": label, "articles": denominators[mode]}
                for mode, label in INVEST_MODES
            },
            "minimum_popular": support,
            "popular_articles": popular_n,
            "topics": investment_topics,
            "unpaid": unpaid_topics,
        },
    }


def _unpaid_topics(connection, archive_total, limit=12):
    rows = connection.execute(
        """
        SELECT t.tag_value AS tag, COUNT(DISTINCT a.canonical_url) AS n
        FROM articles a
        JOIN article_tags t
          ON t.canonical_url = a.canonical_url
         AND t.tag_type = 'subject'
        WHERE a.pub_year = 2026
          AND t.tag_value NOT IN (
            SELECT f.tag_value
            FROM fallback_tags f
            JOIN popular p ON p.canonical_url = f.canonical_url
            WHERE f.tag_type = 'subject'
          )
        GROUP BY t.tag_value
        ORDER BY n DESC, t.tag_value ASC
        """
    ).fetchall()
    picked = []
    for row in rows:
        tag = row["tag"]
        if not usable_tag(tag):
            continue
        if " " not in tag and "-" in tag and tag == tag.lower():
            continue
        zero_scores = {
            mode: {"articles": 0, "pct": 0}
            for mode, _label in INVEST_MODES
        }
        picked.append(
            {
                "topic": tag,
                "archive_articles": row["n"],
                "archive_pct": _pct(row["n"], archive_total),
                "scores": zero_scores,
            }
        )
        if len(picked) == limit:
            break
    return picked


def _coverage_board(connection, names, count_fn, archive_counts):
    if connection.execute("SELECT COUNT(*) AS n FROM popular").fetchone()["n"] == 0:
        return {"ready": False}
    denominators = _popular_denominators(connection)
    archive_total = connection.execute(
        "SELECT COUNT(DISTINCT canonical_url) AS n FROM articles WHERE pub_year = 2026"
    ).fetchone()["n"]
    rows = _investment_rows(names, _mode_maps(count_fn), archive_counts, archive_total, denominators)
    facebook_same = (
        denominators["shared"] == denominators["shared_facebook"]
        and all(
            row["scores"]["shared"]["articles"] == row["scores"]["shared_facebook"]["articles"]
            for row in rows
        )
    )
    return {
        "ready": True,
        "facebook_matches_shared": facebook_same,
        "investment": {
            "archive_articles": archive_total,
            "modes": {
                mode: {"label": label, "articles": denominators[mode]}
                for mode, label in INVEST_MODES
            },
            "topics": rows,
        },
    }


def _included_names(connection, rows):
    archive_n, popular_n, _matched, _months = _counts(connection)
    return [
        row["tag"]
        for row in _enrich(rows, popular_n, archive_n, minimum_popular(popular_n))
    ]


def build_region_board(connection):
    names = _included_names(connection, _ranked_tags(connection, "glocations"))
    return _coverage_board(
        connection,
        names,
        lambda list_name: _tag_counts(connection, "glocations", list_name),
        _archive_2026_counts(connection, names, "glocations"),
    )


def build_section_board(connection):
    names = _included_names(connection, _ranked_sections(connection))
    return _coverage_board(
        connection,
        names,
        lambda list_name: _section_counts(connection, list_name),
        _archive_2026_sections(connection, names),
    )


def build_dashboard(connection):
    status = section_status(connection)
    section1 = build_section1(connection)
    return {
        "status": status,
        "section1": section1,
        "topic_board": build_topic_board(connection),
        "region_board": build_region_board(connection),
        "section_board": build_section_board(connection),
        "recommendations": build_recommendations(section1),
    }
