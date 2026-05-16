import re
import socket
import ipaddress
from urllib.parse import urlparse

import requests
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request
from markupsafe import Markup, escape

app = Flask(__name__)

DEFAULT_TEXT_URL = "https://raw.githubusercontent.com/leejaew/SearchKeywordOccurrences/main/lyrics.txt"

MAX_URL_LENGTH = 2048
MAX_QUERY_LENGTH = 200
MAX_CONTENT_BYTES = 4 * 1024 * 1024  # 4 MB
REQUEST_TIMEOUT = 15
MAX_RESULT_LINES = 10

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

ALLOWED_TEXT_CONTENT_TYPES = (
    "text/plain",
    "text/markdown",
    "text/csv",
    "text/tab-separated-values",
    "application/json",
    "application/xml",
    "text/xml",
)

HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")

# Tags whose contents should be stripped completely before extracting text.
HTML_STRIP_TAGS = (
    "script", "style", "noscript", "template", "iframe",
    "header", "footer", "nav", "aside", "form", "button",
    "menu", "svg", "canvas",
)

# CSS selectors used to locate the main readable content on common sites.
# Tried in order; first non-empty match wins.
CONTENT_SELECTORS = (
    '[data-lyrics-container="true"]',           # Genius
    'div.lyrics',                                # Genius (legacy)
    'div[class*="Lyrics__Container"]',           # Genius (newer)
    'div[class*="lyrics_box"]',                  # AZLyrics-style
    'div.ringtone ~ div',                        # AZLyrics: lyrics div after ringtone
    'pre.lyric-body',                            # LyricsFreak
    'div.song_body-lyrics',                      # Songlyrics
    'article',                                   # Generic article
    'main',                                      # Generic main
)


def is_safe_url(url):
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


def extract_text_from_html(html):
    """Pull the most article-like / main-content text out of an HTML document."""
    soup = BeautifulSoup(html, "lxml")

    # Strip non-content elements outright.
    for tag in soup(HTML_STRIP_TAGS):
        tag.decompose()

    # Replace <br> with a newline so line breaks survive get_text().
    for br in soup.find_all("br"):
        br.replace_with("\n")

    candidates = []

    for selector in CONTENT_SELECTORS:
        try:
            elements = soup.select(selector)
        except Exception:
            continue
        if not elements:
            continue
        text_parts = [el.get_text("\n", strip=False) for el in elements]
        combined = "\n".join(text_parts).strip()
        if len(combined) >= 80:
            candidates.append(combined)
            break  # first matching selector wins

    if not candidates:
        # Fall back to the whole body's visible text.
        body = soup.body or soup
        candidates.append(body.get_text("\n", strip=False))

    text = candidates[0]

    # Collapse runs of blank lines and trim each line.
    lines = [ln.strip() for ln in text.splitlines()]
    cleaned = []
    blank = False
    for ln in lines:
        if not ln:
            if not blank:
                cleaned.append("")
            blank = True
        else:
            cleaned.append(ln)
            blank = False

    return "\n".join(cleaned).strip()


def fetch_text(url):
    """Fetch the URL and return cleaned plain-text content, or an error message.

    Uses curl_cffi to impersonate a real Chrome browser (TLS + HTTP/2 fingerprint),
    which lets us through many soft anti-bot checks. Falls back to vanilla
    requests if curl_cffi raises.
    """
    response = None
    try:
        response = cffi_requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            impersonate="chrome131",
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            allow_redirects=True,
        )
    except Exception:
        try:
            response = requests.get(
                url,
                timeout=REQUEST_TIMEOUT,
                stream=False,
                headers={
                    "User-Agent": BROWSER_USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                allow_redirects=True,
            )
        except requests.RequestException as e:
            return None, f"Request failed: {type(e).__name__}"

    try:
        if response.status_code == 403:
            return (
                None,
                "Source returned HTTP 403 (Forbidden). The site is blocking automated "
                "requests from this server. Try a URL that points directly to a plain-text "
                "file (for example a raw GitHub link), or a site without bot protection.",
            )

        if response.status_code == 429:
            return None, "Source returned HTTP 429. Too many requests — try again later."

        if response.status_code != 200:
            return None, f"Source returned HTTP {response.status_code}."

        content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()

        is_html = any(content_type.startswith(t) for t in HTML_CONTENT_TYPES)
        is_text = any(content_type.startswith(t) for t in ALLOWED_TEXT_CONTENT_TYPES)

        if content_type and not is_html and not is_text:
            return (
                None,
                f"Source content type '{content_type}' is not text or HTML.",
            )

        raw = response.content
        if len(raw) > MAX_CONTENT_BYTES:
            return None, "Source is too large (max 4 MB)."

        encoding = response.encoding or "utf-8"
        try:
            body = raw.decode(encoding, errors="replace")
        except (LookupError, TypeError):
            body = raw.decode("utf-8", errors="replace")

        if not content_type:
            is_html = bool(re.search(r"<\s*html\b", body[:4096], re.IGNORECASE))

        if is_html:
            text = extract_text_from_html(body)
            if not text or len(text) < 20:
                return None, "Could not extract any readable text from the page."
            return text, None

        return body, None
    finally:
        try:
            response.close()
        except Exception:
            pass


def highlight_line(line, query):
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
    url = raw_url.strip()[:MAX_URL_LENGTH] or DEFAULT_TEXT_URL

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
        default_url=DEFAULT_TEXT_URL,
        max_result_lines=MAX_RESULT_LINES,
    )


@app.errorhandler(404)
def not_found(_):
    return render_template(
        "index.html",
        result=None,
        error=None,
        query="",
        url=DEFAULT_TEXT_URL,
        default_url=DEFAULT_TEXT_URL,
        max_result_lines=MAX_RESULT_LINES,
    ), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
