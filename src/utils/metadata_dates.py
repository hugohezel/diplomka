"""M9 date parsing and chronology checks with explicit precision and scope."""

import calendar
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, NamedTuple

from .checks import (
    CheckResult,
    Metadata,
    all_pass_status,
    make_result,
    normalize_text,
    plain_text,
    read_field,
)


ISO_DATE = re.compile(r"[0-9]{4}(?:-[0-9]{2}){0,2}")
ISO_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}"
    r"(?::[0-9]{2}(?:\.[0-9]+)?)?(?:Z|[+-][0-9]{2}:[0-9]{2})?"
)
ADDITIONAL_DATE_FORMATS = (
    (re.compile(r"[0-9]{4}/[0-9]{2}/[0-9]{2}"), "%Y/%m/%d"),
    (re.compile(r"[0-9]{2}\.[0-9]{2}\.[0-9]{4}"), "%d.%m.%Y"),
)
DATE_FIELDS = {
    "pdb": (
        # Deposition is record creation, not the date of the experiment.
        ("rcsb_accession_info.deposit_date", "created", "record"),
        ("rcsb_accession_info.initial_release_date", "published", "record"),
        ("rcsb_accession_info.revision_date", "updated", "record"),
    ),
    "zenodo": (
        ("metadata.publication_date", "published", "resource"),
        ("created", "created", "record"),
        ("updated", "updated", "record"),
    ),
    "figshare": (
        ("created_date", "created", "resource"),
        ("published_date", "published", "resource"),
        ("modified_date", "updated", "resource"),
    ),
    "dryad": (
        ("publicationDate", "published", "resource"),
        ("creationDate", "created", "resource"),
        ("lastModificationDate", "updated", "resource"),
    ),
}
ZENODO_DATE_TYPES = {
    "created": "created",
    "issued": "published",
    "updated": "updated",
}
COMPARABLE_EVENTS = {("created", "published"), ("created", "updated")}


class ParsedDate(NamedTuple):
    """Precision bounds and whether the source supplied a timezone."""

    earliest: datetime
    latest: datetime
    timezone_aware: bool


def _end_of_day(value: datetime) -> datetime:
    return value.replace(hour=23, minute=59, second=59, microsecond=999999)


def _parse_iso_date(text: str) -> ParsedDate:
    parts = [int(part) for part in text.split("-")]
    year, month, day = (parts + [1, 1])[:3]
    earliest = datetime(year, month, day)

    if len(parts) == 1:
        latest = _end_of_day(datetime(year, 12, 31))
    elif len(parts) == 2:
        last_day = calendar.monthrange(year, month)[1]
        latest = _end_of_day(datetime(year, month, last_day))
    else:
        latest = _end_of_day(earliest)
    return ParsedDate(earliest, latest, False)


def parse_date(value: Any) -> ParsedDate | None:
    """Return a precision interval; never guess ambiguous day/month ordering."""
    text = plain_text(value)
    try:
        if ISO_DATE.fullmatch(text):
            return _parse_iso_date(text)

        if ISO_TIMESTAMP.fullmatch(text):
            iso_text = text[:-1] + "+00:00" if text.endswith("Z") else text
            parsed = datetime.fromisoformat(iso_text)
            aware = parsed.tzinfo is not None
            if aware:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return ParsedDate(parsed, parsed, aware)

        for pattern, date_format in ADDITIONAL_DATE_FORMATS:
            if pattern.fullmatch(text):
                parsed = datetime.strptime(text, date_format)
                return ParsedDate(parsed, _end_of_day(parsed), False)
    except (ValueError, OverflowError):
        return None
    return None


def _date_events(source: Metadata, repository: str) -> list[CheckResult]:
    events = []
    for field, event, scope in DATE_FIELDS[repository]:
        value = read_field(source, field)
        if value is not None:
            events.append({
                "field": field, "event": event, "scope": scope, "value": value,
            })

    dates = read_field(source, "metadata.dates")
    if repository != "zenodo" or not isinstance(dates, list):
        return events

    for index, item in enumerate(dates):
        if not isinstance(item, Mapping):
            continue
        event = ZENODO_DATE_TYPES.get(normalize_text(item.get("type")))
        # Coverage intervals (collected/valid) are not lifecycle events.
        if event:
            events.append({
                "field": f"metadata.dates[{index}].start",
                "event": event,
                "scope": "resource",
                "value": item.get("start"),
            })
    return events


def _compare_dates(before: ParsedDate | None, after: ParsedDate | None) -> str:
    if before is None or after is None:
        return "UNSURE"
    if before.timezone_aware != after.timezone_aware:
        return "UNSURE"
    if before.earliest > after.latest:
        return "FAIL"

    same_interval = (
        before.earliest == after.earliest and before.latest == after.latest
    )
    if before.latest <= after.earliest or same_interval:
        return "PASS"
    return "UNSURE"


def _chronology_evidence(
    events: list[CheckResult], parsed_dates: list[ParsedDate | None]
) -> list[CheckResult]:
    comparisons = []
    for before_event, before_date in zip(events, parsed_dates):
        for after_event, after_date in zip(events, parsed_dates):
            if before_event["scope"] != after_event["scope"]:
                continue
            event_pair = (before_event["event"], after_event["event"])
            if event_pair not in COMPARABLE_EVENTS:
                continue
            # Modifications may precede publication, including embargo release.
            comparisons.append({
                "before": before_event["field"],
                "after": after_event["field"],
                "status": _compare_dates(before_date, after_date),
            })
    return comparisons


def date_checks(source: Metadata, repository: str) -> list[CheckResult]:
    events = _date_events(source, repository)
    parsed_dates = [parse_date(event["value"]) for event in events]
    present = any(plain_text(event["value"]) for event in events)
    all_parsed = bool(events) and all(parsed_dates)
    parsing_evidence = [
        {**event, "parsed": date.earliest.isoformat() if date else None}
        for event, date in zip(events, parsed_dates)
    ]
    comparisons = _chronology_evidence(events, parsed_dates)

    return [
        make_result(
            "M9", "Test-01", "At least one nonempty date", "dates", events,
            status="PASS" if present else "FAIL",
            message="Creation, publication and update dates are considered.",
            max_points=1,
        ),
        make_result(
            "M9", "Test-01-01", "Dates use recognized formats", "dates", events,
            status="PASS" if all_parsed else "UNSURE",
            message=(
                "ISO dates/timestamps, YYYY/MM/DD and DD.MM.YYYY; "
                "ambiguous formats remain unsure."
            ),
            max_points=0.5,
            evidence=parsing_evidence,
        ),
        make_result(
            "M9", "Test-02", "Comparable dates are logically ordered",
            "dates", events,
            status=all_pass_status(item["status"] for item in comparisons),
            message=(
                "Creation must not follow publication or update within the same "
                "scope; precision and timezone must allow comparison. "
                "No past/future cutoff."
            ),
            max_points=0.5,
            evidence=comparisons,
        ),
    ]
