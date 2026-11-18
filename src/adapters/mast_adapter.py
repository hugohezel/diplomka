"""Retrieve one MAST CAOM observation and its paginated product metadata."""

import json
import re
from collections.abc import Mapping
from http.client import HTTPException
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlencode

from ..clients.http_client import fetch_json
from ..clients.repository_client import evaluation_response
from ..utils.references import parse_url
from ..utils.translation_checks import EvaluationContext, evaluate_translation, load_translation


REPOSITORY = "mast"
DISPLAY_NAME = "MAST"
HOSTS = {"mast.stsci.edu", "archive.stsci.edu"}
API_BASE_URL = "https://mast.stsci.edu/api/v0/invoke"
CHECKS_PATH = Path(__file__).with_name("mast_checks.json")
PRODUCT_PAGE_SIZE = 1000
MAX_PRODUCT_PAGES = 5
_NUMBER = re.compile(r"[1-9][0-9]*")
_ACCESSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,199}")
_COLLECTION = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,39}")


def _exact_filters(filters):
    if not isinstance(filters, list) or not 1 <= len(filters) <= 2:
        return None
    result = {}
    for item in filters:
        if not isinstance(item, Mapping) or item.get("freeText"):
            return None
        name, values = item.get("paramName"), item.get("values")
        if name not in {"obsid", "obs_id", "obs_collection"} or name in result:
            return None
        if not isinstance(values, list) or len(values) != 1:
            return None
        value = values[0]
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            return None
        value = str(value)
        pattern = {"obsid": _NUMBER, "obs_id": _ACCESSION, "obs_collection": _COLLECTION}[name]
        if not pattern.fullmatch(value):
            return None
        result[name] = value
    if ("obsid" in result) == ("obs_id" in result):
        return None
    return result


def parse_reference(reference, *, allow_bare=True):
    """Accept exact observation identifiers and exact CAOM API/Portal links."""
    reference = reference.strip()
    prefixed = reference.lower().startswith("mast:")
    candidate = reference[5:] if prefixed else reference
    if _NUMBER.fullmatch(candidate) and (prefixed or allow_bare):
        return {"obsid": candidate}
    if "/" in candidate:
        collection, accession = candidate.split("/", 1)
        if _COLLECTION.fullmatch(collection) and _ACCESSION.fullmatch(accession):
            return {"obs_collection": collection, "obs_id": accession}
    if (prefixed or allow_bare) and _ACCESSION.fullmatch(candidate):
        return {"obs_id": candidate}
    if reference.lower().startswith(tuple(host + "/" for host in HOSTS)):
        reference = "https://" + reference
    url = parse_url(reference)
    if url is None or url.hostname != "mast.stsci.edu":
        return None
    query = parse_qs(url.query)
    try:
        if url.path.rstrip("/") == "/api/v0/invoke":
            request = json.loads(query["request"][0])
            if not isinstance(request, Mapping) or request.get("service") != "Mast.Caom.Filtered":
                return None
            params = request.get("params")
            return _exact_filters(params.get("filters")) if isinstance(params, Mapping) else None
        if url.path == "/portal/Mashup/Clients/Mast/Portal.html":
            request = json.loads(query["searchQuery"][0])
            if isinstance(request, Mapping) and request.get("service") == "CAOMFILTERED":
                return _exact_filters(request.get("inputText"))
    except (KeyError, IndexError, ValueError, TypeError):
        pass
    return None


def can_handle(reference):
    return parse_reference(reference, allow_bare=False) is not None


def _invoke(request):
    response = fetch_json(API_BASE_URL, service=DISPLAY_NAME,
                          form={"request": json.dumps(request, separators=(",", ":"))})
    if response.get("status") != "COMPLETE":
        raise ValueError(f"MAST query is not complete: {response.get('status', 'missing status')}.")
    if not isinstance(response.get("data"), list) or any(not isinstance(row, Mapping) for row in response["data"]):
        raise ValueError("MAST did not return a metadata row list.")
    return response


def _observation(response, filters=None):
    if not isinstance(response, Mapping) or response.get("status") != "COMPLETE":
        raise ValueError("MAST observation metadata are incomplete.")
    rows = response.get("data")
    paging = response.get("paging")
    if (not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], Mapping)
            or not isinstance(paging, Mapping) or paging.get("rowsFiltered") != 1):
        raise ValueError("No unique MAST observation was found; enter its numeric obsid or collection/obs_id.")
    row = rows[0]
    obsid = row.get("obsid")
    if isinstance(obsid, bool) or not isinstance(obsid, (str, int)) or not _NUMBER.fullmatch(str(obsid)):
        raise ValueError("MAST returned an invalid observation Product Group ID.")
    for name, expected in (filters or {}).items():
        if str(row.get(name, "")).casefold() != expected.casefold():
            raise ValueError("Retrieved MAST metadata belong to a different observation.")
    return row


def _products(obsid):
    pages = []
    for page in range(1, MAX_PRODUCT_PAGES + 1):
        try:
            response = _invoke({"service": "Mast.Caom.Products", "params": {"obsid": obsid},
                                "format": "json", "pagesize": PRODUCT_PAGE_SIZE, "page": page})
        except (URLError, TimeoutError, ConnectionError, HTTPException, ValueError) as error:
            return pages, False, f"Product metadata retrieval is incomplete ({type(error).__name__})."
        pages.append(response)
        if any(str(row.get("parent_obsid") or row.get("obsID")) != obsid for row in response["data"]):
            return pages, False, "Product metadata are not consistently bound to the requested observation."
        paging = response.get("paging", {})
        total = paging.get("rowsFiltered") if isinstance(paging, Mapping) else None
        current = paging.get("page") if isinstance(paging, Mapping) else None
        if not isinstance(total, int) or isinstance(total, bool) or total < 0 or current != page:
            return pages, False, "MAST product pagination could not be verified."
        retrieved = sum(len(item["data"]) for item in pages)
        if retrieved >= total:
            return pages, retrieved == total, None if retrieved == total else "MAST product counts disagree."
        if not response["data"]:
            return pages, False, "MAST returned an empty intermediate product page."
    return pages, False, f"Product metadata were limited to {MAX_PRODUCT_PAGES} pages."


def evaluate(repository_response, *, reference=None, source_url=None, lookup=None, semantic=None, on_event=None):
    filters = parse_reference(reference) if reference else None
    if reference and filters is None:
        raise ValueError("The input does not identify one MAST observation.")
    row = _observation(repository_response.get("observation"), filters)
    profile = load_translation(CHECKS_PATH)
    # Completeness belongs to the product inventory, not to the retrieved observation.
    for binding in profile["bindings"]["files"]:
        binding["complete"] = repository_response.get("productsComplete") is True
    context = EvaluationContext(
        reference=reference, expected_record_id=str(row["obsid"]) if reference else None,
        expected_namespace="mast_observation", requested_level="object", source_url=source_url,
    )
    return evaluate_translation(repository_response, profile, context=context, lookup=lookup, semantic=semantic, on_event=on_event)


def fetch(reference, *, requested_reference=None, on_event=None):
    filters = parse_reference(reference)
    if filters is None:
        raise ValueError("Enter a MAST obsid, collection/obs_id, or an exact observation query URL.")
    request = {"service": "Mast.Caom.Filtered", "format": "json", "pagesize": 2, "page": 1,
               "params": {"columns": "*", "filters": [
                   {"paramName": name, "values": [value]} for name, value in filters.items()]}}
    observation = _invoke(request)
    row = _observation(observation, filters)
    products, complete, warning = _products(str(row["obsid"]))
    response = {"observation": observation, "products": products, "productsComplete": complete}
    if warning:
        response["productsWarning"] = warning
    source_url = API_BASE_URL + "?" + urlencode({"request": json.dumps(request, separators=(",", ":"))})
    checks = evaluate(response, reference=requested_reference or reference, source_url=source_url, on_event=on_event)
    # Observation groups do not inherit the DOI of a curated multi-observation collection.
    result = evaluation_response(repository=REPOSITORY, display_name=DISPLAY_NAME, source_url=source_url,
                                 repository_response=response, record_checks=checks, doi=None, on_event=on_event)
    result["requestedReference"] = requested_reference or reference
    return result
