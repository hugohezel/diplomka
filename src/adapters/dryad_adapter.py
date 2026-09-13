"""Dryad references and presence rules for native dataset metadata."""

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote, unquote

from ..clients.repository_client import fetch_and_evaluate
from ..utils.checks import Rule, evaluate_rules
from ..utils.references import extract_doi, parse_url


REPOSITORY = "dryad"
DISPLAY_NAME = "Dryad"
HOSTS = {"datadryad.org", "www.datadryad.org"}
API_BASE_URL = "https://datadryad.org/api/v2/datasets"
DOI_FIELD = "identifier"

_DRYAD_DOI = re.compile(r"10\.5061/dryad\.[^/?#\s]+", re.IGNORECASE)
_DATASET_PATH = re.compile(
    r"/(?:dataset|stash/dataset|resource|api/v2/datasets)/"
    r"(?:doi:)?(10\.5061/dryad\.[^/?#\s]+)/?",
    re.IGNORECASE,
)

# Direct paths in GET /api/v2/datasets/{doi}; no normalized metadata model.
# Source: https://datadryad.org/openapi.yml (dataset, dc_metadata, author, funder).
# Check the scalar affiliation fields once, not their affiliations[] aliases.
RULES = (
    Rule(DOI_FIELD, "DOI"),
    Rule("title", "Title"),
    Rule("abstract", "Description", html=True),
    Rule("publicationDate", "Publication date"),
    Rule("authors[].firstName", "First names of authors"),
    Rule("authors[].lastName", "Last names of authors"),
    Rule("authors[].orcid", "ORCID authors"),
    Rule("authors[].affiliation", "Author affiliations"),
    Rule("authors[].affiliationROR", "ROR author affiliations"),
    Rule("keywords[]", "Keywords"),
    Rule("fieldOfScience", "Field of science"),
    Rule("versionNumber", "Version"),
    Rule("relatedWorks[].identifier", "Related works identifiers"),
    Rule("relatedWorks[].relationship", "Related works relationships"),
    Rule("relatedWorks[].identifierType", "Related works identifier schemes"),
    Rule("funders[].organization", "Funder organizations"),
    Rule("funders[].identifier", "Funder identifiers"),
    Rule("funders[].identifierType", "Funder identifier schemes"),
    Rule("funders[].awardNumber", "Grant numbers"),
    Rule("funders[].awardDescription", "Grant descriptions"),
    Rule("methods", "Methods", html=True),
    Rule("usageNotes", "Usage notes", html=True),
    Rule("locations[]", "Spatial coverage"),
)


def extract_dataset_doi(reference: str) -> str | None:
    doi = extract_doi(reference)
    if doi is not None:
        return f"doi:{doi.lower()}" if _DRYAD_DOI.fullmatch(doi) else None

    url = parse_url(reference)
    if url is None or url.hostname not in HOSTS:
        return None
    match = _DATASET_PATH.fullmatch(unquote(url.path))
    return f"doi:{match.group(1).lower()}" if match else None


def can_handle(reference: str) -> bool:
    return extract_dataset_doi(reference) is not None


def evaluate(repository_response: Mapping[str, Any]) -> list[dict[str, Any]]:
    if repository_response.get("id") is None:
        raise ValueError("Dryad response does not contain a record ID.")
    return evaluate_rules(repository_response, RULES)


def fetch(reference: str) -> dict[str, Any]:
    doi = extract_dataset_doi(reference)
    if doi is None:
        raise ValueError("Invalid Dryad reference.")
    return fetch_and_evaluate(
        repository=REPOSITORY,
        display_name=DISPLAY_NAME,
        source_url=f"{API_BASE_URL}/{quote(doi, safe='')}",
        reference=reference,
        doi_field=DOI_FIELD,
        evaluator=evaluate,
    )
