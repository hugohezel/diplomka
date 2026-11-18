"""One persistent candidate set shared by the four relationship criteria."""

from copy import deepcopy

from ..utils.checks import normalize_text, plain_text
from .identifier_validation import validate_identifier
from .identifiers import normalize_identifier
from .model import outcome
from .normalization import canonical_code
from .recipe_helpers import by_key, combine, derived_row, has_text, text_inputs


def relations_present(op, artifacts):
    selected = op.read("relations")
    rows = deepcopy(selected.rows)
    for row in rows:
        row["origin"] = "structured"
        row["declared"] = True
        row["values"].setdefault("predicate", row["constants"].get("predicate"))
    targets = by_key(op.validate(rows, "text", slot="target", identifier_text=True))
    links = by_key(op.compare([
        {"key": row["key"], "linked": bool(not row["malformed"] and plain_text(row["values"].get("predicate"))), "evidence": row["paths"]}
        for row in rows
    ], "linked"))
    results = [combine(row["key"], targets[row["key"]], links[row["key"]]) for row in rows]
    text, text_complete = text_inputs(op, ["descriptions"])
    extraction_complete = True
    if has_text(text):
        findings = op.semantic([*text, *artifacts.get("dataset_ids", {}).get("rows", [])])
        extraction_complete = findings["complete"]
        for finding in findings["items"]:
            value = finding.get("value")
            if not isinstance(value, dict):
                if finding["status"] == "UNSURE":
                    results.append(finding)
                continue
            target, predicate = value.get("target"), value.get("relationship_text")
            evidence = finding.get("evidence", [])
            source_path = evidence[0]["path"] if evidence else None
            row = derived_row("text:" + finding["key"], {"target": target, "predicate": predicate, "subject": value.get("subject")},
                              paths={"target": source_path, "predicate": source_path}, evidence=evidence, binding="relations")
            row.update(origin="text", declared=bool(predicate), finding=finding)
            rows.append(row)
            results.append({**finding, "key": row["key"]})
    else:
        op.skip("LLM", "No nonblank description is available for explicit prose relationships.")
    own_ids = [entry for entry in artifacts.get("dataset_ids", {}).get("results", []) if entry["status"] == "PASS"]
    self_pairs = []
    for row in rows:
        candidate = normalize_identifier(row["values"].get("target"), op.registry["identifiers"], scheme=row["values"].get("scheme"))
        identifier = validate_identifier(candidate, op.registry["identifiers"])
        if identifier["status"] == "PASS":
            for own in own_ids:
                self_pairs.append({"key": row["key"], "left": [identifier["namespace"], identifier["canonical"]], "right": [own["namespace"], own["canonical"]]})
    self_matches = op.compare(self_pairs, "equal")
    self_keys = {item["key"] for item in self_matches if item["status"] == "PASS"}
    rows = [row for row in rows if row["key"] not in self_keys]
    results = [item for item in results if item.get("key") not in self_keys]
    artifact = {"rows": rows, "complete": selected.complete and text_complete and extraction_complete,
                "text": text, "message": "All structured and grounded prose candidates, including incomplete pairs."}
    artifacts["relations"] = artifact
    return op.reduce(results, quantifier="ANY", complete=artifact["complete"])


def _targets(op, artifacts):
    selected = op.artifact("supplied_targets", artifacts["relations"])
    rows = []
    for candidate in selected.rows:
        value = candidate["values"].get("target")
        supplied = candidate.get("supplied", {}).get("target", value is not None)
        if supplied:
            row = derived_row(candidate["key"], {"value": value, "scheme": candidate["values"].get("scheme")},
                              paths={"value": candidate["paths"].get("target")},
                              constants={"namespace": candidate["constants"].get("namespace")}, binding="relation_targets")
            row["malformed"] = candidate["malformed"]
            rows.append(row)
    return rows, selected.complete


def relation_identifiers(op, artifacts):
    rows, complete = _targets(op, artifacts)
    rows = op.normalize(rows, "identifier")
    results = op.validate(rows, "identifier")
    artifacts["relation_ids"] = {"rows": rows, "results": results, "complete": complete}
    return op.reduce(results, empty="NOT_APPLICABLE", complete=complete)


def _relation_interpretation(op, key, predicate, direction, evidence):
    canonical = canonical_code(predicate, op.registry["relations"])
    if normalize_text(predicate) in {"related", "related to", "isrelatedto", "relation", "other"}:
        return outcome("FAIL", "A generic relationship is not a specific supported type.", key=key)
    if not plain_text(predicate):
        return outcome("FAIL", "The declared relationship lacks a predicate.", key=key)
    if not canonical:
        return outcome("UNSURE", "No shared definition exists for this predicate.", key=key)
    if canonical in op.registry["symmetricRelations"]:
        return outcome("PASS", "Supported symmetric relationship.", key=key, type=canonical, direction="symmetric", evidence=evidence)
    if direction == "target_to_dataset":
        canonical = op.registry["inverseRelations"].get(canonical)
        if canonical is None:
            return outcome("UNSURE", "No documented inverse is available.", key=key)
    elif direction != "dataset_to_target":
        return outcome("UNSURE", "The relationship direction is not established.", key=key)
    return outcome("PASS", "Normalize the documented predicate from the dataset's perspective.", key=key, type=canonical, direction="dataset_to_target", evidence=evidence)


def relation_types(op, artifacts):
    artifact = artifacts["relations"]
    selected = op.artifact("declared_relationships", artifact)
    structured, prose = [], []
    for row in selected.rows:
        if not row.get("declared"):
            continue
        (structured if row["origin"] == "structured" else prose).append(row)
    normalized = op.normalize(structured, "controlled", slots=["predicate"], supported=op.registry["relations"])
    results = []
    for row in normalized:
        if row["malformed"]:
            results.append(outcome("FAIL", "Malformed declared relationship.", key=row["key"]))
        else:
            direction = row["values"].get("direction", row["constants"].get("direction"))
            results.append(_relation_interpretation(op, row["key"], row["values"].get("predicate"), direction, row["paths"]))
    if prose:
        findings = op.semantic([*prose, *artifact["text"]], required={row["key"]: row["values"].get("target") for row in prose})
        for finding in findings["items"]:
            if finding["status"] == "PASS":
                value = finding["value"]
                results.append(combine(finding["key"], finding, _relation_interpretation(op, finding["key"], value["type"], value["direction"], finding["evidence"])))
            else:
                results.append(finding)
        complete = selected.complete and findings["complete"]
    else:
        op.skip("LLM", "No explicit prose assertions require relation interpretation.")
        complete = selected.complete
    membership = op.compare([{"key": result["key"], "value": result.get("type"), "accepted": op.registry["relations"]}
                             for result in results if result["status"] == "PASS" and result.get("type")], "member")
    directions = op.compare([{"key": result["key"], "linked": True, "evidence": result.get("evidence", result.get("conditions"))}
                             for result in results if result["status"] == "PASS"], "linked")
    return op.reduce(results, empty="NOT_APPLICABLE", complete=complete)


def relation_resolves(op, artifacts):
    selected = op.artifact("supplied_targets", artifacts["relations"])
    identifiers = artifacts["relation_ids"]
    requests, results = [], []
    for identifier in identifiers["results"]:
        namespace = identifier.get("namespace")
        definition = op.registry["identifiers"].get(namespace)
        if definition is None:
            results.append(outcome("UNSURE", "The target namespace/resolver support is unresolved.", key=identifier["key"]))
        elif definition.get("resolver"):
            if identifier["status"] != "PASS":
                results.append(identifier)
            else:
                requests.append({"key": identifier["key"], "url": identifier["resolver"]})
    results.extend(op.lookup(requests, "target"))
    return op.reduce(results, empty="NOT_APPLICABLE", complete=selected.complete and identifiers["complete"])
