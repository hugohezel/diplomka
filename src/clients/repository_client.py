"""Fetch original repository JSON and return the adapter's check results."""

from collections import Counter
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from ..utils.aggregator_checks import evaluate_aggregators
from ..utils.checks import CheckResult
from ..utils.references import extract_doi
from ..utils.translation_summary import summarize_translation_checks
from .http_client import fetch_json


def _summarize_checks(
    sections: Mapping[str, list[CheckResult]],
) -> dict[str, Any]:
    all_checks = sections["recordLevel"] + sections["aggregators"]
    statuses = Counter(check["status"] for check in all_checks)
    return {
        "total": len(all_checks),
        "passed": statuses["PASS"],
        "failed": statuses["FAIL"],
        "errors": statuses["ERROR"],
        "warnings": statuses["WARNING"],
        "unsure": statuses["UNSURE"],
        "notApplicable": statuses["NOT_APPLICABLE"],
        **summarize_translation_checks(sections["recordLevel"]),
    }


def fetch_and_evaluate(
    *,
    repository: str,
    display_name: str,
    source_url: str,
    reference: str,
    doi_field: str,
    evaluator: Callable[[Mapping[str, Any]], list[CheckResult]],
    accept: str = "application/json",
    on_event=None,
) -> dict[str, Any]:
    repository_response = fetch_json(source_url, service=display_name, accept=accept)
    record_checks = evaluator(repository_response)
    doi_value = repository_response.get(doi_field)
    doi = extract_doi(reference)
    if doi is None and isinstance(doi_value, str):
        doi = extract_doi(doi_value)

    return evaluation_response(
        repository=repository, display_name=display_name, source_url=source_url,
        repository_response=repository_response, record_checks=record_checks, doi=doi, on_event=on_event,
    )


def evaluation_response(*, repository, display_name, source_url, repository_response, record_checks, doi, on_event=None):
    """Use the same result envelope for each repository's retrieved metadata."""
    checks = {
        "recordLevel": record_checks,
        "aggregators": evaluate_aggregators(doi.lower() if doi else None, on_event=on_event),
    }
    return {
        "repository": repository,
        "repositoryName": display_name,
        "sourceUrl": source_url,
        "evaluatedAt": datetime.now(timezone.utc).isoformat(),
        "repositoryResponse": repository_response,
        "checks": checks,
        "summary": _summarize_checks(checks),
    }
