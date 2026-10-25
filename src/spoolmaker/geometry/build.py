"""Assemble the spool halves."""

from __future__ import annotations

from typing import Literal

from manifold3d import Manifold

from ..config import SpoolConfig
from .body import core_tube, flange_disc, sleeve
from .dims import dims
from .lock import TWIST_DEG, lock_cuts, lugs


def build_half(cfg: SpoolConfig, half: Literal["a", "b"]) -> Manifold:
    """One half in print pose: outer flange face on z=0, core/sleeve toward +Z."""
    d = dims(cfg)
    if half == "a":
        return flange_disc(d) + core_tube(d) - lock_cuts(d)
    if half == "b":
        return flange_disc(d) + sleeve(d) + lugs(d)
    raise ValueError(f"unknown half {half!r}")


def assembled(cfg: SpoolConfig) -> tuple[Manifold, Manifold]:
    """Both halves in assembled pose, B twisted into the locked position."""
    a = build_half(cfg, "a")
    b = (
        build_half(cfg, "b")
        .rotate((180, 0, 0))
        .translate((0, 0, cfg.overall_width))
        .rotate((0, 0, TWIST_DEG))
    )
    return a, b
