"""Behavioral coverage for G01–G10 across all three generic adapters."""

import copy
import json
import unittest
from unittest.mock import patch

from src.adapters import dryad_adapter, figshare_adapter, zenodo_adapter
from src.utils.generic_metadata_checks import evaluate_generic_metadata
from src.utils.generic_metadata_model import EvaluationContext
from src.utils.generic_metadata_summary import summarize_generic_checks
from src.utils.metadata_verification import verify_metadata_checks


ADAPTERS = (zenodo_adapter, dryad_adapter, figshare_adapter)


def record(repository):
    common = {
        "title": "Bird observations in Slovakia",
        "description": "<p>Counts of birds at monitoring sites in 2019–2022.</p>",
        "keywords": ["birds"],
    }
    if repository == "zenodo":
        return {"id": 123, "doi": "10.5281/zenodo.123", "conceptdoi": "10.5281/zenodo.100",
                "metadata": {**common, "resource_type": {"type": "dataset"},
                             "creators": [{"name": "Bird Monitoring Team"}]}}
    if repository == "dryad":
        return {"id": 123, "identifier": "doi:10.5061/dryad.example", "title": common["title"],
                "abstract": common["description"], "keywords": common["keywords"],
                "authors": [{"lastName": "Bird Monitoring Team"}]}
    return {**common, "id": 123, "doi": "10.6084/m9.figshare.123.v2", "version": 2,
            "defined_type_name": "Dataset", "authors": [{"full_name": "Bird Monitoring Team"}]}


def check(checks, group, test):
    return next(item for item in checks if (item["group"], item["testId"]) == (group, test))


class GenericContract(unittest.TestCase):
    def test_all_adapters_use_ten_groups_and_preserve_original_metadata(self):
        for adapter in ADAPTERS:
            with self.subTest(repository=adapter.REPOSITORY):
                source = record(adapter.REPOSITORY)
                original = copy.deepcopy(source)
                checks = adapter.evaluate(source)
                self.assertEqual({item["group"] for item in checks}, {f"G{number:02}" for number in range(1, 11)})
                self.assertEqual(len({(item["group"], item["testId"]) for item in checks}), len(checks))
                self.assertTrue(all(item["maxPoints"] == 0 for item in checks))
                self.assertTrue(all(item["kind"] != "bonus" for item in checks))
                for item in checks:
                    for key in ("applicable", "applicabilityReason", "profile", "ruleVersion",
                                "sourceRepresentation", "targetObject", "decisionMethod"):
                        self.assertIn(key, item)
                self.assertEqual(source, original)
                json.dumps(checks)

    def test_optional_catalog_fields_are_not_universal_record_failures(self):
        for adapter in ADAPTERS:
            checks = adapter.evaluate(record(adapter.REPOSITORY))
            self.assertFalse(any(item["label"] in {"Language", "Grant codes", "Funding description", "Version"} for item in checks))
            self.assertEqual(check(checks, "G06", "origin.named")["status"], "PASS")

    def test_incomplete_harvest_does_not_prove_missing_values(self):
        checks = evaluate_generic_metadata({"id": 123, "metadata": {}}, "zenodo",
                                          context=EvaluationContext(complete=False))
        for group, test in (("G02", "name.present"), ("G03", "description.present"), ("G06", "origin.named")):
            self.assertEqual(check(checks, group, test)["status"], "UNSURE")
        checks = evaluate_generic_metadata({"id": 123, "metadata": {
            "title": "Dataset", "keywords": ["data"], "method": "Methods available",
        }}, "zenodo", context=EvaluationContext(complete=False))
        for group, test in (("G02", "name.informative"), ("G04", "terms.relevant"),
                            ("G08", "generation_process.searchable")):
            self.assertEqual(check(checks, group, test)["status"], "UNSURE")


class DatasetIdentity(unittest.TestCase):
    def test_requested_native_reference_is_bound_to_record(self):
        cases = ((zenodo_adapter, "123"), (dryad_adapter, "10.5061/dryad.example"),
                 (figshare_adapter, "https://figshare.com/articles/dataset/Birds/123/2"))
        for adapter, reference in cases:
            checks = adapter.evaluate(record(adapter.REPOSITORY), reference=reference)
            self.assertEqual(check(checks, "G01", "metadata.target_binding")["status"], "PASS")
        offline = zenodo_adapter.evaluate(record("zenodo"))
        self.assertEqual(check(offline, "G01", "metadata.target_binding")["status"], "UNSURE")

    def test_wrong_record_or_article_doi_cannot_bind_dataset(self):
        for adapter, reference in ((zenodo_adapter, "124"), (dryad_adapter, "10.5061/dryad.other"),
                                   (figshare_adapter, "10.6084/m9.figshare.124.v2")):
            checks = adapter.evaluate(record(adapter.REPOSITORY), reference=reference)
            self.assertEqual(check(checks, "G01", "metadata.target_binding")["status"], "FAIL")
        source = record("zenodo")
        source["metadata"]["resource_type"]["type"] = "publication"
        checks = zenodo_adapter.evaluate(source, reference="123")
        self.assertEqual(check(checks, "G01", "metadata.target_binding")["status"], "FAIL")

    def test_local_id_has_an_explicit_repository_namespace(self):
        source = record("figshare")
        del source["doi"]
        result = check(figshare_adapter.evaluate(source), "G01", "identifier.interpretable")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["evidence"][0]["namespace"], "figshare:record-id")
        source["id"] = True
        self.assertEqual(check(figshare_adapter.evaluate(source), "G01", "identifier.interpretable")["status"], "FAIL")

    def test_zenodo_concept_reference_keeps_series_and_version_distinct(self):
        checks = zenodo_adapter.evaluate(record("zenodo"), reference="10.5281/zenodo.100")
        self.assertEqual(check(checks, "G01", "metadata.target_binding")["status"], "PASS")
        self.assertEqual(check(checks, "G01", "version.binding")["status"], "NOT_APPLICABLE")

    def test_series_doi_and_dryad_url_inputs_are_normalized_for_binding(self):
        cases = (
            (figshare_adapter, "10.6084/m9.figshare.123"),
            (dryad_adapter, "https://datadryad.org/dataset/doi:10.5061/dryad.example"),
            (zenodo_adapter, "https://zenodo.org/doi/10.5281/zenodo.100"),
        )
        for adapter, reference in cases:
            checks = adapter.evaluate(record(adapter.REPOSITORY), reference=reference)
            self.assertEqual(check(checks, "G01", "metadata.target_binding")["status"], "PASS")

    def test_native_doi_and_record_id_conflict_is_detected(self):
        source = record("figshare")
        source["doi"] = "10.6084/m9.figshare.999.v2"
        checks = figshare_adapter.evaluate(source, reference=source["doi"])
        self.assertEqual(check(checks, "G01", "metadata.target_binding")["status"], "FAIL")

    def test_equal_article_and_version_numbers_do_not_confuse_resolver(self):
        source = record("figshare")
        source.update(id=2, doi="10.6084/m9.figshare.2.v2")
        checks = figshare_adapter.evaluate(source, reference=source["doi"])
        with patch("src.utils.metadata_verification._request", return_value={
            "status": "PASS", "targetUrl": "https://figshare.com/articles/2/2",
        }):
            verified = verify_metadata_checks(checks)
        self.assertEqual(check(verified, "G01", "pid.resolution")["status"], "PASS")

    def test_figshare_wrong_version_is_reported(self):
        source = record("figshare")
        source["version"] = 3
        checks = figshare_adapter.evaluate(source, reference="10.6084/m9.figshare.123.v2")
        self.assertEqual(check(checks, "G01", "version.binding")["status"], "FAIL")

    def test_resolver_homepage_or_other_version_does_not_pass(self):
        checks = figshare_adapter.evaluate(record("figshare"), reference="10.6084/m9.figshare.123.v2")
        for target, expected in (("https://figshare.com/", "UNSURE"),
                                 ("https://figshare.com/articles/999/2", "FAIL"),
                                 ("https://figshare.com/articles/dataset/Birds/123/1", "FAIL"),
                                 ("https://figshare.com/articles/dataset/Birds/123/2", "PASS")):
            with patch("src.utils.metadata_verification._request", return_value={
                "status": "PASS", "targetUrl": target, "redirectChain": [{"to": target}],
                "checkedAt": "2026-10-14T08:00:00Z",
            }):
                result = check(verify_metadata_checks(checks), "G01", "pid.resolution")
            self.assertEqual(result["status"], expected)
            self.assertEqual(result["checkedAt"], "2026-10-14T08:00:00Z")
            self.assertEqual(result["redirectChain"][0]["to"], target)

    def test_resolver_outage_does_not_invalidate_identifier_syntax(self):
        checks = zenodo_adapter.evaluate(record("zenodo"), reference="123")
        with patch("src.utils.metadata_verification._request", return_value={"status": "UNSURE", "message": "timeout"}):
            verified = verify_metadata_checks(checks)
        self.assertEqual(check(verified, "G01", "identifier.interpretable")["status"], "PASS")
        self.assertEqual(check(verified, "G01", "pid.resolution")["status"], "UNSURE")


class TextAndTerms(unittest.TestCase):
    def test_empty_nontext_and_html_only_summary_fail_presence(self):
        for value in (None, "", " \u00a0 ", False, 0, ["birds"], "<p>&nbsp;<br></p>"):
            source = record("zenodo")
            source["metadata"]["description"] = value
            self.assertEqual(check(zenodo_adapter.evaluate(source), "G03", "description.present")["status"], "FAIL")

    def test_presence_does_not_establish_semantic_quality(self):
        checks = zenodo_adapter.evaluate(record("zenodo"))
        for group, test in (("G02", "name.informative"), ("G03", "description.data_focus"),
                            ("G03", "description.discriminating_information"), ("G04", "terms.relevant")):
            self.assertEqual(check(checks, group, test)["status"], "UNSURE")
        source = record("zenodo")
        source["metadata"]["title"] = "Untitled"
        self.assertEqual(check(zenodo_adapter.evaluate(source), "G02", "name.informative")["status"], "FAIL")

    def test_sample_code_and_domain_abbreviation_are_not_assumed_placeholders(self):
        for title in ("Sample 123", "N/A", "file_001.csv", "air_temperature_slovakia_2022.csv"):
            source = record("zenodo")
            source["metadata"]["title"] = title
            self.assertEqual(check(zenodo_adapter.evaluate(source), "G02", "name.informative")["status"], "UNSURE")

    def test_title_copy_has_no_distinguishing_information(self):
        source = record("zenodo")
        source["metadata"].update(title="BIRD Counts", description="<p>ｂｉｒｄ</p><p>counts</p>")
        checks = zenodo_adapter.evaluate(source)
        self.assertEqual(check(checks, "G03", "description.present")["status"], "PASS")
        self.assertEqual(check(checks, "G03", "description.discriminating_information")["status"], "FAIL")

    def test_free_terms_do_not_require_vocabulary_or_both_fields(self):
        checks = zenodo_adapter.evaluate(record("zenodo"))
        self.assertEqual(check(checks, "G04", "terms.access_function")["status"], "PASS")
        self.assertFalse(any(item["testId"] == "concepts.valid" for item in checks))
        source = record("figshare")
        del source["keywords"]
        source["tags"] = ["Birds", " ｂｉｒｄｓ "]
        result = check(figshare_adapter.evaluate(source), "G04", "terms.duplicates")
        self.assertEqual(result["status"], "WARNING")
        self.assertEqual(result["field"], "tags")

    def test_concept_membership_and_label_alignment_do_not_prove_relevance(self):
        source = record("figshare")
        source["categories"] = [{"id": 1, "title": "Birds"}]
        checks = figshare_adapter.evaluate(source)
        with patch("src.utils.metadata_verification._request", return_value={
            "status": "PASS", "data": [{"id": 1, "title": "Chemistry"}],
        }) as request:
            verified = verify_metadata_checks(checks)
        self.assertEqual(check(verified, "G04", "concepts.valid")["status"], "PASS")
        self.assertEqual(check(verified, "G04", "concepts.label_alignment")["status"], "FAIL")
        self.assertEqual(check(verified, "G04", "terms.relevant")["status"], "UNSURE")
        self.assertEqual(sum(call.args[0].endswith("/categories") for call in request.call_args_list), 1)

    def test_one_valid_concept_cannot_hide_an_invalid_assignment(self):
        source = record("dryad")
        source["fieldOfScience"] = ["1.6", "Invented science"]
        self.assertEqual(check(dryad_adapter.evaluate(source), "G04", "concepts.valid")["status"], "FAIL")

    def test_dataset_and_mime_type_do_not_establish_data_kind(self):
        for value, status in (("Dataset", "UNSURE"), ("CSV", "UNSURE"), ("Image", "PASS")):
            source = record("figshare")
            source["defined_type_name"] = value
            self.assertEqual(check(figshare_adapter.evaluate(source), "G05", "data_kind.usable")["status"], status)


class OriginScopeAndRelations(unittest.TestCase):
    def test_declared_contributor_roles_are_evaluated_individually(self):
        source = record("zenodo")
        source["metadata"]["contributors"] = [{"name": "Research Team", "type": "DataCollector"}]
        self.assertEqual(check(zenodo_adapter.evaluate(source), "G06", "agent_role.contributor.usable")["status"], "PASS")
        source["metadata"]["contributors"].append({"name": "A", "type": "Other"})
        self.assertEqual(check(zenodo_adapter.evaluate(source), "G06", "agent_role.contributor.usable")["status"], "UNSURE")
        source["metadata"]["contributors"].append({"type": "Editor"})
        self.assertEqual(check(zenodo_adapter.evaluate(source), "G06", "agent_role.contributor.usable")["status"], "FAIL")

    def test_methods_available_is_not_a_generation_process(self):
        source = record("dryad")
        source["methods"] = "<p>Methods available</p>"
        self.assertEqual(check(dryad_adapter.evaluate(source), "G08", "generation_process.searchable")["status"], "FAIL")

    def test_host_cannot_replace_creator_or_hide_unnamed_creator(self):
        source = record("figshare")
        source.update(authors=[], repository="Figshare")
        self.assertEqual(check(figshare_adapter.evaluate(source), "G06", "origin.named")["status"], "FAIL")
        source["authors"] = [{"full_name": "Research Team"}, {}]
        self.assertEqual(check(figshare_adapter.evaluate(source), "G06", "origin.named")["status"], "FAIL")

    def test_lifecycle_dates_do_not_fill_content_time(self):
        source = record("zenodo")
        source["metadata"].update(publication_date="2024-01-01", dates=[{"start": "2024", "type": "Issued"}])
        result = check(zenodo_adapter.evaluate(source), "G07", "scope.temporal_coverage.usable")
        self.assertEqual(result["status"], "UNSURE")
        self.assertIsNone(result["applicable"])

    def test_scope_dimensions_are_independent_and_keep_unknown_applicability(self):
        source = record("zenodo")
        source["metadata"]["locations"] = [{"place": "Slovakia"}]
        checks = zenodo_adapter.evaluate(source)
        self.assertEqual(check(checks, "G07", "scope.spatial_coverage.usable")["status"], "PASS")
        self.assertEqual(check(checks, "G07", "scope.properties.usable")["status"], "UNSURE")
        self.assertEqual(next(group for group in summarize_generic_checks(checks)["groups"] if group["group"] == "G07")["status"], "UNSURE")

    def test_explicit_scope_tasks_determine_exclusion_and_missing_value(self):
        source = record("zenodo")
        checks = evaluate_generic_metadata(source, "zenodo", context=EvaluationContext(scope_dimensions=frozenset({"S"})))
        self.assertEqual(check(checks, "G07", "scope.spatial_coverage.usable")["status"], "FAIL")
        excluded = check(checks, "G07", "scope.temporal_coverage.usable")
        self.assertEqual(excluded["status"], "NOT_APPLICABLE")
        self.assertTrue(excluded["applicabilityReason"])

    def test_coordinate_zero_is_preserved_but_invalid_ranges_fail(self):
        for latitude, expected in ((0, "PASS"), (91, "FAIL"), (False, "FAIL")):
            source = record("zenodo")
            source["metadata"]["locations"] = [{"lat": latitude, "lon": 0, "crs": "EPSG:4326"}]
            self.assertEqual(check(zenodo_adapter.evaluate(source), "G07", "scope.spatial_coverage.usable")["status"], expected)

    def test_dryad_native_point_and_box_representations_are_validated(self):
        for location, expected in (
            ({"place": "Slovakia", "point": {"latitude": "48", "longitude": "19"}}, "PASS"),
            ({"point": {"latitude": "0", "longitude": "0"}}, "UNSURE"),
            ({"point": {"latitude": "95", "longitude": "0"}}, "FAIL"),
            ({"box": {"swLatitude": "49", "swLongitude": "18", "neLatitude": "48", "neLongitude": "19"}}, "FAIL"),
        ):
            source = record("dryad")
            source["locations"] = [location]
            self.assertEqual(check(dryad_adapter.evaluate(source), "G07", "scope.spatial_coverage.usable")["status"], expected)

    def test_open_partial_temporal_interval_and_reversed_bounds(self):
        for bounds, expected in (({"start": "2019"}, "PASS"),
                                 ({"start": "2019", "end": "2022"}, "PASS"),
                                 ({"start": "2022", "end": "2019"}, "FAIL"),
                                 ({"start": "antiquity"}, "UNSURE")):
            source = record("zenodo")
            source["metadata"]["dates"] = [{"type": "Collected", **bounds}]
            self.assertEqual(check(zenodo_adapter.evaluate(source), "G07", "scope.temporal_coverage.usable")["status"], expected)

    def test_existing_relations_keep_type_and_target_separate(self):
        source = record("zenodo")
        source["metadata"]["related_identifiers"] = [{"identifier": "10.1234/article", "scheme": "doi", "relation": "IsSupplementTo"}]
        checks = zenodo_adapter.evaluate(source)
        self.assertEqual(check(checks, "G09", "relation.target_interpretable")["status"], "PASS")
        self.assertEqual(check(checks, "G09", "relation.type_usable")["status"], "PASS")
        self.assertEqual(check(checks, "G09", "relation.meaning_consistent")["status"], "UNSURE")
        source["metadata"]["related_identifiers"].append({"identifier": "broken"})
        checks = zenodo_adapter.evaluate(source)
        self.assertEqual(check(checks, "G09", "relation.target_interpretable")["status"], "FAIL")
        self.assertEqual(check(checks, "G09", "relation.type_usable")["status"], "FAIL")

    def test_absent_relations_and_method_are_not_automatic_failures(self):
        checks = dryad_adapter.evaluate(record("dryad"))
        for group, test in (("G08", "generation_process.searchable"), ("G09", "relation.target_interpretable")):
            result = check(checks, group, test)
            self.assertEqual(result["status"], "UNSURE")
            self.assertIsNone(result["applicable"])

    def test_relation_accession_requires_its_declared_namespace(self):
        source = record("figshare")
        source["related_materials"] = [{"identifier": "1234567", "identifier_type": "PMID", "relation": "References"}]
        self.assertEqual(check(figshare_adapter.evaluate(source), "G09", "relation.target_interpretable")["status"], "PASS")
        source["related_materials"][0].pop("identifier_type")
        self.assertEqual(check(figshare_adapter.evaluate(source), "G09", "relation.target_interpretable")["status"], "FAIL")


class FetchIntegration(unittest.TestCase):
    def test_group_summary_preserves_failures_and_semantic_uncertainty(self):
        source = record("zenodo")
        source["metadata"]["description"] = source["metadata"]["title"]
        checks = zenodo_adapter.evaluate(source, reference="123")
        groups = {group["group"]: group for group in summarize_generic_checks(checks)["groups"]}
        self.assertEqual(groups["G03"]["status"], "FAIL")
        self.assertEqual(groups["G02"]["status"], "UNSURE")
        self.assertEqual(groups["G06"]["status"], "PASS")

    def test_fetch_propagates_binding_retrieval_and_capability_profile(self):
        references = {"zenodo": "123", "dryad": "10.5061/dryad.example", "figshare": "10.6084/m9.figshare.123.v2"}
        for adapter in ADAPTERS:
            with (
                self.subTest(repository=adapter.REPOSITORY),
                patch("src.clients.repository_client.fetch_json", return_value=record(adapter.REPOSITORY)),
                patch("src.clients.repository_client.verify_metadata_checks", side_effect=lambda checks: checks),
                patch("src.clients.repository_client.evaluate_aggregators", return_value=[]),
            ):
                result = adapter.fetch(references[adapter.REPOSITORY])
                checks = result["checks"]["recordLevel"]
                self.assertEqual(check(checks, "G01", "metadata.target_binding")["status"], "PASS")
                self.assertEqual(check(checks, "G10", "metadata.route_available")["status"], "PASS")
                self.assertEqual(check(checks, "G10", "metadata.profile_supported")["status"], "PASS")
                self.assertEqual(result["summary"]["profile"], "public_repository_api")
                self.assertNotIn("score", result["summary"])
                self.assertEqual(len(result["summary"]["groups"]), 10)
                self.assertEqual(len(result["checks"]["repositoryLevel"]), len(adapter.RULES))
                for item in checks:
                    self.assertEqual(item["sourceRepresentation"]["url"], result["sourceUrl"])
                summary = result["summary"]
                self.assertEqual(summary["total"], sum(summary[key] for key in (
                    "passed", "failed", "errors", "warnings", "unsure", "notApplicable")))
                json.dumps(result)

    def test_offline_api_json_is_not_evidence_of_crawling_or_discovery(self):
        checks = zenodo_adapter.evaluate(record("zenodo"))
        self.assertEqual(check(checks, "G10", "metadata.route_available")["status"], "UNSURE")
        self.assertEqual(check(checks, "G10", "metadata.discovery_route")["status"], "UNSURE")


if __name__ == "__main__":
    unittest.main()
