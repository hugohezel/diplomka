"""Validate prepared identifier candidates, preserving their original context."""

import re
from urllib.parse import quote

from ..utils.checks import plain_text
from ..utils.metadata_identifiers import orcid_id
from ..utils.references import parse_url
from .model import outcome


def _isbn_issn(value, scheme):
    if scheme == "isbn" and re.fullmatch(r"97[89][0-9]{10}", value):
        return sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(value)) % 10 == 0
    length = 10 if scheme == "isbn" else 8
    if not re.fullmatch(rf"[0-9]{{{length - 1}}}[0-9X]", value):
        return False
    return sum((10 if c == "X" else int(c)) * (length - i) for i, c in enumerate(value)) % 11 == 0


def _ror(value):
    if not re.fullmatch(r"0[0-9a-hj-km-np-tv-z]{6}[0-9]{2}", value):
        return False
    alphabet = "0123456789abcdefghjkmnpqrstvwxyz"
    number = 0
    for char in value[:7]:
        number = number * 32 + alphabet.index(char)
    return int(value[-2:]) == 98 - (number * 100) % 97


def _gnd(value):
    if not re.fullmatch(r"[0-9]+(?:-[0-9X])?", value):
        return False
    compact = value.replace("-", "")
    if len(compact) < 2:
        return False
    total = sum(int(c) * weight for weight, c in enumerate(reversed(compact[:-1]), 2))
    check = total % 11 if "-" in value else (11 - total % 11) % 11
    return compact[-1] == ("X" if check == 10 else str(check))


def validate_identifier(identifier, definitions):
    """Assess a normalized candidate without repeating its transformations."""
    value = identifier["value"]
    selected, declared = identifier["namespace"], identifier["declaredScheme"]
    detected, scheme = identifier["detectedNamespace"], identifier["suppliedScheme"]
    text = str(value) if isinstance(value, int) and not isinstance(value, bool) else plain_text(value)
    result = {key: identifier[key] for key in ("value", "namespace", "canonical", "declaredScheme")}
    if scheme is not None and (not isinstance(scheme, str) or not scheme.strip()):
        return outcome("FAIL", "A supplied scheme declaration must be a nonblank string.", **result)
    if not text or any(ord(c) < 32 for c in text):
        return outcome("FAIL", "Identifier is blank, malformed or of an unsupported value type.", **result)
    if selected not in definitions:
        return outcome("UNSURE" if selected else "FAIL", "No shared validator is available for this namespace.", **result)
    definition = definitions[selected]
    if isinstance(value, int) and not definition.get("integer"):
        return outcome("FAIL", "This namespace requires a string identifier.", **result)
    compatible_url = declared == "url" and parse_url(text) is not None
    if declared and declared != selected and not compatible_url:
        return outcome("FAIL", "The scheme declaration contradicts the identifier namespace.", **result)
    if detected and detected not in {"url", selected}:
        return outcome("FAIL", "The recognized PID contradicts its declared namespace.", **result)
    validators = {
        "orcid": lambda s: orcid_id(s) is not None,
        "url": lambda s: parse_url(s) is not None,
        "isbn": lambda s: _isbn_issn(s, "isbn"),
        "issn": lambda s: _isbn_issn(s, "issn"),
        "ror": _ror, "gnd": _gnd,
    }
    validator = definition.get("validator")
    if validator and validator not in validators:
        return outcome("UNSURE", "The namespace's validator has not been implemented.", **result)
    canonical = identifier["canonical"]
    valid = validators[validator](canonical) if validator else bool(re.fullmatch(definition["pattern"], canonical))
    if selected == "urn" and canonical.casefold().startswith("urn:uuid:"):
        valid = bool(re.fullmatch(definitions["uuid"]["pattern"], canonical[9:]))
    if valid and "resolver" in definition:
        result["resolver"] = definition["resolver"].format(value=quote(canonical, safe="/:"))
    checksum = validator in {"isbn", "issn", "orcid", "gnd", "ror"}
    message = ("Namespace syntax and checksum accepted." if checksum else "Namespace syntax accepted.") if valid else (
        "Invalid namespace syntax or checksum." if checksum else "Invalid namespace syntax.")
    return outcome("PASS" if valid else "FAIL", message, **result)
