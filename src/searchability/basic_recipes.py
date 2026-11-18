"""Fixed recipes for identity, titles, descriptions, subjects and files."""

from ..utils.checks import normalize_text, plain_text
from .recipe_helpers import by_key, combine, missing, nonblank, scalar_rows, semantic_any, text_inputs, has_text


def dataset_identifier(op, artifacts):
    selected = op.read("dataset_ids")
    rows = op.normalize(selected.rows, "identifier")
    validated = op.validate(rows, "identifier")
    artifacts["dataset_ids"] = {"rows": rows, "results": validated, "complete": selected.complete}
    return op.reduce(validated, quantifier="ANY", complete=selected.complete)


def identity_matches(op, artifacts):
    selected = op.read("dataset_ids")
    rows = op.normalize(selected.rows, "identifier")
    identifiers = op.validate(rows, "identifier")
    input_row = op.input_identity()
    if input_row["values"]["value"] is None:
        return op.reduce([missing("The input identifier is unavailable.")], quantifier="ANY")
    input_row = op.normalize([input_row], "identifier")[0]
    expected = op.validate([input_row], "identifier")[0]
    comparisons = op.compare([
        {"key": row["key"], "left": expected, "right": identifier,
         "left_level": op.context.requested_level,
         "right_level": row["values"].get("level", row["constants"].get("level", "object")),
         "level_known": "level" in row["constants"] or "level" in row["values"]}
        for row, identifier in zip(rows, identifiers)
    ], "same_object")
    if not any(item["status"] == "PASS" for item in comparisons) and op.registry.get("identityAliases"):
        aliases = op.lookup([{"kind": "identity", "left": expected, "right": identifier, "level": op.context.requested_level,
                             "rightLevel": row["values"].get("level", row["constants"].get("level", "object"))}
                            for row, identifier in zip(rows, identifiers)])
        comparisons.extend(aliases)
    else:
        op.skip("LOOKUP", "Direct comparison suffices, or no authoritative same-level alias resource is declared.")
    return op.reduce(comparisons, quantifier="ANY", complete=selected.complete)


def title(op, artifacts):
    selected = op.read("titles")
    rows = op.normalize(selected.rows)
    return op.reduce(op.validate(rows, "text", placeholders=True), quantifier="ANY", complete=selected.complete)


def title_detail(op, artifacts):
    return semantic_any(op, ["titles"])


def description(op, artifacts):
    return semantic_any(op, ["descriptions"])


def added_content(op, artifacts):
    titles, titles_complete = text_inputs(op, ["titles"])
    titles = nonblank(titles)
    if not titles:
        op.skip("LLM", "A nonblank comparison title is required.")
        return op.reduce([missing("The comparison title is missing.")], quantifier="ANY")
    descriptions, descriptions_complete = text_inputs(op, ["descriptions"])
    descriptions = nonblank(descriptions)
    copies = op.compare([
        {"key": desc["key"], "left": normalize_text(desc["values"]["value"]), "right": normalize_text(title["values"]["value"])}
        for desc in descriptions for title in titles
    ], "equal")
    copied_keys = {item["key"] for item in copies if item["status"] == "PASS"}
    remaining = [row for row in descriptions if row["key"] not in copied_keys]
    if not remaining:
        op.skip("LLM", "No description remains after excluding exact whole-title copies.")
        return op.reduce([], quantifier="ANY", complete=descriptions_complete)
    findings = op.semantic([*titles, *remaining])
    return op.reduce(findings["items"], quantifier="ANY", complete=titles_complete and descriptions_complete and findings["complete"])


def terms(op, artifacts):
    selected = op.read("terms")
    rows = op.normalize(selected.rows)
    artifacts["terms"] = {"rows": nonblank(rows), "complete": selected.complete}
    return op.reduce(op.validate(rows, "text"), quantifier="ANY", complete=selected.complete)


def topical_mismatch(op, artifacts):
    term_rows, complete = text_inputs(op, ["terms"])
    term_rows = nonblank(term_rows)
    if not term_rows:
        op.skip("LLM", "No searchable subject terms are present.")
        return op.reduce([], quantifier="ALL", complete=complete)
    context, context_complete = text_inputs(op, ["titles", "descriptions"])
    if not has_text(context):
        op.skip("LLM", "The topic cannot be assessed without title/description context.")
        return op.reduce([missing("Subject terms have no assessable context.")])
    findings = op.semantic([*term_rows, *context], required={row["key"]: row["values"]["value"] for row in term_rows})
    return op.reduce(findings["items"], complete=complete and context_complete and findings["complete"])


def controlled_subjects(op, artifacts):
    selected = op.read("controlled_subjects")
    rows = op.normalize(selected.rows, slots=["label", "scheme", "language"])
    identifiers = op.normalize(scalar_rows(rows, "id"), "identifier")
    ids = by_key(op.validate(identifiers, "identifier"))
    labels = by_key(op.validate(rows, "text", slot="label"))
    lookups = by_key(op.lookup([
        {"key": row["key"], "kind": "vocabulary",
         "id": ids[row["key"]]["canonical"] if ids[row["key"]].get("namespace") in op.registry["vocabularies"] else row["values"].get("id"),
         "scheme": ids[row["key"]].get("namespace") if ids[row["key"]].get("namespace") in op.registry["vocabularies"] else row["values"].get("scheme")}
        for row in rows if ids[row["key"]]["status"] == "PASS" and labels[row["key"]]["status"] == "PASS"
    ]))
    comparisons = []
    for row in rows:
        entry = lookups.get(row["key"])
        if not entry or entry["status"] != "PASS":
            continue
        language = row["values"].get("language", row["constants"].get("language"))
        accepted = [label["value"] for label in entry.get("labels", []) if not language or label.get("language") in {None, language}]
        comparisons.append({"key": row["key"], "value": row["values"].get("label"), "accepted": accepted,
                            "label_comparison": True, "complete_labels": entry.get("completeLabels", False),
                            "languages": entry.get("languages", []), "language": language})
    matches = by_key(op.compare(comparisons, "member"))
    results = [combine(row["key"], ids[row["key"]], labels[row["key"]],
                       lookups.get(row["key"], missing("Concept lookup was not possible.")),
                       matches.get(row["key"], missing("Concept-label comparison was not possible."))) for row in rows]
    return op.reduce(results, empty="NOT_APPLICABLE", complete=selected.complete)


def scientific_kind(op, artifacts):
    return semantic_any(op, ["titles", "descriptions", "data_types"])


def representation(op, artifacts):
    return semantic_any(op, ["titles", "descriptions", "representations"])


def file_formats(op, artifacts):
    selected = op.read("files")
    ancillary = {"ancillary", "documentation", "readme", "license"}
    rows = [row for row in selected.rows if normalize_text(row["values"].get("role", row["constants"].get("role"))) not in ancillary]
    results = op.validate(rows, "format")
    return op.reduce(results, empty="FAIL", complete=selected.complete)


def dates(op, artifacts):
    selected = op.read("dates")
    rows = op.normalize(selected.rows, "controlled", slots=["event"])
    eligible = []
    event_results = []
    for row in rows:
        event = normalize_text(row["values"].get("event", row["constants"].get("event")))
        canonical = op.registry["dateEvents"].get(event)
        event_results.append({"key": row["key"], "value": canonical or event, "accepted": ["publication", "update"]})
        if canonical:
            eligible.append(row)
    event_checks = by_key(op.compare(event_results, "member", strict=True))
    results = op.validate(eligible, "date")
    results = [combine(item["key"], item, event_checks[item["key"]]) for item in results]
    return op.reduce(results, quantifier="ANY", complete=selected.complete)


def studied_entity(op, artifacts):
    return semantic_any(op, ["titles", "descriptions", "entities"])


def variables(op, artifacts):
    selected = op.read("variables")
    rows = op.normalize(selected.rows)
    definitions = by_key(op.lookup([{"key": row["key"], "kind": "definition", "code": row["values"].get("code", row["values"].get("name")), "definitions": row["constants"]["definitions"]}
                                    for row in rows if row["constants"].get("definitions") and not row["values"].get("label")]))
    for row in rows:
        entry = definitions.get(row["key"])
        if entry and entry["status"] == "PASS":
            row["values"]["label"] = entry["label"]
    labels = by_key(op.validate(rows, "label"))
    entity_rows = []
    entity_complete = True
    if any(row["values"].get("entity_ref") for row in rows):
        entities = op.read("entities")
        entity_rows, entity_complete = entities.rows, entities.complete
    entity_keys = {str(row["values"].get("id", row["values"].get("value"))) for row in entity_rows}
    links = []
    for row in rows:
        direct = plain_text(row["values"].get("entity"))
        reference = row["values"].get("entity_ref")
        scope = row["constants"].get("scope")
        linked = bool(direct or (scope and scope != "dataset") or (reference is not None and str(reference) in entity_keys))
        if reference is not None and str(reference) not in entity_keys and not entity_complete:
            linked = None
        links.append({"key": row["key"], "linked": linked, "evidence": row.get("paths", {})})
    compared = by_key(op.compare(links, "linked"))
    return op.reduce([combine(row["key"], labels[row["key"]], compared[row["key"]]) for row in rows], quantifier="ANY", complete=selected.complete)
