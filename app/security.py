"""URL safety / SSRF protection.

Kept in its own module (rather than folded into ``fetcher``) because:
    - Security-critical code benefits from being prominent and easy to audit.
    - Pure validation with zero I/O — trivially testable in isolation.
    - Gives us a single chokepoint to extend (e.g. domain allowlists later).

What we defend against:
    1. Non-http(s) schemes (e.g. file://, gopher://) that could read local files
       or hit weird protocols.
    2. Server-Side Request Forgery (SSRF): URLs that resolve to internal /
       private IPs. A malicious user could otherwise probe the cloud metadata
       endpoint (169.254.169.254), localhost services, or other reachable
       internal hosts via our server.

What we explicitly do NOT defend against here:
    - DNS rebinding attacks (would require resolving + pinning the IP and
      passing it to the HTTP client). Out of scope for the current threat model
      since we don't authenticate against internal services.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from .config import AppConfig
from .results import Result


def is_safe_url(url: str, config: AppConfig) -> Result[str]:
    """Validate a user-submitted URL and return it on success, or a friendly
    error message on rejection.

    Performs four checks, in cheapest-first order so we fail fast:
        1. Length cap — early reject before any parsing.
        2. Scheme — must be http or https.
        3. Hostname — must be present and DNS-resolvable.
        4. SSRF — none of the resolved IPs may be private / loopback /
           link-local / multicast / reserved / unspecified.
    """
    # --- Check 1: length cap ---
    if not url or len(url) > config.max_url_length:
        return Result.fail("URL is missing or too long.")

    # --- Check 2: parseable + correct scheme ---
    try:
        parsed = urlparse(url)
    except ValueError:
        return Result.fail("URL could not be parsed.")

    if parsed.scheme not in ("http", "https"):
        return Result.fail("URL must start with http:// or https://.")

    if not parsed.hostname:
        return Result.fail("URL is missing a hostname.")

    # --- Check 3: DNS resolution ---
    try:
        addr_infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        return Result.fail("Could not resolve hostname.")

    # --- Check 4: SSRF guard ---
    # Some hostnames resolve to multiple IPs (IPv4 + IPv6, round-robin pools).
    # We must reject if *any* resolved address points somewhere internal:
    # an attacker could otherwise pick a hostname whose A-record is public
    # but whose AAAA-record points at an internal IPv6 address.
    for info in addr_infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            # Skip anything that doesn't parse as a real IP — getaddrinfo
            # shouldn't return one, but defensive.
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return Result.fail("URL points to a non-public address.")

    return Result.ok(url)
