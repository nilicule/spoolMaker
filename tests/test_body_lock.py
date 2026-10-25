import pytest
from manifold3d import Error, Manifold

from spoolmaker.config import SpoolConfig
from spoolmaker.geometry.build import assembled, build_half

CFG = SpoolConfig(pattern="none", label=False, gauge=False, clip_holes=0)


@pytest.mark.parametrize("half", ["a", "b"])
def test_half_is_valid_solid(half):
    m = build_half(CFG, half)
    assert m.status() == Error.NoError and m.volume() > 0


def test_assembled_envelope():
    a, b = assembled(CFG)
    lo, hi = (a + b).bounding_box()[:3], (a + b).bounding_box()[3:]
    assert hi[2] - lo[2] == pytest.approx(CFG.overall_width, abs=0.01)
    assert hi[0] - lo[0] == pytest.approx(CFG.outer_diameter, abs=0.2)


def test_locked_halves_do_not_intersect():
    a, b = assembled(CFG)
    assert (a ^ b).volume() < 1e-3


def test_lug_blocked_when_not_in_channel():
    a, b = assembled(CFG)  # locked
    b_pulled = b.translate((0, 0, 5.0))  # try to pull apart axially
    assert (a ^ b_pulled).volume() > 1.0  # lugs collide -> locked


def test_bore_clear():
    a, b = assembled(CFG)
    probe = Manifold.cylinder(CFG.overall_width, CFG.bore_diameter / 2 - 0.05, circular_segments=128)
    assert ((a + b) ^ probe).volume() < 1e-3
