"""Parse metadata dates while preserving their precision and timezone information."""

import calendar
import re
from datetime import datetime, timezone
from typing import Any, NamedTuple

from .checks import plain_text


ISO_DATE = re.compile(r"[0-9]{4}(?:-[0-9]{2}){0,2}")
ISO_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}"
    r"(?::[0-9]{2}(?:\.[0-9]+)?)?(?:Z|[+-][0-9]{2}:[0-9]{2})?"
)
ADDITIONAL_DATE_FORMATS = (
    (re.compile(r"[0-9]{4}/[0-9]{2}/[0-9]{2}"), "%Y/%m/%d"),
    (re.compile(r"[0-9]{2}\.[0-9]{2}\.[0-9]{4}"), "%d.%m.%Y"),
)


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
