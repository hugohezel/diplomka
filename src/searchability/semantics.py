"""Validate model grounding without replacing semantic verdicts with schema success."""

import re
from copy import deepcopy

from ..llm_schema import object_schema, response_schema, validate_shape
from ..utils.checks import normalize_text, plain_text
from .model import outcome
from .normalization import canonical_code


VALUE_FIELDS = {
    "G2.2": {"detail", "type"}, "G3.1": {"content"}, "G3.2": {"fact", "adds"},
    "G4.2": {"term", "assessment"}, "G5.1": {"kind"}, "G5.2": {"representation"},
    "G6.2": {"role"}, "G7.1": {"entity"}, "G7.3": {"kind", "place", "geometry", "crs"},
    "G7.4": {"kind", "point", "start", "end", "precision", "open_start", "open_end"},
    "G8.1": {"item", "role", "scope"},
    "G9.1": {"target", "relationship_text", "subject"},
    "G9.3": {"type", "direction", "target"},
}
REQUIRED_VALUES = {
    "G2.2": {"detail", "type"}, "G3.1": {"content"}, "G3.2": {"fact", "adds"},
    "G4.2": {"term", "assessment"}, "G5.1": {"kind"}, "G5.2": {"representation"},
    "G6.2": {"role"}, "G7.1": {"entity"}, "G7.3": {"kind"}, "G7.4": {"kind"},
    "G8.1": {"item", "role", "scope"}, "G9.1": {"target", "relationship_text", "subject"},
    "G9.3": {"type", "direction"},
}
VERBATIM_TEXT = ("Copy one contiguous, verbatim substring of a supporting evidence quote. "
                 "Preserve its wording, word order, grammatical form, capitalization, punctuation and language. "
                 "Explain or paraphrase only in reason.")


def _geometry_schema():
    coordinates = {"type": "array", "items": {"type": "number"}, "minItems": 2}
    variants = []
    for kind, minimums in {"Point": (), "MultiPoint": (1,), "LineString": (2,),
                           "MultiLineString": (2, 1), "Polygon": (4, 1), "MultiPolygon": (4, 1, 1)}.items():
        nested = deepcopy(coordinates)
        for minimum in minimums:
            nested = {"type": "array", "items": nested, "minItems": minimum}
        variants.append(object_schema({"type": {"type": "string", "enum": [kind],
                                                "description": "Use the canonical GeoJSON type of the explicitly evidenced geometry."},
                                       "coordinates": nested}))
    return {"anyOf": [*variants, {"type": "null"}],
            "description": "Encode only explicitly supplied geometry as GeoJSON, preserving the supplied coordinates and their order. Keep the original text in evidence.quote; use null if no geometry is given."}


def task_schema(task_id, registry, *, positive=False):
    properties = {name: {"type": ["string", "null"], "description": VERBATIM_TEXT}
                  for name in sorted(VALUE_FIELDS[task_id])}
    enums = {
        "G2.2": {"type": ["subject", "data_form", "scale", "place", "time", "origin"]},
        "G4.2": {"assessment": ["no_mismatch", "mismatch", "uncertain"]},
        "G6.2": {"role": registry["roles"]},
        "G7.3": {"kind": ["place", "geometry"]},
        "G7.4": {"kind": ["point", "interval"], "precision": ["year", "month", "day", "timestamp"]},
        "G8.1": {"role": registry["productionRoles"]},
        "G9.3": {"type": registry["relations"], "direction": ["dataset_to_target", "target_to_dataset", "symmetric"]},
    }
    for name, values in enums.get(task_id, {}).items():
        properties[name]["enum"] = [*values, None]
        properties[name]["description"] = ("Classify only the evidenced meaning using an exact schema enum value. "
                                           "Keep the original wording in evidence.quote and explain the classification only in reason.")
    if task_id == "G4.2":
        properties["term"]["description"] = "Copy the exact original input term for this key, without renaming, translating or normalizing it. The contextual evidence need not repeat the term."
    if task_id == "G7.3":
        properties["geometry"] = _geometry_schema()
        properties["crs"]["description"] = "Copy the explicitly declared CRS verbatim from the evidence; use null if it is absent."
    if task_id == "G7.4":
        for name in ("point", "start", "end"):
            properties[name]["description"] = "Convert only the date/time representation to the required ISO form, preserving the evidenced era, bounds and precision. Keep the original wording in evidence.quote and explain any conversion in reason; use null when absent."
        for name in ("open_start", "open_end"):
            properties[name] = {"type": "boolean", "description": "True only for an explicitly open interval bound; otherwise false."}
    if task_id == "G8.1":
        properties["item"]["description"] = ("Copy the production method, process/action or instrument phrase verbatim from an evidence quote, "
                                            "keeping its original grammatical form. For a required input item, preserve its supplied name exactly.")
        properties["scope"]["description"] = ("Copy one contiguous, verbatim phrase naming the affected data, subset or variable from an evidence quote. "
                                             "Do not append or reorder the production action. The fixed marker dataset is allowed only when the quote "
                                             "explicitly applies to the whole evaluated dataset; use null when scope is missing.")
    if task_id in {"G9.1", "G9.3"}:
        properties["target"]["description"] = "Copy the literal supplied target ID or URI unchanged, preserving its spelling and prefixes. Do not normalize, expand or invent it."
    if task_id == "G9.1":
        properties["subject"]["description"] = ("Copy the explicit subject identifier or phrase verbatim from the quoted assertion. "
                                               "The fixed marker dataset is allowed only when that assertion explicitly has the evaluated dataset as its subject; otherwise use null if missing.")
    if positive:
        for name in REQUIRED_VALUES[task_id]:
            properties[name]["type"] = "string"
            properties[name]["minLength"] = 1
            if "enum" in properties[name]:
                properties[name]["enum"] = [value for value in properties[name]["enum"] if value is not None]
    if positive and task_id in {"G7.3", "G7.4"}:
        return _positive_coverage_schema(task_id, properties)
    return object_schema(properties, nullable=not positive)


def _positive_coverage_schema(task_id, properties):
    variants = []
    if task_id == "G7.3":
        for kind in ("place", "geometry"):
            branch = deepcopy(properties)
            branch["kind"]["enum"] = [kind]
            if kind == "place":
                branch["place"] = {**branch["place"], "type": "string", "minLength": 1}
                branch["geometry"] = {"type": "null", "description": properties["geometry"]["description"]}
            else:
                branch["geometry"]["anyOf"] = branch["geometry"]["anyOf"][:-1]
                branch["place"] = {"type": "null", "description": properties["place"]["description"]}
            variants.append(object_schema(branch))
    else:
        for kind, has_start, has_end in (("point", False, False), ("interval", True, True),
                                         ("interval", True, False), ("interval", False, True)):
            branch = deepcopy(properties)
            branch["kind"]["enum"] = [kind]
            for name, present in (("point", kind == "point"), ("start", has_start), ("end", has_end)):
                branch[name] = ({**branch[name], "type": "string", "minLength": 1} if present
                                else {"type": "null", "description": properties[name]["description"]})
            branch["open_start"]["enum"] = [kind == "interval" and not has_start]
            branch["open_end"]["enum"] = [kind == "interval" and not has_end]
            variants.append(object_schema(branch))
    return {"anyOf": variants}


def task_response_schema(task_id, registry):
    schema = response_schema(task_schema(task_id, registry), task_schema(task_id, registry, positive=True),
                             evidence_for_failure=task_id in {"G4.2", "G6.2", "G8.1", "G9.3"})
    if task_id == "G4.2":
        assessments = {"PASS": "no_mismatch", "FAIL": "mismatch", "UNSURE": "uncertain"}
        for variant in schema["properties"]["items"]["items"]["anyOf"]:
            status = variant["properties"]["status"]["enum"][0]
            properties = variant["properties"]["value"]["properties"]
            properties["assessment"]["enum"] = [assessments[status]]
            properties["term"]["type"] = "string"
            properties["term"]["minLength"] = 1
    return schema


def evidence_fields(rows):
    fields = []
    for row in rows:
        for slot, value in row.get("values", {}).items():
            path = row.get("paths", {}).get(slot)
            if isinstance(value, list) and isinstance(path, list):
                for item, item_path in zip(value, path):
                    if isinstance(item, str) and isinstance(item_path, str):
                        fields.append({"key": row["key"], "binding": row.get("binding"), "slot": slot, "path": item_path, "text": item})
            if isinstance(value, str) and isinstance(path, str):
                fields.append({"key": row["key"], "binding": row.get("binding"), "slot": slot, "path": path, "text": value})
    return fields


def _check_value(task_id, item, fields, registry, required):
    value = item["value"]
    if value is None and item["status"] != "PASS":
        return
    quoted = [e["quote"] for e in item["evidence"]]
    if task_id == "G9.1":
        for slot in ("target", "relationship_text"):
            supplied = value.get(slot)
            if supplied is not None and (not isinstance(supplied, str) or not any(supplied in quote for quote in quoted)):
                raise ValueError("Even incomplete relation candidates must retain literal source identifiers and phrases.")
    if task_id == "G8.1" and value.get("item") is not None:
        item_name = plain_text(value["item"])
        if not item_name or not any(normalize_text(item_name) in normalize_text(quote) for quote in quoted):
            raise ValueError("A production item must be named in the supplied evidence.")
        if item["key"] in required and normalize_text(item_name) != normalize_text(required[item["key"]]):
            raise ValueError("The model changed the original production item.")
    if item["status"] != "PASS":
        return
    if any(not plain_text(value.get(key)) for key in REQUIRED_VALUES[task_id]):
        raise ValueError("A positive finding lacks a required value, role or scope.")
    if task_id == "G3.2":
        description_paths = {field["path"] for field in fields if field.get("binding") == "descriptions"}
        if not any(proof["path"] in description_paths for proof in item["evidence"]):
            raise ValueError("An added fact must be quoted from a description.")
    if task_id == "G2.2":
        if value["type"] not in {"subject", "data_form", "scale", "place", "time", "origin"} or not any(value["detail"] in quote for quote in quoted):
            raise ValueError("A title detail must be a quoted span of an eligible type.")
    if task_id == "G5.1" and normalize_text(value["kind"]) in {"data", "dataset", "datasets", "resource", "other"}:
        raise ValueError("A generic resource label does not identify a concrete scientific data kind.")
    if task_id == "G4.2":
        if value["assessment"] != "no_mismatch" or value["term"] != required.get(item["key"]):
            raise ValueError("The term or assessment differs from its input item.")
        context_paths = {f["path"] for f in fields if f.get("binding") in {"titles", "descriptions"}}
        if not any(e["path"] in context_paths for e in item["evidence"]):
            raise ValueError("Quoting the term alone does not assess its context.")
    if task_id == "G6.2" and canonical_code(value["role"], registry["roles"]) is None:
        raise ValueError("The extracted actor role is unsupported.")
    if task_id == "G8.1" and value["role"] not in registry["productionRoles"]:
        raise ValueError("The extracted production role is unsupported.")
    if task_id == "G8.1" and value["scope"] != "dataset" and not any(normalize_text(value["scope"]) in normalize_text(quote) for quote in quoted):
        raise ValueError("The production subset/variable scope must be grounded in the quoted text.")
    if task_id == "G7.3" and value.get("kind") == "place":
        if not plain_text(value.get("place")) or not any(value["place"] in quote for quote in quoted):
            raise ValueError("The place must be explicitly named in the supplied coverage text.")
    if task_id == "G7.4":
        if value.get("kind") not in {"point", "interval"} or (value["kind"] == "point" and not value.get("point")) or (value["kind"] == "interval" and value.get("start") is None and value.get("end") is None):
            raise ValueError("Temporal findings need a point or an interval with an explicit bound.")
        for slot in ("point", "start", "end"):
            date = value.get(slot)
            if date is not None:
                if not isinstance(date, str) or not any(date[:4] in quote for quote in quoted):
                    raise ValueError("Do not invent years or interval bounds absent from the evidence.")
                if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", date):
                    day = int(date[-2:])
                    if not any(re.search(rf"(?<![0-9])0?{day}(?![0-9])", quote) for quote in quoted):
                        raise ValueError("Day precision was not supplied by the evidence.")
                if value.get("precision") == "month" and len(date) != 7:
                    raise ValueError("Preserve the explicitly stated month precision.")
    if task_id == "G9.1" and not any(value["target"] in quote and value["relationship_text"] in quote for quote in quoted):
        raise ValueError("Target and relationship must occur in the same quoted assertion.")
    if task_id == "G9.3":
        if canonical_code(value["type"], registry["relations"]) is None or value["direction"] not in {"dataset_to_target", "target_to_dataset", "symmetric"}:
            raise ValueError("Unknown relation type or direction.")
        if item["key"] in required and value.get("target") != required[item["key"]]:
            raise ValueError("The model changed the original relation target.")


def validate_findings(task_id, response, fields, registry, *, required=None, allow_extra=False):
    required = required or {}
    results = []
    transport_error = (isinstance(response, dict) and set(response) == {"coverage", "items", "error"}
                       and response["coverage"] == "unsure" and response["items"] == []
                       and bool(plain_text(response["error"])))
    if (not isinstance(response, dict) or response.get("coverage") not in ("complete", "unsure")
            or not isinstance(response.get("items"), list)
            or (not transport_error and set(response) != {"coverage", "items"})):
        response = {"coverage": "unsure", "items": [], "error": "Invalid LLM response envelope."}
    complete = response["coverage"] == "complete"
    item_schema = task_response_schema(task_id, registry)["properties"]["items"]["items"]
    by_path = {}
    for field in fields:
        by_path.setdefault(field["path"], []).append(field["text"])
    seen = set()
    for item in response["items"]:
        key = item.get("key") if isinstance(item, dict) else None
        try:
            validate_shape(item, item_schema, path=f"items[{len(results)}]")
            if not isinstance(key, str) or not key.strip() or key in seen:
                raise ValueError("Finding keys must be nonblank and unique.")
            if required and key not in required and not allow_extra:
                raise ValueError("The model returned an unrelated item key.")
            if item["status"] not in {"PASS", "FAIL", "UNSURE"} or not plain_text(item["reason"]):
                raise ValueError("Missing semantic verdict or explanation.")
            evidence = item["evidence"]
            if not isinstance(evidence, list):
                raise ValueError("Evidence must be a list.")
            for proof in evidence:
                if (not isinstance(proof, dict) or set(proof) != {"path", "quote"}
                        or not isinstance(proof["path"], str) or not plain_text(proof["quote"])
                        or not any(proof["quote"] in text for text in by_path.get(proof["path"], []))):
                    raise ValueError("Evidence must quote an allowed input field exactly.")
            if item["status"] == "PASS" and not evidence:
                raise ValueError("A positive semantic finding needs evidence.")
            if item["status"] == "FAIL" and task_id in {"G4.2", "G6.2", "G8.1", "G9.3"} and not evidence:
                raise ValueError("An item-level semantic failure needs its textual basis.")
            _check_value(task_id, item, fields, registry, required)
            if task_id == "G4.2" and isinstance(item["value"], dict):
                expected = {"PASS": "no_mismatch", "FAIL": "mismatch", "UNSURE": "uncertain"}[item["status"]]
                if item["value"].get("assessment") != expected or item["value"].get("term") != required.get(key):
                    raise ValueError("The verdict must agree with the original term and assessment.")
                context_paths = {field["path"] for field in fields if field.get("binding") in {"titles", "descriptions"}}
                if item["status"] != "UNSURE" and not any(proof["path"] in context_paths for proof in evidence):
                    raise ValueError("A topical judgement needs evidence from the title or description.")
            results.append({**item, "message": item["reason"]})
        except (ValueError, TypeError, KeyError) as error:
            complete = False
            results.append(outcome("UNSURE", str(error), key=key if isinstance(key, str) else f"invalid-{len(results)}", value=None, evidence=[]))
        if isinstance(key, str):
            seen.add(key)
    for key in required.keys() - seen:
        complete = False
        results.append(outcome("UNSURE", "No valid finding was returned for this required input item.", key=key, value=None, evidence=[]))
    if response.get("error"):
        complete = False
    return {"items": results, "complete": complete, "message": response.get("error", "Validate task shape, item coverage and exact quotations.")}
