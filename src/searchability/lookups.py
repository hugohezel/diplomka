"""Session-cached authoritative lookups, separate from check pass rules."""

import json
import re
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

from ..utils.checks import plain_text
from ..utils.metadata_verification import request_public_json, resolve_public_target
from ..utils.vocabularies import FOS
from .model import outcome


_OLS_ONTOLOGIES = {"efo", "chebi", "pato", "chmo", "ncit"}


def _ols_iri(scheme, code):
    base = "http://www.ebi.ac.uk/efo/" if scheme == "efo" else "http://purl.obolibrary.org/obo/"
    return base + code


def _labels(values, language=None):
    return [{"value": value, "language": language} for value in values if plain_text(value)]


class LookupService:
    def __init__(self, registry, *, fetch=request_public_json, resolve=resolve_public_target):
        self.registry, self.fetch, self.resolve = registry, fetch, resolve
        self.cache = {}

    def lookup(self, requests, mode="entry"):
        keys = [json.dumps({"mode": mode, **{key: value for key, value in request.items() if key != "key"}}, sort_keys=True) for request in requests]
        pending = {key: request for key, request in zip(keys, requests) if key not in self.cache}
        if pending:
            with ThreadPoolExecutor(max_workers=min(8, len(pending))) as executor:
                futures = {key: executor.submit(self._lookup, request, mode) for key, request in pending.items()}
                for key, future in futures.items():
                    self.cache[key] = future.result()
        return [{**self.cache[key], "key": request.get("key", key)} for key, request in zip(keys, requests)]

    def _lookup(self, request, mode):
        try:
            return self._lookup_resource(request, mode)
        except (KeyError, TypeError, AttributeError, ValueError):
            return outcome("UNSURE", "The authoritative service returned an unsupported or malformed payload.")

    def _lookup_resource(self, request, mode):
        if mode == "target":
            url = request.get("url")
            return self.resolve(url, self.registry["retrieval"]) if url else outcome("UNSURE", "No resolver adapter is installed.")
        kind = request.get("kind")
        if kind == "definition":
            value = request.get("definitions", {}).get(str(request.get("code")))
            return outcome("PASS" if value else "FAIL", "Look up the exact documented code.", label=value)
        if kind == "identity":
            left, right, level = request["left"], request["right"], request["level"]
            if left.get("status") != "PASS" or right.get("status") != "PASS" or request.get("rightLevel") != level:
                return outcome("FAIL", "An alias cannot bridge invalid IDs or different object/version levels.")
            endpoints = {(left["namespace"], left["canonical"]), (right["namespace"], right["canonical"])}
            for alias in self.registry.get("identityAliases", []):
                pair = {(alias["left"]["namespace"], alias["left"]["value"]), (alias["right"]["namespace"], alias["right"]["value"])}
                if pair == endpoints and alias.get("level") == level and plain_text(alias.get("source")):
                    return outcome("PASS", "An authoritative same-level alias establishes identity.", sourceUrl=alias["source"])
            return outcome("FAIL", "No authoritative same-level alias establishes this equivalence.")
        if kind == "actor":
            return self._actor(request)
        if kind == "vocabulary":
            return self._vocabulary(request)
        return outcome("UNSURE", "No authoritative adapter is installed for this resource.")

    def _actor(self, request):
        namespace, identifier = request["namespace"], request["value"]
        urls = {"orcid": f"https://pub.orcid.org/v3.0/{identifier}/person",
                "gnd": f"https://lobid.org/gnd/{identifier}.json",
                "ror": f"https://api.ror.org/v2/organizations/{identifier}"}
        if namespace not in urls:
            return outcome("UNSURE", "No actor registry adapter is installed for this namespace.")
        response = deepcopy(self.fetch(urls[namespace], self.registry["retrieval"]))
        data = response.pop("data", None)
        if response["status"] != "PASS":
            return response
        if not isinstance(data, dict):
            return {**response, "status": "UNSURE", "message": "Malformed actor registry response."}
        names = []
        if namespace == "orcid":
            if "name" not in data:
                return {**response, "status": "UNSURE", "message": "The response is not an ORCID person record."}
            if data["name"] is not None and not isinstance(data["name"], dict):
                return {**response, "status": "UNSURE", "message": "Malformed ORCID name payload."}
            name = data.get("name") or {}
            given = (name.get("given-names") or {}).get("value")
            family = (name.get("family-name") or {}).get("value")
            credit = (name.get("credit-name") or {}).get("value")
            full = " ".join((given, family)) if isinstance(given, str) and given.strip() and isinstance(family, str) and family.strip() else None
            names = [credit if isinstance(credit, str) and len(credit.split()) > 1 else None, full]
            names.extend(item.get("content") for item in (data.get("other-names") or {}).get("other-name", []) if isinstance(item, dict))
        elif namespace == "gnd":
            if data.get("gndIdentifier") != identifier:
                return {**response, "status": "UNSURE", "message": "The response does not identify the requested GND entry."}
            if not isinstance(data.get("variantName", []), list):
                return {**response, "status": "UNSURE", "message": "Malformed GND name variants."}
            names = [data.get("preferredName"), *data.get("variantName", [])]
        else:
            returned = str(data.get("id", "")).rstrip("/").rsplit("/", 1)[-1]
            if returned != identifier:
                return {**response, "status": "UNSURE", "message": "The response does not identify the requested ROR entry."}
            names = [item.get("value") for item in data.get("names", []) if isinstance(item, dict)]
        return {**response, "message": "Authoritative actor entry exists; identity compatibility is checked separately.",
                "namespace": namespace, "identifier": identifier, "names": [name for name in names if plain_text(name)]}

    def _vocabulary(self, request):
        identifier, declared = plain_text(request.get("id")), plain_text(request.get("scheme")).casefold()
        vocabularies = self.registry["vocabularies"]
        selected = next((name for name, rule in vocabularies.items() if declared in rule["aliases"]), None)
        if selected is None:
            selected = next((name for name, rule in vocabularies.items() if re.fullmatch(rule["pattern"], identifier, re.I)), None)
        if not selected:
            return outcome("UNSURE", "The controlled vocabulary has no installed shared adapter.")
        code = identifier.rstrip("/").rsplit("/", 1)[-1]
        if selected == "fos":
            label = FOS.get(identifier)
            return outcome("PASS" if label else "FAIL", "Look up the OECD FOS 2007 snapshot.",
                           vocabulary=selected, labels=_labels([label], "en"), completeLabels=True, languages=["en"])
        patterns = {"lcsh": r"sh[0-9]+", "mesh": r"[DC][0-9]{6,9}", "gnd": r"[0-9]+(?:-[0-9X])?",
                    "ncbi_taxonomy": r"[1-9][0-9]*"}
        if selected in _OLS_ONTOLOGIES:
            code = code.replace(":", "_").upper()
            pattern = selected.upper() + (r"_C[0-9]+" if selected == "ncit" else r"_[0-9]+")
        else:
            pattern = patterns[selected]
        if not re.fullmatch(pattern, code, re.I):
            return outcome("FAIL", "The concept identifier contradicts its vocabulary syntax.")
        if selected == "mesh":
            code = code.upper()
        urls = {
            "lcsh": f"https://id.loc.gov/authorities/subjects/{code}.json",
            "mesh": f"https://id.nlm.nih.gov/mesh/{code}.json",
            "gnd": f"https://lobid.org/gnd/{code}.json",
            "ncbi_taxonomy": f"https://www.ebi.ac.uk/ena/taxonomy/rest/tax-id/{code}",
        }
        if selected in _OLS_ONTOLOGIES:
            urls[selected] = f"https://www.ebi.ac.uk/ols4/api/ontologies/{selected}/terms?" + urlencode({"iri": _ols_iri(selected, code)})
        response = deepcopy(self.fetch(urls[selected], self.registry["retrieval"]))
        data = response.pop("data", None)
        if response["status"] != "PASS":
            return response
        labels, complete, exists = self._concept_payload(selected, code, data)
        if exists is None:
            return {**response, "status": "UNSURE", "message": "The registry response does not identify the requested concept."}
        return {**response, "status": "PASS" if exists else "FAIL", "vocabulary": selected,
                "message": "Retrieve the exact concept and applicable labels.", "labels": labels,
                "completeLabels": complete, "languages": sorted({label["language"] for label in labels if label.get("language")})}

    @staticmethod
    def _concept_payload(scheme, code, data):
        if scheme == "ncbi_taxonomy":
            if isinstance(data, list):
                if not data:
                    return [], True, False
                data = data[0] if len(data) == 1 else None
            if isinstance(data, dict) and str(data.get("taxId")) == code and plain_text(data.get("scientificName")):
                return _labels([data["scientificName"], data.get("commonName")]), False, True
        if scheme in _OLS_ONTOLOGIES and isinstance(data, dict):
            if data.get("page", {}).get("totalElements") == 0:
                return [], True, False
            terms = data.get("_embedded", {}).get("terms", [])
            term = next((term for term in terms if isinstance(term, dict) and term.get("iri") == _ols_iri(scheme, code)), None)
            if term:
                synonyms = term.get("synonyms")
                if not plain_text(term.get("label")) or (synonyms is not None and not isinstance(synonyms, list)):
                    return [], False, None
                return _labels([term["label"], *(synonyms or [])], "en"), isinstance(synonyms, list), True
        if scheme == "gnd" and isinstance(data, dict) and data.get("gndIdentifier") == code:
            if not isinstance(data.get("variantName", []), list):
                return [], False, None
            return _labels([data.get("preferredName"), *data.get("variantName", [])]), "variantName" in data, True
        if scheme == "mesh" and isinstance(data, dict):
            entry = data.get(f"http://id.nlm.nih.gov/mesh/{code}")
            if isinstance(entry, dict):
                labels = []
                for predicate in ("http://www.w3.org/2000/01/rdf-schema#label", "http://www.w3.org/2004/02/skos/core#prefLabel", "http://www.w3.org/2004/02/skos/core#altLabel"):
                    labels.extend({"value": item["value"], "language": item.get("lang")} for item in entry.get(predicate, []) if isinstance(item, dict) and isinstance(item.get("value"), str))
                return labels, False, True
        if scheme == "lcsh" and isinstance(data, list):
            uri = f"http://id.loc.gov/authorities/subjects/{code}"
            main = next((item for item in data if isinstance(item, dict) and item.get("@id") == uri), None)
            if main:
                variants = {item["@id"] for item in main.get("http://www.loc.gov/mads/rdf/v1#hasVariant", []) if isinstance(item, dict) and "@id" in item}
                accepted = {uri, *variants}
                found, labels = set(), []
                predicates = ("http://www.loc.gov/mads/rdf/v1#authoritativeLabel", "http://www.loc.gov/mads/rdf/v1#variantLabel", "http://www.w3.org/2004/02/skos/core#prefLabel", "http://www.w3.org/2004/02/skos/core#altLabel")
                for item in data:
                    if isinstance(item, dict) and item.get("@id") in accepted:
                        found.add(item["@id"])
                        for predicate in predicates:
                            labels.extend({"value": label["@value"], "language": label.get("@language")} for label in item.get(predicate, []) if isinstance(label, dict) and isinstance(label.get("@value"), str))
                return labels, accepted <= found, True
        return [], False, None
