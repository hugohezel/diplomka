"""The seven shared operations and their inspectable execution traces."""

import unicodedata
import os
from collections import Counter
from copy import deepcopy
from dataclasses import asdict

from ..clients import llm_client
from ..utils.checks import normalize_text, plain_text
from .bindings import read_binding
from .comparisons import compare_items
from .identifiers import normalize_identifier
from .model import Selection, outcome, reduce_status
from .normalization import canonical_code
from .semantics import evidence_fields, task_response_schema, task_schema, validate_findings
from .validators import validate_rows


class Operations:
    def __init__(self, source, profile, context, definition, registry, lookup, semantic=None):
        self.source, self.profile, self.context = source, profile, context
        self.definition, self.registry, self.lookup_service = definition, registry, lookup
        self.semantic_service = semantic or llm_client.evaluate_task
        self.steps = []

    def _record(self, operation, inputs, output, *, message, status=None, label=None, executed=True):
        step = {
            "number": len(self.steps) + 1, "operation": operation,
            "method": "LLM" if operation == "LLM" else "DET",
            "label": label or message, "message": message,
            "input": deepcopy(inputs), "output": deepcopy(output), "executed": executed,
        }
        if status is not None:
            step["status"] = status
        self.steps.append(step)
        return output

    def skip(self, operation, reason):
        self._record(operation, None, None, status="SKIPPED", message=reason, executed=False)

    def read(self, name):
        selection = read_binding(self.source, self.profile, name, complete=self.context.complete)
        status = "UNSURE" if not selection.mapped or not selection.complete else "FAIL" if any(row["malformed"] for row in selection.rows) else "PASS"
        self._record("READ", {"source": "record", "sourceUrl": self.context.source_url,
                              "binding": name, "mappings": self.profile["bindings"].get(name)}, selection.to_dict(),
                     status=status, message=selection.message or f"Read {len(selection.rows)} {name} entries.")
        return selection

    def artifact(self, name, artifact):
        selection = Selection(rows=deepcopy(artifact["rows"]), complete=artifact["complete"], present=bool(artifact["rows"]))
        self._record("READ", {"source": "artifact:G9.1", "binding": name}, selection.to_dict(),
                     status="PASS" if selection.complete else "UNSURE", message="Read the persisted relation candidates, including incomplete entries.")
        return selection

    def input_identity(self):
        context = self.context
        if context.expected_identifier:
            value, namespace = context.expected_identifier, "doi"
        elif context.expected_record_id:
            value, namespace = context.expected_record_id, context.expected_namespace
        else:
            value, namespace = context.reference, None
        row = {"key": "input", "binding": "input", "values": {"value": value},
               "paths": {"value": "input.reference"}, "constants": {"namespace": namespace, "level": context.requested_level},
               "supplied": {"value": value is not None}, "malformed": False, "identifiers": []}
        self._record("READ", {"source": "input", "context": asdict(context)}, [row],
                     status="PASS" if value else "UNSURE", message="Read the requested identifier and object/version scope.")
        return row

    def normalize(self, rows, profile="text", *, slots=None, supported=None):
        normalized = deepcopy(rows)
        canonical_values = []
        for row in normalized:
            row.setdefault("original", deepcopy(row.get("values", {})))
            row["normalized"] = {}
            if profile == "identifier":
                row["identifier"] = normalize_identifier(row["values"].get("value"), self.registry["identifiers"],
                                                         namespace=row.get("constants", {}).get("namespace"), scheme=row["values"].get("scheme"))
                continue
            if profile not in {"text", "controlled"}:
                raise ValueError(f"Unknown normalization profile: {profile}.")
            for slot in slots or list(row.get("values", {})):
                value = row["values"].get(slot)
                mapping = row.get("constants", {}).get("maps", {}).get(slot, {})
                if slot in {"role", "role_text"} and isinstance(value, list):
                    items = []
                    for item in value:
                        if isinstance(item, str):
                            item = " ".join(unicodedata.normalize("NFKC", plain_text(mapping.get(item, item), html=row.get("constants", {}).get("html", False))).split())
                            if profile == "controlled" and supported:
                                item = canonical_code(item, supported) or item
                        items.append(item)
                    row["values"][slot] = items
                    row["normalized"][slot] = [normalize_text(item) for item in items]
                    continue
                if isinstance(value, str) and value in mapping:
                    value = mapping[value]
                if not isinstance(value, str):
                    continue
                visible = " ".join(unicodedata.normalize("NFKC", plain_text(value, html=row.get("constants", {}).get("html", False))).split())
                if profile == "controlled" and supported:
                    visible = canonical_code(visible, supported) or visible
                row["values"][slot] = visible
                row["normalized"][slot] = normalize_text(visible)
                if slot == "value" and visible:
                    canonical_values.append(normalize_text(visible))
        duplicates = [value for value, count in Counter(canonical_values).items() if count > 1]
        self._record("NORMALIZE", {"rows": rows, "profile": profile, "slots": slots, "registry": self.registry["version"]},
                     {"rows": normalized, "duplicateGroups": duplicates},
                     message=f"Apply the shared {profile} profile; retain original values.")
        return normalized

    def validate(self, rows, rule, **parameters):
        if rule not in self.registry["validators"] or rule == "llm_evidence":
            raise ValueError(f"Use the fixed typed validation contract for {rule}.")
        result = validate_rows(rows, rule, self.registry, **parameters)
        self._record("VALIDATE", {"rule": rule, "parameters": parameters, "registry": self.registry["version"], "rows": rows}, result,
                     status=reduce_status([item["status"] for item in result], empty="NOT_APPLICABLE"), message=f"Validate every candidate with the shared {rule} rule.")
        return result

    def compare(self, items, mode, **parameters):
        result = compare_items(items, mode, self.registry, **parameters)
        self._record("COMPARE", {"mode": mode, "parameters": parameters, "registry": self.registry["version"], "items": items}, result,
                     status=reduce_status([item["status"] for item in result], empty="NOT_APPLICABLE"), message=f"Compare candidates using {mode}.")
        return result

    def lookup(self, requests, mode="entry"):
        result = self.lookup_service.lookup(requests, mode)
        self._record("LOOKUP", {"mode": mode, "registry": self.registry["version"], "requests": requests}, result,
                     status=reduce_status([item["status"] for item in result], empty="NOT_APPLICABLE"), message=f"Look up {len(requests)} authoritative {mode} results.")
        return result

    def semantic(self, rows, *, required=None, allow_extra=False):
        task_id = self.definition["id"]
        task = {"id": task_id, "instruction": self.definition["task"]["instruction"],
                "valueSchema": task_schema(task_id, self.registry),
                "responseSchema": task_response_schema(task_id, self.registry),
                "allowExtraKeys": allow_extra}
        fields = evidence_fields(rows)
        response = self.semantic_service(task, fields, required_keys=list(required or {}))
        raw_items = response.get("items") if isinstance(response, dict) else None
        statuses = [item.get("status", "UNSURE") for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []
        complete = isinstance(response, dict) and response.get("coverage") == "complete" and isinstance(raw_items, list)
        quantifier = "ALL" if task_id in {"G4.2", "G6.2", "G8.1", "G9.3"} else "ANY"
        self._record("LLM", {"task": task, "systemInstruction": llm_client.SYSTEM_PROMPT,
                             "responseFormat": os.environ.get("LLM_RESPONSE_FORMAT", "json_schema"),
                             "model": os.environ.get("LLM_MODEL") or "endpoint default", "requiredKeys": list(required or {}), "fields": fields}, response,
                     status=reduce_status(statuses, quantifier=quantifier, complete=complete),
                     message="Run the fixed semantic task; its findings still require evidence validation.")
        validated = validate_findings(task_id, response, fields, self.registry, required=required, allow_extra=allow_extra)
        self._record("VALIDATE", {"rule": "llm_evidence", "task": task_id, "response": response, "fields": fields, "requiredKeys": list(required or {})}, validated,
                     status=reduce_status([item["status"] for item in validated["items"]], quantifier=quantifier, complete=validated["complete"]),
                     message=validated["message"])
        return validated

    def reduce(self, items, *, quantifier="ALL", empty="FAIL", complete=True, message=None):
        statuses = [item["status"] if isinstance(item, dict) else item for item in items]
        status = reduce_status(statuses, quantifier=quantifier, empty=empty, complete=complete)
        result = outcome(status, message or self.definition["passRule"], evidence=items)
        return self._record("REDUCE", {"expression": quantifier, "empty": empty, "complete": complete, "items": items}, result,
                            status=status, message=result["message"])
