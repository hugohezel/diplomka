"""Reusable metadata evidence for people, organizations and controlled terms."""

import re
from collections.abc import Mapping
from typing import Any

from .checks import CheckResult, normalize_text, plain_text
from .metadata_config import (
    FIGSHARE_CATEGORIES_URL, FOS, FOS_SCHEMES, LOOKUP_SUBJECT_SCHEMES, MetadataProfile,
)
from .metadata_identifiers import (
    ROR_URL_PREFIXES, identifier_present, orcid_id, ror_id,
)
from .pdb_vocabulary import classification_evidence


def fos_match(term: Any) -> str | None:
    text = normalize_text(term).removeprefix("fos: ").removeprefix("fos:").strip()
    for code, label in FOS.items():
        if text in {code, normalize_text(label)}:
            return code
    return None


def fos_evidence(term: Any) -> CheckResult:
    code = fos_match(term)
    return {
        "code": code,
        "status": "PASS" if code else "FAIL",
        "message": "Found in OECD FOS." if code else "Not found in OECD FOS.",
    }


def subject_evidence(item: Any, repository: str) -> CheckResult:
    if repository == "pdb":
        return classification_evidence(item)
    evidence: CheckResult = {
        "value": item,
        "status": "FAIL",
        "message": "A category name/code and vocabulary are required.",
    }
    if repository == "dryad":
        evidence.update(vocabulary="OECD FOS 2007", **fos_evidence(item))
        return evidence
    if not isinstance(item, Mapping):
        return evidence

    if repository == "figshare":
        code, title = item.get("id"), plain_text(item.get("title"))
        if title or identifier_present(code):
            evidence.update(
                vocabulary="Figshare categories",
                status="UNSURE",
                message="Category membership verification pending.",
                verification={
                    "kind": "figshare-category",
                    "url": FIGSHARE_CATEGORIES_URL,
                    "id": code,
                    "title": title,
                },
            )
        return evidence

    scheme = plain_text(item.get("scheme"))
    term = plain_text(item.get("term"))
    code = plain_text(item.get("identifier"))
    if not scheme or not (term or code):
        return evidence

    evidence.update(
        vocabulary=scheme,
        status="UNSURE",
        message="No supported vocabulary lookup for this assignment.",
    )
    normalized_scheme = normalize_text(scheme)
    if normalized_scheme in FOS_SCHEMES:
        evidence.update(**fos_evidence(code or term))
    elif normalized_scheme in LOOKUP_SUBJECT_SCHEMES and code:
        evidence["verification"] = {
            "kind": "vocabulary-term", "scheme": normalized_scheme, "id": code,
        }
    return evidence


def creator_name(item: Any) -> str:
    if not isinstance(item, Mapping):
        return ""
    for field in ("name", "full_name", "fullName", "organizationName"):
        name = plain_text(item.get(field))
        if name:
            return name
    name_parts = [plain_text(item.get("firstName")), plain_text(item.get("lastName"))]
    return " ".join(part for part in name_parts if part)


def affiliations(item: Any) -> list[Any]:
    if not isinstance(item, Mapping):
        return []
    values = []
    for field in ("affiliation", "affiliations", "affiliationROR", "affiliationISNI"):
        value = item.get(field)
        if isinstance(value, list):
            values.extend(value)
        elif value is not None:
            values.append(value)
    return values


def organization_present(value: Any) -> bool:
    if isinstance(value, str):
        return bool(plain_text(value))
    if not isinstance(value, Mapping):
        return False

    fields = ("name", "title", "organization", "ror", "id", "identifier")
    if any(plain_text(value.get(field)) for field in fields):
        return True
    identifiers = value.get("identifiers")
    return isinstance(identifiers, list) and any(
        organization_present(item) for item in identifiers
    )


def creator_orcid_evidence(
    item: Any, value: Any, index: int, profile: MetadataProfile,
) -> CheckResult:
    name = creator_name(item)
    surname_field = profile.get("creator_surname_field")
    if surname_field:
        surname = (
            plain_text(item.get(surname_field)) if isinstance(item, Mapping) else ""
        )
    elif "," in name:
        surname = name.split(",", 1)[0].strip()
    else:
        # For an unstructured given-name-first name, the resolved family name
        # determines how many trailing words to compare (including particles).
        surname = None

    identifier = orcid_id(value)
    evidence: CheckResult = {
        "authorIndex": index,
        "metadataName": name,
        "metadataSurname": surname,
        "orcid": value,
        "status": "UNSURE",
        "message": "No ORCID is supplied for this creator.",
    }
    if identifier:
        evidence.update(
            message="ORCID resolution and surname comparison pending.",
            verification={
                "kind": "orcid-name",
                "url": f"https://pub.orcid.org/v3.0/{identifier}/person",
                "name": name,
                "surname": surname,
            },
        )
    elif value is not None and (not isinstance(value, str) or plain_text(value)):
        evidence.update(
            status="FAIL", message="Invalid ORCID format or checksum.",
        )
    return evidence


def ror_values(organizations: list[Any], creators: list[Any]) -> list[Any]:
    values = [
        item["affiliationROR"] for item in creators
        if isinstance(item, Mapping) and item.get("affiliationROR") is not None
    ]
    for organization in organizations:
        if isinstance(organization, str):
            if organization.startswith(ROR_URL_PREFIXES) or re.fullmatch(
                r"0[0-9a-z]{6}[0-9]{2}", organization
            ):
                values.append(organization)
            continue
        if not isinstance(organization, Mapping):
            continue

        if organization.get("ror") is not None:
            values.append(organization["ror"])
        identifiers = organization.get("identifiers")
        if isinstance(identifiers, list):
            for entry in identifiers:
                if (
                    isinstance(entry, Mapping)
                    and normalize_text(entry.get("scheme")) == "ror"
                ):
                    values.append(entry.get("identifier"))
        for field in ("id", "identifier"):
            value = plain_text(organization.get(field))
            if value.startswith(("https://ror.org/", "ror.org/")):
                values.append(organization[field])
    return values


def ror_evidence(value: Any) -> CheckResult:
    code = ror_id(value)
    evidence: CheckResult = {
        "value": value,
        "status": "UNSURE" if code else "FAIL",
        "message": (
            "ROR registry verification pending."
            if code else "Invalid ROR format or checksum."
        ),
    }
    if code:
        evidence["verification"] = {
            "kind": "ror",
            "url": f"https://api.ror.org/v2/organizations/{code}",
            "id": f"https://ror.org/{code}",
        }
    return evidence
