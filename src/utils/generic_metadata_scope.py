"""Independent scope dimensions; lifecycle dates never stand in for data time."""

import math
from collections.abc import Mapping
from typing import Any

from .checks import CheckResult, all_pass_status, has_value, normalize_text, plain_text, read_field
from .generic_metadata_config import SCOPE_DIMENSIONS
from .generic_metadata_model import CheckBuilder
from .metadata_dates import parse_date


def _coordinate(value: Any, limit: int) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return False
    try:
        numeric = float(value)
    except (ValueError, OverflowError):
        return False
    return math.isfinite(numeric) and -limit <= numeric <= limit


def _spatial_evidence(value: Any) -> CheckResult:
    evidence = {"value": value, "status": "UNSURE"}
    if not isinstance(value, Mapping):
        return {**evidence, "message": "No supported structured location mapping."}
    place = plain_text(value.get("place"))
    coordinate_sets = []
    if "lat" in value or "lon" in value:
        coordinate_sets.append((value.get("lat"), value.get("lon")))
    point = value.get("point")
    box = value.get("box")
    # Dryad's native point/box model uses string coordinates. Retain that
    # representation and validate its geometry instead of silently ignoring it.
    if point is not None:
        if not isinstance(point, Mapping):
            return {**evidence, "status": "FAIL", "message": "Malformed point geometry."}
        coordinate_sets.append((point.get("latitude"), point.get("longitude")))
    if box is not None:
        if not isinstance(box, Mapping):
            return {**evidence, "status": "FAIL", "message": "Malformed box geometry."}
        coordinate_sets.extend((
            (box.get("swLatitude"), box.get("swLongitude")),
            (box.get("neLatitude"), box.get("neLongitude")),
        ))
    if coordinate_sets:
        if not all(_coordinate(lat, 90) and _coordinate(lon, 180)
            for lat, lon in coordinate_sets):
            return {**evidence, "status": "FAIL", "message": "Invalid latitude/longitude or incomplete coordinate pair."}
        if isinstance(box, Mapping) and float(box["swLatitude"]) > float(box["neLatitude"]):
            return {**evidence, "status": "FAIL", "message": "Box's south latitude is north of its north latitude."}
        if not plain_text(value.get("crs")):
            return {**evidence, "status": "PASS" if place else "UNSURE",
                "message": "A named place supports text search; coordinate frame is not verified for geometric interpretation."}
        if normalize_text(value["crs"]) not in {"epsg:4326", "wgs84", "wgs 84"}:
            return {**evidence, "message": "Coordinate frame is not supported by this profile."}
        return {**evidence, "status": "PASS", "message": "Usable geographic coordinates in a supported frame."}
    return {**evidence, "status": "PASS" if place else "FAIL",
        "message": "A named data location supports textual geographic search; no geometry is inferred."}


def _temporal_evidence(value: Any) -> CheckResult:
    evidence = {"value": value, "status": "UNSURE"}
    if not isinstance(value, Mapping):
        return {**evidence, "message": "No supported content-time interval mapping."}
    role = normalize_text(value.get("type"))
    if role != "collected":
        return {**evidence, "message": "The date's role does not establish time of data content."}
    bounds = [value.get("start"), value.get("end")]
    present_bounds = [bound for bound in bounds if has_value(bound)]
    if not present_bounds:
        return {**evidence, "status": "FAIL", "message": "Content-time interval has no boundary."}
    parsed = [parse_date(bound) for bound in bounds]
    if any(parse_date(bound) is None for bound in present_bounds):
        return {**evidence, "message": "Unsupported or invalid time representation; no calendar or precision is guessed."}
    start, end = parsed
    if start and end:
        if start.timezone_aware != end.timezone_aware:
            return {**evidence, "message": "Timezone conventions do not allow comparison."}
        if start.earliest > end.latest:
            return {**evidence, "status": "FAIL", "message": "Interval starts after it ends."}
    return {**evidence, "status": "PASS", "role": "collection_time",
        "message": "Interpretable collection interval, preserving partial precision and open boundaries."}


def scope_checks(builder: CheckBuilder) -> list[CheckResult]:
    checks = []
    selected = builder.context.scope_dimensions
    for code, dimension in SCOPE_DIMENSIONS.items():
        path = {"S": builder.mapping.spatial, "T": builder.mapping.temporal}.get(code)
        textual_scope = code in {"E", "P", "G"}
        if textual_scope:
            path = builder.fields["description"]
        value = read_field(builder.source, path)
        values = value if isinstance(value, list) else [value] if value is not None else []
        if code == "T":
            # Publication, creation, update and withdrawal belong to lifecycle,
            # not coverage. Unknown/valid date roles remain visible as uncertain.
            values = [item for item in values if not isinstance(item, Mapping) or
                normalize_text(item.get("type")) not in {
                    "created", "issued", "updated", "withdrawn",
                }]
        declared = not textual_scope and any(has_value(item) for item in values)
        applicable = code in selected if selected is not None else True if declared else None
        if applicable is False:
            status = "NOT_APPLICABLE"
            message = "This scope dimension is excluded by the declared search tasks."
            evidence = []
        elif code in {"S", "T"} and declared:
            evaluator = _spatial_evidence if code == "S" else _temporal_evidence
            evidence = [evaluator(item) for item in values]
            status = all_pass_status(item["status"] for item in evidence)
            message = "Evaluate every declared item; one valid value cannot hide a conflicting value."
        else:
            evidence = [{"field": builder.fields["description"],
                "text": plain_text(read_field(builder.source, builder.fields["description"]), html=True)}]
            status = builder.missing_status() if applicable and path and not textual_scope else "UNSURE"
            message = (
                (
                    "No value is provided for this active dimension in the complete mapped "
                    "representation."
                )
                if status == "FAIL" else
                (
                    "Applicability or a trustworthy content mapping is unknown; textual scope "
                    "needs semantic review."
                )
            )
        reason = (
            "Scope tasks were explicitly selected by the evaluation profile."
            if selected is not None else
            (
                "A declared content dimension is evaluated; absence does not establish "
                "inapplicability."
            )
        )
        checks.append(builder.result(
            "G07",
            f"scope.{dimension}.usable",
            f"Scope {code}: {dimension.replace('_', ' ')}",
            path or f"{dimension} (unmapped)",
            value,
            status=status,
            message=message,
            applicable=applicable,
            applicability_reason=reason,
            evidence=evidence,
            semantic=textual_scope,
            supports=(f"{dimension}_search",),
        ))
        if code in {"S", "T"}:
            # An API value passing basic interpretation is not proof of an
            # implemented spatial/temporal facet in a particular indexer.
            checks.append(builder.result(
                "G07",
                f"scope.{dimension}.filter_ready",
                f"Scope {code}: structured filter readiness",
                path or f"{dimension} (unmapped)",
                value,
                status="NOT_APPLICABLE" if applicable is False else "UNSURE",
                message="This profile has no verified mapping to an indexer's geographic or temporal filter.",
                applicable=applicable,
                applicability_reason=reason,
                required=False,
                supports=(f"{dimension}_filter",),
            ))
    return checks
