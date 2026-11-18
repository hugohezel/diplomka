"""Retrieve ICPSR-registered DataCite metadata and apply its JSON bindings."""

import re
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import quote, unquote, urlencode

from ..clients.http_client import fetch_json
from ..clients.repository_client import evaluation_response
from ..utils.references import extract_doi, parse_url
from ..utils.translation_checks import EvaluationContext, evaluate_translation, load_translation


REPOSITORY = "icpsr"
DISPLAY_NAME = "ICPSR"
HOSTS = {"www.icpsr.umich.edu", "icpsr.umich.edu", "archive.icpsr.umich.edu"}
CHECKS_PATH = Path(__file__).with_name("icpsr_checks.json")
API_BASE_URL = "https://api.datacite.org/dois"
_DOI = re.compile(r"10\.3886/icpsr(0*[1-9][0-9]*)\.v([0-9]+(?:\.[0-9]+)*)", re.I)
_STUDY_PATH = re.compile(
    r"/(?:web|icpsrweb)/[A-Za-z0-9_-]+/studies/(0*[1-9][0-9]*)"
    r"(?:/versions/[vV]([0-9]+(?:\.[0-9]+)*))?(?:/[A-Za-z-]+)?/?"
)


def parse_reference(reference, *, allow_numeric=True):
    """Return study number, optional version and exact DOI, without network IO."""
    reference = reference.strip()
    doi = extract_doi(reference)
    if doi is not None:
        match = _DOI.fullmatch(doi)
        return (str(int(match[1])), match[2], doi.lower()) if match else None
    match = re.fullmatch(r"ICPSR\s*:?\s*(0*[1-9][0-9]*)", reference, re.I)
    if match or (allow_numeric and re.fullmatch(r"0*[1-9][0-9]*", reference)):
        return str(int(match[1] if match else reference)), None, None
    url = parse_url(reference)
    if url is None or url.hostname not in HOSTS:
        return None
    match = _STUDY_PATH.fullmatch(unquote(url.path))
    return (str(int(match[1])), match[2], None) if match else None


def can_handle(reference, *, allow_numeric=False):
    return parse_reference(reference, allow_numeric=allow_numeric) is not None


def _version(value):
    return tuple(int(part) for part in value.split("."))


def _find_doi(study, version=None):
    """Select the highest registered version, or the explicitly requested one."""
    spellings = {study, study.zfill(5)}
    query = " OR ".join(f"doi:10.3886/icpsr{number}.v*" for number in sorted(spellings))
    search_url = API_BASE_URL + "?" + urlencode({"query": query, "page[size]": 100})
    response = fetch_json(search_url, service="DataCite")
    rows = response.get("data")
    total = response.get("meta", {}).get("total")
    if not isinstance(rows, list) or not isinstance(total, int):
        raise ValueError("DataCite did not return a study search result list.")
    if total > len(rows):
        raise ValueError("This study has too many registered versions; enter its exact DOI.")
    matches = []
    for row in rows:
        doi = row.get("id") if isinstance(row, Mapping) else None
        match = _DOI.fullmatch(doi) if isinstance(doi, str) else None
        if match and int(match[1]) == int(study) and (version is None or _version(match[2]) == _version(version)):
            matches.append((_version(match[2]), doi.lower()))
    if not matches:
        raise ValueError("No registered ICPSR study/version was found. Check the study number or enter its DOI.")
    return max(matches)[1], search_url


def evaluate(repository_response, *, reference=None, source_url=None, expected_doi=None, lookup=None, semantic=None, on_event=None):
    data = repository_response.get("data")
    attributes = data.get("attributes") if isinstance(data, Mapping) else None
    if not isinstance(attributes, Mapping):
        raise ValueError("DataCite response does not contain DOI metadata attributes.")
    doi = attributes.get("doi")
    match = _DOI.fullmatch(doi) if isinstance(doi, str) else None
    if not match or not isinstance(data.get("id"), str) or data["id"].lower() != doi.lower():
        raise ValueError("The response is not an ICPSR DOI metadata record.")
    parsed = parse_reference(reference) if reference else None
    if parsed and (int(parsed[0]) != int(match[1]) or (parsed[1] and _version(parsed[1]) != _version(match[2]))):
        raise ValueError("Retrieved metadata belong to a different ICPSR study/version.")
    if expected_doi and expected_doi.lower() != doi.lower():
        raise ValueError("DataCite returned a different DOI than requested.")
    if attributes.get("url"):
        landing = parse_reference(attributes["url"], allow_numeric=False)
        if not landing or int(landing[0]) != int(match[1]) or (landing[1] and _version(landing[1]) != _version(match[2])):
            raise ValueError("The DOI landing URL does not identify the requested ICPSR study/version.")
    profile = load_translation(CHECKS_PATH)
    context = EvaluationContext(
        reference=reference, expected_identifier=(extract_doi(reference) if reference else None) or expected_doi,
        source_url=source_url, requested_level="version",
    )
    return evaluate_translation(repository_response, profile, context=context, lookup=lookup, semantic=semantic, on_event=on_event)


def fetch(reference, *, requested_reference=None, on_event=None):
    parsed = parse_reference(reference)
    if parsed is None:
        raise ValueError("Enter an ICPSR study number, study URL or version DOI.")
    study, version, doi = parsed
    search_url = None
    if doi is None:
        doi, search_url = _find_doi(study, version)
    source_url = f"{API_BASE_URL}/{quote(doi, safe='/')}?affiliation=true&publisher=true"
    response = fetch_json(source_url, service="DataCite")
    record_checks = evaluate(response, reference=requested_reference or reference, source_url=source_url, expected_doi=doi, on_event=on_event)
    result = evaluation_response(
        repository=REPOSITORY, display_name=DISPLAY_NAME, source_url=source_url,
        repository_response=response, record_checks=record_checks, doi=doi, on_event=on_event,
    )
    result.update(metadataProvider="DataCite (metadata registered by ICPSR)", resolvedDoi=doi,
                  landingUrl=response["data"]["attributes"].get("url"), resolutionSourceUrl=search_url)
    return result
