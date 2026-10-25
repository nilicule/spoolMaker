"""Assemble the spool halves."""

from __future__ import annotations

from typing import Literal

from manifold3d import Manifold

from ..config import SpoolConfig
from .body import core_a, core_b, flange_disc
from .dims import dims
from .features import apply_features, core_pockets_a, core_pockets_b, layout
from .lock import TWIST_DEG, lock_cuts, lugs


def build_half(cfg: SpoolConfig, half: Literal["a", "b"]) -> Manifold:
    """One half in print pose: outer flange face on z=0, core toward +Z.

    Half A is female (core ends in the lock socket), half B male (shorter core + sleeve
    with lugs); both are roughly half the spool's width tall."""
    d = dims(cfg)
    if half == "a":
        body = flange_disc(d) + core_a(d) - lock_cuts(d)
        if cfg.lightweight:
            body -= core_pockets_a(d)
    elif half == "b":
        body = flange_disc(d) + core_b(d) + lugs(d)
        if cfg.lightweight:
            body -= core_pockets_b(d)
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
