"""Assemble the spool halves."""

from __future__ import annotations

from typing import Literal

from manifold3d import Manifold

from ..config import SpoolConfig
from .body import core_tube, flange_disc, sleeve
from .dims import dims
from .features import apply_features, core_pockets, layout
from .lock import TWIST_DEG, lock_cuts, lugs


def build_half(cfg: SpoolConfig, half: Literal["a", "b"]) -> Manifold:
    """One half in print pose: outer flange face on z=0, core/sleeve toward +Z."""
    d = dims(cfg)
    if half == "a":
        body = flange_disc(d) + core_tube(d) - lock_cuts(d)
        if cfg.lightweight:
            body -= core_pockets(d)
    elif half == "b":
        body = flange_disc(d) + sleeve(d) + lugs(d)
    else:
        raise ValueError(f"unknown half {half!r}")
    return apply_features(body, cfg, d, layout(cfg, d))


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
