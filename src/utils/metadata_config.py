"""Repository field mappings and controlled values shared by metadata checks."""

import re
from typing import TypedDict


class ProfileOptions(TypedDict, total=False):
    keyword_separator: str
    creator_surname_field: str
    organization_fields: tuple[str, ...]


class MetadataProfile(ProfileOptions):
    title: str
    description: str | None
    keywords: str
    creators: str
    creator_orcid_field: str
    subjects: str
    type: str | None
    doi: str
    api: str
    replaced: set[str]


PROFILES: dict[str, MetadataProfile] = {
    "pdb": {
        "title": "struct.title",
        # The entry endpoint has no equivalent description or generic type.
        # None means unmapped, distinct from a mapped field missing in a record.
        "description": None,
        "subjects": "struct_keywords.pdbx_keywords",
        "type": None,
        "keywords": "struct_keywords.text",
        "keyword_separator": ",",
        "creators": "audit_author",
        "creator_orcid_field": "pdbx_ORCID",
        "organization_fields": ("pdbx_database_status.process_site",),
        "doi": "database_2[].pdbx_DOI",
        "api": "https://data.rcsb.org/rest/v1/core/entry/",
        "replaced": {
            "rcsb_id",
            "database_2[].pdbx_DOI",
            "struct.title",
            "struct_keywords.text",
            "struct_keywords.pdbx_keywords",
            "audit_author[].name",
            "audit_author[].pdbx_ORCID",
            "pdbx_database_status.process_site",
            "rcsb_accession_info.deposit_date",
            "rcsb_accession_info.initial_release_date",
            "rcsb_accession_info.revision_date",
        },
    },
    "zenodo": {
        "title": "metadata.title",
        "description": "metadata.description",
        "keywords": "metadata.keywords",
        "creators": "metadata.creators",
        "creator_orcid_field": "orcid",
        "subjects": "metadata.subjects",
        "type": "metadata.resource_type.type",
        "doi": "doi",
        "api": "https://zenodo.org/api/records/",
        "replaced": {
            "doi",
            "metadata.title",
            "metadata.description",
            "metadata.resource_type.type",
            "metadata.publication_date",
            "metadata.creators[].name",
            "metadata.creators[].orcid",
            "metadata.creators[].affiliation",
            "metadata.keywords[]",
            "metadata.subjects[].term",
            "metadata.subjects[].identifier",
            "metadata.subjects[].scheme",
        },
    },
    "dryad": {
        "title": "title",
        "description": "abstract",
        "keywords": "keywords",
        "creators": "authors",
        "creator_orcid_field": "orcid",
        "creator_surname_field": "lastName",
        "subjects": "fieldOfScience",
        "type": "type",
        "doi": "identifier",
        "api": "https://datadryad.org/api/v2/datasets/",
        "replaced": {
            "identifier",
            "title",
            "abstract",
            "publicationDate",
            "authors[].firstName",
            "authors[].lastName",
            "authors[].orcid",
            "authors[].affiliation",
            "authors[].affiliationROR",
            "keywords[]",
            "fieldOfScience",
        },
    },
    "figshare": {
        "title": "title",
        "description": "description",
        "keywords": "keywords",
        "creators": "authors",
        "creator_orcid_field": "orcid_id",
        "subjects": "categories",
        "type": "defined_type_name",
        "doi": "doi",
        "api": "https://api.figshare.com/v2/articles/",
        "replaced": {
            "doi",
            "title",
            "description",
            "defined_type_name",
            "published_date",
            "authors[].full_name",
            "authors[].orcid_id",
            "keywords[]",
            "categories[].title",
            "categories[].id",
        },
    },
}

TITLE_TEMPLATE = re.compile(
    r"(?:untitled(?: (?:dataset|data|record))?|title(?: here)?|"
    r"dataset(?: title)?|test(?: dataset)?|sample(?: dataset)?|"
    r"example(?: dataset)?|todo|tbd|n/?a|bez názvu|názov(?: datasetu)?|"
    r"(?:insert|enter|add|your) (?:a )?(?:dataset )?title(?: here)?)"
    r"(?:[ _-]*[0-9]+)?"
)
BRACKETED_TITLE_TEMPLATE = re.compile(r"[\[{<].*(?:title|názov).*[\]}>]")

FILE_FORMATS = {
    "csv", "tsv", "json", "xml", "xlsx", "xls", "txt", "pdf", "zip",
    "netcdf", "hdf5", "text/csv", "application/json",
}
OTHER_RESOURCE_TYPES = {
    "other", "software", "publication", "image", "video", "audio",
    "poster", "presentation", "workflow", "model", "collection",
    "figure", "media", "journal contribution",
}
FOS_SCHEMES = {"fos", "oecd", "oecd fos", "oecd fos 2007"}
LOOKUP_SUBJECT_SCHEMES = {"efo", "mesh", "gnd"}
FIGSHARE_CATEGORIES_URL = "https://api.figshare.com/v2/categories"

# OECD FOS 2007; Dryad explicitly uses this controlled vocabulary.
# https://www.oecd-ilibrary.org/mapping-careers-and-mobility-of-doctorate-holders_5kzsnsbph6g5.pdf
# https://github.com/datadryad/dryad-app/blob/main/documentation/apis/dataset_metadata.md
FOS = {
    "1": "Natural sciences",
    "1.1": "Mathematics",
    "1.2": "Computer and information sciences",
    "1.3": "Physical sciences",
    "1.4": "Chemical sciences",
    "1.5": "Earth and related environmental sciences",
    "1.6": "Biological sciences",
    "1.7": "Other natural sciences",
    "2": "Engineering and technology",
    "2.1": "Civil engineering",
    "2.2": "Electrical engineering, electronic engineering, information engineering",
    "2.3": "Mechanical engineering",
    "2.4": "Chemical engineering",
    "2.5": "Materials engineering",
    "2.6": "Medical engineering",
    "2.7": "Environmental engineering",
    "2.8": "Environmental biotechnology",
    "2.9": "Industrial biotechnology",
    "2.10": "Nanotechnology",
    "2.11": "Other engineering and technologies",
    "3": "Medical and health sciences",
    "3.1": "Basic medicine",
    "3.2": "Clinical medicine",
    "3.3": "Health sciences",
    "3.4": "Medical biotechnology",
    "3.5": "Other medical sciences",
    "4": "Agricultural sciences",
    "4.1": "Agriculture, forestry and fisheries",
    "4.2": "Animal and dairy science",
    "4.3": "Veterinary science",
    "4.4": "Agricultural biotechnology",
    "4.5": "Other agricultural sciences",
    "5": "Social sciences",
    "5.1": "Psychology",
    "5.2": "Economics and business",
    "5.3": "Educational sciences",
    "5.4": "Sociology",
    "5.5": "Law",
    "5.6": "Political science",
    "5.7": "Social and economic geography",
    "5.8": "Media and communications",
    "5.9": "Other social sciences",
    "6": "Humanities",
    "6.1": "History and archaeology",
    "6.2": "Languages and literature",
    "6.3": "Philosophy, ethics and religion",
    "6.4": "Arts",
    "6.5": "Other humanities",
}
