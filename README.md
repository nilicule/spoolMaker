# Spool Maker

A designer for two-part, twist-lock, Bambu AMS-compatible filament spools that hold refill coils. Tweak the parameters, watch a live 3D preview, and download print-ready STL or 3MF files.

## Features

- Two halves that twist-lock together around a refill coil, sized for AMS-compatible dimensions (200 mm flange, 53 mm bore by default)
- Thin-walled tube core (3 mm) with a short bore collar on each flange, printable without supports
- Refill presets (Bambu Lab refill, custom coil dimensions) with coil clearance and lock clearance settings
- Flange patterns: honeycomb, spokes, voronoi, holes, isogrid, or none, with density and seed
- Lightweight mode that thins the flange webs and narrows their solid rim and hub ring
- Engraved label outline with custom text
- Filament gauge ticks by material
- Clip holes and an optional NFC tag pocket (for tracking with a phone; the AMS does not read it)
- Live three.js preview, mass and fit stats, STL per half or a combined 3MF

## Run

```
uv sync && uv run spoolmaker
```

Then open http://127.0.0.1:5000. Set the `PORT` environment variable to use another port.

## Tests

```
uv run pytest
```

## Printing notes

- Print each half flange-down, with no supports. The STLs are already in print pose.
- The 200 mm flange needs a bed of at least 200 mm. It will not fit on an A1 mini.
- If the halves are too tight or too loose when twisting together, adjust the twist-lock clearance setting and reprint.
- The Bambu refill preset dimensions are community-sourced, not from an official spec. Measure your coil and use the custom preset if they differ.

## Project layout

- `src/spoolmaker/app.py` - Flask app and routes
- `src/spoolmaker/config.py` - configuration model, presets, validation
- `src/spoolmaker/geometry/` - manifold3d geometry (body, lock, patterns, text, features)
- `src/spoolmaker/export.py` - STL and 3MF export
- `src/spoolmaker/filament.py`, `stats.py` - mass and fit calculations
- `src/spoolmaker/static/` - web UI and three.js preview
- `tests/` - pytest suite, including printability checks
