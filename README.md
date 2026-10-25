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
- Filament clip hole pairs (weave the filament end down through one hole and back up the other) and an optional NFC tag pocket (for tracking with a phone; the AMS does not read it)
- Live three.js preview with an animated exploded view, a slicer-like filament estimate, fit stats, STL per half or a combined 3MF
- "Open in Bambu Studio": a Bambu Studio project with each half on its own plate

## Run

```
uv sync && uv run spoolmaker
```

Then open http://127.0.0.1:5000. Set the `PORT` environment variable to use another port.

## Deploying

The image runs the app under gunicorn on port 8000 as a non-root user. Commands are shown for podman; docker takes the same arguments (`docker build`, `docker run`, `docker compose`).

```
podman build --format docker -t spoolmaker .
podman run -d --name spoolmaker -p 127.0.0.1:8000:8000 --restart unless-stopped spoolmaker
```

`--format docker` keeps the image's `HEALTHCHECK` (it polls `/healthz`); podman's default OCI format drops it with a warning. Docker builds need no flag. Rootless podman can publish port 8000 (or any port from 1024 up) without extra setup. Or with compose (`podman compose` uses docker-compose or podman-compose, whichever is installed):

```
podman compose up -d --build
```

Settings (environment variables):

- `WEB_CONCURRENCY` - gunicorn workers (default 2). Each worker keeps its own cache of built models.
- `PORT` - listen port inside the container (default 8000).
- `TRUST_PROXY` - `1` (the image default) trusts one proxy hop's `X-Forwarded-For`, `-Proto`, `-Host` and `-Prefix` headers. Only safe when the app is reachable solely through that proxy, which must set or strip these headers; keep the published port bound to `127.0.0.1` (as above) and set `TRUST_PROXY=0` if clients can reach the app directly.
- `BASE_PATH` - see below.

### Under a sub-path (e.g. n2g.dev/spool/)

Every URL in the page is relative to a `<base href>` the server fills in, so the app works at `/` or under any prefix. The usual setup is a proxy that strips the prefix and sends `X-Forwarded-Prefix`. nginx:

```
location = /spool { return 301 /spool/; }
location /spool/ {
    proxy_pass http://127.0.0.1:8000/;      # trailing slash strips /spool
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /spool;
    client_max_body_size 1m;
}
```

Caddy:

```
n2g.dev {
    redir /spool /spool/
    handle_path /spool/* {
        reverse_proxy 127.0.0.1:8000 {
            header_up X-Forwarded-Prefix /spool
        }
    }
}
```

Redirect `/spool` to `/spool/` as shown. The page also loads without the slash (the `<base>` tag pins its URLs), but the redirect keeps addresses consistent.

If the proxy forwards the full path instead (`/spool/api/...` reaches the app unchanged), set `BASE_PATH=/spool` (for example `podman run -e BASE_PATH=/spool ...`); the app then serves under `/spool/` and still answers `/healthz` at the root.

There is no rate limiting in the app. Each request's CPU time is bounded (a model build takes well under a second), but if the site is public, add limits at the proxy, e.g. nginx `limit_req_zone $binary_remote_addr zone=spool:10m rate=5r/s;` with `limit_req zone=spool burst=20;` in the location.

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

## Filament estimate

The stats bar shows how much filament each half takes, estimated the way a slicer would print it with the selected Bambu printer's "0.20mm Standard" profile and Bambu PLA Basic (2 walls, 15% grid infill, 5 top and 3 bottom shell layers). Each half is cut into 0.2 mm layers and every layer is split into walls, solid infill (top, bottom and vertical shells, and pockets too small for sparse infill), internal bridges and sparse infill with its anchors; all factors come from the profile (`src/spoolmaker/estimate.py`). With another print material the same volume is weighed at that material's density. The API's `/api/stats` also reports the solid (100% infill) weight as `weight_g`.

The estimate is checked against what Bambu Studio's own slicer reports for the app's Bambu project, for a matrix of designs on the A1 and H2D: it stays within 6% (currently about 2%). The reference numbers are in `tests/fixtures/bambu_grams.json`; to regenerate them after a Bambu Studio or profile update (macOS, Bambu Studio installed; slices with the CLI, takes a few minutes):

```
uv run python scripts/calibrate_estimate.py [--app /Applications/BambuStudio.app] [--only default@a1]
```

## Open in Bambu Studio

The "Open in Bambu Studio" button downloads a Bambu Studio project 3MF with half A on plate 1 and half B on plate 2. Open the file (double-click, or File > Open Project) to launch Bambu Studio with both plates ready. A web page cannot start Bambu Studio directly, so this is a download. The project needs Bambu Studio 2.x; an older version may warn that the file comes from a newer version (update Bambu Studio, or continue anyway).

The project carries the system settings of the printer chosen under Print > Bambu printer (its "0.20mm Standard" process with Bambu PLA Basic), so opening it switches Bambu Studio to those presets; change them as usual after opening. Printers with a bed under 205 mm (A1 mini) are not offered. "Download both (3MF)" stays available as a plain 3MF for any slicer.

The per-printer settings live in `src/spoolmaker/bambu/templates/` with an index in `src/spoolmaker/bambu/printers.json`. They are generated by the Bambu Studio CLI from its bundled profiles; regenerate them after a Bambu Studio update (macOS, Bambu Studio installed):

```
uv run python scripts/make_bambu_templates.py [--app /Applications/BambuStudio.app]
```

## Project layout

- `src/spoolmaker/app.py` - Flask app and routes
- `Dockerfile`, `compose.yaml` - production image (gunicorn)
- `src/spoolmaker/config.py` - configuration model, presets, validation
- `src/spoolmaker/geometry/` - manifold3d geometry (body, lock, patterns, text, features)
- `src/spoolmaker/export.py` - STL and 3MF export
- `src/spoolmaker/bambu/` - Bambu Studio project export and per-printer settings templates
- `scripts/make_bambu_templates.py` - regenerates those templates (dev-only)
- `src/spoolmaker/filament.py`, `stats.py` - mass and fit calculations
- `src/spoolmaker/estimate.py` - slicer-like filament estimate
- `scripts/calibrate_estimate.py` - re-slices the estimate's reference designs with Bambu Studio (dev-only)
- `src/spoolmaker/static/` - web UI and three.js preview; `scripts/make_favicons.py` renders its PNG favicons from `favicon.svg` (dev-only, needs rsvg-convert)
- `tests/` - pytest suite, including printability checks

## License

Spool Maker is licensed under the GNU Affero General Public License v3.0 only (AGPL-3.0-only); see [LICENSE](LICENSE).

The Bambu Studio project settings in `src/spoolmaker/bambu/templates/` are derived from the Bambu Studio 02.08.04.61 system profiles, which are AGPL-3.0 licensed ([bambulab/BambuStudio](https://github.com/bambulab/BambuStudio)).
