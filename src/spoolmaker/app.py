"""Flask app: stateless GET API; the config is entirely in the query string."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from flask import Flask, Response, jsonify, request
from manifold3d import Manifold

from .config import SpoolConfig, config_schema, from_query, to_query, validate
from .export import to_3mf, to_stl
from .geometry.build import build_half
from .stats import stats

STATIC_DIR = Path(__file__).parent / "static"
CACHE = "public, max-age=3600"


@lru_cache(maxsize=64)
def _half(cfg: SpoolConfig, half: str) -> Manifold:
    return build_half(cfg, half)


@lru_cache(maxsize=64)
def _stl(cfg: SpoolConfig, half: str) -> bytes:
    return to_stl(_half(cfg, half))


@lru_cache(maxsize=16)
def _3mf(cfg: SpoolConfig) -> bytes:
    return to_3mf({"spool-half-a": _half(cfg, "a"), "spool-half-b": _half(cfg, "b")})


def _args() -> dict[str, str]:
    return {k: request.args.getlist(k)[0] for k in request.args}


def _model_response(data: bytes, mimetype: str, filename: str | None) -> Response:
    resp = Response(data, mimetype=mimetype)
    resp.headers["Cache-Control"] = CACHE
    if filename:
        resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return resp


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)

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
        return _model_response(_stl(cfg, half), "model/stl", name)

    @app.get("/api/spool.3mf")
    def spool_3mf():
        cfg = from_query(_args())
        errors = validate(cfg)
        if errors:
            return jsonify(errors=errors), 422
        return _model_response(_3mf(cfg), "model/3mf", "spool.3mf")

    return app


def main() -> None:
    create_app().run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)
