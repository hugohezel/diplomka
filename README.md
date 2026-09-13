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

The app is intended for scientific datasets. Enter a DOI or record URL and click **Check**.
The app recognizes Zenodo, Dryad or Figshare and retrieves the record's metadata.
It checks selected fields for missing values and looks up the DOI in OpenAIRE and OpenAlex.

Results contain three groups:

- **Record-level:** metadata completeness checks.
- **Repository-level:** reserved for future checks; currently empty.
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
DOIs embedded in prose are not extracted.
Bare positive integer IDs without leading zeros select Zenodo.

**How metadata checks work**

Each row in a metadata table is one presence check. Paths refer to the original JSON response.
`[]` means every item in a list. Fields marked **HTML** are checked using their parsed text.

- A missing field, `null`, blank text, an empty list or an empty object produces `FAIL`.
- A list must contain items, and every checked item must have a value.
  One author without an ORCID therefore fails the entire author ORCID check.
- An object must contain at least one nonempty value.
- HTML without text, such as `<p>&nbsp;</p>`, produces `FAIL` in HTML fields.
- `0` and `false` count as present values.

Missing optional fields also produce `FAIL`.
These checks measure completeness only. They do not validate metadata schemas, identifier formats or research quality.
Repository request failures appear as loading errors; they do not produce metadata check results.

**Submission requirements**

The **Required from submitter?** column describes publication requirements for the standard repository forms.
The requirements were checked against the linked documentation on 9 September 2026.

- **Yes:** the value or selection is required; a supplied default may satisfy it.
- **No:** optional, even when recommended by the repository.
- **Conditional:** required in the situation stated in the row.
- **Automatic:** supplied by the repository or a selected registry entry; no separate manual value is required.
- **Depends on form:** the requirement differs between documented form versions.

These labels do not change the app's presence checks.
The tables cover the checked metadata only, not the complete submission checklist.
Required properties in an API response schema do not necessarily require input from the scientist.

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

**Metadata checks: 30 for every record**

All checks run regardless of the declared resource type.
The resource type check only requires a nonempty value.

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

**Metadata checks: 23**

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
| Related work relationships | `relatedWorks[].relationship` | Conditional — choose the work type when adding a related work. |
| Related work identifier schemes | `relatedWorks[].identifierType` | Automatic from the DOI or URL entered in the form. |
| Funder organizations | `funders[].organization` | Conditional — when adding funding. |
| Funder identifiers | `funders[].identifier` | Automatic when a registered funder is selected. |
| Funder identifier schemes | `funders[].identifierType` | Automatic from the selected funder identifier. |
| Grant numbers | `funders[].awardNumber` | No — recommended when applicable. |
| Grant descriptions | `funders[].awardDescription` | No. |
| Methods (HTML) | `methods` | No — recommended. |
| Usage notes (HTML) | `usageNotes` | No — legacy field; guidance belongs in the dataset README. |
| Spatial coverage | `locations[]` | No. |

[ORCID login](https://datadryad.org/help/account/login) is required for the submitter.
It does not require an ORCID for every coauthor, although the app checks every author.
[Related works](https://datadryad.org/help/submission_steps/connect) need a DOI or URL when added.
Funding is optional; the [funding form](https://datadryad.org/help/submission_steps/description#support) requires an organization name for each entry.
Dryad manages [DOI assignment, publication and versions](https://datadryad.org/help/guides/publication).

Affiliation checks use `affiliation` and `affiliationROR`.
The alternative `affiliations[]` representation is not checked separately.

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

**Metadata checks: 22**

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
