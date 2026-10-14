"""Identity checks preserve dataset, series and version roles separately."""

import re
from typing import Any
from urllib.parse import unquote

from .checks import CheckResult, all_pass_status, normalize_text, read_field
from .generic_metadata_model import CheckBuilder
from .metadata_identifiers import identifier_syntax
from .pdb_identifiers import normalize_pdb_id
from .references import extract_doi, parse_url


def dataset_binding(builder: CheckBuilder) -> tuple[str, list[CheckResult]]:
    source, context, repository = builder.source, builder.context, builder.repository
    record_id = source.get("id")
    _, valid_id, _ = identifier_syntax(record_id, local_scheme=f"{repository}:record-id")
    evidence: list[CheckResult] = [{"field": "id", "value": record_id}]
    if not valid_id:
        return builder.missing_status(), evidence
    requested_identifier = context.expected_identifier or context.reference
    doi = extract_doi(requested_identifier) if requested_identifier else None
    native_doi = read_field(source, builder.fields["doi"])
    parsed = extract_doi(native_doi) if isinstance(native_doi, str) else None
    native_pattern = {
        "zenodo": r"10\.5281/zenodo\.([1-9][0-9]*)",
        "figshare": r"10\.6084/m9\.figshare\.([1-9][0-9]*)(?:\.v[1-9][0-9]*)?",
    }.get(repository)
    native_id = re.fullmatch(native_pattern, parsed, re.I) if native_pattern and parsed else None
    if native_id and native_id.group(1) != str(record_id):
        evidence.append({"field": builder.fields["doi"], "value": parsed,
            "message": "Native DOI and repository record ID disagree."})
        return "FAIL", evidence
    if doi:
        identifiers = [parsed]
        if repository == "zenodo":
            concept = source.get("conceptdoi")
            identifiers.append(extract_doi(concept) if isinstance(concept, str) else None)
        elif repository == "figshare" and native_id:
            # An unversioned series DOI can retrieve the latest version.
            # A versioned input must still match the exact returned version.
            identifiers.append(re.sub(r"\.v[1-9][0-9]*$", "", parsed, flags=re.I))
        evidence.append({"input": doi, "declaredIdentifiers": identifiers})
        if doi.lower() not in {value.lower() for value in identifiers if value}:
            return builder.missing_status() if not parsed else "FAIL", evidence
    elif context.expected_record_id is not None:
        evidence.append({"expectedRecordId": context.expected_record_id})
        if str(record_id) != context.expected_record_id:
            return "FAIL", evidence
    else:
        # An offline fixture has no requested target. Do not manufacture a match.
        return "UNSURE", evidence

    # Dryad's dataset endpoint declares the object role. For general-purpose
    # repositories use the native type as additional evidence alongside the ID
    # and endpoint, rather than treating @type or a shared domain as identity.
    resource_type = read_field(source, builder.fields["type"])
    evidence.append({"field": builder.fields["type"], "value": resource_type})
    if repository == "dryad" or normalize_text(resource_type) == "dataset":
        return "PASS", evidence
    if normalize_text(resource_type) in {"publication", "software", "poster", "presentation"}:
        return "FAIL", evidence
    return "UNSURE", evidence


def resolver_target_status(spec: dict[str, Any], target: Any) -> str:
    """A successful homepage cannot establish that a PID reaches this object."""
    url = parse_url(target) if isinstance(target, str) else None
    if spec.get("bindingStatus") == "FAIL":
        return "FAIL"
    if url is None or spec.get("bindingStatus") != "PASS":
        return "UNSURE"
    repository, record_id = spec["repository"], str(spec["recordId"])
    path = unquote(url.path)
    if repository == "pdb":
        if url.hostname in {"wwpdb.org", "www.wwpdb.org"} and path.rstrip("/") == "/pdb":
            from urllib.parse import parse_qs
            ids = parse_qs(url.query).get("id", [])
            target_id = normalize_pdb_id(ids[0]) if len(ids) == 1 else None
        elif url.hostname in {"rcsb.org", "www.rcsb.org", "data.rcsb.org"}:
            match = re.fullmatch(r"/(?:structure|rest/v1/core/entry)/([^/]+)/?", path)
            target_id = normalize_pdb_id(match.group(1)) if match else None
        else:
            return "UNSURE"
        return "PASS" if target_id == normalize_pdb_id(record_id) else "FAIL" if target_id else "UNSURE"
    hosts_and_paths = {
        "zenodo": (
            {"zenodo.org", "www.zenodo.org"},
            r"/(?:records?|api/records)/([1-9][0-9]*)/?",
        ),
        "figshare": (
            {"figshare.com", "www.figshare.com", "api.figshare.com"},
            r"/(?:articles/(?:[^/]+/[^/]+/)?([1-9][0-9]*)(?:/([1-9][0-9]*))?"
            r"|v2/articles/([1-9][0-9]*)(?:/versions/([1-9][0-9]*))?)/?",
        ),
    }
    if repository == "dryad":
        if url.hostname not in {"datadryad.org", "www.datadryad.org"}:
            return "UNSURE"
        doi = spec.get("doi")
        match = re.fullmatch(
            r"/(?:dataset|stash/dataset|resource|api/v2/datasets)/"
            r"(?:doi:)?(10\.5061/dryad\.[^/?#\s]+)/?", path, re.I,
        )
        target_doi = extract_doi(match.group(1)) if match else None
        if doi and target_doi:
            return "PASS" if doi.lower() == target_doi.lower() else "FAIL"
        landing_value = spec.get("landingPage")
        landing_page = parse_url(landing_value) if isinstance(landing_value, str) else None
        legacy_dataset_path = re.fullmatch(
            r"/(?:dataset|stash/dataset|resource)/[1-9][0-9]*/?", path,
        )
        if landing_page and legacy_dataset_path and (url.hostname, url.path, url.query) == (
            landing_page.hostname, landing_page.path, landing_page.query,
        ):
            return "PASS"
        # Legacy landing URLs may use an unrelated resource ID. They need a
        # documented crosswalk; matching the domain alone is never sufficient.
        return "UNSURE"
    hosts, pattern = hosts_and_paths[repository]
    match = re.fullmatch(pattern, path)
    if url.hostname not in hosts or match is None:
        return "UNSURE"
    resolved_id = match.group(1) if repository == "zenodo" else match.group(1) or match.group(3)
    if resolved_id != record_id:
        return "FAIL"
    expected_version = spec.get("version")
    if repository == "figshare" and expected_version is not None:
        resolved_version = match.group(2) or match.group(4)
        # An unversioned article URL cannot verify a particular version.
        if resolved_version is None:
            return "UNSURE"
        return "PASS" if resolved_version == str(expected_version) else "FAIL"
    return "PASS"


def identity_checks(builder: CheckBuilder) -> list[CheckResult]:
    source, fields, context = builder.source, builder.fields, builder.context
    doi = read_field(source, fields["doi"])
    _, valid_doi, resolver = identifier_syntax(doi)
    record_scheme = f"{builder.repository}:record-id"
    _, valid_local, _ = identifier_syntax(source.get("id"), local_scheme=record_scheme)
    evidence = [
        {"field": "id", "value": source.get("id"), "namespace": record_scheme,
            "role": "repository_record", "status": "PASS" if valid_local else builder.missing_status()},
        {"field": fields["doi"], "value": doi, "role": "dataset",
            "status": "PASS" if valid_doi else builder.missing_status()},
    ]
    if builder.repository == "zenodo" and source.get("conceptdoi") is not None:
        evidence.append({"field": "conceptdoi", "value": source["conceptdoi"],
            "role": "dataset_series"})
    binding, binding_evidence = dataset_binding(builder)
    checks = [
        builder.result(
            "G01",
            "identifier.interpretable",
            "Dataset identifier is interpretable",
            f"id / {fields['doi']}",
            evidence,
            status="PASS" if valid_local or valid_doi else builder.missing_status(),
            message=(
                "A repository-qualified record ID or recognized dataset identifier is "
                "sufficient; syntax does not prove uniqueness."
            ),
            evidence=evidence,
            supports=("known_object_search",),
        ),
        builder.result(
            "G01",
            "metadata.target_binding",
            "Metadata describe the requested dataset",
            f"id / {fields['doi']}",
            context.reference,
            status=binding,
            evidence=binding_evidence,
            message=(
                "Compare the requested reference with native IDs and the object role in this "
                "API representation."
            ),
            supports=("known_object_search",),
        ),
    ]
    version_value = read_field(source, builder.mapping.version)
    version_doi = extract_doi(doi) if isinstance(doi, str) else None
    doi_match =(
        re.search(r"\.v([1-9][0-9]*)$", version_doi or "", re.I)
        if builder.repository == "figshare"
        else None
    )
    version_status = "NOT_APPLICABLE"
    version_active = context.expected_version is not None or doi_match is not None and version_value is not None
    if version_active:
        if version_value is None and doi_match is None:
            version_status = builder.missing_status()
        else:
            expected_version = context.expected_version or doi_match.group(1)
            matches = [str(value) == expected_version for value in (
                version_value, doi_match.group(1) if doi_match else None,
            ) if value is not None]
            version_status = all_pass_status("PASS" if match else "FAIL" for match in matches)
    checks.append(builder.result(
        "G01",
        "version.binding",
        "Metadata match the requested version",
        builder.mapping.version,
        version_value,
        status=version_status,
        applicable=version_active,
        applicability_reason=(
            "Evaluate a selected version or consistency between an explicit version DOI "
            "and version label."
        ),
        evidence=[{"version": version_value, "versionDoi": version_doi,
            "expectedVersion": context.expected_version}],
        message=(
            "Version labels and series identifiers are kept separate; a version number "
            "need not be a PID."
        ),
    ))
    details = {}
    if resolver and binding == "PASS":
        details["verification"] = {
            "kind": "resolve", "url": resolver, "repository": builder.repository,
            "recordId": source.get("id"), "bindingStatus": binding,
            "doi": version_doi,
            "version": context.expected_version or (doi_match.group(1) if doi_match else None),
            "landingPage": read_field(source, builder.mapping.landing_page),
        }
    checks.append(builder.result(
        "G01",
        "pid.resolution",
        "Dataset PID reaches the matching object",
        fields["doi"],
        doi,
        status="UNSURE",
        required=False,
        message=(
            "Resolver reachability and target binding require external verification; "
            "persistence is not inferred from one request."
        ),
        sourceUrl=resolver,
        **details,
    ))
    return checks
