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


def _b_at(cfg, twist, dz=0.0):
    from spoolmaker.geometry.build import build_half as bh

    return (
        bh(cfg, "b").rotate((180, 0, 0)).translate((0, 0, cfg.overall_width + dz)).rotate((0, 0, twist))
    )


@pytest.mark.parametrize("clearance", [0.15, 0.3, 0.6])
def test_detent_engages_for_all_clearances(clearance):
    from spoolmaker.geometry.lock import TWIST_DEG

    cfg = SpoolConfig(pattern="none", label=False, gauge=False, clip_holes=0, lock_clearance=clearance)
    a = build_half(cfg, "a")
    assert (a ^ _b_at(cfg, 20)).volume() > 0.1
    assert (a ^ _b_at(cfg, TWIST_DEG)).volume() == pytest.approx(0, abs=1e-6)


@pytest.mark.parametrize("clearance", [0.15, 0.6])
@pytest.mark.parametrize("dz", [0, 5, 20, 40])
def test_insertion_path_clear_at_zero_twist(clearance, dz):
    cfg = SpoolConfig(pattern="none", label=False, gauge=False, clip_holes=0, lock_clearance=clearance)
    a = build_half(cfg, "a")
    assert (a ^ _b_at(cfg, 0, dz)).volume() == pytest.approx(0, abs=1e-6)


def test_pocket_roof_chamfered_45():
    from spoolmaker.geometry.dims import dims
    from spoolmaker.geometry.lock import LUG_AXIAL, channel_r

    d = dims(CFG)
    a = build_half(CFG, "a")
    # Probe a thin ring just below the flat roof height, near the pocket wall, at the
    # locked lug angle (30 deg). With a 45 deg chamfer the roof is lower at the wall,
    # so the probe hits material there.
    r_wall = channel_r(d)
    z = d.t + LUG_AXIAL + d.lock_clearance - 0.3
    probe = (
        Manifold.cube((0.3, 0.5, 0.2), center=True)
        .translate((r_wall - 0.25, 0, z))
        .rotate((0, 0, 30))
    )
    assert (a ^ probe).volume() > 0.01
