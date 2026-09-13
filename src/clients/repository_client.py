"""Fetch original repository JSON and return the adapter's check results."""

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from .http_client import fetch_json
from ..utils.aggregator_checks import evaluate_aggregators
from ..utils.references import extract_doi


def fetch_and_evaluate(
    *,
    repository: str,
    display_name: str,
    source_url: str,
    reference: str,
    doi_field: str,
    evaluator: Callable[[Mapping[str, Any]], list[dict[str, Any]]],
) -> dict[str, Any]:
    repository_response = fetch_json(source_url, service=display_name)
    record_checks = evaluator(repository_response)
    doi_value = repository_response.get(doi_field)
    doi = extract_doi(reference)
    if doi is None and isinstance(doi_value, str):
        doi = extract_doi(doi_value)

    checks = {
        "recordLevel": record_checks,
        "repositoryLevel": [],
        "aggregators": evaluate_aggregators(doi.lower() if doi else None),
    }
    all_checks = [check for section in checks.values() for check in section]
    return {
        "repository": repository,
        "repositoryName": display_name,
        "sourceUrl": source_url,
        "evaluatedAt": datetime.now(timezone.utc).isoformat(),
        "repositoryResponse": repository_response,
        "checks": checks,
        "summary": {
            "total": len(all_checks),
            "passed": sum(check["status"] == "PASS" for check in all_checks),
            "failed": sum(check["status"] == "FAIL" for check in all_checks),
            "errors": sum(check["status"] == "ERROR" for check in all_checks),
        },
    }
