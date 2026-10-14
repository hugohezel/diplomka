"""Documented submission policies for the adapters' metadata field catalogs.

These describe the standard deposit forms, not API response requirements.
Keep requirements and automatic filling separate: a required field can have a
default, and registry completion can depend on an optional user selection.
"""

from dataclasses import dataclass
from typing import Literal


Requirement = Literal["required", "optional", "conditional", "system", "varies", "unknown"]
AutoFill = Literal["none", "generated", "default", "selection", "detected", "import", "unknown"]


@dataclass(frozen=True)
class FieldPolicy:
    requirement: Requirement
    auto_fill: AutoFill
    note: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class RepositoryPolicy:
    reviewed_at: str
    scope: str
    fields: dict[str, FieldPolicy]


ZENODO_HELP = "https://help.zenodo.org/docs/deposit/describe-records/"
ZENODO_SCHEMA = (
    "https://github.com/inveniosoftware/invenio-rdm-records/blob/master/"
    "invenio_rdm_records/services/schemas/metadata.py"
)
ZENODO_CREATORS = ZENODO_HELP + "creators/"
ZENODO_SUBJECTS = ZENODO_HELP + "keywords-and-subjects/"
ZENODO_CONTRIBUTORS = ZENODO_HELP + "contributors/"
ZENODO_FUNDING = ZENODO_HELP + "funding/"
ZENODO_IDENTIFIERS = (
    "https://github.com/inveniosoftware/marshmallow-utils/blob/master/"
    "marshmallow_utils/schemas/identifier.py"
)
DRYAD_HELP = "https://datadryad.org/help/"
DRYAD_METADATA = DRYAD_HELP + "requirements/metadata"
DRYAD_AUTHORS = DRYAD_HELP + "submission_steps/authors"
DRYAD_DESCRIPTION = DRYAD_HELP + "submission_steps/description"
DRYAD_CONNECT = DRYAD_HELP + "submission_steps/connect"
DRYAD_PUBLICATION = DRYAD_HELP + "guides/publication"
DRYAD_API_METADATA = (
    "https://github.com/datadryad/dryad-app/blob/main/"
    "documentation/apis/dataset_metadata.md"
)
DRYAD_RELATIONS = (
    "https://github.com/datadryad/dryad-app/blob/main/"
    "app/controllers/stash_datacite/related_identifiers_controller.rb"
)
DRYAD_FUNDING_FORM = (
    "https://github.com/datadryad/dryad-app/blob/main/"
    "app/javascript/react/components/MetadataEntry/Support/FunderForm.jsx"
)
DRYAD_FUNDING_SEARCH = (
    "https://github.com/datadryad/dryad-app/blob/main/"
    "app/javascript/react/components/MetadataEntry/Support/FundingSearch.jsx"
)
FIGSHARE_HELP = "https://info.figshare.com/user-guide/"
FIGSHARE_SCHEMA = FIGSHARE_HELP + "figshare-metadata-schema-overview/"
FIGSHARE_FORM = FIGSHARE_HELP + "how-to-fill-in-the-metadata-fields-first-step/"
FIGSHARE_API = "https://docs.figshare.com/swagger.json"
PDB_DATA_API = "https://data.rcsb.org/"
PDB_DICTIONARY = "https://mmcif.wwpdb.org/dictionaries/mmcif_pdbx_v50.dic/Items/"
PDB_IDENTIFIERS = "https://www.wwpdb.org/documentation/new-format-for-pdb-ids"
PDB_FAQ = "https://www.wwpdb.org/deposition/faq"
PDB_VERSIONS = "https://www.wwpdb.org/ftp/pdb-versioned-ftp-site"


ZENODO_FIELDS = {
    "doi": FieldPolicy(
        "conditional", "generated",
        "Zenodo registers a new DOI by default. Supply the existing DOI if the same resource already has one.",
        (ZENODO_HELP + "reserve-doi/",),
    ),
    "metadata.title": FieldPolicy(
        "required", "none", "A title is required.", (ZENODO_SCHEMA,),
    ),
    "metadata.description": FieldPolicy(
        "optional", "none", "A description is recommended, but is not required by the current form.",
        (ZENODO_HELP + "descriptions/", ZENODO_SCHEMA),
    ),
    "metadata.resource_type.type": FieldPolicy(
        "required", "none", "Select a resource type.", (ZENODO_SCHEMA,),
    ),
    "metadata.publication_date": FieldPolicy(
        "required", "default",
        "Prefilled with the draft creation date; correct it for previously published resources.",
        (ZENODO_HELP + "publication-date/",),
    ),
    "metadata.creators[].name": FieldPolicy(
        "required", "selection",
        "At least one named creator is required. Selecting an ORCID search result can complete a person's name.",
        (ZENODO_CREATORS, ZENODO_SCHEMA),
    ),
    "metadata.creators[].orcid": FieldPolicy(
        "optional", "selection",
        "Optional; an ORCID search result can supply the identifier. It is not ensured for every creator.",
        (ZENODO_CREATORS, ZENODO_SCHEMA),
    ),
    "metadata.creators[].affiliation": FieldPolicy(
        "optional", "selection",
        "Optional; selecting a ROR result supplies the affiliation. Free text is also allowed.",
        (ZENODO_CREATORS, ZENODO_SCHEMA),
    ),
    "metadata.keywords[]": FieldPolicy(
        "optional", "none", "Custom keywords are optional and entered by the author.",
        (ZENODO_SUBJECTS, ZENODO_SCHEMA),
    ),
    "metadata.subjects[].term": FieldPolicy(
        "conditional", "selection",
        "Subjects are optional. Selecting a controlled term supplies its label.",
        (ZENODO_SUBJECTS,),
    ),
    "metadata.subjects[].identifier": FieldPolicy(
        "system", "selection",
        "Supplied by a selected controlled term; no controlled subject is added without a selection.",
        (ZENODO_SUBJECTS,),
    ),
    "metadata.subjects[].scheme": FieldPolicy(
        "system", "selection", "Supplied by the vocabulary of the selected controlled term.",
        (ZENODO_SUBJECTS,),
    ),
    "metadata.language": FieldPolicy(
        "optional", "none", "Language selection is optional.", (ZENODO_SCHEMA,),
    ),
    "metadata.version": FieldPolicy(
        "optional", "none",
        "An author-defined version label is optional; "
        "it is not the repository's version identifier.",
        (ZENODO_SCHEMA,),
    ),
    "metadata.contributors[].name": FieldPolicy(
        "conditional", "selection",
        "A name is needed when adding an optional contributor; person lookup is available.",
        (ZENODO_CONTRIBUTORS, ZENODO_CREATORS),
    ),
    "metadata.contributors[].type": FieldPolicy(
        "conditional", "none", "Select a role when adding a contributor.",
        (ZENODO_CONTRIBUTORS,),
    ),
    "metadata.contributors[].orcid": FieldPolicy(
        "optional", "selection", "Optional, as for creators; person lookup can supply an ORCID.",
        (ZENODO_CONTRIBUTORS, ZENODO_CREATORS, ZENODO_SCHEMA),
    ),
    "metadata.contributors[].affiliation": FieldPolicy(
        "optional", "selection", "Optional, as for creators; ROR selection can supply an affiliation.",
        (ZENODO_CONTRIBUTORS, ZENODO_CREATORS, ZENODO_SCHEMA),
    ),
    "metadata.related_identifiers[].identifier": FieldPolicy(
        "conditional", "none", "Enter an identifier when adding an optional related resource.",
        (ZENODO_SCHEMA, ZENODO_IDENTIFIERS),
    ),
    "metadata.related_identifiers[].relation": FieldPolicy(
        "conditional", "none", "Choose a relation when adding a related resource.", (ZENODO_SCHEMA,),
    ),
    "metadata.related_identifiers[].scheme": FieldPolicy(
        "conditional", "detected", "The scheme is detected for recognized identifiers; otherwise supply it.",
        (ZENODO_IDENTIFIERS,),
    ),
    "metadata.references[]": FieldPolicy(
        "optional", "none", "References are optional.", (ZENODO_SCHEMA,),
    ),
    "metadata.grants[].code": FieldPolicy(
        "optional", "selection", "A selected grant may supply its number; a custom grant number is optional.",
        (ZENODO_FUNDING,),
    ),
    "metadata.grants[].title": FieldPolicy(
        "optional", "selection", "A selected grant may supply its title; a custom grant title is optional.",
        (ZENODO_FUNDING,),
    ),
    "metadata.grants[].funder.name": FieldPolicy(
        "conditional", "selection", "Select a funder when adding funding; grant selection can supply the funder.",
        (ZENODO_FUNDING, ZENODO_SCHEMA),
    ),
    "metadata.communities[].identifier": FieldPolicy(
        "optional", "selection", "Community submission is optional; choosing a community supplies its identifier.",
        ("https://help.zenodo.org/docs/about/whats-changed/",
         "https://help.zenodo.org/docs/share/submit-to-community/"),
    ),
    "metadata.notes": FieldPolicy(
        "optional", "none", "Additional descriptions, including notes, are optional.",
        (ZENODO_HELP + "descriptions/",),
    ),
    "metadata.method": FieldPolicy(
        "optional", "none", "An additional methods description is optional.",
        (ZENODO_HELP + "descriptions/",),
    ),
    "metadata.locations[]": FieldPolicy(
        "optional", "none", "Locations are optional.", (ZENODO_SCHEMA,),
    ),
    "metadata.dates[]": FieldPolicy(
        "optional", "none", "Additional resource dates or coverage dates are optional.", (ZENODO_SCHEMA,),
    ),
}


DRYAD_FIELDS = {
    "identifier": FieldPolicy(
        "system", "generated", "Dryad reserves a DOI when a submission starts.", (DRYAD_PUBLICATION,),
    ),
    "title": FieldPolicy(
        "required", "import", "A title is required; it can be imported from a linked publication.",
        (DRYAD_METADATA, DRYAD_CONNECT),
    ),
    "abstract": FieldPolicy(
        "required", "import", "An abstract is required; publication import can supply an initial value.",
        (DRYAD_DESCRIPTION, DRYAD_CONNECT),
    ),
    "publicationDate": FieldPolicy(
        "system", "generated", "Set by Dryad's publication workflow.",
        (DRYAD_PUBLICATION, DRYAD_API_METADATA),
    ),
    "authors[].firstName": FieldPolicy(
        "required", "import",
        "Each author needs a name. The first author is prefilled from the account; "
        "author lists can be imported.",
        (DRYAD_AUTHORS, DRYAD_CONNECT),
    ),
    "authors[].lastName": FieldPolicy(
        "required", "import",
        "Each author needs a name. The first author is prefilled from the account; "
        "author lists can be imported.",
        (DRYAD_AUTHORS, DRYAD_CONNECT),
    ),
    "authors[].orcid": FieldPolicy(
        "conditional", "none",
        "ORCID is required for account login, not for every coauthor. Coauthors can add an ORCID after publication.",
        (DRYAD_HELP + "account/login", DRYAD_METADATA),
    ),
    "authors[].affiliation": FieldPolicy(
        "required", "selection", "At least one affiliation per author; ROR selection or a free-text name is accepted.",
        (DRYAD_AUTHORS,),
    ),
    "authors[].affiliationROR": FieldPolicy(
        "system", "selection", "ROR selection supplies the identifier; a free-text affiliation need not have one.",
        (DRYAD_AUTHORS,),
    ),
    "keywords[]": FieldPolicy(
        "required", "import", "At least three keywords are required; publication metadata can be imported.",
        (DRYAD_DESCRIPTION, DRYAD_CONNECT),
    ),
    "fieldOfScience": FieldPolicy(
        "required", "selection", "Select at least one OECD research domain; selection supplies the controlled value.",
        (DRYAD_DESCRIPTION,),
    ),
    "versionNumber": FieldPolicy(
        "system", "generated", "Version numbering is managed by Dryad; revisions retain the dataset DOI.",
        (DRYAD_PUBLICATION, DRYAD_API_METADATA),
    ),
    "relatedWorks[].identifier": FieldPolicy(
        "conditional", "none", "Enter a DOI or URL when connecting a related work or associated published article.",
        (DRYAD_CONNECT, DRYAD_METADATA),
    ),
    "relatedWorks[].relationship": FieldPolicy(
        "conditional", "selection",
        "Choose the work type when adding a related work; Dryad derives the relationship from that choice.",
        (DRYAD_CONNECT, DRYAD_RELATIONS),
    ),
    "relatedWorks[].identifierType": FieldPolicy(
        "system", "detected", "The related-work form accepts a DOI or URL and records its identifier type.",
        (DRYAD_CONNECT, DRYAD_RELATIONS),
    ),
    "funders[].organization": FieldPolicy(
        "conditional", "selection", "Funding is optional; each added award needs a granting organization name.",
        (DRYAD_DESCRIPTION, DRYAD_METADATA, DRYAD_FUNDING_FORM),
    ),
    "funders[].identifier": FieldPolicy(
        "system", "selection", "Selecting a registered funding organization supplies its identifier.",
        (DRYAD_METADATA, DRYAD_FUNDING_FORM),
    ),
    "funders[].identifierType": FieldPolicy(
        "system", "selection", "The funding form supplies the ROR scheme for a selected organization.",
        (DRYAD_FUNDING_FORM,),
    ),
    "funders[].awardNumber": FieldPolicy(
        "optional", "selection",
        "Grant numbers are recommended. For supported funders, choosing an award search result supplies the number.",
        (DRYAD_METADATA, DRYAD_FUNDING_SEARCH),
    ),
    "funders[].awardDescription": FieldPolicy(
        "optional", "none", "Additional award information is optional.",
        (DRYAD_DESCRIPTION, DRYAD_API_METADATA),
    ),
    "methods": FieldPolicy(
        "optional", "none", "Methods are recommended, but optional.", (DRYAD_DESCRIPTION,),
    ),
    "usageNotes": FieldPolicy(
        "optional", "none",
        "Legacy usage notes are optional; current guidance asks for reuse instructions in a README.",
        (DRYAD_API_METADATA, DRYAD_HELP + "submission_steps/readme"),
    ),
    "locations[]": FieldPolicy(
        "optional", "none", "Spatial coverage is optional metadata.", (DRYAD_API_METADATA,),
    ),
}


FIGSHARE_FIELDS = {
    "doi": FieldPolicy(
        "system", "generated", "Figshare assigns a DOI automatically for public figshare.com items.",
        (FIGSHARE_FORM, FIGSHARE_SCHEMA),
    ),
    "title": FieldPolicy(
        "required", "none", "A title is required.", (FIGSHARE_SCHEMA,),
    ),
    "description": FieldPolicy(
        "required", "none", "A description is required; some item types label it Abstract.",
        (FIGSHARE_SCHEMA, FIGSHARE_FORM),
    ),
    "defined_type_name": FieldPolicy(
        "required", "selection", "Select an item type; Figshare supplies the corresponding type name.",
        (FIGSHARE_SCHEMA, FIGSHARE_FORM),
    ),
    "published_date": FieldPolicy(
        "system", "generated", "Set by Figshare when the version is published.", (FIGSHARE_SCHEMA,),
    ),
    "authors[].full_name": FieldPolicy(
        "required", "selection", "At least one author; selecting an existing account supplies its name.",
        (FIGSHARE_SCHEMA, FIGSHARE_FORM),
    ),
    "authors[].orcid_id": FieldPolicy(
        "optional", "selection", "Optional on figshare.com; an existing author's profile may supply an ORCID.",
        (FIGSHARE_SCHEMA, FIGSHARE_FORM, FIGSHARE_API),
    ),
    "keywords[]": FieldPolicy(
        "required", "none", "At least one keyword is required; keyword suggestions still need author selection.",
        (FIGSHARE_SCHEMA, FIGSHARE_FORM),
    ),
    "categories[].title": FieldPolicy(
        "varies", "selection",
        "The schema overview calls categories required; the newer form guide calls "
        "them optional unless an institution requires them. Selection supplies titles.",
        (FIGSHARE_SCHEMA, FIGSHARE_FORM),
    ),
    "categories[].id": FieldPolicy(
        "varies", "selection",
        "Category requirements depend on the form (the official guides differ). Selection supplies IDs.",
        (FIGSHARE_SCHEMA, FIGSHARE_FORM),
    ),
    "version": FieldPolicy(
        "system", "generated", "Version numbering is managed by Figshare.", (FIGSHARE_SCHEMA,),
    ),
    "related_materials[].identifier": FieldPolicy(
        "conditional", "none", "Enter an identifier when adding optional related material.",
        (FIGSHARE_FORM, FIGSHARE_API),
    ),
    "related_materials[].relation": FieldPolicy(
        "conditional", "default", "A related material needs a relation; the API default is References.",
        (FIGSHARE_FORM, FIGSHARE_API),
    ),
    "related_materials[].identifier_type": FieldPolicy(
        "conditional", "default", "A related material needs an identifier type; the API default is URL.",
        (FIGSHARE_FORM, FIGSHARE_API),
    ),
    "related_materials[].title": FieldPolicy(
        "optional", "none", "A related resource title is optional.", (FIGSHARE_API,),
    ),
    "references[]": FieldPolicy(
        "optional", "none", "Optional legacy field; superseded by related materials.", (FIGSHARE_API,),
    ),
    "funding": FieldPolicy(
        "optional", "none", "A free-text funding description is optional.", (FIGSHARE_FORM, FIGSHARE_SCHEMA),
    ),
    "funding_list[].grant_code": FieldPolicy(
        "system", "selection",
        "A selected Dimensions grant supplies its code when available; custom funding need not include it.",
        (FIGSHARE_FORM, FIGSHARE_API),
    ),
    "funding_list[].title": FieldPolicy(
        "conditional", "selection", "Custom funding needs a title; selecting a Dimensions grant supplies one.",
        (FIGSHARE_FORM, FIGSHARE_API),
    ),
    "funding_list[].funder_name": FieldPolicy(
        "system", "selection",
        "A selected Dimensions grant supplies its funder when available; custom funding need not include it.",
        (FIGSHARE_FORM, FIGSHARE_API),
    ),
    "resource_doi": FieldPolicy(
        "optional", "none", "Deprecated optional field; use related materials.", (FIGSHARE_SCHEMA, FIGSHARE_API),
    ),
    "resource_title": FieldPolicy(
        "optional", "none", "Deprecated optional field; use related materials.", (FIGSHARE_SCHEMA, FIGSHARE_API),
    ),
}


PDB_FIELDS = {
    "rcsb_id": FieldPolicy(
        "system", "generated", "A public PDB accession is assigned by the archive, distinct from a deposition session ID.",
        (PDB_IDENTIFIERS,),
    ),
    "database_2[].pdbx_DOI": FieldPolicy(
        "system", "generated", "The PDB database row supplies the structure DOI; other rows can describe different datasets.",
        (PDB_IDENTIFIERS,),
    ),
    "struct.title": FieldPolicy(
        "required", "none", "A structure title is required for deposition; it must distinguish this experiment from related entries.",
        (PDB_DICTIONARY + "_struct.title.html",),
    ),
    "struct_keywords.text": FieldPolicy(
        "required", "none", "Provide descriptive keywords for deposition. The API represents them as comma-separated text.",
        (PDB_DICTIONARY + "_struct_keywords.text.html",),
    ),
    "struct_keywords.pdbx_keywords": FieldPolicy(
        "required", "selection", "Deposition requires classification terms; the dictionary lists a controlled deposition vocabulary.",
        (PDB_DICTIONARY + "_struct_keywords.pdbx_keywords.html",),
    ),
    "audit_author[].name": FieldPolicy(
        "required", "none", "List the people or groups responsible for the structure entry, separately from citation authors.",
        (PDB_DICTIONARY + "_audit_author.name.html",),
    ),
    "audit_author[].pdbx_ORCID": FieldPolicy(
        "conditional", "none", "OneDep requires ORCIDs for contact authors; this does not ensure a public ORCID for every structure author.",
        ("https://www.wwpdb.org/news/news?year=2023", PDB_FAQ),
    ),
    "pdbx_database_status.process_site": FieldPolicy(
        "system", "generated", "OneDep routes the deposition to a processing site. Its archive code identifies the processing organization, not an author affiliation.",
        (PDB_FAQ, PDB_DATA_API),
    ),
    "rcsb_accession_info.deposit_date": FieldPolicy(
        "system", "generated", "Archive deposition timestamp; it is not the experiment's creation date.",
        (PDB_DATA_API, PDB_FAQ),
    ),
    "rcsb_accession_info.initial_release_date": FieldPolicy(
        "system", "generated", "The archive records initial public release following the depositor's release instructions.",
        (PDB_DATA_API, PDB_FAQ),
    ),
    "rcsb_accession_info.revision_date": FieldPolicy(
        "system", "generated", "The archive records the latest revision date independently of the primary article's publication date.",
        (PDB_VERSIONS, PDB_DATA_API),
    ),
    "rcsb_accession_info.major_revision": FieldPolicy(
        "system", "generated", "The archive increments the major version for changes to coordinates, polymer sequence or chemical identity.",
        (PDB_VERSIONS,),
    ),
    "rcsb_accession_info.minor_revision": FieldPolicy(
        "system", "generated", "Other metadata updates increment the minor version. A version number alone is not a version identifier.",
        (PDB_VERSIONS,),
    ),
    "exptl[].method": FieldPolicy(
        "required", "none", "Declare the experimental method when starting the deposition and supply the corresponding experimental data.",
        (PDB_FAQ, "https://deposit-1.wwpdb.org/"),
    ),
    "rcsb_entry_container_identifiers.polymer_entity_ids[]": FieldPolicy(
        "system", "generated", "RCSB exposes entity IDs from the deposited molecular definitions; detailed entity metadata has separate endpoints.",
        (PDB_DATA_API,),
    ),
    "rcsb_primary_citation.pdbx_database_id_DOI": FieldPolicy(
        "conditional", "none", "An associated publication may be linked or updated later; unpublished entries need not have an article DOI.",
        (PDB_FAQ,),
    ),
}


REPOSITORY_POLICIES = {
    "pdb": RepositoryPolicy(
        "2026-09-25",
        "Public PDB structure entries via RCSB; OneDep deposition and PDBx/mmCIF deposition requirements.",
        PDB_FIELDS,
    ),
    "zenodo": RepositoryPolicy(
        "2026-09-24", "Standard Zenodo deposit form; community-specific requirements can add constraints.",
        ZENODO_FIELDS,
    ),
    "dryad": RepositoryPolicy(
        "2026-09-25", "Standard Dryad dataset submission checklist.", DRYAD_FIELDS,
    ),
    "figshare": RepositoryPolicy(
        "2026-09-25", "Public figshare.com workflow; institutional forms may impose additional requirements.",
        FIGSHARE_FIELDS,
    ),
}
