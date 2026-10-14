"""ORCID resolution, per-author surname comparisons and record integration."""

import copy
import json
import unittest
from unittest.mock import patch

from src.adapters import dryad_adapter, figshare_adapter, pdb_adapter, zenodo_adapter
from src.clients.repository_client import fetch_and_evaluate
from src.utils.metadata_verification import _verify_payload, verify_metadata_checks


ORCID = "0000-0002-1825-0097"
ORCID_URL = f"https://pub.orcid.org/v3.0/{ORCID}/person"


def surname_check(checks):
    return next(
        item for item in checks
        if (item.get("group"), item["testId"]) in {
            ("M6", "Test-02-01"), ("G06", "agent_identifier.orcid_name_consistent"),
        }
    )


def person_response(surname="Carberry"):
    return {
        "status": "PASS",
        "targetUrl": ORCID_URL,
        "data": {"name": {"family-name": {"value": surname}}},
    }


def creator_checks(authors):
    return zenodo_adapter.evaluate({"metadata": {"creators": authors}})


class ORCIDNames(unittest.TestCase):
    def test_each_repository_maps_its_author_name_and_orcid(self):
        cases = [
            (zenodo_adapter, {"metadata": {"creators": [{
                "name": " Carberry , J.", "orcid": f"https://orcid.org/{ORCID}",
            }]}}),
            (dryad_adapter, {"id": 1, "authors": [{
                "firstName": "Josiah", "lastName": "CARBERRY", "orcid": ORCID,
            }]}),
            (figshare_adapter, {"id": 1, "authors": [{
                "full_name": "Josiah Carberry", "orcid_id": ORCID,
            }]}),
            (pdb_adapter, {"rcsb_id": "4HHB", "audit_author": [{
                "name": "Carberry, J.", "pdbx_ORCID": ORCID,
            }]}),
        ]
        for adapter, metadata in cases:
            with self.subTest(repository=adapter.REPOSITORY):
                original = copy.deepcopy(metadata)
                local = surname_check(adapter.evaluate(metadata))
                self.assertEqual(local["status"], "UNSURE")
                with patch(
                    "src.utils.metadata_verification._request",
                    return_value=person_response(),
                ) as request:
                    result = surname_check(verify_metadata_checks([local]))
                request.assert_called_once_with(ORCID_URL, resolve=False)
                self.assertEqual(result["status"], "PASS")
                self.assertEqual(result["kind"], "diagnostic")
                self.assertEqual((result["points"], result["maxPoints"]), (0, 0))
                evidence = result["evidence"][0]
                self.assertEqual(evidence["orcidSurname"], "Carberry")
                self.assertEqual(evidence["sourceUrl"], ORCID_URL)
                self.assertNotIn("verification", json.dumps(result))
                self.assertIn("verification", local["evidence"][0])
                self.assertEqual(metadata, original)

    def test_surname_matching_normalizes_unicode_case_and_spacing(self):
        cases = [
            ("Novák, J.", "NOVA\u0301K", "PASS"),
            ("Ｃａｒｂｅｒｒｙ, J.", "Carberry", "PASS"),
            ("de   la Cruz, A.", "DE LA CRUZ", "PASS"),
            ("Ana de la Cruz", "de  la Cruz", "PASS"),
            ("Anne Smith-Jones", "Smith-Jones", "PASS"),
            ("Smithson, J.", "Smith", "FAIL"),
            ("John Smithson", "Smith", "FAIL"),
            ("Carberry, J.", "Smith", "FAIL"),
            ("Novak, J.", "Novák", "FAIL"),
            ("Jan Vries", "de Vries", "FAIL"),
        ]
        for metadata_name, orcid_surname, expected in cases:
            with self.subTest(name=metadata_name, surname=orcid_surname):
                local = surname_check(creator_checks([{
                    "name": metadata_name, "orcid": ORCID,
                }]))
                with patch(
                    "src.utils.metadata_verification._request",
                    return_value=person_response(orcid_surname),
                ):
                    result = surname_check(verify_metadata_checks([local]))
                self.assertEqual(result["status"], expected)

    def test_same_orcid_is_fetched_once_but_each_author_is_compared(self):
        local = surname_check(creator_checks([
            {"name": "Carberry, J.", "orcid": ORCID},
            {"name": "Smith, J.", "orcid": f"http://orcid.org/{ORCID}"},
        ]))
        with patch(
            "src.utils.metadata_verification._request", return_value=person_response(),
        ) as request:
            result = surname_check(verify_metadata_checks([local]))
        request.assert_called_once_with(ORCID_URL, resolve=False)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual([item["status"] for item in result["evidence"]], ["PASS", "FAIL"])
        self.assertEqual([item["authorIndex"] for item in result["evidence"]], [0, 1])

    def test_absent_or_invalid_orcids_are_retained_without_requests(self):
        for value, expected in (
            (None, "UNSURE"), ("", "UNSURE"), ("  ", "UNSURE"),
            ("0000-0002-1825-0098", "FAIL"),
            ("https://evil.example/0000-0002-1825-0097", "FAIL"),
            ({"orcid": ORCID}, "FAIL"),
        ):
            with self.subTest(value=value):
                local = surname_check(creator_checks([{"name": "Carberry", "orcid": value}]))
                with patch("src.utils.metadata_verification._request") as request:
                    result = surname_check(verify_metadata_checks([local]))
                request.assert_not_called()
                self.assertEqual(result["status"], expected)
                self.assertEqual(result["evidence"][0]["orcid"], value)
        for authors in ([], [None]):
            result = surname_check(creator_checks(authors))
            self.assertEqual(result["status"], "UNSURE")

    def test_one_unverifiable_author_prevents_a_record_pass(self):
        local = surname_check(creator_checks([
            {"name": "Carberry, J.", "orcid": ORCID},
            {"name": "Smith, J."},
        ]))
        with patch(
            "src.utils.metadata_verification._request", return_value=person_response(),
        ):
            result = surname_check(verify_metadata_checks([local]))
        self.assertEqual(result["status"], "UNSURE")
        self.assertEqual([item["status"] for item in result["evidence"]], ["PASS", "UNSURE"])

    def test_missing_metadata_surname_is_not_replaced_by_given_name(self):
        cases = [
            surname_check(dryad_adapter.evaluate({"id": 1, "authors": [{
                "firstName": "Carberry", "orcid": ORCID,
            }]})),
            surname_check(creator_checks([{"orcid": ORCID}])),
            surname_check(creator_checks([{"name": ", J.", "orcid": ORCID}])),
        ]
        for local in cases:
            with patch(
                "src.utils.metadata_verification._request", return_value=person_response(),
            ):
                result = surname_check(verify_metadata_checks([local]))
            self.assertEqual(result["status"], "UNSURE")
            self.assertEqual(result["evidence"][0]["orcidSurname"], "Carberry")

    def test_private_missing_and_malformed_public_names_are_unsure(self):
        spec = {"kind": "orcid-name", "name": "Carberry, J.", "surname": "Carberry"}
        for data in (
            None, [], {}, {"name": None}, {"name": []},
            {"name": {}}, {"name": {"family-name": None}},
            {"name": {"family-name": "Carberry"}},
            {"name": {"family-name": {"value": ""}}},
            {"name": {"family-name": {"value": 123}}},
            {"name": {"given-names": {"value": "Carberry"}}},
        ):
            with self.subTest(data=data):
                result = _verify_payload(spec, {"status": "PASS", "data": data})
                self.assertEqual(result["status"], "UNSURE")

    def test_missing_orcid_and_service_failures_propagate_to_record(self):
        local = surname_check(creator_checks([{"name": "Carberry, J.", "orcid": ORCID}]))
        for status, message in (
            ("FAIL", "HTTP 404: target not found."),
            ("FAIL", "HTTP 410: target not found."),
            ("UNSURE", "HTTP 429: verification could not be completed."),
            ("UNSURE", "Verification unavailable: timed out"),
        ):
            with self.subTest(message=message):
                with patch(
                    "src.utils.metadata_verification._request",
                    return_value={"status": status, "message": message},
                ):
                    result = surname_check(verify_metadata_checks([local]))
                self.assertEqual(result["status"], status)
                self.assertEqual(result["evidence"][0]["message"], message)

    def test_new_check_reaches_record_response_without_changing_scores(self):
        metadata = {"id": 123, "metadata": {"creators": [{
            "name": "Carberry, J.", "orcid": ORCID,
        }]}}

        def response(url, *, resolve):
            if url == ORCID_URL:
                return person_response()
            return {"status": "UNSURE", "message": "Unavailable."}

        with (
            patch("src.clients.repository_client.fetch_json", return_value=metadata),
            patch("src.utils.metadata_verification._request", side_effect=response),
            patch("src.clients.repository_client.evaluate_aggregators", return_value=[]),
        ):
            result = fetch_and_evaluate(
                repository="zenodo", display_name="Zenodo",
                source_url="https://zenodo.org/api/records/123", reference="123",
                doi_field="doi", evaluator=zenodo_adapter.evaluate,
                rules=zenodo_adapter.RULES,
            )
        self.assertEqual(surname_check(result["checks"]["recordLevel"])["status"], "PASS")
        self.assertEqual(result["summary"]["profile"], "public_repository_api")
        self.assertNotIn("maxScore", result["summary"])
        self.assertNotIn("maxBonusScore", result["summary"])
        self.assertEqual(result["repositoryResponse"], metadata)


if __name__ == "__main__":
    unittest.main()
