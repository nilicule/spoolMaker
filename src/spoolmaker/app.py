"""Flask app: stateless GET API; the config is entirely in the query string."""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, Response, jsonify, request

from . import cache
from .config import config_schema, from_query, to_query, validate
from .stats import stats

STATIC_DIR = Path(__file__).parent / "static"
CACHE = "public, max-age=3600"


def _args() -> dict[str, str]:
    return {k: request.args.getlist(k)[0] for k in request.args}


def _model_response(data: bytes, mimetype: str, filename: str | None) -> Response:
    resp = Response(data, mimetype=mimetype)
    resp.headers["Cache-Control"] = CACHE
    if filename:
        resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return resp


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")

    @app.get("/")
    def index():
        return Response((STATIC_DIR / "index.html").read_bytes(), mimetype="text/html")

    @app.get("/api/schema")
    def schema():
        return jsonify(config_schema())

    @app.get("/api/stats")
    def api_stats():
        cfg = from_query(_args())
        errors = validate(cfg)
        body = {"valid": not errors, "errors": errors, "query": to_query(cfg)}
        if not errors:
            body.update(stats(cfg))
        return jsonify(body)

    @app.get("/api/half/<half>.stl")
    def half_stl(half: str):
        if half not in ("a", "b"):
            return jsonify(errors=[f"unknown half: {half}"]), 404
        cfg = from_query(_args())
        errors = validate(cfg)
        if errors:
            return jsonify(errors=errors), 422
        name = f"spool-{half}.stl" if request.args.get("download") else None
        return _model_response(cache.stl(cfg, half), "model/stl", name)

    @app.get("/api/spool.3mf")
    def spool_3mf():
        cfg = from_query(_args())
        errors = validate(cfg)
        if errors:
            return jsonify(errors=errors), 422
        return _model_response(cache.three_mf(cfg), "model/3mf", "spool.3mf")

    return app


def main() -> None:
    create_app().run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)
