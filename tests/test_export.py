import io
import struct
import zipfile
import xml.etree.ElementTree as ET

import numpy as np
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
    tv = np.frombuffer(data[84:], dtype=_STL_REC)["v"].astype(np.float64)
    cross = np.cross(tv[:, 1] - tv[:, 0], tv[:, 2] - tv[:, 0])
    assert np.all(np.any(cross != 0, axis=1))
    same = (tv[:, 0] == tv[:, 1]).all(1) | (tv[:, 1] == tv[:, 2]).all(1) | (tv[:, 2] == tv[:, 0]).all(1)
    assert not same.any()
