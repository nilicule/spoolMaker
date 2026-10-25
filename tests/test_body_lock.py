import pytest
from manifold3d import Error, Manifold

from spoolmaker.config import SpoolConfig
from spoolmaker.geometry.build import assembled, build_half

_PLAIN = dict(pattern="none", label=False, gauge=False, clip_holes=0, lightweight=False)
CFG = SpoolConfig(**_PLAIN)
# Tightest accepted lock: minimum coil ID for the largest bore with default clearances.
TIGHT = SpoolConfig(**_PLAIN, refill="custom", coil_inner_diameter=70.8, bore_diameter=58.0)


@pytest.mark.parametrize("half", ["a", "b"])
def test_half_is_valid_solid(half):
    m = build_half(CFG, half)
    assert m.status() == Error.NoError and m.volume() > 0


def test_assembled_envelope():
    a, b = assembled(CFG)
    lo, hi = (a + b).bounding_box()[:3], (a + b).bounding_box()[3:]
    assert hi[2] - lo[2] == pytest.approx(CFG.overall_width, abs=0.01)
    assert hi[0] - lo[0] == pytest.approx(CFG.outer_diameter, abs=0.2)


@pytest.mark.parametrize("cfg", [CFG, TIGHT], ids=["default", "tight"])
def test_locked_halves_do_not_intersect(cfg):
    a, b = assembled(cfg)
    assert (a ^ b).volume() < 1e-3


@pytest.mark.parametrize("cfg", [CFG, TIGHT], ids=["default", "tight"])
def test_lug_blocked_when_not_in_channel(cfg):
    a, b = assembled(cfg)  # locked
    b_pulled = b.translate((0, 0, 5.0))  # try to pull apart axially
    assert (a ^ b_pulled).volume() > 1.0  # lugs collide -> locked


@pytest.mark.parametrize("cfg", [CFG, TIGHT], ids=["default", "tight"])
def test_bore_clear(cfg):
    # The tightest accepted config puts B's sleeve bore flush with the bore.
    a, b = assembled(cfg)
    probe = Manifold.cylinder(cfg.overall_width, cfg.bore_diameter / 2 - 0.05, circular_segments=128)
    assert ((a + b) ^ probe).volume() < 1e-3


def _b_at(cfg, twist, dz=0.0):
    from spoolmaker.geometry.build import build_half as bh

    return (
        bh(cfg, "b").rotate((180, 0, 0)).translate((0, 0, cfg.overall_width + dz)).rotate((0, 0, twist))
    )


@pytest.mark.parametrize("clearance", [0.15, 0.3, 0.6])
def test_detent_engages_for_all_clearances(clearance):
    from spoolmaker.geometry.lock import TWIST_DEG

    cfg = SpoolConfig(**_PLAIN, lock_clearance=clearance)
    a = build_half(cfg, "a")
    assert (a ^ _b_at(cfg, 20)).volume() > 0.1
    assert (a ^ _b_at(cfg, TWIST_DEG)).volume() == pytest.approx(0, abs=1e-6)


@pytest.mark.parametrize("clearance", [0.15, 0.6])
@pytest.mark.parametrize("dz", [0, 5, 9.5])  # engagement is SOCKET_DEPTH = 10 mm
def test_insertion_path_clear_at_zero_twist(clearance, dz):
    cfg = SpoolConfig(**_PLAIN, lock_clearance=clearance)
    a = build_half(cfg, "a")
    assert (a ^ _b_at(cfg, 0, dz)).volume() == pytest.approx(0, abs=1e-6)


def test_pocket_roof_chamfered_45():
    from spoolmaker.geometry.dims import dims
    from spoolmaker.geometry.lock import LUG_AXIAL, channel_r, socket_floor_z

    d = dims(CFG)
    a = build_half(CFG, "a")
    # Probe a thin ring just below the flat roof height, near the pocket wall, at the
    # locked lug angle (30 deg). With a 45 deg chamfer the roof is lower at the wall,
    # so the probe hits material there.
    r_wall = channel_r(d)
    z = socket_floor_z(d) + LUG_AXIAL + d.lock_clearance - 0.3
    probe = (
        Manifold.cube((0.3, 0.5, 0.2), center=True)
        .translate((r_wall - 0.25, 0, z))
        .rotate((0, 0, 30))
    )
    assert (a ^ probe).volume() > 0.01


def test_only_core_tops_seat_the_halves():
    from spoolmaker.geometry.body import tube
    from spoolmaker.geometry.dims import SEAT_GAP, dims
    from spoolmaker.geometry.lock import core_height_a, socket_floor_z

    d = dims(CFG)
    a, b = assembled(CFG)
    z_floor = socket_floor_z(d)
    # B's sleeve tip stops SEAT_GAP short of A's socket floor ...
    gap = tube(SEAT_GAP - 0.02, d.r_bore - 0.5, d.r_socket_in - 0.01, d.seg).translate((0, 0, z_floor + 0.01))
    assert (b ^ gap).volume() == pytest.approx(0, abs=1e-6)
    # ... and not much more: the tip is right there (gap ~= SEAT_GAP).
    tip = tube(0.02, d.r_sleeve_in + 0.01, d.r_sleeve_out - 0.01, d.seg).translate((0, 0, z_floor + SEAT_GAP + 0.01))
    assert (b ^ tip).volume() > 0
    # A's core top meets B's core top at the joint: both reach it, with zero-volume overlap.
    z_joint = d.t + core_height_a(d)
    below = tube(0.02, d.r_socket_in + 0.01, d.r_core_out - 0.01, d.seg).translate((0, 0, z_joint - 0.02))
    above = tube(0.02, d.r_socket_in + 0.01, d.r_core_out - 0.01, d.seg).translate((0, 0, z_joint))
    assert (a ^ below).volume() > 0
    assert (b ^ above).volume() > 0
    assert (a ^ above).volume() == pytest.approx(0, abs=1e-6)
    assert (b ^ below).volume() == pytest.approx(0, abs=1e-6)


@pytest.mark.parametrize("cfg", [CFG, SpoolConfig(), SpoolConfig(lightweight=False, label=True, gauge=True),
                                 SpoolConfig(coil_width=40.0, flange_thickness=5.0, lightweight=False,
                                             label=True, gauge=True),
                                 SpoolConfig(coil_width=60.0, flange_thickness=2.0, lightweight=True,
                                             label=True, gauge=True)])
def test_halves_roughly_equal_height(cfg):
    from spoolmaker.geometry.lock import SOCKET_DEPTH

    ha, hb = (build_half(cfg, h).bounding_box() for h in "ab")
    za, zb = ha[5] - ha[2], hb[5] - hb[2]
    assert abs(za - zb) <= 1.0
    cap = cfg.flange_thickness + cfg.inner_width / 2 + SOCKET_DEPTH / 2 + 0.01
    assert za <= cap and zb <= cap


def test_socket_wall_thickened_with_chamfered_step():
    """Only the socket (top SOCKET_DEPTH of A's tube) is thickened, to MIN_LOCK_WALL behind
    the channels/pocket; below it the tube is TUBE_WALL, joined by a 45 deg chamfer."""
    import math

    from manifold3d import CrossSection

    from spoolmaker.config import MIN_LOCK_WALL
    from spoolmaker.geometry.dims import TUBE_WALL, dims
    from spoolmaker.geometry.lock import channel_r, socket_floor_z

    d = dims(CFG)
    a = build_half(CFG, "a")
    assert d.r_core_out - channel_r(d) == pytest.approx(MIN_LOCK_WALL)
    assert d.r_core_out - d.r_tube_a_in == pytest.approx(TUBE_WALL)
    z0 = socket_floor_z(d)
    step = d.r_tube_a_in - d.r_socket_in
    assert step > 0

    def bore_at(z, angle_deg=90):  # 90 deg: clear of the channels and pockets
        """Radius of the first material along a ray (0.01 mm steps)."""
        sec = a.slice(z)
        c, s = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
        r = d.r_sleeve_in
        while r < d.r_core_out:
            if not (CrossSection.square((0.02, 0.02), center=True).translate((r * c, r * s)) ^ sec).is_empty():
                return r
            r += 0.01
        return None

    assert bore_at(z0 + 2) == pytest.approx(d.r_socket_in, abs=0.03)
    assert bore_at(z0 - step / 2) == pytest.approx(d.r_socket_in + step / 2, abs=0.03)  # 45 deg
    assert bore_at(z0 - step - 1) == pytest.approx(d.r_tube_a_in, abs=0.03)
