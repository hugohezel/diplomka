"""Retrieve public MetaboLights ISA investigation metadata and apply bindings."""

import re
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import unquote

from ..clients.http_client import fetch_json
from ..clients.repository_client import evaluation_response
from ..utils.references import extract_doi, parse_url
from ..utils.translation_checks import EvaluationContext, evaluate_translation, load_translation


REPOSITORY = "metabolights"
DISPLAY_NAME = "MetaboLights"
HOSTS = {"www.ebi.ac.uk", "ebi.ac.uk"}
API_BASE_URL = "https://www.ebi.ac.uk/metabolights/ws/studies"
CHECKS_PATH = Path(__file__).with_name("metabolights_checks.json")
_ACCESSION = re.compile(r"MTBLS[1-9][0-9]*", re.I)
_STUDY_PATH = re.compile(
    r"/metabolights/(?:studies/|editor/|ws/studies/(?:public/study/)?)?"
    r"(MTBLS[1-9][0-9]*)/?", re.I,
)


def extract_record_id(reference: str) -> str | None:
    """Accept study accessions and official study URLs, never compound IDs."""
    reference = reference.strip()
    if _ACCESSION.fullmatch(reference):
        return reference.upper()
    url = parse_url(reference)
    if url is None or url.hostname not in HOSTS:
        return None
    match = _STUDY_PATH.fullmatch(unquote(url.path))
    return match[1].upper() if match else None


def can_handle(reference: str) -> bool:
    return extract_record_id(reference) is not None


def evaluate(
    repository_response: Mapping, *, reference=None, source_url=None,
    expected_record_id=None, lookup=None, semantic=None, on_event=None,
):
    investigation = repository_response.get("isaInvestigation")
    studies = investigation.get("studies") if isinstance(investigation, Mapping) else None
    if not isinstance(studies, list) or len(studies) != 1 or not isinstance(studies[0], Mapping):
        raise ValueError("MetaboLights did not return a single ISA study.")
    identifier = studies[0].get("identifier")
    if not isinstance(identifier, str) or not _ACCESSION.fullmatch(identifier):
        raise ValueError("The ISA study does not declare a MetaboLights accession.")
    identifier = identifier.upper()
    expected = expected_record_id or (extract_record_id(reference) if reference else None)
    if expected and expected != identifier:
        raise ValueError("Retrieved metadata belong to a different MetaboLights study.")
    investigation_id = investigation.get("identifier")
    if investigation_id and (not isinstance(investigation_id, str) or investigation_id.upper() != identifier):
        raise ValueError("The MetaboLights investigation and study identifiers disagree.")
    profile = load_translation(CHECKS_PATH)
    context = EvaluationContext(
        reference=reference, source_url=source_url,
        expected_record_id=expected, expected_namespace="metabolights_study",
        expected_identifier=extract_doi(reference) if reference else None,
        requested_level="object",
    )
    return evaluate_translation(repository_response, profile, context=context, lookup=lookup, semantic=semantic, on_event=on_event)


def fetch(reference: str, *, requested_reference: str | None = None, on_event=None):
    record_id = extract_record_id(reference)
    if record_id is None:
        raise ValueError("Enter a MetaboLights study accession (MTBLS…) or study URL.")
    # Explicitly avoid loading the much larger sample, assay and process graphs.
    source_url = f"{API_BASE_URL}/{record_id}?investigation_only=true"
    response = fetch_json(source_url, service=DISPLAY_NAME)
    checks = evaluate(
        response, reference=requested_reference or reference,
        expected_record_id=record_id, source_url=source_url, on_event=on_event,
    )
    result = evaluation_response(
        repository=REPOSITORY, display_name=DISPLAY_NAME, source_url=source_url,
        repository_response=response, record_checks=checks,
        # Study publications' DOIs identify articles, not the assessed dataset.
        doi=None, on_event=on_event,
    )
    result.update(accession=record_id, landingUrl=f"https://www.ebi.ac.uk/metabolights/{record_id}")
    return result
