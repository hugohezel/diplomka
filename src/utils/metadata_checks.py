"""Offline M1–M9 evaluation on the original repository metadata.

Checks queue external lookups as evidence. metadata_verification completes them
after the repository response is loaded; no NLP or LLM processing runs here.
"""

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .checks import (
    CheckResult,
    Metadata,
    Rule,
    all_pass_status,
    any_pass_status,
    evaluate_rules,
    make_result,
    normalize_text,
    plain_text,
    read_field,
)
from .metadata_config import (
    BRACKETED_TITLE_TEMPLATE,
    FILE_FORMATS,
    OTHER_RESOURCE_TYPES,
    PROFILES,
    TITLE_TEMPLATE,
    MetadataProfile,
)

from .metadata_evidence import (
    subject_evidence as _subject_evidence,
    creator_name as _creator_name,
    affiliations as _affiliations,
    organization_present as _organization_present,
    creator_orcid_evidence as _creator_orcid_evidence,
    ror_values as _ror_values,
    ror_evidence as _ror_evidence,
)
from .metadata_dates import date_checks
from .metadata_identifiers import (
    identifier_present,
    identifier_syntax,
    valid_orcid,
)
from .references import extract_doi, parse_url
from .pdb_identifiers import normalize_pdb_id


FIGSHARE_VERSION_DOI = re.compile(
    r"10\.6084/m9\.figshare\.[1-9][0-9]*\.v[1-9][0-9]*", re.I
)
VERSION_SUFFIX = re.compile(r"\.v[1-9][0-9]*$", re.I)


@dataclass(frozen=True)
class IdentifierTarget:
    test_number: str
    label: str
    field: str
    value: Any
    local_scheme: str | None = None


def _identifier_targets(
    source: Metadata, repository: str, profile: MetadataProfile
) -> list[IdentifierTarget]:
    doi = read_field(source, profile["doi"])
    dataset_field, dataset = profile["doi"], doi
    version_field, version = "versionIdentifier", source.get("versionIdentifier")

    if repository == "zenodo":
        if identifier_present(source.get("conceptdoi")):
            dataset_field, dataset = "conceptdoi", source["conceptdoi"]
        version_field, version = "doi", doi
    elif repository == "figshare":
        parsed_doi = extract_doi(doi) if isinstance(doi, str) else None
        if parsed_doi and FIGSHARE_VERSION_DOI.fullmatch(parsed_doi):
            dataset_field = "doi (without version suffix)"
            dataset = VERSION_SUFFIX.sub("", parsed_doi)
            version_field, version = "doi", doi

    # Version numbers and author-defined labels are not identifiers.
    return [
        IdentifierTarget(
            "01", "Metadata record", "id", source.get("id"),
            local_scheme=f"{repository}:record-id",
        ),
        IdentifierTarget("02", "Dataset", dataset_field, dataset),
        IdentifierTarget("03", "Specific version", version_field, version),
    ]


def _record_resolver(
    source: Metadata, repository: str, profile: MetadataProfile, record_id: Any
) -> str | None:
    if repository == "dryad":
        self_link = read_field(source, "_links.self.href")
        if plain_text(self_link) and parse_url(self_link):
            return self_link
        return None
    if repository == "pdb":
        record_id = normalize_pdb_id(record_id)
    return f"{profile['api']}{str(record_id).strip()}"


def _identifier_checks(
    source: Metadata, repository: str, profile: MetadataProfile,
    targets: Sequence[IdentifierTarget] | None = None,
) -> list[CheckResult]:
    checks = []
    if targets is None:
        targets = _identifier_targets(source, repository, profile)
    for target in targets:
        present = identifier_present(target.value)
        scheme, valid, resolver = identifier_syntax(
            target.value, local_scheme=target.local_scheme
        )
        if target.local_scheme and valid:
            resolver = _record_resolver(source, repository, profile, target.value)

        is_version = target.test_number == "03"
        kind = "bonus" if is_version else "required"
        test_id = f"Test-{target.test_number}"
        resolution_details: CheckResult = {"sourceUrl": resolver}
        if resolver:
            resolution_details["verification"] = {
                "kind": "resolve", "url": resolver,
            }

        checks.extend([
            make_result(
                "M1", test_id, f"{target.label} identifier present",
                target.field, target.value,
                status="PASS" if present else "FAIL",
                message=(
                    "Identifier is present." if present else "Identifier is missing."
                ),
                max_points=0.5 if is_version else 0,
                kind=kind,
            ),
            make_result(
                "M1", f"{test_id}-01", f"{target.label} identifier syntax",
                target.field, target.value,
                status="PASS" if valid else "FAIL",
                message=(
                    f"Valid {scheme} syntax."
                    if valid else "Missing, invalid or unsupported identifier scheme."
                ),
                max_points=0.5 if is_version else 1,
                kind=kind,
                scheme=scheme,
            ),
            make_result(
                "M1", f"{test_id}-02", f"{target.label} identifier resolves",
                target.field, target.value,
                status="UNSURE" if present and valid else "FAIL",
                message=(
                    "Resolver verification pending."
                    if resolver else "No suitable resolver is available."
                ),
                max_points=0.5,
                kind="bonus",
                **resolution_details,
            ),
        ])
    return checks


def _title_checks(source: Metadata, profile: MetadataProfile) -> list[CheckResult]:
    title = read_field(source, profile["title"])
    normalized = normalize_text(title)
    is_template = bool(
        TITLE_TEMPLATE.fullmatch(normalized)
        or BRACKETED_TITLE_TEMPLATE.fullmatch(normalized)
    )
    uninformative = not normalized or is_template

    return [
        make_result(
            "M2", "Test-01", "Title is nonempty text", profile["title"], title,
            status="PASS" if normalized else "FAIL",
            message="Requires nonempty text.",
            max_points=1,
        ),
        make_result(
            "M2", "Test-02", "Title informativeness: obvious templates",
            profile["title"], title,
            status="FAIL" if uninformative else "UNSURE",
            message=(
                "Empty title or obvious placeholder/template."
                if uninformative else
                "No obvious template; semantic informativeness is not assessed."
            ),
            max_points=1,
        ),
    ]


def _description_checks(
    source: Metadata, profile: MetadataProfile
) -> list[CheckResult]:
    if profile["description"] is None:
        return [make_result(
            "M3", test, label, "description (unmapped)", None,
            status="UNSURE",
            message=(
                "No equivalent general record description is mapped from this endpoint. "
                "This does not establish that the repository cannot accept "
                "descriptive metadata."
            ),
            max_points=points, kind=kind,
        ) for test, label, points, kind in (
            ("Test-01", "Description is nonempty text", 1, "required"),
            ("Test-03", "Description repeats the title", 0, "warning"),
        )]
    title = normalize_text(read_field(source, profile["title"]))
    description = read_field(source, profile["description"])
    normalized = normalize_text(description, html=True)
    identical = bool(title) and normalized == title
    if identical:
        identity_status = "WARNING"
    elif title and normalized:
        identity_status = "PASS"
    else:
        identity_status = "UNSURE"

    return [
        make_result(
            "M3", "Test-01", "Description is nonempty text",
            profile["description"], description,
            status="PASS" if normalized else "FAIL",
            message="Requires nonempty text after HTML parsing.",
            max_points=1,
        ),
        make_result(
            "M3", "Test-03", "Description repeats the title",
            profile["description"], description,
            status=identity_status,
            message=(
                "Description and title are identical after text normalization."
                if identical else "Compare normalized title and description."
            ),
            kind="warning",
        ),
    ]


def _keyword_checks(
    source: Metadata, profile: MetadataProfile
) -> list[CheckResult]:
    keywords = read_field(source, profile["keywords"])
    separator = profile.get("keyword_separator")
    items = keywords.split(separator) if separator and isinstance(keywords, str) else keywords
    terms = []
    if isinstance(items, list):
        terms = [normalize_text(term) for term in items]
        terms = [term for term in terms if term]
    duplicates = [term for term, count in Counter(terms).items() if count > 1]

    return [
        make_result(
            "M4", "Test-01", "At least one normalized keyword",
            profile["keywords"], keywords,
            status="PASS" if terms else "FAIL",
            message="Whitespace, Unicode NFKC and case are normalized.",
            max_points=1,
            normalizedValue=terms,
        ),
        make_result(
            "M4", "Test-02", "Duplicate keywords", profile["keywords"], keywords,
            status="WARNING" if duplicates else "PASS",
            message="Duplicates found." if duplicates else "No duplicate nonempty terms.",
            kind="warning",
            evidence=duplicates,
        ),
    ]


def _subject_check(
    source: Metadata, repository: str, profile: MetadataProfile
) -> CheckResult:
    subjects = read_field(source, profile["subjects"])
    items = subjects if isinstance(subjects, list) else [subjects]
    evidence = [_subject_evidence(item, repository) for item in items]
    return make_result(
        "M5", "Test-01", "At least one verified controlled subject",
        profile["subjects"], subjects,
        status=any_pass_status(item["status"] for item in evidence),
        message="At least one category must belong to an identified controlled vocabulary.",
        max_points=1,
        evidence=evidence,
    )


def _creator_checks(
    source: Metadata, profile: MetadataProfile
) -> list[CheckResult]:
    creators = read_field(source, profile["creators"])
    items = creators if isinstance(creators, list) else []
    names = [_creator_name(item) for item in items]
    orcids = [
        item.get(profile["creator_orcid_field"]) if isinstance(item, Mapping) else None
        for item in items
    ]
    affiliations = [_affiliations(item) for item in items]
    orcid_evidence = [
        _creator_orcid_evidence(item, value, index, profile)
        for index, (item, value) in enumerate(zip(items, orcids))
    ]
    all_have_orcids = bool(items) and all(valid_orcid(value) for value in orcids)
    all_have_affiliations = bool(items) and all(
        any(_organization_present(value) for value in values)
        for values in affiliations
    )

    return [
        make_result(
            "M6", "Test-01", "At least one named creator",
            profile["creators"], creators,
            status="PASS" if any(names) else "FAIL",
            message="Groups and organizations can also be named creators.",
            max_points=1,
            evidence=names,
        ),
        make_result(
            "M6", "Test-02", "All creators have valid ORCIDs",
            profile["creators"], creators,
            status="PASS" if all_have_orcids else "FAIL",
            message="ORCID format and checksum are checked; ownership is not inferred.",
            max_points=1,
            kind="bonus",
            evidence=orcids,
        ),
        make_result(
            "M6", "Test-02-01", "Author surnames match resolved ORCIDs",
            profile["creators"], creators,
            status=all_pass_status(item["status"] for item in orcid_evidence),
            message=(
                "Each creator's metadata surname is compared with the public "
                "ORCID family name. A surname match does not establish ownership."
            ),
            kind="diagnostic",
            evidence=orcid_evidence,
        ),
        make_result(
            "M6", "Test-03", "All creators have affiliations",
            profile["creators"], creators,
            status="PASS" if all_have_affiliations else "FAIL",
            message="Every creator needs at least one named or identified affiliation.",
            max_points=1,
            kind="bonus",
            evidence=affiliations,
        ),
    ]


def _organization_values(
    source: Metadata, creators: list[Any], profile: MetadataProfile
) -> list[Any]:
    organizations = [value for item in creators for value in _affiliations(item)]
    for field in ("publisher", "repository", "organizations"):
        value = source.get(field)
        if isinstance(value, list):
            organizations.extend(value)
        elif value is not None:
            organizations.append(value)
    for field in profile.get("organization_fields", ()):
        value = read_field(source, field)
        if value is not None:
            organizations.append(value)

    publisher = read_field(source, "metadata.publisher")
    if publisher is not None:
        organizations.append(publisher)
    for field in ("funders", "funding_list", "metadata.grants"):
        funders = read_field(source, field)
        if not isinstance(funders, list):
            continue
        for funder in funders:
            if not isinstance(funder, Mapping):
                continue
            organization = (
                funder.get("funder")
                or funder.get("organization")
                or funder.get("funder_name")
            )
            if organization is not None:
                organizations.append(organization)
            if normalize_text(funder.get("identifierType")) == "ror":
                organizations.append({"ror": funder.get("identifier")})
    return organizations


def _organization_checks(
    source: Metadata, profile: MetadataProfile
) -> list[CheckResult]:
    raw_creators = read_field(source, profile["creators"])
    creators = raw_creators if isinstance(raw_creators, list) else []
    organizations = _organization_values(source, creators, profile)
    rors = _ror_values(organizations, creators)
    unique_rors = {str(value): value for value in rors}
    evidence = [_ror_evidence(value) for value in unique_rors.values()]
    invalid_ror = any(item["status"] == "FAIL" for item in evidence)
    present = any(_organization_present(value) for value in organizations)
    fields = ("publisher", "affiliations", "repository", *profile.get("organization_fields", ()))

    # Hosting provenance does not invent an organization absent from metadata.
    return [
        make_result(
            "M7", "Test-01", "At least one organization",
            " / ".join(fields), organizations,
            status="PASS" if present else "FAIL",
            message=(
                "Requires a named or identified publisher, affiliation or "
                "repository in the metadata."
            ),
            max_points=1,
        ),
        make_result(
            "M7", "Test-02", "Organization ROR identifiers are valid",
            "affiliations / organizations", rors,
            status="FAIL" if invalid_ror else "UNSURE",
            message=(
                "ROR identifiers are verified in the registry; names are not "
                "semantically matched." if rors else "No ROR identifier is supplied."
            ),
            kind="diagnostic",
            evidence=evidence,
        ),
    ]


def _classify_type(value: str) -> str:
    if value == "dataset":
        return "Dataset"
    if value in FILE_FORMATS:
        return "File format"
    if value in OTHER_RESOURCE_TYPES:
        return "Other resource type"
    return "Unknown"


def _type_checks(source: Metadata, profile: MetadataProfile) -> list[CheckResult]:
    if profile["type"] is None:
        return [make_result(
            "M8", test, label, "type (unmapped)", None,
            status="UNSURE", max_points=points, kind=kind,
            message=(
                "No generic resource type is mapped from this endpoint. "
                "Experimental method, molecular composition and file format "
                "are not declarations of the Dataset resource type."
            ),
        ) for test, label, points, kind in (
            ("Test-01", "Resource type is present", 1, "required"),
            ("Test-02", "Resource type classification", 0, "diagnostic"),
        )]
    resource_type = read_field(source, profile["type"])
    normalized = normalize_text(resource_type)
    classification = _classify_type(normalized)
    classification_status = {
        "Dataset": "PASS", "Unknown": "UNSURE",
    }.get(classification, "FAIL")
    return [
        make_result(
            "M8", "Test-01", "Resource type is present",
            profile["type"], resource_type,
            status="PASS" if normalized else "FAIL",
            message="Requires a nonempty resource type.",
            max_points=1,
        ),
        make_result(
            "M8", "Test-02", "Resource type classification",
            profile["type"], resource_type,
            status=classification_status,
            message=f"Declared type classification: {classification}.",
            kind="diagnostic",
            classification=classification,
        ),
    ]


def evaluate_metadata(
    source: Metadata, repository: str, legacy_rules: Sequence[Rule],
    *, identifier_targets: Sequence[IdentifierTarget] | None = None,
) -> list[CheckResult]:
    """Run each group in order, then retain presence rules outside M1–M9."""
    profile = PROFILES[repository]
    checks = _identifier_checks(source, repository, profile, identifier_targets)
    checks.extend(_title_checks(source, profile))
    checks.extend(_description_checks(source, profile))
    checks.extend(_keyword_checks(source, profile))
    checks.append(_subject_check(source, repository, profile))
    checks.extend(_creator_checks(source, profile))
    checks.extend(_organization_checks(source, profile))
    checks.extend(_type_checks(source, profile))
    checks.extend(date_checks(source, repository))

    remaining_rules = [
        rule for rule in legacy_rules if rule.field not in profile["replaced"]
    ]
    checks.extend(evaluate_rules(source, remaining_rules))
    return checks
