"""Filament capacity math: how much radius a given mass of filament occupies."""

from __future__ import annotations

import math

from .config import SpoolConfig

DENSITY: dict[str, float] = {
    "PLA": 1.24, "PETG": 1.27, "ABS": 1.04, "ASA": 1.07, "TPU": 1.21, "PC": 1.20,
}  # g/cm^3
PACKING = 0.85
RIM_MARGIN = 5.0  # mm filament must stay inside the flange edge


def mass_between(r_inner_mm: float, r_outer_mm: float, width_mm: float, material: str) -> float:
    """Grams of wound filament between two radii."""
    return (DENSITY[material] * PACKING * math.pi
            * (r_outer_mm**2 - r_inner_mm**2) * width_mm / 1000)


def radius_for_mass(mass_g: float, r_core_mm: float, width_mm: float, material: str) -> float:
    """Outer radius reached by mass_g of filament wound on a core of radius r_core_mm."""
    k = DENSITY[material] * PACKING * math.pi * width_mm / 1000
    return math.sqrt(r_core_mm**2 + mass_g / k)


def coil_fits(cfg: SpoolConfig) -> bool:
    r = radius_for_mass(1000, cfg.coil_inner_diameter / 2, cfg.coil_width, cfg.gauge_material)
    return r <= cfg.outer_diameter / 2 - RIM_MARGIN


def gauge_ticks(cfg: SpoolConfig) -> list[tuple[int, float]]:
    """(grams_remaining, radius_mm) for 1000/750/500/250 g, measured from the core."""
    r_core = cfg.coil_inner_diameter / 2
    return [(g, radius_for_mass(g, r_core, cfg.coil_width, cfg.gauge_material))
            for g in (1000, 750, 500, 250)]
