"""Presence checks on fields in the original repository response."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any


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


def read_field(source: Any, path: str) -> Any:
    """Read a dotted field path; [] projects a field from every list item.

    Missing values remain None, including inside lists, so an author without
    an ORCID cannot disappear from the check's evidence.
    """
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
        if html:
            parser = _HTMLText()
            parser.feed(value)
            parser.close()
            value = "".join(parser.parts)
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value) and all(has_value(item, html=html) for item in value)
    if isinstance(value, Mapping):
        return any(has_value(item, html=html) for item in value.values())
    return True


def evaluate_rules(
    source: Mapping[str, Any], rules: Sequence[Rule]
) -> list[dict[str, Any]]:
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
