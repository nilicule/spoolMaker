import io
import json
import os
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

import numpy as np
import pytest

from spoolmaker.bambu import DEFAULT_PRINTER, PLATE_GAP, PRINTERS, plate_offset, to_bambu_project
from spoolmaker.config import SpoolConfig
from spoolmaker.geometry.build import build_half
from test_export import _edges_closed

CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
PROD = "{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}"
BAMBU_CLI = Path("/Applications/BambuStudio.app/Contents/MacOS/BambuStudio")
# Slicing with the real Bambu Studio takes minutes: opt in with SPOOLMAKER_BAMBU_LIVE=1.
LIVE = os.environ.get("SPOOLMAKER_BAMBU_LIVE") == "1" and BAMBU_CLI.exists()
REQUIRED = {
    "[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model", "3D/_rels/3dmodel.model.rels",
    "Metadata/project_settings.config", "Metadata/model_settings.config",
}


@lru_cache(maxsize=1)
def _halves():
    cfg = SpoolConfig()
    return {"spool-half-a": build_half(cfg, "a"), "spool-half-b": build_half(cfg, "b")}


@lru_cache(maxsize=None)
def _project(printer: str) -> bytes:
    return to_bambu_project(_halves(), printer)


def _zip(printer: str) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(_project(printer)))


def _meta(el, key):
    return next(m.get("value") for m in el.findall("metadata") if m.get("key") == key)


def test_printers_index():
    assert DEFAULT_PRINTER in PRINTERS and PRINTERS[DEFAULT_PRINTER].printer_model == "Bambu Lab A1"
    for p in PRINTERS.values():
        w, d = p.size
        assert w >= 205 and d >= 205, p.key
        assert p.printer_model.startswith("Bambu Lab ")
        assert p.app_version.count(".") == 3


def test_required_parts():
    z = _zip(DEFAULT_PRINTER)
    names = set(z.namelist())
    assert REQUIRED <= names
    rels = z.read("3D/_rels/3dmodel.model.rels").decode()
    for path in ("3D/Objects/object_1.model", "3D/Objects/object_2.model"):
        assert path in names and f'Target="/{path}"' in rels
    assert not any(n.endswith(".png") for n in names)


def test_application_metadata():
    root = ET.fromstring(_zip(DEFAULT_PRINTER).read("3D/3dmodel.model"))
    meta = {m.get("name"): m.text for m in root.findall(f"{CORE}metadata")}
    assert meta["Application"].startswith("BambuStudio-")
    assert meta["BambuStudio:3mfVersion"] == "1"
    assert root.get("requiredextensions") == "p"


@pytest.mark.parametrize("printer", sorted(PRINTERS))
def test_project_settings_match_printer(printer):
    s = json.loads(_zip(printer).read("Metadata/project_settings.config"))
    p = PRINTERS[printer]
    assert s["printer_model"] == p.printer_model
    pts = [tuple(float(v) for v in xy.split("x")) for xy in s["printable_area"]]
    xs, ys = zip(*pts)
    assert (min(xs), min(ys), max(xs), max(ys)) == p.bed
    assert s["print_settings_id"] == p.process
    assert s["filament_settings_id"][0] == p.filament


def _plates(z: zipfile.ZipFile):
    root = ET.fromstring(z.read("Metadata/model_settings.config"))
    return root, root.findall("plate")


def test_plates_one_instance_each():
    z = _zip(DEFAULT_PRINTER)
    root, plates = _plates(z)
    assert [_meta(p, "plater_id") for p in plates] == ["1", "2"]
    model = ET.fromstring(z.read("3D/3dmodel.model"))
    build_ids = [i.get("objectid") for i in model.iter(f"{CORE}item")]
    instances = [p.findall("model_instance") for p in plates]
    assert all(len(i) == 1 for i in instances)
    objs = [_meta(i[0], "object_id") for i in instances]
    assert objs == build_ids and len(set(objs)) == 2
    ids = [_meta(i, "identify_id") for i in root.iter("model_instance")]
    assert len(set(ids)) == len(ids)
    assert {o.get("id") for o in root.findall("object")} == set(build_ids)


@pytest.mark.parametrize("printer", sorted(PRINTERS))
def test_each_half_inside_its_plate(printer):
    p = PRINTERS[printer]
    model = ET.fromstring(_zip(printer).read("3D/3dmodel.model"))
    items = list(model.iter(f"{CORE}item"))
    assert len(items) == 2
    for i, (item, m) in enumerate(zip(items, _halves().values())):
        t = [float(v) for v in item.get("transform").split()]
        assert t[:9] == [1, 0, 0, 0, 1, 0, 0, 0, 1] and t[11] == 0
        ox, oy = plate_offset(p, i, 2)
        x0, y0, z0, x1, y1, _ = m.bounding_box()
        assert z0 == pytest.approx(0, abs=1e-6)
        fx0, fy0, fx1, fy1 = x0 + t[9], y0 + t[10], x1 + t[9], y1 + t[10]
        bx0, by0, bx1, by1 = p.bed
        assert bx0 + ox <= fx0 and fx1 <= bx1 + ox, (printer, i)
        assert by0 + oy <= fy0 and fy1 <= by1 + oy, (printer, i)


def test_plate_offsets():
    p = PRINTERS[DEFAULT_PRINTER]
    w, d = p.size
    assert plate_offset(p, 0, 2) == (0, 0)
    assert plate_offset(p, 1, 2) == (pytest.approx(w * PLATE_GAP), 0)
    assert plate_offset(p, 2, 3) == (0, pytest.approx(-d * PLATE_GAP))


def test_a1_matches_bambu_layout():
    # Item positions Bambu Studio's own arrange produced for the A1 (verified reference file).
    model = ET.fromstring(_zip("a1").read("3D/3dmodel.model"))
    xy = [tuple(float(v) for v in i.get("transform").split()[9:11]) for i in model.iter(f"{CORE}item")]
    assert xy == [(128, 128), (pytest.approx(435.2), 128)]


def test_meshes_watertight_and_unique_uuids():
    z = _zip(DEFAULT_PRINTER)
    uuids = []
    for k in (1, 2):
        root = ET.fromstring(z.read(f"3D/Objects/object_{k}.model"))
        obj = root.find(f".//{CORE}object")
        uuids.append(obj.get(f"{PROD}UUID"))
        tris = np.array([[int(t.get(a)) for a in ("v1", "v2", "v3")]
                         for t in obj.iterfind(f".//{CORE}triangle")])
        assert _edges_closed(tris)
    model = ET.fromstring(z.read("3D/3dmodel.model"))
    uuids += [e.get(f"{PROD}UUID") for e in model.iter() if e.get(f"{PROD}UUID")]
    assert len(uuids) == len(set(uuids))


def test_unknown_printer():
    with pytest.raises(ValueError):
        to_bambu_project(_halves(), "nope")


@pytest.mark.skipif(not BAMBU_CLI.exists(), reason="Bambu Studio not installed")
def test_bambu_studio_loads_two_plates(tmp_path):
    f = tmp_path / "spool.3mf"
    f.write_bytes(_project(DEFAULT_PRINTER))
    r = subprocess.run([str(BAMBU_CLI), "--debug", "3", "--info", str(f)], cwd=tmp_path,
                       capture_output=True, text=True, timeout=120)
    log = r.stdout + r.stderr
    assert "is a 3mf, version" in log and "got plate count 2" in log, log[-3000:]
    assert log.count("manifold = yes") == 2


def _settings(printer: str) -> dict:
    return json.loads(_zip(printer).read("Metadata/project_settings.config"))


@pytest.mark.parametrize("printer", sorted(PRINTERS))
def test_extruder_nozzle_stats(printer):
    """Multi-nozzle exports carry the nozzle stats the CLI needs; single-nozzle exports and
    the unconfirmed nozzle-changer H2C keep the template's settings byte for byte."""
    from spoolmaker.bambu import DATA_DIR, NOZZLE_STATS_UNCONFIRMED

    raw = (DATA_DIR / "templates" / f"{printer}.json").read_bytes()
    exported = _zip(printer).read("Metadata/project_settings.config")
    n = len(json.loads(raw)["nozzle_diameter"])
    if n == 1 or printer in NOZZLE_STATS_UNCONFIRMED:
        assert exported == raw
    else:
        got = json.loads(exported)
        assert got["extruder_nozzle_stats"] == ["Standard#1"] * n
        assert {k: v for k, v in got.items() if k != "extruder_nozzle_stats"} == {
            k: v for k, v in json.loads(raw).items() if k != "extruder_nozzle_stats"}


@pytest.mark.skipif(not LIVE, reason="set SPOOLMAKER_BAMBU_LIVE=1 (needs Bambu Studio)")
def test_bambu_cli_slices_h2d_export():
    """The exported H2D project slices as is (no CLI-only patching), matching the fixture."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from calibrate_estimate import slice_case

    fixture = json.loads((Path(__file__).parent / "fixtures" / "bambu_grams.json").read_text())
    case = fixture["default@h2d"]
    a, b = slice_case(BAMBU_CLI, case["query"])
    assert a == pytest.approx(case["a_g"], rel=0.01) and b == pytest.approx(case["b_g"], rel=0.01)
