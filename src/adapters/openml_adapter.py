"""Fetch the OpenML description for one dataset version (data ID)."""

import re
from pathlib import Path
from urllib.parse import parse_qs

from ..clients.http_client import fetch_json
from .common import finish_record, local_value, record_url


REPOSITORY = "openml"
DISPLAY_NAME = "OpenML"
HOSTS = {"openml.org", "www.openml.org", "api.openml.org"}
CHECKS_PATH = Path(__file__).with_name("openml.translation.json")
_NUMBER = r"[1-9][0-9]*"
_RECORD_PATH = re.compile(rf"/(?:d|api/v1/json/data)/({_NUMBER})/?")


def _data_id(reference):
    value = local_value(reference, REPOSITORY)
    if re.fullmatch(_NUMBER, value):
        return value
    url = record_url(value, HOSTS)
    if url is None:
        return None
    if match := _RECORD_PATH.fullmatch(url.path):
        return match[1]
    if url.path.rstrip("/") == "/search":
        query = parse_qs(url.query, keep_blank_values=True)
        ids = query.get("id", [])
        if query.get("type") == ["data"] and len(ids) == 1 and re.fullmatch(_NUMBER, ids[0]):
            return ids[0]
    return None


def can_handle(reference):
    return _data_id(reference) is not None


def fetch(reference, *, requested_reference=None, on_event=None):
    data_id = _data_id(reference)
    if data_id is None:
        raise ValueError("Enter an OpenML dataset ID or dataset URL.")
    source_url = f"https://www.openml.org/api/v1/json/data/{data_id}"
    record = fetch_json(source_url, service=DISPLAY_NAME)
    description = record.get("data_set_description")
    if "error" in record or not isinstance(description, dict) or str(description.get("id")) != data_id:
        raise ValueError("OpenML did not return the requested dataset description.")
    return finish_record(
        record, profile_path=CHECKS_PATH, display_name=DISPLAY_NAME, source_url=source_url,
        reference=requested_reference or reference, expected_id=data_id, namespace="openml_dataset",
        level="version", on_event=on_event,
    )
