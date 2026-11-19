"""Retrieve a PANGAEA dataset's native Schema.org JSON-LD metadata export."""

import re
from pathlib import Path
from urllib.parse import unquote

from ..clients.http_client import fetch_json
from ..utils.references import extract_doi
from .common import finish_record, local_value, record_url


REPOSITORY = "pangaea"
DISPLAY_NAME = "PANGAEA"
HOSTS = {"doi.pangaea.de"}
CHECKS_PATH = Path(__file__).with_name("pangaea.translation.json")
_DOI = re.compile(r"10\.1594/PANGAEA\.([1-9][0-9]*)", re.I)


def dataset_doi(reference):
    value = local_value(reference, REPOSITORY)
    url = record_url(value, HOSTS)
    candidate = unquote(url.path).strip("/") if url else extract_doi(value) or value
    if re.fullmatch(r"PANGAEA\.[1-9][0-9]*", candidate, re.I):
        candidate = "10.1594/" + candidate
    elif value != reference.strip() and re.fullmatch(r"[1-9][0-9]*", candidate):
        candidate = "10.1594/PANGAEA." + candidate
    match = _DOI.fullmatch(candidate)
    return f"10.1594/PANGAEA.{match[1]}" if match else None


def can_handle(reference):
    return dataset_doi(reference) is not None


def fetch(reference, *, requested_reference=None, on_event=None):
    doi = dataset_doi(reference)
    if not doi:
        raise ValueError("Enter a PANGAEA dataset DOI or record URL.")
    url = f"https://doi.pangaea.de/{doi}?format=metadata_jsonld"
    record = fetch_json(url, service=DISPLAY_NAME, accept="application/ld+json, application/json")
    identifier = record.get("identifier")
    if record.get("@type") != "Dataset" or not isinstance(identifier, str) or dataset_doi(identifier) != doi:
        raise ValueError("PANGAEA did not return the requested dataset.")
    return finish_record(
        record, profile_path=CHECKS_PATH, display_name=DISPLAY_NAME, source_url=url,
        reference=requested_reference or reference, expected_id=doi, namespace="doi",
        level="object", doi=doi, on_event=on_event,
    )
