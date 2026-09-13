"""Zenodo references, API access, and rules for native Zenodo metadata fields."""

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import unquote

from ..clients.repository_client import fetch_and_evaluate
from ..utils.checks import Rule, evaluate_rules
from ..utils.references import extract_doi, parse_url


REPOSITORY = "zenodo"
DISPLAY_NAME = "Zenodo"
HOSTS = {"zenodo.org", "www.zenodo.org"}
API_BASE_URL = "https://zenodo.org/api/records"
DOI_FIELD = "doi"

_RECORD_ID = re.compile(r"[1-9][0-9]*")
_ZENODO_DOI = re.compile(r"10\.5281/zenodo\.([1-9][0-9]*)", re.IGNORECASE)
_RECORD_PATH = re.compile(r"/(?:records?|api/records)/([1-9][0-9]*)/?")

# These are completeness recommendations, not Zenodo publication requirements.
# All rules apply to every record, assuming users select scientific datasets.
# Paths refer directly to GET /api/records/{id}; there is no normalized record.
# Sources: https://developers.zenodo.org/#records
#          https://developers.zenodo.org/#deposit-metadata
RULES = (
    Rule(DOI_FIELD, "DOI"),
    Rule("metadata.title", "Title"),
    Rule("metadata.description", "Description", html=True),
    Rule("metadata.resource_type.type", "Resource type"),
    Rule("metadata.publication_date", "Publication date"),
    Rule("metadata.creators[].name", "Authors"),
    Rule("metadata.creators[].orcid", "ORCID authors"),
    Rule("metadata.creators[].affiliation", "Author affiliations"),
    Rule("metadata.keywords[]", "Keywords"),
    Rule("metadata.subjects[].term", "Subject terms"),
    Rule("metadata.subjects[].identifier", "Subject term identifiers"),
    Rule("metadata.subjects[].scheme", "Subject term schemes"),
    Rule("metadata.language", "Language"),
    Rule("metadata.version", "Version"),
    Rule("metadata.contributors[].name", "Contributors"),
    Rule("metadata.contributors[].type", "Contributor roles"),
    Rule("metadata.contributors[].orcid", "ORCID contributors"),
    Rule("metadata.contributors[].affiliation", "Contributor affiliations"),
    Rule("metadata.related_identifiers[].identifier", "Related identifiers"),
    Rule("metadata.related_identifiers[].relation", "Related identifier relations"),
    Rule("metadata.related_identifiers[].scheme", "Related identifier schemes"),
    Rule("metadata.references[]", "References"),
    Rule("metadata.grants[].code", "Grant codes"),
    Rule("metadata.grants[].title", "Grant titles"),
    Rule("metadata.grants[].funder.name", "Grant funders"),
    Rule("metadata.communities[].identifier", "Communities"),
    Rule("metadata.notes", "Additional notes", html=True),
    Rule("metadata.method", "Methods", html=True),
    Rule("metadata.locations[]", "Spatial coverage"),
    Rule("metadata.dates[]", "Temporal coverage"),
)


def extract_record_id(reference: str) -> str | None:
    """Recognize complete Zenodo references, never substrings on other domains."""
    reference = reference.strip()
    if _RECORD_ID.fullmatch(reference):
        return reference

    doi = extract_doi(reference)
    if doi is not None:
        match = _ZENODO_DOI.fullmatch(doi)
        return match.group(1) if match else None

    url = parse_url(reference)
    if url is None or url.hostname not in HOSTS:
        return None

    path = unquote(url.path)
    match = _RECORD_PATH.fullmatch(path)
    if not match and path.startswith("/doi/"):
        match = _ZENODO_DOI.fullmatch(path.removeprefix("/doi/"))
    return match.group(1) if match else None


def can_handle(reference: str) -> bool:
    return extract_record_id(reference) is not None


def evaluate(repository_response: Mapping[str, Any]) -> list[dict[str, Any]]:
    metadata = repository_response.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ValueError("Zenodo response does not contain metadata object.")

    return evaluate_rules(repository_response, RULES)


def fetch(reference: str) -> dict[str, Any]:
    record_id = extract_record_id(reference)
    if record_id is None:
        raise ValueError("Invalid Zenodo reference.")

    return fetch_and_evaluate(
        repository=REPOSITORY,
        display_name=DISPLAY_NAME,
        source_url=f"{API_BASE_URL}/{record_id}",
        reference=reference,
        doi_field=DOI_FIELD,
        evaluator=evaluate,
    )
