"""Offline syntax and checksum validation for metadata identifiers."""

import re
from typing import Any
from urllib.parse import quote, unquote

from .checks import plain_text
from .references import DOI_HOSTS, extract_doi, parse_url
from .pdb_identifiers import normalize_pdb_id


UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
)
ORCID_PATTERN = re.compile(r"[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]")
ROR_PATTERN = re.compile(r"0[0-9a-hjkmnp-tv-z]{6}[0-9]{2}")
CROCKFORD_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"
ROR_URL_PREFIXES = ("https://ror.org/", "http://ror.org/", "ror.org/")


def identifier_present(value: Any) -> bool:
    return bool(plain_text(value)) or (
        isinstance(value, int) and not isinstance(value, bool) and value > 0
    )


def orcid_id(value: Any) -> str | None:
    """Return the bare identifier only after format and checksum validation."""
    value = plain_text(value)
    if value.startswith(("https://orcid.org/", "http://orcid.org/")):
        value = value.split("orcid.org/", 1)[1]
    if not ORCID_PATTERN.fullmatch(value):
        return None

    digits = value.replace("-", "")
    # ORCID uses ISO 7064 MOD 11-2 for its final check digit.
    total = 0
    for digit in digits[:-1]:
        total = (total + int(digit)) * 2
    checksum = (12 - total % 11) % 11
    expected = "X" if checksum == 10 else str(checksum)
    return value if digits[-1] == expected else None


def valid_orcid(value: Any) -> bool:
    return orcid_id(value) is not None


def ror_id(value: Any) -> str | None:
    value = plain_text(value)
    for prefix in ROR_URL_PREFIXES:
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    if not ROR_PATTERN.fullmatch(value):
        return None

    # Decode Crockford base32, then validate the two MOD 97-10 check digits.
    number = 0
    for char in value[:7]:
        number = number * 32 + CROCKFORD_ALPHABET.index(char)
    checksum = 98 - (number * 100) % 97
    return value if int(value[-2:]) == checksum else None


def identifier_syntax(
    value: Any, *, local_scheme: str | None = None
) -> tuple[str | None, bool, str | None]:
    """Return the recognized scheme, syntax validity and optional resolver URL."""
    if local_scheme is not None:
        if local_scheme == "pdb:record-id":
            return local_scheme, normalize_pdb_id(value) is not None, None
        valid = (
            not isinstance(value, bool)
            and isinstance(value, (str, int))
            and bool(re.fullmatch(r"[1-9][0-9]*", str(value).strip()))
        )
        return local_scheme, valid, None

    value = plain_text(value)
    if not value or any(ord(char) < 32 for char in value):
        return None, False, None

    doi = extract_doi(value)
    if doi is not None:
        return "DOI", True, f"https://doi.org/{quote(doi, safe='/')}"

    url = parse_url(value)
    lower_value = value.lower()
    if lower_value.startswith(("doi:", "10.")) or (
        url and url.hostname in DOI_HOSTS
    ):
        return "DOI", False, None

    handle = value[4:] if lower_value.startswith("hdl:") else value
    if url and url.hostname == "hdl.handle.net":
        handle = unquote(url.path).lstrip("/")
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)*/[^\s]+", handle):
        return "Handle", True, f"https://hdl.handle.net/{quote(handle, safe='/')}"
    if lower_value.startswith("hdl:") or (
        url and url.hostname == "hdl.handle.net"
    ):
        return "Handle", False, None

    if lower_value.startswith("ark:"):
        valid = bool(re.fullmatch(r"ark:/[0-9]{5}/[^\s]+", value, re.I))
        canonical = "ark:" + value[4:]
        resolver = f"https://n2t.net/{quote(canonical, safe='/:')}" if valid else None
        return "ARK", valid, resolver

    if lower_value.startswith("urn:"):
        valid = bool(re.fullmatch(
            r"urn:[a-zA-Z0-9][a-zA-Z0-9-]{1,31}:[^\s]+", value, re.I
        ))
        if lower_value.startswith("urn:uuid:"):
            valid = bool(UUID_PATTERN.fullmatch(value[9:]))
        return "URN", valid, None

    if UUID_PATTERN.fullmatch(value):
        return "UUID", True, None
    if url and lower_value.startswith(("https://", "http://")):
        return "URL", True, value
    return None, False, None
