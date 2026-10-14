# Concrete search-readiness checks for four repositories

Designed with `design-search-readiness-checks`, reviewed **14 October 2026**.
Schema references: Zenodo public Records API; Dryad REST API v2; Figshare OpenAPI
API 2.0; RCSB REST v1/core and PDBx/mmCIF v5. Authoritative sources and native
representative responses were inspected on the review date.

The evaluated object is the dataset or selected version for Zenodo, Dryad and
Figshare, and the **current structure entry** for PDB. The search channel is a
public-API harvester with native mappings. Tasks cover identifier/name lookup,
topical matching, creator lookup, applicable content constraints, method lookup
and navigation to related resources. The PDB task additionally covers molecular
names, source organisms, polymer sequences, structural resolution and chain/model
granularity. Geographic and calendar-time filtering are excluded from that
declared molecular task, with explicit reasons.

Every individual UI result includes its field, target object/level, applicability,
PASS/FAIL/UNSURE rules, coverage, search benefit and dated schema sources.

## Decision and coverage rules

- **PASS:** evidence meets the stated criterion at the correct object level.
- **FAIL:** sufficient applicable metadata show an empty, invalid or contradictory value.
- **UNSURE:** retrieval, applicability, semantics or a verified mapping is incomplete.
- **NOT_APPLICABLE:** a stated task or supplied-identifier diagnostic excludes the criterion; give the reason.
- Presence, syntax, meaning and consistency remain separate tests. Semantic title,
  description, topical relevance and relationship-content questions need review.
- Validate **all declared** creators, relation targets, method values, concept
  assignments and labels. Topical access may use either keywords or subjects;
  the separate all-labels check prevents one valid term hiding malformed terms.
- For PDB, validate **all declared polymer entities**; explicitly distinguish
  polymer, non-polymer and entry levels. Unavailable related API metadata stay
  UNSURE. Do not infer all-molecule coverage from the polymer subset.
- Do not infer data kind from `Dataset`, ZIP or MIME alone. No length thresholds,
  tag quotas, universal weights or ranking/index-inclusion claims are introduced.

## G01 — Identity and metadata binding

Separate identifier interpretation, input/record binding, selected-version binding
and optional resolver verification. PASS requires namespace and object agreement;
FAIL requires missing applicable identity or a contradiction. Offline evaluation
without an expected object, unresolved redirects and unknown versions stay UNSURE.
Search benefit: known-object lookup and version disambiguation.

| Repository | Native checks and evidence |
| --- | --- |
| Zenodo | Compare `id`, `doi`, requested reference and `metadata.resource_type.type`. Keep `conceptdoi` as the series identity; `metadata.version` is a label, not automatically a PID. |
| Dryad | Compare `id` and `identifier` against the requested dataset DOI. The dataset endpoint establishes the object role; `versionNumber` is separate version evidence. |
| Figshare | Compare `id`, `doi`, `defined_type_name`, requested record and requested version. A `.vN` DOI must agree with `version`; an unversioned redirect cannot verify a requested version. |
| PDB | Normalize `rcsb_id`; compare `entry.id`, container `entry_id`, input accession and only the `database_2` row with `database_id=PDB`. Article/BMRB DOIs do not identify the structure. Revisions are not immutable version PIDs. |

## G02 — Identifying name

PASS for presence requires nonempty native object-level text; informative meaning
requires a distinguishing object label or established name. Empty titles and
recognized placeholders FAIL when retrieval is complete. Unexplained codes and
meaning not verified by content stay UNSURE. Benefit: name lookup and result recognition.

| Repository | Fields |
| --- | --- |
| Zenodo | `metadata.title` |
| Dryad | `title`, assessed as a dataset name even when it refers to an article |
| Figshare | `title`, at the evaluated article/item level |
| PDB | `struct.title`; never substitute `rcsb_primary_citation.title` |

## G03 — Informative content summary

Separate presence, data focus and distinguishing information. PASS for meaning
requires actual content/context at the evaluated level; empty mapped summaries,
title-only copies, boilerplate and proven unrelated descriptions FAIL. HTML length
and mere textual difference do not prove informative meaning. Benefit: topical
matching and relevance assessment.

| Repository | Fields and criterion |
| --- | --- |
| Zenodo | Parse `metadata.description`; compare its normalized text with `metadata.title`; data focus needs semantic evidence. |
| Dryad | Parse `abstract`; determine whether it characterizes the dataset rather than only article results. |
| Figshare | Parse `description`; distinguish data content from associated publication text. |
| PDB | Combine `rcsb_entry_info.polymer_composition`, `exptl[].method` and every bound polymer's `rcsb_polymer_entity.pdbx_description`. An isolated molecular label does not satisfy entry-level G03. Missing related-source retrieval stays UNSURE. |

## G04 — Terms and concepts

PASS for an access key requires a labeled topic; PASS for relevance requires content
agreement. Validate every declared label and controlled concept, with label/identifier
alignment separately. Empty or malformed declared labels FAIL. Unknown vocabulary
membership or unverified relevance stays UNSURE. Duplicate terms produce a diagnostic
WARNING. Benefit: alternative query terminology and thematic browsing.

| Repository | Fields |
| --- | --- |
| Zenodo | `metadata.keywords[]`; `metadata.subjects[].term`, `identifier`, `scheme` |
| Dryad | `keywords[]`; `fieldOfScience` against the documented OECD FOS vocabulary |
| Figshare | `keywords[]` or `tags[]` alias; `categories[].id`, `title` and native taxonomy context |
| PDB | Comma-separated `struct_keywords.text`; every component of `struct_keywords.pdbx_keywords` against the reviewed dictionary snapshot |

## G05 — Scientific data kind

PASS requires an interpretable content-kind crosswalk; a contradicted active content
criterion FAILS. Generic object roles and formats alone leave meaning UNSURE.
Benefit: selection by the scientific content sought.

| Repository | Fields and limits |
| --- | --- |
| Zenodo | `metadata.resource_type.type` plus description evidence; `dataset` alone does not identify observations, images, sequences or another content kind. |
| Dryad | `abstract` and `usageNotes` can support semantic assessment. No undocumented native content-kind field is invented. |
| Figshare | `defined_type_name` supports documented kinds such as Figure; `Dataset` alone needs description/content evidence. |
| PDB | Positive `rcsb_entry_info.deposited_atom_count` and `deposited_model_count`, interpreted in the documented structural object model, establish atomic structural-model content. |

## G06 — Actors and roles

PASS requires every relevant declared creator to have a person/team/organization
name and a preserved role. Missing required creators and unnamed declared actors
FAIL. ORCID/ROR consistency checks apply to supplied identifiers; their absence
does not fail creator search. Benefit: creator/provider lookup and origin recognition.

| Repository | Fields |
| --- | --- |
| Zenodo | Every `metadata.creators[]`; contributors separately through `metadata.contributors[].name/type`; optional actor IDs and explicit publisher/host roles |
| Dryad | Every `authors[].firstName/lastName`; optional `orcid`, affiliation and `affiliationROR` diagnostics |
| Figshare | Every `authors[].full_name`; optional `orcid_id`; do not invent unavailable affiliations |
| PDB | Every `audit_author[].name`; optional `pdbx_ORCID`; explicit `pdbx_database_status.process_site` is a processor role, not a creator |

## G07 — Independent scope dimensions

Assess entities, properties, geography, content time and granularity independently.
PASS requires the dimension's correct role and a usable representation; malformed
declared coordinates, inverted content intervals and invalid applicable resolutions
FAIL. Unselected/unmapped semantic dimensions stay UNSURE. Lifecycle dates and
institution addresses cannot replace data coverage. Benefit: content constraints.

| Repository | Applicable field-level checks |
| --- | --- |
| Zenodo | Entity/property/granularity evidence in `metadata.description` needs review. Validate every `metadata.locations[]` and `metadata.dates[]` with `type=Collected`; keep presence, coordinate validity and indexer-filter mapping separate. |
| Dryad | Entity/property/granularity evidence in `abstract` needs review. Validate all `locations[]` places, points and boxes. Publication date is not temporal coverage. |
| Figshare | Scope statements in `description` need semantic review; arbitrary `custom_fields` names are not silently assigned meanings. No verified standard geographic/temporal mapping is assumed. |
| PDB | For every bound polymer: molecule label, all `rcsb_entity_source_organism[]` names/supplied taxon IDs, canonical `entity_poly.pdbx_seq_one_letter_code_can`, supplied sequence-length agreement, and container `entity_id/asym_ids[]`. Combine chains with entry model count. Validate every `resolution_combined[]` as positive finite angstroms when method-applicable; NMR-only resolution is NOT_APPLICABLE. Geographic/calendar-time filters are explicitly outside this task. |

## G08 — Generation method

Separate native statement presence from production meaning. PASS for meaning
requires an interpretable process linked to these data. Empty active method
information and boilerplate FAIL; mere methodology words or undocumented custom
fields stay UNSURE. Benefit: method-based data lookup.

| Repository | Fields |
| --- | --- |
| Zenodo | `metadata.method`, HTML parsed; process meaning needs review |
| Dryad | `methods`, HTML parsed; collecting/processing meaning needs review |
| Figshare | No verified standard method mapping; `description` or locally defined custom fields need explicit semantic/schema review |
| PDB | Every `exptl[].method` against the PDBx/mmCIF method enumeration; unknown historical methods remain UNSURE |

## G09 — Qualified relationships

Validate target syntax, meaningful type/direction and content consistency separately.
PASS for the first two requires every declared target and native relation to be
interpretable. Missing/malformed declared targets or contradicted relationships
FAIL; absence of an expected relation not established by the task stays UNSURE.
A related publication is not universally required. Benefit: related-resource navigation.

| Repository | Fields and role handling |
| --- | --- |
| Zenodo | Every `metadata.related_identifiers[].identifier/relation/scheme`; preserve DataCite direction |
| Dryad | Every `relatedWorks[].identifier/identifierType/relationship`; native article/dataset/software/preprint/supplement roles describe association, not inferred derivation/equivalence |
| Figshare | Every `related_materials[].identifier/identifier_type/relation`; retain explicit directional relationship |
| PDB | Supplied `rcsb_primary_citation.pdbx_database_id_DOI` and PubMed IDs are primary-publication targets. Keep structure and publication identity distinct; publication-content confirmation remains semantic. |

## G10 — Public metadata channel

PASS requires successful retrieval, useful supported parsing and binding for the
same representation or documented bound chain. A supplied URL and valid empty JSON
alone cannot PASS the complete profile. Proven route/representation/binding failures
FAIL; incomplete discovery or retrieval evidence stays UNSURE. Benefit: API harvesting.

| Repository | Route and native evidence |
| --- | --- |
| Zenodo | `/api/records/{id}`, useful native metadata, object binding and explicit `status=published`; use `links.self_html` for the inspected response |
| Dryad | `/api/v2/datasets/{encoded DOI}`, useful native fields, DOI binding and `visibility=public` |
| Figshare | `/v2/articles/{id}[/versions/{version}]`, useful native fields, selected-object/version binding and `is_public`; file embargo is a different property |
| PDB | `/rest/v1/core/entry/{id}` plus explicitly linked `/polymer_entity/{id}/{entity}` responses, each separately bound; documented RCSB catalog/Search API route is a diagnostic, not observed index inclusion |

## Sources and unresolved mappings

- [Zenodo native metadata definitions](https://developers.zenodo.org/#deposit-metadata)
  and [Records API](https://developers.zenodo.org/#records).
- [Dryad dataset field definitions](https://github.com/datadryad/dryad-app/blob/main/documentation/apis/dataset_metadata.md)
  and [link relation definitions](https://github.com/datadryad/dryad-app/blob/main/documentation/apis/link_relations.md).
- [Figshare OpenAPI schemas](https://docs.figshare.com/swagger.json),
  [API v2](https://docs.figshare.com/v2/).
- [RCSB data organization and APIs](https://data.rcsb.org/),
  [Search API attributes](https://search.rcsb.org/),
  [PDBx/mmCIF dictionary](https://mmcif.wwpdb.org/dictionaries/mmcif_pdbx_v50.dic/Index/).

Representative native responses inspected: Zenodo `3357455` (software, useful as
an object-role counterexample), Dryad `10.5061/dryad.j1fd7`, Figshare `1407024`
and PDB `4HHB` with polymer entity `1`. These examples do not validate semantic
quality or represent every repository record.

Generic semantic scope/content-kind mappings, Figshare institutional custom fields,
independent observed discovery/index membership, PDB non-polymer coverage and
immutable historical PDB versions require separate supported profiles. They are
not replaced by invented field mappings or automatic semantic PASS results.
