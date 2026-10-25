"""Derived dimensions shared by all geometry modules."""

from __future__ import annotations

from dataclasses import dataclass

from ..config import MIN_LOCK_WALL, RIM_WIDTH, RIM_WIDTH_LIGHT, SpoolConfig

SLEEVE_WALL = 2.4
TUBE_WALL = 3.0  # plain core tube wall
LUG_RADIAL = 1.4  # radial reach of B's lugs (and depth of A's channels into the socket wall)
# Half A's socket wall (top SOCKET_DEPTH of its tube): channel depth (measured from the
# socket bore) plus the wall left behind the channels and pocket. Thicker than the tube;
# a 45 deg chamfer below the socket makes the inward step.
SOCKET_WALL = LUG_RADIAL + MIN_LOCK_WALL
COLLAR_DEPTH = 8.0  # bore collar height above each flange's inner face
COLLAR_WALL = 2.4
HUB_RING = 6.0  # solid flange zone around the core
HUB_RING_LIGHT = 4.0  # narrower in lightweight mode
SEAT_GAP = 0.3  # B's sleeve stops short of A's socket floor; the core tops alone set the width
SEGMENTS = 128


@dataclass(frozen=True)
class Dims:
    R: float  # outer radius
    t: float  # flange thickness
    inner_width: float  # distance between flange inner faces
    r_bore: float
    r_collar: float  # outer radius of the bore collar
    r_core_out: float
    r_tube_a_in: float  # inner radius of half A's tube below the socket
    r_tube_b_in: float  # inner radius of half B's tube
    r_socket_in: float  # bore of half A's socket
    sleeve_wall: float
    r_sleeve_out: float
    r_sleeve_in: float
    hub_ring_r: float  # solid zone on the flange around the core
    rim_width: float  # solid outer rim
    rim_r: float
    lock_clearance: float
    seg: int


def dims(cfg: SpoolConfig) -> Dims:
    r_bore = cfg.bore_diameter / 2
    r_core_out = cfg.coil_inner_diameter / 2 - cfg.coil_clearance / 2
    r_socket_in = r_core_out - SOCKET_WALL
    r_sleeve_out = r_socket_in - cfg.lock_clearance
    R = cfg.outer_diameter / 2
    rim_width = RIM_WIDTH_LIGHT if cfg.lightweight else RIM_WIDTH
    hub_ring = HUB_RING_LIGHT if cfg.lightweight else HUB_RING
    return Dims(
        R=R,
        t=cfg.flange_thickness,
        inner_width=cfg.inner_width,
        r_bore=r_bore,
        r_collar=r_bore + COLLAR_WALL,
        r_core_out=r_core_out,
        r_tube_a_in=r_core_out - TUBE_WALL,
        r_tube_b_in=r_core_out - TUBE_WALL,
        r_socket_in=r_socket_in,
        sleeve_wall=SLEEVE_WALL,
        r_sleeve_out=r_sleeve_out,
        r_sleeve_in=r_sleeve_out - SLEEVE_WALL,
        hub_ring_r=r_core_out + hub_ring,
        rim_width=rim_width,
        rim_r=R - rim_width,
        lock_clearance=cfg.lock_clearance,
        seg=SEGMENTS,
    )
