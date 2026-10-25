"""Regenerate the PNG favicons from src/spoolmaker/static/favicon.svg (dev-only).

Needs rsvg-convert (librsvg, e.g. `brew install librsvg`). Writes favicon-32.png and
apple-touch-icon.png (180x180, on the page background: iOS shows no transparency).

    uv run python scripts/make_favicons.py
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "src" / "spoolmaker" / "static"
PAGE_BG = "#f3ede2"  # --bg in style.css (light theme)


def render(out: str, size: int, background: str | None = None, pad: int = 0) -> None:
    rsvg = shutil.which("rsvg-convert")
    if not rsvg:
        raise SystemExit("rsvg-convert not found (brew install librsvg)")
    svg = (STATIC / "favicon.svg").read_text()
    if pad:  # inset the mark so it doesn't touch the rounded icon corners
        svg = svg.replace('viewBox="0 0 32 32"', f'viewBox="{-pad} {-pad} {32 + 2 * pad} {32 + 2 * pad}"')
    cmd = [rsvg, "-w", str(size), "-h", str(size), "-o", str(STATIC / out)]
    if background:
        cmd += ["--background-color", background]
    subprocess.run(cmd, input=svg.encode(), check=True)
    print(f"{out}: {size}x{size}")


if __name__ == "__main__":
    render("favicon-32.png", 32)
    render("apple-touch-icon.png", 180, background=PAGE_BG, pad=4)
