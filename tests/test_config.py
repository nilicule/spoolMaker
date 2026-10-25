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
    # Minimum coil ID for the bore with default clearances leaves exactly 1.6 mm.
    cfg = SpoolConfig(refill="custom", coil_inner_diameter=70.0, bore_diameter=58.0)
    assert not any("twist-lock" in e for e in validate(cfg))


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
    assert set(s["limits"]) == {"od", "width", "bore", "rim_width", "max_text", "twist_deg"}
    from spoolmaker.geometry.lock import TWIST_DEG

    assert s["limits"]["twist_deg"] == TWIST_DEG


def test_from_query_nonfinite_ints_fall_back():
    cfg = from_query({"clip_holes": "inf", "pattern_seed": "1e999", "coil_width": "-inf"})
    assert cfg.clip_holes == 4 and cfg.pattern_seed == 1 and cfg.coil_width == 60.0
