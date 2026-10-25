import io
import zipfile

import pytest

from spoolmaker.app import create_app


@pytest.fixture
def client():
    return create_app().test_client()


def test_index(client): assert client.get("/").status_code == 200
def test_static_assets(client):
    for path in ("/static/app.js", "/static/style.css"):
        assert client.get(path).status_code == 200, path


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.get_data(as_text=True) == "ok"


def test_schema(client): assert "pattern" in client.get("/api/schema").json["fields"]


def test_stats_default(client):
    j = client.get("/api/stats").json
    assert j["valid"] and j["weight_g"]["total"] > 0 and len(j["gauge"]) == 4


def test_stats_estimate(client):
    j = client.get("/api/stats?bambu_printer=h2d").json
    assert 0 < j["estimate_g"]["a"] < j["weight_g"]["a"]
    assert "Bambu Lab H2D" in j["estimate_note"]


def test_stats_invalid(client):
    j = client.get("/api/stats?refill=custom&coil_inner_diameter=58").json
    assert not j["valid"] and j["errors"] and "weight_g" not in j


def test_stl(client):
    r = client.get("/api/half/a.stl?pattern=spokes")
    assert r.status_code == 200 and r.mimetype == "model/stl" and len(r.data) > 84
    assert r.headers["Cache-Control"] == "no-cache"
    assert "Content-Disposition" not in r.headers


def test_stl_download(client):
    r = client.get("/api/half/b.stl?download=1")
    assert "attachment" in r.headers["Content-Disposition"]
    assert "spool-b.stl" in r.headers["Content-Disposition"]


@pytest.mark.parametrize("flag", ["0", "false", "off", "", "no"])
def test_stl_download_off(client, flag):
    r = client.get(f"/api/half/b.stl?download={flag}")
    assert r.status_code == 200 and "Content-Disposition" not in r.headers


def test_3mf(client):
    r = client.get("/api/spool.3mf")
    assert r.status_code == 200 and zipfile.is_zipfile(io.BytesIO(r.data))
    assert "spool.3mf" in r.headers["Content-Disposition"]


def test_invalid_config_returns_422(client):
    r = client.get("/api/half/a.stl?refill=custom&coil_inner_diameter=58")
    assert r.status_code == 422 and r.json["errors"]
    assert client.get("/api/spool.3mf?refill=custom&coil_inner_diameter=58").status_code == 422


def test_bad_half_404(client): assert client.get("/api/half/c.stl").status_code == 404


def test_bambu_project(client):
    r = client.get("/api/spool-bambu.3mf?bambu_printer=p1s")
    assert r.status_code == 200 and r.mimetype == "model/3mf"
    assert "attachment" in r.headers["Content-Disposition"]
    assert "spool-p1s.3mf" in r.headers["Content-Disposition"]
    assert r.headers["Cache-Control"] == "no-cache" and r.headers["ETag"]
    z = zipfile.ZipFile(io.BytesIO(r.data))
    assert '"printer_model": "Bambu Lab P1S"' in z.read("Metadata/project_settings.config").decode()


def test_bambu_project_default_printer(client):
    r = client.get("/api/spool-bambu.3mf?bambu_printer=garbage")
    assert r.status_code == 200 and "spool-a1.3mf" in r.headers["Content-Disposition"]


def test_bambu_project_invalid_422(client):
    r = client.get("/api/spool-bambu.3mf?refill=custom&coil_inner_diameter=58")
    assert r.status_code == 422 and r.json["errors"]


def test_schema_geometry_version(client):
    from spoolmaker.app import GEOMETRY_VERSION, geometry_version

    v = client.get("/api/schema").json["geometry_version"]
    assert v == GEOMETRY_VERSION == geometry_version() and len(v) == 12


def test_stl_etag_and_304(client):
    r = client.get("/api/half/a.stl?pattern=spokes")
    etag = r.headers["ETag"]
    assert r.status_code == 200 and etag.startswith('"') and not etag.startswith('W/')
    assert r.headers["Cache-Control"] == "no-cache"
    again = client.get("/api/half/a.stl?pattern=spokes", headers={"If-None-Match": etag})
    assert again.status_code == 304 and not again.data
    other = client.get("/api/half/a.stl?pattern=holes", headers={"If-None-Match": etag})
    assert other.status_code == 200 and other.headers["ETag"] != etag


def test_3mf_etag(client):
    r = client.get("/api/spool.3mf")
    assert r.headers["Cache-Control"] == "no-cache"
    assert client.get("/api/spool.3mf", headers={"If-None-Match": r.headers["ETag"]}).status_code == 304


def test_app_js_versions_model_urls():
    from spoolmaker.app import STATIC_DIR

    js = (STATIC_DIR / "app.js").read_text()
    assert 'modelQs.set("v", schema.geometry_version)' in js  # preview
    assert "half/${h}.stl?${modelQs}" in js
    assert 'qs.set("v", schema.geometry_version)' in js  # downloads: STL, 3MF, Bambu


@pytest.mark.parametrize("path, mimetype", [
    ("/favicon.ico", "image/png"),
    ("/static/favicon.svg", "image/svg+xml"),
    ("/static/favicon-32.png", "image/png"),
    ("/static/apple-touch-icon.png", "image/png"),
])
def test_favicons(client, path, mimetype):
    r = client.get(path)
    assert r.status_code == 200 and r.mimetype == mimetype and r.data


def test_index_links_favicons(client):
    html = client.get("/").data.decode()
    for href in ("static/favicon.svg", "static/favicon-32.png", "static/apple-touch-icon.png"):
        assert f'href="{href}"' in html


def test_printer_hint_matches_js():
    """The static hint names the default printer exactly as app.js will, so nothing shifts."""
    from spoolmaker.app import STATIC_DIR
    from spoolmaker.bambu import DEFAULT_PRINTER, PRINTERS

    html = (STATIC_DIR / "index.html").read_text()
    assert f'<span id="bambu-printer">{PRINTERS[DEFAULT_PRINTER].name}</span>' in html


def test_ui_drops_solid_weight():
    from spoolmaker.app import STATIC_DIR

    js = (STATIC_DIR / "app.js").read_text()
    assert "solid" not in js.lower()
    assert "-solid" not in (STATIC_DIR / "index.html").read_text()


# ---------- sub-path hosting ----------

def test_index_base_root(client):
    assert '<base href="/">' in client.get("/").get_data(as_text=True)


def test_index_base_script_name(client):
    page = client.get("/", environ_overrides={"SCRIPT_NAME": "/spool"}).get_data(as_text=True)
    assert '<base href="/spool/">' in page


def test_forwarded_prefix_ignored_without_trust_proxy(monkeypatch):
    monkeypatch.delenv("TRUST_PROXY", raising=False)
    page = create_app().test_client().get("/", headers={"X-Forwarded-Prefix": "/spool"})
    assert '<base href="/">' in page.get_data(as_text=True)


def test_forwarded_prefix_with_trust_proxy(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY", "1")
    c = create_app().test_client()
    page = c.get("/", headers={"X-Forwarded-Prefix": "/spool"}).get_data(as_text=True)
    assert '<base href="/spool/">' in page
    evil = c.get("/", headers={"X-Forwarded-Prefix": "/x<script>"}).get_data(as_text=True)
    assert "<script>" not in evil and '<base href="/x&lt;script&gt;/">' in evil


@pytest.mark.parametrize("base_path", ["/spool", "spool/", "/spool/"])
def test_base_path_env(monkeypatch, base_path):
    monkeypatch.setenv("BASE_PATH", base_path)
    monkeypatch.delenv("TRUST_PROXY", raising=False)
    c = create_app().test_client()
    assert '<base href="/spool/">' in c.get("/spool/").get_data(as_text=True)
    assert '<base href="/spool/">' in c.get("/spool").get_data(as_text=True)
    assert c.get("/spool/api/stats").json["valid"]
    assert c.get("/spool/static/app.js").status_code == 200
    r = c.get("/spool/api/half/a.stl")
    assert r.status_code == 200 and r.mimetype == "model/stl"
    assert '<base href="/">' in c.get("/").get_data(as_text=True)  # outside the prefix


def test_frontend_urls_are_relative():
    import re
    from spoolmaker.app import STATIC_DIR
    for name in ("index.html", "app.js", "style.css"):
        text = (STATIC_DIR / name).read_text(encoding="utf-8")
        hits = re.findall(r"""["'`(]/(?:api|static)\b""", text)
        assert not hits, (name, hits)
