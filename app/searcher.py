"""Keyword search and HTML-safe highlighting.

Two pure functions and one dataclass. No I/O.

Why a dataclass for the result instead of a dict:
    The template needs ``query``, ``count``, and ``lines`` — three named fields
    with stable types. A dataclass documents the contract once, lets the IDE
    auto-complete it, and removes the "is the key spelled 'lines' or 'matches'?"
    class of bugs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from markupsafe import Markup, escape


@dataclass
class SearchResult:
    """The shape of a successful search, ready for the template."""

    query: str
    count: int
    lines: list[Markup] = field(default_factory=list)


def search(text: str, query: str, max_lines: int) -> SearchResult:
    """Count occurrences of ``query`` in ``text`` (case-insensitive) and collect
    up to ``max_lines`` matching lines with the keyword highlighted.

    Counting and line-matching are separate concerns:
        - ``count``: total occurrences across the whole document, even those
          on the same line. ``str.count`` is O(n) and uses optimized C code.
        - ``lines``: a sample of distinct matching lines for display, capped
          at ``max_lines`` so the page stays compact for very common keywords.
    """
    needle = query.lower()
    count = text.lower().count(needle)

    matches: list[Markup] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or needle not in line.lower():
            continue
        matches.append(_highlight_line(line, query))
        if len(matches) >= max_lines:
            break

    return SearchResult(query=query, count=count, lines=matches)


def _highlight_line(line: str, query: str) -> Markup:
    """Return ``line`` HTML-escaped with ``query`` matches wrapped in <mark>.

    Critical security note:
        The line and the query both come (transitively) from external sources
        — the line from a fetched URL, the query from the request string. We
        MUST NOT pass either through Jinja's ``| safe`` filter without escaping.

        The order matters: escape first, THEN inject the <mark> tags into the
        already-escaped string. Doing it the other way around would leave any
        ``<`` or ``>`` characters in the line unescaped within the highlighted
        segments, opening an XSS hole.
    """
    escaped_line = str(escape(line))
    escaped_query = str(escape(query))
    if not escaped_query:
        return Markup(escaped_line)

    # ``re.escape`` neutralizes any regex metacharacters in the user's keyword
    # so e.g. searching for "(love)" doesn't blow up the regex engine.
    pattern = re.compile(re.escape(escaped_query), re.IGNORECASE)
    highlighted = pattern.sub(
        lambda m: f"<mark>{m.group(0)}</mark>",
        escaped_line,
    )
    # Markup() tells Jinja "this string is already safe to render verbatim".
    return Markup(highlighted)
