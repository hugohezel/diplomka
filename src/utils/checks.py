"""Shared field, text and result helpers, plus legacy presence checks."""

import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any


CheckResult = dict[str, Any]
Metadata = Mapping[str, Any]


@dataclass(frozen=True)
class Rule:
    field: str
    label: str
    html: bool = False


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "div", "li", "h1", "h2", "h3"}:
            self.parts.append(" ")


def plain_text(value: Any, *, html: bool = False) -> str:
    """Return text only; numbers and containers are not textual metadata."""
    if not isinstance(value, str):
        return ""
    if html:
        parser = _HTMLText()
        parser.feed(value)
        parser.close()
        value = "".join(parser.parts)
    return value.strip()


def normalize_text(value: Any, *, html: bool = False) -> str:
    normalized = unicodedata.normalize("NFKC", plain_text(value, html=html))
    return " ".join(normalized.casefold().split())


def make_result(
    group: str,
    test: str,
    label: str,
    field: str,
    value: Any,
    *,
    status: str,
    message: str,
    max_points: float = 0,
    kind: str = "required",
    **details: Any,
) -> CheckResult:
    """Build a check result; only a passing check earns declared legacy points."""
    return {
        "group": group,
        "testId": test,
        "label": label,
        "field": field,
        "value": value,
        "status": status,
        "message": message,
        "kind": kind,
        "points": max_points if status == "PASS" else 0,
        "maxPoints": max_points,
        **details,
    }


def any_pass_status(statuses: Iterable[str]) -> str:
    """One passing item suffices; unresolved items prevent a definite failure."""
    statuses = set(statuses)
    if "PASS" in statuses:
        return "PASS"
    if "UNSURE" in statuses:
        return "UNSURE"
    return "FAIL"


def all_pass_status(statuses: Iterable[str]) -> str:
    """Every item must pass; a known failure takes precedence over uncertainty."""
    statuses = set(statuses)
    if "FAIL" in statuses:
        return "FAIL"
    if statuses == {"PASS"}:
        return "PASS"
    return "UNSURE"


def read_field(source: Any, path: str | None) -> Any:
    """Read a dotted field path; [] projects a field from every list item.

    Missing values remain None, including inside lists, so an author without
    an ORCID cannot disappear from the check's evidence.
    """
    if path is None:
        return None
    if not path:
        return source
    if not isinstance(source, Mapping):
        return None

    field, _, remaining = path.partition(".")
    if field.endswith("[]"):
        items = source.get(field[:-2])
        if not isinstance(items, list):
            return None
        return [read_field(item, remaining) for item in items]

    return read_field(source.get(field), remaining)


def has_value(value: Any, *, html: bool = False) -> bool:
    """Require content in every list item; zero and false are present values."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(plain_text(value, html=html))
    if isinstance(value, list):
        return bool(value) and all(has_value(item, html=html) for item in value)
    if isinstance(value, Mapping):
        return any(has_value(item, html=html) for item in value.values())
    return True


def evaluate_rules(
    source: Metadata, rules: Sequence[Rule]
) -> list[CheckResult]:
    results = []
    for rule in rules:
        value = read_field(source, rule.field)
        passed = has_value(value, html=rule.html)
        results.append(
            {
                "field": rule.field,
                "label": rule.label,
                "value": value,
                "status": "PASS" if passed else "FAIL",
                "message": (
                    "Value is present."
                    if passed
                    else "Value is missing or empty (in at least one item)."
                ),
            }
        )
    return results
