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
    assert "/api/half/${h}.stl?${query}&v=${schema.geometry_version}" in js
    assert 'qs.set("v", schema.geometry_version)' in js  # downloads: STL, 3MF, Bambu
