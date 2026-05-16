# Search Keyword Occurrences

A small Flask web app that fetches text content from any URL and counts how many times a keyword appears, showing the matching lines with the keyword highlighted.

**Live demo:** https://search-keyword-occurrences.replit.app

---

## What it does

1. You paste a URL (plain-text file or HTML page) and a keyword.
2. The app fetches the URL, extracts readable text (HTML is parsed and stripped down to the main content), and counts case-insensitive occurrences of your keyword.
3. It shows the total count plus up to 10 matching lines with each match wrapped in `<mark>` for visibility.

Originally built for searching lyric sites; the URL/keyword pipeline works for any plain-text or article-style HTML source.

---

## Features

- **Works on plain text and HTML** — plain text is searched as-is; HTML is run through an extraction pipeline (BeautifulSoup) that strips `<script>`, `<style>`, `<nav>`, `<footer>`, etc. and pulls the main article/content block.
- **Browser-fingerprint impersonation** — uses `curl_cffi` to mimic a real Chrome TLS/HTTP-2 fingerprint, bypassing many soft anti-bot checks. Falls back to plain `requests` if curl_cffi is unavailable.
- **SSRF-hardened** — validates every URL (initial request *and* every redirect hop) against private / loopback / link-local / multicast / reserved IPs so the server can't be tricked into hitting internal targets like cloud metadata.
- **XSS-safe highlighting** — both the fetched text and the user's keyword are HTML-escaped before `<mark>` tags are injected.
- **Resource caps** — 4 MB response limit, 15 s timeout, 2048-char URL limit, 200-char keyword limit, max 10 result lines.

---

## Architecture

The code is split into small focused modules under `app/`. Each module has a single, clear responsibility:

| File | Responsibility |
|---|---|
| `main.py` | 4-line entry point — exposes `app` for gunicorn / `python main.py` |
| `app/__init__.py` | Flask app factory (`create_app`) |
| `app/config.py` | Frozen `AppConfig` dataclass — all tunable knobs in one place |
| `app/results.py` | Generic `Result[T]` type replacing fragile `(value, error)` tuples |
| `app/security.py` | URL safety / SSRF guard (kept separate so security code is easy to audit) |
| `app/fetcher.py` | HTTP fetch with browser-fingerprint impersonation, fallback chain, and manual safe-redirect following |
| `app/extractor.py` | HTML → clean plain text (pure function) |
| `app/searcher.py` | Keyword search + HTML-safe `<mark>` highlighting (pure function) |
| `app/routes.py` | Flask blueprint — thin orchestration only |
| `app/templates/index.html` | Single-page dark-mode UI |

Patterns deliberately avoided to keep the project right-sized: DI containers, abstract base classes, repository/DAO layers, DTO classes, async, caching. They'd be over-engineering for an app this size.

Inline comments throughout explain *why* each decision was made (not just what the code does) so the codebase reads cleanly for both humans and AI coding assistants.

---

## Running locally

Requires **Python 3.11+**.

```bash
# 1. Install dependencies (using uv — recommended)
uv sync

# 2a. Dev server
python main.py
# → http://localhost:5000

# 2b. Production-style server
gunicorn --bind 0.0.0.0:5000 --reuse-port main:app
```

Alternative with pip:

```bash
pip install flask gunicorn requests curl-cffi beautifulsoup4 lxml markupsafe
python main.py
```

---

## Tech stack

- **Flask 3** — web framework
- **Gunicorn** — production WSGI server
- **curl_cffi** — Chrome fingerprint impersonation (primary HTTP client)
- **requests** — fallback HTTP client
- **BeautifulSoup 4 + lxml** — HTML parsing / extraction
- **MarkupSafe** — XSS-safe template rendering

---

## Known limitations

- **Aggressive anti-bot sites** (e.g. Genius) may still return HTTP 403 — the server's datacenter IP is on most block lists. The error message points users at a raw-text URL alternative (e.g. raw GitHub).
- **No caching** — every search re-fetches the source URL. Fine for the current load profile; would be the first thing to add if usage grew.
- **No JavaScript rendering** — pages that build their content client-side will yield empty extraction.

---

## License

No license declared. If you'd like to reuse this code, please open an issue first.
