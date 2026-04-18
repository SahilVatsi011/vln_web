"""
Flask application factory.

Creates and configures the Flask app, registers route blueprints,
and wires up template/static directories.
"""

from flask import Flask

from vln_web.routes.pages import pages_blueprint
from vln_web.routes.api import api_blueprint
from vln_web.routes.smart_api import smart_api


def create_app() -> Flask:
    """Build and return a fully configured Flask application."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
        static_url_path="/static",
    )

    app.register_blueprint(pages_blueprint)
    app.register_blueprint(api_blueprint)
    app.register_blueprint(smart_api)

    return app
