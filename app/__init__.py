from __future__ import annotations
from flask import Flask

def create_app(env: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.update(SECRET_KEY="dev-secret")

    from .routes.main import bp as main_bp
    app.register_blueprint(main_bp)

    return app