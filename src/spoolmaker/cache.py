"""Shared, memoised geometry and export bytes for the API and stats."""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

from manifold3d import Manifold

from .config import SpoolConfig
from .export import to_3mf, to_stl
from .geometry.build import build_half


def _geometry_key(cfg: SpoolConfig) -> SpoolConfig:
    """Config with fields that don't affect geometry normalised, so they share a cache entry."""
    return replace(cfg, print_material=SpoolConfig.print_material)


@lru_cache(maxsize=64)
def _half(cfg: SpoolConfig, half: str) -> Manifold:
    return build_half(cfg, half)


@lru_cache(maxsize=64)
def _stl(cfg: SpoolConfig, half: str) -> bytes:
    return to_stl(_half(cfg, half))


@lru_cache(maxsize=16)
def _3mf(cfg: SpoolConfig) -> bytes:
    return to_3mf({"spool-half-a": _half(cfg, "a"), "spool-half-b": _half(cfg, "b")})


def half(cfg: SpoolConfig, h: str) -> Manifold:
    return _half(_geometry_key(cfg), h)


def stl(cfg: SpoolConfig, h: str) -> bytes:
    return _stl(_geometry_key(cfg), h)


def three_mf(cfg: SpoolConfig) -> bytes:
    return _3mf(_geometry_key(cfg))
