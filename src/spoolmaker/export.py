"""Mesh export: manifold3d Manifold -> binary STL / 3MF bytes."""

import io
import zipfile
from xml.sax.saxutils import quoteattr

import numpy as np
from manifold3d import Manifold

BUILD_OFFSET_X = 210.0

_STL_DTYPE = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
    "</Types>"
)
_RELS = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
    'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
    "</Relationships>"
)


def mesh_arrays(m: Manifold) -> tuple[np.ndarray, np.ndarray]:
    """Export-ready mesh: vertices welded by float32 position, degenerate triangles dropped."""
    mesh = m.to_mesh()
    verts = np.ascontiguousarray(mesh.vert_properties[:, :3], dtype=np.float32)
    tris = np.asarray(mesh.tri_verts, dtype=np.int64)
    uniq, inverse = np.unique(verts, axis=0, return_inverse=True)
    tris = inverse.reshape(-1)[tris]
    keep = (tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 2] != tris[:, 0])
    tris = tris[keep]
    tv = uniq.astype(np.float64)[tris]
    cross = np.cross(tv[:, 1] - tv[:, 0], tv[:, 2] - tv[:, 0])
    tris = tris[np.any(cross != 0, axis=1)]
    used, remap = np.unique(tris, return_inverse=True)
    return (
        np.ascontiguousarray(uniq[used], dtype=np.float32),
        np.ascontiguousarray(remap.reshape(-1, 3), dtype=np.uint32),
    )


def to_stl(m: Manifold) -> bytes:
    verts, tris = mesh_arrays(m)
    tv = verts[tris]  # (M, 3, 3)
    n = np.cross(tv[:, 1] - tv[:, 0], tv[:, 2] - tv[:, 0]).astype(np.float64)
    length = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.divide(n, length, out=np.zeros_like(n), where=length > 0)
    rec = np.zeros(len(tris), dtype=_STL_DTYPE)
    rec["n"] = n
    rec["v"] = tv
    header = b"spoolmaker binary STL".ljust(80, b"\0")
    return header + np.uint32(len(tris)).astype("<u4").tobytes() + rec.tobytes()


def _object_xml(oid: int, name: str, m: Manifold) -> str:
    verts, tris = mesh_arrays(m)
    vs = "".join(f'<vertex x="{x:.6g}" y="{y:.6g}" z="{z:.6g}"/>' for x, y, z in verts.tolist())
    ts = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in tris.tolist())
    return (
        f'<object id="{oid}" name={quoteattr(name)} type="model"><mesh>'
        f"<vertices>{vs}</vertices><triangles>{ts}</triangles></mesh></object>"
    )


def to_3mf(parts: dict[str, Manifold]) -> bytes:
    objects, items = [], []
    for i, (name, m) in enumerate(parts.items()):
        oid = i + 1
        objects.append(_object_xml(oid, name, m))
        x = i * BUILD_OFFSET_X
        items.append(f'<item objectid="{oid}" transform="1 0 0 0 1 0 0 0 1 {x:g} 0 0"/>')
    model = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
        f"<resources>{''.join(objects)}</resources>"
        f"<build>{''.join(items)}</build></model>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("3D/3dmodel.model", model)
    return buf.getvalue()
