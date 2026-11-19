"""Run the fixed catalogue against a small repository binding profile."""

from copy import deepcopy

from . import actor_recipes as actors
from . import basic_recipes as basic
from . import coverage_recipes as coverage
from . import relation_recipes as relations
from .bindings import mapped_fields
from .catalogue import catalogue, registries
from .lookups import LookupService
from .model import EvaluationContext
from .operations import Operations
from .profile import validate_translation


RECIPES = {
    "G1.1": basic.dataset_identifier, "G1.2": basic.identity_matches,
    "G2.1": basic.title, "G2.2": basic.title_detail,
    "G3.1": basic.description, "G3.2": basic.added_content,
    "G4.1": basic.terms, "G4.2": basic.topical_mismatch, "G4.3": basic.controlled_subjects,
    "G5.1": basic.scientific_kind, "G5.2": basic.representation, "G5.3": basic.file_formats,
    "G6.1": actors.named_actor, "G6.2": actors.actor_roles, "G6.3": actors.actor_identifiers,
    "G6.4": actors.institutional_origin, "G6.5": basic.dates,
    "G7.1": basic.studied_entity, "G7.2": basic.variables,
    "G7.3": coverage.spatial, "G7.4": coverage.temporal, "G8.1": coverage.production,
    "G9.1": relations.relations_present, "G9.2": relations.relation_identifiers,
    "G9.3": relations.relation_types, "G9.4": relations.relation_resolves,
}


def _public_definition(definition, profile):
    public = {"testId": definition["id"], "group": definition["group"], "label": definition["title"],
              "decisionMethod": definition["type"], "passRule": definition["passRule"],
              "searchabilityBenefit": definition["searchabilityBenefit"],
              "duplicateOf": deepcopy(definition["duplicateOf"]),
              "fujiCounterparts": deepcopy(definition["fujiCounterparts"]),
              "fujiOverlap": definition.get("fujiOverlap")}
    if profile is not None:
        public["mappedFields"] = mapped_fields(profile, definition["bindings"])
    return public


def describe_translation(profile=None):
    """Describe the fixed checks, adding native field mappings when the repository is known."""
    if profile is not None:
        validate_translation(profile)
    fixed = catalogue()
    return {"version": fixed["version"], "registryVersion": registries()["version"],
            "repository": profile["repository"] if profile is not None else None,
            "groups": fixed["groups"], "operations": fixed["operations"],
            "checks": [{**_public_definition(definition, profile), "plannedSteps": definition["steps"]} for definition in fixed["checks"]]}


def evaluate_translation(source, profile, *, context=None, lookup=None, semantic=None, on_event=None):
    validate_translation(profile)
    fixed, registry = catalogue(), registries()
    if set(RECIPES) != {check["id"] for check in fixed["checks"]}:
        raise ValueError("The system catalogue and fixed recipe set disagree.")
    context = context or EvaluationContext()
    lookup = lookup or LookupService(registry)
    groups = {group["id"]: group["title"] for group in fixed["groups"]}
    results, artifacts = [], {}
    if on_event:
        on_event({"event": "record_loaded", "catalogue": describe_translation(profile), "repositoryResponse": source})
    for definition in fixed["checks"]:
        if on_event:
            on_event({"event": "check_started", "testId": definition["id"]})
        op = Operations(source, profile, context, definition, registry, lookup, semantic)
        result = RECIPES[definition["id"]](op, artifacts)
        results.append({
            **_public_definition(definition, profile), **result,
            "groupLabel": groups[definition["group"]], "steps": op.steps,
            "profile": "public_repository_api", "ruleVersion": fixed["version"], "registryVersion": registry["version"],
            "requiredForGroup": True, "applicable": result["status"] != "NOT_APPLICABLE",
            "applicabilityReason": "No applicable supplied items." if result["status"] == "NOT_APPLICABLE" else "Fixed searchability criterion.",
            "sourceRepresentation": {"kind": "public_repository_api", "schema": profile["repository"], "url": context.source_url, "complete": context.complete},
            "evaluatedAt": context.evaluated_at,
        })
        if on_event:
            on_event({"event": "check_finished", "check": results[-1]})
    return results
