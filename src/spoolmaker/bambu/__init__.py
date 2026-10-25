"""Bambu Studio project 3MF: one part per plate, with a printer's default project settings.

Bambu Studio only restores plates from a 3MF that it recognises as one of its own projects:
an `Application` of "BambuStudio-<version>" and a Metadata/project_settings.config whose
printer_model is a Bambu Lab printer. The settings come from templates produced by
scripts/make_bambu_templates.py (Bambu Studio CLI output); the layout mirrors a project the
CLI wrote and Bambu Studio opened with each half on its own plate.
"""

from __future__ import annotations

import io
import json
import math
import uuid
import zipfile
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path
from xml.sax.saxutils import quoteattr

from manifold3d import Manifold

from ..export import mesh_xml

DATA_DIR = Path(__file__).parent
DEFAULT_PRINTER = "a1"
PLATE_GAP = 1.2  # Bambu Studio's plate stride is the bed size x 1.2
# Nozzle-changer printers whose extruder_nozzle_stats format we have not confirmed (the
# H2C's right extruder draws from a nozzle rack): left as the template has them.
NOZZLE_STATS_UNCONFIRMED = frozenset({"h2c"})


@dataclass(frozen=True)
class Printer:
    key: str
    name: str
    printer_model: str
    bed: tuple[float, float, float, float]  # x0, y0, x1, y1 of the printable area
    center: tuple[float, float]  # where Bambu Studio's arrange centres an item on plate 1
    app_version: str
    process: str
    filament: str

    @property
    def size(self) -> tuple[float, float]:
        return self.bed[2] - self.bed[0], self.bed[3] - self.bed[1]


def _load_printers() -> dict[str, Printer]:
    raw = json.loads((DATA_DIR / "printers.json").read_text())
    return {
        k: Printer(k, v["name"], v["printer_model"], tuple(v["bed"]), tuple(v["center"]),
                   v["app_version"], v["process"], v["filament"])
        for k, v in raw.items()
    }


PRINTERS: dict[str, Printer] = _load_printers()


@cache
def project_settings(key: str) -> bytes:
    """The printer's template, with extruder_nozzle_stats filled in on multi-nozzle printers.

    The templates leave extruder_nozzle_stats empty. Bambu Studio's GUI fills it in when
    it opens a project, but the CLI refuses to slice a dual-nozzle (H2D-family) project
    without it ("No valid nozzle found"), so write one standard nozzle per extruder, as the
    GUI would. Single-nozzle templates are passed through byte for byte."""
    raw = (DATA_DIR / "templates" / f"{key}.json").read_bytes()
    settings = json.loads(raw)
    n = len(settings.get("nozzle_diameter", []))
    if n < 2 or settings.get("extruder_nozzle_stats") or key in NOZZLE_STATS_UNCONFIRMED:
        return raw
    settings["extruder_nozzle_stats"] = ["Standard#1"] * n
    return (json.dumps(settings, indent=4) + "\n").encode()


def plate_offset(printer: Printer, index: int, n_plates: int) -> tuple[float, float]:
    """Offset of plate `index` (0-based) from plate 1: columns go +X, rows go -Y."""
    cols = math.ceil(math.sqrt(n_plates))
    w, d = printer.size
    return (index % cols) * w * PLATE_GAP, -(index // cols) * d * PLATE_GAP


_NS = (
    'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
    'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
    'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" '
    'requiredextensions="p"'
)
_XML = '<?xml version="1.0" encoding="UTF-8"?>\n'
_MODEL_REL = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"
_CONTENT_TYPES = (
    _XML + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
    ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
    ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
    ' <Default Extension="png" ContentType="image/png"/>\n'
    ' <Default Extension="gcode" ContentType="text/x.gcode"/>\n'
    "</Types>"
)
_MODEL_METADATA = (  # Bambu Studio's order; the dates and versions are filled in
    "Application", "BambuStudio:3mfVersion", "Copyright", "CreationDate", "Description",
    "Designer", "DesignerCover", "DesignerUserId", "License", "ModificationDate", "Origin",
    "ProfileCover", "ProfileDescription", "ProfileTitle", "Title",
)
_IDENTITY_COMPONENT = "1 0 0 0 1 0 0 0 1 0 0 0"
_IDENTITY_MATRIX = "1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"


def _rels(targets: list[str]) -> str:
    rels = "".join(
        f' <Relationship Target="{t}" Id="rel-{i + 1}" Type="{_MODEL_REL}"/>\n'
        for i, t in enumerate(targets)
    )
    return (_XML + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
            f'relationships">\n{rels}</Relationships>')


def _uuid(seed: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"spoolmaker:{seed}"))


def _meta(key: str, value, indent: str) -> str:
    return f"{indent}<metadata key={quoteattr(key)} value={quoteattr(str(value))}/>\n"


def to_bambu_project(parts: dict[str, Manifold], printer: str) -> bytes:
    """Bambu Studio project with part i alone on plate i+1, centred where Bambu would put it."""
    if printer not in PRINTERS:
        raise ValueError(f"unknown Bambu printer: {printer}")
    pr = PRINTERS[printer]
    today = date.today().isoformat()
    n = len(parts)
    files: dict[str, str] = {}
    resources, items, objects, plates, cuts = [], [], [], [], []
    for i, (name, m) in enumerate(parts.items()):
        mesh_id, obj_id, k = 2 * i + 1, 2 * i + 2, i + 1
        path = f"/3D/Objects/object_{k}.model"
        mesh, faces = mesh_xml(m)
        files[path[1:]] = (
            f'{_XML}<model unit="millimeter" xml:lang="en-US" {_NS}>\n'
            ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n <resources>\n'
            f'  <object id="{mesh_id}" p:UUID="{k:04x}0000-81cb-4c03-9d28-80fed5dfa1dc" '
            f'type="model">{mesh}</object>\n </resources>\n <build/>\n</model>\n'
        )
        resources.append(
            f'  <object id="{obj_id}" p:UUID="{k:08x}-61cb-4c03-9d28-80fed5dfa1dc" type="model">\n'
            f'   <components>\n    <component p:path="{path}" objectid="{mesh_id}" '
            f'p:UUID="{k:04x}0000-b206-40ff-9872-83e8017abed1" transform="{_IDENTITY_COMPONENT}"/>\n'
            "   </components>\n  </object>\n"
        )
        x0, y0, _, x1, y1, _ = m.bounding_box()
        ox, oy = plate_offset(pr, i, n)
        tx = pr.center[0] + ox - (x0 + x1) / 2
        ty = pr.center[1] + oy - (y0 + y1) / 2
        items.append(
            f'  <item objectid="{obj_id}" p:UUID="{obj_id:08x}-b1ec-4553-aec9-835e5b724bb4" '
            f'transform="1 0 0 0 1 0 0 0 1 {tx:.9g} {ty:.9g} 0" printable="1"/>\n'
        )
        objects.append(
            f'  <object id="{obj_id}">\n'
            + _meta("name", name, "    ") + _meta("extruder", 1, "    ")
            + f'    <metadata face_count="{faces}"/>\n'
            f'    <part id="{mesh_id}" subtype="normal_part" uuid="{_uuid(f"{printer}/{name}")}">\n'
            + _meta("name", name, "      ") + _meta("matrix", _IDENTITY_MATRIX, "      ")
            + _meta("source_file", f"{name}.stl", "      ")
            + "".join(_meta(f"source_{s}", 0, "      ") for s in
                      ("object_id", "volume_id", "offset_x", "offset_y", "offset_z"))
            + f'      <mesh_stat face_count="{faces}" edges_fixed="0" degenerate_facets="0" '
            'facets_removed="0" facets_reversed="0" backwards_edges="0"/>\n'
            "    </part>\n  </object>\n"
        )
        plates.append(
            "  <plate>\n"
            + _meta("plater_id", k, "    ") + _meta("plater_name", "", "    ")
            + _meta("locked", "false", "    ") + _meta("filament_map_mode", "Auto For Flush", "    ")
            + _meta("gcode_file", "", "    ")
            + "    <model_instance>\n"
            + _meta("object_id", obj_id, "      ") + _meta("instance_id", 0, "      ")
            + _meta("identify_id", 100 + k, "      ")
            + "    </model_instance>\n  </plate>\n"
        )
        cuts.append(f' <object id="{k}">\n  <cut_id id="0" check_sum="1" connectors_cnt="0"/>\n </object>\n')

    values = {"Application": f"BambuStudio-{pr.app_version}", "BambuStudio:3mfVersion": "1",
              "CreationDate": today, "ModificationDate": today}
    metadata = "".join(f' <metadata name="{k}">{values.get(k, "")}</metadata>\n'
                       for k in _MODEL_METADATA)
    model = (
        f'{_XML}<model unit="millimeter" xml:lang="en-US" {_NS}>\n{metadata}'
        f' <resources>\n{"".join(resources)} </resources>\n'
        f' <build p:UUID="{_uuid("build")}">\n{"".join(items)} </build>\n</model>\n'
    )
    model_settings = (
        f"{_XML}<config>\n{''.join(objects)}{''.join(plates)}  <assemble>\n  </assemble>\n</config>\n"
    )
    slice_info = (
        f'{_XML}<config>\n  <header>\n'
        '    <header_item key="X-BBL-Client-Type" value="slicer"/>\n'
        f'    <header_item key="X-BBL-Client-Version" value="{pr.app_version}"/>\n'
        "  </header>\n</config>\n"
    )
    sequence = json.dumps(
        {f"plate_{i + 1}": {"nozzle_sequence": [], "optimal_assignment": [], "sequence": []}
         for i in range(n)}, separators=(",", ":"))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _rels(["/3D/3dmodel.model"]))
        z.writestr("3D/3dmodel.model", model)
        z.writestr("3D/_rels/3dmodel.model.rels", _rels(["/" + p for p in files]))
        for path, body in files.items():
            z.writestr(path, body)
        z.writestr("Metadata/project_settings.config", project_settings(printer))
        z.writestr("Metadata/model_settings.config", model_settings)
        z.writestr("Metadata/slice_info.config", slice_info)
        z.writestr("Metadata/cut_information.xml",
                   f'<?xml version="1.0" encoding="utf-8"?>\n<objects>\n{"".join(cuts)}</objects>\n')
        z.writestr("Metadata/filament_sequence.json", sequence)
    return buf.getvalue()
