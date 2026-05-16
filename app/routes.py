"""HTTP route handlers — the orchestration layer.

Routes here are deliberately thin: parse inputs, call the right service
modules in order, render the template. All real work lives in the security
/ fetcher / extractor / searcher modules so the routes stay readable and
the business logic stays unit-testable without spinning up a Flask test client.
"""

from __future__ import annotations

from flask import Blueprint, current_app, render_template, request

from .config import AppConfig
from .fetcher import fetch_text
from .searcher import SearchResult, search
from .security import is_safe_url

# Single blueprint for the (currently single) page. Easy to extend with more
# routes (e.g. a JSON API endpoint) without touching the app factory.
bp = Blueprint("main", __name__)


@bp.route("/", methods=["GET"])
def index():
    """Search page — accepts ``?url=<source>&q=<keyword>`` and renders results."""
    config: AppConfig = current_app.config["APP_CONFIG"]

    # Sanitize inputs at the boundary: strip whitespace, cap length, fall back
    # to the default URL if the field came in empty.
    query = request.args.get("q", "").strip()[: config.max_query_length]
    url = (
        request.args.get("url", "").strip()[: config.max_url_length]
        or config.default_text_url
    )

    result, error = _run_search(url, query, config) if query else (None, None)

    return render_template(
        "index.html",
        result=result,
        error=error,
        query=query,
        url=url,
        default_url=config.default_text_url,
        max_result_lines=config.max_result_lines,
    )


def _run_search(
    url: str, query: str, config: AppConfig
) -> tuple[SearchResult | None, str | None]:
    """Pipeline: validate URL → fetch text → run search.

    Returns a ``(result, error)`` pair where exactly one is non-None. We use
    a plain tuple here (not Result[T]) because the template needs both fields
    rendered side-by-side anyway.
    """
    url_check = is_safe_url(url, config)
    if not url_check.is_ok:
        return None, url_check.error

    fetched = fetch_text(url, config)
    if not fetched.is_ok:
        return None, fetched.error

    return search(fetched.value, query, config.max_result_lines), None


def register_error_handlers(app) -> None:
    """Attach app-wide error handlers. Called by the app factory."""

    @app.errorhandler(404)
    def _not_found(_error):
        # Render the index template so visitors hitting a typo URL still see
        # a working search form rather than a default Flask 404 page.
        config: AppConfig = app.config["APP_CONFIG"]
        return render_template(
            "index.html",
            result=None,
            error=None,
            query="",
            url=config.default_text_url,
            default_url=config.default_text_url,
            max_result_lines=config.max_result_lines,
        ), 404
