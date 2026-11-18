"""Shared transformations for controlled values; no assessment outcomes."""

import re

from ..utils.checks import normalize_text


def canonical_code(value, supported):
    text = normalize_text(value)
    for code in supported:
        spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", code)
        if text in {normalize_text(code), normalize_text(spaced)}:
            return code
    return None
