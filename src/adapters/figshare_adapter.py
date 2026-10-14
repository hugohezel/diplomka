"""Figshare article references, versions, and native metadata evaluation."""

import re
from collections.abc import Mapping
from functools import partial
from typing import Any
from urllib.parse import unquote

from ..clients.repository_client import fetch_and_evaluate
from ..utils.checks import Rule
from ..utils.generic_metadata_checks import evaluate_generic_metadata
from ..utils.generic_metadata_model import EvaluationContext
from ..utils.references import extract_doi, parse_url


REPOSITORY = "figshare"
DISPLAY_NAME = "Figshare"
HOSTS = {"figshare.com", "www.figshare.com", "api.figshare.com"}
API_BASE_URL = "https://api.figshare.com/v2/articles"
DOI_FIELD = "doi"

_FIGSHARE_DOI = re.compile(
    r"10\.6084/m9\.figshare\.(?P<id>[1-9][0-9]*)(?:\.v(?P<version>[1-9][0-9]*))?",
    re.IGNORECASE,
)
_ARTICLE_PATH = re.compile(
    r"/articles/(?:[^/]+/[^/]+/)?(?P<id>[1-9][0-9]*)"
    r"(?:/(?P<version>[1-9][0-9]*))?/?"
)
_API_PATH = re.compile(
    r"/v2/articles/(?P<id>[1-9][0-9]*)(?:/versions/(?P<version>[1-9][0-9]*))?/?"
)

# Direct paths in GET /v2/articles/{id}[/versions/{version}].
# Source: https://docs.figshare.com/swagger.json (ArticleComplete).
# keywords and tags are aliases, so only keywords is checked. Standard public
# article metadata does not expose author affiliations, language, or coverage.
RULES = (
    Rule(DOI_FIELD, "DOI"),
    Rule("title", "Title"),
    Rule("description", "Description", html=True),
    Rule("defined_type_name", "Resource type"),
    Rule("published_date", "Publication date"),
    Rule("authors[].full_name", "Authors"),
    Rule("authors[].orcid_id", "ORCID authors"),
    Rule("keywords[]", "Keywords"),
    Rule("categories[].title", "Subject categories"),
    Rule("categories[].id", "Subject category identifiers"),
    Rule("version", "Version"),
    Rule("related_materials[].identifier", "Related identifiers"),
    Rule("related_materials[].relation", "Related identifier relations"),
    Rule("related_materials[].identifier_type", "Related identifier schemes"),
    Rule("related_materials[].title", "Related resource titles"),
    Rule("references[]", "References"),
    Rule("funding", "Funding description", html=True),
    Rule("funding_list[].grant_code", "Grant codes"),
    Rule("funding_list[].title", "Grant titles"),
    Rule("funding_list[].funder_name", "Grant funders"),
    Rule("resource_doi", "Related publication DOI"),
    Rule("resource_title", "Related publication title"),
)


def extract_article_reference(reference: str) -> tuple[str, str | None] | None:
    """Return the article ID and optional version from a complete DOI or URL."""
    doi = extract_doi(reference)
    if doi is not None:
        match = _FIGSHARE_DOI.fullmatch(doi)
    else:
        url = parse_url(reference)
        if url is None or url.hostname not in HOSTS:
            return None
        pattern = _API_PATH if url.hostname == "api.figshare.com" else _ARTICLE_PATH
        match = pattern.fullmatch(unquote(url.path))
    return (match.group("id"), match.group("version")) if match else None


def can_handle(reference: str) -> bool:
    return extract_article_reference(reference) is not None


def evaluate(
    repository_response: Mapping[str, Any], *, reference: str | None = None,
    source_url: str | None = None,
) -> list[dict[str, Any]]:
    if repository_response.get("id") is None:
        raise ValueError("Figshare response does not contain a record ID.")
    article = extract_article_reference(reference) if reference else None
    context = EvaluationContext(
        reference=reference, expected_record_id=article[0] if article else None,
        expected_version=article[1] if article else None, source_url=source_url,
    )
    return evaluate_generic_metadata(repository_response, REPOSITORY, context=context)


def fetch(reference: str) -> dict[str, Any]:
    article = extract_article_reference(reference)
    if article is None:
        raise ValueError("Invalid Figshare reference.")
    article_id, version = article
    source_url = f"{API_BASE_URL}/{article_id}"
    if version is not None:
        source_url += f"/versions/{version}"
    return fetch_and_evaluate(
        repository=REPOSITORY,
        display_name=DISPLAY_NAME,
        source_url=source_url,
        reference=reference,
        doi_field=DOI_FIELD,
        evaluator=partial(evaluate, reference=reference, source_url=source_url),
        rules=RULES,
    )
