"""Bounded resolver and controlled-vocabulary checks, isolated from local rules."""

import ipaddress
import json
import re
import socket
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from http.client import HTTPException
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .checks import (
    CheckResult, all_pass_status, any_pass_status, normalize_text, plain_text,
)
from .references import USER_AGENT, parse_url
from .generic_metadata_identity import resolver_target_status


REQUEST_TIMEOUT = 8
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_CONCURRENT_REQUESTS = 8
RESOLVER_HOSTS = {"doi.org", "dx.doi.org", "hdl.handle.net", "n2t.net"}


@dataclass(frozen=True)
class RequestTarget:
    url: str
    resolve: bool


@dataclass
class PendingVerification:
    entry: CheckResult
    spec: Mapping[str, Any]
    target: RequestTarget


def _require_public_url(url: str) -> None:
    """Metadata identifiers may only resolve to public HTTP(S) destinations."""
    parsed = parse_url(url)
    if parsed is None or any(ord(char) < 32 for char in url):
        raise ValueError("Invalid resolver target URL.")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = socket.getaddrinfo(
        parsed.hostname, port, type=socket.SOCK_STREAM
    )
    if not addresses or any(
        not ipaddress.ip_address(address[4][0]).is_global
        for address in addresses
    ):
        raise ValueError("Resolver target is not a public address.")


class _PublicRedirects(HTTPRedirectHandler):
    max_redirections = 5

    def __init__(self):
        super().__init__()
        self.chain: list[dict[str, Any]] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _require_public_url(newurl)
        self.chain.append({"from": req.full_url, "status": code, "to": newurl})
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _resolver_result(url: str, target: str) -> CheckResult:
    initial_url, target_url = parse_url(url), parse_url(target)
    stays_at_resolver = (
        initial_url is not None
        and initial_url.hostname in RESOLVER_HOSTS
        and (target_url is None or target_url.hostname in RESOLVER_HOSTS)
    )
    return {
        "status": "UNSURE" if stays_at_resolver else "PASS",
        "message": (
            "Resolver did not expose a resource target." if stays_at_resolver
            else "Resolver path reached a successful target."
        ),
        "targetUrl": target,
    }


def _request(url: str, *, resolve: bool) -> CheckResult:
    try:
        _require_public_url(url)
        redirects = _PublicRedirects()
        opener = build_opener(redirects)
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "*/*" if resolve else "application/json",
        }
        # A streamed GET handles resolvers that do not implement HEAD. For M1,
        # close after the response headers; no landing-page body is downloaded.
        request = Request(url, headers=headers)
        with opener.open(request, timeout=REQUEST_TIMEOUT) as response:
            target = response.geturl()
            if resolve:
                return {
                    **_resolver_result(url, target), "redirectChain": redirects.chain,
                    "checkedAt": datetime.now(timezone.utc).isoformat(),
                }

            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError("Registry response exceeded the size limit.")
            return {
                "status": "PASS", "data": json.loads(raw), "targetUrl": target,
            }
    except HTTPError as error:
        not_found = error.code in {404, 410}
        message = (
            f"HTTP {error.code}: target not found." if not_found
            else f"HTTP {error.code}: verification could not be completed."
        )
        error.close()
        return {"status": "FAIL" if not_found else "UNSURE", "message": message}
    except (URLError, OSError, HTTPException, ValueError, UnicodeDecodeError) as error:
        return {
            "status": "UNSURE", "message": f"Verification unavailable: {error}",
        }


def _lookup_url(spec: Mapping[str, Any]) -> str | None:
    if spec["kind"] != "vocabulary-term":
        return spec.get("url")

    scheme, identifier = spec["scheme"], spec["id"]
    if scheme == "efo":
        if re.fullmatch(r"EFO[:_][0-9]+", identifier, re.I):
            identifier = (
                "http://www.ebi.ac.uk/efo/"
                + identifier.upper().replace(":", "_")
            )
        if re.fullmatch(
            r"https?://www\.ebi\.ac\.uk/efo/EFO_[0-9]+", identifier
        ):
            iri = identifier.replace("https://", "http://", 1)
            query = urlencode({"iri": iri})
            return (
                "https://www.ebi.ac.uk/ols4/api/ontologies/efo/terms?" + query
            )
    elif scheme == "mesh":
        code = identifier.rsplit("/", 1)[-1]
        valid_code = re.fullmatch(r"[DC][0-9]{6,9}", code)
        valid_uri = re.fullmatch(
            r"https?://id\.nlm\.nih\.gov/mesh/[DC][0-9]{6,9}", identifier
        )
        if valid_code and (identifier == code or valid_uri):
            return f"https://id.nlm.nih.gov/mesh/{code}.json"
    elif scheme == "gnd":
        code = identifier.rsplit("/", 1)[-1]
        valid_code = re.fullmatch(r"[0-9]+(?:-[0-9X])?", code)
        valid_uri = re.fullmatch(
            r"https?://d-nb\.info/gnd/[0-9]+(?:-[0-9X])?", identifier
        )
        if valid_code and (identifier == code or valid_uri):
            return f"https://lobid.org/gnd/{code}.json"
    return None


def _registry_result(valid: bool, target_url: str | None) -> CheckResult:
    return {
        "status": "PASS" if valid else "FAIL",
        "message": (
            "Identifier found in the controlled registry." if valid
            else "Identifier not found in the controlled registry."
        ),
        "targetUrl": target_url,
    }


def _verify_ror(
    spec: Mapping[str, Any], data: Any, target_url: str | None
) -> CheckResult:
    if not isinstance(data, Mapping) or not isinstance(data.get("id"), str):
        return {
            "status": "UNSURE", "message": "Malformed ROR registry response.",
        }
    return _registry_result(data["id"] == spec["id"], target_url)


def _verify_orcid_name(
    spec: Mapping[str, Any], data: Any, target_url: str | None,
) -> CheckResult:
    result: CheckResult = {"status": "UNSURE", "targetUrl": target_url}
    if not isinstance(data, Mapping) or "name" not in data:
        return {**result, "message": "Malformed ORCID person response."}

    name = data["name"]
    if name is None:
        return {**result, "message": "ORCID does not expose a public family name."}
    if not isinstance(name, Mapping):
        return {**result, "message": "Malformed ORCID name response."}
    family_name = name.get("family-name")
    if family_name is not None and not isinstance(family_name, Mapping):
        return {**result, "message": "Malformed ORCID family-name response."}
    surname = plain_text(family_name.get("value")) if family_name else ""
    result["orcidSurname"] = surname or None
    if not surname:
        return {**result, "message": "ORCID does not expose a public family name."}

    normalized_surname = normalize_text(surname)
    metadata_surname = spec.get("surname")
    if metadata_surname is None:
        # Compare whole trailing words, so a compound family name is preserved
        # and Smith cannot match Smithson. Do not compare given-name initials.
        name_parts = plain_text(spec.get("name")).split()
        surname_length = len(normalized_surname.split())
        metadata_surname = " ".join(name_parts[-surname_length:])
    result["metadataSurname"] = metadata_surname
    if not plain_text(metadata_surname):
        return {**result, "message": "No metadata surname is available to compare."}

    matches = normalize_text(metadata_surname) == normalized_surname
    result.update(
        status="PASS" if matches else "FAIL",
        message=(
            "Metadata surname matches the public ORCID family name." if matches
            else "Metadata surname differs from the public ORCID family name."
        ),
    )
    return result


def _verify_figshare_category(
    spec: Mapping[str, Any], data: Any, target_url: str | None
) -> CheckResult:
    if not isinstance(data, list) or any(
        not isinstance(entry, Mapping) or "id" not in entry for entry in data
    ):
        return {
            "status": "UNSURE",
            "message": "Malformed Figshare categories response.",
        }

    if spec.get("id") is not None:
        valid = any(str(entry["id"]) == str(spec["id"]) for entry in data)
    else:
        title = normalize_text(spec.get("title"))
        valid = any(normalize_text(entry.get("title")) == title for entry in data)
    return _registry_result(valid, target_url)


def _verify_efo(
    identifier: str, data: Mapping[str, Any], target_url: str | None
) -> CheckResult:
    page = data.get("page")
    if isinstance(page, Mapping) and page.get("totalElements") == 0:
        return {"status": "FAIL", "message": "Identifier not found in EFO."}

    embedded = data.get("_embedded")
    if not isinstance(embedded, Mapping) or not isinstance(
        embedded.get("terms"), list
    ):
        return {
            "status": "UNSURE", "message": "Malformed EFO lookup response.",
        }
    wanted = identifier.rsplit("/", 1)[-1].replace(":", "_").upper()
    valid = any(
        isinstance(term, Mapping)
        and isinstance(term.get("iri"), str)
        and term["iri"].rsplit("/", 1)[-1].upper() == wanted
        for term in embedded["terms"]
    )
    return _registry_result(valid, target_url)


def _verify_gnd(
    identifier: str, data: Mapping[str, Any], target_url: str | None
) -> CheckResult:
    if "gndIdentifier" not in data:
        return {
            "status": "UNSURE", "message": "Malformed GND lookup response.",
        }
    valid = data["gndIdentifier"] == identifier.rsplit("/", 1)[-1]
    return _registry_result(valid, target_url)


def _verify_mesh(
    identifier: str, data: Mapping[str, Any], target_url: str | None
) -> CheckResult:
    # NLM's .json endpoint serves RDF/JSON, keyed by subject URI.
    code = identifier.rsplit("/", 1)[-1]
    subject_uri = f"http://id.nlm.nih.gov/mesh/{code}"
    subject = data.get(subject_uri)
    if isinstance(subject, Mapping) and subject:
        valid = True
    elif "@id" in data:
        valid = data["@id"] in {
            subject_uri, f"https://id.nlm.nih.gov/mesh/{code}",
        }
    else:
        return {
            "status": "UNSURE", "message": "Malformed MeSH lookup response.",
        }
    return _registry_result(valid, target_url)


def _verify_vocabulary(
    spec: Mapping[str, Any], data: Any, target_url: str | None
) -> CheckResult:
    if not isinstance(data, Mapping):
        return {"status": "UNSURE", "message": "Malformed vocabulary response."}

    verifier = {
        "efo": _verify_efo,
        "gnd": _verify_gnd,
        "mesh": _verify_mesh,
    }.get(spec["scheme"])
    if verifier is None:
        return _registry_result(False, target_url)
    return verifier(spec["id"], data, target_url)


def _verify_payload(
    spec: Mapping[str, Any], response: CheckResult
) -> CheckResult:
    if response["status"] != "PASS":
        return {key: value for key, value in response.items() if key != "data"}
    if spec["kind"] == "resolve":
        result = {key: value for key, value in response.items() if key != "data"}
        if "bindingStatus" in spec:
            status = resolver_target_status(dict(spec), response.get("targetUrl"))
            result.update(
                status=status,
                message=("Resolver target is bound to the evaluated dataset/version."
                         if status == "PASS" else
                         "Resolver target contradicts the dataset or selected version."
                         if status == "FAIL" else
                         "HTTP success does not establish binding to this dataset/version."),
            )
        return result

    verifier = {
        "orcid-name": _verify_orcid_name,
        "ror": _verify_ror,
        "figshare-category": _verify_figshare_category,
        "vocabulary-term": _verify_vocabulary,
    }.get(spec["kind"])
    target_url = response.get("targetUrl")
    if verifier is None:
        return _registry_result(False, target_url)
    result = verifier(spec, response.get("data"), target_url)
    if result["status"] == "PASS" and spec.get("matchLabel"):
        return _verify_label_alignment(spec, response.get("data"), target_url)
    return result


def _verify_label_alignment(
    spec: Mapping[str, Any], data: Any, target_url: str | None,
) -> CheckResult:
    """Verify labels separately from membership; neither proves relevance."""
    labels: list[Any] = []
    if spec["kind"] == "figshare-category":
        labels = [entry.get("title") for entry in data
                  if str(entry.get("id")) == str(spec.get("id"))]
        if spec.get("id") is None:
            labels = [entry.get("title") for entry in data]
    elif spec.get("scheme") == "efo":
        wanted = spec["id"].rsplit("/", 1)[-1].replace(":", "_").upper()
        for term in data.get("_embedded", {}).get("terms", []):
            if isinstance(term, Mapping) and str(term.get("iri", "")).rsplit("/", 1)[-1].upper() == wanted:
                labels.append(term.get("label"))
                synonyms = term.get("synonyms")
                if isinstance(synonyms, list):
                    labels.extend(synonyms)
    elif spec.get("scheme") == "gnd":
        labels = [data.get("preferredName")]
        variants = data.get("variantName")
        if isinstance(variants, list):
            labels.extend(variants)
    elif spec.get("scheme") == "mesh":
        subject = data.get("http://id.nlm.nih.gov/mesh/" + spec["id"].rsplit("/", 1)[-1], {})
        for predicate in (
            "http://www.w3.org/2000/01/rdf-schema#label",
            "http://www.w3.org/2004/02/skos/core#prefLabel",
            "http://www.w3.org/2004/02/skos/core#altLabel",
        ):
            values = subject.get(predicate, []) if isinstance(subject, Mapping) else []
            if isinstance(values, list):
                labels.extend(value.get("value") for value in values if isinstance(value, Mapping))
    normalized = {normalize_text(label) for label in labels if plain_text(label)}
    label = normalize_text(spec.get("label"))
    status = "PASS" if label in normalized else "FAIL" if label and normalized else "UNSURE"
    if status == "FAIL" and spec.get("scheme") in {"mesh", "gnd"}:
        # These payloads may expose only a preferred label. Without collecting
        # linked/variant terms, an unmatched alias is not a proven contradiction.
        status = "UNSURE"
    return {"status": status, "targetUrl": target_url, "registryLabels": labels,
            "message": "Compare the supplied label with verified preferred/alternative labels."}


def _pending_verifications(
    checks: list[CheckResult],
) -> list[PendingVerification]:
    pending = []
    for check in checks:
        for entry in [check, *check.get("evidence", [])]:
            if not isinstance(entry, dict) or "verification" not in entry:
                continue
            spec = entry.pop("verification")
            url = _lookup_url(spec)
            if url:
                entry["sourceUrl"] = url
                target = RequestTarget(url, resolve=spec["kind"] == "resolve")
                pending.append(PendingVerification(entry, spec, target))
            else:
                entry.update(
                    status="FAIL",
                    message="Invalid identifier for the selected vocabulary.",
                )
    return pending


def _fetch_verifications(
    pending: list[PendingVerification],
) -> dict[RequestTarget, CheckResult]:
    targets = dict.fromkeys(item.target for item in pending)
    if not targets:
        return {}

    worker_count = min(MAX_CONCURRENT_REQUESTS, len(targets))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            target: executor.submit(
                _request, target.url, resolve=target.resolve
            )
            for target in targets
        }
        return {target: future.result() for target, future in futures.items()}


def _refresh_check_status(check: CheckResult) -> None:
    evidence = check.get("evidence")
    if check.get("evidenceAggregation") == "all" and evidence:
        check["status"] = all_pass_status(entry["status"] for entry in evidence)
    elif check.get("group") in {"M5", "M6", "M7"} and evidence:
        statuses = (entry["status"] for entry in evidence)
        if check["group"] == "M5":
            check["status"] = any_pass_status(statuses)
        elif (
            check["group"] == "M7" and check["testId"] == "Test-02"
        ) or (
            check["group"] == "M6" and check["testId"] == "Test-02-01"
        ):
            check["status"] = all_pass_status(statuses)
    if "maxPoints" in check:
        check["points"] = check["maxPoints"] if check["status"] == "PASS" else 0


def verify_metadata_checks(checks: list[CheckResult]) -> list[CheckResult]:
    """Complete queued lookups, fetching each distinct URL only once per record."""
    checks = deepcopy(checks)
    pending = _pending_verifications(checks)
    responses = _fetch_verifications(pending)
    for item in pending:
        item.entry.update(_verify_payload(item.spec, responses[item.target]))
    for check in checks:
        _refresh_check_status(check)
    return checks
