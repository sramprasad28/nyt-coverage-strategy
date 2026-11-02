from app.urls import canonical_url

TAG_ALIASES = {
    "subject": "subject",
    "subjects": "subject",
    "des": "subject",
    "glocations": "glocations",
    "glocation": "glocations",
    "geo": "glocations",
    "location": "glocations",
    "locations": "glocations",
    "persons": "persons",
    "person": "persons",
    "organizations": "organizations",
    "organization": "organizations",
    "org": "organizations",
}


def as_list(value):
    if value is None or value == "":
        return []
    if isinstance(value, list):
        items = []
        for item in value:
            if isinstance(item, str) and item.strip():
                items.append(item.strip())
            elif isinstance(item, dict):
                text = item.get("value") or item.get("name") or item.get("main")
                if isinstance(text, str) and text.strip():
                    items.append(text.strip())
        return items
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def to_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def text_of(value):
    if isinstance(value, dict):
        for key in ("main", "original", "print_headline", "name", "value"):
            if isinstance(value.get(key), str) and value[key].strip():
                return value[key].strip()
        return ""
    if isinstance(value, str):
        return value.strip()
    return ""


def unwrap_doc(doc):
    if not isinstance(doc, dict):
        return None
    if doc.get("web_url") or doc.get("url"):
        return doc
    for key in ("article", "document"):
        inner = doc.get(key)
        if isinstance(inner, dict):
            return inner
    return doc


def keyword_tags(doc):
    tags = []
    keywords = doc.get("keywords")
    pairs = []
    if isinstance(keywords, list):
        for item in keywords:
            if isinstance(item, dict):
                pairs.append((item.get("name"), item.get("value")))
            elif isinstance(item, str):
                pairs.append(("subject", item))
    elif isinstance(keywords, dict):
        for name, values in keywords.items():
            for value in as_list(values):
                pairs.append((name, value))
    seen = set()
    for name, value in pairs:
        tag_type = TAG_ALIASES.get(str(name or "").strip().lower(), str(name or "").strip().lower())
        tag_value = text_of(value) if not isinstance(value, str) else value.strip()
        if not tag_type or not tag_value:
            continue
        key = (tag_type, tag_value)
        if key in seen:
            continue
        seen.add(key)
        tags.append(key)
    return tags


def article_from_doc(doc, year, month):
    doc = unwrap_doc(doc)
    if not doc:
        return None
    canonical = canonical_url(doc.get("web_url") or doc.get("url"))
    if not canonical:
        return None
    return {
        "canonical_url": canonical,
        "url": doc.get("web_url") or doc.get("url") or canonical,
        "uri": text_of(doc.get("uri")),
        "pub_date": text_of(doc.get("pub_date")),
        "pub_year": year,
        "pub_month": month,
        "headline": text_of(doc.get("headline")) or text_of(doc.get("title")),
        "abstract": text_of(doc.get("abstract")),
        "section_name": text_of(doc.get("section_name") or doc.get("section")),
        "news_desk": text_of(doc.get("news_desk")),
        "subsection_name": text_of(doc.get("subsection_name")),
        "type_of_material": text_of(doc.get("type_of_material")),
        "document_type": text_of(doc.get("document_type")),
        "byline": text_of(doc.get("byline")),
        "word_count": to_int(doc.get("word_count")),
        "tags": keyword_tags(doc),
    }


FACET_MAP = (
    ("des_facet", "subject"),
    ("geo_facet", "glocations"),
    ("org_facet", "organizations"),
    ("per_facet", "persons"),
)


def popular_from_result(result, list_name, period, rank):
    if not isinstance(result, dict):
        return None
    canonical = canonical_url(result.get("url") or result.get("link") or result.get("web_url"))
    if not canonical:
        return None
    tags = []
    seen = set()
    for field, tag_type in FACET_MAP:
        for value in as_list(result.get(field)):
            key = (tag_type, value)
            if key in seen:
                continue
            seen.add(key)
            tags.append(key)
    return {
        "list_name": list_name,
        "period": period,
        "rank": rank,
        "canonical_url": canonical,
        "title": text_of(result.get("title") or result.get("headline")),
        "section": text_of(result.get("section") or result.get("section_name")),
        "published_date": text_of(result.get("published_date")),
        "views": to_int(result.get("views")),
        "share_count": to_int(result.get("share_count") or result.get("shares")),
        "tags": tags,
    }
