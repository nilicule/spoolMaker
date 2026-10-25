"""The slicer-like estimate against what Bambu Studio's slicer reports for the same project.

tests/fixtures/bambu_grams.json comes from scripts/calibrate_estimate.py (Bambu Studio CLI).
"""

import json
import os
import subprocess
import time
from pathlib import Path

import pytest
from manifold3d import Manifold

from spoolmaker import cache
from spoolmaker.bambu import PRINTERS, project_settings
from spoolmaker.config import from_query
from spoolmaker.estimate import (
    bambu_profile, estimate_grams, layer_heights, profile_from_settings, volume_breakdown,
)
from spoolmaker.stats import stats

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "bambu_grams.json").read_text())
TOLERANCE = 0.06
BAMBU_CLI = Path("/Applications/BambuStudio.app/Contents/MacOS/BambuStudio")
# Re-slicing with the real Bambu Studio is slow: opt in with SPOOLMAKER_BAMBU_LIVE=1.
LIVE = os.environ.get("SPOOLMAKER_BAMBU_LIVE") == "1" and BAMBU_CLI.exists()


def _errors(case: dict) -> dict[str, float]:
    cfg = from_query(case["query"])
    profile = bambu_profile(case["printer"])
    return {h: estimate_grams(cache.half(cfg, h), profile) / case[f"{h}_g"] - 1 for h in "ab"}


def test_fixture_matrix_covers_the_brief():
    names = {k.split("@")[0] for k in FIXTURES}
    printers = {c["printer"] for c in FIXTURES.values()}
    assert {"default", "classic", "windows", "voronoi_text_tag", "spokes", "coil_70_bore_58",
            "flange_2", "flange_5"} <= names
    assert {"a1", "h2d"} <= printers


@pytest.mark.parametrize("case", sorted(FIXTURES))
def test_estimate_matches_bambu_studio(case):
    errors = _errors(FIXTURES[case])
    for h, e in errors.items():
        assert abs(e) <= TOLERANCE, f"{case} half {h}: {e:+.1%} vs Bambu Studio"


def test_estimate_well_below_solid_weight():
    cfg = from_query({})
    s = stats(cfg)
    for h in "ab":
        assert 0.6 * s["weight_g"][h] < s["estimate_g"][h] < 0.9 * s["weight_g"][h]


def test_stats_estimate_fields():
    s = stats(from_query({"bambu_printer": "h2d"}))
    assert s["estimate_g"]["total"] == pytest.approx(s["estimate_g"]["a"] + s["estimate_g"]["b"])
    note = s["estimate_note"]
    assert "Bambu Lab H2D" in note and "0.20 mm Standard" in note and "15% infill" in note
    assert "2 walls" in note and "Bambu PLA Basic" in note


def test_stats_estimate_other_material_uses_its_density():
    pla = stats(from_query({}))["estimate_g"]["a"]
    abs_ = stats(from_query({"print_material": "ABS"}))
    assert abs_["estimate_g"]["a"] < pla and "ABS" in abs_["estimate_note"]


def test_profile_reads_template():
    p = bambu_profile("a1")
    assert (p.layer_height, p.wall_loops, p.top_shell_layers, p.bottom_shell_layers) == (0.2, 2, 5, 3)
    assert p.sparse_density == pytest.approx(0.15)
    assert p.filament_density == pytest.approx(1.26) and p.flow_ratio == pytest.approx(0.98)
    assert p.sparse_anchor == pytest.approx(1.8)  # 400% of 0.45 mm, under the 20 mm cap


def test_shell_thickness_raises_layer_count():
    base = json.loads(project_settings("a1"))
    p = profile_from_settings({**base, "top_shell_thickness": "1.5", "bottom_shell_thickness": "0"})
    assert p.top_shell_layers == 8 and p.bottom_shell_layers == 3


def test_solid_cube_is_all_solid():
    """A 20 mm cube is walls + solid skin + sparse core; full infill would weigh the solid."""
    p = bambu_profile("a1")
    cube = Manifold.cube((20, 20, 20))
    v = volume_breakdown(cube, p)
    assert sum(v[k] for k in ("wall", "solid", "bridge", "sparse")) == pytest.approx(8000, rel=0.01)
    solid = p.__class__(**{**p.__dict__, "sparse_density": 1.0, "sparse_anchor": 0.0})
    assert estimate_grams(cube, solid) == pytest.approx(
        8 * p.filament_density * p.flow_ratio, rel=0.03)
    assert estimate_grams(cube, p) < 0.5 * estimate_grams(cube, solid)


def test_layer_heights():
    p = bambu_profile("a1")
    layers = layer_heights(3.0, p)
    assert len(layers) == 15 and layers[0] == pytest.approx((0.1, 0.2))
    assert sum(h for _, h in layers) == pytest.approx(3.0)


def test_estimate_is_fast_for_default():
    cfg = from_query({})
    p = bambu_profile("a1")
    for h in "ab":
        m = cache.half(cfg, h)
        t = time.perf_counter()
        volume_breakdown(m, p)
        assert time.perf_counter() - t < 0.5, f"half {h} took too long"


@pytest.mark.skipif(not LIVE, reason="set SPOOLMAKER_BAMBU_LIVE=1 (needs Bambu Studio)")
def test_live_bambu_studio_matches_fixture(tmp_path):
    """Re-slice the default case with the installed Bambu Studio (slow, dev machines only)."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from calibrate_estimate import slice_case

    case = FIXTURES["default@a1"]
    a, b = slice_case(BAMBU_CLI, case["query"])
    assert a == pytest.approx(case["a_g"], rel=0.01) and b == pytest.approx(case["b_g"], rel=0.01)


def test_other_material_note_is_honest():
    note = stats(from_query({"print_material": "PETG"}))["estimate_note"]
    assert note.endswith("Bambu PLA Basic profile, weighed as PETG (1.27 g/cm³)")


@pytest.mark.parametrize("printer", sorted(PRINTERS))
def test_bundled_templates_use_grid_infill(printer):
    """SliceProfile.anchor_cover models grid infill."""
    assert json.loads(project_settings(printer))["sparse_infill_pattern"] == "grid"
    assert bambu_profile(printer).sparse_pattern == "grid"


def test_estimate_cache_shared_by_identical_profiles():
    from dataclasses import replace

    assert bambu_profile("a1").geometry_key() == bambu_profile("p1s").geometry_key()
    cfg = from_query({"pattern": "spokes", "pattern_density": "0.37"})
    cache.extruded_mm3_for(replace(cfg, bambu_printer="a1"), "a")
    misses = cache._extruded.cache_info().misses
    cache.extruded_mm3_for(replace(cfg, bambu_printer="p1s"), "a")
    assert cache._extruded.cache_info().misses == misses
