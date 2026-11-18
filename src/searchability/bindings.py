"""Read native paths while preserving item owners and exact evidence pointers."""

import re
from collections.abc import Mapping
from copy import deepcopy

from .model import Selection


PATH_PART = re.compile(r"([^.[\]]+)(?:\[(\d*)\])?")


def path_parts(path):
    if path == "":
        return []
    parts = []
    for token in path.split("."):
        match = PATH_PART.fullmatch(token)
        if not match:
            raise ValueError(f"Invalid binding path: {path!r}.")
        key, index = match.groups()
        parts.append((key, index))
    return parts


def pointer_part(value):
    return str(value).replace("~", "~0").replace("/", "~1")


def select(source, path, prefix=""):
    """Return (pointer, value, malformed) triples, never flattening owners."""
    current = [(prefix, source, False)]
    for key, index in path_parts(path):
        following = []
        for pointer, value, malformed in current:
            if malformed:
                following.append((pointer, value, True))
                continue
            if not isinstance(value, Mapping) or key not in value:
                continue
            value = value[key]
            pointer += "/" + pointer_part(key)
            if index is None:
                following.append((pointer, value, False))
            elif value is None:
                continue
            elif not isinstance(value, list):
                following.append((pointer, value, True))
            elif index == "":
                following.extend((pointer + f"/{i}", item, False) for i, item in enumerate(value))
            elif int(index) < len(value):
                following.append((pointer + "/" + index, value[int(index)], False))
        current = following
    return current


def _slot(item, path, prefix):
    selected = select(item, path, prefix)
    if len(selected) == 1:
        pointer, value, malformed = selected[0]
        return value, pointer, not malformed and value is not None
    if not selected:
        return None, None, False
    return [value for _, value, _ in selected], [pointer for pointer, _, _ in selected], True


def mapped_fields(profile, names):
    fields = []
    for name in names:
        for entry in profile["bindings"].get(name, []):
            spec = {"path": entry} if isinstance(entry, str) else entry
            path = spec["path"]
            paths = [".".join(filter(None, [path, relative])) for relative in spec.get("fields", {}).values()]
            identifiers = spec.get("identifiers", {})
            if isinstance(identifiers, dict):
                paths.extend(".".join(filter(None, [path, relative])) for relative in identifiers.values())
            else:
                paths.extend(".".join(filter(None, [path, identifier["path"], relative]))
                             for identifier in identifiers for relative in identifier["fields"].values())
            paths = paths or [path]
            fields.append({"binding": name, "paths": paths})
    return fields


def read_binding(source, profile, name, *, complete=True):
    entries = profile["bindings"].get(name)
    if entries is None:
        return Selection(complete=False, mapped=False, message=f"No binding is available for {name}.")
    result = Selection(complete=complete)
    for entry in entries:
        spec = {"path": entry} if isinstance(entry, str) else entry
        path = spec["path"]
        result.fields.append(path)
        result.complete = result.complete and spec.get("complete", True)
        container = path.removesuffix("[]") if path.endswith("[]") else path
        present = any(value is not None for _, value, _ in select(source, container))
        result.present = result.present or present
        if name == "files" and not present:
            result.complete = False
        for pointer, item, malformed in select(source, path):
            # Distinguish free annotations from controlled terms, and ignore empty
            # optional identifier columns without discarding malformed candidates.
            if "if_any" in spec and not malformed and ("fields" not in spec or isinstance(item, Mapping)):
                candidates = [entry for relative in spec["if_any"] for entry in select(item, relative, pointer)]
                if not any(invalid or (value is not None and (not isinstance(value, str) or value.strip()))
                           for _, value, invalid in candidates):
                    continue
            fields = spec.get("fields")
            if fields is not None:
                malformed = malformed or not isinstance(item, Mapping)
                slots = {key: _slot(item, relative, pointer) for key, relative in fields.items()}
            else:
                slot = {"actors": "name", "institutions": "name", "relations": "target", "files": "name"}.get(name, "value")
                slots = {slot: (item, pointer, item is not None)}
            values = {key: value for key, (value, _, _) in slots.items()}
            paths = {key: pointer for key, (_, pointer, _) in slots.items()}
            supplied = {key: supplied for key, (_, _, supplied) in slots.items()}
            if name == "actors" and (not isinstance(values.get("name"), str) or not values["name"].strip()):
                parts = [values.get("family"), values.get("given")] if spec.get("name_order") == "family_given" else [values.get("given"), values.get("family")]
                separator = ", " if spec.get("name_order") == "family_given" else " "
                values["name"] = separator.join(part for part in parts if isinstance(part, str) and part.strip())
                paths["name"] = None
            identifiers = []
            identifier_bindings = spec.get("identifiers", {})
            if isinstance(identifier_bindings, dict):
                for namespace, relative in identifier_bindings.items():
                    for id_path, value, malformed_id in select(item, relative, pointer):
                        if value is not None:
                            identifiers.append({"value": value, "path": id_path, "namespace": namespace, "malformed": malformed_id})
            else:
                for identifier in identifier_bindings:
                    for owner_path, owner, malformed_id in select(item, identifier["path"], pointer):
                        value, id_path, _ = _slot(owner, identifier["fields"]["value"], owner_path)
                        scheme, scheme_path, _ = _slot(owner, identifier["fields"]["scheme"], owner_path)
                        if value is None and not identifier["path"] and not malformed_id:
                            continue
                        scheme_map = identifier.get("maps", {}).get("scheme", {})
                        if isinstance(scheme, str):
                            scheme = scheme_map.get(scheme, scheme)
                        identifiers.append({"value": value, "path": id_path or owner_path, "namespace": None,
                                            "scheme": scheme, "schemePath": scheme_path,
                                            "malformed": malformed_id or not isinstance(owner, Mapping)})
            constants = {key: value for key, value in spec.items() if key not in {"path", "fields", "identifiers"}}
            result.rows.append({
                "key": pointer or "/", "binding": name, "values": values,
                "paths": paths, "supplied": supplied, "constants": constants,
                "identifiers": identifiers, "malformed": malformed,
            })
    return deepcopy(result)
