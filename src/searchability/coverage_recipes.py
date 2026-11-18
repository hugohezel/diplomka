"""Structured coverage first, fixed semantic fallback, and scoped production."""

from ..utils.checks import normalize_text, plain_text
from .model import outcome
from .recipe_helpers import by_key, combine, derived_row, has_text, text_inputs


def _coverage(op, binding, rule):
    selected = op.read(binding)
    candidates = []
    for row in selected.rows:
        if rule == "temporal":
            event = normalize_text(row["values"].get("event", row["constants"].get("event")))
            canonical = op.registry["temporalEvents"].get(event)
            if canonical == "withdrawal":
                continue
            row["coverage_event"] = canonical
        candidates.append(row)
    checked = by_key(op.validate(candidates, rule))
    links = by_key(op.compare([
        {"key": row["key"], "linked": (row.get("coverage_event") in {"collection", "valid", "coverage"}) if rule == "temporal" else (row["constants"].get("scope") == "dataset"), "evidence": row["paths"]}
        for row in candidates
    ], "linked"))
    results = [combine(row["key"], checked[row["key"]], links[row["key"]]) for row in candidates]
    if any(item["status"] == "PASS" for item in results):
        op.skip("LLM", "A valid structured coverage witness already establishes this existential criterion.")
        return op.reduce(results, quantifier="ANY", complete=selected.complete)
    text, text_complete = text_inputs(op, ["descriptions"])
    if not has_text(text):
        op.skip("LLM", "No nonblank coverage text is available.")
        return op.reduce(results, quantifier="ANY", complete=selected.complete and text_complete)
    findings = op.semantic(text)
    extracted = []
    for finding in findings["items"]:
        if finding["status"] != "PASS":
            results.append(finding)
            continue
        value = finding["value"]
        if rule == "spatial":
            if value.get("kind") == "place":
                values = {"place": value.get("place")}
            elif value.get("kind") == "geometry":
                values = {"geometry": value.get("geometry"), "crs": value.get("crs")}
            else:
                results.append(outcome("UNSURE", "Unknown extracted coverage representation.", key=finding["key"]))
                continue
            constants = {}
        else:
            values = {slot: value.get(slot) for slot in ("point", "start", "end") if slot in value}
            constants = {"parser": "iso", "allow_open": bool(value.get("open_start") or value.get("open_end"))}
        row = derived_row(finding["key"], values, constants=constants, evidence=finding["evidence"])
        extracted.append(row)
    parsed = by_key(op.validate(extracted, rule))
    grounded = by_key(findings["items"])
    results.extend(combine(row["key"], grounded[row["key"]], parsed[row["key"]]) for row in extracted)
    return op.reduce(results, quantifier="ANY", complete=selected.complete and text_complete and findings["complete"])


def spatial(op, artifacts):
    return _coverage(op, "spatial", "spatial")


def temporal(op, artifacts):
    return _coverage(op, "temporal", "temporal")


def production(op, artifacts):
    selected = op.read("production_items")
    rows = op.normalize(selected.rows, "controlled", slots=["role"], supported=op.registry["productionRoles"])
    named = by_key(op.validate(rows, "text", slot="name"))
    role_results = by_key(op.compare([
        {"key": row["key"], "value": row["values"].get("role", row["constants"].get("role")), "accepted": op.registry["productionRoles"]}
        for row in rows
    ], "member"))
    scopes = by_key(op.compare([
        {"key": row["key"], "linked": bool(plain_text(row["values"].get("scope", row["constants"].get("scope")))), "evidence": row["paths"]}
        for row in rows
    ], "linked"))
    initial = {row["key"]: combine(row["key"], named[row["key"]], role_results[row["key"]], scopes[row["key"]]) for row in rows}
    unresolved = [row for row in rows if initial[row["key"]]["status"] != "PASS" and named[row["key"]]["status"] == "PASS"]
    text, text_complete = text_inputs(op, ["descriptions", "production_text"])
    if has_text(text):
        findings = op.semantic([*unresolved, *text], required={row["key"]: row["values"].get("name") for row in unresolved}, allow_extra=True)
        for finding in findings["items"]:
            if finding.get("value") is None and finding["key"] not in initial and finding["status"] == "FAIL":
                continue
            if finding["key"] in initial:
                if named[finding["key"]]["status"] == "PASS":
                    initial[finding["key"]] = finding
            else:
                initial[finding["key"]] = finding
        complete = selected.complete and text_complete and findings["complete"]
    else:
        op.skip("LLM", "No production text is available; inspect the complete structured statements.")
        complete = selected.complete and text_complete
    return op.reduce(list(initial.values()), empty="FAIL", complete=complete)
