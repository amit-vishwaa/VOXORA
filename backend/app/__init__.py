"""Voxora AI backend: Flask app factory. Serves the JSON API (/api/*) and the static frontend (/)."""
import os
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from . import config, db
from .security import ApiError


def create_app(test_config=None):
    config.load_dotenv()
    app = Flask(__name__, static_folder=None)
    cfg = dict(test_config or {})
    if "DATABASE" not in cfg:
        inst = Path(os.environ.get("VOXORA_INSTANCE_DIR") or config.DEFAULT_INSTANCE)
        inst.mkdir(parents=True, exist_ok=True)
        cfg.setdefault("DATABASE", str(inst / "voxora.db"))
        cfg.setdefault("RECORDINGS_DIR", str(inst / "recordings"))
        cfg.setdefault("SECRET_KEY", config.get_secret(inst))
    cfg.setdefault("JWT_HOURS", int(os.environ.get("VOXORA_JWT_HOURS", 12)))
    cfg.setdefault("MAX_CONTENT_LENGTH", 1024 * 1024)
    app.config.update(cfg)
    Path(app.config["RECORDINGS_DIR"]).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    with app.app_context():
        db.run_migrations()

    from .routes import auth, admin, agents, calls, business
    for m in (auth, admin, agents, calls, business):
        app.register_blueprint(m.bp)

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", mode="simulated-providers")

    @app.errorhandler(ApiError)
    def api_error(e):
        return jsonify(error=e.message), e.status

    @app.errorhandler(404)
    def nf(_e):
        return jsonify(error="Not found"), 404

    @app.errorhandler(405)
    def na(_e):
        return jsonify(error="Method not allowed"), 405

    @app.errorhandler(Exception)
    def boom(e):
        app.logger.exception("Unhandled error")
        return jsonify(error="Internal server error"), 500

    @app.after_request
    def headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = ("default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                                                   "media-src 'self' blob:; frame-ancestors 'none'")
        if resp.mimetype == "application/json":
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/", defaults={"path": "index.html"})
    @app.get("/<path:path>")
    def frontend(path):
        if path.startswith("api/"):
            return jsonify(error="Not found"), 404
        return send_from_directory(config.FRONTEND_DIR, path)

    return app
