"""Printability checks: valid, single solid, flat on the bed, watertight STL."""

import math
from collections import Counter

import numpy as np
import pytest
from manifold3d import Error

from spoolmaker.config import SpoolConfig
from spoolmaker.export import to_stl
from spoolmaker.geometry.build import build_half
from spoolmaker.geometry.features import ENGRAVE_DEPTH

CONFIGS = {
    "default": SpoolConfig(),
    "classic": SpoolConfig(lightweight=False, label=True, gauge=True),  # the defaults before lightweight
    "everything": SpoolConfig(
        label=True, gauge=True,
        pattern="voronoi",
        pattern_density=1.0,
        lightweight=True,
        text="PETG 1.75",
        tag_pocket=True,
        clip_holes=8,
    ),
    "custom-coil": SpoolConfig(refill="custom", coil_inner_diameter=70.8, bore_diameter=58.0,
                               lightweight=False, label=True, gauge=True),
    "id70-lightweight-windows": SpoolConfig(refill="custom", coil_inner_diameter=70.0,
                                            lightweight=True, pattern="windows",
                                            pattern_density=1.0, label=True, gauge=True),
    "lightweight-windows": SpoolConfig(lightweight=True, pattern="windows", pattern_density=1.0,
                                       text="PLA", tag_pocket=True, label=True, gauge=True),
}


def _stl_triangles(data: bytes) -> np.ndarray:
    dt = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    return np.frombuffer(data[84:], dtype=dt)["v"]


@pytest.fixture(params=[(k, h) for k in CONFIGS for h in "ab"], ids=lambda p: f"{p[0]}-{p[1]}")
def half(request):
    key, h = request.param
    cfg = CONFIGS[key]
    return cfg, build_half(cfg, h)


@pytest.mark.parametrize("key", list(CONFIGS))
def test_configs_are_valid(key):
    from spoolmaker.config import validate

    assert not validate(CONFIGS[key])


def test_valid_single_solid(half):
    _, m = half
    assert m.status() == Error.NoError
    assert not m.is_empty()
    assert len(m.decompose()) == 1


def test_flat_on_bed(half):
    from manifold3d import CrossSection

    from spoolmaker.geometry.dims import dims

    cfg, m = half
    assert m.bounding_box()[2] == pytest.approx(0.0, abs=1e-6)
    footprint = m.slice(0.01)
    d = dims(cfg)
    # The flange, not a core end, is on the bed: at least its always-solid rim and hub
    # ring (bore to hub_ring_r) are there, whatever the pattern opens up.
    solid = math.pi * (d.R**2 - d.rim_r**2 + d.hub_ring_r**2 - d.r_bore**2)
    assert footprint.area() >= 0.9 * solid
    # ... out to its edge: the outer 1.5 mm of the rim is on the bed all the way round.
    edge = CrossSection.circle(d.R - 0.05, d.seg) - CrossSection.circle(d.R - 1.5, d.seg)
    assert (edge - footprint).area() < 1e-2


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


def _overhang_area(m, z_min: float) -> float:
    """Total area of faces steeper than ~46 deg past vertical facing down (normal_z <
    -0.72) whose lowest point is above z_min."""
    mesh = m.to_mesh()
    v = np.asarray(mesh.vert_properties)[:, :3]
    p = v[np.asarray(mesh.tri_verts)]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    norm = np.linalg.norm(n, axis=1)
    nz = n[:, 2] / np.maximum(norm, 1e-12)
    sel = (nz < -0.72) & (p[:, :, 2].min(axis=1) > z_min)
    return float(norm[sel].sum() / 2)


_PLAIN = dict(pattern="none", label=False, gauge=False, clip_holes=0, lightweight=False)


@pytest.mark.parametrize("h", "ab")
@pytest.mark.parametrize("cfg,z_min", [
    (SpoolConfig(), ENGRAVE_DEPTH + 0.1),
    (SpoolConfig(lightweight=False, label=True, gauge=True), ENGRAVE_DEPTH + 0.1),
    (SpoolConfig(lightweight=True, label=True, gauge=True), ENGRAVE_DEPTH + 0.1),
    (SpoolConfig(lightweight=True, label=True, gauge=True, pattern="windows", pattern_density=1.0),
     ENGRAVE_DEPTH + 0.1),
    (SpoolConfig(**_PLAIN), 0.2),
    (SpoolConfig(**{**_PLAIN, "lightweight": True}), 0.2),
], ids=["default", "classic", "lightweight", "lightweight-windows", "plain", "plain-lightweight"])
def test_support_free(cfg, z_min, h):
    """No downward faces steeper than 45 deg (beyond boolean slivers). Engraved text,
    label outline and gauge ticks on the bed face are short bridges ENGRAVE_DEPTH up,
    so the engraved configs start the scan above them."""
    assert _overhang_area(build_half(cfg, h), z_min) < 5.0


def test_classic_half_a_volume_target():
    # the full-weight design that was the default before lightweight mode became the default
    assert build_half(SpoolConfig(lightweight=False, label=True, gauge=True), "a").volume() <= 100_000


@pytest.mark.parametrize("h", "ab")
def test_default_volume_target(h):
    # the default (lightweight, no label) spool
    assert build_half(SpoolConfig(), h).volume() <= 70_000


@pytest.mark.parametrize("h", "ab")
def test_lightweight_windows_volume_target(h):
    cfg = SpoolConfig(lightweight=True, pattern="windows", pattern_density=1.0)
    assert build_half(cfg, h).volume() <= 70_000
