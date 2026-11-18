"""Exercise streamed progress through the real adapters and HTTP handler, offline."""

import json
import sys
import threading
import unittest
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import server
from src.adapters import icpsr_adapter, mast_adapter, metabolights_adapter, opencontext_adapter
from src.clients import llm_client, repository_client
from src.searchability.lookups import LookupService
from src.utils import aggregator_checks


ZENODO_RECORD = {
    "id": 123,
    "metadata": {"title": "River temperature observations", "description": "Daily river temperature measurements."},
}
ICPSR_RECORD = {"data": {"id": "10.3886/icpsr123.v1", "attributes": {"doi": "10.3886/icpsr123.v1"}}}
OPENCONTEXT_RECORD = {"id": "https://opencontext.org/subjects/00112233-4455-6677-8899-aabbccddeeff", "@context": {}}
MAST_OBSERVATION = {"status": "COMPLETE", "data": [{"obsid": "123"}], "paging": {"rowsFiltered": 1}}
METABOLIGHTS_RECORD = {"isaInvestigation": {"identifier": "MTBLS1", "studies": [{"identifier": "MTBLS1"}]}}


def semantic_response(task, fields, **kwargs):
    return {"coverage": "complete", "items": []}


@contextmanager
def offline_services(semantic=semantic_response):
    with ExitStack() as stack:
        for module, value in (
            (repository_client, ZENODO_RECORD),
            (icpsr_adapter, ICPSR_RECORD),
            (opencontext_adapter, OPENCONTEXT_RECORD),
            (metabolights_adapter, METABOLIGHTS_RECORD),
        ):
            stack.enter_context(patch.object(module, "fetch_json", side_effect=lambda *args, record=value, **kwargs: deepcopy(record)))
        stack.enter_context(patch.object(mast_adapter, "_invoke", return_value=MAST_OBSERVATION))
        stack.enter_context(patch.object(mast_adapter, "_products", return_value=([], True, None)))
        stack.enter_context(patch.object(llm_client, "evaluate_task", side_effect=semantic))
        stack.enter_context(patch.object(LookupService, "lookup", return_value=[]))
        stack.enter_context(patch.object(aggregator_checks, "find_in_openaire", return_value=("record", "https://example.test/openaire")))
        stack.enter_context(patch.object(aggregator_checks, "find_in_openalex", return_value=("record", "https://example.test/openalex")))
        yield


class AdapterProgressTests(unittest.TestCase):
    def test_all_repositories_emit_ordered_progress_and_unchanged_results(self):
        with offline_services():
            for repository, reference in (
                ("zenodo", "123"),
                ("icpsr", "10.3886/ICPSR123.v1"),
                ("opencontext", OPENCONTEXT_RECORD["id"]),
                ("mast", "123"),
                ("metabolights", "MTBLS1"),
            ):
                with self.subTest(repository=repository):
                    events = []
                    result = server.evaluate_reference(reference, repository, on_event=events.append)
                    self.assertEqual(events[0]["event"], "record_loaded")
                    self.assertEqual(events[0]["catalogue"]["repository"], repository)
                    checks = result["checks"]["recordLevel"]
                    self.assertEqual(len(checks), 26)
                    progress = events[1:53]
                    for index, check in enumerate(checks):
                        self.assertEqual(progress[index * 2], {"event": "check_started", "testId": check["testId"]})
                        self.assertEqual(progress[index * 2 + 1], {"event": "check_finished", "check": check})
                    self.assertEqual(sum(event["event"] == "aggregator_finished" for event in events), 2)

    def test_fast_aggregator_is_reported_before_slow_aggregator(self):
        release = threading.Event()
        finished = []

        def slow_lookup(doi):
            if not release.wait(2):
                raise AssertionError("The faster aggregator was buffered behind the slower one.")
            return "slow", "https://example.test/slow"

        def on_event(event):
            if event["event"] == "aggregator_finished":
                finished.append(event["check"]["label"])
                release.set()

        with patch.object(aggregator_checks, "find_in_openaire", side_effect=slow_lookup), patch.object(
            aggregator_checks, "find_in_openalex", return_value=("fast", "https://example.test/fast")
        ):
            try:
                results = aggregator_checks.evaluate_aggregators("10.1234/example", on_event=on_event)
            finally:
                release.set()
        self.assertEqual(finished, ["Discoverable in OpenAlex", "Discoverable in OpenAIRE"])
        self.assertEqual([result["label"] for result in results], ["Discoverable in OpenAIRE", "Discoverable in OpenAlex"])


class QuietHandler(server.Handler):
    def log_message(self, *args):
        pass


class StreamingHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=3)

    def request(self, body, accept="application/x-ndjson"):
        connection = HTTPConnection(*self.httpd.server_address, timeout=5)
        self.addCleanup(connection.close)
        connection.request("POST", "/evaluate", body=json.dumps(body), headers={"Content-Type": "application/json", "Accept": accept})
        return connection.getresponse()

    def test_progress_arrives_while_llm_is_still_blocked(self):
        release = threading.Event()
        entered = threading.Event()

        def blocked_semantic(task, fields, **kwargs):
            if task["id"] == "G2.2":
                entered.set()
                if not release.wait(4):
                    raise AssertionError("The client did not receive progress before inference finished.")
            return semantic_response(task, fields, **kwargs)

        with offline_services(blocked_semantic):
            try:
                response = self.request({"reference": "123", "repository": "zenodo"})
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader("Content-Type"), "application/x-ndjson; charset=utf-8")
                self.assertEqual(response.getheader("X-Accel-Buffering"), "no")
                events = []
                while True:
                    event = json.loads(response.readline())
                    events.append(event)
                    if event == {"event": "check_started", "testId": "G2.2"}:
                        break
                self.assertTrue(entered.wait(1))
                self.assertEqual(sum(event["event"] == "check_finished" for event in events), 3)
                self.assertFalse(release.is_set())
                release.set()
                events.extend(json.loads(line) for line in response if line.strip())
            finally:
                release.set()
        self.assertEqual(events[-1]["event"], "evaluation_finished")
        self.assertEqual(len(events[-1]["result"]["checks"]["recordLevel"]), 26)

    def test_invalid_input_keeps_http_error_response(self):
        response = self.request({"reference": " "})
        self.assertEqual(response.status, 400)
        self.assertTrue(response.getheader("Content-Type").startswith("application/json"))
        self.assertIn("error", json.load(response))

    def test_error_after_progress_is_a_terminal_stream_event(self):
        def fail(reference, repository, *, on_event):
            on_event({"event": "check_started", "testId": "G2.2"})
            raise ValueError("Malformed upstream response")

        with patch.object(server, "evaluate_reference", side_effect=fail):
            response = self.request({"reference": "123"})
            events = [json.loads(line) for line in response if line.strip()]
        self.assertEqual(response.status, 200)
        self.assertEqual(events[-1], {"event": "evaluation_error", "error": "Invalid service response: Malformed upstream response"})
        self.assertFalse(any(event["event"] == "evaluation_finished" for event in events))

    def test_json_clients_still_receive_a_complete_result(self):
        with offline_services():
            response = self.request({"reference": "123", "repository": "zenodo"}, "application/json")
            result = json.load(response)
        self.assertEqual(response.status, 200)
        self.assertEqual(len(result["checks"]["recordLevel"]), 26)
        self.assertEqual(len(result["checks"]["aggregators"]), 2)


if __name__ == "__main__":
    unittest.main()
