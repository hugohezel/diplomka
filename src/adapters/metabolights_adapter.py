"""Retrieve the public MetaboLights study and its ISA investigation metadata."""

import re
from pathlib import Path
from urllib.parse import unquote

from ..clients.http_client import fetch_json
from .common import finish_record, local_value, record_url


REPOSITORY = "metabolights"
DISPLAY_NAME = "MetaboLights"
HOSTS = {"www.ebi.ac.uk", "ebi.ac.uk"}
API_URL = "https://www.ebi.ac.uk/metabolights/ws/studies"
CHECKS_PATH = Path(__file__).with_name("metabolights.translation.json")
_ACCESSION = r"MTBLS[1-9][0-9]*"
_STUDY_PATH = re.compile(
    rf"/metabolights/(?:studies/|editor/|ws/studies/(?:public/study/)?)?({_ACCESSION})/?", re.I
)


def extract_record_id(reference):
    value = local_value(reference, REPOSITORY)
    if re.fullmatch(_ACCESSION, value, re.I):
        return value.upper()
    url = record_url(value, HOSTS)
    match = _STUDY_PATH.fullmatch(unquote(url.path)) if url else None
    return match[1].upper() if match else None


def can_handle(reference):
    return extract_record_id(reference) is not None


def fetch(reference, *, requested_reference=None, on_event=None):
    accession = extract_record_id(reference)
    if accession is None:
        raise ValueError("Enter a MetaboLights study accession or study URL.")
    source_url = f"{API_URL}/{accession}?investigation_only=true"
    record = fetch_json(source_url, service=DISPLAY_NAME)
    study_metadata = record.get("mtblsStudy")
    investigation = record.get("isaInvestigation")
    if not isinstance(study_metadata, dict) or not isinstance(investigation, dict):
        raise ValueError("MetaboLights did not return study metadata and an ISA investigation.")
    studies = investigation.get("studies")
    if not isinstance(studies, list) or len(studies) != 1 or not isinstance(studies[0], dict):
        raise ValueError("MetaboLights did not return exactly one ISA study.")
    if studies[0].get("identifier") != accession:
        raise ValueError("MetaboLights returned a different study.")
    permissions = study_metadata.get("studyPermission")
    permission_id = permissions.get("studyId") if isinstance(permissions, dict) else None
    for identity in (investigation.get("identifier"), permission_id):
        if identity and identity != accession:
            raise ValueError("The MetaboLights record contains conflicting study accessions.")
    return finish_record(
        record, profile_path=CHECKS_PATH, display_name=DISPLAY_NAME, source_url=source_url,
        reference=requested_reference or reference, expected_id=accession, namespace="metabolights_study",
        level="object", on_event=on_event,
    )
