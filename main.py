import re
import socket
import ipaddress
from urllib.parse import urlparse

import requests
from flask import Flask, render_template, request
from markupsafe import Markup, escape

app = Flask(__name__)

DEFAULT_LYRICS_URL = "https://raw.githubusercontent.com/leejaew/SearchKeywordOccurrences/main/lyrics.txt"

MAX_URL_LENGTH = 2048
MAX_QUERY_LENGTH = 200
MAX_CONTENT_BYTES = 2 * 1024 * 1024  # 2 MB
REQUEST_TIMEOUT = 10
MAX_RESULT_LINES = 10

ALLOWED_TEXT_CONTENT_TYPES = (
    "text/plain",
    "text/markdown",
    "text/csv",
    "text/tab-separated-values",
    "application/json",
    "application/xml",
    "text/xml",
)

HTML_SNIFF_PATTERNS = re.compile(
    r"<\s*(html|body|head|script|!doctype|style|iframe|meta|link)\b",
    re.IGNORECASE,
)


def is_safe_url(url):
    """Validate the URL: scheme must be http/https; host must be public."""
    if not url or len(url) > MAX_URL_LENGTH:
        return False, "URL is missing or too long."

    try:
        parsed = urlparse(url)
    except ValueError:
        return False, "URL could not be parsed."

    if parsed.scheme not in ("http", "https"):
        return False, "URL must start with http:// or https://."

    if not parsed.hostname:
        return False, "URL is missing a hostname."

    # SSRF protection: block private, loopback, link-local, multicast addresses.
    try:
        addr_infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        return False, "Could not resolve hostname."

    for info in addr_infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False, "URL points to a non-public address."

    return True, None


def fetch_text(url):
    """Fetch the URL and return plain-text content, or an error message."""
    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            stream=True,
            headers={"User-Agent": "LyricSearch/1.0"},
            allow_redirects=True,
        )
    except requests.RequestException as e:
        return None, f"Request failed: {type(e).__name__}"

    try:
        if response.status_code != 200:
            return None, f"Source returned HTTP {response.status_code}."

        content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if content_type and not any(content_type.startswith(t) for t in ALLOWED_TEXT_CONTENT_TYPES):
            return (
                None,
                f"Source content type '{content_type}' is not plain text. "
                "Please provide a URL pointing directly to a .txt file.",
            )

        # Read up to MAX_CONTENT_BYTES to avoid huge responses.
        chunks = []
        total = 0
        for chunk in response.iter_content(chunk_size=16384, decode_unicode=False):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_CONTENT_BYTES:
                return None, "Source is too large (max 2 MB)."
            chunks.append(chunk)

        raw = b"".join(chunks)
        encoding = response.encoding or "utf-8"
        try:
            text = raw.decode(encoding, errors="replace")
        except (LookupError, TypeError):
            text = raw.decode("utf-8", errors="replace")

        # Even with a permissive content type, sniff for HTML markup.
        if HTML_SNIFF_PATTERNS.search(text[:4096]):
            return (
                None,
                "Source appears to contain HTML markup. Please provide a URL "
                "pointing directly to a plain-text file.",
            )

        return text, None
    finally:
        response.close()


def highlight_line(line, query):
    """Escape the line, then wrap case-insensitive matches of query in <mark>."""
    escaped_line = str(escape(line))
    escaped_query = str(escape(query))
    if not escaped_query:
        return Markup(escaped_line)

    pattern = re.compile(re.escape(escaped_query), re.IGNORECASE)
    highlighted = pattern.sub(
        lambda m: f"<mark>{m.group(0)}</mark>",
        escaped_line,
    )
    return Markup(highlighted)


@app.route("/", methods=["GET"])
def index():
    raw_query = request.args.get("q", "")
    raw_url = request.args.get("url", "")

    query = raw_query.strip()[:MAX_QUERY_LENGTH]
    url = raw_url.strip()[:MAX_URL_LENGTH] or DEFAULT_LYRICS_URL

    result = None
    error = None

    if query:
        url_ok, url_error = is_safe_url(url)
        if not url_ok:
            error = url_error
        else:
            text, fetch_error = fetch_text(url)
            if fetch_error:
                error = fetch_error
            else:
                count = text.lower().count(query.lower())
                matches = []
                for raw_line in text.splitlines():
                    line = raw_line.strip()
                    if line and query.lower() in line.lower():
                        matches.append(highlight_line(line, query))
                        if len(matches) >= MAX_RESULT_LINES:
                            break
                result = {
                    "query": query,
                    "count": count,
                    "lines": matches,
                }

    return render_template(
        "index.html",
        result=result,
        error=error,
        query=query,
        url=url,
        default_url=DEFAULT_LYRICS_URL,
        max_result_lines=MAX_RESULT_LINES,
    )


@app.errorhandler(404)
def not_found(_):
    return render_template(
        "index.html",
        result=None,
        error=None,
        query="",
        url=DEFAULT_LYRICS_URL,
        default_url=DEFAULT_LYRICS_URL,
        max_result_lines=MAX_RESULT_LINES,
    ), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
