"""PDB accession syntax and canonical API IDs, shared by parsing and M1."""

import re
from typing import Any

from .checks import plain_text


LEGACY_ID_PATTERN = r"[1-9][a-z0-9]{3}"
EXTENDED_ID_PATTERN = r"pdb_[a-z0-9]{8}"


def normalize_pdb_id(value: Any) -> str | None:
    """Map legacy extended aliases to four characters; retain new extended IDs.

    A deposition session ID (D_...) is not a public PDB accession.
    https://www.wwpdb.org/documentation/new-format-for-pdb-ids
    """
    value = plain_text(value).lower()
    if re.fullmatch(LEGACY_ID_PATTERN, value):
        return value.upper()
    if not re.fullmatch(EXTENDED_ID_PATTERN, value):
        return None
    if value.startswith("pdb_0000") and re.fullmatch(LEGACY_ID_PATTERN, value[8:]):
        return value[8:].upper()
    return value
