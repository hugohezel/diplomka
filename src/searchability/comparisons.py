"""Fixed comparison modes; repositories provide evidence, not algorithms."""

from ..utils.checks import normalize_text, plain_text
from .model import outcome
from .normalization import canonical_code


def compare_items(items, mode, registry, **parameters):
    results = []
    for item in items:
        if mode == "equal":
            status = "PASS" if item.get("left") == item.get("right") else "FAIL"
            result = outcome(status, "Compare exact canonical values.")
        elif mode == "member":
            value, accepted = item.get("value"), item.get("accepted", parameters.get("accepted", []))
            match = canonical_code(value, accepted) if isinstance(value, str) else None
            if item.get("label_comparison"):
                matches = normalize_text(value) in {normalize_text(label) for label in accepted}
                language = item.get("language")
                language_known = not language or language in item.get("languages", [])
                status = "PASS" if matches else "FAIL" if item.get("complete_labels") and language_known else "UNSURE"
                if not plain_text(value):
                    status = "FAIL"
                result = outcome(status, "Compare with the concept's applicable preferred and alternative labels.")
            elif match:
                result = outcome("PASS", "Value is in the supported set.", canonical=match)
            else:
                status = "FAIL" if not plain_text(value) or parameters.get("strict") else "UNSURE"
                result = outcome(status, "The value is missing, unsupported or lacks a documented mapping.")
        elif mode == "linked":
            linked = item.get("linked")
            result = outcome("PASS" if linked is True else "FAIL" if linked is False else "UNSURE",
                             item.get("message", "Verify the explicit structural or schema-defined link."), evidence=item.get("evidence", []))
        elif mode == "same_object":
            left, right = item["left"], item["right"]
            if left.get("status") != "PASS" or right.get("status") != "PASS":
                status = "UNSURE" if "UNSURE" in {left.get("status"), right.get("status")} else "FAIL"
            elif not item.get("level_known", True):
                status = "UNSURE"
            else:
                status = "PASS" if (left["namespace"], left["canonical"], item.get("left_level")) == (right["namespace"], right["canonical"], item.get("right_level")) else "FAIL"
            result = outcome(status, "Compare canonical namespace/value at the requested object and version level.")
        elif mode == "actor_compatible":
            name = plain_text(item.get("name"))
            variants = {normalize_text(name)} if name else set()
            if item.get("name_order") == "family_given" and "," in name:
                family, given = name.split(",", 1)
                variants.add(normalize_text(given + " " + family))
            names = {normalize_text(name) for name in item.get("registry_names", []) if plain_text(name)}
            status = "PASS" if variants & names else "UNSURE"
            if item.get("identity_conflict"):
                status = "FAIL"
            result = outcome(status, "Exact documented name/alias compatibility; unmatched names remain uncertain.", metadataNames=sorted(variants), registryNames=sorted(names))
        else:
            raise ValueError(f"Unknown comparison mode: {mode}.")
        results.append({**result, "key": item.get("key"), "input": item})
    return results
