"""Spool configuration model: defaults, ranges, query-string parsing, validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields

from .bambu import DEFAULT_PRINTER, PRINTERS

OD_RANGE = (197.0, 201.0)
WIDTH_RANGE = (50.0, 68.0)
BORE_RANGE = (53.0, 58.0)
RIM_WIDTH = 7.0  # solid outer rim of each flange
RIM_WIDTH_LIGHT = 6.0  # narrower rim in lightweight mode
MAX_TEXT = 24
PATTERNS = ("none", "honeycomb", "spokes", "voronoi", "holes", "isogrid", "windows")
MATERIALS = ("PLA", "PETG", "ABS", "ASA", "TPU", "PC")
TAG_SIZES = (20, 25, 30)
BORE_MARGIN = 12.0
MIN_LOCK_WALL = 2.0  # socket wall left behind half A's bayonet channels and pocket


@dataclass(frozen=True)
class RefillPreset:
    key: str
    name: str
    inner_diameter: float
    width: float
    verified: bool


PRESETS: dict[str, RefillPreset] = {
    # Placeholder dimensions; Task 10 confirms them.
    "bambu": RefillPreset("bambu", "Bambu Lab refill", 82.0, 60.0, False),
    "custom": RefillPreset("custom", "Custom", 82.0, 60.0, False),
}


@dataclass(frozen=True)
class SpoolConfig:
    outer_diameter: float = 200.0
    bore_diameter: float = 53.0
    refill: str = "bambu"
    coil_inner_diameter: float = 82.0
    coil_width: float = 60.0
    coil_clearance: float = 0.6
    flange_thickness: float = 3.0
    pattern: str = "honeycomb"
    pattern_density: float = 0.5
    pattern_seed: int = 1
    lightweight: bool = True
    label: bool = False
    label_width: float = 60.0
    label_height: float = 18.0
    text: str = ""
    gauge: bool = False
    gauge_material: str = "PLA"
    clip_holes: int = 4  # filament clip hole pairs (two holes each)
    clip_hole_diameter: float = 2.6
    tag_pocket: bool = False
    tag_diameter: int = 25
    lock_clearance: float = 0.3
    print_material: str = "PLA"
    bambu_printer: str = DEFAULT_PRINTER

    @property
    def inner_width(self) -> float:
        return self.coil_width + self.coil_clearance

    @property
    def overall_width(self) -> float:
        return self.inner_width + 2 * self.flange_thickness


RANGES: dict[str, tuple[float, float]] = {
    "outer_diameter": OD_RANGE,
    "bore_diameter": BORE_RANGE,
    "coil_inner_diameter": (40.0, 150.0),
    "coil_width": (30.0, 68.0),
    "coil_clearance": (0.2, 2.0),
    "flange_thickness": (2.0, 5.0),
    "pattern_density": (0.0, 1.0),
    "pattern_seed": (0, 9999),
    "label_width": (20.0, 80.0),
    "label_height": (10.0, 30.0),
    "clip_holes": (0, 8),
    # 2.9 leaves >= 1.5 mm to both edges of the 6 mm lightweight rim, measured to the
    # faceted outer edge (3.0 would leave ~1.47 mm there).
    "clip_hole_diameter": (2.0, 2.9),
    "lock_clearance": (0.15, 0.6),
}

CHOICES: dict[str, tuple] = {
    "refill": tuple(PRESETS),
    "pattern": PATTERNS,
    "gauge_material": MATERIALS,
    "print_material": MATERIALS,
    "tag_diameter": TAG_SIZES,
    "bambu_printer": tuple(PRINTERS),
}

_DEFAULTS = SpoolConfig()
_TRUE = {"1", "true", "on"}
_FALSE = {"0", "false", "off", ""}


def is_true(raw: str | None) -> bool:
    """Query-string boolean: true only for 1/true/on."""
    return raw is not None and raw.strip().lower() in _TRUE


def _parse_field(name: str, default, raw: str):
    """Parse one raw string; return the default on garbage."""
    try:
        if isinstance(default, bool):
            v = raw.strip().lower()
            if v in _TRUE:
                return True
            if v in _FALSE:
                return False
            return default
        if name == "text":
            return raw[:MAX_TEXT]
        if name in CHOICES:
            choices = CHOICES[name]
            value = type(choices[0])(raw)
            return value if value in choices else default
        if isinstance(default, int):
            value = int(float(raw))
        else:
            value = float(raw)
            if value != value or value in (float("inf"), float("-inf")):
                return default
        lo, hi = RANGES[name]
        return type(default)(min(max(value, lo), hi))
    except (ValueError, TypeError, OverflowError):
        return default


def from_query(args: Mapping[str, str]) -> SpoolConfig:
    values = {}
    for f in fields(SpoolConfig):
        if f.name in args:
            values[f.name] = _parse_field(f.name, f.default, str(args[f.name]))
    if values.get("refill", _DEFAULTS.refill) != "custom":
        preset = PRESETS[values.get("refill", _DEFAULTS.refill)]
        values["coil_inner_diameter"] = preset.inner_diameter
        values["coil_width"] = preset.width
    return SpoolConfig(**values)


def to_query(cfg: SpoolConfig) -> dict[str, str]:
    out = {}
    for f in fields(SpoolConfig):
        v = getattr(cfg, f.name)
        if v != f.default:
            out[f.name] = ("1" if v else "0") if isinstance(v, bool) else str(v)
    return out


def validate(cfg: SpoolConfig) -> list[str]:
    from .filament import coil_fits

    errors = []
    lo, hi = WIDTH_RANGE
    if not lo <= cfg.overall_width <= hi:
        errors.append(
            f"Overall width {cfg.overall_width:.1f} mm must be between {lo:g} and {hi:g} mm "
            "to fit the AMS."
        )
    need = cfg.bore_diameter + BORE_MARGIN
    if cfg.coil_inner_diameter < need:
        errors.append(
            f"Coil inner diameter must be at least {need:g} mm for this bore."
        )
    from .geometry.dims import dims

    d = dims(cfg)
    # Half A's socket wall keeps MIN_LOCK_WALL behind the channels by construction; the
    # socket wall, sleeve clearance and B's sleeve must then fit outside the bore.
    room = d.r_core_out - d.r_bore
    need = d.r_core_out - d.r_sleeve_in
    if d.r_sleeve_in < d.r_bore - 1e-9:
        errors.append(
            f"The twist-lock needs {need:.1f} mm between the bore and the core but only "
            f"{room:.1f} mm is available (wall behind the lock at least {MIN_LOCK_WALL:g} mm); "
            "increase the coil inner diameter or reduce the bore, coil clearance or "
            "twist-lock clearance."
        )
    if not coil_fits(cfg):
        errors.append(
            f"1 kg of {cfg.gauge_material} does not fit inside the flanges for this coil; "
            "reduce the coil inner diameter or increase its width."
        )
    if cfg.tag_pocket:
        from .geometry.features import tag_fits

        if not tag_fits(cfg, d):
            errors.append(
                f"A {cfg.tag_diameter} mm NFC tag pocket does not fit between the core and "
                "the rim; choose a smaller tag or a smaller coil inner diameter."
            )
    return errors


def config_schema() -> dict:
    from .geometry.lock import TWIST_DEG

    fdefs = {}
    for f in fields(SpoolConfig):
        d = f.default
        entry: dict = {
            "type": "bool" if isinstance(d, bool) else "int" if isinstance(d, int)
            else "float" if isinstance(d, float) else "string",
            "default": d,
        }
        if f.name in RANGES:
            entry["min"], entry["max"] = RANGES[f.name]
        if f.name in CHOICES:
            entry["type"] = "choice"
            entry["choices"] = list(CHOICES[f.name])
        if f.name == "text":
            entry["max_length"] = MAX_TEXT
        fdefs[f.name] = entry
    return {
        "fields": fdefs,
        "presets": {
            k: {"name": p.name, "inner_diameter": p.inner_diameter, "width": p.width,
                "verified": p.verified}
            for k, p in PRESETS.items()
        },
        "bambu_printers": {k: {"name": p.name, "process": p.process, "filament": p.filament}
                           for k, p in PRINTERS.items()},
        "limits": {"od": list(OD_RANGE), "width": list(WIDTH_RANGE), "bore": list(BORE_RANGE),
                   "rim_width": RIM_WIDTH, "rim_width_light": RIM_WIDTH_LIGHT,
                   "max_text": MAX_TEXT,
                   "twist_deg": TWIST_DEG},
    }
