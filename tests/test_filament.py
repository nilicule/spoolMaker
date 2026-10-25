from spoolmaker.config import SpoolConfig
from spoolmaker.filament import coil_fits, gauge_ticks, mass_between, radius_for_mass


def test_mass_radius_inverse():
    r = radius_for_mass(1000, 40.0, 62.0, "PLA")
    assert abs(mass_between(40.0, r, 62.0, "PLA") - 1000) < 1e-6


def test_lower_density_needs_more_radius():
    assert radius_for_mass(1000, 40, 62, "ABS") > radius_for_mass(1000, 40, 62, "PLA")


def test_default_config_fits():
    assert coil_fits(SpoolConfig())


def test_gauge_ticks_descending_radius():
    ticks = gauge_ticks(SpoolConfig())
    assert [g for g, _ in ticks] == [1000, 750, 500, 250]
    assert all(a[1] > b[1] for a, b in zip(ticks, ticks[1:]))
    assert ticks[-1][1] > SpoolConfig().coil_inner_diameter / 2
