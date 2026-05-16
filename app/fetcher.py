"""HTTP fetching with browser-fingerprint impersonation, safe redirect
following, and graceful fallback.

Strategy (a deliberate two-step fallback, NOT a full Strategy pattern):
    1. Try ``curl_cffi`` impersonating Chrome 131 — this matches a real
       browser's TLS + HTTP/2 fingerprint and bypasses many soft anti-bot
       checks (Cloudflare's basic IUAM, Akamai light mode, etc.).
    2. If curl_cffi raises (binary missing, network glitch), fall back to
       plain ``requests`` with a realistic User-Agent so the app keeps working.

Why two private functions instead of an abstract base class:
    There are exactly two fetch strategies and they're tried in a fixed order.
    A Strategy interface with concrete subclasses would add ceremony with no
    real flexibility benefit. If a third strategy ever appears (e.g. a paid
    proxy service), THAT is the moment to introduce a protocol — not before.

Redirect handling — security-critical:
    Both HTTP libraries support ``allow_redirects=True``, but we deliberately
    set it to ``False`` and follow redirects manually. Reason: the SSRF guard
    only validates the *initial* URL the user submitted. If we let the library
    auto-follow, an attacker could submit a public URL that 30x-redirects to
    an internal address (e.g. cloud-metadata 169.254.169.254), and our guard
    would never see the final destination. By following manually we re-run
    :func:`is_safe_url` on every Location header before issuing the next hop.

Returns:
    ``Result[str]`` containing either the cleaned plain-text body, or a
    user-facing error string. HTML responses are passed through the extractor
    here so callers always get plain text.
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urljoin

import requests
from curl_cffi import requests as cffi_requests

from .config import AppConfig
from .extractor import extract_text_from_html
from .results import Result
from .security import is_safe_url

# Cap the redirect chain. Real sites rarely chain more than 2-3 hops; allowing
# a small budget covers legitimate cases (HTTP→HTTPS→canonical-host) while
# preventing infinite loops and slow-loris redirect attacks.
_MAX_REDIRECTS = 5

# HTTP status codes we treat as redirects to follow. 3xx codes outside this
# set (e.g. 304 Not Modified) are surfaced to the caller as-is.
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def fetch_text(url: str, config: AppConfig) -> Result[str]:
    """Fetch ``url`` and return its readable text content.

    Wraps the safe-redirect loop and the response-processing pipeline.
    """
    response_or_error = _fetch_following_redirects_safely(url, config)
    if isinstance(response_or_error, Result):
        # Failure path — already a Result.fail with a user-facing message.
        return response_or_error

    response = response_or_error
    try:
        return _process_response(response, config)
    finally:
        # Both libraries expose ``close``; ignore failures since we may be in
        # an error path already and we don't want to mask the real cause.
        try:
            response.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Safe redirect handling
# ---------------------------------------------------------------------------

def _fetch_following_redirects_safely(
    url: str, config: AppConfig
) -> "Any | Result[str]":
    """Issue a GET, then manually follow up to ``_MAX_REDIRECTS`` hops,
    re-validating every redirect target through :func:`is_safe_url`.

    Returns the final response object on success, or a ``Result.fail`` if
    the chain exceeds the budget, hits an unsafe target, or both transport
    strategies fail at the network layer.
    """
    current_url = url

    for _ in range(_MAX_REDIRECTS + 1):  # +1 = the original request itself
        response = _fetch_once(current_url, config)
        if response is None:
            return Result.fail("Request failed: could not reach the URL.")

        # Not a redirect — give the response back to the caller for processing.
        if response.status_code not in _REDIRECT_STATUSES:
            return response

        # Redirect path: read the Location header, resolve relative redirects
        # against the current URL, then re-validate before following.
        location = response.headers.get("Location")
        try:
            response.close()
        except Exception:
            pass

        if not location:
            return Result.fail("Source returned a redirect without a target.")

        next_url = urljoin(current_url, location)
        safety = is_safe_url(next_url, config)
        if not safety.is_ok:
            # Surface the SSRF rejection with context so the user understands
            # the request was blocked at a redirect hop, not at submission.
            return Result.fail(f"Blocked unsafe redirect: {safety.error}")

        current_url = next_url

    return Result.fail("Too many redirects.")


def _fetch_once(url: str, config: AppConfig) -> Optional[Any]:
    """Single GET with the curl_cffi → requests fallback chain.

    Crucially, ``allow_redirects=False`` is set on both libraries so the
    safe-redirect loop above stays in control of the chain.
    """
    return _fetch_with_curl_cffi(url, config) or _fetch_with_requests(url, config)


# ---------------------------------------------------------------------------
# Private fetch strategies
# ---------------------------------------------------------------------------

def _fetch_with_curl_cffi(url: str, config: AppConfig) -> Optional[Any]:
    """Primary strategy: real Chrome TLS + HTTP/2 fingerprint via curl_cffi.

    Returns the response object on success, or ``None`` if curl_cffi raised
    (caller will then try the requests fallback).
    """
    try:
        return cffi_requests.get(
            url,
            timeout=config.request_timeout,
            impersonate="chrome131",
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            allow_redirects=False,  # see module docstring on safe redirects
        )
    except Exception:
        # We catch broad Exception here on purpose: curl_cffi may raise from
        # native code with non-standard exception types, and the only sensible
        # response is "try the next strategy".
        return None


def _fetch_with_requests(url: str, config: AppConfig) -> Optional[Any]:
    """Fallback strategy: vanilla ``requests`` with a realistic User-Agent.

    Returns the response object on success, or ``None`` if the network hop
    itself failed (DNS / connection / TLS error).
    """
    try:
        return requests.get(
            url,
            timeout=config.request_timeout,
            stream=False,
            headers={
                "User-Agent": config.browser_user_agent,
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
                "Accept-Language": "en-US,en;q=0.9",
            },
            allow_redirects=False,  # see module docstring on safe redirects
        )
    except requests.RequestException:
        return None


# ---------------------------------------------------------------------------
# Response processing pipeline
# ---------------------------------------------------------------------------

def _process_response(response: Any, config: AppConfig) -> Result[str]:
    """Turn an HTTP response into plain text or a user-facing error.

    Steps (each returns early on failure for readability):
        1. Map common error statuses (403, 429) to friendly messages.
        2. Validate the Content-Type against text/HTML whitelists.
        3. Enforce the byte-size cap on the body.
        4. Decode bytes → str using the response's stated encoding.
        5. Sniff for HTML when Content-Type is missing.
        6. If HTML, route through the extractor; otherwise return raw text.
    """
    # --- Step 1: status-code triage -----------------------------------------
    status_error = _status_to_error(response.status_code)
    if status_error:
        return Result.fail(status_error)

    # --- Step 2: content-type triage ----------------------------------------
    content_type = (
        response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    )
    is_html = any(content_type.startswith(t) for t in config.html_content_types)
    is_text = any(content_type.startswith(t) for t in config.allowed_text_content_types)

    if content_type and not is_html and not is_text:
        return Result.fail(f"Source content type '{content_type}' is not text or HTML.")

    # --- Step 3: size cap ---------------------------------------------------
    raw = response.content
    if len(raw) > config.max_content_bytes:
        return Result.fail(
            f"Source is too large (max {config.max_content_bytes // (1024 * 1024)} MB)."
        )

    # --- Step 4: decode bytes ----------------------------------------------
    body = _decode_body(raw, response.encoding)

    # --- Step 5: HTML sniff when Content-Type is empty/missing -------------
    if not content_type:
        is_html = bool(re.search(r"<\s*html\b", body[:4096], re.IGNORECASE))

    # --- Step 6: dispatch to extractor or return raw -----------------------
    if is_html:
        text = extract_text_from_html(body, config)
        if not text or len(text) < 20:
            return Result.fail("Could not extract any readable text from the page.")
        return Result.ok(text)

    return Result.ok(body)


def _status_to_error(status_code: int) -> Optional[str]:
    """Map HTTP status codes to user-facing error messages.

    Returns ``None`` when the status is 200 (caller should keep going).
    Specific codes get tailored messages; everything else falls through to
    a generic "HTTP <n>" message.
    """
    if status_code == 200:
        return None
    if status_code == 403:
        return (
            "Source returned HTTP 403 (Forbidden). The site is blocking automated "
            "requests from this server. Try a URL that points directly to a plain-text "
            "file (for example a raw GitHub link), or a site without bot protection."
        )
    if status_code == 429:
        return "Source returned HTTP 429. Too many requests — try again later."
    return f"Source returned HTTP {status_code}."


def _decode_body(raw: bytes, encoding: Optional[str]) -> str:
    """Decode response bytes using the declared encoding, with a UTF-8 fallback.

    ``errors="replace"`` keeps a single bad byte from killing the whole search;
    visitors get a slightly garbled character at worst, instead of a 500.
    """
    encoding = encoding or "utf-8"
    try:
        return raw.decode(encoding, errors="replace")
    except (LookupError, TypeError):
        # LookupError: unknown encoding name.  TypeError: encoding wasn't a str.
        return raw.decode("utf-8", errors="replace")
