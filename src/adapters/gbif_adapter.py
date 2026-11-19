"""Dataset metadata from the GBIF Registry API."""

import re
from pathlib import Path
from urllib.parse import quote

from ..clients.http_client import fetch_json
from ..utils.references import extract_doi
from .common import finish_record, local_value, record_url


REPOSITORY = "gbif"
DISPLAY_NAME = "GBIF"
HOSTS = {"gbif.org", "www.gbif.org", "api.gbif.org"}
CHECKS_PATH = Path(__file__).with_name("gbif.translation.json")
API_URL = "https://api.gbif.org/v1/dataset"
_KEY = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"


def _reference(reference):
    value = local_value(reference, REPOSITORY)
    if re.fullmatch(_KEY, value, re.I):
        return value.lower()
    doi = extract_doi(value)
    if doi and (value != reference.strip() or re.fullmatch(r"10\.15468/[a-z0-9]{6}", doi, re.I)):
        return doi.lower()
    url = record_url(value, HOSTS)
    if url:
        path = r"/v1/dataset/" if url.hostname == "api.gbif.org" else r"/(?:[a-z]{2}(?:-[a-z]+)?/)?dataset/"
        match = re.fullmatch(path + rf"({_KEY})/?", url.path, re.I)
        if match:
            return match[1].lower()
    return None


def can_handle(reference):
    return _reference(reference) is not None


def fetch(reference, *, requested_reference=None, on_event=None):
    key = _reference(reference)
    if key is None:
        raise ValueError("Enter a GBIF dataset UUID, record URL or dataset DOI.")
    original = requested_reference or reference
    requested_doi = extract_doi(local_value(original, REPOSITORY))
    if extract_doi(key):
        matches = fetch_json(f"{API_URL}/doi/{quote(key, safe='/')}?limit=2", service=DISPLAY_NAME)
        rows = matches.get("results")
        if (not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict)
                or matches.get("endOfRecords") is not True or matches.get("count", 1) != 1):
            raise ValueError("GBIF did not identify exactly one dataset for this DOI.")
        key = rows[0].get("key")
        if not isinstance(key, str) or not re.fullmatch(_KEY, key, re.I):
            raise ValueError("GBIF returned an invalid dataset key.")
        key = key.lower()
    source_url = f"{API_URL}/{key}"
    record = fetch_json(source_url, service=DISPLAY_NAME)
    if str(record.get("key")).lower() != key or not record.get("type"):
        raise ValueError("GBIF did not return the requested dataset registry record.")
    doi = extract_doi(record["doi"]) if isinstance(record.get("doi"), str) else None
    if requested_doi and (doi or "").lower() != requested_doi.lower():
        raise ValueError("The GBIF dataset does not declare the requested DOI.")
    return finish_record(record, profile_path=CHECKS_PATH, display_name=DISPLAY_NAME,
                         source_url=source_url, reference=original, expected_id=key,
                         namespace="uuid", level="object", doi=doi, on_event=on_event)
