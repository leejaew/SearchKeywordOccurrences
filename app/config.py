"""Application configuration.

Single source of truth for all tunable knobs (timeouts, size limits, default URL,
HTTP headers, content-type whitelists, CSS selectors, etc.).

Why a frozen dataclass instead of module-level constants:
    - Immutable: prevents accidental runtime mutation.
    - Injectable: tests / alternate environments can build their own AppConfig and
      pass it to ``create_app(config=...)`` without monkey-patching.
    - Type-checked: IDEs / type-checkers catch typos in field names.

Why a single config object instead of one per module:
    - Avoids circular imports between sibling modules that all need the same knobs.
    - Makes the full surface of "things you can change" discoverable in one file.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# Default text source loaded when the user submits an empty URL field.
# Kept as a module constant (not on the dataclass) because dataclass field
# defaults can't reference other field defaults cleanly.
DEFAULT_TEXT_URL = (
    "https://raw.githubusercontent.com/leejaew/SearchKeywordOccurrences/main/lyrics.txt"
)

# Realistic Chrome User-Agent. Used by the requests fallback path (curl_cffi
# sets its own UA when impersonating a browser fingerprint).
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Content-Type prefixes accepted as "already plain text" — no HTML parsing needed.
ALLOWED_TEXT_CONTENT_TYPES: tuple[str, ...] = (
    "text/plain",
    "text/markdown",
    "text/csv",
    "text/tab-separated-values",
    "application/json",
    "application/xml",
    "text/xml",
)

# Content-Type prefixes that should be routed through the HTML extractor.
HTML_CONTENT_TYPES: tuple[str, ...] = ("text/html", "application/xhtml+xml")

# Tags whose contents are stripped wholesale from any HTML page before
# we look for the main readable content. These never carry article text.
HTML_STRIP_TAGS: tuple[str, ...] = (
    "script", "style", "noscript", "template", "iframe",
    "header", "footer", "nav", "aside", "form", "button",
    "menu", "svg", "canvas",
)

# CSS selectors used by the extractor to locate the main readable content
# on common sites. Tried in order; the first selector with substantive text wins.
# Kept ordered from most-specific (named lyric containers) to most-generic
# (article / main) so we prefer well-known wrappers when available.
CONTENT_SELECTORS: tuple[str, ...] = (
    '[data-lyrics-container="true"]',           # Genius
    'div.lyrics',                                # Genius (legacy)
    'div[class*="Lyrics__Container"]',           # Genius (newer)
    'div[class*="lyrics_box"]',                  # AZLyrics-style
    'div.ringtone ~ div',                        # AZLyrics: lyrics div after ringtone
    'pre.lyric-body',                            # LyricsFreak
    'div.song_body-lyrics',                      # Songlyrics
    'article',                                   # Generic article container
    'main',                                      # Generic main landmark
)


@dataclass(frozen=True)
class AppConfig:
    """Immutable runtime configuration for the application.

    Pass an instance to :func:`app.create_app` to override defaults — useful
    for tests (e.g. shorter timeouts, smaller size limits) and for any future
    environment-specific tuning.
    """

    # ------- input limits -------
    # Maximum length we accept for the URL input. Mirrors the HTML maxlength
    # attribute. Defends against pathological URLs and template explosion.
    max_url_length: int = 2048

    # Maximum length we accept for the keyword input. Long keywords would
    # bloat the regex used for highlighting and rarely make sense.
    max_query_length: int = 200

    # ------- network limits -------
    # Hard ceiling on the response body in bytes. Prevents memory exhaustion
    # if a user points us at a huge file.
    max_content_bytes: int = 4 * 1024 * 1024  # 4 MB

    # Per-request HTTP timeout in seconds. Applies to both connect and read.
    request_timeout: int = 15

    # ------- result shaping -------
    # Maximum number of matching lines we render. Keeps the page compact and
    # avoids dumping thousands of lines into the DOM for very common keywords.
    max_result_lines: int = 10

    # ------- whitelists / strip lists -------
    # These default to the module-level tuples above so callers can swap them
    # for testing without editing the constants.
    allowed_text_content_types: tuple[str, ...] = field(
        default_factory=lambda: ALLOWED_TEXT_CONTENT_TYPES
    )
    html_content_types: tuple[str, ...] = field(
        default_factory=lambda: HTML_CONTENT_TYPES
    )
    html_strip_tags: tuple[str, ...] = field(
        default_factory=lambda: HTML_STRIP_TAGS
    )
    content_selectors: tuple[str, ...] = field(
        default_factory=lambda: CONTENT_SELECTORS
    )

    # Default URL pre-filled in the form when the user submits no URL.
    default_text_url: str = DEFAULT_TEXT_URL

    # User-Agent sent on the requests fallback path.
    browser_user_agent: str = BROWSER_USER_AGENT
