"""Small data contracts shared by bindings, operations and recipes."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


STATUSES = {"PASS", "FAIL", "UNSURE", "NOT_APPLICABLE"}


@dataclass(frozen=True)
class EvaluationContext:
    reference: str | None = None
    expected_record_id: str | None = None
    expected_identifier: str | None = None
    expected_namespace: str | None = None
    requested_level: str = "version"
    source_url: str | None = None
    complete: bool = True
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Selection:
    rows: list[dict[str, Any]] = field(default_factory=list)
    complete: bool = True
    mapped: bool = True
    present: bool = False
    fields: list[str] = field(default_factory=list)
    message: str = ""

    def to_dict(self):
        return asdict(self)


def outcome(status, message, **details):
    return {"status": status, "message": message, **details}


def reduce_status(statuses, *, quantifier="ALL", empty="FAIL", complete=True):
    """Existence needs one witness; universality needs complete enumeration."""
    active = [status if isinstance(status, str) and status in STATUSES else "UNSURE"
              for status in statuses if status != "NOT_APPLICABLE"]
    if quantifier in {"ANY", "OR"}:
        if "PASS" in active:
            return "PASS"
        if "UNSURE" in active or not complete:
            return "UNSURE"
        return "FAIL" if active else empty
    if quantifier not in {"ALL", "AND"}:
        raise ValueError(f"Unknown reduction: {quantifier}.")
    if "FAIL" in active:
        return "FAIL"
    if "UNSURE" in active or not complete:
        return "UNSURE"
    return "PASS" if active else empty
