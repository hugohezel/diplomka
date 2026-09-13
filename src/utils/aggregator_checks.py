"""Check whether a record's DOI is discoverable in external aggregators."""

import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPException
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode

from ..clients.http_client import fetch_json


REQUEST_TIMEOUT = 12
OPENAIRE_API = "https://api.openaire.eu/graph/v3/research-products"
OPENALEX_API = "https://api.openalex.org/works"


def find_in_openaire(doi: str) -> tuple[str | None, str]:
    """Return the matching record ID and the URL used to search for it."""
    query = urlencode({"pid": doi, "pageSize": 1})
    url = f"{OPENAIRE_API}?{query}"
    response = fetch_json(
        url,
        service="OpenAIRE",
        timeout=REQUEST_TIMEOUT,
        token=os.environ.get("OPENAIRE_ACCESS_TOKEN"),
    )
    results = response.get("results")
    if not isinstance(results, list):
        raise ValueError("OpenAIRE response does not contain a results list.")
    if not results:
        return None, url

    record = results[0]
    if not isinstance(record, dict) or not isinstance(record.get("id"), str):
        raise ValueError("OpenAIRE result does not contain a record ID.")
    if not record["id"].strip():
        raise ValueError("OpenAIRE returned an empty record ID.")
    return record["id"], url


def find_in_openalex(doi: str) -> tuple[str | None, str]:
    """Return the matching record ID and the URL used to look up its DOI."""
    url = (
        f"{OPENALEX_API}/https://doi.org/{quote(doi, safe='/')}"
        "?corpus=all&select=id,doi"
    )
    try:
        response = fetch_json(
            url,
            service="OpenAlex",
            timeout=REQUEST_TIMEOUT,
            token=os.environ.get("OPENALEX_API_KEY"),
        )
    except HTTPError as error:
        if error.code != 404:
            raise
        error.close()
        return None, url

    record_id = response.get("id")
    if not isinstance(record_id, str) or not record_id.strip():
        raise ValueError("OpenAlex response does not contain a record ID.")
    return record_id, url


def check_discoverability(
    name: str, lookup: Callable[[str], tuple[str | None, str]], doi: str | None
) -> dict[str, Any]:
    result = {
        "label": f"Discoverable in {name}",
        "doi": doi,
        "recordId": None,
        "sourceUrl": None,
        "status": "FAIL",
        "message": "No DOI is available to look up this record.",
    }
    if doi is None:
        return result

    try:
        record_id, source_url = lookup(doi)
    except HTTPError as error:
        message = f"{name} returned HTTP {error.code}; discoverability could not be checked."
        error.close()
    except (URLError, OSError, HTTPException):
        message = f"{name} is currently unavailable; discoverability could not be checked."
    except ValueError as error:
        message = str(error)
    else:
        result.update(
            recordId=record_id,
            sourceUrl=source_url,
            status="PASS" if record_id is not None else "FAIL",
            message=(
                f"Record found in {name}"
                if record_id is not None
                else f"No record found in {name} for this DOI"
            ),
        )
        return result

    # A failed request is not evidence that the record is absent.
    result.update(status="ERROR", message=message)
    return result


def evaluate_aggregators(doi: str | None) -> list[dict[str, Any]]:
    lookups = (("OpenAIRE", find_in_openaire), ("OpenAlex", find_in_openalex))
    with ThreadPoolExecutor(max_workers=len(lookups)) as executor:
        futures = [
            executor.submit(check_discoverability, name, lookup, doi)
            for name, lookup in lookups
        ]
        return [future.result() for future in futures]
