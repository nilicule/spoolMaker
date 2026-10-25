import io
import random
import struct
import zipfile
import xml.etree.ElementTree as ET

import numpy as np
import pytest
from manifold3d import Manifold

from spoolmaker.export import mesh_arrays, to_3mf, to_stl

_STL_REC = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])


def test_stl_size():
    data = to_stl(Manifold.cube((10, 10, 10)))
    assert len(data) == 84 + 50 * 12
    assert struct.unpack("<I", data[80:84])[0] == 12


def test_stl_normals_unit():
    data = to_stl(Manifold.cube((10, 10, 10)))
    rec = np.frombuffer(data[84:], dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]))
    assert np.allclose(np.linalg.norm(rec["n"], axis=1), 1.0)


def test_mesh_arrays():
    v, t = mesh_arrays(Manifold.cube((1, 1, 1)))
    assert v.dtype == np.float32 and v.shape[1] == 3
    assert t.dtype == np.uint32 and t.shape == (12, 3)


def test_3mf_has_two_objects():
    z = zipfile.ZipFile(io.BytesIO(to_3mf({"a": Manifold.cube((1, 1, 1)), "b": Manifold.cube((1, 1, 1))})))
    model = z.read("3D/3dmodel.model").decode()
    assert model.count("<object ") == 2 and 'unit="millimeter"' in model


def test_3mf_structure():
    z = zipfile.ZipFile(io.BytesIO(to_3mf({"a": Manifold.cube((1, 1, 1)), "b": Manifold.cube((1, 1, 1))})))
    assert "application/vnd.ms-package.3dmanufacturing-3dmodel+xml" in z.read("[Content_Types].xml").decode()
    rels = z.read("_rels/.rels").decode()
    assert "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel" in rels
    ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
    root = ET.fromstring(z.read("3D/3dmodel.model"))
    assert [o.get("name") for o in root.findall(".//m:object", ns)] == ["a", "b"]
    xs = [i.get("transform").split()[-3] for i in root.findall(".//m:item", ns)]
    assert xs == ["0", "210"]


def test_mesh_arrays_matches_stl():
    from spoolmaker.config import SpoolConfig
    from spoolmaker.geometry.build import build_half

    m = build_half(SpoolConfig(), "a")
    _, t = mesh_arrays(m)
    assert (len(to_stl(m)) - 84) // 50 == len(t)


def test_stl_has_no_degenerate_triangles():
    from spoolmaker.config import SpoolConfig
    from spoolmaker.geometry.build import build_half

    data = to_stl(build_half(SpoolConfig(), "a"))
    tv = np.frombuffer(data[84:], dtype=_STL_REC)["v"]
    same = (tv[:, 0] == tv[:, 1]).all(1) | (tv[:, 1] == tv[:, 2]).all(1) | (tv[:, 2] == tv[:, 0]).all(1)
    assert not same.any()


def _edges_closed(tris: np.ndarray) -> bool:
    """Every undirected edge is shared by exactly two triangles."""
    e = np.sort(np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), axis=1)
    _, counts = np.unique(e, axis=0, return_counts=True)
    return bool(len(tris)) and bool((counts == 2).all())


def _stl_tris(data: bytes) -> np.ndarray:
    tv = np.frombuffer(data[84:], dtype=_STL_REC)["v"].reshape(-1, 3)
    _, idx = np.unique(tv, axis=0, return_inverse=True)  # weld by exact float32 position
    return idx.reshape(-1, 3)


def _3mf_tris(data: bytes) -> dict[str, np.ndarray]:
    ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
    root = ET.fromstring(zipfile.ZipFile(io.BytesIO(data)).read("3D/3dmodel.model"))
    out = {}
    for obj in root.findall(".//m:object", ns):
        verts = np.array([[float(v.get(k)) for k in "xyz"] for v in obj.iterfind(".//m:vertex", ns)],
                         dtype=np.float32)
        tris = np.array([[int(t.get(k)) for k in ("v1", "v2", "v3")]
                         for t in obj.iterfind(".//m:triangle", ns)])
        # Printed coordinates must stay distinct, or a slicer's weld would change the mesh.
        assert len(np.unique(verts, axis=0)) == len(verts)
        out[obj.get("name")] = tris
    return out


def _random_queries(n: int, seed: int) -> list[dict[str, str]]:
    from spoolmaker.config import CHOICES, RANGES, from_query, validate

    rng = random.Random(seed)
    texts = ["", "8B\u00ae", "PETG 240\u00b0C", "WWWWWWWWWWWWWWWWWWWWWWWW", "iiiiiiiiiiiiiiiiiiiiiiii"]
    out = []
    while len(out) < n:
        q = {}
        for name, (lo, hi) in RANGES.items():
            if rng.random() < 0.6:
                q[name] = str(rng.uniform(lo, hi) if rng.random() < 0.7 else rng.choice([lo, hi]))
        for name, ch in CHOICES.items():
            if rng.random() < 0.6:
                q[name] = str(rng.choice(ch))
        for b in ("lightweight", "label", "gauge", "tag_pocket"):
            q[b] = rng.choice(["0", "1"])
        q["text"] = rng.choice(texts)
        if not validate(from_query(q)):
            out.append(q)
    return out


_KNOWN_CRACKS = [  # configs whose exports cracked when colinear slivers were dropped
    {"outer_diameter": "201.0", "bore_diameter": "53.95287824891415",
     "coil_clearance": "0.9419902288624415", "pattern_density": "0.0", "label_width": "20.0",
     "clip_holes": "0", "lock_clearance": "0.48373990456627924", "pattern": "isogrid",
     "lightweight": "1", "label": "1", "gauge": "0", "tag_pocket": "1",
     "text": "iiiiiiiiiiiiiiiiiiiiiiii"},
    {"outer_diameter": "198.44030115830375", "bore_diameter": "54.399988522879084",
     "coil_clearance": "1.5237997289608196", "pattern_density": "0.6990564091203973",
     "pattern_seed": "0", "pattern": "holes", "lightweight": "1", "label": "0", "gauge": "1",
     "text": "PETG 240\u00b0C"},
]


@pytest.mark.parametrize("query", _KNOWN_CRACKS + _random_queries(12, seed=3))
def test_exports_are_watertight(query):
    from spoolmaker.config import from_query, validate
    from spoolmaker.geometry.build import build_half

    cfg = from_query(query)
    assert not validate(cfg)
    halves = {h: build_half(cfg, h) for h in ("a", "b")}
    for h, m in halves.items():
        assert _edges_closed(_stl_tris(to_stl(m))), f"STL half {h} not watertight"
    for name, tris in _3mf_tris(to_3mf(halves)).items():
        assert _edges_closed(tris), f"3MF object {name} not watertight"
