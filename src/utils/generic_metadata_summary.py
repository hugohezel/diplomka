"""Conservative capability summaries without universal points or bonuses."""

from collections import Counter

from .checks import CheckResult, all_pass_status
from .generic_metadata_config import GROUP_LABELS, PROFILE_NAME


def summarize_generic_checks(checks: list[CheckResult]) -> dict:
    groups = []
    for group, label in GROUP_LABELS.items():
        criteria = [check for check in checks
            if check.get("group") == group and check.get("requiredForGroup")]
        active = [check for check in criteria if check.get("applicable") is not False]
        statuses = Counter(check["status"] for check in active)
        unknown = sum(check.get("applicable") is None for check in active)
        status = all_pass_status(check["status"] for check in active) if active else "NOT_APPLICABLE"
        if unknown and status == "PASS":
            status = "UNSURE"
        groups.append({
            "group": group, "label": label, "status": status,
            "passed": statuses["PASS"], "failed": statuses["FAIL"],
            "unsure": statuses["UNSURE"], "unknownApplicability": unknown,
            "notApplicable": len(criteria) - len(active),
            "message": "All active required subtests must pass; failures take precedence over uncertainty.",
        })
    return {"profile": PROFILE_NAME, "groups": groups}
