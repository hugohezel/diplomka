"""G01–G10 for a PDB structure entry and its explicitly linked polymer entities.

Polymer descriptions support entry context only through a verified entry/entity
binding. Article abstracts and citation authors never replace structure metadata.
"""

import math
import re
from collections.abc import Mapping

from .checks import all_pass_status, normalize_text, plain_text, read_field
from .generic_metadata_checks import agent_checks
from .generic_metadata_config import TITLE_PLACEHOLDER
from .generic_metadata_model import CheckBuilder, EvaluationContext
from .metadata_identifiers import identifier_syntax
from .pdb_identifiers import normalize_pdb_id
from .pdb_vocabulary import classification_evidence
from .references import extract_doi


METHODS = {
    "X-RAY DIFFRACTION", "SOLUTION NMR", "SOLID-STATE NMR", "ELECTRON MICROSCOPY",
    "ELECTRON CRYSTALLOGRAPHY", "NEUTRON DIFFRACTION", "POWDER DIFFRACTION",
    "SOLUTION SCATTERING", "FIBER DIFFRACTION", "INFRARED SPECTROSCOPY",
    "FLUORESCENCE TRANSFER", "EPR", "THEORETICAL MODEL",
}
RESOLUTION_METHODS = {
    "X-RAY DIFFRACTION", "ELECTRON MICROSCOPY", "ELECTRON CRYSTALLOGRAPHY",
    "NEUTRON DIFFRACTION", "POWDER DIFFRACTION", "FIBER DIFFRACTION",
}


def _positive_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def _positive_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _doi_entry(doi):
    parsed = extract_doi(doi) if isinstance(doi, str) else None
    match = re.fullmatch(r"10\.2210/(pdb[^/]+)/pdb", parsed or "", re.I)
    if not match:
        return None
    accession = match.group(1)
    return normalize_pdb_id(accession if accession.lower().startswith("pdb_") else accession[3:])


def evaluate_pdb_metadata(source, *, context=None, polymer_entities=None):
    builder = CheckBuilder(source, "pdb", context or EvaluationContext())
    result = builder.result
    entry_id = normalize_pdb_id(source.get("rcsb_id"))
    doi_path, doi = "database_2[].pdbx_DOI (database_id=PDB)", None
    for index, row in enumerate(source.get("database_2") or []):
        if isinstance(row, Mapping) and plain_text(row.get("database_id")).upper() == "PDB":
            doi_path, doi = f"database_2[{index}].pdbx_DOI", row.get("pdbx_DOI")
            break
    binding_evidence = [{"field": "rcsb_id", "value": entry_id, "expected": builder.context.expected_record_id}]
    contradictions = []
    if builder.context.expected_record_id and entry_id != normalize_pdb_id(builder.context.expected_record_id):
        contradictions.append("Requested and returned PDB accessions differ.")
    for path in ("entry.id", "rcsb_entry_container_identifiers.entry_id"):
        value = read_field(source, path)
        if value is not None and normalize_pdb_id(value) != entry_id:
            contradictions.append(f"{path} identifies another entry.")
        binding_evidence.append({"field": path, "value": value})
    if _doi_entry(doi) and _doi_entry(doi) != entry_id:
        contradictions.append("The PDB structure DOI identifies another entry.")
    binding = "FAIL" if contradictions else "PASS" if entry_id and builder.context.expected_record_id else "UNSURE"
    checks = [
        result("G01", "identifier.interpretable", "PDB accession has an explicit namespace", "rcsb_id", source.get("rcsb_id"),
            status="PASS" if entry_id else builder.missing_status(), message="Normalize legacy and extended PDB accessions in the PDB namespace.", supports=("accession_search",)),
        result("G01", "identifier.structure_doi_syntax", "Structure DOI uses the PDB namespace", doi_path, doi,
            status="PASS" if _doi_entry(doi) else builder.missing_status(), required=False,
            message="Select only database_id=PDB; BMRB and article DOIs identify different resources. The namespaced accession independently supports object identification."),
        result("G01", "metadata.target_binding", "Entry and structure DOI bind to the requested structure", "rcsb_id / entry.id / database_2", entry_id,
            status=binding, message=" ".join(contradictions) or "Compare the requested accession with native entry IDs and the selected structure DOI.", evidence=binding_evidence),
        result("G01", "version.binding", "Current-entry revision is distinguished from an immutable version", "rcsb_accession_info.major_revision / minor_revision", source.get("rcsb_accession_info"),
            status="NOT_APPLICABLE", applicable=False, applicability_reason="The declared profile evaluates the current structure entry; no immutable historical version was requested.",
            message="Major/minor revisions describe history; they are not a fabricated version PID."),
    ]
    resolver = f"https://doi.org/{extract_doi(doi)}" if _doi_entry(doi) else None
    verification = {"verification": {"kind": "resolve", "url": resolver, "repository": "pdb", "recordId": entry_id, "bindingStatus": binding}} if resolver and binding == "PASS" else {}
    checks.append(result("G01", "pid.resolution", "Structure DOI resolves to this entry", doi_path, doi,
        status="UNSURE", required=False, message="Resolver success must be bound to the same PDB accession.", sourceUrl=resolver, **verification))

    title = read_field(source, "struct.title")
    title_text = normalize_text(title)
    checks.extend([
        result("G02", "name.present", "Structure title is present", "struct.title", title,
            status="PASS" if title_text else builder.missing_status(), message="Use the structure title, not the citation title."),
        result("G02", "name.informative", "Title distinguishes the structural object", "struct.title", title,
            status=builder.missing_status() if not title_text or TITLE_PLACEHOLDER.fullmatch(title_text) else "UNSURE", semantic=True,
            message="Confirm that the title names a molecule, complex or structural state; no word-count threshold is used."),
    ])

    raw_ids = read_field(source, "rcsb_entry_container_identifiers.polymer_entity_ids")
    ids = raw_ids if isinstance(raw_ids, list) else []
    entities = polymer_entities or {}
    no_polymers = raw_ids == [] and read_field(source, "rcsb_entry_info.polymer_entity_count") == 0
    polymer_applicable = False if no_polymers else True if ids else None

    def polymer_evidence(reader):
        evidence = []
        for entity_id in ids:
            entity = entities.get(str(entity_id))
            item = {"entityId": entity_id, "sourceUrl": f"https://data.rcsb.org/rest/v1/core/polymer_entity/{entry_id}/{entity_id}", "targetLevel": "polymer entity"}
            if not isinstance(entity, Mapping):
                evidence.append({**item, "status": "UNSURE", "message": "Linked polymer metadata were not retrieved."})
                continue
            identifiers = entity.get("rcsb_polymer_entity_container_identifiers") or {}
            if (normalize_pdb_id(identifiers.get("entry_id")) != entry_id
                    or str(identifiers.get("entity_id")) != str(entity_id)):
                evidence.append({**item, "status": "FAIL", "message": "Polymer metadata identify another entry or entity."})
                continue
            evidence.append({**item, **reader(entity)})
        return evidence

    def polymer_status(evidence):
        return "NOT_APPLICABLE" if no_polymers else all_pass_status(item["status"] for item in evidence)

    def molecule_label(entity):
        value = read_field(entity, "rcsb_polymer_entity.pdbx_description")
        return {"value": value, "status": "PASS" if plain_text(value) else builder.missing_status()}

    labels = polymer_evidence(molecule_label)
    methods = read_field(source, "exptl[].method") or []
    composition = read_field(source, "rcsb_entry_info.polymer_composition")
    summary_status = all_pass_status((polymer_status(labels), "PASS" if plain_text(composition) and methods else "UNSURE"))
    checks.append(result("G03", "description.structured_content", "Bound molecular labels and entry facts describe the structural data",
        "rcsb_entry_info.polymer_composition / exptl[].method + polymer_entity.rcsb_polymer_entity.pdbx_description",
        {"composition": composition, "methods": methods}, status=summary_status,
        message="Combine entry-level facts with all explicitly linked polymer labels. A molecule label alone does not satisfy an entry-level summary; citation abstracts are excluded.",
        evidence=labels, coverage="All declared polymer entities plus bound structure-entry context."))

    keyword_text = read_field(source, "struct_keywords.text")
    keywords = [plain_text(term) for term in plain_text(keyword_text).split(",") if plain_text(term)]
    classification = read_field(source, "struct_keywords.pdbx_keywords")
    vocabulary = classification_evidence(classification)
    checks.extend([
        result("G04", "terms.access_function", "PDB keywords or classification supply topical access", "struct_keywords.text / struct_keywords.pdbx_keywords",
            {"keywords": keywords, "classification": classification}, status="PASS" if keywords or plain_text(classification) else builder.missing_status(),
            message="Use comma-separated free terms or the classification header; both are not mandatory."),
        result("G04", "terms.relevant", "Terms agree with the described molecules", "struct_keywords", source.get("struct_keywords"),
            status="UNSURE", semantic=True, message="Vocabulary membership alone does not prove functional or topical relevance."),
        result("G04", "concepts.valid", "Every classification component is in the reviewed vocabulary", "struct_keywords.pdbx_keywords", classification,
            status=all_pass_status(item["status"] for item in vocabulary["assignments"]) if plain_text(classification) else "NOT_APPLICABLE",
            required=False, applicable=bool(plain_text(classification)), applicability_reason="Validate a supplied classification; free keywords can support topical search independently.",
            message="Check all components of a composite header; unknown historical labels remain UNSURE.", evidence=[vocabulary]),
    ])

    atom_count = read_field(source, "rcsb_entry_info.deposited_atom_count")
    model_count = read_field(source, "rcsb_entry_info.deposited_model_count")
    checks.append(result("G05", "data_kind.usable", "The content is interpretable as atomic structural models",
        "rcsb_entry_info.deposited_atom_count / deposited_model_count / structure_determination_methodology",
        {"atomCount": atom_count, "modelCount": model_count, "methodology": read_field(source, "rcsb_entry_info.structure_determination_methodology")},
        status="PASS" if _positive_integer(atom_count) and _positive_integer(model_count) else "UNSURE",
        message="Bound atom/model counts and the documented PDB object model establish structural content, independently of coordinate-file format.", normalizedValue="macromolecular atomic structure models"))
    checks.extend(agent_checks(builder))

    checks.append(result("G07", "scope.entities.usable", "Every declared polymer molecule is named",
        "polymer_entity.rcsb_polymer_entity.pdbx_description", [item.get("value") for item in labels],
        status=polymer_status(labels), applicable=polymer_applicable, evidence=labels,
        applicability_reason="The molecular query profile assesses all polymers declared by the entry; non-polymers are a separate entity class.",
        message="A label for one polymer cannot cover the other declared polymer entities.", targetLevel="polymer entities linked to the structure entry", coverage="All declared polymer entities."))

    def taxonomy(entity):
        organisms = entity.get("rcsb_entity_source_organism")
        if not isinstance(organisms, list) or not organisms:
            return {"status": "UNSURE", "message": "Biological-source applicability is not established; expression hosts do not replace source organisms."}
        assignments = [{"name": row.get("ncbi_scientific_name"), "taxonId": row.get("ncbi_taxonomy_id"),
            "status": "PASS" if plain_text(row.get("ncbi_scientific_name")) and (row.get("ncbi_taxonomy_id") is None or _positive_integer(row.get("ncbi_taxonomy_id"))) else builder.missing_status()}
            if isinstance(row, Mapping) else {"status": builder.missing_status()} for row in organisms]
        return {"status": all_pass_status(row["status"] for row in assignments), "value": assignments}

    taxa = polymer_evidence(taxonomy)
    checks.append(result("G07", "scope.taxonomy.usable", "Declared source organisms have usable names and supplied taxon IDs",
        "polymer_entity.rcsb_entity_source_organism[].ncbi_scientific_name / ncbi_taxonomy_id", taxa,
        status=polymer_status(taxa), applicable=polymer_applicable, evidence=taxa,
        message="Assess every declared biological source, separately from an expression host. ID syntax does not prove registry membership.",
        applicability_reason="Assess biological sources for declared polymer entities; absent source information leaves applicability uncertain.",
        coverage="All declared biological sources in all declared polymer entities."))

    resolution = read_field(source, "rcsb_entry_info.resolution_combined")
    resolution_values = resolution if isinstance(resolution, list) else [resolution] if resolution is not None else []
    resolution_applicable = bool(resolution_values) or any(method in RESOLUTION_METHODS for method in methods)
    known_nmr = bool(methods) and all(method in {"SOLUTION NMR", "SOLID-STATE NMR"} for method in methods)
    resolution_status = all_pass_status("PASS" if _positive_number(value) else builder.missing_status() for value in resolution_values)
    if not resolution_values:
        resolution_status = builder.missing_status() if resolution_applicable else "NOT_APPLICABLE" if known_nmr else "UNSURE"
    checks.append(result("G07", "scope.properties.usable", "Reported structural resolution is interpretable",
        "rcsb_entry_info.resolution_combined[]", resolution, status=resolution_status,
        applicable=resolution_applicable if resolution_applicable or known_nmr else None,
        applicability_reason="Resolution applies to diffraction or microscopy methods; an NMR-only entry has no comparable crystallographic-resolution requirement.",
        message="Check every supplied resolution as a positive finite value in angstroms. No high-resolution cutoff or quality score is imposed.", coverage="Every supplied structural resolution."))

    def granularity(entity):
        chains = read_field(entity, "rcsb_polymer_entity_container_identifiers.asym_ids")
        valid = isinstance(chains, list) and bool(chains) and all(plain_text(chain) for chain in chains) and len(chains) == len(set(chains))
        return {"value": chains, "status": "PASS" if valid and _positive_integer(model_count) else builder.missing_status()}

    chains = polymer_evidence(granularity)
    checks.append(result("G07", "scope.granularity.usable", "Entity, chain and model levels are distinguishable",
        "polymer_entity.rcsb_polymer_entity_container_identifiers.entity_id / asym_ids[] + rcsb_entry_info.deposited_model_count", chains,
        status=polymer_status(chains), applicable=polymer_applicable, evidence=chains,
        applicability_reason="This molecular query profile distinguishes polymer entities, chain instances and deposited models.",
        message="Entity identity and chain identity are different levels; a positive model count supplies the entry model context.", coverage="All declared polymer entities and their declared chains."))

    def sequence(entity):
        raw = read_field(entity, "entity_poly.pdbx_seq_one_letter_code_can")
        value = re.sub(r"\s+", "", plain_text(raw))
        length = read_field(entity, "entity_poly.rcsb_sample_sequence_length")
        valid = bool(re.fullmatch(r"[A-Z]+", value)) and (length is None or _positive_integer(length) and length == len(value))
        return {"sequenceLength": len(value), "declaredLength": length, "status": "PASS" if valid else builder.missing_status()}

    sequences = polymer_evidence(sequence)
    checks.append(result("G07", "scope.sequences.usable", "Every polymer has an interpretable canonical sequence",
        "polymer_entity.entity_poly.pdbx_seq_one_letter_code_can / rcsb_sample_sequence_length", sequences,
        status=polymer_status(sequences), applicable=polymer_applicable, evidence=sequences,
        applicability_reason="Sequence search applies to the polymer subset explicitly declared by this structure entry.",
        message="Canonical sequence text and any supplied length must agree; sequence presence does not validate coordinates.", coverage="All declared polymer entities."))
    for dimension, label in (("spatial_coverage", "Geographic data coverage"), ("temporal_coverage", "Calendar-time data coverage")):
        checks.append(result("G07", f"scope.{dimension}.usable", label, "declared molecular search profile", None,
            status="NOT_APPLICABLE", applicable=False, applicability_reason="The declared profile searches structures by molecule, source organism, sequence, method and resolution; geographic or calendar-time filtering is outside this task.",
            message="Molecular coordinates are not geographic extent; deposition and release dates are lifecycle dates."))

    method_evidence = [{"value": method, "status": "PASS" if plain_text(method).upper() in METHODS else "UNSURE" if plain_text(method) else builder.missing_status()} for method in methods]
    checks.append(result("G08", "generation_process.searchable", "Every structural determination method is interpretable", "exptl[].method", methods,
        status=all_pass_status(item["status"] for item in method_evidence) if method_evidence else builder.missing_status(),
        message="Use the PDBx/mmCIF experimental-method enumeration; unknown methods need review rather than a guessed mapping.", evidence=method_evidence, coverage="All declared determination methods."))

    citation = source.get("rcsb_primary_citation")
    citation = citation if isinstance(citation, Mapping) else {}
    targets = []
    article_doi = citation.get("pdbx_database_id_DOI")
    pmid = citation.get("pdbx_database_id_PubMed")
    if article_doi is not None:
        targets.append({"namespace": "DOI", "value": article_doi, "status": "PASS" if identifier_syntax(article_doi)[1] else builder.missing_status()})
    if pmid is not None:
        targets.append({"namespace": "PubMed", "value": pmid, "status": "PASS" if _positive_integer(pmid) else builder.missing_status()})
    citation_active = True if citation else None
    checks.extend([
        result("G09", "relation.target_interpretable", "Declared primary-publication identifiers are interpretable", "rcsb_primary_citation.pdbx_database_id_DOI / pdbx_database_id_PubMed", targets,
            status=all_pass_status(item["status"] for item in targets) if targets else builder.missing_status() if citation else "UNSURE",
            applicable=citation_active, applicability_reason="Validate a declared primary citation; a publication is not required for every structure.",
            message="The publication DOI remains a relation target and never replaces the structure DOI.", evidence=targets, coverage="Every supplied primary-citation identifier."),
        result("G09", "relation.type_usable", "The primary-citation role and direction are preserved", "rcsb_primary_citation", citation or None,
            status="PASS" if citation and targets else "UNSURE", applicable=citation_active,
            applicability_reason="Assess a declared primary-structure-publication relation.",
            message="The documented relation points from the structure entry to its primary publication; it does not mean equivalence."),
        result("G09", "relation.meaning_consistent", "The primary publication actually describes this structure", "rcsb_primary_citation", citation or None,
            status="UNSURE", semantic=True, applicable=citation_active,
            applicability_reason="A declared publication relation needs content confirmation for semantic consistency.", message="A valid publication DOI alone cannot confirm the article's content."),
    ])

    route = "PASS" if builder.context.source_url and builder.context.complete else "UNSURE"
    useful = "PASS" if plain_text(title) or _positive_integer(atom_count) else "UNSURE"
    checks.extend([
        result("G10", "metadata.route_available", "Public entry metadata were retrieved", "sourceUrl", builder.context.source_url,
            status=route, message="The retrieved entry API is a metadata route; a coordinate-file download is not substituted."),
        result("G10", "metadata.parseable", "The native parser extracts useful structure metadata", "struct / rcsb_entry_info / exptl", {"title": title, "atomCount": atom_count, "methods": methods},
            status=useful, message="An empty JSON object is insufficient; the native structure representation must contain useful content."),
        result("G10", "metadata.profile_supported", "The public representation is bound and processable", "sourceUrl / rcsb_id", builder.context.source_url,
            status=all_pass_status((route, useful, binding)), message="Entry and related polymer representations use documented identifiers and preserve their different object levels."),
        result("G10", "metadata.discovery_route", "Catalog and structure-search discovery routes are documented", "RCSB Search API / holdings", "https://search.rcsb.org/",
            status="PASS", required=False, message="RCSB documents catalog/search routes to entry accessions. This is route documentation, not an observed indexing or ranking test."),
    ])
    checks.sort(key=lambda item: item["group"])
    return checks
