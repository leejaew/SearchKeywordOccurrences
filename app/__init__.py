"""Application package and Flask app factory.

The factory pattern (``create_app(...)``) is the Flask community standard for
non-trivial apps because it:

    - Lets tests build a fresh Flask instance per test with custom config,
      avoiding shared global state between test runs.
    - Defers app construction so import-time side effects don't bite when
      modules import ``app`` only for type hints.
    - Makes the wiring (which blueprints, which config, which extensions)
      explicit and discoverable in one place.
"""

from __future__ import annotations

from typing import Optional

from flask import Flask

from .config import AppConfig
from .routes import bp as main_blueprint
from .routes import register_error_handlers

__all__ = ["create_app", "AppConfig"]


def create_app(config: Optional[AppConfig] = None) -> Flask:
    """Build and return a configured Flask application instance.

    Args:
        config: Optional :class:`AppConfig` override. Defaults to the standard
            production config when not provided.
    """
    app = Flask(__name__)

    # Stash the AppConfig on Flask's own config dict so routes can retrieve it
    # via ``current_app.config["APP_CONFIG"]``. Using Flask's existing config
    # bag avoids introducing a separate accessor pattern just for one object.
    app.config["APP_CONFIG"] = config or AppConfig()

    # Wire the blueprint(s) and error handlers. Adding more pages later is
    # purely additive: define a blueprint, register it here.
    app.register_blueprint(main_blueprint)
    register_error_handlers(app)

    return app
