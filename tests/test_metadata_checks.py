"""Regression coverage for the legacy M evaluator retained by PDB.

Generic adapters now use G01–G10; their public behavior is tested separately in
test_generic_metadata_checks.py. These fixtures exercise the shared legacy rules.
"""

import copy
import json
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from src.adapters import dryad_adapter, figshare_adapter, zenodo_adapter
from src.clients.repository_client import fetch_and_evaluate
from src.utils.checks import evaluate_rules
from src.utils.metadata_config import PROFILES
from src.utils.metadata_checks import evaluate_metadata
from src.utils.metadata_dates import parse_date
from src.utils.metadata_identifiers import identifier_syntax, ror_id, valid_orcid
from src.utils.metadata_verification import (
    _lookup_url,
    _request,
    _require_public_url,
    _verify_payload,
    verify_metadata_checks,
)


class LegacyMetadataAdapter:
    """Exercise the legacy evaluator with its original native-field fixtures."""

    def __init__(self, adapter):
        self.REPOSITORY = adapter.REPOSITORY
        self.RULES = adapter.RULES

    def evaluate(self, source):
        return evaluate_metadata(source, self.REPOSITORY, self.RULES)


zenodo_adapter = LegacyMetadataAdapter(zenodo_adapter)
dryad_adapter = LegacyMetadataAdapter(dryad_adapter)
figshare_adapter = LegacyMetadataAdapter(figshare_adapter)


def zenodo(**metadata):
    return {
        "id": 123,
        "doi": "10.5281/zenodo.123",
        "conceptdoi": "10.5281/zenodo.100",
        "metadata": {
            "title": "Bird observations in Slovakia",
            "description": "<p>Counts of birds at monitoring sites.</p>",
            "resource_type": {"type": "dataset"},
            "publication_date": "2024-01-01",
            "creators": [{
                "name": "Bird Monitoring Team",
                "orcid": "0000-0002-1825-0097",
                "affiliation": "University",
            }],
            "keywords": ["birds"],
            **metadata,
        },
    }


def check(checks, group, test):
    return next(
        item for item in checks
        if item.get("group") == group and item["testId"] == test
    )


class IdentifierChecks(unittest.TestCase):
    def test_record_dataset_and_version_identifiers_are_distinct(self):
        checks = zenodo_adapter.evaluate(zenodo())
        self.assertEqual(check(checks, "M1", "Test-01")["value"], 123)
        self.assertEqual(check(checks, "M1", "Test-02")["value"], "10.5281/zenodo.100")
        self.assertEqual(check(checks, "M1", "Test-03")["value"], "10.5281/zenodo.123")
        self.assertEqual(check(checks, "M1", "Test-01-01")["points"], 1)
        self.assertEqual(check(checks, "M1", "Test-03-01")["kind"], "bonus")

    def test_syntax_must_validate_not_only_be_present(self):
        record = zenodo()
        record.update(doi="doi:broken", conceptdoi="something", id=True)
        checks = zenodo_adapter.evaluate(record)
        self.assertEqual(check(checks, "M1", "Test-02")["status"], "PASS")
        for test in ("Test-01-01", "Test-02-01", "Test-03-01"):
            self.assertEqual(check(checks, "M1", test)["status"], "FAIL")

    def test_figshare_version_doi_is_not_used_as_parent_doi(self):
        record = {"id": 123, "doi": "10.6084/m9.figshare.123.V2"}
        checks = figshare_adapter.evaluate(record)
        self.assertEqual(check(checks, "M1", "Test-02")["value"], "10.6084/m9.figshare.123")
        self.assertEqual(check(checks, "M1", "Test-03")["value"], record["doi"])

    def test_numeric_version_is_not_a_version_identifier(self):
        cases = [
            (dryad_adapter, {"id": 1, "versionNumber": 3}),
            (figshare_adapter, {
                "id": 1, "version": 3, "doi": "10.1234/example",
            }),
        ]
        for adapter, record in cases:
            with self.subTest(repository=adapter.REPOSITORY):
                checks = adapter.evaluate(record)
                self.assertEqual(check(checks, "M1", "Test-03")["status"], "FAIL")
                self.assertTrue(any(item["label"] == "Version" for item in checks))

    def test_identifier_schemes_and_missing_resolver(self):
        cases = [
            ("10.1234/abc", "DOI", True),
            ("https://doi.org/10.1234%2Fabc", "DOI", True),
            ("https://dx.doi.org/broken", "DOI", False),
            ("hdl:12345/data", "Handle", True),
            ("HDL:12345/data", "Handle", True),
            ("https://hdl.handle.net/broken", "Handle", False),
            ("ark:/12345/item", "ARK", True),
            ("ark:/bad/item", "ARK", False),
            ("urn:uuid:12345678-1234-1234-1234-123456789abc", "URN", True),
            ("urn:uuid:bad", "URN", False),
            ("URN:UUID:12345678-1234-1234-1234-123456789abc", "URN", True),
            ("https://example.org/item", "URL", True),
            ("HTTPS://example.org/item", "URL", True),
            ("https://user:secret@example.org/item", None, False),
        ]
        for value, scheme, valid in cases:
            with self.subTest(value=value):
                actual = identifier_syntax(value)
                self.assertEqual(actual[:2], (scheme, valid))
        record = {"id": 1, "identifier": "urn:uuid:12345678-1234-1234-1234-123456789abc"}
        result = check(dryad_adapter.evaluate(record), "M1", "Test-02-02")
        self.assertEqual(result["status"], "UNSURE")
        self.assertEqual(result["points"], 0)


class TextChecks(unittest.TestCase):
    def test_title_and_description_require_text(self):
        for value in (None, "", " \u00a0 ", 0, False, ["text"], {"text": "text"}):
            with self.subTest(value=value):
                checks = zenodo_adapter.evaluate(zenodo(title=value, description=value))
                self.assertEqual(check(checks, "M2", "Test-01")["status"], "FAIL")
                self.assertEqual(check(checks, "M3", "Test-01")["status"], "FAIL")

    def test_html_without_text_is_empty(self):
        checks = zenodo_adapter.evaluate(zenodo(description="<p>&nbsp;<br></p>"))
        self.assertEqual(check(checks, "M3", "Test-01")["status"], "FAIL")

    def test_obvious_template_fails_but_quality_is_not_inferred(self):
        for title in ("Untitled", "Insert dataset title here", "[Title]", "test dataset 123"):
            result = check(zenodo_adapter.evaluate(zenodo(title=title)), "M2", "Test-02")
            self.assertEqual(result["status"], "FAIL")
        result = check(zenodo_adapter.evaluate(zenodo()), "M2", "Test-02")
        self.assertEqual(result["status"], "UNSURE")

    def test_identical_description_is_warning_after_html_and_unicode_normalization(self):
        checks = zenodo_adapter.evaluate(zenodo(
            title="BIRD Counts", description="<p>ｂｉｒｄ</p><p>counts</p>",
        ))
        self.assertEqual(check(checks, "M3", "Test-03")["status"], "WARNING")
        self.assertEqual(check(checks, "M3", "Test-01")["points"], 1)

    def test_semantic_description_and_keyword_checks_are_omitted(self):
        checks = zenodo_adapter.evaluate(zenodo())
        self.assertFalse(any(
            item.get("group") == "M3" and item["testId"].startswith("Test-02")
            for item in checks
        ))
        self.assertFalse(any(
            item.get("group") == "M4" and item["testId"] == "Test-03"
            for item in checks
        ))

    def test_keyword_normalization_presence_and_duplicates(self):
        checks = zenodo_adapter.evaluate(zenodo(keywords=[
            "", " \u00a0", "Birds", " ｂｉｒｄｓ ", "cafe\u0301", "CAFÉ", 0, None,
        ]))
        self.assertEqual(check(checks, "M4", "Test-01")["status"], "PASS")
        duplicates = check(checks, "M4", "Test-02")
        self.assertEqual(duplicates["status"], "WARNING")
        self.assertEqual(duplicates["evidence"], ["birds", "café"])


class CreatorsAndOrganizations(unittest.TestCase):
    def test_named_group_and_partial_person_name_satisfy_presence(self):
        for author in (
            {"name": "Research Consortium"},
            {"firstName": "Plato"},
            {"lastName": "Research Group"},
        ):
            checks = dryad_adapter.evaluate({"id": 1, "authors": [None, author]})
            self.assertEqual(check(checks, "M6", "Test-01")["status"], "PASS")

    def test_orcid_checksum_and_uri(self):
        for value in (
            "0000-0002-1825-0097",
            "https://orcid.org/0000-0002-1825-0097",
            "0000-0002-9079-593X",
        ):
            self.assertTrue(valid_orcid(value))
        for value in ("0000-0002-1825-0098", "0000000218250097", None, "0000-0002-9079-593x"):
            self.assertFalse(valid_orcid(value))

    def test_every_creator_must_have_orcid_and_affiliation_for_bonus(self):
        checks = zenodo_adapter.evaluate(zenodo(creators=[
            {
                "name": "A",
                "orcid": "0000-0002-1825-0097",
                "affiliation": "University",
            },
            {"name": "B"},
        ]))
        self.assertEqual(check(checks, "M6", "Test-01")["status"], "PASS")
        for test in ("Test-02", "Test-03"):
            result = check(checks, "M6", test)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["kind"], "bonus")
            self.assertEqual(result["points"], 0)

    def test_empty_creators_do_not_earn_bonus(self):
        checks = zenodo_adapter.evaluate(zenodo(creators=[]))
        for test in ("Test-01", "Test-02", "Test-03"):
            self.assertEqual(check(checks, "M6", test)["status"], "FAIL")

    def test_structured_affiliations_and_identifier_only_affiliations(self):
        checks = dryad_adapter.evaluate({
            "id": 1,
            "authors": [
                {"name": "A", "affiliations": [{"name": "University", "identifiers": None}]},
                {"name": "B", "affiliationROR": "https://ror.org/03yrm5c26"},
            ],
        })
        self.assertEqual(check(checks, "M6", "Test-03")["status"], "PASS")
        self.assertEqual(check(checks, "M7", "Test-01")["status"], "PASS")

    def test_repository_name_is_not_invented_to_pass_presence(self):
        checks = figshare_adapter.evaluate({"id": 1})
        self.assertEqual(check(checks, "M7", "Test-01")["status"], "FAIL")
        checks = figshare_adapter.evaluate({"id": 1, "publisher": "University Repository"})
        self.assertEqual(check(checks, "M7", "Test-01")["status"], "PASS")

    def test_invalid_ror_is_retained_as_failed_evidence(self):
        for value in ("not-a-ror", "03yrm5c27", {"invalid": True}):
            checks = dryad_adapter.evaluate({
                "id": 1, "authors": [{"name": "A", "affiliationROR": value}],
            })
            result = check(checks, "M7", "Test-02")
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["evidence"][0]["value"], value)
        self.assertEqual(ror_id("https://ror.org/03yrm5c26"), "03yrm5c26")


class SubjectsAndType(unittest.TestCase):
    def test_dryad_subject_is_checked_in_controlled_vocabulary(self):
        cases = [
            ("Biological sciences", "PASS"),
            ("1.6", "PASS"),
            ("Invented science", "FAIL"),
            ("", "FAIL"),
        ]
        for term, status in cases:
            checks = dryad_adapter.evaluate({"id": 1, "fieldOfScience": term})
            self.assertEqual(check(checks, "M5", "Test-01")["status"], status)

    def test_at_least_one_controlled_subject_and_unknown_vocabulary(self):
        checks = zenodo_adapter.evaluate(zenodo(subjects=[
            {"term": "Birds"},
            {"scheme": "OECD FOS", "term": "Biological sciences"},
        ]))
        self.assertEqual(check(checks, "M5", "Test-01")["status"], "PASS")
        checks = zenodo_adapter.evaluate(zenodo(subjects=[{"term": "Birds", "scheme": "unknown"}]))
        self.assertEqual(check(checks, "M5", "Test-01")["status"], "UNSURE")

    def test_resource_type_is_distinguished_from_file_format(self):
        cases = [
            ("Dataset", "PASS", "Dataset"),
            ("Other", "FAIL", "Other resource type"),
            ("CSV", "FAIL", "File format"),
            ("NovelType", "UNSURE", "Unknown"),
        ]
        for value, status, classification in cases:
            checks = figshare_adapter.evaluate({"id": 1, "defined_type_name": value})
            result = check(checks, "M8", "Test-02")
            self.assertEqual(result["status"], status)
            self.assertEqual(result["classification"], classification)
            self.assertEqual(result["maxPoints"], 0)


class DateChecks(unittest.TestCase):
    def test_known_formats_and_invalid_or_ambiguous_dates(self):
        for date in (
            "2024", "2024-02", "2024-02-29", "2024/02/29", "29.02.2024",
            "2024-02-29T12:00:00Z", "9999-12-31",
        ):
            self.assertIsNotNone(parse_date(date), date)
        for date in (
            "01/02/2024", "2023-02-29", "2024-13-01", "yesterday", 2024,
            "20240101", "2024-W01-1",
        ):
            self.assertIsNone(parse_date(date), date)

    def test_order_and_future_embargo_dates(self):
        record = {"id": 1, "created_date": "2099-01-01", "published_date": "2100-01-01"}
        checks = figshare_adapter.evaluate(record)
        self.assertEqual(check(checks, "M9", "Test-01")["status"], "PASS")
        self.assertEqual(check(checks, "M9", "Test-01-01")["status"], "PASS")
        self.assertEqual(check(checks, "M9", "Test-02")["status"], "PASS")
        record["created_date"] = "2101-01-01"
        result = check(figshare_adapter.evaluate(record), "M9", "Test-02")
        self.assertEqual(result["status"], "FAIL")

    def test_precision_and_timezone_uncertainty(self):
        cases = [
            ("2024", "2024-02", "UNSURE"),
            ("2023", "2024", "PASS"),
            ("2024-01-01T10:00:00", "2024-01-01T11:00:00Z", "UNSURE"),
            ("2024-01-01T10:00:00+02:00", "2024-01-01T08:30:00Z", "PASS"),
        ]
        for created, published, expected in cases:
            checks = figshare_adapter.evaluate({
                "id": 1, "created_date": created, "published_date": published,
            })
            result = check(checks, "M9", "Test-02")
            self.assertEqual(result["status"], expected)

    def test_embargo_and_prepublication_modification_do_not_violate_order(self):
        record = {
            "id": 1,
            "created_date": "2024-01-01",
            "modified_date": "2024-02-01",
            "published_date": "2100-01-01",
        }
        result = check(figshare_adapter.evaluate(record), "M9", "Test-02")
        self.assertEqual(result["status"], "PASS")
        del record["created_date"]
        result = check(figshare_adapter.evaluate(record), "M9", "Test-02")
        self.assertEqual(result["status"], "UNSURE")

    def test_metadata_creation_is_not_compared_with_dataset_publication(self):
        record = zenodo(publication_date="1900-01-01")
        record.update(created="2024-01-01", updated="2024-02-01")
        result = check(zenodo_adapter.evaluate(record), "M9", "Test-02")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["evidence"], [
            {"before": "created", "after": "updated", "status": "PASS"},
        ])

    def test_missing_unparseable_or_unpaired_dates_remain_unsure(self):
        for record in (
            {"id": 1},
            {"id": 1, "published_date": "bad"},
            {"id": 1, "published_date": "2024-01-01"},
        ):
            result = check(figshare_adapter.evaluate(record), "M9", "Test-02")
            self.assertEqual(result["status"], "UNSURE")


class ExternalVerification(unittest.TestCase):
    def test_lookups_are_deduplicated_and_points_are_updated(self):
        checks = figshare_adapter.evaluate({
            "id": 1,
            "doi": "10.6084/m9.figshare.1.v1",
            "categories": [
                {"id": 1, "title": "Science"},
                {"id": 2, "title": "Other"},
            ],
        })
        original = copy.deepcopy(checks)

        def response(url, *, resolve):
            if resolve:
                return {
                    "status": "PASS",
                    "message": "Reached target.",
                    "targetUrl": "https://figshare.com/articles/1",
                }
            return {"status": "PASS", "data": [{"id": 1, "title": "Science"}]}

        with patch("src.utils.metadata_verification._request", side_effect=response) as request:
            verified = verify_metadata_checks(checks)
            category_requests = [
                call for call in request.call_args_list
                if call.args[0] == "https://api.figshare.com/v2/categories"
            ]
            self.assertEqual(len(category_requests), 1)
        self.assertEqual(checks, original)
        self.assertEqual(check(verified, "M5", "Test-01")["points"], 1)
        self.assertEqual(check(verified, "M1", "Test-03-02")["points"], 0.5)
        self.assertNotIn("verification", json.dumps(verified))

    def test_unknown_category_and_registry_outage(self):
        checks = figshare_adapter.evaluate({"id": 1, "categories": [{"id": 999, "title": "Bogus"}]})
        cases = [
            ({"status": "PASS", "data": [{"id": 1, "title": "Real"}]}, "FAIL"),
            ({"status": "UNSURE", "message": "Rate limited."}, "UNSURE"),
        ]
        for response, status in cases:
            with patch("src.utils.metadata_verification._request", return_value=response):
                result = check(verify_metadata_checks(checks), "M5", "Test-01")
            self.assertEqual(result["status"], status)
            self.assertEqual(result["points"], 0)

    def test_ror_response_must_return_the_requested_identifier(self):
        spec = {"kind": "ror", "id": "https://ror.org/03yrm5c26"}
        cases = [
            ({"id": spec["id"]}, "PASS"),
            ({"id": "https://ror.org/015w2mp89"}, "FAIL"),
            ({}, "UNSURE"),
        ]
        for data, status in cases:
            result = _verify_payload(spec, {"status": "PASS", "data": data})
            self.assertEqual(result["status"], status)

    def test_supported_vocabulary_requests_and_payloads(self):
        cases = [
            (
                {"kind": "vocabulary-term", "scheme": "efo", "id": "EFO:0000311"},
                {"_embedded": {"terms": [{
                    "iri": "http://www.ebi.ac.uk/efo/EFO_0000311",
                }]}},
            ),
            (
                {"kind": "vocabulary-term", "scheme": "gnd", "id": "4079154-3"},
                {"gndIdentifier": "4079154-3"},
            ),
            (
                {"kind": "vocabulary-term", "scheme": "mesh", "id": "D012345"},
                {"http://id.nlm.nih.gov/mesh/D012345": {
                    "http://www.w3.org/2000/01/rdf-schema#label": [
                        {"value": "Label", "type": "literal"},
                    ],
                }},
            ),
        ]
        for spec, data in cases:
            self.assertIsNotNone(_lookup_url(spec))
            result = _verify_payload(spec, {"status": "PASS", "data": data})
            self.assertEqual(result["status"], "PASS")
        self.assertIsNone(_lookup_url({
            "kind": "vocabulary-term", "scheme": "mesh",
            "id": "https://evil.example/D012345",
        }))

    def test_http_missing_targets_fail_and_service_errors_are_unsure(self):
        for code, expected in (
            (404, "FAIL"), (410, "FAIL"), (403, "UNSURE"),
            (429, "UNSURE"), (503, "UNSURE"),
        ):
            opener = MagicMock()
            opener.open.side_effect = HTTPError(
                "https://doi.org/item", code, "error", {}, BytesIO(),
            )
            with (
                patch("src.utils.metadata_verification._require_public_url"),
                patch("src.utils.metadata_verification.build_opener", return_value=opener),
            ):
                result = _request("https://doi.org/item", resolve=True)
            self.assertEqual(result["status"], expected)

    def test_resolver_closes_without_reading_landing_page_body(self):
        response = MagicMock()
        response.geturl.return_value = "https://example.org/dataset"
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        with (
            patch("src.utils.metadata_verification._require_public_url"),
            patch("src.utils.metadata_verification.build_opener", return_value=opener),
        ):
            result = _request("https://doi.org/10.1234/item", resolve=True)
        self.assertEqual(result["status"], "PASS")
        response.read.assert_not_called()

    def test_resolver_success_without_resource_target_remains_unsure(self):
        response = MagicMock()
        response.geturl.return_value = "https://doi.org/10.1234/item"
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        with (
            patch("src.utils.metadata_verification._require_public_url"),
            patch("src.utils.metadata_verification.build_opener", return_value=opener),
        ):
            result = _request(response.geturl.return_value, resolve=True)
        self.assertEqual(result["status"], "UNSURE")

    def test_empty_efo_lookup_is_a_failed_membership_check(self):
        spec = {"kind": "vocabulary-term", "scheme": "efo", "id": "EFO:0000311"}
        response = {"status": "PASS", "data": {"page": {"totalElements": 0}}}
        self.assertEqual(_verify_payload(spec, response)["status"], "FAIL")

    def test_private_addresses_are_not_requested(self):
        with patch(
            "src.utils.metadata_verification.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("127.0.0.1", 443))],
        ):
            with self.assertRaises(ValueError):
                _require_public_url("https://example.org/item")
        with patch(
            "src.utils.metadata_verification._require_public_url",
            side_effect=URLError("offline"),
        ):
            result = _request("https://example.org/item", resolve=True)
            self.assertEqual(result["status"], "UNSURE")


class CompatibilityAndSummary(unittest.TestCase):
    def test_unlisted_checks_are_unchanged_in_all_adapters(self):
        records = [
            (zenodo_adapter, zenodo(
                language="eng", version="1.0", locations=[{"lat": 0}],
                contributors=[{"name": "A"}],
            )),
            (dryad_adapter, {
                "id": 1, "versionNumber": 1,
                "methods": "<p>method</p>", "locations": [],
            }),
            (figshare_adapter, {
                "id": 1, "version": 1, "funding": "Grant",
                "references": ["ref", ""],
            }),
        ]
        for adapter, record in records:
            with self.subTest(repository=adapter.REPOSITORY):
                replaced = PROFILES[adapter.REPOSITORY]["replaced"]
                rules = [rule for rule in adapter.RULES if rule.field not in replaced]
                old = evaluate_rules(record, rules)
                current = [item for item in adapter.evaluate(record) if "group" not in item]
                self.assertEqual(current, old)

    def test_score_summary_separates_bonus_warnings_and_unsure(self):
        record = zenodo(
            description="<p>Bird observations in Slovakia</p>",
            keywords=["Bird", "bird"],
        )
        with (
            patch("src.clients.repository_client.fetch_json", return_value=record),
            patch(
                "src.clients.repository_client.verify_metadata_checks",
                side_effect=lambda checks: checks,
            ),
            patch(
                "src.clients.repository_client.evaluate_aggregators",
                return_value=[{"status": "ERROR"}, {"status": "FAIL"}],
            ),
        ):
            result = fetch_and_evaluate(
                repository="zenodo",
                display_name="Zenodo",
                source_url="https://zenodo.org/api/records/123",
                reference="123",
                doi_field="doi",
                evaluator=zenodo_adapter.evaluate,
                rules=zenodo_adapter.RULES,
            )
        summary = result["summary"]
        self.assertEqual(summary["maxScore"], 12)
        self.assertEqual(summary["maxBonusScore"], 4.5)
        self.assertEqual(summary["warnings"], 2)
        self.assertEqual(summary["errors"], 1)
        status_total = sum(
            summary[key] for key in ("passed", "failed", "warnings", "unsure", "errors")
        )
        self.assertEqual(summary["total"], status_total)
        self.assertEqual(len(result["checks"]["repositoryLevel"]), len(zenodo_adapter.RULES))
        json.dumps(result)


if __name__ == "__main__":
    unittest.main()
