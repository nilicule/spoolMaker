"""Printability checks: valid, single solid, flat on the bed, watertight STL."""

import math
from collections import Counter

import numpy as np
import pytest
from manifold3d import Error

from spoolmaker.config import SpoolConfig
from spoolmaker.export import to_stl
from spoolmaker.geometry.build import build_half

CONFIGS = {
    "default": SpoolConfig(),
    "everything": SpoolConfig(
        pattern="voronoi",
        pattern_density=1.0,
        lightweight=True,
        text="PETG 1.75",
        tag_pocket=True,
        clip_holes=8,
    ),
    "custom-coil": SpoolConfig(refill="custom", coil_inner_diameter=70.0, bore_diameter=58.0),
}


def _stl_triangles(data: bytes) -> np.ndarray:
    dt = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    return np.frombuffer(data[84:], dtype=dt)["v"]


@pytest.fixture(params=[(k, h) for k in CONFIGS for h in "ab"], ids=lambda p: f"{p[0]}-{p[1]}")
def half(request):
    key, h = request.param
    cfg = CONFIGS[key]
    return cfg, build_half(cfg, h)


def test_valid_single_solid(half):
    _, m = half
    assert m.status() == Error.NoError
    assert not m.is_empty()
    assert len(m.decompose()) == 1


def test_flat_on_bed(half):
    cfg, m = half
    assert m.bounding_box()[2] == pytest.approx(0.0, abs=1e-6)
    area = m.slice(0.01).area()
    disc = math.pi * (cfg.outer_diameter / 2) ** 2
    assert area > 0.5 * disc


def test_stl_watertight(half):
    _, m = half
    tv = _stl_triangles(to_stl(m))
    flat = tv.reshape(-1, 3)
    _, idx = np.unique(flat, axis=0, return_inverse=True)
    tris = idx.reshape(-1, 3)
    edges = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    counts = Counter(map(tuple, np.sort(edges, axis=1)))
    assert set(counts.values()) == {2}
    # Consistent orientation: each directed edge appears exactly once.
    directed = Counter(map(tuple, edges))
    assert max(directed.values()) == 1
