"""Derived dimensions shared by all geometry modules."""

from __future__ import annotations

from dataclasses import dataclass

from ..config import RIM_WIDTH, SpoolConfig

SLEEVE_WALL = 2.4
HUB_RING = 6.0
SEGMENTS = 128


@dataclass(frozen=True)
class Dims:
    R: float  # outer radius
    t: float  # flange thickness
    inner_width: float  # distance between flange inner faces
    r_bore: float
    sleeve_wall: float
    r_sleeve_out: float
    r_core_in: float
    r_core_out: float
    hub_ring_r: float  # solid zone on the flange around the core
    rim_r: float
    lock_clearance: float
    seg: int


def dims(cfg: SpoolConfig) -> Dims:
    r_bore = cfg.bore_diameter / 2
    r_sleeve_out = r_bore + SLEEVE_WALL
    r_core_out = cfg.coil_inner_diameter / 2 - cfg.coil_clearance / 2
    R = cfg.outer_diameter / 2
    return Dims(
        R=R,
        t=cfg.flange_thickness,
        inner_width=cfg.inner_width,
        r_bore=r_bore,
        sleeve_wall=SLEEVE_WALL,
        r_sleeve_out=r_sleeve_out,
        r_core_in=r_sleeve_out + cfg.lock_clearance,
        r_core_out=r_core_out,
        hub_ring_r=r_core_out + HUB_RING,
        rim_r=R - RIM_WIDTH,
        lock_clearance=cfg.lock_clearance,
        seg=SEGMENTS,
    )
