"""System-owned criteria and shared, versioned resources."""

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).parent


@lru_cache(maxsize=1)
def _catalogue():
    return json.loads((ROOT / "catalogue.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _registries():
    return json.loads((ROOT / "registries.json").read_text(encoding="utf-8"))


def catalogue():
    """Return an isolated copy; callers cannot mutate the system definitions."""
    return deepcopy(_catalogue())


def registries():
    return deepcopy(_registries())
