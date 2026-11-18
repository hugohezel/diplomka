"""Prepare namespace-aware identifier candidates without judging their validity."""

import re
from urllib.parse import unquote

from ..utils.checks import plain_text
from ..utils.references import parse_url


def namespace_name(value, definitions):
    value = plain_text(value).casefold()
    for name, definition in definitions.items():
        if value == name or value in definition.get("aliases", []):
            return name
    return value or None


def detect_namespace(text, definitions):
    for name, definition in definitions.items():
        if any(text.casefold().startswith(prefix.casefold()) for prefix in definition.get("prefixes", [])):
            return name
        if pattern := definition.get("prefix_pattern"):
            url = parse_url(text)
            if url and re.fullmatch(pattern, url._replace(query="", fragment="").geturl(), re.I):
                return name
    signatures = [
        ("doi", r"10\."), ("ark", r"ark:"), ("urn", r"urn:"),
        ("pmcid", r"PMC[0-9]"), ("orcid", r"[0-9]{4}-[0-9]{4}-[0-9]{4}-"),
    ]
    for name, pattern in signatures:
        if name in definitions and re.match(pattern, text, re.I):
            return name
    for name in ("uuid", "arxiv"):
        if name in definitions and re.fullmatch(definitions[name]["pattern"], text, re.I):
            return name
    if parse_url(text):
        return "url"
    return None


def normalize_identifier(value, definitions, *, namespace=None, scheme=None):
    """Canonicalize a candidate and retain the evidence needed by VALIDATE."""
    expected = namespace_name(namespace, definitions)
    declared = namespace_name(scheme, definitions)
    if isinstance(value, int) and not isinstance(value, bool):
        text = str(value)
    else:
        text = plain_text(value)
    detected = detect_namespace(text, definitions)
    selected = (expected if expected != "url" else None) or (detected if detected and detected != "url" else expected or declared or detected)
    result = {
        "value": value, "namespace": selected, "canonical": text,
        "expectedNamespace": expected, "declaredScheme": declared,
        "detectedNamespace": detected, "suppliedScheme": scheme,
    }
    definition = definitions.get(selected, {})
    if pattern := definition.get("prefix_pattern"):
        url = parse_url(text)
        if url and (match := re.fullmatch(pattern, url._replace(query="", fragment="").geturl(), re.I)):
            text = match.group(1)
    for prefix in definition.get("prefixes", []):
        if text.casefold().startswith(prefix.casefold()):
            text = text[len(prefix):].strip()
            if prefix.startswith(("https://", "http://")):
                text = unquote(text.split("?", 1)[0].split("#", 1)[0])
            break
    if definition.get("strip_trailing_slash"):
        text = text.rstrip("/")
    if remove := definition.get("remove"):
        text = re.sub(remove, "", text)
    if definition.get("casefold"):
        text = text.casefold()
    for old, new in definition.get("replacements", {}).items():
        if text.casefold().startswith(old.casefold()):
            text = new + text[len(old):]
            break
    if selected == "urn" and text.count(":") >= 2:
        _, nid, suffix = text.split(":", 2)
        text = "urn:" + nid.casefold() + ":" + suffix
    if selected == "ark" and text[:4].casefold() == "ark:":
        text = "ark:" + text[4:]
    if definition.get("uppercase"):
        text = text.upper()
    result["canonical"] = text
    return result
