"""Closed JSON Schemas and validation of the subset used by fixed LLM tasks."""

import math
from copy import deepcopy


def object_schema(properties, *, nullable=False):
    return {
        "type": ["object", "null"] if nullable else "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def response_schema(value_schema, positive_value_schema, *, evidence_for_failure=False):
    """A PASS has a concrete value and evidence; negative findings may be partial."""
    proof = object_schema({"path": {"type": "string", "minLength": 1,
                                    "description": "Copy the original supplied source path unchanged."},
                           "quote": {"type": "string", "minLength": 1,
                                     "description": "Copy one exact contiguous substring of the supplied field text, preserving wording, case, punctuation and language. Never paraphrase the quotation."}})
    variants = []
    for status in ("PASS", "FAIL", "UNSURE"):
        positive = status == "PASS"
        evidence = {"type": "array", "items": deepcopy(proof)}
        if positive or (status == "FAIL" and evidence_for_failure):
            evidence["minItems"] = 1
        variants.append(object_schema({
            "key": {"type": "string", "minLength": 1},
            "status": {"type": "string", "enum": [status]},
            "value": deepcopy(positive_value_schema if positive else value_schema),
            "evidence": evidence,
            "reason": {"type": "string", "minLength": 1,
                       "description": "Briefly explain the decision in your own words. This is the only field for explanations, interpretations and paraphrases."},
        }))
    return object_schema({
        "coverage": {"type": "string", "enum": ["complete", "unsure"]},
        "items": {"type": "array", "items": {"anyOf": variants}},
    })


def validate_shape(value, schema, *, path="response"):
    """Check our generated schema subset without a runtime dependency or coercion."""
    if "anyOf" in schema:
        errors = []
        for variant in schema["anyOf"]:
            try:
                validate_shape(value, variant, path=path)
                return
            except ValueError as error:
                errors.append(str(error))
        raise ValueError(f"{path} does not match an allowed shape: " + " | ".join(errors))
    expected = schema["type"]
    types = [expected] if isinstance(expected, str) else expected
    matches = {
        "null": value is None,
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
        "number": (isinstance(value, (int, float)) and not isinstance(value, bool)
                   and (isinstance(value, int) or math.isfinite(value))),
    }
    if not any(matches.get(kind, False) for kind in types):
        raise ValueError(f"{path} must have type {' or '.join(types)}.")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} must be one of {schema['enum']}.")
    if value is None:
        return
    if isinstance(value, dict):
        properties = schema["properties"]
        missing = set(schema["required"]) - value.keys()
        extra = value.keys() - properties.keys()
        if missing:
            raise ValueError(f"{path} lacks required fields: {', '.join(sorted(missing))}.")
        if extra and schema.get("additionalProperties") is False:
            raise ValueError(f"{path} has unsupported fields: {', '.join(sorted(extra))}.")
        for key, property_schema in properties.items():
            if key in value:
                validate_shape(value[key], property_schema, path=f"{path}.{key}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise ValueError(f"{path} needs at least {schema['minItems']} item(s).")
        for index, item in enumerate(value):
            validate_shape(item, schema["items"], path=f"{path}[{index}]")
    if isinstance(value, str) and len(value) < schema.get("minLength", 0):
        raise ValueError(f"{path} must not be empty.")
