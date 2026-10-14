"""Evidence context and consistent results for the generic API profile."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .checks import CheckResult, Metadata, make_result, read_field
from .generic_metadata_config import (
    GROUP_LABELS, PROFILE_NAME, REPOSITORY_MAPPINGS, RULE_VERSION,
    SCOPE_DIMENSIONS, RepositoryMapping,
)
from .metadata_config import PROFILES, MetadataProfile
from .search_readiness_specs import check_specification


@dataclass(frozen=True)
class EvaluationContext:
    reference: str | None = None
    expected_record_id: str | None = None
    expected_identifier: str | None = None
    expected_version: str | None = None
    source_url: str | None = None
    complete: bool = True
    # None means applicability has not been declared. An explicit selection
    # activates those scope tasks and disables the others with a recorded reason.
    scope_dimensions: frozenset[str] | None = None
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self) -> None:
        if self.scope_dimensions is not None:
            unknown = self.scope_dimensions - SCOPE_DIMENSIONS.keys()
            if unknown:
                raise ValueError(f"Unknown scope dimensions: {sorted(unknown)}")


@dataclass(frozen=True)
class CheckBuilder:
    source: Metadata
    repository: str
    context: EvaluationContext

    @property
    def fields(self) -> MetadataProfile:
        return PROFILES[self.repository]

    @property
    def mapping(self) -> RepositoryMapping:
        return REPOSITORY_MAPPINGS[self.repository]

    def missing_status(self) -> str:
        return "FAIL" if self.context.complete else "UNSURE"

    def result(
        self, group: str, test: str, label: str, path: str, value: Any,
        *, status: str, message: str, applicable: bool | None = True,
        applicability_reason: str = "Required by the declared API search task.",
        required: bool = True, semantic: bool = False,
        supports: tuple[str, ...] = (), **details: Any,
    ) -> CheckResult:
        identifier = read_field(self.source, self.fields["doi"])
        if self.repository == "pdb":
            identifier = next((item.get("pdbx_DOI") for item in (self.source.get("database_2") or [])
                if isinstance(item, dict) and item.get("database_id") == "PDB"), None)
        specification = check_specification(self.repository, group, test, path, semantic)
        specification.update(details)
        return make_result(
            group, test, label, path, value, status=status, message=message,
            kind="required" if required else "diagnostic",
            groupLabel=GROUP_LABELS[group], ruleVersion=RULE_VERSION,
            profile=PROFILE_NAME, applicable=applicable,
            applicabilityReason=applicability_reason, requiredForGroup=required,
            decisionMethod=("semantic_review_required" if semantic else "deterministic"),
            sourceRepresentation={
                "kind": "public_repository_api", "schema": self.repository,
                "url": self.context.source_url,
                "complete": self.context.complete,
            },
            targetObject={
                "repository": self.repository, "recordId": self.source.get("rcsb_id", self.source.get("id")),
                "identifier": identifier,
                "version": read_field(self.source, self.mapping.version),
            },
            evaluatedAt=self.context.evaluated_at, supports=list(supports),
            **specification,
        )
