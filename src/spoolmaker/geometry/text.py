"""Text to 2D outline, using matplotlib's bundled DejaVu Sans Bold."""
from functools import lru_cache

from manifold3d import CrossSection, FillRule
from matplotlib import font_manager
from matplotlib.font_manager import FontProperties
from matplotlib.ft2font import FT2Font
from matplotlib.textpath import TextPath

_FP = FontProperties(family="DejaVu Sans", weight="bold")
_BIG = 100.0  # build at large size so flattened curves are dense, then scale down


@lru_cache(maxsize=1)
def _font() -> FT2Font:
    return FT2Font(font_manager.findfont(_FP, fallback_to_default=False))


def _supported(text: str) -> str:
    f = _font()
    return "".join(c for c in text if c.isprintable() and f.get_char_index(ord(c)) != 0)


@lru_cache(maxsize=1)
def _cap_ratio() -> float:
    """Cap height of 'H' as a fraction of the font size."""
    ys = [p[:, 1] for p in TextPath((0, 0), "H", size=_BIG, prop=_FP).to_polygons()]
    return (max(y.max() for y in ys) - min(y.min() for y in ys)) / _BIG


def text_outline(text: str, cap_height_mm: float) -> CrossSection:
    text = _supported(text).strip()
    if not text:
        return CrossSection()
    polys = TextPath((0, 0), text, size=_BIG, prop=_FP).to_polygons(closed_only=True)
    polys = [p.tolist() for p in polys if len(p) >= 3]
    if not polys:
        return CrossSection()
    cs = CrossSection(polys, FillRule.EvenOdd)
    if cs.is_empty():
        return cs
    s = cap_height_mm / (_BIG * _cap_ratio())
    x0, y0, x1, y1 = cs.bounds()
    return cs.translate((-(x0 + x1) / 2, -(y0 + y1) / 2)).scale((s, s))
