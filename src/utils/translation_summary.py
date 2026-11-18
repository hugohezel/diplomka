"""Summarize fixed catalogue groups with failure-before-uncertainty semantics."""

from collections import Counter

from .checks import CheckResult, all_pass_status


def summarize_translation_checks(checks: list[CheckResult]) -> dict:
    groups = []
    labels = {check["group"]: check["groupLabel"] for check in checks}
    for group, label in labels.items():
        criteria = [
            check for check in checks
            if check.get("group") == group and check.get("requiredForGroup")
        ]
        active = [check for check in criteria if check.get("applicable") is not False]
        statuses = Counter(check["status"] for check in active)
        unknown = sum(check.get("applicable") is None for check in active)
        status = (
            all_pass_status(check["status"] for check in active)
            if active else "NOT_APPLICABLE"
        )
        if unknown and status == "PASS":
            status = "UNSURE"
        groups.append({
            "group": group, "label": label, "status": status,
            "passed": statuses["PASS"], "failed": statuses["FAIL"],
            "unsure": statuses["UNSURE"], "unknownApplicability": unknown,
            "notApplicable": len(criteria) - len(active),
            "message": "All active required subtests must pass; failures take precedence over uncertainty.",
        })
    return {"profile": "public_repository_api", "groups": groups}
