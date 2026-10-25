"""Plain bodies of the two halves, in print pose (outer flange face on z=0)."""

from __future__ import annotations

from manifold3d import Manifold

from .dims import SEAT_GAP, Dims
from .lock import SOCKET_DEPTH, core_height_a, core_height_b


def tube(height: float, r_in: float, r_out: float, seg: int) -> Manifold:
    outer = Manifold.cylinder(height, r_out, circular_segments=seg)
    inner = Manifold.cylinder(height + 2, r_in, circular_segments=seg).translate((0, 0, -1))
    return outer - inner


def flange_disc(d: Dims) -> Manifold:
    """Flange disc on z=0..t with a bore-sized hole."""
    return tube(d.t, d.r_bore, d.R, d.seg)


def core_a(d: Dims) -> Manifold:
    """Half A's (female) core on the flange inner face: solid tube r_bore..r_core_out,
    with the top SOCKET_DEPTH opened out to r_core_in to receive B's sleeve."""
    h = core_height_a(d)
    solid = tube(h - SOCKET_DEPTH, d.r_bore, d.r_core_out, d.seg)
    socket = tube(SOCKET_DEPTH, d.r_core_in, d.r_core_out, d.seg).translate((0, 0, h - SOCKET_DEPTH))
    return (solid + socket).translate((0, 0, d.t))


def core_b(d: Dims) -> Manifold:
    """Half B's (male) core tube r_bore..r_core_out plus the sleeve on top of it. The sleeve
    plugs into A's socket and ends SEAT_GAP short of its floor, so only the two core tops
    meeting at the joint seat the halves."""
    h = core_height_b(d)
    core = tube(h, d.r_bore, d.r_core_out, d.seg)
    sleeve = tube(SOCKET_DEPTH - SEAT_GAP, d.r_bore, d.r_sleeve_out, d.seg).translate((0, 0, h))
    return (core + sleeve).translate((0, 0, d.t))
