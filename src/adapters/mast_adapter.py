"""Retrieve one CAOM observation in the native MAST result envelope."""

import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from ..clients.http_client import fetch_json
from .common import finish_record, local_value, record_url


REPOSITORY = "mast"
DISPLAY_NAME = "MAST"
HOSTS = {"mast.stsci.edu"}
API_URL = "https://mast.stsci.edu/api/v0/invoke"
CHECKS_PATH = Path(__file__).with_name("mast.translation.json")
_NUMBER = re.compile(r"[1-9][0-9]*")
_ACCESSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}")
_COLLECTION = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,39}")
_FILTERS = {"obsid": _NUMBER, "objID": _NUMBER, "obs_id": _ACCESSION, "obs_collection": _COLLECTION}
_COLLECTION_NAMES = {"GALEX", "HST", "IUE", "JWST", "TESS"}


def _query_filters(request, api):
    if not isinstance(request, dict):
        return None
    if api and request.get("service") == "Mast.Caom.Filtered":
        params = request.get("params")
        rows = params.get("filters") if isinstance(params, dict) else None
    elif not api and request.get("service") == "CAOMFILTERED":
        rows = request.get("inputText")
    else:
        return None
    if not isinstance(rows, list):
        return None
    filters = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("freeText"):
            return None
        key, values = row.get("paramName"), row.get("values")
        if not isinstance(key, str) or key not in _FILTERS or key in filters:
            return None
        if not isinstance(values, list) or len(values) != 1 or type(values[0]) not in (str, int):
            return None
        value = str(values[0])
        if not _FILTERS[key].fullmatch(value):
            return None
        filters[key] = value
    return filters if "obsid" in filters or "obs_id" in filters else None


def parse_reference(reference):
    candidate = local_value(reference, REPOSITORY)
    prefixed = reference.strip().lower().startswith("mast:")
    if _NUMBER.fullmatch(candidate):
        return {"obsid": candidate}
    if (prefixed or candidate.isdecimal()) and _ACCESSION.fullmatch(candidate):
        return {"obs_id": candidate}
    collection, _, accession = candidate.partition("/")
    if ((prefixed or collection.upper() in _COLLECTION_NAMES)
            and _COLLECTION.fullmatch(collection) and _ACCESSION.fullmatch(accession)):
        return {"obs_collection": collection, "obs_id": accession}
    url = record_url(candidate, HOSTS)
    if url is None:
        return None
    api = url.path.rstrip("/") == "/api/v0/invoke"
    if not api and url.path != "/portal/Mashup/Clients/Mast/Portal.html":
        return None
    query = parse_qs(url.query).get("request" if api else "searchQuery", [])
    if len(query) != 1:
        return None
    try:
        return _query_filters(json.loads(query[0]), api)
    except (ValueError, RecursionError):
        return None


def can_handle(reference):
    return parse_reference(reference) is not None


def fetch(reference, *, requested_reference=None, on_event=None):
    filters = parse_reference(reference)
    if not filters:
        raise ValueError("Enter a MAST observation identifier or an exact observation URL.")
    request = {
        "service": "Mast.Caom.Filtered", "format": "json", "pagesize": 2, "page": 1,
        "params": {"columns": "*", "filters": [
            {"paramName": key, "values": [value]} for key, value in filters.items()
        ]},
    }
    source_url = API_URL + "?" + urlencode({"request": json.dumps(request, separators=(",", ":"))})
    record = fetch_json(source_url, service=DISPLAY_NAME)
    if record.get("status") != "COMPLETE":
        raise ValueError("MAST did not return a completed observation query.")
    rows, paging = record.get("data"), record.get("paging")
    if (not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict)
            or not isinstance(paging, dict) or paging.get("rowsFiltered") != 1):
        raise ValueError("Enter an exact MAST query identifying a single observation row.")
    row = rows[0]
    if any(str(row.get(key, "")).casefold() != value.casefold() for key, value in filters.items()):
        raise ValueError("MAST returned a different observation.")
    obsid = str(row.get("obsid", ""))
    if not _NUMBER.fullmatch(obsid):
        raise ValueError("The observation lacks a valid MAST Product Group ID.")
    return finish_record(
        record, profile_path=CHECKS_PATH, display_name=DISPLAY_NAME, source_url=source_url,
        reference=requested_reference or reference, expected_id=obsid, namespace="mast_observation",
        level="object", on_event=on_event,
    )
