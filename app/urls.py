from urllib.parse import unquote, urlparse


def canonical_url(value):
    if not value or not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.startswith("//"):
        raw = "https:" + raw
    if not raw.startswith("http://") and not raw.startswith("https://"):
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host.endswith(":443") or host.endswith(":80"):
        host = host.rsplit(":", 1)[0]
    if not host or " " in host:
        return None
    path = unquote(parsed.path or "")
    if path == "/":
        path = ""
    elif path.endswith("/"):
        path = path.rstrip("/")
    return f"https://{host}{path}"
