"""Validate repository bindings. Criteria and algorithms are system-owned."""

import json
from pathlib import Path
from urllib.parse import urlsplit

from .bindings import path_parts
from .catalogue import catalogue, registries


BINDING_SLOTS = {
    "dataset_ids": {"value", "scheme", "level", "scope"},
    "titles": {"value", "language"}, "descriptions": {"value", "language"},
    "terms": {"value", "code", "scheme"},
    "controlled_subjects": {"id", "label", "scheme", "language"},
    "files": {"name", "format", "mime", "role"},
    "actors": {"name", "given", "family", "role", "affiliation", "type", "role_text"},
    "institutions": {"name", "role"},
    "dates": {"value", "event"},
    "spatial": {"place", "latitude", "longitude", "geometry", "crs"},
    "temporal": {"point", "start", "end", "event"},
    "variables": {"name", "label", "code", "entity", "entity_ref"},
    "production_items": {"name", "role", "scope"},
    "production_text": {"value"}, "data_types": {"value"},
    "representations": {"value"}, "entities": {"value", "id"},
    "relations": {"target", "scheme", "predicate", "direction"},
}

BINDING_OPTIONS = {
    "path", "fields", "identifiers", "namespace", "level", "scope", "html",
    "role", "event", "direction", "requires_subtype", "allow_open", "crs",
    "parser", "name_order", "complete", "language", "maps", "definitions", "type", "predicate", "if_any", "separator",
}
ROOT_OPTIONS = {"$schema", "version", "repository", "catalogue", "registries", "sources", "bindings"}
BOOLEAN_OPTIONS = {"html", "requires_subtype", "allow_open", "complete"}


def _mapping(value, label):
    if not isinstance(value, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()):
        raise ValueError(f"{label} must map string keys to string values.")


def validate_translation(profile):
    if not isinstance(profile, dict) or set(profile) - ROOT_OPTIONS:
        raise ValueError("A translation layer may contain only repository binding configuration.")
    if "$schema" in profile and not isinstance(profile["$schema"], str):
        raise ValueError("The schema reference must be a string.")
    if profile.get("version") != 2:
        raise ValueError("Unsupported translation-layer version; expected 2.")
    if profile.get("catalogue") != catalogue()["version"] or profile.get("registries") != registries()["version"]:
        raise ValueError("Unknown catalogue or shared-registry version.")
    if not isinstance(profile.get("repository"), str) or not profile["repository"].strip():
        raise ValueError("A repository name is required.")
    sources = profile.get("sources", [])
    if not isinstance(sources, list) or any(not isinstance(url, str) or urlsplit(url).scheme not in {"http", "https"} for url in sources):
        raise ValueError("Sources must be HTTP(S) documentation URLs.")
    bindings = profile.get("bindings")
    if not isinstance(bindings, dict) or set(bindings) - BINDING_SLOTS.keys():
        raise ValueError("Unknown or missing binding collection.")
    known_namespaces = registries()["identifiers"]
    for name, entries in bindings.items():
        if not isinstance(entries, list):
            raise ValueError(f"{name} must be a list; use [] for documented absence or omit an unresolved mapping.")
        seen = set()
        for entry in entries:
            encoded = json.dumps(entry, sort_keys=True)
            if encoded in seen:
                raise ValueError(f"Duplicate {name} binding.")
            seen.add(encoded)
            spec = {"path": entry} if isinstance(entry, str) else entry
            if not isinstance(spec, dict) or set(spec) - BINDING_OPTIONS or not isinstance(spec.get("path"), str):
                raise ValueError(f"Invalid {name} binding.")
            path_parts(spec["path"])
            if "separator" in spec and (not isinstance(spec["separator"], str) or not spec["separator"]
                                        or "fields" in spec or "identifiers" in spec):
                raise ValueError("A separator requires a nonempty delimiter and a scalar binding.")
            for option in BOOLEAN_OPTIONS & spec.keys():
                if not isinstance(spec[option], bool):
                    raise ValueError(f"{name}.{option} must be boolean.")
            for option in spec.keys() - BOOLEAN_OPTIONS - {"fields", "identifiers", "maps", "definitions", "if_any"}:
                if not isinstance(spec[option], str):
                    raise ValueError(f"{name}.{option} must be a string.")
            if "if_any" in spec:
                paths = spec["if_any"]
                if not isinstance(paths, list) or not paths or any(not isinstance(path, str) for path in paths):
                    raise ValueError(f"{name}.if_any must contain relative field paths.")
                for path in paths:
                    path_parts(path)
            fields = spec.get("fields", {})
            _mapping(fields, f"{name}.fields")
            if set(fields) - BINDING_SLOTS[name]:
                raise ValueError(f"Unknown field slot in {name}.")
            ids = spec.get("identifiers", {})
            if "identifiers" in spec and name != "actors":
                raise ValueError("Only actor bindings declare actor identifiers.")
            if isinstance(ids, list):
                id_paths = []
                for identifier in ids:
                    if not isinstance(identifier, dict) or set(identifier) - {"path", "fields", "maps"} or not isinstance(identifier.get("path"), str):
                        raise ValueError("Actor identifier bindings require a path and value/scheme fields.")
                    path_parts(identifier["path"])
                    slots = identifier.get("fields", {})
                    _mapping(slots, f"{name}.identifiers.fields")
                    if set(slots) != {"value", "scheme"}:
                        raise ValueError("Actor identifier bindings require value and scheme fields.")
                    id_paths.extend(slots.values())
                    maps = identifier.get("maps", {})
                    if not isinstance(maps, dict) or set(maps) - {"scheme"}:
                        raise ValueError("Actor identifier maps may normalize only the scheme.")
                    for mapping in maps.values():
                        _mapping(mapping, f"{name}.identifiers.maps")
            else:
                _mapping(ids, f"{name}.identifiers")
                if set(ids) - known_namespaces.keys():
                    raise ValueError("Register an unfamiliar namespace globally before referencing it.")
                id_paths = list(ids.values())
            if "namespace" in spec and spec["namespace"] not in known_namespaces:
                raise ValueError("Register an unfamiliar namespace globally before referencing it.")
            for relative in [*fields.values(), *id_paths]:
                path_parts(relative)
            for option in {"maps", "definitions"} & spec.keys():
                if not isinstance(spec[option], dict):
                    raise ValueError(f"{name}.{option} must be an object.")
                if option == "definitions":
                    _mapping(spec[option], f"{name}.definitions")
                else:
                    if set(spec[option]) - BINDING_SLOTS[name]:
                        raise ValueError(f"Unknown mapped slot in {name}.")
                    for value in spec[option].values():
                        _mapping(value, f"{name}.maps")
            if "direction" in spec and spec["direction"] not in {"dataset_to_target", "target_to_dataset", "symmetric"}:
                raise ValueError("Unknown relationship direction.")
            if "level" in spec and spec["level"] not in {"version", "concept", "object"}:
                raise ValueError("Unknown identity level.")
            if "parser" in spec and spec["parser"] not in {"iso", "iso_extended", "iso_interval", "year", "dmy", "ymd_slash", "mjd"}:
                raise ValueError("Unknown date parser profile.")
    return profile


def load_translation(path: Path):
    return validate_translation(json.loads(Path(path).read_text(encoding="utf-8")))
