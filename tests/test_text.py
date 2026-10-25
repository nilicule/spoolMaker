import pytest

from spoolmaker.geometry.text import text_outline


def test_text_nonempty():
    cs = text_outline("PLA", 6.0)
    assert cs.area() > 0


def test_text_height():
    b = text_outline("H", 6.0).bounds()
    assert b[3] - b[1] == pytest.approx(6.0, rel=0.05)


def test_empty_text():
    assert text_outline("   ", 6.0).is_empty()


def test_unsupported_glyphs_dropped():
    assert text_outline("A🧵<&", 6.0).area() > 0


def test_holes_in_letters():
    b = text_outline("O", 10.0).bounds()
    assert text_outline("O", 10.0).area() < 0.6 * (b[2] - b[0]) * (b[3] - b[1])


def test_degree_sign_kept():
    assert text_outline("210°C", 6.0).area() > text_outline("210C", 6.0).area()


def test_centered():
    b = text_outline("PETG 240°C", 6.0).bounds()
    assert (b[0] + b[2]) / 2 == pytest.approx(0, abs=1e-6)
    assert (b[1] + b[3]) / 2 == pytest.approx(0, abs=1e-6)
