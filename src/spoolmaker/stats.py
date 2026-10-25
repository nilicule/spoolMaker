"""Weight, width and gauge statistics for a spool configuration.

estimate_g is the slicer-like filament estimate (see estimate.py) for the selected Bambu
printer's profile; weight_g is the solid (100% infill) weight, kept for comparison."""

from __future__ import annotations

from .cache import extruded_mm3_for, half
from .config import SpoolConfig
from .estimate import bambu_profile
from .filament import DENSITY, gauge_ticks


def stats(cfg: SpoolConfig) -> dict:
    density = DENSITY[cfg.print_material]
    w = {h: round(half(cfg, h).volume() / 1000 * density, 1) for h in ("a", "b")}
    w["total"] = round(w["a"] + w["b"], 1)
    profile = bambu_profile(cfg.bambu_printer)
    profile_filament = profile.filament.split(" @")[0]
    if cfg.print_material == "PLA":  # the profile's own filament (Bambu PLA Basic)
        rho, filament = profile.filament_density, profile_filament
    else:  # sliced with the PLA profile, weighed at the chosen material's density
        rho = DENSITY[cfg.print_material]
        filament = (f"{profile_filament} profile, weighed as {cfg.print_material} "
                    f"({rho:g} g/cm\u00b3)")
    est = {h: round(extruded_mm3_for(cfg, h) / 1000 * rho * profile.flow_ratio, 1)
           for h in ("a", "b")}
    est["total"] = round(est["a"] + est["b"], 1)
    flange = f"{cfg.outer_diameter:g}"
    return {
        "estimate_g": est,
        "estimate_note": f"{profile.note()} \u00b7 {filament}",
        "weight_g": w,
        "weight_note": f"solid (100% infill) estimate in {cfg.print_material}",
        "overall_width": cfg.overall_width,
        "gauge": [{"grams": g, "radius": r} for g, r in gauge_ticks(cfg)],
        "bed_note": f"Flange is {flange} mm \u2014 needs a bed \u2265 {flange} mm (not A1 mini).",
    }
