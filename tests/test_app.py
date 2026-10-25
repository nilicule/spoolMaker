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
    assert "max-age=3600" in r.headers["Cache-Control"]
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
    assert "max-age=3600" in r.headers["Cache-Control"]
    z = zipfile.ZipFile(io.BytesIO(r.data))
    assert '"printer_model": "Bambu Lab P1S"' in z.read("Metadata/project_settings.config").decode()


def test_bambu_project_default_printer(client):
    r = client.get("/api/spool-bambu.3mf?bambu_printer=garbage")
    assert r.status_code == 200 and "spool-a1.3mf" in r.headers["Content-Disposition"]


def test_bambu_project_invalid_422(client):
    r = client.get("/api/spool-bambu.3mf?refill=custom&coil_inner_diameter=58")
    assert r.status_code == 422 and r.json["errors"]
