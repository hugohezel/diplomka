"""Native API mappings and the declared G01–G10 search-readiness profile.

Mappings describe meaning, not mandatory repository fields. Unmapped dimensions
stay unknown; arbitrary custom fields and article abstracts are not crosswalked.
"""

from dataclasses import dataclass
import re


RULE_VERSION = "1.1"
PROFILE_NAME = "public_repository_api"
# Restrict deterministic failures to explicit placeholders. Sample identifiers,
# acronyms and domain abbreviations such as N/A need semantic review.
TITLE_PLACEHOLDER = re.compile(
    r"(?:untitled(?: (?:dataset|data|record))?|dataset(?: title)?|title(?: here)?|"
    r"bez názvu|názov datasetu|todo|tbd|"
    r"(?:insert|enter|add|your) (?:a )?(?:dataset )?title(?: here)?|"
    r"\[title\]|\{title\}|<title>)"
)
GROUP_LABELS = {
    "G01": "Identity and dataset binding",
    "G02": "Identifying name",
    "G03": "Informative summary",
    "G04": "Terms and concepts",
    "G05": "Data kind",
    "G06": "Origin and agent roles",
    "G07": "Scope",
    "G08": "Generation process",
    "G09": "Typed relations",
    "G10": "Metadata publication channel",
}
SCOPE_DIMENSIONS = {
    "E": "entities", "P": "properties", "S": "spatial_coverage",
    "T": "temporal_coverage", "G": "granularity",
}


@dataclass(frozen=True)
class RepositoryMapping:
    version: str
    landing_page: str
    relations: str
    relation_type: str
    relation_scheme: str
    method: str | None = None
    spatial: str | None = None
    temporal: str | None = None
    contributors: str | None = None
    contributor_role: str | None = None
    publishers: tuple[tuple[str, str], ...] = ()


# Shared title/description/creator/term paths are in metadata_config.PROFILES.
# Sources: https://developers.zenodo.org/#deposit-metadata
# https://github.com/datadryad/dryad-app/blob/main/documentation/apis/dataset_metadata.md
# https://docs.figshare.com/swagger.json (ArticleComplete, RelatedMaterial)
REPOSITORY_MAPPINGS = {
    "pdb": RepositoryMapping(
        version="rcsb_accession_info.major_revision", landing_page="rcsb_id",
        relations="rcsb_primary_citation", relation_type="id",
        relation_scheme="pdbx_database_id_DOI", method="exptl[].method",
        publishers=(("pdbx_database_status.process_site", "processor"),),
    ),
    "zenodo": RepositoryMapping(
        version="metadata.version", landing_page="links.self_html",
        relations="metadata.related_identifiers", relation_type="relation",
        relation_scheme="scheme", method="metadata.method",
        spatial="metadata.locations", temporal="metadata.dates",
        contributors="metadata.contributors", contributor_role="type",
        publishers=(("metadata.publisher", "publisher"), ("repository", "host")),
    ),
    "dryad": RepositoryMapping(
        version="versionNumber", landing_page="_links.stash:dataset.href",
        relations="relatedWorks", relation_type="relationship",
        relation_scheme="identifierType", method="methods", spatial="locations",
        publishers=(("publisher", "publisher"), ("repository", "host")),
    ),
    "figshare": RepositoryMapping(
        version="version", landing_page="url_public_html",
        relations="related_materials", relation_type="relation",
        relation_scheme="identifier_type",
        publishers=(("publisher", "publisher"), ("repository", "host")),
    ),
}

# This extensible crosswalk describes content. Dataset and MIME/file formats
# deliberately have no mapping: they cannot establish scientific data kind.
DATA_KINDS = {
    "image": "images", "figure": "images", "audio": "audio",
    "video": "video", "text corpus": "text corpus",
    "tabular data": "tabular observations", "time series": "time series",
    "sequence": "sequences", "spatial data": "spatial layers",
    "graph": "graph", "mixed collection": "mixed collection",
}

# DataCite relation names encode direction from the evaluated object to target.
# Unknown labels remain UNSURE rather than being assigned a guessed meaning.
RELATION_TYPES = {
    "iscitedby", "cites", "issupplementto", "issupplementedby",
    "iscontinuedby", "continues", "isdescribedby", "describes",
    "hasmetadata", "ismetadatafor", "hasversion", "isversionof",
    "isnewversionof", "ispreviousversionof", "ispartof", "haspart",
    "ispublishedin", "isreferencedby", "references", "isdocumentedby",
    "documents", "iscompiledby", "compiles", "isvariantformof",
    "isoriginalformof", "isidenticalto", "isreviewedby", "reviews",
    "isderivedfrom", "issourceof", "isrequiredby", "requires", "obsoletes",
    "isobsoletedby", "collects", "iscollectedby", "isalternateidentifier",
}

# Native Zenodo contributor roles; Other carries no interpretable specific role.
# https://developers.zenodo.org/#deposit-metadata
CONTRIBUTOR_ROLES = {
    "contactperson", "datacollector", "datacurator", "datamanager",
    "distributor", "editor", "hostinginstitution", "producer",
    "projectleader", "projectmanager", "projectmember", "registrationagency",
    "registrationauthority", "relatedperson", "researcher", "researchgroup",
    "rightsholder", "supervisor", "sponsor", "workpackageleader",
}

# Accession namespaces supported by the generic relation interpreter.
# Recognition establishes interpretation, not registry existence or relevance.
RELATION_ACCESSIONS = {
    "pmid": re.compile(r"[1-9][0-9]*"),
    "arxiv": re.compile(r"(?:[0-9]{4}\.[0-9]{4,5}|[a-z-]+(?:\.[A-Z]{2})?/[0-9]{7})(?:v[1-9][0-9]*)?", re.I),
    "isbn": re.compile(r"(?:[0-9][ -]?){9}[0-9X]|(?:[0-9][ -]?){12}[0-9]", re.I),
    "issn": re.compile(r"[0-9]{4}-[0-9]{3}[0-9X]", re.I),
    "eissn": re.compile(r"[0-9]{4}-[0-9]{3}[0-9X]", re.I),
}
