"""HTML → readable plain text.

Pure function — no I/O, no global state. Easy to unit-test by feeding fixed
HTML strings and asserting on the output.

Pipeline (top-to-bottom):
    1. Parse the HTML with lxml (fast, lenient).
    2. Strip non-content tags (script, style, nav, footer, …) outright.
    3. Replace <br> with newlines so soft line breaks survive get_text().
    4. Try a list of CSS selectors known to wrap main content on common sites.
       The first selector with substantive (>= 80 chars) text wins — this
       prevents an empty/placeholder match from outranking a richer fallback.
    5. If no selector matched, fall back to the whole <body>.
    6. Collapse runs of blank lines and trim whitespace per line.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from .config import AppConfig

# Threshold below which a selector match is considered "too thin to trust" —
# we'd rather fall through to a more generic selector or the body fallback.
_MIN_CANDIDATE_CHARS = 80


def extract_text_from_html(html: str, config: AppConfig) -> str:
    """Extract the most article-like / main-content text from an HTML document."""
    soup = BeautifulSoup(html, "lxml")

    # --- Step 1+2: strip everything that never carries article text ---
    for tag in soup(config.html_strip_tags):
        tag.decompose()

    # --- Step 3: preserve soft line breaks ---
    # ``<br>`` carries no text but conveys a line break that lyric/article
    # markup relies on. Replacing with "\n" before get_text() preserves it.
    for br in soup.find_all("br"):
        br.replace_with("\n")

    # --- Step 4: try ordered selectors, first substantive match wins ---
    text = _select_best_content(soup, config)

    # --- Step 5: fall back to whole-body text if no selector matched ---
    if text is None:
        body = soup.body or soup
        text = body.get_text("\n", strip=False)

    # --- Step 6: tidy whitespace ---
    return _tidy_whitespace(text)


def _select_best_content(soup: BeautifulSoup, config: AppConfig) -> str | None:
    """Return text from the first selector whose match is substantive enough.

    "Substantive" is defined by ``_MIN_CANDIDATE_CHARS`` so a hidden /
    decorative element matching one of our selectors doesn't outrank the
    real content waiting in a more generic selector below it.
    """
    for selector in config.content_selectors:
        try:
            elements = soup.select(selector)
        except Exception:
            # Defensive: a malformed selector would raise; skip and keep going.
            continue
        if not elements:
            continue
        combined = "\n".join(el.get_text("\n", strip=False) for el in elements).strip()
        if len(combined) >= _MIN_CANDIDATE_CHARS:
            return combined
    return None


def _tidy_whitespace(text: str) -> str:
    """Trim each line and collapse runs of blank lines into a single blank.

    Keeps stanza breaks (one blank line between paragraphs) but kills the
    huge gaps that fall out of get_text() when many empty inline elements
    sit between content blocks.
    """
    lines = (ln.strip() for ln in text.splitlines())
    cleaned: list[str] = []
    previous_blank = False
    for line in lines:
        if not line:
            if not previous_blank:
                cleaned.append("")
            previous_blank = True
        else:
            cleaned.append(line)
            previous_blank = False
    return "\n".join(cleaned).strip()
