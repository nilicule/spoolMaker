"""Bayonet twist-lock: lugs on half B's sleeve tip, channels + pocket in half A's core.

Both are expressed in each half's print pose. Lugs are centred on angles
i * 360/LUGS, which map onto themselves when half B is flipped about X, so
the channels in A sit at the same angles. Twisting B by +TWIST_DEG (about +Z
in the assembled frame) moves the lugs into the circumferential pocket.
"""

from __future__ import annotations

import math

from manifold3d import CrossSection, Manifold

from .dims import Dims

LUGS = 3
LUG_ARC_DEG = 20
LUG_RADIAL = 1.4
LUG_AXIAL = 4.0
TWIST_DEG = 30
DETENT_BUMP = 0.4
DETENT_ARC = 1.5  # mm of arc length the detent ridge occupies


def _sector(profile: list[tuple[float, float]], start_deg: float, arc_deg: float, seg: int) -> Manifold:
    """Revolve an (r, z) profile over arc_deg starting at start_deg about +Z."""
    return CrossSection([profile]).revolve(seg, arc_deg).rotate((0, 0, start_deg))


def _box_profile(r0: float, r1: float, z0: float, z1: float) -> list[tuple[float, float]]:
    return [(r0, z0), (r1, z0), (r1, z1), (r0, z1)]


def _deg(arc_mm: float, r: float) -> float:
    return math.degrees(arc_mm / r)


def channel_r(d: Dims) -> float:
    """Outer radius of channels and pocket in half A."""
    return d.r_sleeve_out + LUG_RADIAL + d.lock_clearance


def lugs(d: Dims) -> Manifold:
    """Lugs at the free tip of B's sleeve, underside chamfered 45 deg (print pose)."""
    z1 = d.t + d.inner_width
    z0 = z1 - LUG_AXIAL
    r_in = d.r_sleeve_out - d.sleeve_wall / 2  # overlap into the sleeve wall
    r_out = d.r_sleeve_out + LUG_RADIAL
    profile = [(r_in, z0), (d.r_sleeve_out, z0), (r_out, z0 + LUG_RADIAL), (r_out, z1), (r_in, z1)]
    out = Manifold()
    for i in range(LUGS):
        centre = i * 360 / LUGS
        out += _sector(profile, centre - LUG_ARC_DEG / 2, LUG_ARC_DEG, d.seg)
    return out


def lock_cuts(d: Dims) -> Manifold:
    """Material to remove from half A's core: axial channels, pocket, minus detent ridges."""
    r_out = channel_r(d)
    r_in = d.r_core_in - 0.5  # start inside the empty hole for a clean cut
    clr = _deg(d.lock_clearance, r_out)
    half_arc = LUG_ARC_DEG / 2
    z0 = d.t
    z_top = d.t + d.inner_width + 1.0
    z_pocket = d.t + LUG_AXIAL + d.lock_clearance
    bump_arc = _deg(DETENT_ARC, r_out)

    cuts = Manifold()
    for i in range(LUGS):
        c = i * 360 / LUGS
        channel = _sector(_box_profile(r_in, r_out, z0, z_top), c - half_arc - clr,
                          LUG_ARC_DEG + 2 * clr, d.seg)
        pocket = _sector(_box_profile(r_in, r_out, z0, z_pocket), c - half_arc - clr,
                         TWIST_DEG + LUG_ARC_DEG + 2 * clr, d.seg)
        # Detent ridge just behind the locked lug's trailing edge (c + TWIST - half_arc).
        a1 = c + TWIST_DEG - half_arc - clr
        a0 = a1 - bump_arc
        pocket -= _detent(d, r_out, a0, a1, z0 - 1.0, z_pocket + 1.0)
        cuts += channel + pocket
    return cuts


def _detent(d: Dims, r_wall: float, a0: float, a1: float, z0: float, z1: float) -> Manifold:
    """Ramped ridge protruding DETENT_BUMP inward from the pocket's outer wall."""
    am = (a0 + a1) / 2
    back = r_wall + 1.0

    def p(r: float, a: float) -> tuple[float, float]:
        return (r * math.cos(math.radians(a)), r * math.sin(math.radians(a)))

    poly = [p(back, a0), p(back, a1), p(r_wall, a1), p(r_wall - DETENT_BUMP, am), p(r_wall, a0)]
    if _signed_area(poly) < 0:
        poly.reverse()
    return CrossSection([poly]).extrude(z1 - z0).translate((0, 0, z0))


def _signed_area(poly: list[tuple[float, float]]) -> float:
    return 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]))
