"""Retrieve archaeological subject records from the Open Context GeoJSON-LD API."""

import re
from pathlib import Path
from urllib.parse import unquote, urlencode

from ..clients.http_client import fetch_json
from ..utils.references import extract_doi
from .common import finish_record, local_value, record_url


REPOSITORY = "opencontext"
DISPLAY_NAME = "Open Context"
HOSTS = {"opencontext.org", "www.opencontext.org"}
BASE_URL = "https://opencontext.org"
CHECKS_PATH = Path(__file__).with_name("opencontext.translation.json")
_UUID = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
_SUBJECT_PATH = re.compile(rf"/subjects/({_UUID})(?:\.json(?:ld)?)?/?", re.I)
_ARK = re.compile(r"ark:/[0-9]{5}/[^\s?#]+")


def _subject_uuid(reference):
    url = record_url(reference, HOSTS)
    match = _SUBJECT_PATH.fullmatch(unquote(url.path)) if url else None
    return match[1].lower() if match else None


def _ark_value(reference):
    if not isinstance(reference, str):
        return None
    url = record_url(reference, {"n2t.net"})
    value = unquote(url.path).lstrip("/") if url else reference
    return value if _ARK.fullmatch(value) else None


def _identity(reference):
    value = local_value(reference, REPOSITORY)
    if re.fullmatch(_UUID, value, re.I):
        return "uuid", value.lower()
    if uuid := _subject_uuid(value):
        return "uuid", uuid
    if reference.strip().lower().startswith("opencontext:") and (ark := _ark_value(value)):
        return "ark", ark
    return None


def can_handle(reference):
    return _identity(reference) is not None


def _subject_for_ark(ark):
    query = urlencode({"type": "subjects", "id": ark, "response": "metadata,uri-meta", "rows": 2})
    result = fetch_json(f"{BASE_URL}/query/.json?{query}", service=DISPLAY_NAME, user_agent="oc-api-client")
    rows = result.get("oc-api:has-results")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("The ARK does not identify a unique Open Context subject.")
    url = rows[0].get("href") or rows[0].get("uri")
    uuid = _subject_uuid(url) if isinstance(url, str) else None
    if not uuid:
        raise ValueError("Open Context returned an invalid subject URL.")
    return uuid


def fetch(reference, *, requested_reference=None, on_event=None):
    identity = _identity(reference)
    if not identity:
        raise ValueError("Enter an Open Context subject URL, UUID or repository-prefixed ARK.")
    namespace, value = identity
    uuid = value if namespace == "uuid" else _subject_for_ark(value)
    source_url = f"{BASE_URL}/subjects/{uuid}.json"
    record = fetch_json(source_url, service=DISPLAY_NAME, user_agent="oc-api-client")
    native_id = record.get("id")
    if (not isinstance(native_id, str) or _subject_uuid(native_id) != uuid
            or str(record.get("uuid")).lower() != uuid):
        raise ValueError("Open Context returned a different subject.")
    if record.get("type") != "FeatureCollection" or not record.get("@context"):
        raise ValueError("Open Context did not return a subject GeoJSON-LD record.")
    identifiers = record.get("dc-terms:identifier", [])
    if not isinstance(identifiers, list):
        identifiers = [identifiers]
    if namespace == "ark" and value not in {_ark_value(item) for item in identifiers}:
        raise ValueError("The Open Context subject does not declare the requested ARK.")
    doi = next((match for item in identifiers if isinstance(item, str) and (match := extract_doi(item))), None)
    return finish_record(
        record, profile_path=CHECKS_PATH, display_name=DISPLAY_NAME, source_url=source_url,
        reference=requested_reference or reference, expected_id=value, namespace=namespace,
        level="object", doi=doi, on_event=on_event,
    )
