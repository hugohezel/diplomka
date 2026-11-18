"""Pure typed rules used by the shared VALIDATE operation."""

import math
import re
import calendar
from datetime import datetime, timedelta, timezone

from ..utils.checks import normalize_text, plain_text
from ..utils.metadata_dates import ISO_DATE, ISO_TIMESTAMP, parse_date
from .identifier_validation import validate_identifier
from .identifiers import namespace_name, normalize_identifier
from .model import outcome, reduce_status


def _text(value, registry, *, placeholders=False):
    text = normalize_text(value)
    excluded = {normalize_text(item) for values in registry["placeholders"].values() for item in values} if placeholders else set()
    valid = bool(text) and text not in excluded
    return outcome("PASS" if valid else "FAIL", "Nonblank text accepted." if valid else "Text is absent, blank or a whole-value placeholder.", normalized=text)


def _extended_bounds(text):
    """Proleptic Gregorian bounds, including ISO astronomical year 0000 (1 BCE)."""
    match = re.fullmatch(r"([+-]?[0-9]{4,})(?:-([0-9]{2})(?:-([0-9]{2}))?)?", text)
    if not match:
        return None
    year = int(match[1])
    month = int(match[2]) if match[2] else None
    day = int(match[3]) if match[3] else None
    if month is None:
        return (year, 1, 1), (year, 12, 31), "year"
    if not 1 <= month <= 12:
        return None
    last_day = calendar.monthrange(year, month)[1]
    if day is None:
        return (year, month, 1), (year, month, last_day), "month"
    if not 1 <= day <= last_day:
        return None
    return (year, month, day), (year, month, day), "day"


def _date(value, parser="iso"):
    if parser == "year":
        text = f"{value:04d}" if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 9999 else plain_text(value)
        if not re.fullmatch(r"[0-9]{4}", text):
            return outcome("FAIL", "A publication year must be an integer or four-digit year string.", value=value)
        return {**_date(text, "iso"), "value": value}
    if parser == "iso_interval":
        text = plain_text(value)
        if "/" not in text:
            return _date(value, "iso")
        bounds = text.split("/")
        if len(bounds) != 2 or not all(bounds):
            return outcome("FAIL", "An ISO interval requires two explicit date bounds.", value=value)
        return {**_temporal({"start": bounds[0], "end": bounds[1]}, {"parser": "iso"}),
                "value": value, "precision": "interval"}
    if parser == "mjd":
        try:
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                raise ValueError("MJD requires a numeric day count.")
            days = float(value)
            if not math.isfinite(days):
                raise ValueError("MJD must be finite.")
            instant = datetime(1858, 11, 17, tzinfo=timezone.utc) + timedelta(days=days)
        except (ValueError, TypeError, OverflowError):
            return outcome("FAIL", "Invalid or unrepresentable Modified Julian Date.", value=value)
        return outcome("PASS", "Valid Modified Julian Date; native day count retained.",
                       value=value, normalized=instant.isoformat(), precision="timestamp", timezoneAware=True)
    text = plain_text(value)
    if parser == "iso_extended":
        if ISO_TIMESTAMP.fullmatch(text):
            return _date(value, "iso")
        bounds = _extended_bounds(text)
        if bounds is None:
            return outcome("FAIL", "Invalid ISO astronomical calendar date.", value=value)
        return outcome("PASS", "Valid ISO astronomical calendar date; original era and precision preserved.",
                       value=value, precision=bounds[2], timezoneAware=False)
    formats = {"iso": lambda: ISO_DATE.fullmatch(text) or ISO_TIMESTAMP.fullmatch(text),
               "dmy": lambda: re.fullmatch(r"[0-9]{2}\.[0-9]{2}\.[0-9]{4}", text),
               "ymd_slash": lambda: re.fullmatch(r"[0-9]{4}/[0-9]{2}/[0-9]{2}", text)}
    if parser not in formats:
        return outcome("UNSURE", "The date parser is unsupported.")
    parsed = parse_date(value) if formats[parser]() else None
    if not parsed:
        return outcome("FAIL", "The date is not calendar-valid under the declared parser.", value=value)
    precision = "timestamp" if ISO_TIMESTAMP.fullmatch(text) else {4: "year", 7: "month"}.get(len(text), "day")
    return outcome("PASS", "Calendar-valid date; original precision preserved.", value=value, precision=precision, timezoneAware=parsed.timezone_aware)


def _coordinate_pair(latitude, longitude):
    try:
        valid = (not isinstance(latitude, bool) and not isinstance(longitude, bool)
                 and math.isfinite(float(latitude)) and math.isfinite(float(longitude))
                 and -90 <= float(latitude) <= 90 and -180 <= float(longitude) <= 180)
    except (TypeError, ValueError, OverflowError):
        valid = False
    return valid


def _geometry(geometry, crs):
    if crs not in {None, "EPSG:4326", "WGS84"}:
        return outcome("UNSURE", "No geometry parser is installed for the declared CRS.")
    if not isinstance(geometry, dict):
        return outcome("FAIL", "Malformed geometry.")
    kind, coordinates = geometry.get("type"), geometry.get("coordinates")
    def point(value):
        return isinstance(value, list) and len(value) >= 2 and _coordinate_pair(value[1], value[0])
    def line(value, minimum=2):
        return isinstance(value, list) and len(value) >= minimum and all(point(item) for item in value)
    def polygon(value):
        return isinstance(value, list) and bool(value) and all(line(ring, 4) and ring[0] == ring[-1] for ring in value)
    rules = {"Point": point, "LineString": line, "MultiPoint": lambda c: line(c, 1),
             "Polygon": polygon, "MultiLineString": lambda c: isinstance(c, list) and bool(c) and all(line(x) for x in c),
             "MultiPolygon": lambda c: isinstance(c, list) and bool(c) and all(polygon(x) for x in c)}
    if kind not in rules:
        return outcome("UNSURE", "Unsupported geometry type.")
    valid = rules[kind](coordinates)
    return outcome("PASS" if valid else "FAIL", "Validate geometry structure, coordinate order and ranges.", geometry=geometry, crs=crs or "EPSG:4326")


def _spatial(values, constants, registry):
    place = values.get("place", values.get("value"))
    results = []
    if isinstance(place, str):
        results.append(_text(place, registry, placeholders=True))
    if values.get("geometry") is not None:
        results.append(_geometry(values["geometry"], values.get("crs", constants.get("crs"))))
    latitude, longitude = values.get("latitude"), values.get("longitude")
    if latitude is not None or longitude is not None:
        crs = values.get("crs", constants.get("crs", "EPSG:4326"))
        if crs not in {"EPSG:4326", "WGS84"}:
            results.append(outcome("UNSURE", "Coordinate CRS is unsupported."))
        else:
            results.append(outcome("PASS" if _coordinate_pair(latitude, longitude) else "FAIL", "Validate latitude and longitude ranges."))
    return outcome(reduce_status([r["status"] for r in results], quantifier="ANY"), "A place label or valid geometry is required.", place=place, details=results)


def _temporal(values, constants):
    parser = constants.get("parser", "iso")
    if values.get("point") is not None:
        return _date(values["point"], parser)
    start, end = values.get("start"), values.get("end")
    present = [value for value in (start, end) if value is not None]
    if not present or ((start is None or end is None) and not constants.get("allow_open")):
        return outcome("FAIL", "An interval needs documented bounds or an explicitly supported open bound.")
    validation = [_date(value, parser) for value in present]
    status = reduce_status([entry["status"] for entry in validation])
    if status == "PASS" and start is not None and end is not None:
        if parser == "iso_extended":
            first_bounds, last_bounds = _extended_bounds(plain_text(start)), _extended_bounds(plain_text(end))
            if first_bounds is not None and last_bounds is not None:
                status = "FAIL" if first_bounds[0] > last_bounds[1] else "PASS"
                return outcome(status, "Compare astronomical calendar bounds without shifting BCE years.",
                               start=start, end=end, details=validation)
        first = parse_date(validation[0].get("normalized", start))
        last = parse_date(validation[-1].get("normalized", end))
        if first is None or last is None or first.timezone_aware != last.timezone_aware:
            status = "UNSURE"
        elif first.earliest > last.latest:
            status = "FAIL"
    return outcome(status, "Validate temporal bounds without inventing missing precision.", start=start, end=end, details=validation)


def _format(values, registry):
    declared, mime, name = (plain_text(values.get(key)) for key in ("format", "mime", "name"))
    excluded = {"unknown", "other", "none", "n/a", "application/octet-stream", "binary/octet-stream"}
    supported = set(registry["extensions"])
    evidence, warnings = [], []
    if declared and declared.casefold() not in excluded:
        if declared.casefold().lstrip(".") in supported or normalize_text(declared) in registry.get("formatLabels", {}) or re.fullmatch(r"[\w.+-]+/[\w.+-]+", declared):
            evidence.append({"source": "format", "value": declared})
    if mime and mime.casefold() not in excluded and re.fullmatch(r"[\w.+-]+/[\w.+-]+(?:\s*;[^\r\n]*)?", mime):
        evidence.append({"source": "mime", "value": mime})
    suffix = next((suffix for suffix in sorted(supported, key=len, reverse=True) if name.casefold().endswith("." + suffix)), None)
    if suffix:
        evidence.append({"source": "filename", "value": suffix})
    if declared and not evidence:
        return outcome("UNSURE" if declared.casefold() not in excluded else "FAIL", "No usable shared format definition or suffix is available.", declared=declared)
    if len(evidence) > 1:
        warnings.append("All supplied format sources are retained; archive formats describe only the listed container.")
    return outcome("PASS" if evidence else "FAIL", "Identify the listed file's format from a declaration, media type or recognized suffix.", formatEvidence=evidence, warnings=warnings)


def validate_rows(rows, rule, registry, **parameters):
    results = []
    for row in rows:
        values, constants = row.get("values", {}), row.get("constants", {})
        slot = parameters.get("slot", "value")
        value = values.get(slot)
        if row.get("malformed"):
            result = outcome("FAIL", "Malformed collection entry; it has not been discarded.")
        elif rule == "text":
            if parameters.get("identifier_text") and isinstance(value, int) and not isinstance(value, bool):
                namespace = namespace_name(constants.get("namespace") or values.get("scheme"), registry["identifiers"])
                if registry["identifiers"].get(namespace, {}).get("integer"):
                    value = str(value)
            result = _text(value, registry, placeholders=parameters.get("placeholders", False))
        elif rule == "identifier":
            identifier = row.get("identifier")
            if identifier is None:
                identifier = normalize_identifier(value, registry["identifiers"], namespace=constants.get("namespace"), scheme=values.get("scheme"))
            result = validate_identifier(identifier, registry["identifiers"])
        elif rule == "date":
            result = _date(value, constants.get("parser", "iso"))
        elif rule == "spatial":
            result = _spatial(values, constants, registry)
        elif rule == "temporal":
            result = _temporal(values, constants)
        elif rule == "format":
            result = _format(values, registry)
        elif rule == "label":
            code = values.get("code", values.get("name"))
            label = values.get("label") or constants.get("definitions", {}).get(str(code)) or values.get("name")
            result = _text(label, registry, placeholders=True)
            if result["status"] == "PASS" and not constants.get("definitions", {}).get(str(code)) and re.fullmatch(r"(?:v|var|variable|col|column|x)[ _-]?[0-9]+", label, re.I):
                result = outcome("FAIL", "An opaque variable code needs a documented label.")
            result["label"] = label
        else:
            raise ValueError(f"Unknown validator: {rule}.")
        results.append({**result, "key": row["key"], "paths": row.get("paths", {}), "input": values})
    return results
