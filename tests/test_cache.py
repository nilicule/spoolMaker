from dataclasses import replace

from spoolmaker import cache
from spoolmaker.config import SpoolConfig
from spoolmaker.stats import stats

CFG = SpoolConfig(pattern="none", label=False, gauge=False, clip_holes=0, lightweight=False)


def test_print_material_does_not_rebuild_geometry():
    cache.half(CFG, "a")
    misses = cache._half.cache_info().misses
    petg = replace(CFG, print_material="PETG")
    assert cache.half(petg, "a") is cache.half(CFG, "a")
    assert cache.stl(petg, "a") is cache.stl(CFG, "a")
    assert cache._half.cache_info().misses == misses


def test_stats_weight_still_follows_print_material():
    pla = stats(CFG)["weight_g"]["total"]
    petg = stats(replace(CFG, print_material="PETG"))["weight_g"]["total"]
    assert petg > pla


def test_stats_does_not_import_app():
    import inspect

    import spoolmaker.stats as s

    assert ".app" not in inspect.getsource(s)


def test_bambu_printer_does_not_rebuild_geometry():
    cache.half(CFG, "a")
    misses = cache._half.cache_info().misses
    x1c = replace(CFG, bambu_printer="x1-carbon")
    assert cache.half(x1c, "a") is cache.half(CFG, "a")
    assert cache.three_mf(x1c) is cache.three_mf(CFG)
    assert cache.bambu_project(x1c) != cache.bambu_project(CFG)
    assert cache._half.cache_info().misses == misses
