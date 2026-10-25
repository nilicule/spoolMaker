"""2D flange cutout patterns (pure 2D, returned as manifold3d CrossSections)."""
from __future__ import annotations

import math

import numpy as np
from manifold3d import CrossSection, FillRule, JoinType, OpType

MIN_AREA = 4.0  # mm^2, smaller fragments are unprintable slivers
_ARC_SEGS = 24
GRID_MIN_CELL = 13.0
_RING_SEGS = 128


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _union(polys: list) -> CrossSection:
    if not polys:
        return CrossSection()
    return CrossSection([np.asarray(p, dtype=float) for p in polys], FillRule.Positive)


def _shrunk_regular(centers: np.ndarray, verts: np.ndarray, inradius: float, wall: float):
    """Polygons (centers + unit-shape verts scaled to shrink walls by wall/2)."""
    k = (inradius - wall / 2) / inradius
    if k <= 0:
        return []
    return [c + verts * k for c in centers]


def _honeycomb(cell, wall, r_in, r_out, seed):
    R = cell / 2
    ang = np.radians(np.arange(6) * 60)
    verts = R * np.stack([np.cos(ang), np.sin(ang)], axis=1)
    dx, dy = 1.5 * R, math.sqrt(3) * R
    reach = r_out + R
    nx, ny = int(reach / dx) + 2, int(reach / dy) + 2
    cs = []
    for i in range(-nx, nx + 1):
        for j in range(-ny, ny + 1):
            x = i * dx
            y = j * dy + (dy / 2 if i % 2 else 0.0)
            if r_in - R <= math.hypot(x, y) <= reach:
                cs.append((x, y))
    return _shrunk_regular(np.array(cs).reshape(-1, 2), verts, math.sqrt(3) / 2 * R, wall)


def _isogrid(cell, wall, r_in, r_out, seed):
    s = cell
    h = s * math.sqrt(3) / 2
    ri = s / (2 * math.sqrt(3))
    rc = s / math.sqrt(3)
    up = rc * np.array([[0, 1], [-math.sqrt(3) / 2, -0.5], [math.sqrt(3) / 2, -0.5]])
    down = -up
    k = (ri - wall / 2) / ri
    if k <= 0:
        return []
    reach = r_out + s
    polys = []
    nj = int(reach / h) + 2
    ni = int(reach / s) + 3
    for j in range(-nj, nj + 1):
        for i in range(-ni, ni + 1):
            x = i * s + (s / 2 if j % 2 else 0.0)
            y = j * h
            # upward triangle centroid at y + ri, downward at y + 2*ri ... use
            # row base y: up centroid y+ri, down centroid y+h-ri, x shifted s/2
            for shape, cx, cy in ((up, x, y + ri), (down, x + s / 2, y + h - ri)):
                if r_in - s <= math.hypot(cx, cy) <= reach:
                    polys.append(np.array([cx, cy]) + shape * k)
    return polys


def _holes(cell, wall, r_in, r_out, seed):
    d = cell - wall
    rad = d / 2
    t = np.linspace(0, 2 * np.pi, _ARC_SEGS, endpoint=False)
    unit = rad * np.stack([np.cos(t), np.sin(t)], axis=1)
    r0, r1 = r_in + wall + rad, r_out - wall - rad
    if r1 < r0:
        return []
    n_rings = int((r1 - r0) / cell) + 1
    radii = [(r0 + r1) / 2] if n_rings == 1 else list(np.linspace(r0, r1, n_rings))
    polys = []
    for ri, r in enumerate(radii):
        n = max(int(2 * math.pi * r / cell), 3)
        off = (ri % 2) * math.pi / n
        for a in off + np.arange(n) * 2 * math.pi / n:
            polys.append(np.array([r * math.cos(a), r * math.sin(a)]) + unit)
    return polys


def _spokes(cell, wall, r_in, r_out, seed, density):
    n = round(_lerp(6, 18, density))
    ri, ro = r_in + wall, r_out - wall
    arc_mid = 2 * math.pi * (ri + ro) / 2 / n
    w = min(_lerp(0.4, 0.7, density) * arc_mid, 2 * math.pi * ri / n - wall)
    if w < 2.0 or ro - ri < w:
        return CrossSection()
    a, b = ri + w / 2, ro - w / 2
    base = CrossSection.square((b - a, 1e-3), center=True).translate(((a + b) / 2, 0))
    slot = base.offset(w / 2 - 5e-4, JoinType.Round, 2.0, _ARC_SEGS)
    slots = [slot.rotate(360.0 * i / n) for i in range(n)]
    return CrossSection.batch_boolean(slots, OpType.Add)


def _voronoi(cell, wall, r_in, r_out, seed):
    from scipy.spatial import Voronoi

    rng = np.random.default_rng(seed)
    lo, hi = r_in - cell, r_out + cell
    dy = cell * math.sqrt(3) / 2
    n = int(hi / dy) + 2
    pts = []
    for j in range(-n, n + 1):
        for i in range(-n, n + 1):
            pts.append((i * cell + (cell / 2 if j % 2 else 0.0), j * dy))
    pts = np.array(pts)
    pts += rng.uniform(-0.3 * cell, 0.3 * cell, pts.shape)
    rr = np.hypot(pts[:, 0], pts[:, 1])
    real = pts[(rr >= lo) & (rr <= hi)]
    # Mirror/dummy points far outside and inside so every real cell is finite.
    far = []
    for R, step in ((hi + cell, cell), (max(lo - cell, 0.0), cell)):
        if R <= 0:
            continue
        m = max(int(2 * math.pi * R / step), 6)
        a = np.arange(m) * 2 * math.pi / m
        far.append(np.stack([R * np.cos(a), R * np.sin(a)], axis=1))
    allp = np.vstack([real] + far)
    vor = Voronoi(allp)
    polys = []
    for i in range(len(real)):
        reg = vor.regions[vor.point_region[i]]
        if not reg or -1 in reg:
            continue
        polys.append(vor.vertices[reg])
    out = []
    for p in polys:
        cs = CrossSection([p], FillRule.Positive).offset(
            -wall / 2, JoinType.Round, 2.0, _ARC_SEGS
        )
        if not cs.is_empty():
            out.append(cs)
    return CrossSection.batch_boolean(out, OpType.Add) if out else CrossSection()


_POLY_KINDS = {
    "honeycomb": _honeycomb,
    "isogrid": _isogrid,
    "holes": _holes,
}


def pattern_cutouts(
    kind: str,
    density: float,
    r_in: float,
    r_out: float,
    seed: int,
    keepouts: CrossSection,
) -> CrossSection:
    """Union of hole shapes inside the annulus r_in..r_out.

    Holes keep at least one wall width of material from both annulus
    boundaries and from the keep-outs.
    """
    if kind == "none":
        return CrossSection()
    density = min(max(density, 0.0), 1.0)
    cell = _lerp(22, 9, density)
    if kind in ("honeycomb", "isogrid"):
        # With the spec'd 22->9 range the web/pitch ratio grows faster than the
        # wall thins, so open area would *drop* with density. Keep the tiling
        # coarser at the dense end so open area rises monotonically.
        cell = _lerp(22, GRID_MIN_CELL, density)
    wall = _lerp(3.0, 1.6, density)

    if kind in _POLY_KINDS:
        shapes = _union(_POLY_KINDS[kind](cell, wall, r_in, r_out, seed))
    elif kind == "spokes":
        shapes = _spokes(cell, wall, r_in, r_out, seed, density)
    elif kind == "voronoi":
        shapes = _voronoi(cell, wall, r_in, r_out, seed)
    else:
        raise ValueError(f"unknown pattern kind: {kind!r}")
    if shapes.is_empty():
        return CrossSection()

    region = CrossSection.circle(r_out - wall, _RING_SEGS) - CrossSection.circle(
        r_in + wall, _RING_SEGS
    )
    if not keepouts.is_empty():
        region = region - keepouts.offset(wall, JoinType.Round, 2.0, _ARC_SEGS)
    cs = shapes ^ region
    parts = [p for p in cs.decompose() if p.area() >= MIN_AREA]
    return CrossSection.batch_boolean(parts, OpType.Add) if parts else CrossSection()
