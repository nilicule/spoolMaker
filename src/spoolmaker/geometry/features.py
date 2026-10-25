"""Flange features: patterns, label panel, text, fill gauge, clip holes, tag pocket,
lightweight mode.

Frames: the half is in print pose, the outer flange face on z=0. Layout angles are
measured CCW from +X in that model frame (label 90 deg, text 270 deg, gauge 0 deg,
tag 180 deg). Someone looking at the outside of the spool sees the z=0 face from -Z,
which mirrors X. Engravings are therefore composed in a "viewer frame" (what the
viewer sees, +Y up) and mirrored in X into the model frame, so they read correctly.
In the viewer frame the gauge (model 0 deg) is on the left and the tag pocket (model
180 deg, on the hidden inner face) is on the right.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from manifold3d import CrossSection, JoinType, Manifold, OpType

from ..config import RIM_WIDTH, SpoolConfig
from ..filament import gauge_ticks
from .dims import Dims
from .lock import LUG_ARC_DEG, LUG_AXIAL, LUGS, channel_r
from .patterns import pattern_cutouts
from .text import text_outline

ENGRAVE_DEPTH = 0.6
LABEL_OUTLINE_W = 0.8
TAG_DEPTH = 1.0
CLIP_HOLE_D = 2.2

TEXT_CAP = 7.0
TEXT_MARGIN = 2.0  # text keeps this far from the hub ring and the rim
TEXT_KEEPOUT_PAD = 1.5
GAUGE_W = 10.0
TICK_W = 1.2
GAUGE_TEXT_CAP = 3.5
TAG_CLEARANCE = 0.4
TAG_WALL = 2.0  # full-thickness wall around the tag pocket (matters in lightweight)
MIN_WEB_T = 1.6
CORE_SKIN = 1.2
CORE_POCKET_GAP = 3.0  # material kept above the lock zone, below the core pockets
_SEG = 64


@dataclass(frozen=True)
class Layout:
    label: CrossSection  # label panel (keep-out)
    text: CrossSection  # text keep-out zone around the engraved text
    gauge: CrossSection  # gauge strip (keep-out)
    tag: CrossSection  # tag pocket keep-out (pocket + wall)
    keepouts: CrossSection  # union of the above
    engrave: CrossSection  # everything engraved into the outer face, model frame
    tag_pocket: CrossSection  # the pocket itself, model frame


def _to_model(cs: CrossSection) -> CrossSection:
    """Viewer frame -> model frame (mirror X)."""
    return cs.mirror((1, 0))


def _rect(x0: float, y0: float, x1: float, y1: float) -> CrossSection:
    return CrossSection.square((x1 - x0, y1 - y0)).translate((x0, y0))


def _annulus(r_in: float, r_out: float, seg: int) -> CrossSection:
    return CrossSection.circle(r_out, seg) - CrossSection.circle(r_in, seg)


def tag_center_r(cfg: SpoolConfig, d: Dims) -> float:
    return d.r_core_out + cfg.tag_diameter / 2 + 3


def tag_fits(cfg: SpoolConfig, d: Dims) -> bool:
    return tag_center_r(cfg, d) + (cfg.tag_diameter + TAG_CLEARANCE) / 2 <= d.rim_r


def _fit_text(cs: CrossSection, r_mid: float, d: Dims) -> CrossSection:
    """Scale text centred at the origin so that, placed at (0, -r_mid), it stays
    inside the annulus hub_ring_r..rim_r with TEXT_MARGIN."""
    x0, y0, x1, y1 = cs.bounds()
    w, h = x1 - x0, y1 - y0
    lo, hi = d.hub_ring_r + TEXT_MARGIN, d.rim_r - TEXT_MARGIN
    s = min(1.0, 2 * min(r_mid - lo, hi - r_mid) / h)
    hh = h * s / 2
    half_w = math.sqrt(max(hi**2 - (r_mid + hh) ** 2, 0.0))
    s = min(s, 2 * half_w / w)
    return cs.scale((s, s))


def _place_1d(centres: list[float], lengths: list[float], lo: float, hi: float,
              gap: float) -> list[float]:
    """Left edges for sorted intervals as close to their centres as possible, ordered,
    at least `gap` apart and inside lo..hi (caller ensures they fit)."""
    edges = []
    for i, (c, L) in enumerate(zip(centres, lengths)):
        e = c - L / 2
        e = max(e, lo if i == 0 else edges[-1] + lengths[i - 1] + gap)
        edges.append(e)
    for i in range(len(edges) - 1, -1, -1):
        cap = hi - lengths[i] if i == len(edges) - 1 else edges[i + 1] - gap - lengths[i]
        edges[i] = min(edges[i], cap)
    return edges


def _gauge(cfg: SpoolConfig, d: Dims) -> CrossSection:
    """Ruler-style tick marks and gram values in the viewer frame (strip along -X).

    Ticks run across the lower half of the strip at each gauge radius; the values sit
    on the upper half, centred over their ticks and nudged apart where they would
    collide (scaled down only if they cannot fit at GAUGE_TEXT_CAP).
    """
    lo, hi = d.hub_ring_r + TICK_W, d.rim_r - TICK_W
    ticks = sorted((r, g) for g, r in gauge_ticks(cfg) if lo <= r <= hi)
    if not ticks:
        return CrossSection()
    half = GAUGE_W / 2
    gap = 1.2
    labels = [text_outline(str(g), GAUGE_TEXT_CAP) for _, g in ticks]
    lengths = [lab.bounds()[2] - lab.bounds()[0] for lab in labels]
    span_lo, span_hi = d.hub_ring_r + 0.5, d.rim_r - 0.5
    room = span_hi - span_lo - gap * (len(ticks) - 1)
    s = max(min(1.0, room / sum(lengths)), 0.3)
    lengths = [L * s for L in lengths]
    edges = _place_1d([r for r, _ in ticks], lengths, span_lo, span_hi, gap)
    parts = []
    for (r, _), lab, L, e in zip(ticks, labels, lengths, edges):
        parts.append(_rect(-r - TICK_W / 2, -(half - 0.5), -r + TICK_W / 2, -0.3))
        parts.append(lab.scale((s, s)).translate((-(e + L / 2), half / 2)))
    return CrossSection.batch_boolean(parts, OpType.Add)


def layout(cfg: SpoolConfig, d: Dims) -> Layout:
    r_mid = (d.hub_ring_r + d.rim_r) / 2
    zone = _annulus(d.hub_ring_r + 1.0, d.rim_r - 1.0, d.seg)
    empty = CrossSection()
    engrave_v: list[CrossSection] = []

    label = empty
    if cfg.label:
        panel = CrossSection.square((cfg.label_width, cfg.label_height), center=True).translate((0, r_mid))
        label = panel ^ zone
        if not label.is_empty():
            engrave_v.append(label - label.offset(-LABEL_OUTLINE_W, JoinType.Miter))

    text = empty
    glyphs = text_outline(cfg.text, TEXT_CAP) if cfg.text else empty
    if not glyphs.is_empty():
        glyphs = _fit_text(glyphs, r_mid, d).translate((0, -r_mid))
        x0, y0, x1, y1 = glyphs.bounds()
        text = _rect(x0, y0, x1, y1).offset(TEXT_KEEPOUT_PAD, JoinType.Round, 2.0, 8)
        engrave_v.append(glyphs)

    gauge = empty
    if cfg.gauge:
        gauge = _rect(-d.rim_r, -GAUGE_W / 2, -d.hub_ring_r, GAUGE_W / 2)
        marks = _gauge(cfg, d)
        if not marks.is_empty():
            engrave_v.append(marks ^ gauge)

    tag = tag_pocket = empty
    if cfg.tag_pocket and tag_fits(cfg, d):
        c = (-tag_center_r(cfg, d), 0.0)  # model frame, 180 deg
        r = (cfg.tag_diameter + TAG_CLEARANCE) / 2
        tag_pocket = CrossSection.circle(r, _SEG).translate(c)
        tag = CrossSection.circle(r + TAG_WALL, _SEG).translate(c)

    label, text, gauge = (_to_model(cs) for cs in (label, text, gauge))
    engrave = (
        _to_model(CrossSection.batch_boolean(engrave_v, OpType.Add)) if engrave_v else empty
    )
    keepouts = CrossSection.batch_boolean([label, text, gauge, tag], OpType.Add)
    # Engravings must stay inside full-thickness keep-outs (lightweight mode).
    engrave = engrave ^ keepouts if not engrave.is_empty() else engrave
    return Layout(label, text, gauge, tag, keepouts, engrave, tag_pocket)


def _clip_holes(cfg: SpoolConfig, d: Dims) -> CrossSection:
    n = cfg.clip_holes
    if n <= 0:
        return CrossSection()
    r = d.R - RIM_WIDTH / 2
    hole = CrossSection.circle(CLIP_HOLE_D / 2, 24)
    holes = []
    for i in range(n):
        a = math.radians(45 + 360 * i / n)
        holes.append(hole.translate((r * math.cos(a), r * math.sin(a))))
    return CrossSection.batch_boolean(holes, OpType.Add)


def web_thickness(d: Dims) -> float:
    return max(MIN_WEB_T, 0.6 * d.t)


def cutters(cfg: SpoolConfig, d: Dims, lay: Layout) -> list[Manifold]:
    """Solids to subtract from either half's flange."""
    out: list[Manifold] = []
    through = CrossSection.batch_boolean(
        [
            pattern_cutouts(cfg.pattern, cfg.pattern_density, d.hub_ring_r, d.rim_r,
                            cfg.pattern_seed, lay.keepouts),
            _clip_holes(cfg, d),
        ],
        OpType.Add,
    )
    if not through.is_empty():
        out.append(through.extrude(d.t + 2).translate((0, 0, -1)))
    if not lay.engrave.is_empty():
        out.append(lay.engrave.extrude(ENGRAVE_DEPTH + 1).translate((0, 0, -1)))
    if not lay.tag_pocket.is_empty():
        out.append(lay.tag_pocket.extrude(TAG_DEPTH + 1).translate((0, 0, d.t - TAG_DEPTH)))
    if cfg.lightweight:
        web_t = web_thickness(d)
        if web_t < d.t:
            region = _annulus(d.hub_ring_r, d.rim_r, d.seg)
            if not lay.keepouts.is_empty():
                region = region - lay.keepouts
            out.append(region.extrude(d.t - web_t + 1).translate((0, 0, web_t)))
    return out


def apply_features(m: Manifold, cfg: SpoolConfig, d: Dims, lay: Layout) -> Manifold:
    cuts = cutters(cfg, d, lay)
    if not cuts:
        return m
    return Manifold.batch_boolean([m, *cuts], OpType.Subtract)


def core_pockets(d: Dims) -> Manifold:
    """LUGS*3 blind axial pockets from the top end of half A's core wall, placed
    radially outside the lock channels/pocket and angularly between the channels."""
    r0 = channel_r(d) + CORE_SKIN
    r1 = d.r_core_out - CORE_SKIN
    depth = d.inner_width - LUG_AXIAL - CORE_POCKET_GAP
    if r1 - r0 < 1.0 or depth <= 0:
        return Manifold()
    z_top = d.t + d.inner_width
    gap = 360 / LUGS
    free = gap - LUG_ARC_DEG - 4  # angular room between channels (with margin)
    pitch = free / 3
    rib = math.degrees(CORE_SKIN / r0) + 1.0  # keep >= CORE_SKIN rib between pockets
    arc = pitch - rib
    profile = CrossSection([[(r0, 0.0), (r1, 0.0), (r1, depth + 1), (r0, depth + 1)]])
    pocket = profile.revolve(max(d.seg // 8, 8), arc)
    parts = []
    for i in range(LUGS):
        start = i * gap + LUG_ARC_DEG / 2 + 2
        for k in range(3):
            a = start + k * pitch + rib / 2
            parts.append(pocket.rotate((0, 0, a)))
    return Manifold.compose(parts).translate((0, 0, z_top - depth))
