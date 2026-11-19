"""Fetch the indexed metadata envelope of a computational entry at NOMAD Central."""

import re
from pathlib import Path

from ..clients.http_client import fetch_json
from .common import finish_record, local_value, record_url


REPOSITORY = "nomad-central"
DISPLAY_NAME = "NOMAD Central"
HOSTS = {"nomad-lab.eu"}
CHECKS_PATH = Path(__file__).with_name("nomad-central.translation.json")
_ENTRY = r"[A-Za-z0-9_-]{28}"
_API_PATH = re.compile(rf"/(?:prod/v1|backend)/api/v1/entries/(?P<entry>{_ENTRY})/?")
_GUI_PATH = re.compile(
    rf"/prod/v1/gui/(?:search/entries/|user/search/|"
    rf"user/uploads/upload/id/(?P<upload>[A-Za-z0-9_-]{{22}})/)?entry/id/(?P<entry>{_ENTRY})/?"
)


def _entry(reference):
    value = local_value(reference, REPOSITORY)
    if re.fullmatch(_ENTRY, value):
        return value, None
    url = record_url(value, HOSTS)
    if url:
        if match := _API_PATH.fullmatch(url.path):
            return match["entry"], None
        if match := _GUI_PATH.fullmatch(url.path):
            return match["entry"], match["upload"]
    return None


def can_handle(reference):
    return _entry(reference) is not None


def fetch(reference, *, requested_reference=None, on_event=None):
    identity = _entry(reference)
    if identity is None:
        raise ValueError("Enter a NOMAD Central entry ID or entry URL.")
    entry_id, upload_id = identity
    source_url = f"https://nomad-lab.eu/prod/v1/api/v1/entries/{entry_id}"
    record = fetch_json(source_url, service=DISPLAY_NAME)
    entry = record.get("data")
    if record.get("entry_id") != entry_id or not isinstance(entry, dict) or entry.get("entry_id") != entry_id:
        raise ValueError("NOMAD Central did not return the requested entry.")
    if upload_id is not None and entry.get("upload_id") != upload_id:
        raise ValueError("The NOMAD entry belongs to a different upload.")
    return finish_record(
        record, profile_path=CHECKS_PATH, display_name=DISPLAY_NAME, source_url=source_url,
        reference=requested_reference or reference, expected_id=entry_id, namespace="nomad_entry",
        level="object", on_event=on_event,
    )
