"""Fetch original repository JSON and return the adapter's check results."""

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from ..utils.aggregator_checks import evaluate_aggregators
from ..utils.checks import CheckResult, Rule
from ..utils.generic_metadata_summary import summarize_generic_checks
from ..utils.metadata_verification import verify_metadata_checks
from ..utils.repository_checks import evaluate_repository_checks
from ..utils.references import extract_doi
from .http_client import fetch_json


def _summarize_checks(
    sections: Mapping[str, list[CheckResult]],
) -> dict[str, Any]:
    # Repository policies describe the service, not the quality of this record.
    all_checks = sections["recordLevel"] + sections["aggregators"]
    statuses = Counter(check["status"] for check in all_checks)
    required = [
        check for check in sections["recordLevel"]
        if check.get("kind") == "required"
    ]
    bonuses = [
        check for check in sections["recordLevel"]
        if check.get("kind") == "bonus"
    ]
    counts = {
        "total": len(all_checks),
        "passed": statuses["PASS"],
        "failed": statuses["FAIL"],
        "errors": statuses["ERROR"],
        "warnings": statuses["WARNING"],
        "unsure": statuses["UNSURE"],
        "notApplicable": statuses["NOT_APPLICABLE"],
    }
    if any(check.get("group") == "G01" for check in sections["recordLevel"]):
        return {**counts, **summarize_generic_checks(sections["recordLevel"])}
    return {
        **counts,
        "score": sum(check.get("points", 0) for check in required),
        "maxScore": sum(check.get("maxPoints", 0) for check in required),
        "bonusScore": sum(check.get("points", 0) for check in bonuses),
        "maxBonusScore": sum(check.get("maxPoints", 0) for check in bonuses),
    }


def fetch_and_evaluate(
    *,
    repository: str,
    display_name: str,
    source_url: str,
    reference: str,
    doi_field: str,
    evaluator: Callable[[Mapping[str, Any]], list[CheckResult]],
    rules: Sequence[Rule],
    doi_extractor: Callable[[Mapping[str, Any]], str | None] | None = None,
) -> dict[str, Any]:
    repository_response = fetch_json(source_url, service=display_name)
    record_checks = verify_metadata_checks(evaluator(repository_response))
    if doi_extractor is not None:
        # An adapter may need to distinguish the dataset DOI from other DOIs.
        # Its selection is authoritative, including a missing dataset DOI.
        doi = doi_extractor(repository_response)
    else:
        doi_value = repository_response.get(doi_field)
        doi = extract_doi(reference)
        if doi is None and isinstance(doi_value, str):
            doi = extract_doi(doi_value)

    checks = {
        "recordLevel": record_checks,
        "repositoryLevel": evaluate_repository_checks(repository, rules),
        "aggregators": evaluate_aggregators(doi.lower() if doi else None),
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
