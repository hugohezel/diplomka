"""CERN Open Data dataset release metadata."""

import re
from pathlib import Path

from ..clients.http_client import fetch_json
from ..utils.references import extract_doi, resolve_doi
from .common import finish_record, local_value, record_url


REPOSITORY = "cern-open-data"
DISPLAY_NAME = "CERN Open Data"
HOSTS = {"opendata.cern.ch"}
CHECKS_PATH = Path(__file__).with_name("cern-open-data.translation.json")
API_URL = "https://opendata.cern.ch/api/records"
_RECORD = r"[1-9][0-9]*"


def _record_id(reference):
    value = local_value(reference, REPOSITORY)
    match = re.fullmatch(rf"(?:oai:cernopendata\.cern:)?({_RECORD})", value, re.I)
    if match:
        return match[1]
    url = record_url(value, HOSTS)
    if url and (match := re.fullmatch(rf"/(?:record|api/records)/({_RECORD})/?", url.path)):
        return match[1]
    return None


def _cern_doi(reference):
    doi = extract_doi(local_value(reference, REPOSITORY))
    return doi if doi and doi.lower().startswith("10.7483/opendata.") else None


def can_handle(reference):
    return bool(_record_id(reference) or _cern_doi(reference))


def fetch(reference, *, requested_reference=None, on_event=None):
    record_id = _record_id(reference)
    if record_id is None and (doi := _cern_doi(reference)):
        record_id = _record_id(resolve_doi(doi))
    if record_id is None:
        raise ValueError("Enter a CERN Open Data dataset record ID, URL or DOI.")
    source_url = f"{API_URL}/{record_id}"
    record = fetch_json(source_url, service=DISPLAY_NAME)
    metadata = record.get("metadata")
    if not isinstance(metadata, dict) or str(record.get("id")) != record_id:
        raise ValueError("CERN Open Data did not return the requested record.")
    if "recid" in metadata and str(metadata["recid"]) != record_id:
        raise ValueError("The CERN metadata and record identifiers disagree.")
    resource_type = metadata.get("type")
    if not isinstance(resource_type, dict) or resource_type.get("primary") != "Dataset":
        raise ValueError("The CERN Open Data record must describe a dataset.")
    doi = extract_doi(metadata["doi"]) if isinstance(metadata.get("doi"), str) else None
    original = requested_reference or reference
    requested_doi = extract_doi(local_value(original, REPOSITORY))
    if requested_doi and (doi or "").lower() != requested_doi.lower():
        raise ValueError("The retrieved CERN dataset does not declare the requested DOI.")
    return finish_record(record, profile_path=CHECKS_PATH, display_name=DISPLAY_NAME,
                         source_url=source_url, reference=original, expected_id=record_id,
                         namespace="cern_record", level="version", doi=doi, on_event=on_event)
