"""Zenodo API access and execution of its JSON searchability translation layer."""

import re
from collections.abc import Mapping
from functools import partial
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from ..clients.repository_client import fetch_and_evaluate
from ..utils.references import extract_doi, parse_url
from ..utils.translation_checks import (
    EvaluationContext, evaluate_translation, load_translation,
)


REPOSITORY = "zenodo"
DISPLAY_NAME = "Zenodo"
HOSTS = {"zenodo.org", "www.zenodo.org"}
API_BASE_URL = "https://zenodo.org/api/records"
DOI_FIELD = "doi"
CHECKS_PATH = Path(__file__).with_name("zenodo_checks.json")
MEDIA_TYPE = "application/vnd.zenodo.v1+json"

_RECORD_ID = re.compile(r"[1-9][0-9]*")
_ZENODO_DOI = re.compile(r"10\.5281/zenodo\.([1-9][0-9]*)", re.IGNORECASE)
_RECORD_PATH = re.compile(r"/(?:records?|api/records)/([1-9][0-9]*)/?")


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


def evaluate(
    repository_response: Mapping[str, Any], *, reference: str | None = None,
    source_url: str | None = None, lookup=None, semantic=None, on_event=None,
) -> list[dict[str, Any]]:
    metadata = repository_response.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ValueError("Zenodo response does not contain metadata object.")

    expected_id = extract_record_id(reference) if reference else None
    expected_identifier = extract_doi(reference) if reference else None
    url = parse_url(reference) if reference else None
    if url and url.hostname in HOSTS and unquote(url.path).startswith("/doi/"):
        expected_identifier = extract_doi(unquote(url.path).removeprefix("/doi/"))
    context = EvaluationContext(
        reference=reference, expected_record_id=expected_id, source_url=source_url,
        expected_identifier=expected_identifier, expected_namespace="zenodo_record",
    )
    profile = load_translation(CHECKS_PATH)
    if profile["repository"] != REPOSITORY:
        raise ValueError("The translation layer does not describe Zenodo.")
    return evaluate_translation(repository_response, profile, context=context, lookup=lookup, semantic=semantic, on_event=on_event)


def fetch(reference: str, *, requested_reference: str | None = None, on_event=None) -> dict[str, Any]:
    record_id = extract_record_id(reference)
    if record_id is None:
        raise ValueError("Invalid Zenodo reference.")

    source_url = f"{API_BASE_URL}/{record_id}"
    return fetch_and_evaluate(
        repository=REPOSITORY,
        display_name=DISPLAY_NAME,
        source_url=source_url,
        reference=requested_reference or reference,
        doi_field=DOI_FIELD,
        accept=MEDIA_TYPE,
        evaluator=partial(evaluate, reference=requested_reference or reference, source_url=source_url, on_event=on_event),
        on_event=on_event,
    )
