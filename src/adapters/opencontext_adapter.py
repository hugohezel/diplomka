"""Retrieve native Open Context GeoJSON-LD without borrowing project metadata."""

import re
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import unquote, urlencode

from ..clients.http_client import fetch_json
from ..clients.repository_client import evaluation_response
from ..utils.references import extract_doi, parse_url
from ..utils.translation_checks import EvaluationContext, evaluate_translation, load_translation


REPOSITORY = "opencontext"
DISPLAY_NAME = "Open Context"
HOSTS = {"opencontext.org", "www.opencontext.org"}
BASE_URL = "https://opencontext.org"
CHECKS_PATH = Path(__file__).with_name("opencontext_checks.json")
USER_AGENT = "oc-api-client"
_UUID = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
_RECORD_PATH = re.compile(
    rf"/(projects|subjects|media|documents|tables)/({_UUID})(?:\.json(?:ld)?)?/?", re.I
)


def parse_reference(reference):
    """Return a canonical record URL; restrict requests to scientific record routes."""
    reference = reference.strip()
    if reference.lower().startswith(("opencontext.org/", "www.opencontext.org/")):
        reference = "https://" + reference
    url = parse_url(reference)
    if url is None or url.hostname not in HOSTS:
        return None
    match = _RECORD_PATH.fullmatch(unquote(url.path))
    return f"{BASE_URL}/{match[1].lower()}/{match[2].lower()}" if match else None


def can_handle(reference):
    return parse_reference(reference) is not None or re.fullmatch(_UUID, reference.strip(), re.I) is not None


def _record_for_uuid(uuid):
    """Resolve a UUID through the documented identifier search, retaining its level."""
    query_url = BASE_URL + "/query/.json?" + urlencode({
        "id": uuid, "response": "metadata,uri-meta", "rows": 2,
    })
    response = fetch_json(query_url, service=DISPLAY_NAME, user_agent=USER_AGENT)
    rows = response.get("oc-api:has-results")
    if not isinstance(rows, list):
        raise ValueError("Open Context did not return an identifier search result list.")
    matches = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        url = row.get("href") or row.get("uri")
        canonical = parse_reference(url) if isinstance(url, str) else None
        if canonical and canonical.rsplit("/", 1)[-1] == uuid.lower():
            matches.add(canonical)
    if len(matches) != 1:
        raise ValueError("No unique Open Context data record was found; enter its record URL or DOI.")
    return matches.pop()


def evaluate(repository_response, *, reference=None, source_url=None, lookup=None, semantic=None, on_event=None):
    record_id = repository_response.get("id")
    if not isinstance(record_id, str) or parse_reference(record_id) is None:
        raise ValueError("Open Context response does not identify a supported data record.")
    if not isinstance(repository_response.get("@context"), (str, list, Mapping)):
        raise ValueError("Open Context response does not contain a JSON-LD context.")
    canonical = parse_reference(reference) if reference else None
    uuid = reference.strip().lower() if reference and re.fullmatch(_UUID, reference.strip(), re.I) else None
    context = EvaluationContext(
        reference=reference, expected_record_id=canonical or uuid,
        expected_identifier=extract_doi(reference) if reference else None,
        expected_namespace="opencontext_record" if canonical else "uuid" if uuid else None,
        requested_level="object", source_url=source_url,
    )
    profile = load_translation(CHECKS_PATH)
    if profile["repository"] != REPOSITORY:
        raise ValueError("The translation layer does not describe Open Context.")
    return evaluate_translation(repository_response, profile, context=context, lookup=lookup, semantic=semantic, on_event=on_event)


def fetch(reference, *, requested_reference=None, on_event=None):
    canonical = parse_reference(reference)
    if canonical is None and re.fullmatch(_UUID, reference.strip(), re.I):
        canonical = _record_for_uuid(reference.strip().lower())
    if canonical is None:
        raise ValueError("Invalid Open Context record reference.")
    source_url = canonical + ".json"
    response = fetch_json(source_url, service=DISPLAY_NAME, user_agent=USER_AGENT)
    original = requested_reference or reference
    checks = evaluate(response, reference=original, source_url=source_url, on_event=on_event)
    # Only identifiers belonging to this object may drive aggregator lookups.
    # A subject's parent project DOI is deliberately never substituted.
    identifiers = response.get("dc-terms:identifier", [])
    if not isinstance(identifiers, list):
        identifiers = [identifiers]
    doi = next((value for item in identifiers if isinstance(item, str)
                and (value := extract_doi(item))), None)
    return evaluation_response(
        repository=REPOSITORY, display_name=DISPLAY_NAME, source_url=source_url,
        repository_response=response, record_checks=checks, doi=doi, on_event=on_event,
    )
