"""Actor names, roles, identifier compatibility and institutional origin."""

from ..utils.checks import normalize_text, plain_text
from .model import outcome
from .recipe_helpers import by_key, combine, derived_row, has_text, missing, text_inputs
from .normalization import canonical_code


def _values(value):
    return value if isinstance(value, list) else [value]


def _explicit_roles(row, registry):
    return [role for value in _values(row["values"].get("role"))
            if (role := canonical_code(value, registry["roles"]))]


def named_actor(op, artifacts):
    selected = op.read("actors")
    rows = op.normalize(selected.rows, slots=["name", "given", "family"])
    return op.reduce(op.validate(rows, "text", slot="name"), quantifier="ANY", complete=selected.complete)


def _role_result(row, registry):
    if row["malformed"]:
        return outcome("FAIL", "Malformed actor entry.", key=row["key"])
    explicit = row["values"].get("role")
    implicit = row["constants"].get("role")
    roles = _explicit_roles(row, registry)
    requires_subtype = row["constants"].get("requires_subtype", False)
    sufficient = [role for role in roles if not requires_subtype or role not in {"Creator", "Contributor", "Publisher"}]
    if sufficient:
        return outcome("PASS", "The explicit role meets the documented granularity.", key=row["key"], role=sufficient[0], roles=roles)
    if implicit and not requires_subtype and canonical_code(implicit, registry["roles"]):
        return outcome("PASS", "Documented container semantics supply a sufficient role.", key=row["key"], role=implicit)
    return outcome("UNSURE" if explicit else "FAIL", "No sufficient documented role is available.", key=row["key"])


def actor_roles(op, artifacts):
    selected = op.read("actors")
    rows = op.normalize(selected.rows, "controlled", slots=["role"], supported=op.registry["roles"])
    initial = {row["key"]: _role_result(row, op.registry) for row in rows}
    op.compare([{"key": key, "value": result.get("role"), "accepted": op.registry["roles"]} for key, result in initial.items() if result["status"] == "PASS"], "member")
    unresolved = [row for row in rows if initial[row["key"]]["status"] != "PASS" and not row["malformed"]]
    if unresolved:
        text, text_complete = text_inputs(op, ["descriptions"])
        actor_text = op.normalize(unresolved, slots=["name", "role_text"])
        if has_text(text) or any(plain_text(value) for row in actor_text for value in _values(row["values"].get("role_text"))):
            findings = op.semantic([*actor_text, *text], required={row["key"]: row["values"].get("name") for row in unresolved})
            for finding in findings["items"]:
                if finding["key"] not in initial:
                    continue
                row = next(row for row in rows if row["key"] == finding["key"])
                if finding["status"] == "PASS":
                    name = plain_text(row["values"].get("name"))
                    names = [normalize_text(name)] if name else []
                    if row["constants"].get("name_order") == "family_given" and "," in name:
                        family, given = name.split(",", 1)
                        names.append(normalize_text(given + " " + family))
                    role_paths = _values(row["paths"].get("role_text"))
                    context_paths = {entry["paths"].get("value") for entry in text}
                    linked = any(proof["path"] in role_paths or (proof["path"] in context_paths and any(name in normalize_text(proof["quote"]) for name in names)) for proof in finding["evidence"])
                    role = canonical_code(finding["value"]["role"], op.registry["roles"])
                    sufficient = not row["constants"].get("requires_subtype") or role not in {"Creator", "Contributor", "Publisher"}
                    links = op.compare([{"key": row["key"], "linked": True if linked else None, "evidence": finding["evidence"]}], "linked")
                    initial[row["key"]] = combine(row["key"], finding, links[0], outcome("PASS" if sufficient else "FAIL", "Check schema-required role granularity."), role=role)
                else:
                    initial[row["key"]] = finding
            complete = selected.complete and text_complete and findings["complete"]
        else:
            op.skip("LLM", "No explicit role statements are available for unresolved actors.")
            complete = selected.complete and text_complete
    else:
        op.skip("LLM", "Every actor has a sufficient documented role, or no actor is listed.")
        complete = selected.complete
    return op.reduce(list(initial.values()), empty="NOT_APPLICABLE", complete=complete)


def actor_identifiers(op, artifacts):
    selected = op.read("actors")
    actors = {row["key"]: row for row in selected.rows}
    rows = []
    owners = {}
    for actor in selected.rows:
        for identifier in actor["identifiers"]:
            key = identifier["path"]
            row = derived_row(key, {"value": identifier["value"], "scheme": identifier.get("scheme")},
                              paths={"value": key, "scheme": identifier.get("schemePath")},
                              constants={"namespace": identifier["namespace"]}, binding="actor_ids")
            row["malformed"] = actor["malformed"] or identifier.get("malformed", False)
            rows.append(row)
            owners[key] = actor["key"]
    rows = op.normalize(rows, "identifier")
    valid = by_key(op.validate(rows, "identifier"))
    linked = by_key(op.compare([{"key": row["key"], "linked": bool(owners[row["key"]] in actors and plain_text(actors[owners[row["key"]]]["values"].get("name"))),
                                 "evidence": {"actor": owners[row["key"]], "identifier": row["key"]}} for row in rows], "linked"))
    entries = by_key(op.lookup([{"key": key, "kind": "actor", "namespace": value["namespace"], "value": value["canonical"]}
                               for key, value in valid.items() if value["status"] == "PASS" and linked[key]["status"] == "PASS"]))
    pairs = []
    for key, entry in entries.items():
        if entry["status"] == "PASS":
            actor = actors[owners[key]]
            pairs.append({"key": key, "name": actor["values"].get("name"), "name_order": actor["constants"].get("name_order"), "registry_names": entry.get("names", [])})
    compatible = by_key(op.compare(pairs, "actor_compatible"))
    results = [combine(row["key"], valid[row["key"]], linked[row["key"]], entries.get(row["key"], missing("Registry lookup was not possible.")),
                       compatible.get(row["key"], missing("Actor identity compatibility is unresolved."))) for row in rows]
    return op.reduce(results, empty="NOT_APPLICABLE", complete=selected.complete)


def institutional_origin(op, artifacts):
    actors = op.read("actors")
    institutions = op.read("institutions")
    actor_rows = op.normalize(actors.rows, "controlled", slots=["role", "type"], supported=op.registry["roles"])
    rows, links = [], []
    eligible = op.registry["originRoles"]
    for row in institutions.rows:
        role = canonical_code(row["values"].get("role", row["constants"].get("role")), op.registry["roles"])
        rows.append(row)
        links.append({"key": row["key"], "linked": role in {"Creator", "Producer", "Publisher"} if role else None, "evidence": row["paths"]})
    for actor in actor_rows:
        roles = _explicit_roles(actor, op.registry)
        if not roles:
            implicit = canonical_code(actor["constants"].get("role"), op.registry["roles"])
            roles = [implicit] if implicit else []
        affiliations = actor["values"].get("affiliation")
        if affiliations is not None:
            names = affiliations if isinstance(affiliations, list) else [affiliations]
            paths = actor["paths"].get("affiliation")
            for index, name in enumerate(names):
                key = f"{actor['key']}/affiliation/{index}"
                path = paths[index] if isinstance(paths, list) and index < len(paths) else paths
                rows.append(derived_row(key, {"name": name}, paths={"name": path}, binding="institutions"))
                production_role = any(role in eligible and role != "Publisher" for role in roles)
                links.append({"key": key, "linked": production_role if roles else None, "evidence": {"actor": actor["key"], "roles": roles, "affiliation": path}})
        actor_type = actor["values"].get("type", actor["constants"].get("type"))
        if actor_type == "organization" and any(role in {"Creator", "Producer", "Publisher"} for role in roles):
            rows.append(derived_row(actor["key"], {"name": actor["values"].get("name")}, paths={"name": actor["paths"].get("name")}))
            links.append({"key": actor["key"], "linked": True, "evidence": actor["paths"]})
    rows = op.normalize(rows, slots=["name"])
    names = by_key(op.validate(rows, "text", slot="name"))
    relationships = by_key(op.compare(links, "linked"))
    return op.reduce([combine(row["key"], names[row["key"]], relationships[row["key"]]) for row in rows], quantifier="ANY", complete=actors.complete and institutions.complete)
