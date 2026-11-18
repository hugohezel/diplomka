"""Shared recipe wiring; none of these choices come from an adapter."""

from copy import deepcopy

from ..utils.checks import plain_text
from .model import outcome, reduce_status


def text_inputs(op, names):
    selections = [op.read(name) for name in names]
    rows = op.normalize([row for selection in selections for row in selection.rows])
    return rows, all(selection.complete for selection in selections)


def has_text(rows):
    return any(plain_text(value) for row in rows for value in row["values"].values())


def nonblank(rows, slot="value"):
    return [row for row in rows if plain_text(row["values"].get(slot))]


def combine(key, *items, **details):
    return outcome(reduce_status([item["status"] for item in items]), "All required conditions for this item must hold.", key=key, conditions=list(items), **details)


def by_key(items):
    return {item["key"]: item for item in items}


def missing(message="No applicable result is available."):
    return outcome("UNSURE", message)


def derived_row(key, values, *, paths=None, constants=None, evidence=None, binding="derived"):
    return {"key": key, "binding": binding, "values": values, "paths": paths or {},
            "constants": constants or {}, "supplied": {slot: value is not None for slot, value in values.items()},
            "identifiers": [], "malformed": False, "evidence": evidence or []}


def scalar_rows(rows, source_slot, *, namespace=None):
    result = []
    for original in rows:
        row = deepcopy(original)
        row["values"] = {"value": original["values"].get(source_slot), "scheme": original["values"].get("scheme")}
        row["paths"] = {"value": original.get("paths", {}).get(source_slot)}
        if namespace:
            row["constants"]["namespace"] = namespace
        result.append(row)
    return result


def semantic_any(op, names):
    rows, complete = text_inputs(op, names)
    if not has_text(rows):
        op.skip("LLM", "No nonblank permitted input is available.")
        return op.reduce([], quantifier="ANY", complete=complete)
    findings = op.semantic(rows)
    return op.reduce(findings["items"], quantifier="ANY", complete=complete and findings["complete"])
