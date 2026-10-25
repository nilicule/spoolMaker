import math
import time

import pytest
from manifold3d import CrossSection, Error, JoinType, Manifold, OpType

from spoolmaker.config import RIM_WIDTH, RIM_WIDTH_LIGHT, SpoolConfig, validate
from spoolmaker.geometry.build import assembled, build_half
from spoolmaker.geometry.dims import dims
from spoolmaker.geometry.features import (
    CLIP_COLLAR,
    CLIP_EDGE_WALL,
    CLIP_HOLE_D,
    CLIP_PAIR_PITCH,
    ENGRAVE_DEPTH,
    TAG_DEPTH,
    clip_hole_centres,
    layout,
)

PLAIN = dict(pattern="none", label=False, gauge=False, clip_holes=0, lightweight=False)


# --- brief tests -----------------------------------------------------------

@pytest.mark.parametrize("lightweight", [False, True])
def test_rim_ring_intact(lightweight):
    cfg = SpoolConfig(pattern="voronoi", pattern_density=1.0, clip_holes=8, lightweight=lightweight,
                      label=True, gauge=True)
    m = build_half(cfg, "a")
    d = dims(cfg)
    assert d.rim_width == (RIM_WIDTH_LIGHT if lightweight else RIM_WIDTH)
    ring = Manifold.cylinder(d.t, d.R, circular_segments=d.seg) - Manifold.cylinder(
        d.t, d.R - 2.4, circular_segments=d.seg)
    assert (ring - m).volume() < 1e-2           # outer 2.4 mm of rim fully solid
    # The whole active rim is full thickness apart from the clip holes (8 pairs).
    rim = Manifold.cylinder(d.t, d.R, circular_segments=d.seg) - Manifold.cylinder(
        d.t, d.rim_r + 0.1, circular_segments=d.seg)
    holes = 16 * math.pi * (CLIP_HOLE_D / 2) ** 2 * d.t
    assert (rim - m).volume() < holes * 1.05 + 1e-2


def test_lightweight_narrows_rim_and_hub_ring():
    from spoolmaker.geometry.dims import HUB_RING, HUB_RING_LIGHT
    from spoolmaker.geometry.features import web_thickness

    heavy, light = dims(SpoolConfig(lightweight=False)), dims(SpoolConfig(lightweight=True))
    assert heavy.R - heavy.rim_r == RIM_WIDTH and light.R - light.rim_r == RIM_WIDTH_LIGHT
    assert heavy.hub_ring_r - heavy.r_core_out == HUB_RING
    assert light.hub_ring_r - light.r_core_out == HUB_RING_LIGHT
    assert web_thickness(dims(SpoolConfig(flange_thickness=5.0, lightweight=True))) == 2.5
    assert web_thickness(dims(SpoolConfig(flange_thickness=2.0, lightweight=True))) == 1.6


def test_width_unchanged_by_features():
    plain = build_half(SpoolConfig(**PLAIN), "a").bounding_box()
    full = build_half(SpoolConfig(text="PETG 240", tag_pocket=True, label=True, gauge=True, lightweight=False), "a").bounding_box()
    assert full[5] - full[2] == pytest.approx(plain[5] - plain[2], abs=1e-6)


def test_lightweight_is_lighter():
    heavy = build_half(SpoolConfig(lightweight=False, label=True, gauge=True), "a").volume()
    assert build_half(SpoolConfig(lightweight=True, label=True, gauge=True), "a").volume() < heavy * 0.9


def test_pattern_lighter_than_none():
    for lw in (False, True):
        assert (build_half(SpoolConfig(pattern="honeycomb", lightweight=lw), "b").volume()
                < build_half(SpoolConfig(pattern="none", lightweight=lw), "b").volume())


def test_keepouts_stay_solid():
    cfg = SpoolConfig(pattern="holes", pattern_density=1.0, label=True, gauge=True, lightweight=False)
    lay = layout(cfg, dims(cfg))
    m = build_half(cfg, "a")
    label_prism = lay.label.offset(-1.0, JoinType.Miter).extrude(dims(cfg).t).translate((0, 0, 0))
    assert (label_prism - m).volume() < 1.0     # only the outline groove missing


def test_all_features_max_density_valid():
    cfg = SpoolConfig(pattern="honeycomb", pattern_density=1.0, lightweight=True, label=True, gauge=True, text="WWWWWWWWWWWWWWWWWWWWWWWW",
                      tag_pocket=True, tag_diameter=30, clip_holes=8, gauge_material="ABS")
    for h in "ab":
        m = build_half(cfg, h)
        assert m.status() == Error.NoError and m.volume() > 0


def test_lock_still_works_with_lightweight():
    a, b = assembled(SpoolConfig(lightweight=True, label=True, gauge=True))
    assert (a ^ b).volume() < 1e-3


# --- additional tests ------------------------------------------------------

def _slice_removed(cfg_a, cfg_b, z):
    """2D region present in half A of cfg_a but missing from cfg_b, sliced at z."""
    return (build_half(cfg_a, "a") - build_half(cfg_b, "a")).slice(z)


def _centre_x(cs: CrossSection) -> float:
    x0, _, x1, _ = cs.bounds()
    return (x0 + x1) / 2


def test_text_engraving_reads_correctly_from_outside():
    """The flange's outer face is z=0 (bed face; outward-facing in the assembled spool).

    A viewer looks at it from -Z toward +Z with +Y up. For a camera looking along +Z with
    up +Y, its right-hand direction is forward x up = Z x Y = -X. So a correctly reading
    "L" (vertical stroke on the viewer's left, foot extending to the viewer's right) must
    have its stroke on the model's +X side and its foot extending toward -X. Therefore
    the top half of the engraved "L" (stroke only) sits at larger X than the glyph's
    overall centre.
    """
    removed = _slice_removed(SpoolConfig(**PLAIN), SpoolConfig(**PLAIN, text="L"), ENGRAVE_DEPTH / 2)
    assert removed.area() > 1.0
    x0, y0, x1, y1 = removed.bounds()
    top = removed ^ CrossSection.square((x1 - x0 + 2, (y1 - y0) / 2)).translate((x0 - 1, (y0 + y1) / 2))
    bottom = removed ^ CrossSection.square((x1 - x0 + 2, (y1 - y0) / 2)).translate((x0 - 1, y0))
    assert _centre_x(top) > _centre_x(removed) + 0.5        # stroke on model +X
    assert bottom.bounds()[0] == pytest.approx(x0, abs=0.2)  # foot reaches model -X
    # Text sits at 270 deg (model -Y) and is not upside down: the foot is at the bottom,
    # i.e. toward the rim (more negative Y), with the label (90 deg) at the top.
    assert (y0 + y1) / 2 < 0


def test_engraving_depth_and_location():
    cfg = SpoolConfig(**PLAIN, text="HELLO")
    lay = layout(cfg, dims(cfg))
    diff = build_half(SpoolConfig(**PLAIN), "a") - build_half(cfg, "a")
    # drop zero-volume boolean slivers from differencing two near-identical meshes
    removed = Manifold.compose([p for p in diff.decompose() if p.volume() > 1e-6])
    lo, hi = removed.bounding_box()[2], removed.bounding_box()[5]
    assert lo == pytest.approx(0, abs=1e-6) and hi == pytest.approx(ENGRAVE_DEPTH, abs=1e-6)
    assert (removed.slice(0.3) - lay.text).area() < 1e-3


def test_text_scaled_to_fit_chord():
    cfg = SpoolConfig(**PLAIN, text="W" * 24)
    d = dims(cfg)
    x0, y0, x1, y1 = layout(cfg, d).text.bounds()
    for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        assert math.hypot(x, y) < d.rim_r
    assert y1 < 0  # stays on the 270 deg side


def test_label_at_90_text_at_270_gauge_at_0_tag_at_180():
    cfg = SpoolConfig(text="PLA", tag_pocket=True, label=True, gauge=True, lightweight=False)
    lay = layout(cfg, dims(cfg))
    def centre(cs):
        x0, y0, x1, y1 = cs.bounds()
        return (x0 + x1) / 2, (y0 + y1) / 2
    lx, ly = centre(lay.label)
    assert abs(lx) < 1e-6 and ly > 0
    tx, ty = centre(lay.text)
    assert abs(tx) < 1e-6 and ty < 0
    gx, gy = centre(lay.gauge)
    assert gx > 0 and abs(gy) < 1e-6
    cx, cy = centre(lay.tag)
    assert cx < 0 and abs(cy) < 1e-6


def test_gauge_ticks_engraved_at_tick_radii():
    from spoolmaker.filament import gauge_ticks

    cfg = SpoolConfig(pattern="none", label=False, clip_holes=0, lightweight=False, gauge=True)
    removed = _slice_removed(SpoolConfig(**PLAIN), cfg, ENGRAVE_DEPTH / 2)
    for _, r in gauge_ticks(cfg):
        probe = CrossSection.square((0.4, 0.4), center=True).translate((r, 2.0))
        probe_other = CrossSection.square((0.4, 0.4), center=True).translate((r, -2.0))
        assert (removed ^ probe).area() > 0.1 or (removed ^ probe_other).area() > 0.1


@pytest.mark.parametrize("lightweight", [False, True])
def test_clip_holes_through(lightweight):
    cfg = SpoolConfig(pattern="none", label=False, gauge=False, clip_holes=4, lightweight=lightweight)
    d = dims(cfg)
    m = build_half(cfg, "b")
    r = d.R - CLIP_EDGE_WALL - CLIP_HOLE_D / 2
    # clear of the flange's real, faceted outer edge (its d.seg-gon apothem)
    assert d.R * math.cos(math.pi / d.seg) - (r + CLIP_HOLE_D / 2) >= 2.4
    pairs = clip_hole_centres(cfg, d)
    assert len(pairs) == 4
    for i, pair in enumerate(pairs):
        a = math.radians(45 + 90 * i)
        mid = ((pair[0][0] + pair[1][0]) / 2, (pair[0][1] + pair[1][1]) / 2)
        assert math.atan2(mid[1], mid[0]) == pytest.approx(math.atan2(math.sin(a), math.cos(a)))
        for x, y in pair:
            assert math.hypot(x, y) == pytest.approx(r)
            pin = Manifold.cylinder(d.t, CLIP_HOLE_D / 2 - 0.1, circular_segments=24).translate((x, y, 0))
            assert (pin ^ m).volume() < 1e-6


@pytest.mark.parametrize("lightweight", [False, True])
def test_clip_holes_come_in_tangential_pairs(lightweight):
    cfg = SpoolConfig(pattern="none", label=False, gauge=False, clip_holes=4, lightweight=lightweight)
    d = dims(cfg)
    m = build_half(cfg, "a")
    r = d.R - CLIP_EDGE_WALL - CLIP_HOLE_D / 2
    for (x0, y0), (x1, y1) in clip_hole_centres(cfg, d):
        assert math.hypot(x1 - x0, y1 - y0) == pytest.approx(CLIP_PAIR_PITCH)
        # side by side along the rim: the pair's axis is tangential (normal to the radius)
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        assert abs((x1 - x0) * mx + (y1 - y0) * my) < 1e-9
        # the bridge between the two holes is solid, full thickness
        assert CLIP_PAIR_PITCH == 28.0
        # probe the middle of the bridge (radius capped to stay inside the rim: the
        # straight bridge dips ~1 mm inward of the hole circle at its middle)
        probe = (Manifold.cylinder(d.t, 0.6, circular_segments=24)
                 .translate((mx, my, 0)))
        assert (probe - m).volume() < 1e-6
        # and so is the whole strip from one hole's edge to the other's: the measured
        # bridge is pitch - diameter (solid just inside it, holes just outside it)
        def strip(length, width):
            return (Manifold.cube((length, width, d.t), center=True)
                    .rotate((0, 0, math.degrees(math.atan2(y1 - y0, x1 - x0))))
                    .translate((mx, my, d.t / 2)))
        bridge = CLIP_PAIR_PITCH - CLIP_HOLE_D
        assert (strip(bridge - 0.1, 1.0) - m).volume() < 1e-6
        assert (strip(bridge + 0.1, 0.4) - m).volume() > 1e-4
        assert math.hypot(mx, my) <= r + 1e-9


@pytest.mark.parametrize("n", [1, 2, 4, 8])
def test_clip_hole_count_is_twice_the_pairs(n):
    base = dict(pattern="none", label=False, gauge=False, lightweight=False)
    d = dims(SpoolConfig(**base, clip_holes=0))
    removed = build_half(SpoolConfig(**base, clip_holes=0), "b").slice(d.t / 2) - build_half(
        SpoolConfig(**base, clip_holes=n), "b").slice(d.t / 2)
    holes = [p for p in removed.decompose() if p.area() > 1e-3]
    assert len(holes) == 2 * n
    for h in holes:
        assert h.area() == pytest.approx(math.pi * (CLIP_HOLE_D / 2) ** 2, rel=0.03)


def test_clip_pair_overlapping_a_keepout_is_skipped():
    cfg = SpoolConfig(**{**PLAIN, "clip_holes": 4})
    d = dims(cfg)
    pairs = clip_hole_centres(cfg, d)
    x, y = pairs[1][0]
    blocker = CrossSection.circle(1.0, 16).translate((x, y))
    kept = clip_hole_centres(cfg, d, blocker)
    assert kept == [pairs[0], pairs[2], pairs[3]]


@pytest.mark.parametrize("lightweight", [False, True])
def test_clip_pairs_clear_the_keepouts(lightweight):
    cfg = SpoolConfig(pattern="none", lightweight=lightweight, clip_holes=8, label=True, gauge=True,
                      text="WWWWWWWWWWWW", tag_pocket=True, tag_diameter=30)
    d = dims(cfg)
    lay = layout(cfg, d)
    pairs = clip_hole_centres(cfg, d, lay.keepouts)
    assert len(pairs) == 8
    holes = CrossSection.batch_boolean(
        [CrossSection.circle(CLIP_HOLE_D / 2, 24).translate(c) for p in pairs for c in p], OpType.Add)
    assert (holes ^ lay.keepouts).is_empty()


@pytest.mark.parametrize("pattern", ["honeycomb", "voronoi", "windows"])
def test_clip_collars_full_thickness(pattern):
    cfg = SpoolConfig(pattern=pattern, pattern_density=1.0, lightweight=True, clip_holes=8)
    d = dims(cfg)
    m = build_half(cfg, "b")
    for x, y in (c for p in clip_hole_centres(cfg, d) for c in p):
        collar = (Manifold.cylinder(d.t, CLIP_HOLE_D / 2 + CLIP_COLLAR - 0.05, circular_segments=48)
                  - Manifold.cylinder(d.t, CLIP_HOLE_D / 2 + 0.05, circular_segments=48)
                  ).translate((x, y, 0))
        assert (collar - m).volume() < 1e-3
        assert math.hypot(x, y) - CLIP_HOLE_D / 2 - CLIP_COLLAR < d.rim_r  # reaches past the rim


def test_tag_pocket_on_inner_face():
    cfg = SpoolConfig(**PLAIN, tag_pocket=True, tag_diameter=25)
    d = dims(cfg)
    diff = build_half(SpoolConfig(**PLAIN), "b") - build_half(cfg, "b")
    removed = Manifold.compose([p for p in diff.decompose() if p.volume() > 1e-6])
    bb = removed.bounding_box()
    assert bb[2] == pytest.approx(d.t - TAG_DEPTH, abs=1e-6) and bb[5] == pytest.approx(d.t, abs=1e-6)
    assert bb[3] - bb[0] == pytest.approx(25.4, abs=0.1)
    assert (bb[0] + bb[3]) / 2 == pytest.approx(-(d.r_core_out + 12.5 + 3), abs=0.05)


def test_tag_fit_validation():
    ok = SpoolConfig(tag_pocket=True, tag_diameter=30, lightweight=False, label=True, gauge=True)
    assert not any("tag" in e.lower() for e in validate(ok))
    bad = SpoolConfig(tag_pocket=True, tag_diameter=30, refill="custom", coil_inner_diameter=150.0,
                      lightweight=False, label=True, gauge=True)
    assert any("tag" in e.lower() for e in validate(bad))
    assert not any("tag" in e.lower() for e in validate(
        SpoolConfig(tag_pocket=False, refill="custom", coil_inner_diameter=150.0,
                    lightweight=False, label=True, gauge=True)))


def test_lightweight_web_thinned_but_keepouts_full():
    cfg = SpoolConfig(pattern="none", lightweight=True, clip_holes=0, label=True, gauge=True)
    d = dims(cfg)
    lay = layout(cfg, d)
    m = build_half(cfg, "b")
    web_t = max(1.6, 0.5 * d.t)
    # outer face flat: full footprint at the bottom
    assert m.slice(0.01).area() == pytest.approx(build_half(SpoolConfig(pattern="none", clip_holes=0, lightweight=False, label=True, gauge=True), "b").slice(0.01).area(), rel=1e-3)
    upper = m.slice((web_t + d.t) / 2)
    # keep-outs remain at full thickness
    for ko in (lay.label, lay.gauge):
        assert (ko - upper).area() < 1e-3
    # a point in the open web is thinned
    probe = CrossSection.square((1, 1), center=True).translate((-(d.hub_ring_r + d.rim_r) / 2 * 0.7071,
                                                               (d.hub_ring_r + d.rim_r) / 2 * 0.7071))
    assert (probe ^ upper).area() < 1e-6
    # hub ring and rim ring at full thickness
    rim = CrossSection.circle(d.R, d.seg) - CrossSection.circle(d.rim_r + 0.1, d.seg)
    assert (rim - upper).area() < 1e-2


def test_lightweight_engravings_do_not_break_through():
    cfg = SpoolConfig(pattern="voronoi", pattern_density=1.0, lightweight=True, text="PETG",
                      flange_thickness=2.0, coil_width=60.0, clip_holes=0, tag_pocket=True,
                      label=True, gauge=True)
    d = dims(cfg)
    lay = layout(cfg, d)
    m = build_half(cfg, "a")
    # Every engraved region still has material from ENGRAVE_DEPTH up to t.
    for cs in (lay.text, lay.label, lay.gauge):
        prism = cs.extrude(d.t - ENGRAVE_DEPTH - 0.02).translate((0, 0, ENGRAVE_DEPTH + 0.01))
        assert (prism - m).volume() < 1e-3


@pytest.mark.parametrize("lightweight", [False, True])
@pytest.mark.parametrize("half", ["a", "b"])
def test_cores_are_thin_tubes(half, lightweight):
    """Between the collar and the lock, each core is just its thin tube wall: nothing but
    air from the bore out to the tube's bore."""
    from spoolmaker.geometry.dims import COLLAR_DEPTH
    from spoolmaker.geometry.lock import core_height_b

    cfg = SpoolConfig(**{**PLAIN, "lightweight": lightweight})
    d = dims(cfg)
    m = build_half(cfg, half)
    r_in = d.r_tube_a_in if half == "a" else d.r_tube_b_in
    for z in (d.t + COLLAR_DEPTH + 1, d.t + core_height_b(d) - 4):
        sec = m.slice(z) ^ CrossSection.circle(d.r_core_out + 1, d.seg)
        assert sec.area() == pytest.approx(math.pi * (d.r_core_out**2 - r_in**2), rel=0.01)
        assert (sec ^ CrossSection.circle(r_in - 0.05, d.seg)).is_empty()


@pytest.mark.parametrize("half", ["a", "b"])
def test_bore_collar(half):
    from spoolmaker.geometry.dims import COLLAR_DEPTH, COLLAR_WALL

    d = dims(SpoolConfig(**PLAIN))
    m = build_half(SpoolConfig(**PLAIN), half)
    probe = Manifold.cylinder(COLLAR_DEPTH - 0.5, 0.2, circular_segments=8)
    for k in range(6):
        a = math.radians(k * 60 + 7)
        p = probe.translate(((d.r_bore + 1) * math.cos(a), (d.r_bore + 1) * math.sin(a), d.t))
        assert (p - m).volume() < 1e-6  # solid collar wall at r_bore + 1
    # ... and nothing beyond its top
    above = Manifold.cylinder(1.0, d.r_bore + COLLAR_WALL - 0.1, circular_segments=d.seg) - \
        Manifold.cylinder(1.0, d.r_bore + 0.1, circular_segments=d.seg)
    assert (above.translate((0, 0, d.t + COLLAR_DEPTH + 0.2)) ^ m).volume() < 1e-6


def test_b_tube_top_is_full_annulus():
    """B's tube top (its contact face with A's tube top) is a full annulus: the 45 deg
    bridge to the sleeve sits inside it."""
    from spoolmaker.geometry.lock import core_height_b

    cfg = SpoolConfig(**PLAIN)
    d = dims(cfg)
    sec = build_half(cfg, "b").slice(d.t + core_height_b(d) - 0.05)
    ring = CrossSection.circle(d.r_core_out - 0.05, d.seg) - CrossSection.circle(d.r_tube_b_in, d.seg)
    assert (ring - sec).area() < 1e-3
    # the bridge reaches almost to the sleeve bore just below the joint
    assert (CrossSection.circle(d.r_tube_b_in, d.seg) ^ sec).area() > 0.8 * math.pi * (
        d.r_tube_b_in**2 - (d.r_sleeve_in + 0.1) ** 2)


def test_build_half_performance():
    cfg = SpoolConfig(pattern="voronoi", pattern_density=1.0, lightweight=True, text="WWWWWWWWWWWW",
                      tag_pocket=True, clip_holes=8, label=True, gauge=True)
    build_half(cfg, "a").to_mesh()  # warm caches (font, scipy import)
    t0 = time.perf_counter()
    build_half(cfg, "a").to_mesh()  # manifold3d is lazy; force evaluation
    assert time.perf_counter() - t0 < 1.5


def test_lightweight_windows_ribs_full_thickness():
    """Lightweight mode doesn't web-thin the windows pattern: its ribs (and the hub ring
    and rim) stay full flange thickness."""
    from spoolmaker.geometry.patterns import _window_ribs

    cfg = SpoolConfig(pattern="windows", pattern_density=1.0, lightweight=True, label=False,
                      gauge=False, clip_holes=0)
    d = dims(cfg)
    sec = build_half(cfg, "a").slice(d.t - 0.1)
    n, rib = _window_ribs(1.0)
    r_mid = (d.hub_ring_r + d.rim_r) / 2
    probe = CrossSection.square((10.0, rib * 0.8), center=True).translate((r_mid, 0))
    for i in range(n):
        p = probe.rotate(360 * i / n)
        assert (p - sec).area() < 1e-3  # rib i is solid right up to the inner face
    # the windows themselves are open
    win = CrossSection.circle(2.0, 24).translate((r_mid, 0)).rotate(180 / n)
    assert (win ^ sec).is_empty()


@pytest.mark.parametrize("pattern", ["none", "honeycomb", "voronoi", "windows"])
@pytest.mark.parametrize("lightweight", [False, True])
def test_tag_pocket_full_depth_in_full_thickness_pad(pattern, lightweight):
    """The pocket is a full-diameter, TAG_DEPTH-deep recess in a full-thickness pad, also
    where lightweight mode thins the web around it."""
    cfg = SpoolConfig(pattern=pattern, lightweight=lightweight, label=False, gauge=False,
                      clip_holes=0, tag_pocket=True, tag_diameter=25)
    d = dims(cfg)
    lay = layout(cfg, d)
    m = build_half(cfg, "b")
    floor_t = d.t - TAG_DEPTH
    want = math.pi * (cfg.tag_diameter / 2 + 0.2) ** 2 * TAG_DEPTH
    recess = lay.tag_pocket.extrude(TAG_DEPTH).translate((0, 0, floor_t))
    assert (recess - m).volume() == pytest.approx(want, rel=0.05)    # pocket is empty
    floor = lay.tag_pocket.extrude(floor_t)
    assert (floor - m).volume() == pytest.approx(0, abs=1e-3)       # floor is solid
    ring = (lay.tag - lay.tag_pocket).extrude(d.t)
    assert (ring - m).volume() == pytest.approx(0, abs=1e-3)        # pad wall full height
