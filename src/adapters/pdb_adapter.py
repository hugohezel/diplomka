"""Evaluate native RCSB PDB entry metadata, keeping structure and article distinct.

The REST entry endpoint describes the current structure record. Entity, chain
and assembly metadata, coordinates and validation reports have separate APIs.
https://data.rcsb.org/
"""

import re
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from http.client import HTTPException
from typing import Any
from urllib.error import URLError
from urllib.parse import parse_qs, unquote

from ..clients.repository_client import fetch_and_evaluate
from ..clients.http_client import fetch_json
from ..utils.checks import CheckResult, Rule, plain_text, read_field
from ..utils.generic_metadata_model import EvaluationContext
from ..utils.metadata_checks import IdentifierTarget
from ..utils.pdb_metadata_checks import evaluate_pdb_metadata
from ..utils.pdb_identifiers import (
    EXTENDED_ID_PATTERN,
    LEGACY_ID_PATTERN,
    normalize_pdb_id,
)
from ..utils.references import extract_doi, parse_url


REPOSITORY = "pdb"
DISPLAY_NAME = "RCSB PDB"
HOSTS = {"rcsb.org", "www.rcsb.org", "data.rcsb.org", "wwpdb.org", "www.wwpdb.org"}
API_BASE_URL = "https://data.rcsb.org/rest/v1/core/entry"
DOI_FIELD = "database_2[].pdbx_DOI"

_PDB_DOI = re.compile(
    rf"10\.2210/(?:pdb(?P<legacy>{LEGACY_ID_PATTERN})|"
    rf"(?P<extended>{EXTENDED_ID_PATTERN}))/pdb", re.I,
)
_STRUCTURE_PATH = re.compile(r"/structure/([^/]+)/?", re.I)
_API_PATH = re.compile(r"/rest/v1/core/entry/([^/]+)/?", re.I)

# Direct paths in GET /rest/v1/core/entry/{id}; no synthetic metadata record.
# database_2 includes other databases: M1 selects only database_id == PDB.
# The primary citation DOI describes an article, not the structure dataset.
RULES = (
    Rule("rcsb_id", "PDB accession"),
    Rule(DOI_FIELD, "Structure DOI (PDB database row)"),
    Rule("struct.title", "Structure title"),
    Rule("struct_keywords.text", "Keywords"),
    Rule("struct_keywords.pdbx_keywords", "PDB classification"),
    Rule("audit_author[].name", "Structure authors"),
    Rule("audit_author[].pdbx_ORCID", "ORCID structure authors"),
    Rule("pdbx_database_status.process_site", "Processing organization"),
    Rule("rcsb_accession_info.deposit_date", "Deposition date"),
    Rule("rcsb_accession_info.initial_release_date", "Initial release date"),
    Rule("rcsb_accession_info.revision_date", "Latest revision date"),
    Rule("rcsb_accession_info.major_revision", "Major revision"),
    Rule("rcsb_accession_info.minor_revision", "Minor revision"),
    Rule("exptl[].method", "Experimental methods"),
    Rule("rcsb_entry_container_identifiers.polymer_entity_ids[]", "Polymer entity links"),
    Rule("rcsb_primary_citation.pdbx_database_id_DOI", "Related publication DOI"),
)


def _entry_id_from_doi(doi: str) -> str | None:
    match = _PDB_DOI.fullmatch(doi)
    if match is None:
        return None
    return normalize_pdb_id(match.group("legacy") or match.group("extended"))


def extract_entry_id(reference: str) -> str | None:
    """Accept complete PDB accessions, structure DOIs and supported entry URLs.

    Bare all-numeric references retain the application's Zenodo interpretation;
    use pdb:1234 or a PDB URL for an all-numeric PDB accession.
    wwPDB DOI landing pages select an entry through exactly one `id` parameter.
    """
    reference = reference.strip()
    if reference.lower().startswith("pdb:"):
        return normalize_pdb_id(reference[4:])
    if not reference.isdecimal():
        entry_id = normalize_pdb_id(reference)
        if entry_id:
            return entry_id

    doi = extract_doi(reference)
    if doi is not None:
        return _entry_id_from_doi(doi)

    url = parse_url(reference)
    if url is None or url.hostname not in HOSTS:
        return None
    path = unquote(url.path)
    if url.hostname in {"wwpdb.org", "www.wwpdb.org"}:
        if path.rstrip("/") != "/pdb":
            return None
        ids = parse_qs(url.query, keep_blank_values=True).get("id", [])
        return normalize_pdb_id(ids[0]) if len(ids) == 1 else None

    pattern = _API_PATH if url.hostname == "data.rcsb.org" else _STRUCTURE_PATH
    match = pattern.fullmatch(path)
    return normalize_pdb_id(match.group(1)) if match else None


def can_handle(reference: str) -> bool:
    return extract_entry_id(reference) is not None


def _structure_doi_target(source: Mapping[str, Any]) -> IdentifierTarget:
    """Select the PDB row, retaining the original value and its exact JSON path."""
    databases = source.get("database_2")
    if isinstance(databases, list):
        for index, item in enumerate(databases):
            if (
                isinstance(item, Mapping)
                and plain_text(item.get("database_id")).upper() == "PDB"
            ):
                return IdentifierTarget(
                    "02", "Dataset", f"database_2[{index}].pdbx_DOI", item.get("pdbx_DOI"),
                )
    return IdentifierTarget("02", "Dataset", DOI_FIELD, None)


def extract_structure_doi(source: Mapping[str, Any]) -> str | None:
    """Return only a structure DOI that identifies this entry, for aggregators."""
    value = _structure_doi_target(source).value
    doi = extract_doi(value) if isinstance(value, str) else None
    entry_id = normalize_pdb_id(source.get("rcsb_id"))
    if entry_id and doi and _entry_id_from_doi(doi) == entry_id:
        return doi.lower()
    return None


def evaluate(
    repository_response: Mapping[str, Any], *, expected_entry_id: str | None = None,
    source_url: str | None = None,
    polymer_entities: Mapping[str, Mapping[str, Any] | None] | None = None,
) -> list[CheckResult]:
    entry_id = normalize_pdb_id(repository_response.get("rcsb_id"))
    if entry_id is None:
        raise ValueError("RCSB PDB response does not contain a valid PDB accession.")
    return evaluate_pdb_metadata(
        repository_response,
        context=EvaluationContext(expected_record_id=expected_entry_id, source_url=source_url),
        polymer_entities=polymer_entities,
    )


def _evaluate_with_polymer_metadata(repository_response, *, expected_entry_id, source_url):
    """Fetch the declared polymer subset; unavailable related metadata stay UNSURE."""
    ids = read_field(repository_response, "rcsb_entry_container_identifiers.polymer_entity_ids")
    ids = ids if isinstance(ids, list) else []

    def retrieve(entity_id):
        # Entity identifiers come from public metadata, so validate before URL use.
        if not re.fullmatch(r"[1-9][0-9]*", str(entity_id)):
            return str(entity_id), None
        try:
            data = fetch_json(
                f"https://data.rcsb.org/rest/v1/core/polymer_entity/{expected_entry_id}/{entity_id}",
                service="RCSB PDB polymer entity", timeout=10,
            )
            return str(entity_id), data
        except (URLError, TimeoutError, ConnectionError, HTTPException, TypeError, ValueError) as error:
            if hasattr(error, "close"):
                error.close()
            return str(entity_id), None

    with ThreadPoolExecutor(max_workers=6) as pool:
        entities = dict(pool.map(retrieve, ids))
    return evaluate(
        repository_response, expected_entry_id=expected_entry_id,
        source_url=source_url, polymer_entities=entities,
    )


def fetch(reference: str) -> dict[str, Any]:
    entry_id = extract_entry_id(reference)
    if entry_id is None:
        raise ValueError("Invalid PDB reference.")
    source_url = f"{API_BASE_URL}/{entry_id}"
    return fetch_and_evaluate(
        repository=REPOSITORY,
        display_name=DISPLAY_NAME,
        source_url=source_url,
        reference=reference,
        doi_field=DOI_FIELD,
        doi_extractor=extract_structure_doi,
        evaluator=partial(_evaluate_with_polymer_metadata, expected_entry_id=entry_id, source_url=source_url),
        rules=RULES,
    )
