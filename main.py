"""Process entry point.

Gunicorn loads ``main:app`` in production; the ``__main__`` block runs the
Flask dev server when invoked directly (used by the dev workflow).

Keeping this file tiny is intentional — all real wiring lives in the ``app``
package's :func:`app.create_app` factory.
"""

from app import create_app

app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
