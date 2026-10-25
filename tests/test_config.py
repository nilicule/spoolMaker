import pytest

from spoolmaker.config import PRESETS, SpoolConfig, config_schema, from_query, to_query, validate


def test_defaults_valid():
    assert validate(SpoolConfig()) == []


def test_roundtrip_query():
    cfg = SpoolConfig(pattern="voronoi", text="PETG 240", clip_holes=6)
    assert from_query(to_query(cfg)) == cfg


def test_to_query_omits_defaults():
    assert to_query(SpoolConfig()) == {}


def test_from_query_garbage():
    cfg = from_query({"outer_diameter": "abc", "bore_diameter": "99", "pattern": "x", "zzz": "1"})
    assert cfg.outer_diameter == 200.0 and cfg.bore_diameter == 58.0 and cfg.pattern == "honeycomb"


def test_text_truncated():
    assert len(from_query({"text": "x" * 100}).text) == 24


def test_preset_overrides_coil_dims():
    cfg = from_query({"refill": "bambu", "coil_inner_diameter": "70"})
    assert cfg.coil_inner_diameter == PRESETS["bambu"].inner_diameter


def test_width_over_limit():
    cfg = SpoolConfig(refill="custom", coil_width=64.0, flange_thickness=3.0)  # 64.6+6 = 70.6
    assert any("width" in e for e in validate(cfg))


def test_coil_too_narrow_for_bore():
    cfg = SpoolConfig(refill="custom", coil_inner_diameter=60.0, bore_diameter=55.0)
    assert any("inner diameter" in e for e in validate(cfg))


def test_default_bore_is_53():
    assert SpoolConfig().bore_diameter == 53.0 and not validate(SpoolConfig())


def test_thin_lock_wall_rejected():
    cfg = SpoolConfig(refill="custom", coil_inner_diameter=70.0, bore_diameter=58.0,
                      coil_clearance=2.0, lock_clearance=0.6)
    errors = validate(cfg)
    assert any("twist-lock" in e and "coil inner diameter" in e for e in errors)


def test_lock_wall_at_minimum_accepted():
    # With default clearances a 58 mm bore needs a 70.8 mm coil ID: socket wall (channel
    # depth + MIN_LOCK_WALL), lock clearance and B's sleeve then end exactly at the bore.
    from spoolmaker.geometry.dims import dims

    cfg = SpoolConfig(refill="custom", coil_inner_diameter=70.8, bore_diameter=58.0)
    assert dims(cfg).r_sleeve_in == pytest.approx(cfg.bore_diameter / 2)
    assert not any("twist-lock" in e for e in validate(cfg))
    tighter = SpoolConfig(refill="custom", coil_inner_diameter=70.6, bore_diameter=58.0)
    assert any("twist-lock" in e for e in validate(tighter))


def test_one_kg_must_fit():
    cfg = SpoolConfig(refill="custom", coil_inner_diameter=150.0, coil_width=45.0)
    assert any("1 kg" in e for e in validate(cfg))


def test_bool_parsing_and_clamping():
    cfg = from_query({"lightweight": "true", "label": "0", "clip_holes": "99", "tag_diameter": "7"})
    assert cfg.lightweight is True and cfg.label is False
    assert cfg.clip_holes == 8 and cfg.tag_diameter == 25


def test_schema_shape():
    s = config_schema()
    assert s["fields"]["outer_diameter"]["min"] == 197.0
    assert "honeycomb" in s["fields"]["pattern"]["choices"]
    assert s["presets"]["bambu"]["verified"] is False
    assert set(s["limits"]) == {"od", "width", "bore", "rim_width", "rim_width_light", "max_text",
                                "twist_deg"}
    from spoolmaker.config import RIM_WIDTH, RIM_WIDTH_LIGHT

    assert s["limits"]["rim_width"] == RIM_WIDTH == 7.0
    assert s["limits"]["rim_width_light"] == RIM_WIDTH_LIGHT == 6.0
    from spoolmaker.geometry.lock import TWIST_DEG

    assert s["limits"]["twist_deg"] == TWIST_DEG


def test_from_query_nonfinite_ints_fall_back():
    cfg = from_query({"clip_holes": "inf", "pattern_seed": "1e999", "coil_width": "-inf"})
    assert cfg.clip_holes == 4 and cfg.pattern_seed == 1 and cfg.coil_width == 60.0


def test_bambu_printer_choice():
    from spoolmaker.bambu import DEFAULT_PRINTER, PRINTERS

    assert SpoolConfig().bambu_printer == DEFAULT_PRINTER == "a1"
    assert from_query({"bambu_printer": "p1s"}).bambu_printer == "p1s"
    assert from_query({"bambu_printer": "garbage"}).bambu_printer == DEFAULT_PRINTER
    assert to_query(from_query({"bambu_printer": "p1s"})) == {"bambu_printer": "p1s"}
    s = config_schema()
    assert s["fields"]["bambu_printer"]["choices"] == list(PRINTERS)
    assert s["bambu_printers"]["a1"]["name"] == "Bambu Lab A1"


def test_defaults_lightweight_no_label_no_gauge():
    d = SpoolConfig()
    assert d.pattern == "honeycomb" and d.lightweight and not d.label and not d.gauge
    # links from before the change still load as written
    old = from_query({"lightweight": "1", "label": "0", "gauge": "1"})
    assert old.lightweight and not old.label and old.gauge
    assert to_query(old) == {"gauge": "1"}
    classic = from_query({"lightweight": "0", "label": "1", "gauge": "1"})
    assert not classic.lightweight and classic.label and classic.gauge
    assert from_query(to_query(classic)) == classic
    assert to_query(SpoolConfig()) == {}
