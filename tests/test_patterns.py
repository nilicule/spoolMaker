import pytest
from manifold3d import CrossSection

from spoolmaker.geometry.patterns import pattern_cutouts

KINDS = ["honeycomb", "spokes", "voronoi", "holes", "isogrid"]


@pytest.mark.parametrize("kind", KINDS)
def test_cutouts_inside_annulus(kind):
    cs = pattern_cutouts(kind, 0.5, 50, 93, 1, CrossSection())
    ring = CrossSection.circle(93, 128) - CrossSection.circle(50, 128)
    assert (cs - ring).area() < 1e-6 and cs.area() > 0


@pytest.mark.parametrize("kind", KINDS)
def test_density_increases_open_area(kind):
    lo = pattern_cutouts(kind, 0.0, 50, 93, 1, CrossSection()).area()
    hi = pattern_cutouts(kind, 1.0, 50, 93, 1, CrossSection()).area()
    assert hi > lo


@pytest.mark.parametrize("kind", KINDS)
def test_keepout_respected(kind):
    ko = CrossSection.square((30, 30)).translate((60, -15))
    cs = pattern_cutouts(kind, 0.5, 50, 93, 1, ko)
    assert (cs ^ ko).area() < 1e-6


def test_voronoi_deterministic():
    a = pattern_cutouts("voronoi", 0.5, 50, 93, 7, CrossSection()).area()
    assert a == pattern_cutouts("voronoi", 0.5, 50, 93, 7, CrossSection()).area()


def test_none_is_empty():
    assert pattern_cutouts("none", 0.5, 50, 93, 1, CrossSection()).is_empty()


@pytest.mark.parametrize("kind", KINDS)
def test_wall_margin_and_no_slivers(kind):
    ko = CrossSection.square((30, 30)).translate((60, -15))
    cs = pattern_cutouts(kind, 1.0, 50, 93, 1, ko)
    wall = 1.6
    # at least one wall of material from hub ring, rim and keep-out
    assert (cs ^ CrossSection.circle(50 + wall - 0.05, 128)).is_empty()
    assert (cs - CrossSection.circle(93 - wall + 0.05, 128)).is_empty()
    assert (cs ^ ko.offset(wall - 0.05)).is_empty()
    assert all(p.area() >= 4 for p in cs.decompose())
