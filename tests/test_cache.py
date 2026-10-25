from dataclasses import replace

from spoolmaker import cache
from spoolmaker.config import SpoolConfig
from spoolmaker.stats import stats

CFG = SpoolConfig(pattern="none", label=False, gauge=False, clip_holes=0)


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
