"""Configuration loader — YAML files in BL_CONFIG_DIR + environment variables.

SRS doc 02 §16: all parameters configurable, no hardcoded values.
Configs are loaded once and exposed as typed, read-only mappings.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(os.getenv("BL_CONFIG_DIR", "configs"))


class ConfigError(Exception):
    pass


@lru_cache(maxsize=None)
def load(name: str) -> dict[str, Any]:
    """Load `configs/<name>.yaml`. Cached; call `load.cache_clear()` to hot-reload."""
    path = CONFIG_DIR / f"{name}.yaml"
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping at top level")
    return data


def engine(name: str) -> dict[str, Any]:
    """Per-engine parameter block from engines.yaml."""
    cfg = load("engines").get(name)
    if cfg is None:
        raise ConfigError(f"engines.yaml has no section '{name}'")
    return cfg


def env(key: str, default: str = "") -> str:
    return os.getenv(key, default)
