import json
import re
import ssl
import time
import urllib.error
import urllib.request

import certifi

USER_AGENT = "nyt-strategy-dashboard/1.0"


class APIError(Exception):
    def __init__(self, status, url, detail, retry_after=None):
        self.status = status
        self.url = url
        self.retry_after = retry_after
        super().__init__(f"HTTP {status} for {url}: {detail}")


def redact(url):
    return re.sub(r"(api-key=)[^&]*", r"\1REDACTED", url)


def get_json(url, headers=None, timeout=180):
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:300]
        retry_after = None
        if error.headers and error.headers.get("Retry-After"):
            try:
                retry_after = int(error.headers.get("Retry-After"))
            except ValueError:
                retry_after = None
        raise APIError(error.code, redact(url), body, retry_after) from None


def get_json_retry(url, headers=None, timeout=180):
    delay = 2
    last = None
    for attempt in range(4):
        try:
            return get_json(url, headers=headers, timeout=timeout)
        except APIError as error:
            last = error
            if error.status not in (429, 500, 502, 503) or attempt == 3:
                raise
            pause = error.retry_after or delay
            if error.status == 429:
                pause = max(pause, 65)
            time.sleep(pause)
            delay *= 2
    raise last
