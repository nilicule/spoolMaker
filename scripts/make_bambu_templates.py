"""Regenerate the Bambu Studio project templates (dev-only; needs Bambu Studio installed).

For every Bambu Lab printer with a 0.4 mm nozzle and a bed of at least 205 mm in X and Y,
resolve its system printer, "0.20mm Standard" process and "Bambu PLA Basic" filament
profiles (following `inherits`), let the Bambu Studio CLI build a two-plate project from
two dummy boxes, and keep the resulting Metadata/project_settings.config as
src/spoolmaker/bambu/templates/<key>.json plus an index src/spoolmaker/bambu/printers.json.

    uv run python scripts/make_bambu_templates.py [--app /Applications/BambuStudio.app]

The app never imports this script; it only reads the generated JSON.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from manifold3d import Manifold

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "spoolmaker" / "bambu"
MIN_BED = 205.0
MIN_PRINTERS = 10  # fewer means profiles or the CLI changed: fail rather than ship a gap
REQUIRED = ("a1",)  # the app's default printer
PLATE_GAP = 1.2  # Bambu Studio lays plates out at bed size x 1.2
CORE_NS = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"

sys.path.insert(0, str(ROOT / "src"))
from spoolmaker.export import to_stl  # noqa: E402


class Profiles:
    def __init__(self, base: Path):
        self.base = base
        index = json.loads((base.parent / "BBL.json").read_text())
        self.paths: dict[str, dict[str, Path]] = {}
        for kind, key in (("machine", "machine_list"), ("process", "process_list"),
                          ("filament", "filament_list"), ("model", "machine_model_list")):
            self.paths[kind] = {e["name"]: base / e["sub_path"] for e in index[key]}
        self.version = index["version"]

    def raw(self, kind: str, name: str) -> dict:
        return json.loads(self.paths[kind][name].read_text())

    def resolve(self, kind: str, name: str) -> dict:
        data = self.raw(kind, name)
        parent = data.pop("inherits", None)
        if parent:
            merged = self.resolve(kind, parent)
            merged.update(data)
            data = merged
        return data

    def system(self, kind: str, name: str) -> dict:
        data = self.resolve(kind, name)
        data.update(name=name, **{"from": "system", "instantiation": "true"})
        return data


def bed_rect(area: list[str]) -> list[float]:
    pts = [tuple(float(v) for v in p.split("x")) for p in area]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [min(xs), min(ys), max(xs), max(ys)]


def key_for(model: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", model.removeprefix("Bambu Lab ").lower()).strip("-")


def pick(profiles: Profiles, kind: str, prefix: str, machine: str) -> str | None:
    for name in sorted(profiles.paths[kind]):
        if not name.startswith(prefix):
            continue
        data = profiles.resolve(kind, name)
        if data.get("instantiation") == "true" and machine in data.get("compatible_printers", []):
            return name
    return None


def bambu_version(app: Path) -> str:
    plist = (app / "Contents" / "Info.plist").read_text()
    m = re.search(r"<key>CFBundleShortVersionString</key>\s*<string>([^<]+)</string>", plist)
    return m.group(1) if m else "unknown"


def build_template(cli: Path, work: Path, machine: dict, process: dict, filament: dict,
                   bed: list[float]) -> tuple[dict, str, list[tuple[float, float]]]:
    w, d = bed[2] - bed[0], bed[3] - bed[1]
    # Boxes too big to share a plate, so --arrange puts one on each plate.
    box = to_stl(Manifold.cube((0.7 * w, 0.7 * d, 2.0), center=True))
    files = {}
    for n, data in (("m", machine), ("p", process), ("f", filament)):
        files[n] = work / f"{n}.json"
        files[n].write_text(json.dumps(data, indent=2))
    stls = [work / "a.stl", work / "b.stl"]
    for s in stls:
        s.write_bytes(box)
    out = work / "out.3mf"
    out.unlink(missing_ok=True)
    cmd = [str(cli), "--arrange", "1", "--load-settings", f"{files['m']};{files['p']}",
           "--load-filaments", str(files["f"]), "--export-3mf", str(out), *map(str, stls)]
    r = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=300)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"Bambu Studio CLI failed ({r.returncode}): {r.stderr[-2000:]}")
    z = zipfile.ZipFile(io.BytesIO(out.read_bytes()))
    settings = json.loads(z.read("Metadata/project_settings.config"))
    root = ET.fromstring(z.read("3D/3dmodel.model"))
    app = next(m.text for m in root.iter(f"{CORE_NS}metadata") if m.get("name") == "Application")
    items = []
    for it in root.iter(f"{CORE_NS}item"):
        t = [float(v) for v in it.get("transform").split()]
        items.append((t[9], t[10]))
    return settings, app, items


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--app", type=Path, default=Path("/Applications/BambuStudio.app"))
    args = ap.parse_args()
    cli = args.app / "Contents" / "MacOS" / "BambuStudio"
    profiles = Profiles(args.app / "Contents" / "Resources" / "profiles" / "BBL")

    # Build everything into a staging dir and swap it in only once the whole run succeeded,
    # so a failure never leaves half-deleted templates behind.
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bambu-templates-", dir=OUT) as staging:
        index = generate(cli, profiles, Path(staging))
        missing = [k for k in REQUIRED if k not in index]
        if missing or len(index) < MIN_PRINTERS:
            raise SystemExit(f"only {len(index)} printers generated (need {MIN_PRINTERS}), "
                             f"missing {missing}; templates left unchanged")
        (Path(staging) / "printers.json").write_text(json.dumps(index, indent=2) + "\n")
        old = OUT / "templates.old"
        shutil.rmtree(old, ignore_errors=True)
        if (OUT / "templates").exists():
            (OUT / "templates").rename(old)
        (Path(staging) / "templates").rename(OUT / "templates")
        (Path(staging) / "printers.json").replace(OUT / "printers.json")
        shutil.rmtree(old, ignore_errors=True)
    print(f"{len(index)} printers, Bambu Studio {bambu_version(args.app)}, "
          f"profiles {profiles.version}")


def generate(cli: Path, profiles: Profiles, staging: Path) -> dict:
    """Write staging/templates/<key>.json for every eligible printer; return the index."""
    (staging / "templates").mkdir()
    index = {}
    for name in sorted(profiles.paths["machine"]):
        if not name.endswith(" 0.4 nozzle"):
            continue
        machine = profiles.system("machine", name)
        if machine.get("printer_model", "").find("Bambu Lab") != 0:
            continue
        bed = bed_rect(machine["printable_area"])
        if bed[2] - bed[0] < MIN_BED or bed[3] - bed[1] < MIN_BED:
            print(f"skip {name}: bed {bed}")
            continue
        model = machine["printer_model"]
        proc_name = pick(profiles, "process", "0.20mm Standard @BBL", name)
        fil_name = (pick(profiles, "filament", "Bambu PLA Basic @BBL", name)
                    or pick(profiles, "filament", "Generic PLA @BBL", name))
        if not proc_name or not fil_name:
            print(f"skip {name}: process={proc_name} filament={fil_name}")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            settings, app, items = build_template(
                cli, Path(tmp), machine, profiles.system("process", proc_name),
                profiles.system("filament", fil_name), bed)
        if settings.get("printer_model") != model:
            raise RuntimeError(f"{name}: template printer_model {settings.get('printer_model')}")
        tbed = bed_rect(settings["printable_area"])
        if tbed != bed:
            raise RuntimeError(f"{name}: template bed {tbed} != profile bed {bed}")
        # Check the plate layout the exporter assumes against what the CLI did: plate 2 one
        # stride (bed width x 1.2) right of plate 1. Keep where arrange centred the item on
        # plate 1 (dual-nozzle beds centre on the region both nozzles reach, not the bed).
        w = bed[2] - bed[0]
        items.sort()
        if (len(items) != 2 or abs(items[1][0] - items[0][0] - w * PLATE_GAP) > 0.5
                or abs(items[1][1] - items[0][1]) > 0.5
                or not (bed[0] < items[0][0] < bed[2] and bed[1] < items[0][1] < bed[3])):
            raise RuntimeError(f"{name}: unexpected arranged items {items}")
        center = [round(items[0][0], 3), round(items[0][1], 3)]
        key = key_for(model)
        (staging / "templates" / f"{key}.json").write_text(json.dumps(settings, indent=4) + "\n")
        index[key] = {"name": model, "printer_model": model, "bed": bed, "center": center,
                      "app_version": app.removeprefix("BambuStudio-"),
                      "process": proc_name, "filament": fil_name}
        print(f"{key}: {model} bed {bed} centre {center} {proc_name} / {fil_name}")
    return index


if __name__ == "__main__":
    main()
