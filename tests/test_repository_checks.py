"""Repository guarantees, conditional completion, and API integration."""

import json
import unittest
from unittest.mock import patch

from src.adapters import dryad_adapter, figshare_adapter, zenodo_adapter
from src.clients.repository_client import _summarize_checks
from src.utils.checks import Rule
from src.utils.repository_checks import evaluate_repository_checks
from src.utils.repository_policies import REPOSITORY_POLICIES


ADAPTERS = (zenodo_adapter, dryad_adapter, figshare_adapter)


def policies(adapter):
    return {
        item["field"]: item
        for item in evaluate_repository_checks(adapter.REPOSITORY, adapter.RULES)
    }


class RepositoryPolicies(unittest.TestCase):
    def test_every_catalog_field_has_a_sourced_policy(self):
        for adapter in ADAPTERS:
            with self.subTest(repository=adapter.REPOSITORY):
                results = evaluate_repository_checks(adapter.REPOSITORY, adapter.RULES)
                catalog = [rule.field for rule in adapter.RULES]
                self.assertEqual([item["field"] for item in results], catalog)
                self.assertEqual(set(REPOSITORY_POLICIES[adapter.REPOSITORY].fields), set(catalog))
                for item in results:
                    self.assertTrue(item["sources"], item["field"])
                    self.assertTrue(all(url.startswith("https://") for url in item["sources"]))
                    self.assertEqual(item["reviewedAt"], "2026-10-01")
                    self.assertNotIn("value", item)
                    self.assertNotIn("points", item)
                json.dumps(results)

    def test_description_requirements_differ_between_repositories(self):
        zenodo = policies(zenodo_adapter)["metadata.description"]
        self.assertEqual((zenodo["requirement"], zenodo["status"]), ("optional", "WARNING"))
        for adapter, field in ((dryad_adapter, "abstract"), (figshare_adapter, "description")):
            item = policies(adapter)[field]
            self.assertEqual((item["requirement"], item["status"]), ("required", "PASS"))

    def test_required_publication_date_can_also_have_a_default(self):
        item = policies(zenodo_adapter)["metadata.publication_date"]
        self.assertEqual(item["requirement"], "required")
        self.assertEqual(item["autoFill"], "default")
        self.assertEqual(item["status"], "PASS")
        self.assertIn("draft creation date", item["message"])

    def test_doi_generation_preserves_existing_zenodo_doi_condition(self):
        for adapter in ADAPTERS:
            item = policies(adapter)[adapter.DOI_FIELD]
            self.assertEqual(item["autoFill"], "generated")
            self.assertEqual(item["status"], "PASS")
        item = policies(zenodo_adapter)["doi"]
        self.assertEqual(item["requirement"], "conditional")
        self.assertIn("existing DOI", item["message"])

    def test_registry_completion_does_not_ensure_optional_metadata(self):
        for adapter, field in (
            (zenodo_adapter, "metadata.subjects[].identifier"),
            (dryad_adapter, "authors[].affiliationROR"),
            (figshare_adapter, "funding_list[].grant_code"),
        ):
            with self.subTest(field=field):
                item = policies(adapter)[field]
                self.assertEqual(item["autoFill"], "selection")
                self.assertEqual(item["status"], "WARNING")

    def test_dryad_login_does_not_require_every_coauthor_to_have_orcid(self):
        item = policies(dryad_adapter)["authors[].orcid"]
        self.assertEqual(item["requirement"], "conditional")
        self.assertEqual(item["status"], "WARNING")
        self.assertIn("not for every coauthor", item["message"])

    def test_dryad_derives_related_work_metadata_and_can_complete_awards(self):
        results = policies(dryad_adapter)
        relationship = results["relatedWorks[].relationship"]
        self.assertEqual(relationship["autoFill"], "selection")
        self.assertEqual(relationship["status"], "WARNING")
        self.assertIn("derives the relationship", relationship["message"])
        identifier_type = results["relatedWorks[].identifierType"]
        self.assertEqual(identifier_type["autoFill"], "detected")
        self.assertEqual(identifier_type["status"], "WARNING")
        award = results["funders[].awardNumber"]
        self.assertEqual(award["autoFill"], "selection")
        self.assertEqual(award["requirement"], "optional")

    def test_figshare_categories_expose_conflicting_form_documentation(self):
        for field in ("categories[].title", "categories[].id"):
            item = policies(figshare_adapter)[field]
            self.assertEqual(item["requirement"], "varies")
            self.assertEqual(item["status"], "UNSURE")
            self.assertEqual(len(item["sources"]), 2)

    def test_defaults_in_optional_related_materials_do_not_ensure_a_link(self):
        for field in ("related_materials[].relation", "related_materials[].identifier_type"):
            item = policies(figshare_adapter)[field]
            self.assertEqual(item["autoFill"], "default")
            self.assertEqual(item["requirement"], "conditional")
            self.assertEqual(item["status"], "WARNING")

    def test_new_unmapped_field_is_visible_and_unverified(self):
        item, = evaluate_repository_checks("zenodo", [Rule("metadata.new", "New field")])
        self.assertEqual(item["status"], "UNSURE")
        self.assertEqual(item["requirement"], "unknown")
        self.assertEqual(item["sources"], [])
        self.assertIsNone(item["reviewedAt"])


class RepositoryIntegration(unittest.TestCase):
    def test_all_adapters_include_policies_independent_of_record_values(self):
        for adapter, reference, record in (
            (zenodo_adapter, "123", {"id": 123, "metadata": {}}),
            (dryad_adapter, "10.5061/dryad.example", {"id": 123}),
            (figshare_adapter, "10.6084/m9.figshare.123.v2", {"id": 123}),
        ):
            with (
                self.subTest(repository=adapter.REPOSITORY),
                patch("src.clients.repository_client.fetch_json", return_value=record) as fetch,
                patch("src.clients.repository_client.verify_metadata_checks", side_effect=lambda items: items),
                patch("src.clients.repository_client.evaluate_aggregators", return_value=[]),
            ):
                first = adapter.fetch(reference)
                record.update(title="A different title", authors=[{"full_name": "Author"}])
                second = adapter.fetch(reference)
                expected = evaluate_repository_checks(adapter.REPOSITORY, adapter.RULES)
                self.assertEqual(first["checks"]["repositoryLevel"], expected)
                self.assertEqual(second["checks"]["repositoryLevel"], expected)
                self.assertEqual(fetch.call_count, 2)
                json.dumps(first)

    def test_repository_policies_do_not_inflate_record_counts_or_scores(self):
        sections = {
            "recordLevel": [{"status": "PASS", "kind": "required", "points": 1, "maxPoints": 2}],
            "aggregators": [{"status": "FAIL"}],
            "repositoryLevel": [],
        }
        before = _summarize_checks(sections)
        for adapter in ADAPTERS:
            sections["repositoryLevel"] = evaluate_repository_checks(adapter.REPOSITORY, adapter.RULES)
            self.assertEqual(_summarize_checks(sections), before)
        self.assertEqual((before["total"], before["passed"], before["failed"]), (2, 1, 1))
        self.assertEqual((before["score"], before["maxScore"]), (1, 2))


if __name__ == "__main__":
    unittest.main()
