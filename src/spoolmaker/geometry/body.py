"""Plain bodies of the two halves, in print pose (outer flange face on z=0)."""

from __future__ import annotations

from manifold3d import Manifold

from .dims import SEAT_GAP, Dims


def tube(height: float, r_in: float, r_out: float, seg: int) -> Manifold:
    outer = Manifold.cylinder(height, r_out, circular_segments=seg)
    inner = Manifold.cylinder(height + 2, r_in, circular_segments=seg).translate((0, 0, -1))
    return outer - inner


def flange_disc(d: Dims) -> Manifold:
    """Flange disc on z=0..t with a bore-sized hole."""
    return tube(d.t, d.r_bore, d.R, d.seg)


def core_tube(d: Dims) -> Manifold:
    """Half A's core tube, standing on the flange inner face."""
    return tube(d.inner_width, d.r_core_in, d.r_core_out, d.seg).translate((0, 0, d.t))


def sleeve(d: Dims) -> Manifold:
    """Half B's sleeve; it forms the bore and slides inside A's core, ending SEAT_GAP
    short of A's flange so only A's core top against B's flange seats the halves."""
    return tube(d.inner_width - SEAT_GAP, d.r_bore, d.r_sleeve_out, d.seg).translate((0, 0, d.t))
