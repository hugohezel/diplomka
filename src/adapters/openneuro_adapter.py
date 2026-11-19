"""Retrieve a published OpenNeuro snapshot through the public GraphQL API."""

import re
from pathlib import Path

from ..clients.http_client import fetch_json
from ..utils.references import extract_doi
from .common import finish_record, local_value, record_url


REPOSITORY = "openneuro"
DISPLAY_NAME = "OpenNeuro"
HOSTS = {"openneuro.org", "www.openneuro.org"}
CHECKS_PATH = Path(__file__).with_name("openneuro.translation.json")
_API = "https://openneuro.org/crn/graphql"
_DATASET = r"ds[0-9]{6,}"
_PART = r"(?:0|[1-9][0-9]*)"
_TAG = rf"{_PART}\.{_PART}\.{_PART}"
_ACCESSION = re.compile(rf"({_DATASET})(?::({_TAG}))?", re.I)
_SNAPSHOT_DOI = re.compile(rf"10\.18112/openneuro\.({_DATASET})\.v({_TAG})", re.I)
_DATASET_PATH = re.compile(rf"/datasets/({_DATASET})(?:/versions/({_TAG}))?/?", re.I)

_LATEST_QUERY = """
query LatestSnapshot($datasetId: ID!) {
  dataset(id: $datasetId) { id public latestSnapshot { id tag } }
}
"""
_SNAPSHOT_QUERY = """
query RecordSnapshot($datasetId: ID!, $tag: String!) {
  snapshot(datasetId: $datasetId, tag: $tag) {
    id tag created hexsha readme size
    description {
      id Name BIDSVersion DatasetType Authors SeniorAuthor License DatasetDOI
      Acknowledgements HowToAcknowledge Funding EthicsApprovals ReferencesAndLinks
    }
    summary {
      id schemaVersion dataProcessed modalities primaryModality secondaryModalities
      sessions subjects tasks totalFiles size
    }
    related { id kind relation description }
    files(recursive: false) { id filename directory annexed size urls }
    dataset {
      id name public created publishDate
      metadata {
        datasetId datasetName datasetUrl species studyDesign studyDomain
        studyLongitudinal dxStatus ages modalities tasksCompleted trialCount
        dataProcessed syntheticDataset associatedPaperDOI openneuroPaperDOI
        seniorAuthor grantFunderName grantIdentifier firstSnapshotCreatedAt latestSnapshotCreatedAt
      }
    }
  }
}
"""


def _accession(reference):
    value = local_value(reference, REPOSITORY)
    match = _ACCESSION.fullmatch(value)
    if match is None:
        doi = extract_doi(value)
        if doi:
            match = _SNAPSHOT_DOI.fullmatch(doi)
        else:
            url = record_url(value, HOSTS)
            match = _DATASET_PATH.fullmatch(url.path) if url else None
    return (match[1].lower(), match[2]) if match else None


def can_handle(reference):
    return _accession(reference) is not None


def _query(query, **variables):
    record = fetch_json(_API, service=DISPLAY_NAME, json_body={"query": query, "variables": variables})
    if record.get("errors") or not isinstance(record.get("data"), dict):
        raise ValueError("OpenNeuro could not return the requested metadata.")
    return record


def _latest_tag(dataset_id):
    dataset = _query(_LATEST_QUERY, datasetId=dataset_id)["data"].get("dataset")
    if not isinstance(dataset, dict) or dataset.get("id") != dataset_id or dataset.get("public") is not True:
        raise ValueError("OpenNeuro did not return the requested public dataset.")
    latest = dataset.get("latestSnapshot")
    tag = latest.get("tag") if isinstance(latest, dict) else None
    if not isinstance(tag, str) or not re.fullmatch(_TAG, tag) or latest.get("id") != f"{dataset_id}:{tag}":
        raise ValueError("OpenNeuro did not identify a published snapshot for this dataset.")
    return tag


def fetch(reference, *, requested_reference=None, on_event=None):
    accession = _accession(reference)
    if accession is None:
        raise ValueError("Enter an OpenNeuro dataset accession, snapshot DOI or dataset URL.")
    dataset_id, requested_tag = accession
    tag = requested_tag or _latest_tag(dataset_id)
    snapshot_id = f"{dataset_id}:{tag}"
    record = _query(_SNAPSHOT_QUERY, datasetId=dataset_id, tag=tag)
    snapshot = record["data"].get("snapshot")
    if not isinstance(snapshot, dict) or snapshot.get("id") != snapshot_id or snapshot.get("tag") != tag:
        raise ValueError("OpenNeuro did not return the requested snapshot.")
    dataset = snapshot.get("dataset")
    if not isinstance(dataset, dict) or dataset.get("id") != dataset_id or dataset.get("public") is not True:
        raise ValueError("The OpenNeuro snapshot does not belong to the requested public dataset.")
    description = snapshot.get("description")
    raw_doi = description.get("DatasetDOI") if isinstance(description, dict) else None
    doi = extract_doi(raw_doi) if isinstance(raw_doi, str) else None
    snapshot_doi = f"10.18112/openneuro.{dataset_id}.v{tag}"
    if requested_tag:
        expected_id, namespace, level = snapshot_id, "openneuro_snapshot", "version"
    else:
        expected_id, namespace, level = dataset_id, "openneuro_dataset", "concept"
    return finish_record(
        record, profile_path=CHECKS_PATH, display_name=DISPLAY_NAME, source_url=_API,
        reference=requested_reference or reference, expected_id=expected_id, namespace=namespace, level=level,
        doi=doi if doi and doi.lower() == snapshot_doi else None, on_event=on_event,
    )
