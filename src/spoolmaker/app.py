"""Flask app: stateless GET API; the config is entirely in the query string."""

from __future__ import annotations

import hashlib
import html
import os
import re
from importlib import metadata
from pathlib import Path

from flask import Flask, Response, jsonify, request
from werkzeug.middleware.proxy_fix import ProxyFix

from . import cache
from .config import config_schema, from_query, is_true, to_query, validate
from .stats import stats

PKG_DIR = Path(__file__).parent
STATIC_DIR = PKG_DIR / "static"
# Model responses must revalidate: their URLs (notably the defaults' bare /api/half/a.stl)
# outlive geometry changes. The ETag makes a revalidation a cheap 304.
CACHE = "no-cache"


def geometry_version() -> str:
    """Short hash of everything that shapes the model files: the package version plus the
    geometry, config, export and Bambu project sources and data. The UI appends it to
    every model URL so a new build never reuses a stale browser-cached file."""
    try:
        version = metadata.version("spoolmaker")
    except metadata.PackageNotFoundError:
        version = "dev"
    h = hashlib.sha256(version.encode())
    files = [PKG_DIR / "config.py", PKG_DIR / "export.py", PKG_DIR / "filament.py",
             *sorted((PKG_DIR / "geometry").glob("*.py")),
             *sorted((PKG_DIR / "bambu").rglob("*.py")), *sorted((PKG_DIR / "bambu").rglob("*.json"))]
    for f in files:
        h.update(str(f.relative_to(PKG_DIR)).encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()[:12]


GEOMETRY_VERSION = geometry_version()


def _args() -> dict[str, str]:
    return {k: request.args.getlist(k)[0] for k in request.args}


def _model_response(data: bytes, mimetype: str, filename: str | None) -> Response:
    resp = Response(data, mimetype=mimetype)
    resp.headers["Cache-Control"] = CACHE
    resp.set_etag(hashlib.sha256(data).hexdigest()[:32])
    if filename:
        resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return resp.make_conditional(request)


class BasePath:
    """WSGI middleware for a proxy that forwards the full path (/spool/api/...): moves the
    BASE_PATH prefix from PATH_INFO to SCRIPT_NAME. Requests outside the prefix (such as a
    container health check on /healthz) pass through unchanged."""

    def __init__(self, app, prefix: str):
        self.app = app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path == self.prefix or path.startswith(self.prefix + "/"):
            environ["SCRIPT_NAME"] = self.prefix  # assign: the deployment fixes the mount point
            environ["PATH_INFO"] = path[len(self.prefix):] or "/"
        return self.app(environ, start_response)


# A mount point is "" or "/seg/seg..." of plain URL path characters, with no "." or ".."
# segments: nothing that could make <base href> point at another host or scheme.
_PREFIX_RE = re.compile(r"(/[A-Za-z0-9._~%-]+)*")
_DOT_SEGMENT = re.compile(r"/(\.|%2e)+(?=/|$)", re.IGNORECASE)


def safe_prefix(prefix: str) -> str | None:
    """The mount point with any trailing slash removed, or None if it isn't a plain path."""
    prefix = prefix.rstrip("/")
    if _PREFIX_RE.fullmatch(prefix) and not _DOT_SEGMENT.search(prefix):
        return prefix
    return None


def _base_path() -> str:
    """BASE_PATH env normalised to "/prefix" (no trailing slash), or "" for the root."""
    raw = os.environ.get("BASE_PATH", "").strip().strip("/")
    prefix = safe_prefix(f"/{raw}") if raw else ""
    if prefix is None:
        raise ValueError(f"BASE_PATH is not a plain URL path: {raw!r}")
    return prefix


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    prefix = _base_path()
    if prefix:
        app.wsgi_app = BasePath(app.wsgi_app, prefix)
    if is_true(os.environ.get("TRUST_PROXY")):
        # Behind a reverse proxy: honour X-Forwarded-For/-Proto/-Host (and -Prefix, unless
        # BASE_PATH fixes the mount point) from one hop. Only safe when the proxy sets (or
        # strips) these headers; never expose the app directly with this on.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1,
                                x_prefix=0 if prefix else 1)

    @app.get("/")
    def index():
        # Every URL in the page is relative. When the mount point is known (e.g. /spool/), a
        # <base> pins them to it so they resolve even when the page is opened as /spool.
        # When it isn't (no prefix, or one that isn't a plain path like //host, scheme:, ..),
        # there's no <base>: the URLs resolve against the page's own address, which also works
        # behind a proxy that strips the prefix without sending X-Forwarded-Prefix.
        root = safe_prefix(request.script_root) or ""
        page = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        if root:
            base = html.escape(root + "/", quote=True)
            page = page.replace('<meta charset="utf-8">',
                                f'<meta charset="utf-8">\n  <base href="{base}">', 1)
        resp = Response(page, mimetype="text/html")
        resp.headers["Cache-Control"] = "no-cache"  # the <base> depends on request headers
        return resp

    @app.get("/healthz")
    def healthz():  # liveness for container health checks; does no geometry work
        return Response("ok", mimetype="text/plain")

    @app.get("/favicon.ico")
    def favicon():  # browsers ask for it regardless of the <link rel="icon">s
        return app.send_static_file("favicon-32.png")

    @app.get("/api/schema")
    def schema():
        return jsonify({**config_schema(), "geometry_version": GEOMETRY_VERSION})

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
        name = f"spool-{half}.stl" if is_true(request.args.get("download")) else None
        return _model_response(cache.stl(cfg, half), "model/stl", name)

    @app.get("/api/spool.3mf")
    def spool_3mf():
        cfg = from_query(_args())
        errors = validate(cfg)
        if errors:
            return jsonify(errors=errors), 422
        return _model_response(cache.three_mf(cfg), "model/3mf", "spool.3mf")

    @app.get("/api/spool-bambu.3mf")
    def spool_bambu():
        cfg = from_query(_args())
        errors = validate(cfg)
        if errors:
            return jsonify(errors=errors), 422
        return _model_response(cache.bambu_project(cfg), "model/3mf",
                               f"spool-{cfg.bambu_printer}.3mf")

    return app


def main() -> None:
    create_app().run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)
