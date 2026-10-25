"""Slicer-like filament estimate: what a half weighs printed with a Bambu Studio profile.

The half is cut into layers at the profile's layer heights, the way a slicer does, and each
layer's cross-section is split into:

- walls: the band the wall loops cover, inset from the outline;
- solid infill: top and bottom shells (area exposed within top_shell_layers above or
  bottom_shell_layers below), vertical shells (the wall band of nearby layers with another
  outline, so a step keeps its shell thickness) and sparse pockets smaller than
  minimum_sparse_infill_area;
- internal bridges: solid infill laid straight over sparse infill, printed as round
  strands of nozzle diameter that carry more plastic than a flat solid line;
- sparse infill: the rest, at sparse_infill_density, plus the anchors that run along its
  outline joining the infill lines.

Walls and solid infill fill their area completely (extrusion spacing is chosen so the beads
tile it). Grams are the volume times the filament's flow ratio and density. Every factor
comes from the profile; there is no fitted fudge factor. tests/test_estimate.py checks the
result against what Bambu Studio's own slicer reports (tests/fixtures/bambu_grams.json).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace
from functools import cache

import numpy as np
from manifold3d import CrossSection, JoinType, Manifold, OpType

from .bambu import PRINTERS, project_settings

EPS_AREA = 1e-3  # mm^2: smaller differences between layers are slicing noise
SIMPLIFY = 0.02  # mm: outline tolerance, well under a line width
BRIDGE_EXTRA_SPACING = 0.05  # mm between bridge strands (PrusaSlicer/Bambu Studio constant)


@dataclass(frozen=True)
class SliceProfile:
    layer_height: float
    initial_layer_height: float
    nozzle_diameter: float
    wall_loops: int
    outer_wall_width: float
    inner_wall_width: float
    sparse_width: float
    top_shell_layers: int
    bottom_shell_layers: int
    sparse_density: float  # 0..1
    sparse_anchor: float  # mm of anchor per infill line end
    min_sparse_area: float  # mm^2: smaller sparse islands are printed solid
    filament_density: float  # g/cm^3
    flow_ratio: float
    sparse_pattern: str = "grid"  # anchor_cover models grid; all bundled templates use it
    process: str = ""
    filament: str = ""
    printer: str = ""

    def spacing(self, width: float) -> float:
        """Centre distance of adjacent extrusions of this width (rounded-rectangle bead)."""
        return width - self.layer_height * (1 - math.pi / 4)

    @property
    def wall_thickness(self) -> float:
        """Width of the perimeter band, from the outline to where the infill starts."""
        return (self.spacing(self.outer_wall_width)
                + (self.wall_loops - 1) * self.spacing(self.inner_wall_width))

    @property
    def bridge_factor(self) -> float:
        """Plastic in an internal bridge layer relative to a flat solid layer: round strands
        of nozzle diameter, BRIDGE_EXTRA_SPACING apart."""
        d = self.nozzle_diameter
        return math.pi * d * d / 4 / (self.layer_height * (d + BRIDGE_EXTRA_SPACING))

    @property
    def anchor_cover(self) -> float:
        """Share of a sparse region's outline its infill anchors run along.

        Assumes grid infill (sparse_pattern; every bundled template uses grid, which a test
        checks): other patterns end their lines along the outline at other rates.
        Grid infill splits its density over two line directions, each spaced
        2 w / density; at random orientation a line family of spacing p meets an outline
        2 / (pi p) times per mm, so ends land 2 density / (pi w) apart per mm."""
        ends_per_mm = 2 * self.sparse_density / (math.pi * self.sparse_width)
        return min(1.0, self.sparse_anchor * ends_per_mm)

    def geometry_key(self) -> SliceProfile:
        """This profile without its names: printers whose profiles only differ in name
        slice a part the same way."""
        return replace(self, process="", filament="", printer="")

    def note(self) -> str:
        return (f"\u2248 {self.printer} \u00b7 "
                f"{self.process.split(' @')[0].replace('mm', ' mm')} \u00b7 "
                f"{self.wall_loops} walls \u00b7 {self.sparse_density * 100:g}% infill")


def _first(v):
    return v[0] if isinstance(v, list) and v else v


def _num(v) -> float:
    v = str(_first(v)).strip()
    return float(v[:-1]) / 100 if v.endswith("%") else float(v)


def _layers(s: dict, key: str, h: float) -> int:
    return max(int(_num(s[f"{key}_layers"])), math.ceil(_num(s[f"{key}_thickness"]) / h - 1e-9))


def profile_from_settings(s: dict, printer: str = "") -> SliceProfile:
    """SliceProfile from Bambu Studio project settings (a project_settings.config dict)."""
    h = _num(s["layer_height"])
    sparse_w = _num(s["sparse_infill_line_width"])
    anchor = str(_first(s.get("sparse_infill_anchor", "0"))).strip()
    anchor_mm = _num(anchor) * sparse_w if anchor.endswith("%") else _num(anchor)
    anchor_mm = min(anchor_mm, _num(s.get("sparse_infill_anchor_max", anchor_mm)))
    return SliceProfile(
        layer_height=h,
        initial_layer_height=_num(s["initial_layer_print_height"]),
        nozzle_diameter=_num(s["nozzle_diameter"]),
        wall_loops=int(_num(s["wall_loops"])),
        outer_wall_width=_num(s["outer_wall_line_width"]),
        inner_wall_width=_num(s["inner_wall_line_width"]),
        sparse_width=sparse_w,
        top_shell_layers=_layers(s, "top_shell", h),
        bottom_shell_layers=_layers(s, "bottom_shell", h),
        sparse_density=_num(s["sparse_infill_density"]),
        sparse_anchor=anchor_mm,
        min_sparse_area=_num(s.get("minimum_sparse_infill_area", 0)),
        filament_density=_num(s["filament_density"]),
        flow_ratio=_num(s["filament_flow_ratio"]),
        sparse_pattern=str(_first(s.get("sparse_infill_pattern", "grid"))),
        process=str(s.get("print_settings_id", "")),
        filament=str(_first(s.get("filament_settings_id", ""))),
        printer=printer,
    )


@cache
def bambu_profile(printer: str) -> SliceProfile:
    """The SliceProfile of a Bambu printer's project template (0.20 mm Standard, PLA Basic)."""
    return profile_from_settings(json.loads(project_settings(printer)), PRINTERS[printer].name)


def _area(c: CrossSection) -> float:
    return c.area() if not c.is_empty() else 0.0


def layer_heights(top: float, profile: SliceProfile) -> list[tuple[float, float]]:
    """(slice z, thickness) of each layer: the first at the initial height, then uniform."""
    out = []
    z0, h = 0.0, profile.initial_layer_height
    while z0 + 1e-9 < top:
        h = min(h, top - z0)
        if h < profile.layer_height * 0.3 and out:
            break  # Bambu drops a sliver of a last layer
        out.append((z0 + h / 2, h))
        z0 += h
        h = profile.layer_height
    return out


def _perimeter(c: CrossSection) -> float:
    total = 0.0
    for poly in c.to_polygons():
        pts = np.asarray(poly)
        if len(pts) > 1:
            total += float(np.linalg.norm(pts - np.roll(pts, 1, axis=0), axis=1).sum())
    return total


def _same_outline(a: list, b: list) -> bool:
    """Two layers' polygons are the same (a prism between them)."""
    return len(a) == len(b) and all(
        p.shape == q.shape and np.allclose(p, q, rtol=0, atol=1e-6) for p, q in zip(a, b))


def volume_breakdown(m: Manifold, profile: SliceProfile) -> dict[str, float]:
    """mm^3 of each kind of extrusion, before the sparse-infill and bridge factors.

    "sparse" is the area x height the sparse infill fills (not yet thinned by its density)
    and "anchor" the length x height of the sparse regions' outlines its anchors run along.
    """
    zmin, zmax = m.bounding_box()[2], m.bounding_box()[5]
    m = m.translate((0, 0, -zmin))
    layers = layer_heights(zmax - zmin, profile)
    n = len(layers)
    up, down = profile.top_shell_layers, profile.bottom_shell_layers

    # Runs of consecutive layers with one outline (a prism); skin only appears where runs
    # meet. Each run's outline is simplified to slicer-like resolution.
    slices = [m.slice(z) for z, _ in layers]
    polys = [s.to_polygons() for s in slices]
    runs: list[list[int]] = []  # [first, last] layer of each run
    outlines: list[CrossSection] = []
    for i in range(n):
        if i and _same_outline(polys[i - 1], polys[i]):
            runs[-1][1] = i
            continue
        outline = slices[i].simplify(SIMPLIFY)
        if outlines and _area(outline - outlines[-1]) < EPS_AREA \
                and _area(outlines[-1] - outline) < EPS_AREA:
            runs[-1][1] = i  # differs from the run below by less than slicing noise
            continue
        runs.append([i, i])
        outlines.append(outline)
    k = len(runs)
    run_of = [r for r, (f, l) in enumerate(runs) for _ in range(f, l + 1)]
    # tops[r]: run r's area exposed from above; bottoms[r]: exposed from below.
    tops = [outlines[r] - outlines[r + 1] if r + 1 < k else outlines[r] for r in range(k)]
    bottoms = [outlines[r] - outlines[r - 1] if r else outlines[r] for r in range(k)]
    interiors = [c.offset(-profile.wall_thickness, JoinType.Miter) for c in outlines]
    bands = [c - inner for c, inner in zip(outlines, interiors)]  # the wall loops' footprint
    pieces = {"top": tops, "bottom": bottoms, "band": bands}
    clipped: dict[tuple, CrossSection] = {}

    def clip(kind: str, q: int, r: int) -> CrossSection:
        """Skin piece `kind` of run q, within run r's interior."""
        if (kind, q, r) not in clipped:
            clipped[kind, q, r] = pieces[kind][q] ^ interiors[r]
        return clipped[kind, q, r]

    out = {"wall": 0.0, "solid": 0.0, "bridge": 0.0, "sparse": 0.0, "anchor": 0.0}
    splits: dict[tuple, tuple] = {}  # skin key -> (solid, sparse, solid area, sparse area, perim)
    bridges: dict[tuple, float] = {}
    below_key = None
    for i, (_, h) in enumerate(layers):
        r = run_of[i]
        near = range(run_of[max(0, i - down)], run_of[min(n - 1, i + up)] + 1)
        # Top shells: the area exposed above within top_shell_layers of this one; bottom
        # shells likewise below. Vertical shells: the wall footprint of nearby runs stays
        # solid here, so a step in the outline keeps its shell thickness.
        key = (r,
               tuple(q for q in near if i <= runs[q][1] < i + up),
               tuple(q for q in near if i - down < runs[q][0] <= i),
               tuple(q for q in near if q != r))
        if key not in splits:
            interior = interiors[r]
            skin = [clip("top", q, r) for q in key[1]] + [clip("bottom", q, r) for q in key[2]]
            skin += [clip("band", q, r) for q in key[3]]
            skin = [c for c in skin if not c.is_empty()]
            if skin:
                solid = CrossSection.batch_boolean(skin, OpType.Add)
                sparse = interior - solid
            else:
                solid, sparse = CrossSection(), interior
            keep = []
            for part in sparse.decompose():
                if part.area() < profile.min_sparse_area:
                    solid += part  # too small to bother with sparse infill
                else:
                    keep.append(part)
            sparse = CrossSection.compose(keep) if keep else CrossSection()
            splits[key] = (solid, sparse, _area(solid), _area(sparse), _perimeter(sparse))
        solid, _, solid_a, sparse_a, perim = splits[key]
        # Solid skin straight over sparse infill is laid as an internal bridge.
        bridge_a = 0.0
        if below_key is not None and solid_a > 0 and splits[below_key][3] > 0:
            if (key, below_key) not in bridges:
                bridges[key, below_key] = _area(solid ^ splits[below_key][1])
            bridge_a = bridges[key, below_key]
        below_key = key
        out["wall"] += (_area(outlines[r]) - _area(interiors[r])) * h
        out["solid"] += (solid_a - bridge_a) * h
        out["bridge"] += bridge_a * h
        out["sparse"] += sparse_a * h
        out["anchor"] += perim * h
    return out


def extruded_mm3(v: dict[str, float], profile: SliceProfile) -> float:
    """Plastic volume of a volume_breakdown under the profile's fill factors."""
    return (v["wall"] + v["solid"] + v["bridge"] * profile.bridge_factor
            + v["sparse"] * profile.sparse_density
            + v["anchor"] * profile.anchor_cover * profile.sparse_width)


def estimate_grams(m: Manifold, profile: SliceProfile, density: float | None = None) -> float:
    """Filament grams to print m; density (g/cm^3) defaults to the profile's filament."""
    rho = profile.filament_density if density is None else density
    return extruded_mm3(volume_breakdown(m, profile), profile) / 1000 * rho * profile.flow_ratio
