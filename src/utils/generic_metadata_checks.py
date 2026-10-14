"""G01–G10 checks for Zenodo, Dryad and Figshare public API representations.

Presence, syntax and meaning have separate results. Semantic questions remain
UNSURE without calibrated evidence; length and field counts do not earn points.
The repository field catalog is used for policies, not mandatory presence tests.
"""

from collections import Counter
from collections.abc import Mapping

from .checks import (
    CheckResult, Metadata, all_pass_status, has_value, normalize_text, plain_text, read_field,
)
from .generic_metadata_config import (
    CONTRIBUTOR_ROLES, DATA_KINDS, RELATION_ACCESSIONS, RELATION_TYPES,
    TITLE_PLACEHOLDER,
)
from .generic_metadata_identity import dataset_binding, identity_checks
from .generic_metadata_model import CheckBuilder, EvaluationContext
from .generic_metadata_scope import scope_checks
from .metadata_config import FILE_FORMATS, FOS
from .metadata_evidence import (
    affiliations, creator_name, creator_orcid_evidence, fos_match,
    ror_evidence, ror_values, subject_evidence,
)
from .metadata_identifiers import identifier_syntax


def _text_checks(builder: CheckBuilder) -> list[CheckResult]:
    title = read_field(builder.source, builder.fields["title"])
    description = read_field(builder.source, builder.fields["description"])
    title_text = normalize_text(title)
    description_text = normalize_text(description, html=True)
    placeholder = bool(TITLE_PLACEHOLDER.fullmatch(title_text))
    title_status = "UNSURE"
    if not title_text:
        title_status = builder.missing_status()
    elif placeholder and builder.context.complete:
        title_status = "FAIL"
    repeated = bool(title_text) and description_text == title_text
    description_status = builder.missing_status() if not description_text else "UNSURE"
    return [
        builder.result(
            "G02",
            "name.present",
            "Name is present",
            builder.fields["title"],
            title,
            status="PASS" if title_text else builder.missing_status(),
            message="Requires nonempty text, with no word-count or length threshold.",
            supports=("name_search",),
        ),
        builder.result(
            "G02",
            "name.informative",
            "Name identifies the data",
            builder.fields["title"],
            title,
            status=title_status,
            semantic=True,
            message=(
                "Recognized placeholder."
                if placeholder
                else "Identifying meaning or an established proper name requires semantic evidence."
            ),
            evidence=[{"text": plain_text(title)}],
            supports=("name_search", "result_recognition"),
        ),
        builder.result(
            "G03",
            "description.present",
            "Content summary is present",
            builder.fields["description"],
            description,
            status="PASS" if description_text else builder.missing_status(),
            message="Requires nonempty text after HTML parsing.",
            supports=("thematic_search",),
        ),
        builder.result(
            "G03",
            "description.data_focus",
            "Summary describes the actual data",
            builder.fields["description"],
            description,
            status=description_status,
            semantic=True,
            message=(
                "The content must characterize the data; text length or an article abstract "
                "alone is not evidence."
            ),
            evidence=[{"text": plain_text(description, html=True)}],
            supports=("thematic_search",),
        ),
        builder.result(
            "G03",
            "description.discriminating_information",
            "Summary adds distinguishing information",
            builder.fields["description"],
            description,
            status="FAIL" if repeated and builder.context.complete else description_status,
            semantic=True,
            message=(
                "The summary exactly repeats the normalized name."
                if repeated
                else "Distinct text alone does not establish useful distinguishing content."
            ),
            evidence=[{"text": plain_text(description, html=True), "repeatsName": repeated}],
            supports=("thematic_search", "result_recognition"),
        ),
    ]


def _term_checks(builder: CheckBuilder) -> list[CheckResult]:
    fields, source = builder.fields, builder.source
    keywords = read_field(source, fields["keywords"])
    # Figshare declares tags and keywords as aliases. Use one source, never
    # count the same assignment twice or fall back from an explicitly empty list.
    keyword_path = fields["keywords"]
    if builder.repository == "figshare" and keywords is None:
        keywords, keyword_path = source.get("tags"), "tags"
    keyword_items = keywords if isinstance(keywords, list) else []
    subjects = read_field(source, fields["subjects"])
    subject_items = subjects if isinstance(subjects, list) else [subjects] if has_value(subjects) else []
    terms = [normalize_text(value) for value in keyword_items]
    terms = [term for term in terms if term]
    labels = []
    for item in subject_items:
        label = item
        if isinstance(item, Mapping):
            label = item.get("term") if builder.repository == "zenodo" else item.get("title")
        text = normalize_text(label)
        if text:
            labels.append(text)
    all_terms = terms + labels
    declared = bool(all_terms or any(has_value(item) for item in subject_items))
    applicable = True if declared else None
    reason = (
        "Evaluate declared thematic access points; their absence does not establish "
        "that this task is required."
    )
    generic_only = bool(all_terms) and set(all_terms) <= {"science", "data", "dataset"}
    checks = [
        builder.result(
            "G04",
            "terms.relevant",
            "Terms describe a distinguishing topic",
            f"{keyword_path} / {fields['subjects']}",
            {"keywords": keywords, "subjects": subjects},
            status="FAIL" if generic_only and builder.context.complete else "UNSURE",
            semantic=True,
            message=(
                "Only nondistinguishing generic terms are supplied."
                if generic_only
                else "Relevance must be checked against the data description or documentation."
            ),
            applicable=applicable,
            applicability_reason=reason,
            normalizedValue=list(dict.fromkeys(all_terms)),
            supports=("thematic_search",),
        ),
        builder.result(
            "G04",
            "terms.access_function",
            "Terms provide a thematic access key",
            f"{keyword_path} / {fields['subjects']}",
            all_terms,
            status="PASS" if all_terms else "UNSURE",
            message=(
                "Labeled structured terms can be mapped to a harvester's thematic key; "
                "duplication in flat text alone is not another benefit."
            ),
            applicable=applicable,
            applicability_reason=reason,
            supports=("thematic_browsing",),
        ),
    ]
    duplicates = [term for term, count in Counter(all_terms).items() if count > 1]
    checks.append(builder.result(
        "G04",
        "terms.duplicates",
        "Repeated thematic terms",
        keyword_path,
        duplicates,
        status="WARNING" if duplicates else "PASS",
        required=False,
        message="Duplicate terms are reported without changing the capability assessment.",
        applicable=applicable,
        applicability_reason=reason,
    ))
    if subject_items:
        evidence = [subject_evidence(item, builder.repository) for item in subject_items]
        checks.append(builder.result(
            "G04",
            "concepts.valid",
            "Declared concepts exist in their vocabulary",
            fields["subjects"],
            subjects,
            required=False,
            status=all_pass_status(item["status"] for item in evidence),
            message="Every declared concept is checked; vocabulary membership does not prove relevance.",
            evidence=evidence,
            evidenceAggregation="all",
        ))
        alignments = []
        for item, validity in zip(subject_items, evidence):
            alignment = {**validity, "status": "UNSURE", "message": "No verified vocabulary label mapping."}
            if builder.repository == "dryad":
                alignment["status"] = validity["status"]
            elif isinstance(item, Mapping):
                label = plain_text(item.get("term") if builder.repository == "zenodo" else item.get("title"))
                if validity.get("code") in FOS:
                    if normalize_text(label) == normalize_text(FOS[validity["code"]]):
                        alignment["status"] = "PASS"
                    elif fos_match(label) is not None:
                        alignment["status"] = "FAIL"
                elif "verification" in validity:
                    alignment["verification"] = {**validity["verification"], "matchLabel": True, "label": label}
            alignments.append(alignment)
        checks.append(builder.result(
            "G04",
            "concepts.label_alignment",
            "Concept labels match their vocabulary",
            fields["subjects"],
            subjects,
            status=all_pass_status(item["status"] for item in alignments),
            required=False,
            message="Registry labels and membership are separate from topical relevance.",
            evidence=alignments,
            evidenceAggregation="all",
        ))
    return checks


def _data_kind_check(builder: CheckBuilder) -> CheckResult:
    value = read_field(builder.source, builder.fields["type"])
    normalized = normalize_text(value)
    kind = DATA_KINDS.get(normalized)
    status = "PASS" if kind else "UNSURE"
    return builder.result(
        "G05",
        "data_kind.usable",
        "Scientific data kind is interpretable",
        builder.fields["type"] or "data_kind (unmapped)",
        value,
        status=status,
        message=(f"Content crosswalk: {kind}." if kind else
            (
                "Dataset declares the object role; file formats and containers do not "
                "establish data kind."
            ) if normalized == "dataset" or normalized in FILE_FORMATS else
            "No supported content-kind crosswalk; the description needs semantic review."),
        normalizedValue=kind,
        evidence=[{"description": plain_text(read_field(builder.source, builder.fields["description"]), html=True)}],
        supports=("data_kind_search",),
    )


def agent_checks(builder: CheckBuilder) -> list[CheckResult]:
    source, fields = builder.source, builder.fields
    raw = read_field(source, fields["creators"])
    creators = raw if isinstance(raw, list) else []
    evidence = [{"index": index, "name": creator_name(item), "role": "creator",
        "status": "PASS" if creator_name(item) else builder.missing_status()}
        for index, item in enumerate(creators)]
    status = all_pass_status(item["status"] for item in evidence) if creators else builder.missing_status()
    checks = [
        builder.result(
            "G06",
            "origin.named",
            "Every declared creator is named",
            fields["creators"],
            raw,
            status=status,
            message=(
                "Persons, teams and organizations are allowed; a host or publisher cannot "
                "replace the creator."
            ),
            evidence=evidence,
            supports=("creator_search",),
        ),
        builder.result(
            "G06",
            "agent_role.usable",
            "Creator roles are preserved",
            fields["creators"],
            evidence,
            status=status,
            message=(
                "The native creator/author list declares the creator role; coverage is "
                "evaluated for every item."
            ),
            supports=("creator_search",),
        ),
    ]
    contributors = read_field(source, builder.mapping.contributors)
    if has_value(contributors):
        items = contributors if isinstance(contributors, list) else [contributors]
        role_evidence = []
        for index, item in enumerate(items):
            name = creator_name(item)
            role = plain_text(item.get(builder.mapping.contributor_role)) if isinstance(item, Mapping) else ""
            role_status = builder.missing_status()
            if name and role:
                role_status = "PASS" if normalize_text(role) in CONTRIBUTOR_ROLES else "UNSURE"
            role_evidence.append({
                "index": index, "name": name, "role": role, "status": role_status,
            })
        checks.append(builder.result(
            "G06",
            "agent_role.contributor.usable",
            "Contributor roles are interpretable",
            builder.mapping.contributors,
            contributors,
            status=all_pass_status(item["status"] for item in role_evidence),
            message=(
                "Native contributor roles remain distinct from creators; unspecified or "
                "unknown roles remain uncertain."
            ),
            evidence=role_evidence,
        ))
    organizations = [value for creator in creators for value in affiliations(creator)]
    for path, role in builder.mapping.publishers:
        value = read_field(source, path)
        if value is None:
            continue
        name = plain_text(value) if isinstance(value, str) else creator_name(value)
        checks.append(builder.result(
            "G06",
            f"agent_role.{role}.usable",
            f"Declared {role} is named",
            path,
            value,
            status="PASS" if name else builder.missing_status(),
            message=f"Preserve the explicit {role} role; do not infer it from the server domain.",
            evidence=[{"name": name, "role": role}],
        ))
        organizations.append(value)
    supplied_orcids = [(index, item) for index, item in enumerate(creators)
        if isinstance(item, Mapping) and plain_text(item.get(fields["creator_orcid_field"])) not in {"", "?", "."}]
    orcid_evidence = [creator_orcid_evidence(
        item, item.get(fields["creator_orcid_field"]) if isinstance(item, Mapping) else None,
        index, fields,
    ) for index, item in supplied_orcids]
    checks.append(builder.result(
        "G06",
        "agent_identifier.orcid_name_consistent",
        "Supplied ORCIDs match creator surnames",
        fields["creators"],
        raw,
        status=all_pass_status(item["status"] for item in orcid_evidence) if supplied_orcids else "NOT_APPLICABLE",
        applicable=bool(supplied_orcids),
        applicability_reason="Validate supplied optional ORCIDs; missing ORCIDs do not prevent creator search.",
        required=False,
        message=(
            "Optional consistency diagnostic; missing ORCIDs do not fail the origin task "
            "and a name match does not authenticate ownership."
        ),
        evidence=orcid_evidence,
        evidenceAggregation="all",
    ))
    rors = ror_values(organizations, creators)
    if rors:
        ror_items = [ror_evidence(value) for value in rors]
        checks.append(builder.result(
            "G06",
            "agent_identifier.ror_valid",
            "Supplied ROR identifiers exist",
            "affiliations / publisher / repository",
            rors,
            status=all_pass_status(item["status"] for item in ror_items),
            required=False,
            message=(
                "Registry existence is separate from binding the identifier to the named "
                "organization."
            ),
            evidence=ror_items,
            evidenceAggregation="all",
        ))
    return checks


def _relation_checks(builder: CheckBuilder) -> list[CheckResult]:
    value = read_field(builder.source, builder.mapping.relations)
    items = value if isinstance(value, list) else [value] if has_value(value) else []
    targets, types = [], []
    for index, item in enumerate(items):
        target = item.get("identifier") if isinstance(item, Mapping) else None
        declared_scheme = normalize_text(item.get(builder.mapping.relation_scheme)) if isinstance(item, Mapping) else ""
        scheme, valid, _ = identifier_syntax(target)
        if declared_scheme in {"doi", "url", "uri", "handle", "ark"}:
            valid = valid and (declared_scheme in {"uri", "url"} or normalize_text(scheme) == declared_scheme)
        accession_pattern = RELATION_ACCESSIONS.get(declared_scheme)
        if not valid and accession_pattern:
            valid = bool(accession_pattern.fullmatch(plain_text(target)))
            scheme = declared_scheme
        target_status = "PASS" if valid else builder.missing_status()
        if not valid and plain_text(target) and declared_scheme and declared_scheme not in {
            "doi", "url", "uri", "handle", "ark", "urn", *RELATION_ACCESSIONS,
        }:
            target_status = "UNSURE"
        targets.append({"index": index, "value": target, "declaredScheme": declared_scheme,
            "scheme": scheme, "status": target_status})
        relation = item.get(builder.mapping.relation_type) if isinstance(item, Mapping) else None
        normalized = normalize_text(relation).replace(" ", "").replace("_", "")
        native_relation = builder.repository == "dryad" and normalize_text(relation) in {
            "primary_article", "article", "dataset", "preprint", "software", "supplemental_information",
        }
        types.append({"index": index, "value": relation, "direction": "dataset_to_target",
            "meaning": "Dryad associated resource (not equivalence or derivation)" if native_relation else relation,
            "status": "PASS" if normalized in RELATION_TYPES or native_relation else "UNSURE" if normalized else builder.missing_status()})
    applicable = True if items else None
    reason = (
        "Declared relations are evaluated; absence does not establish an expected "
        "related article or dataset."
    )
    checks = []
    for test, label, evidence in (
        ("relation.target_interpretable", "Every related target is interpretable", targets),
        ("relation.type_usable", "Every relation has an interpretable type and direction", types),
    ):
        checks.append(builder.result(
            "G09",
            test,
            label,
            builder.mapping.relations,
            value,
            status=all_pass_status(item["status"] for item in evidence),
            message=(
                "Relation targets and directions are independent; one valid edge cannot hide "
                "malformed edges."
            ),
            applicable=applicable,
            applicability_reason=reason,
            evidence=evidence,
            supports=("relation_navigation",),
        ))
    checks.append(builder.result(
        "G09",
        "relation.meaning_consistent",
        "Relation meaning agrees with its target",
        builder.mapping.relations,
        value,
        status="UNSURE",
        semantic=True,
        message=(
            "A recognized type or DOI does not verify the actual relationship or a "
            "reverse navigation route."
        ),
        applicable=applicable,
        applicability_reason=reason,
        supports=("relation_navigation",),
    ))
    return checks


def _publication_checks(builder: CheckBuilder) -> list[CheckResult]:
    url = builder.context.source_url
    route_status = "PASS" if url else "UNSURE"
    creators = read_field(builder.source, builder.fields["creators"])
    useful = bool(
        plain_text(read_field(builder.source, builder.fields["title"]))
        or plain_text(read_field(builder.source, builder.fields["description"]), html=True)
        or isinstance(creators, list) and any(creator_name(item) for item in creators)
    )
    parse_status = "PASS" if useful else "UNSURE"
    binding, _ = dataset_binding(builder)
    supported = all_pass_status((route_status, parse_status, binding))
    if supported == "PASS" and not builder.context.complete:
        supported = "UNSURE"
    return [
        builder.result(
            "G10",
            "metadata.route_available",
            "Public metadata API route was retrieved",
            "sourceUrl",
            url,
            status=route_status,
            message=(
                "Successful retrieval of this exact API representation is evidence of route "
                "availability; offline evaluation has no retrieval evidence."
            ),
            supports=("api_harvesting",),
        ),
        builder.result(
            "G10",
            "metadata.parseable",
            "Parser extracts relevant native metadata",
            "repositoryResponse",
            {"repository": builder.repository, "mappedContent": useful},
            status=parse_status,
            message=(
                "JSON syntax alone is insufficient; the supported parser must extract "
                "descriptive metadata."
            ),
            supports=("api_harvesting",),
        ),
        builder.result(
            "G10",
            "metadata.profile_supported",
            "The same representation supports the API profile",
            "sourceUrl",
            url,
            status=supported,
            message=(
                "Availability, parser mapping and dataset binding must hold for this same "
                "public API response."
            ),
            supports=("api_harvesting",),
        ),
        builder.result(
            "G10",
            "metadata.discovery_route",
            "Independent discovery route is documented",
            "discovery_routes (unmapped)",
            None,
            status="UNSURE",
            required=False,
            message=(
                "A supplied DOI does not demonstrate discovery through a sitemap, catalog or "
                "feed. Web crawling and observed indexing require another profile."
            ),
        ),
    ]


def evaluate_generic_metadata(
    source: Metadata, repository: str, *, context: EvaluationContext | None = None,
) -> list[CheckResult]:
    """Evaluate one unmerged representation; retain all independent subtests."""
    builder = CheckBuilder(source, repository, context or EvaluationContext())
    checks = identity_checks(builder)
    checks.extend(_text_checks(builder))
    checks.extend(_term_checks(builder))
    checks.append(_data_kind_check(builder))
    checks.extend(agent_checks(builder))
    checks.extend(scope_checks(builder))
    method = read_field(source, builder.mapping.method)
    method_text = plain_text(method, html=True)
    checks.append(builder.result(
        "G08", "generation_process.present", "Native method statement is present",
        builder.mapping.method or "generation_process (unmapped)", method,
        status="PASS" if method_text else "UNSURE",
        applicable=True if method_text else None,
        applicability_reason="Assess a declared native method; unmapped or inactive method-search tasks remain uncertain.",
        message="Checks the native method statement separately from its scientific meaning.",
        required=False, supports=("method_search",),
    ))
    checks.append(builder.result(
        "G08",
        "generation_process.searchable",
        "Generation process characterizes these data",
        builder.mapping.method or "generation_process (unmapped)",
        method,
        status=(
            "FAIL" if builder.context.complete and normalize_text(method_text) == "methods available"
            else "UNSURE"
        ),
        semantic=True,
        message=(
            "Method text must name a process and link it to these data; presence, a "
            "generic link or a methodological word alone is insufficient."
        ),
        applicable=True if method_text else None,
        applicability_reason=(
            "Declared generation information is evaluated; an absent value does not "
            "establish an active method-search task."
        ),
        evidence=[{"text": method_text}],
        supports=("method_search",),
    ))
    checks.extend(_relation_checks(builder))
    checks.extend(_publication_checks(builder))
    keyword_value = read_field(source, builder.fields["keywords"])
    if builder.repository == "figshare" and keyword_value is None:
        keyword_value = source.get("tags")
    subject_value = read_field(source, builder.fields["subjects"])
    term_evidence = []
    if keyword_value is not None:
        if not isinstance(keyword_value, list):
            term_evidence.append({"kind": "keyword_representation", "value": keyword_value,
                "status": builder.missing_status()})
        keyword_items = keyword_value if isinstance(keyword_value, list) else [keyword_value]
        term_evidence.extend({"kind": "keyword", "value": item,
            "status": "PASS" if plain_text(item) else builder.missing_status()} for item in keyword_items)
    subject_items = subject_value if isinstance(subject_value, list) else [subject_value] if subject_value is not None else []
    for item in subject_items:
        label = item.get("term" if repository == "zenodo" else "title") if isinstance(item, Mapping) else item
        term_evidence.append({"kind": "subject", "value": label,
            "status": "PASS" if plain_text(label) else builder.missing_status()})
    checks.append(builder.result(
        "G04", "terms.labels_usable", "Every declared thematic label is usable",
        f"{builder.fields['keywords']} / {builder.fields['subjects']}", term_evidence,
        status=all_pass_status(item["status"] for item in term_evidence),
        applicable=True if term_evidence else None,
        applicability_reason="Evaluate all declared access points; no keyword quota is imposed.",
        message="One usable keyword cannot hide empty or malformed declared labels.",
        evidence=term_evidence, supports=("thematic_search",),
    ))
    publication_path = {"zenodo": "status", "dryad": "visibility", "figshare": "is_public"}[repository]
    publication_value = read_field(source, publication_path)
    if repository == "figshare":
        publication_status = "PASS" if publication_value is True or publication_value == 1 else "FAIL" if publication_value is False or publication_value == 0 else "UNSURE"
    else:
        publication_status = "PASS" if normalize_text(publication_value) in {"public", "published"} else "FAIL" if normalize_text(publication_value) in {"private", "draft", "unpublished"} else "UNSURE"
    checks.append(builder.result(
        "G10", "metadata.publication_state", "Native metadata publication state is public",
        publication_path, publication_value,
        status=publication_status if builder.context.complete else "UNSURE",
        message="Metadata visibility is distinct from data-file access rights or embargoes.",
        required=False, supports=("api_harvesting",),
    ))
    checks.sort(key=lambda item: item["group"])
    return checks
