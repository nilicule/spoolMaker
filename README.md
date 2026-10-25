# Spool Maker

A designer for two-part, twist-lock, Bambu AMS-compatible filament spools that hold refill coils. Tweak the parameters, watch a live 3D preview, and download print-ready STL or 3MF files.

## Features

- Two halves that twist-lock together around a refill coil, sized for AMS-compatible dimensions (200 mm flange, 53 mm bore by default)
- Defaults: honeycomb pattern in lightweight mode, with the label panel and the remaining-filament gauge off (turn them on under Personalize and Extras)
- Thin-walled tube core (3 mm) with a short bore collar on each flange, printable without supports
- Refill presets (Bambu Lab refill, custom coil dimensions) with coil clearance and lock clearance settings
- Flange patterns: honeycomb, spokes, voronoi, holes, isogrid, windows (large open sectors between radial ribs), or none, with density and seed
- Lightweight mode that thins the flange webs and narrows their solid rim and hub ring
- Engraved label outline with custom text
- Filament gauge ticks by material
- Filament clip hole pairs with an adjustable hole size (weave the filament end down through one hole and back up the other) and an optional NFC tag pocket (for tracking with a phone; the AMS does not read it)
- Live three.js preview with an animated exploded view, a slicer-like filament estimate, fit stats, STL per half or a combined 3MF
- "Open in Bambu Studio": a Bambu Studio project with each half on its own plate

## Run

```
uv sync && uv run spoolmaker
```

Then open http://127.0.0.1:5000. Set the `PORT` environment variable to use another port.

## Deploying

To run Spool Maker on a server (container image, reverse proxy, hosting under a sub-path like `/spool/`), see [DEPLOYING.md](DEPLOYING.md).

## Tests

```
uv run pytest
```

Tests that slice with a locally installed Bambu Studio (macOS, slow) are skipped unless you opt in:

```
SPOOLMAKER_BAMBU_LIVE=1 uv run pytest
```

## Printing notes

- Print each half flange-down, with no supports. The STLs are already in print pose.
- The 200 mm flange needs a bed of at least 200 mm. It will not fit on an A1 mini.
- If the halves are too tight or too loose when twisting together, adjust the twist-lock clearance setting and reprint.
- The Bambu refill preset dimensions are community-sourced, not from an official spec. Measure your coil and use the custom preset if they differ.

## License

Spool Maker is licensed under the GNU Affero General Public License v3.0 only (AGPL-3.0-only); see [LICENSE](LICENSE).

The Bambu Studio project settings in `src/spoolmaker/bambu/templates/` are derived from the Bambu Studio 02.08.04.61 system profiles, which are AGPL-3.0 licensed ([bambulab/BambuStudio](https://github.com/bambulab/BambuStudio)).
