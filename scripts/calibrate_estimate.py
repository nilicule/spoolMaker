"""Regenerate tests/fixtures/bambu_grams.json: what Bambu Studio's slicer says each half weighs.

For a matrix of spool configs and printers, export the app's own Bambu Studio project, slice
it with the Bambu Studio CLI and record the filament used per plate (plate 1 = half A,
plate 2 = half B). tests/test_estimate.py checks spoolmaker.estimate against these numbers.
Dev-only (macOS, Bambu Studio installed); the app never imports this script.

    uv run python scripts/calibrate_estimate.py [--app /Applications/BambuStudio.app] [--only CASE]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "bambu_grams.json"
sys.path.insert(0, str(ROOT / "src"))

from spoolmaker import cache  # noqa: E402
from spoolmaker.config import from_query, validate  # noqa: E402

PRINTERS = ("a1", "h2d")
CASES: dict[str, dict[str, str]] = {
    "default": {},
    "classic": {"lightweight": "0", "label": "1", "gauge": "1"},
    "windows": {"pattern": "windows", "pattern_density": "1"},
    "voronoi_text_tag": {"pattern": "voronoi", "pattern_density": "0.8", "label": "1",
                         "text": "PLA Basic", "tag_pocket": "1"},
    "spokes": {"pattern": "spokes"},
    "coil_70_bore_58": {"refill": "custom", "coil_inner_diameter": "70.8",
                        "bore_diameter": "58"},
    "flange_2": {"flange_thickness": "2"},
    "flange_5": {"flange_thickness": "5", "refill": "custom", "coil_width": "56"},
}


def slice_case(cli: Path, query: dict[str, str]) -> tuple[float, float]:
    cfg = from_query(query)
    errors = validate(cfg)
    if errors:
        raise SystemExit(f"invalid config {query}: {errors}")
    with tempfile.TemporaryDirectory(prefix="spool-calib-") as tmp:
        work = Path(tmp)
        project = work / "spool.3mf"
        project.write_bytes(cache.bambu_project(cfg))  # the real export, as downloaded
        out = work / "out"
        out.mkdir()
        # The CLI also writes a result.json into its cwd: keep that inside the temp dir.
        r = subprocess.run([str(cli), "--slice", "0", "--outputdir", str(out), str(project)],
                           cwd=work, capture_output=True, text=True, timeout=900)
        result = out / "result.json"
        if r.returncode != 0 or not result.exists():
            raise SystemExit(f"slicing failed ({r.returncode}):\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
        plates = json.loads(result.read_text())["sliced_plates"]
        grams = {p["id"]: sum(f["total_used_g"] for f in p["filaments"]) for p in plates}
        return round(grams[1], 2), round(grams[2], 2)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--app", type=Path, default=Path("/Applications/BambuStudio.app"))
    ap.add_argument("--only", action="append", help="re-slice only these case keys")
    args = ap.parse_args()
    cli = args.app / "Contents" / "MacOS" / "BambuStudio"
    if not cli.exists():
        raise SystemExit(f"Bambu Studio CLI not found at {cli}")

    data = json.loads(FIXTURE.read_text()) if FIXTURE.exists() else {}
    for printer in PRINTERS:
        for name, q in CASES.items():
            key = f"{name}@{printer}"
            if args.only and key not in args.only and name not in args.only:
                continue
            query = {**q, "bambu_printer": printer}
            a, b = slice_case(cli, query)
            data[key] = {"printer": printer, "query": query, "a_g": a, "b_g": b}
            print(f"{key:28s} A {a:7.2f} g  B {b:7.2f} g", flush=True)
            FIXTURE.parent.mkdir(parents=True, exist_ok=True)
            FIXTURE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
