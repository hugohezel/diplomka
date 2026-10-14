"""PDB reference boundaries, native-field semantics and evaluation integration."""

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from src.adapters import pdb_adapter, zenodo_adapter
from src.clients.repository_client import _summarize_checks
from src.server import evaluate_reference, recognize_adapter
from src.utils.metadata_identifiers import identifier_syntax
from src.utils.repository_checks import evaluate_repository_checks
from src.utils.repository_policies import REPOSITORY_POLICIES


FIXTURES = Path(__file__).with_name("fixtures") / "pdb"


def entry(entry_id="4hhb"):
    return json.loads((FIXTURES / f"{entry_id}.json").read_text(encoding="utf-8"))


def check(results, group, test):
    return next(item for item in results if item.get("group") == group and item["testId"] == test)


class PDBReferences(unittest.TestCase):
    def test_equivalent_references_select_the_same_entry(self):
        for reference in (
            "4HHB", " 4hhb ", "PDB:4hhb", "pdb_00004hhb",
            "10.2210/pdb4hhb/pdb", "DOI: 10.2210/PDB4HHB/PDB",
            "https://doi.org/10.2210%2Fpdb4hhb%2Fpdb",
            "rcsb.org/structure/4hhb",
            "https://www.rcsb.org/structure/4HHB/?source=test#details",
            "http://rcsb.org:80/structure/4HHB",
            "https://data.rcsb.org/rest/v1/core/entry/4HHB",
            "data.rcsb.org/rest/v1/core/entry/pdb_00004hhb",
            "https://www.wwpdb.org/pdb?id=pdb_00004hhb",
            "wwpdb.org/pdb/?id=4HHB&source=test",
        ):
            with self.subTest(reference=reference):
                self.assertEqual(pdb_adapter.extract_entry_id(reference), "4HHB")
                self.assertIs(recognize_adapter(reference), pdb_adapter)

    def test_new_extended_ids_and_their_dois_are_preserved(self):
        for reference in (
            "pdb_1000axyz", "PDB_1000AXYZ", "pdb:pdb_1000axyz",
            "10.2210/pdb_1000axyz/pdb",
            "https://www.rcsb.org/structure/pdb_1000axyz",
        ):
            with self.subTest(reference=reference):
                self.assertEqual(pdb_adapter.extract_entry_id(reference), "pdb_1000axyz")

    def test_numeric_zenodo_inputs_remain_unambiguous(self):
        self.assertIs(recognize_adapter("1234"), zenodo_adapter)
        self.assertIsNone(pdb_adapter.extract_entry_id("1234"))
        self.assertEqual(pdb_adapter.extract_entry_id("pdb:1234"), "1234")

    def test_other_resources_spoofed_hosts_and_version_files_are_rejected(self):
        for reference in (
            "0HHB", "4HHBB", "D_1000179340", "AF_AFP68871F1",
            "See PDB 4HHB", "https://rcsb.org.evil.test/structure/4HHB",
            "https://user:secret@rcsb.org/structure/4HHB",
            "https://rcsb.org:8443/structure/4HHB", "ftp://rcsb.org/structure/4HHB",
            "https://rcsb.org/structure/4HHB/1",
            "https://rcsb.org/structure/4HHB%2F1",
            "https://rcsb.org/structure/4H HB",
            "https://data.rcsb.org/rest/v1/core/polymer_entity/4HHB/1",
            "https://rcsb.org/rest/v1/core/entry/4HHB",
            "https://data.rcsb.org/structure/4HHB",
            "https://www.wwpdb.org/pdb?id=4HHB&id=2N5E",
            "https://www.wwpdb.org/pdb?id=4HHB&id=",
            "https://www.wwpdb.org/pdb", "https://example.org/structure/4HHB",
            "10.2210/pdb4hhb/pdb/extra", "10.2210/rcsb_pdb/mom_2026_1",
            "10.1016/0022-2836(84)90472-8",
            "https://files-versioned.wwpdb.org/pdb_00004hhb_xyz_v4-3.cif.gz",
        ):
            with self.subTest(reference=reference):
                self.assertFalse(pdb_adapter.can_handle(reference))

    def test_local_accession_syntax_does_not_require_an_integer(self):
        for value, valid in (("4HHB", True), ("pdb_00004hhb", True), (True, False), (4, False)):
            with self.subTest(value=value):
                scheme, actual, resolver = identifier_syntax(value, local_scheme="pdb:record-id")
                self.assertEqual((scheme, actual, resolver), ("pdb:record-id", valid, None))


class NativePDBMetadata(unittest.TestCase):
    def test_structure_doi_is_selected_by_database_not_list_position(self):
        data = entry("2n5e")
        # BMRB has its own DOI; move it before PDB to catch first-DOI selection.
        data["database_2"].reverse()
        results = pdb_adapter.evaluate(data)
        self.assertEqual(check(results, "M1", "Test-02")["value"], "10.2210/pdb2n5e/pdb")
        self.assertEqual(pdb_adapter.extract_structure_doi(data), "10.2210/pdb2n5e/pdb")
        self.assertNotEqual(
            check(results, "M1", "Test-02")["value"],
            data["rcsb_primary_citation"]["pdbx_database_id_DOI"],
        )

    def test_missing_structure_doi_is_not_replaced_by_article_or_bmrb(self):
        data = entry("2n5e")
        data["database_2"] = [item for item in data["database_2"] if item["database_id"] != "PDB"]
        results = pdb_adapter.evaluate(data)
        self.assertEqual(check(results, "M1", "Test-02")["status"], "FAIL")
        self.assertIsNone(pdb_adapter.extract_structure_doi(data))

    def test_missing_or_malformed_doi_values_preserve_other_local_checks(self):
        for value in (None, "doi:broken", 123):
            with self.subTest(value=value):
                data = entry()
                data["database_2"][0]["pdbx_DOI"] = value
                results = pdb_adapter.evaluate(data)
                self.assertEqual(check(results, "M1", "Test-02-01")["status"], "FAIL")
                self.assertEqual(check(results, "M2", "Test-01")["status"], "PASS")
                self.assertIsNone(pdb_adapter.extract_structure_doi(data))

    def test_response_identity_and_structure_doi_must_agree(self):
        with self.assertRaisesRegex(ValueError, "different entry"):
            pdb_adapter.evaluate(entry(), expected_entry_id="2N5E")
        data = entry()
        data["database_2"][0]["pdbx_DOI"] = "10.2210/pdb2n5e/pdb"
        with self.assertRaisesRegex(ValueError, "DOI does not identify"):
            pdb_adapter.evaluate(data)

    def test_non_pdb_and_missing_accessions_are_invalid_responses(self):
        for value in (None, "AF_AFP68871F1", "D_1000179340"):
            with self.subTest(value=value):
                data = entry()
                data["rcsb_id"] = value
                data["database_2"][0]["pdbx_DOI"] = "10.1234/publication"
                self.assertIsNone(pdb_adapter.extract_structure_doi(data))
                with self.assertRaises(ValueError):
                    pdb_adapter.evaluate(data)

    def test_creators_are_structure_authors_not_citation_authors(self):
        results = pdb_adapter.evaluate(entry())
        creators = check(results, "M6", "Test-01")
        self.assertEqual(creators["evidence"], ["Fermi, G.", "Perutz, M.F."])
        self.assertEqual(check(results, "M6", "Test-02")["status"], "FAIL")
        self.assertEqual(check(results, "M6", "Test-03")["status"], "FAIL")

    def test_every_structure_author_needs_their_own_valid_orcid(self):
        data = entry()
        for author in data["audit_author"]:
            author["pdbx_ORCID"] = "0000-0002-1825-0097"
        self.assertEqual(check(pdb_adapter.evaluate(data), "M6", "Test-02")["status"], "PASS")
        data["audit_author"][-1]["pdbx_ORCID"] = "?"
        self.assertEqual(check(pdb_adapter.evaluate(data), "M6", "Test-02")["status"], "FAIL")

    def test_comma_delimited_keywords_are_normalized_without_changing_raw_data(self):
        data = entry()
        data["struct_keywords"]["text"] = "Protein,  protein , ＰＲＯＴＥＩＮ, , DNA"
        before = copy.deepcopy(data)
        results = pdb_adapter.evaluate(data)
        self.assertEqual(check(results, "M4", "Test-01")["normalizedValue"], ["protein"] * 3 + ["dna"])
        self.assertEqual(check(results, "M4", "Test-02")["status"], "WARNING")
        self.assertEqual(data, before)

    def test_classification_uses_controlled_vocabulary_not_free_keywords(self):
        data = entry()
        results = pdb_adapter.evaluate(data)
        subject = check(results, "M5", "Test-01")
        self.assertEqual(subject["status"], "PASS")
        self.assertIn("mmcif.wwpdb.org", subject["evidence"][0]["sourceUrl"])
        for value, expected in (("DNA/RNA", "PASS"), ("UNLISTED HISTORICAL CLASS", "UNSURE"), ("", "FAIL")):
            data["struct_keywords"]["pdbx_keywords"] = value
            with self.subTest(value=value):
                self.assertEqual(check(pdb_adapter.evaluate(data), "M5", "Test-01")["status"], expected)

    def test_article_title_model_notes_and_method_do_not_fill_generic_fields(self):
        data = entry("2n5e")
        results = pdb_adapter.evaluate(data)
        for group in ("M3", "M8"):
            self.assertEqual(check(results, group, "Test-01")["status"], "UNSURE")
            self.assertIsNone(check(results, group, "Test-01")["value"])
        self.assertEqual(check(results, "M2", "Test-01")["value"], data["struct"]["title"])

    def test_organization_comes_from_record_provenance(self):
        data = entry()
        results = pdb_adapter.evaluate(data)
        self.assertEqual(check(results, "M7", "Test-01")["value"], ["BNL"])
        del data["pdbx_database_status"]["process_site"]
        self.assertEqual(check(pdb_adapter.evaluate(data), "M7", "Test-01")["status"], "FAIL")

    def test_revision_numbers_are_not_immutable_identifiers(self):
        results = pdb_adapter.evaluate(entry())
        self.assertEqual(check(results, "M1", "Test-03")["status"], "FAIL")
        self.assertIn("immutable", check(results, "M1", "Test-03")["message"])
        self.assertTrue(any(item["field"] == "rcsb_accession_info.minor_revision" for item in results))

    def test_entry_dates_are_compared_within_record_scope(self):
        data = entry()
        results = pdb_adapter.evaluate(data)
        dates = check(results, "M9", "Test-01")
        self.assertEqual({item["scope"] for item in dates["value"]}, {"record"})
        self.assertEqual(check(results, "M9", "Test-02")["status"], "PASS")
        data["rcsb_accession_info"]["deposit_date"] = "2027-01-01T00:00:00+00:00"
        self.assertEqual(check(pdb_adapter.evaluate(data), "M9", "Test-02")["status"], "FAIL")

    def test_xray_and_nmr_keep_the_same_scoring_contract(self):
        for entry_id in ("4hhb", "2n5e"):
            with self.subTest(entry=entry_id):
                data = entry(entry_id)
                results = pdb_adapter.evaluate(data)
                summary = _summarize_checks({"recordLevel": results, "aggregators": []})
                self.assertEqual((summary["score"], summary["maxScore"]), (9, 12))
                self.assertEqual(summary["maxBonusScore"], 4.5)
                scope = check(results, "PDB", "Scope")
                self.assertEqual(scope["maxPoints"], 0)
                self.assertIn("NMR", scope["message"])
                self.assertFalse(any(item["field"].endswith("resolution_combined") for item in results))
                json.dumps(results)


class PDBIntegration(unittest.TestCase):
    def test_fetch_preserves_raw_entry_and_looks_up_only_structure_doi(self):
        data = entry("2n5e")
        with (
            patch("src.clients.repository_client.fetch_json", return_value=data) as fetch,
            patch("src.clients.repository_client.verify_metadata_checks", side_effect=lambda items: items),
            patch("src.clients.repository_client.evaluate_aggregators", return_value=[]) as aggregators,
            patch("src.server.resolve_doi") as resolve,
        ):
            result = evaluate_reference("https://doi.org/10.2210/pdb2n5e/pdb")
        fetch.assert_called_once_with(f"{pdb_adapter.API_BASE_URL}/2N5E", service="RCSB PDB")
        aggregators.assert_called_once_with("10.2210/pdb2n5e/pdb")
        resolve.assert_not_called()
        self.assertIs(result["repositoryResponse"], data)
        self.assertEqual(result["repository"], "pdb")
        self.assertEqual(len(result["checks"]["repositoryLevel"]), len(pdb_adapter.RULES))
        json.dumps(result)

    def test_legacy_extended_alias_fetches_the_current_api_id(self):
        with (
            patch("src.clients.repository_client.fetch_json", return_value=entry()) as fetch,
            patch("src.clients.repository_client.verify_metadata_checks", side_effect=lambda items: items),
            patch("src.clients.repository_client.evaluate_aggregators", return_value=[]),
        ):
            pdb_adapter.fetch("pdb_00004hhb")
        self.assertEqual(fetch.call_args.args[0], f"{pdb_adapter.API_BASE_URL}/4HHB")

    def test_missing_structure_doi_does_not_fall_back_to_input_doi(self):
        data = entry()
        del data["database_2"][0]["pdbx_DOI"]
        with (
            patch("src.clients.repository_client.fetch_json", return_value=data),
            patch("src.clients.repository_client.verify_metadata_checks", side_effect=lambda items: items),
            patch("src.clients.repository_client.evaluate_aggregators", return_value=[]) as aggregators,
        ):
            pdb_adapter.fetch("10.2210/pdb4hhb/pdb")
        aggregators.assert_called_once_with(None)

    def test_unknown_doi_redirect_can_select_a_wwpdb_landing_page(self):
        with (
            patch("src.server.resolve_doi", return_value="https://www.wwpdb.org/pdb?id=pdb_00004hhb"),
            patch("src.adapters.pdb_adapter.fetch", return_value={"repository": "pdb"}) as fetch,
        ):
            self.assertEqual(evaluate_reference("10.1234/example"), {"repository": "pdb"})
        fetch.assert_called_once_with("https://www.wwpdb.org/pdb?id=pdb_00004hhb")

    def test_repository_http_failure_is_not_replaced_by_partial_results(self):
        error = HTTPError(f"{pdb_adapter.API_BASE_URL}/4HHB", 404, "Not Found", {}, None)
        self.addCleanup(error.close)
        with (
            patch("src.clients.repository_client.fetch_json", side_effect=error),
            patch("src.clients.repository_client.evaluate_aggregators") as aggregators,
            self.assertRaises(HTTPError),
        ):
            pdb_adapter.fetch("4HHB")
        aggregators.assert_not_called()

    def test_all_pdb_catalog_fields_have_reviewed_policy_evidence(self):
        results = evaluate_repository_checks("pdb", pdb_adapter.RULES)
        self.assertEqual(
            set(REPOSITORY_POLICIES["pdb"].fields), {rule.field for rule in pdb_adapter.RULES},
        )
        for result in results:
            self.assertTrue(result["sources"])
            self.assertEqual(result["reviewedAt"], "2026-10-02")
            self.assertNotIn("points", result)
        orcid = next(item for item in results if item["field"] == "audit_author[].pdbx_ORCID")
        self.assertEqual(orcid["status"], "WARNING")


if __name__ == "__main__":
    unittest.main()
