import pytest
from manifold3d import CrossSection

from spoolmaker.geometry.patterns import pattern_cutouts

KINDS = ["honeycomb", "spokes", "voronoi", "holes", "isogrid", "windows"]


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


@pytest.mark.parametrize("with_keepout", [False, True])
@pytest.mark.parametrize("kind", KINDS)
def test_open_area_monotonic_in_density(kind, with_keepout):
    ko = (
        CrossSection.square((30, 30)).translate((60, -15))
        if with_keepout
        else CrossSection()
    )
    areas = [
        pattern_cutouts(kind, d, 50, 93, 1, ko).area()
        for d in (0.0, 0.25, 0.5, 0.75, 1.0)
    ]
    assert all(b >= a for a, b in zip(areas, areas[1:])), areas


def test_windows_ribs_and_rounded_corners():
    import math

    from spoolmaker.geometry.patterns import WINDOW_CORNER_R

    for density, n in ((0.0, 10), (1.0, 8)):
        cs = pattern_cutouts("windows", density, 50, 93, 1, CrossSection())
        assert len(cs.decompose()) == n  # one window between each pair of ribs
    # Rib width lerps 10 -> 5 mm: the gap between neighbouring windows along a ring.
    cs = pattern_cutouts("windows", 1.0, 50, 93, 1, CrossSection())
    probe = CrossSection.square((1.0, 4.8), center=True).translate((70, 0))  # inside a 5 mm rib
    assert (cs ^ probe).is_empty()
    assert not (cs ^ CrossSection.square((1.0, 6.0), center=True).translate((70, 0))).is_empty()
    # Corners are rounded: next to the rib/outer-margin corner (rib at 45 deg, outer
    # margin 93 - MIN_WEB) a sharp window would be cut; the rounded one is not, while the
    # window is cut further along the rib edge.
    r_edge = 93 - 1.6

    def beside_rib(r):
        a = math.radians(45) - (2.5 + 0.3) / r
        return CrossSection.square((0.3, 0.3), center=True).translate((r * math.cos(a), r * math.sin(a)))

    assert (cs ^ beside_rib(r_edge - 0.3)).is_empty()
    assert not (cs ^ beside_rib(r_edge - 2 * WINDOW_CORNER_R)).is_empty()


@pytest.mark.parametrize("density", [0.0, 0.5, 1.0])
def test_windows_leave_no_islands(density):
    """A keep-out in the middle of a window (here 22.5 deg, between the ribs at 0 and
    36 / 45 deg) gets its own rib, so the flange stays one piece."""
    import math

    a = math.radians(22.5)
    ko = CrossSection.square((14, 14), center=True).translate((70 * math.cos(a), 70 * math.sin(a)))
    cs = pattern_cutouts("windows", density, 50, 93, 1, ko)
    flange = CrossSection.circle(100, 128) - CrossSection.circle(40, 128) - cs
    assert len(flange.decompose()) == 1
    assert (cs ^ ko).is_empty()
