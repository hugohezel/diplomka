"""Study-level metadata from the European Nucleotide Archive Portal."""

import re
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from ..clients.http_client import fetch_json
from .common import finish_record, local_value, record_url


REPOSITORY = "ena"
DISPLAY_NAME = "ENA"
HOSTS = {"www.ebi.ac.uk", "ebi.ac.uk"}
CHECKS_PATH = Path(__file__).with_name("ena.translation.json")
API_URL = "https://www.ebi.ac.uk/ena/portal/api/search"
_STUDY = r"(?:PRJ[EDN][A-Z][0-9]+|[EDS]RP[0-9]{6,})"


def _accession(reference):
    value = local_value(reference, REPOSITORY)
    if re.fullmatch(_STUDY, value, re.I | re.ASCII):
        return value.upper()
    url = record_url(value, HOSTS)
    if not url:
        return None
    if match := re.fullmatch(rf"/ena/browser/view/({_STUDY})/?", url.path, re.I | re.ASCII):
        return match[1].upper()
    if url.path.rstrip("/") == "/ena/portal/api/search":
        params = parse_qs(url.query)
        queries = params.get("query", [])
        if params.get("result") == ["study"] and len(queries) == 1:
            match = re.fullmatch(rf'(?:study_accession|secondary_study_accession|accession)="({_STUDY})"',
                                 queries[0], re.I | re.ASCII)
            if match:
                return match[1].upper()
    return None


def can_handle(reference):
    return _accession(reference) is not None


def fetch(reference, *, requested_reference=None, on_event=None):
    accession = _accession(reference)
    if accession is None:
        raise ValueError("Enter an ENA study accession or study URL.")
    field = "study_accession" if accession.startswith("PRJ") else "secondary_study_accession"
    query = urlencode({"result": "study", "query": f'{field}="{accession}"',
                       "format": "json", "limit": 2, "fields": "all"})
    source_url = f"{API_URL}?{query}"
    rows = fetch_json(source_url, service=DISPLAY_NAME, array=True)
    if len(rows) != 1 or not isinstance(rows[0], dict) or rows[0].get(field) != accession:
        raise ValueError("ENA did not return exactly one study matching this accession.")
    return finish_record(rows[0], profile_path=CHECKS_PATH, display_name=DISPLAY_NAME,
                         source_url=source_url, reference=requested_reference or reference,
                         expected_id=accession, namespace="ena_study", level="object", on_event=on_event)
