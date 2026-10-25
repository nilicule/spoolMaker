"""Plain bodies of the two halves, in print pose (outer flange face on z=0)."""

from __future__ import annotations

from manifold3d import CrossSection, Manifold

from .dims import COLLAR_DEPTH, SEAT_GAP, Dims
from .lock import SOCKET_DEPTH, core_height_a, core_height_b

_OVERLAP = 0.5  # cores and collars reach this far into the (solid) flange for a clean union


def tube(height: float, r_in: float, r_out: float, seg: int) -> Manifold:
    outer = Manifold.cylinder(height, r_out, circular_segments=seg)
    inner = Manifold.cylinder(height + 2, r_in, circular_segments=seg).translate((0, 0, -1))
    return outer - inner


def flange_disc(d: Dims) -> Manifold:
    """Flange disc on z=0..t with a bore-sized hole, plus the bore collar on its inner face.
    The flange is solid from the bore out to the hub ring, so the core sits on solid
    material."""
    collar = tube(COLLAR_DEPTH + _OVERLAP, d.r_bore, d.r_collar, d.seg).translate(
        (0, 0, d.t - _OVERLAP))
    return tube(d.t, d.r_bore, d.R, d.seg) + collar


def core_a(d: Dims) -> Manifold:
    """Half A's (female) core: a thin tube up from the flange whose top SOCKET_DEPTH is the
    socket (bore r_socket_in) that receives B's sleeve. The socket wall is thicker than
    the tube; the inward step below it is a 45 deg chamfer (support-free), or an upward
    ledge if the socket bore is the wider one."""
    h = core_height_a(d)
    z_floor = h - SOCKET_DEPTH
    rise = max(d.r_tube_a_in - d.r_socket_in, 0.0)
    profile = [
        (d.r_tube_a_in, -_OVERLAP),
        (d.r_core_out, -_OVERLAP),
        (d.r_core_out, h),
        (d.r_socket_in, h),
        (d.r_socket_in, z_floor),
        (d.r_tube_a_in, z_floor - rise),
    ]
    return CrossSection([profile]).revolve(d.seg).translate((0, 0, d.t))


def core_b(d: Dims) -> Manifold:
    """Half B's (male) core: a thin tube up to the joint, then the sleeve that plugs into
    A's socket and ends SEAT_GAP short of its floor, so only the two core tops meeting at
    the joint seat the halves. The sleeve sits radially inside the tube wall; a 45 deg
    inward chamfer at the top of the tube carries it (support-free), leaving the tube top
    a full annulus."""
    h = core_height_b(d)
    top = h + SOCKET_DEPTH - SEAT_GAP
    # Inner surface: tube bore, then 45 deg inward to the sleeve bore at the joint (or an
    # upward-facing ledge if the tube bore is already inside the sleeve bore).
    drop = max(d.r_tube_b_in - d.r_sleeve_in, 0.0)
    profile = [
        (d.r_tube_b_in, -_OVERLAP),
        (d.r_core_out, -_OVERLAP),
        (d.r_core_out, h),
        (d.r_sleeve_out, h),
        (d.r_sleeve_out, top),
        (d.r_sleeve_in, top),
        (d.r_sleeve_in, h),
        (d.r_tube_b_in, h - drop),
    ]
    return CrossSection([profile]).revolve(d.seg).translate((0, 0, d.t))
