"""Weight, width and gauge statistics for a spool configuration."""

from __future__ import annotations

from .config import SpoolConfig
from .filament import DENSITY, gauge_ticks


def stats(cfg: SpoolConfig) -> dict:
    from .app import _half  # shared, cached geometry

    density = DENSITY[cfg.print_material]
    w = {h: round(_half(cfg, h).volume() / 1000 * density, 1) for h in ("a", "b")}
    w["total"] = round(w["a"] + w["b"], 1)
    flange = f"{cfg.outer_diameter:g}"
    return {
        "weight_g": w,
        "weight_note": f"solid (100% infill) estimate in {cfg.print_material}",
        "overall_width": cfg.overall_width,
        "gauge": [{"grams": g, "radius": r} for g, r in gauge_ticks(cfg)],
        "bed_note": f"Flange is {flange} mm \u2014 needs a bed \u2265 {flange} mm (not A1 mini).",
    }
