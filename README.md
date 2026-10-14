# Metadata Checker

## Running the app

Requires Python 3.10 or newer. No external packages are needed.
Internet access is required for repository and aggregator requests.

Run from the `diplomka` directory:

```sh
python3 -m src.server
```

Alternatively, run `python3 src/server.py` from the same directory.

Open [localhost:8080](http://localhost:8080). Stop the server with `Ctrl+C`.

## Evaluation

The app is intended for scientific datasets. Enter a DOI, record URL or PDB accession and click **Check**.
The app recognizes Zenodo, Dryad, Figshare or RCSB PDB and retrieves the record's metadata.
It evaluates all four repositories in G01–G10 search-readiness groups and looks
up the data-object DOI in OpenAIRE and OpenAlex.

Results contain three groups:

- **Record-level:** G01–G10 criteria and capability summaries for all four repositories. Each group expands on click to show its concrete checks, native fields, decision rules and schema sources.
- **Repository-level:** documented submission requirements and automatic filling for each field in the selected adapter's catalog.
- **Aggregators:** DOI lookups in OpenAIRE and OpenAlex.

**Input recognition and DOI resolution**

1. Leading and trailing whitespace is removed. The input must contain one complete reference.
2. DOI inputs may be bare, prefixed with `doi:`, or given as a URL on `doi.org` or `dx.doi.org`.
3. Known DOI patterns and supported repository URL paths select an adapter directly.
4. An unrecognized DOI is sent to `https://doi.org/{doi}`. The app reads the redirect's `Location` header.
   It follows redirects only within the DOI resolver domains, with at most five requests.
   The first external URL is checked against the supported adapters. Its landing page is not fetched.
5. The selected adapter extracts the record identifier and requests the repository API endpoint listed below.
   Unsupported inputs and unsupported redirect targets are rejected.

Supported domains also accept URLs without `https://`.
HTTP and HTTPS are accepted with their default ports. URLs containing credentials are rejected.
URL paths are decoded before matching. Query strings and fragments do not select a different record or version.
The wwPDB `/pdb` landing page is an exception: exactly one `id` query parameter selects its entry.
DOIs embedded in prose are not extracted.
Bare positive integer IDs without leading zeros select Zenodo.

**Generic metadata checks: G01–G10**

All four repositories use the `public_repository_api` profile based on the
`design-search-readiness-checks` skill and the supplied search-readiness proposal.
Repository-specific rules and sources were reviewed on 14 October 2026; see
[the concrete check specification](docs/search-readiness-checks.md).
Generic adapters evaluate one original public API representation. PDB also
retrieves the polymer entities explicitly linked by the entry. Paths refer to
their stated native representation;
`[]` in repository catalogs projects a field from every list item.

| Group | Task and implemented criteria |
| --- | --- |
| G01 Identity | Repository-qualified or recognized dataset ID; binding to the requested object; selected-version consistency; optional resolver diagnostic. Series and version references are distinguished. |
| G02 Name | Nonempty text and recognized literal placeholders; identifying meaning remains a separate semantic result. |
| G03 Summary | Text after HTML parsing; data focus and distinguishing information separately. An exact title copy fails the additional-information test. |
| G04 Terms | Keywords and subjects together; thematic access keys, relevance, duplicate diagnostics, concept membership and label alignment separately. Free keywords do not require a controlled vocabulary. |
| G05 Data kind | Extensible content crosswalk for native resource types. `Dataset`, CSV, PDF and ZIP alone do not establish scientific data kind. |
| G06 Origin | Every declared creator is named, preserving its role. Contributors, publishers and hosts remain distinct. Supplied ORCID/ROR identifiers have optional diagnostics; no universal affiliation or identifier bonus. |
| G07 Scope | Independent entity, property, spatial, content-time and granularity results. Mapped locations and collection intervals are validated without substituting publication dates. Textual interpretation and filter readiness are separate. |
| G08 Generation | Method text with its source; naming a process and binding it to these data requires semantic evidence. “Methods available” alone fails. |
| G09 Relations | Every declared target and relation type/direction separately; actual relationship meaning remains unverified. A missing related article is not an automatic failure. |
| G10 Publication | Successful retrieval of the same API representation, useful native parser mappings and object binding. Independent discovery, web crawling and observed indexing are not inferred from an API request. |

Each subtest reports `group`, a descriptive `testId`, `ruleVersion`, `profile`,
`targetObject`, `sourceRepresentation`, evidence, `decisionMethod`, `applicable`
and `applicabilityReason`. The application displays the individual results and a
conservative summary for every group: all active required criteria must pass;
a demonstrated failure takes precedence; otherwise the group is `UNSURE`.
Diagnostics do not earn additional points or overwrite a semantic result.

- `PASS`: evidence satisfies the named criterion.
- `FAIL`: the sufficiently retrieved representation demonstrates a failure.
- `UNSURE`: evidence, semantic interpretation or applicability is unknown.
- `NOT_APPLICABLE`: an explicit task selection excludes the criterion, with a reason.

The reference profile activates identity, name, summary, data kind, creator and
API-publication tasks. It examines declared terms, scope, methods and relations;
when these are absent and their applicability is unknown, it reports `UNSURE`.
The internal `EvaluationContext.scope_dimensions` can explicitly select scope
tasks (`E`, `P`, `S`, `T`, `G`). Missing values for active mapped dimensions fail
only with a complete representation. Unmapped dimensions and incomplete harvests
remain uncertain. Missing fields alone never justify `NOT_APPLICABLE`.

No NLP/LLM or uncalibrated semantic heuristic produces a semantic `PASS`.
Name informativeness, description data focus, term relevance, method meaning and
relation meaning therefore usually remain `UNSURE`, with the available text or
assignment retained for review. There are no word-count, keyword-count, recency,
reputation or dataset-size thresholds. Unmapped scope information in descriptions
also remains uncertain; arbitrary custom fields are not given an invented crosswalk.

Generic results have zero `points/maxPoints` for compatibility with result helpers;
their summary contains `profile` and `groups` instead of a universal score or bonus.
Status counts include diagnostics and aggregator results and are not a probability
of dataset discovery. Language, grants, lifecycle dates, download success and
licensing are not universal search-readiness criteria. The original field catalogs
remain available in the separate repository-policy table.

Resolver and registry verification uses bounded public HTTP(S) requests, at most
five redirects, eight workers and eight-second timeouts. Distinct URLs are fetched
once. Resolver evidence retains the redirect chain, final target and check time.
HTTP success at a generic homepage does not establish dataset/version binding;
resolver outages leave local identifier interpretation intact. Controlled-concept
existence, label alignment and relevance have separate results. Supplied creator
ORCIDs retain the previous per-author surname consistency diagnostic; a surname
match does not authenticate ownership.

**PDB evaluation**

PDB uses G01–G10 with namespaced accession and structure-DOI binding, linked
molecular summaries, topical classification, atomic-model content, structure
authors, polymer names, biological source organisms, canonical sequences,
entity/chain/model granularity, method-dependent resolution and primary-citation
relations. Every declared polymer is checked; unavailable entity metadata stay
UNSURE. Publication authors, expression hosts and lifecycle dates do not replace
structure authors, source organisms or data coverage. The current-entry profile
excludes geographic and calendar-time queries with explicit NOT_APPLICABLE reasons.
No legacy points or bonuses are assigned to this profile.

**Submission requirements**

The **Required from submitter?** column describes publication requirements for the standard repository forms.
The requirements were checked against the linked documentation on 1 October 2026
for generic repositories and 2 October 2026 for PDB.

- **Yes:** the value or selection is required; a supplied default may satisfy it.
- **No:** optional, even when recommended by the repository.
- **Conditional:** required in the situation stated in the row.
- **Automatic:** supplied by the repository or a selected registry entry; no separate manual value is required.
- **Depends on form:** the requirement differs between documented form versions.

These labels describe repository policy and do not change record evaluation or scoring.
The tables cover the checked metadata only, not the complete submission checklist.
Required properties in an API response schema do not necessarily require input from the scientist.

**Repository-level checks**

Each evaluation includes a policy table for the recognized repository: 30 Zenodo,
23 Dryad, 22 Figshare or 16 PDB fields, matching the adapter's catalog. The table
shows the submission requirement, automatic filling, explanation, source links,
scope and review date. Policies are stored locally and do not require extra
network requests. They stay the same regardless of the values in a particular record.

Requirements and automatic filling are separate. For example, Zenodo requires a
publication date and prefills it. Dryad requires author affiliations, but only a
ROR selection supplies an affiliation identifier. Importing publication metadata
or selecting an author, subject or grant still needs user action.

- **PASS:** the standard workflow requires the field or supplies it automatically.
  This describes completeness safeguards, not the accuracy of the resulting value.
- **WARNING:** a field is optional, required only in some situations, or filled only
  after an optional selection. The repository does not ensure it for every submission.
- **UNSURE:** the form's requirements vary or the field policy has not been verified.
  Figshare categories retain both conflicting official guides as evidence.

Defaults in optional sections (such as Figshare related materials) do not ensure
that the section is present. Dryad's ORCID login requirement does not require
every coauthor to have an ORCID. A missing policy for a newly added catalog field
produces an explicit unverified result instead of omitting the field.

Repository policy results have no points. The main summary's scores and status
counts include record checks and aggregator lookups only, so optional repository
fields cannot inflate a record's failures or warnings. Repository checks cover
the catalog fields, not the complete submission checklist or all derived evaluation paths.

### Zenodo

- [Records API](https://developers.zenodo.org/#records) — published record retrieval.
- [InvenioRDM metadata schema](https://github.com/inveniosoftware/invenio-rdm-records/blob/master/invenio_rdm_records/services/schemas/metadata.py) — submission validation rules.
- [Record description guide](https://help.zenodo.org/docs/deposit/describe-records/) — guidance for authors.

**Accepted inputs**

Record URLs use `zenodo.org` or `www.zenodo.org`.
`{id}` is a positive integer without leading zeros.

| Input | Accepted form |
| --- | --- |
| DOI | `10.5281/zenodo.{id}` |
| Record ID | `{id}` |
| Record URL path | `/records/{id}` or `/record/{id}` |
| API URL path | `/api/records/{id}` |
| DOI URL path on Zenodo | `/doi/10.5281/zenodo.{id}` |

Example: `10.5281/zenodo.3357455` or [this Zenodo record](https://zenodo.org/records/3357455).

**Metadata source**

```http
GET https://zenodo.org/api/records/{id}
```

The adapter requests JSON and evaluates the returned record directly.

**Metadata field catalog**

G01 uses the native resource type as object-role evidence; G05 separately checks
the scientific data kind. A declared `Dataset` type is insufficient for G05.

| Metadata | JSON field | Required from submitter? |
| --- | --- | --- |
| DOI | `doi` | Automatic for new records; an existing DOI must be supplied if applicable. |
| Title | `metadata.title` | Yes. |
| Description (HTML) | `metadata.description` | No — recommended. |
| Resource type | `metadata.resource_type.type` | Yes — select the appropriate type. |
| Publication date | `metadata.publication_date` | Yes — prefilled with the draft creation date. |
| Author names | `metadata.creators[].name` | Yes — at least one creator, with a name for each. |
| Author ORCIDs | `metadata.creators[].orcid` | No. |
| Author affiliations | `metadata.creators[].affiliation` | No. |
| Keywords | `metadata.keywords[]` | No. |
| Subject terms | `metadata.subjects[].term` | Conditional — when adding a controlled subject; selection supplies the term. |
| Subject identifiers | `metadata.subjects[].identifier` | Automatic from the selected vocabulary term. |
| Subject schemes | `metadata.subjects[].scheme` | Automatic from the selected vocabulary term. |
| Language | `metadata.language` | No. |
| Version | `metadata.version` | No — an optional author-defined version label. |
| Contributor names | `metadata.contributors[].name` | Conditional — when adding a contributor. |
| Contributor roles | `metadata.contributors[].type` | Conditional — when adding a contributor. |
| Contributor ORCIDs | `metadata.contributors[].orcid` | No. |
| Contributor affiliations | `metadata.contributors[].affiliation` | No. |
| Related identifiers | `metadata.related_identifiers[].identifier` | Conditional — when adding a related resource. |
| Related identifier relations | `metadata.related_identifiers[].relation` | Conditional — when adding a related resource. |
| Related identifier schemes | `metadata.related_identifiers[].scheme` | Automatic when recognized; otherwise a scheme must be supplied. |
| References | `metadata.references[]` | No. |
| Grant codes | `metadata.grants[].code` | No — optional for custom funding; selected grants may supply it. |
| Grant titles | `metadata.grants[].title` | No — optional for custom funding; selected grants may supply it. |
| Grant funder names | `metadata.grants[].funder.name` | Conditional — choose a funder when adding funding. |
| Community identifiers | `metadata.communities[].identifier` | No — community selection is optional; its identifier is filled automatically. |
| Additional notes (HTML) | `metadata.notes` | No. |
| Methods (HTML) | `metadata.method` | No. |
| Spatial coverage | `metadata.locations[]` | No. |
| Temporal coverage | `metadata.dates[]` | No. |

[Descriptions](https://help.zenodo.org/docs/deposit/describe-records/descriptions/) are recommended.
[Publication dates](https://help.zenodo.org/docs/deposit/describe-records/publication-date/) are prefilled.
[DOIs](https://help.zenodo.org/docs/deposit/describe-records/reserve-doi/) are generated unless the record already has one.

[Contributors](https://help.zenodo.org/docs/deposit/describe-records/contributors/) and [funding](https://help.zenodo.org/docs/deposit/describe-records/funding/) are optional sections with required fields once an entry is added.
[Controlled subject selection](https://help.zenodo.org/docs/deposit/describe-records/keywords-and-subjects/) supplies vocabulary metadata.
[Identifier schemes](https://github.com/inveniosoftware/marshmallow-utils/blob/master/marshmallow_utils/schemas/identifier.py) are detected automatically when possible.

Coverage checks inspect the objects for content. They do not validate coordinates or date ranges.

### Dryad

- [OpenAPI schema](https://datadryad.org/openapi.yml) — `dataset`, `dc_metadata`, `author` and `funder` definitions.
- [API documentation](https://datadryad.org/api) — dataset retrieval and other API operations.
- [Data description guide](https://datadryad.org/help/submission_steps/description) — descriptions, subjects and funding metadata.
- [Submission metadata requirements](https://datadryad.org/help/requirements/metadata) — required and recommended author inputs.
- [Author requirements](https://datadryad.org/help/submission_steps/authors) — names, affiliations and ROR selection.

**Accepted inputs**

Record URLs use `datadryad.org` or `www.datadryad.org`.
`{doi}` below means `10.5061/dryad.{suffix}`, optionally prefixed with `doi:`.

| Input | Accepted form |
| --- | --- |
| DOI | `10.5061/dryad.{suffix}` |
| Dataset URL path | `/dataset/{doi}` |
| Legacy dataset URL path | `/stash/dataset/{doi}` |
| Resource URL path | `/resource/{doi}` |
| API URL path | `/api/v2/datasets/{doi}` |

URL-encoded DOIs are accepted in these paths.
Numeric Dryad IDs and version or file endpoints are not supported as inputs.

Example: `10.5061/dryad.7d7wm37sz` or [this Dryad dataset](https://datadryad.org/dataset/doi:10.5061/dryad.7d7wm37sz).

**Metadata source**

```http
GET https://datadryad.org/api/v2/datasets/{encoded_doi}
```

The DOI is lowercased, prefixed with `doi:` and URL-encoded as one path segment.
For the example above, `{encoded_doi}` is `doi%3A10.5061%2Fdryad.7d7wm37sz`.
The adapter evaluates the dataset JSON returned by this endpoint.

**Metadata field catalog**

| Metadata | JSON field | Required from submitter? |
| --- | --- | --- |
| DOI | `identifier` | Automatic — reserved by Dryad. |
| Title | `title` | Yes. |
| Description (HTML) | `abstract` | Yes. |
| Publication date | `publicationDate` | Automatic — set through Dryad's publication workflow. |
| Author first names | `authors[].firstName` | Yes — author names are required. |
| Author last names | `authors[].lastName` | Yes — author names are required. |
| Author ORCIDs | `authors[].orcid` | Conditional — required for the submitter's account; optional for other authors. |
| Author affiliations | `authors[].affiliation` | Yes — at least one affiliation per author. |
| Affiliation ROR identifiers | `authors[].affiliationROR` | Automatic when an affiliation is selected from ROR; free-text affiliations are allowed. |
| Keywords | `keywords[]` | Yes — at least three keywords. |
| Field of science | `fieldOfScience` | Yes — select at least one research domain. |
| Version | `versionNumber` | Automatic — managed by Dryad. |
| Related work identifiers | `relatedWorks[].identifier` | Conditional — when linking a related work or an associated published article. |
| Related work relationships | `relatedWorks[].relationship` | Conditional — choosing the work type supplies the relationship automatically. |
| Related work identifier schemes | `relatedWorks[].identifierType` | Automatic from the DOI or URL entered in the form. |
| Funder organizations | `funders[].organization` | Conditional — when adding funding. |
| Funder identifiers | `funders[].identifier` | Automatic when a registered funder is selected. |
| Funder identifier schemes | `funders[].identifierType` | Automatic from the selected funder identifier. |
| Grant numbers | `funders[].awardNumber` | No — recommended; award lookup can supply the number for supported funders. |
| Grant descriptions | `funders[].awardDescription` | No. |
| Methods (HTML) | `methods` | No — recommended. |
| Usage notes (HTML) | `usageNotes` | No — legacy field; guidance belongs in the dataset README. |
| Spatial coverage | `locations[]` | No. |

[ORCID login](https://datadryad.org/help/account/login) is required for the submitter.
It does not require an ORCID for every coauthor, although the app checks every author.
[Related works](https://datadryad.org/help/submission_steps/connect) need a DOI or URL when added.
Funding is optional; the [funding form](https://datadryad.org/help/submission_steps/description#support) requires an organization name for each entry.
Dryad manages [DOI assignment, publication and versions](https://datadryad.org/help/guides/publication).

G06 retains `affiliation`, `affiliationROR`, `affiliationISNI` and structured
`affiliations[]` as origin evidence and verifies supplied ROR identifiers separately.
These optional affiliation identifiers do not replace the creator role.

### Figshare

- [OpenAPI schema](https://docs.figshare.com/swagger.json) — `ArticleComplete` and its referenced schemas.
- [API v2 documentation](https://docs.figshare.com/v2/) — public article and version endpoints.
- [Metadata schema overview](https://info.figshare.com/user-guide/figshare-metadata-schema-overview/) — required, optional and system-managed fields.
- [Current metadata form](https://info.figshare.com/user-guide/how-to-fill-in-the-metadata-fields-first-step/) — author inputs and changes to category requirements.

**Accepted inputs**

Record URLs use `figshare.com` or `www.figshare.com`. API URLs use `api.figshare.com`.
`{id}` and `{version}` are positive integers without leading zeros.

| Input | Accepted form |
| --- | --- |
| DOI | `10.6084/m9.figshare.{id}` |
| DOI for a specific version | `10.6084/m9.figshare.{id}.v{version}` |
| Short record URL path | `/articles/{id}` or `/articles/{id}/{version}` |
| Full record URL path | `/articles/{type}/{slug}/{id}` or `/articles/{type}/{slug}/{id}/{version}` |
| API URL path | `/v2/articles/{id}` or `/v2/articles/{id}/versions/{version}` |

The adapter supports public articles, including datasets.
Collections, projects and institutional Figshare domains are not supported.
Bare numeric input is interpreted as a Zenodo ID.

Example: `10.6084/m9.figshare.33471208.v1` or [this Figshare record](https://figshare.com/articles/33471208/1).

**Metadata source**

Without a version, the adapter requests the current public record:

```http
GET https://api.figshare.com/v2/articles/{id}
```

A version in the DOI or URL selects that exact version:

```http
GET https://api.figshare.com/v2/articles/{id}/versions/{version}
```

**Metadata field catalog**

| Metadata | JSON field | Required from submitter? |
| --- | --- | --- |
| DOI | `doi` | Automatic — assigned by Figshare. |
| Title | `title` | Yes. |
| Description (HTML) | `description` | Yes. |
| Resource type | `defined_type_name` | Yes — select the item type. |
| Publication date | `published_date` | Automatic — set when the version is published. |
| Author names | `authors[].full_name` | Yes — at least one author. |
| Author ORCIDs | `authors[].orcid_id` | No for the public figshare.com workflow. |
| Keywords | `keywords[]` | Yes — at least one keyword. |
| Subject category titles | `categories[].title` | Depends on form — category selection supplies the titles. See the note below. |
| Subject category identifiers | `categories[].id` | Depends on form — category selection supplies the IDs. See the note below. |
| Version | `version` | Automatic — managed by Figshare. |
| Related identifiers | `related_materials[].identifier` | Conditional — when adding a related material. |
| Related identifier relations | `related_materials[].relation` | Conditional — when adding a related material; default is `References`. |
| Related identifier schemes | `related_materials[].identifier_type` | Conditional — when adding a related material; default is `URL`. |
| Related resource titles | `related_materials[].title` | No. |
| References | `references[]` | No — a legacy field superseded by related materials. |
| Funding description (HTML) | `funding` | No. |
| Grant codes | `funding_list[].grant_code` | Automatic from a selected grant, when available. |
| Grant titles | `funding_list[].title` | Conditional — enter a title for custom funding; selected grants supply it. |
| Grant funder names | `funding_list[].funder_name` | Automatic from a selected grant, when available. |
| Related publication DOI | `resource_doi` | No — a legacy field superseded by related materials. |
| Related publication title | `resource_title` | No — a legacy field superseded by related materials. |

The [schema overview](https://info.figshare.com/user-guide/figshare-metadata-schema-overview/) lists categories as required.
The [current form guide](https://info.figshare.com/user-guide/how-to-fill-in-the-metadata-fields-first-step/) says they became optional with the Item Type Based Metadata release, unless an institution requires them.
Category requirements therefore depend on the form in use.

Funding and related materials are optional sections.
The [API schema](https://docs.figshare.com/swagger.json) defines their entry fields in `FundingCreate` and `RelatedMaterial`.
Selecting a grant supplies its details; custom funding can contain only a title.
The response schema's required grant properties do not make grant codes or funder names mandatory author inputs.

Keyword checks use `keywords`. The `tags` alias is not checked separately.

### RCSB PDB

PDB is a specialized archive of macromolecular structures, including proteins,
nucleic acids and their complexes. This adapter evaluates the current public
**entry**, using the native RCSB REST response. It does not retrieve polymer
entities, chains, assemblies, coordinates or full validation reports.

- [Data API and hierarchy](https://data.rcsb.org/) — entry and entity endpoints.
- [PDB accession and DOI formats](https://www.wwpdb.org/documentation/new-format-for-pdb-ids).
- [OneDep submission requirements](https://www.wwpdb.org/deposition/faq).
- [Versioned archive](https://www.wwpdb.org/ftp/pdb-versioned-ftp-site).
- [Framework assessment and live examples](docs/pdb-framework-assessment.md).

**Accepted inputs**

| Input | Example |
| --- | --- |
| PDB accession, case insensitive | `4HHB` or `pdb:4HHB` |
| Extended legacy alias | `pdb_00004hhb` (requests `4HHB`) |
| New extended accession syntax | `pdb_1000axyz` |
| Structure DOI | `10.2210/pdb4hhb/pdb` |
| Extended DOI syntax | `10.2210/pdb_1000axyz/pdb` |
| RCSB structure URL | `https://www.rcsb.org/structure/4HHB` |
| Entry API URL | `https://data.rcsb.org/rest/v1/core/entry/4HHB` |
| wwPDB DOI landing page | `https://www.wwpdb.org/pdb?id=pdb_00004hhb` |

Extended identifiers are parsed without assuming that an example exists in the
live archive. Legacy aliases normalize to the API's four-character identifier;
new extended identifiers retain all 12 characters. Bare numeric input continues
to select Zenodo; use `pdb:1234` for an all-numeric PDB accession. Computed model
IDs such as `AF_...`, deposition sessions `D_...`, entity/chain URLs and archive
version-file URLs are not supported entry references.

**Metadata source**

```http
GET https://data.rcsb.org/rest/v1/core/entry/{pdb_id}
GET https://data.rcsb.org/rest/v1/core/polymer_entity/{pdb_id}/{entity_id}
```

The structure DOI, related article DOI and other database DOIs are kept distinct.
Only the structure DOI selected from the PDB row is sent to aggregators. If it is
missing, the input DOI or article DOI does not fill it. A response identifying a
different entry, or a valid DOI in the PDB row identifying another resource,
fails the G01 binding check. Related polymer responses are separately bound by
entry and entity identifiers. Related-source retrieval failures remain UNSURE.

**Metadata field catalog**

| Metadata | JSON field | Required from submitter? |
| --- | --- | --- |
| PDB accession | `rcsb_id` | Automatic. |
| Structure DOI | `database_2[].pdbx_DOI` (PDB row) | Automatic. |
| Structure title | `struct.title` | Yes. |
| Keywords | `struct_keywords.text` | Yes. |
| Controlled classification | `struct_keywords.pdbx_keywords` | Yes — deposition vocabulary. |
| Structure authors | `audit_author[].name` | Yes. |
| Author ORCIDs | `audit_author[].pdbx_ORCID` | Conditional — contact authors; not ensured for every entry author. |
| Processing organization | `pdbx_database_status.process_site` | Automatic. |
| Deposition date | `rcsb_accession_info.deposit_date` | Automatic. |
| Initial release date | `rcsb_accession_info.initial_release_date` | Automatic. |
| Latest revision date | `rcsb_accession_info.revision_date` | Automatic. |
| Major revision | `rcsb_accession_info.major_revision` | Automatic. |
| Minor revision | `rcsb_accession_info.minor_revision` | Automatic. |
| Experimental methods | `exptl[].method` | Yes. |
| Polymer entity links | `rcsb_entry_container_identifiers.polymer_entity_ids[]` | Automatic. |
| Related article DOI | `rcsb_primary_citation.pdbx_database_id_DOI` | Conditional — when there is an associated publication. |

G06 uses structure authors, not publication authors, and keeps the explicitly
declared processing organization separate. G03 combines bound molecular labels
with entry-level composition and method facts rather than requiring a separate
abstract. G05 identifies atomic structural content independently of mmCIF format.
G07 evaluates every declared polymer's name, source organisms, sequence and
chain identifiers. Missing linked representations remain UNSURE; one fetched
polymer cannot establish coverage of the others. Resolution is method-dependent:
NMR-only records have an explicit NOT_APPLICABLE result for that criterion.
Historical archive versions require a separate retrieval workflow.

## Aggregators

Each retrieved record receives two additional checks:
**Discoverable in OpenAIRE** and **Discoverable in OpenAlex**.
They check whether the DOI can be found through these APIs.
Completed lookups show the exact request URL as a clickable link after `using`, for both `PASS` and `FAIL`.
They do not measure search ranking or compare aggregator metadata with repository metadata.

**DOI used for lookup**

- For a directly recognized DOI input, the app uses the submitted DOI.
- For a record URL or numeric ID, it reads `doi` from Zenodo or Figshare, or `identifier` from Dryad.
- If an unknown DOI was first resolved to a repository URL, the app also uses the DOI from the repository response.

The DOI is lowercased. The `doi:` prefix or resolver URL is removed.
Version suffixes are preserved. No lookup of an alternative or parent DOI is attempted.
Without a usable DOI, both aggregator checks return `FAIL` and explain that no lookup was possible.
No request URL is shown when no lookup was made.

### OpenAIRE

- [Graph API](https://graph.openaire.eu/docs/apis/graph-api/research-products/) — research product search and response structure.
- [Filter reference](https://graph.openaire.eu/docs/apis/graph-api/research-products/filtering/) — persistent identifier filtering.

```http
GET https://api.openaire.eu/graph/v3/research-products?pid={encoded_doi}&pageSize=1
```

The `pid` filter receives the URL-encoded DOI. Only one result is requested.
A first result with a nonempty string `id` produces `PASS`.
An empty `results` list produces `FAIL`.
A missing or malformed list or record ID produces `ERROR`.

### OpenAlex

- [DOI lookup](https://help.openalex.org/api/get-single-entities/) — retrieving a work by its external identifier.
- [Corpus selection](https://help.openalex.org/data/works/corpus/) — including core and expansion records.

```http
GET https://api.openalex.org/works/https://doi.org/{doi}?corpus=all&select=id,doi
```

The DOI is URL-encoded, with its slash preserved.
`corpus=all` includes both the core and expansion corpus.
`select=id,doi` limits the requested response fields.
A response with a nonempty string `id` produces `PASS`.
HTTP `404` produces `FAIL`. A missing or invalid record ID produces `ERROR`.

### Availability

The two lookups run concurrently. Each API request has a 12-second timeout.
Network failures, invalid JSON and other HTTP errors produce `ERROR`.
An aggregator error preserves the metadata checks and the other aggregator's result.
Errors are counted separately from failed checks.

## Implementation details and architecture

Generic G01–G10 orchestration is in `generic_metadata_checks.py`, with native
additional mappings in `generic_metadata_config.py`. `generic_metadata_model.py`
provides the evidence context and result builder; identity/version binding and
independent scope validation are isolated in `generic_metadata_identity.py` and
`generic_metadata_scope.py`. `generic_metadata_summary.py` summarizes capabilities.
Shared title/creator/term paths remain in `metadata_config.py`. Registry, creator
and organization evidence is shared through `metadata_evidence.py`.

PDB retains the M1–M9 evaluator in `metadata_checks.py`. Both profiles share
identifier syntax in `metadata_identifiers.py`, date parsing in `metadata_dates.py`,
verification in `metadata_verification.py` and text/result helpers in `checks.py`.

Adapters evaluate the original repository JSON offline. `metadata_verification.py`
then completes queued resolver and registry lookups, and the shared repository
client computes the summary.
PDB supplies native identifier targets to the shared M1 evaluator and an
authoritative structure-DOI selector to the repository client. `pdb_identifiers.py`
centralizes accession syntax; `pdb_vocabulary.py` stores the dated classification
snapshot. No dependencies or second scoring implementation are introduced.

`repository_policies.py` stores the sourced, dated submission policies separately
from evaluation logic. `repository_checks.py` combines those policies with the
selected adapter's existing field labels and paths. The repository client adds
these results to `checks.repositoryLevel`; the UI renders a separate policy table.

Run the behavioral regression suite from the `diplomka` directory:

```sh
python3 -m unittest discover -s tests -v
```

Tests mock external services and do not require internet access.
PDB tests also use archived public X-ray and NMR entry responses in
`tests/fixtures/pdb`; their sources and capture date are documented there.
