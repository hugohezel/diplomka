import json
import sys
from http.client import HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

if __name__ == "__main__" and not __package__:
    # Support direct execution as well as `python -m src.server`.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "src"

from .adapters import (
    cern_open_data_adapter, ena_adapter, gbif_adapter, mast_adapter, metabolights_adapter,
    nomad_central_adapter, opencontext_adapter, openml_adapter, openneuro_adapter,
    pangaea_adapter, zenodo_adapter,
)
from .utils.references import DOI_HOSTS, extract_doi, resolve_doi
from .searchability.evaluator import describe_translation
from .searchability.profile import load_translation


HOST = "0.0.0.0"
PORT = 8080
MAX_REQUEST_BODY_SIZE = 64 * 1024
HTML_PAGE = Path(__file__).with_name("index.html").read_text(encoding="utf-8")
ADAPTERS = {adapter.REPOSITORY: adapter for adapter in (
    cern_open_data_adapter, ena_adapter, gbif_adapter, mast_adapter, metabolights_adapter,
    nomad_central_adapter, opencontext_adapter, openml_adapter, openneuro_adapter,
    pangaea_adapter, zenodo_adapter,
)}
SERVICE_NAMES = {host: adapter.DISPLAY_NAME for adapter in ADAPTERS.values() for host in adapter.HOSTS}
SERVICE_NAMES.update({host: "EMBL-EBI" for host in ena_adapter.HOSTS & metabolights_adapter.HOSTS})
SERVICE_NAMES.update({host: "DOI resolver" for host in DOI_HOSTS})


class ClientInputError(ValueError):
    """Raised when the submitted reference cannot be processed."""


def _matching_adapters(reference, candidates):
    return [adapter for adapter in candidates if adapter.can_handle(reference)]


def evaluate_reference(reference: str, repository: str = "auto", *, on_event=None) -> dict[str, Any]:
    if not isinstance(repository, str) or repository not in {"auto", *ADAPTERS}:
        raise ClientInputError("Unknown repository.")
    reference = reference.strip()
    requested_reference = reference
    candidates = ADAPTERS.values() if repository == "auto" else (ADAPTERS[repository],)
    matches = _matching_adapters(reference, candidates)
    if len(matches) != 1 and (doi := extract_doi(reference)) is not None:
        reference = resolve_doi(doi)
        matches = _matching_adapters(reference, candidates)
    if not matches:
        raise ClientInputError(
            "No supported repository recognizes this reference. Enter a DOI, full record URL or repository-prefixed identifier."
        )
    if len(matches) > 1:
        prefixes = ", ".join(f"{adapter.REPOSITORY}:" for adapter in matches)
        raise ClientInputError(
            "This identifier matches multiple repositories. Enter its record URL or DOI, "
            f"or add one of these prefixes to the ID ({prefixes})."
        )
    return matches[0].fetch(reference, requested_reference=requested_reference, on_event=on_event)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/":
            self._send_html(200, HTML_PAGE)
            return
        if path in {"/styles.css", "/ui.js"}:
            mime = "text/css" if path.endswith(".css") else "text/javascript"
            self._send_response(200, mime + "; charset=utf-8", Path(__file__).with_name(path[1:]).read_bytes())
            return
        if path == "/catalogue":
            repository = parse_qs(urlsplit(self.path).query).get("repository", ["zenodo"])[0]
            if repository == "auto":
                self._send_json(200, describe_translation())
                return
            adapter = ADAPTERS.get(repository)
            if adapter is None:
                self._send_json(400, {"error": "Unknown repository."})
                return
            self._send_json(200, describe_translation(load_translation(adapter.CHECKS_PATH)))
            return
        if path == "/translation-schema":
            path = Path(__file__).parent / "searchability" / "translation.schema.json"
            self._send_json(200, json.loads(path.read_text(encoding="utf-8")))
            return
        self._send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/evaluate":
            self._send_json(404, {"error": "Not found"})
            return

        self._evaluation_stream_started = False
        try:
            self._evaluate()
        except (BrokenPipeError, ConnectionResetError):
            # Stop evaluating when the browser closes its streaming connection.
            return

    def _evaluate(self) -> None:
        try:
            body = self._read_json_body()
            reference = body.get("reference")
            if not isinstance(reference, str) or not reference.strip():
                raise ClientInputError("Enter a DOI, record URL or repository accession.")

            streaming = "application/x-ndjson" in self.headers.get("Accept", "").lower()
            result = evaluate_reference(
                reference.strip(), body.get("repository", "auto"),
                on_event=self._send_evaluation_event if streaming else None,
            )
            if streaming:
                self._send_evaluation_event({"event": "evaluation_finished", "result": result})
            else:
                self._send_json(200, result)
        except (BrokenPipeError, ConnectionResetError):
            raise
        except ClientInputError as error:
            self._send_evaluation_error(400, str(error))
        except HTTPError as error:
            service = SERVICE_NAMES.get(urlsplit(error.url).hostname, "Repository")
            status = 404 if error.code == 404 else 502
            message = f"{service} returned HTTP {error.code}."
            error.close()
            self._send_evaluation_error(status, message)
        except (URLError, TimeoutError, ConnectionError, HTTPException):
            self._send_evaluation_error(502, "Repository or DOI resolver is currently unavailable.")
        except (TypeError, ValueError) as error:
            self._send_evaluation_error(502, f"Invalid service response: {error}")
        except Exception as error:
            self.log_error("Unexpected evaluation error: %s", type(error).__name__)
            self._send_evaluation_error(500, "Evaluation failed unexpectedly.")

    def _send_evaluation_event(self, event: dict[str, Any]) -> None:
        body = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        if not self._evaluation_stream_started:
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-transform")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            self._evaluation_stream_started = True
        self.wfile.write(body)
        self.wfile.flush()

    def _send_evaluation_error(self, status: int, message: str) -> None:
        if self._evaluation_stream_started:
            self._send_evaluation_event({"event": "evaluation_error", "error": message})
        else:
            self._send_json(status, {"error": message})

    def _read_json_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ClientInputError("Invalid request body length.") from error

        if length < 0:
            raise ClientInputError("Invalid request body length.")
        if length > MAX_REQUEST_BODY_SIZE:
            raise ClientInputError("The request is too large.")

        raw_body = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ClientInputError("The request body is not valid JSON.") from error
        if not isinstance(body, dict):
            raise ClientInputError("The request body must be a JSON object.")
        return body

    def _send_html(self, status: int, body: str) -> None:
        self._send_response(status, "text/html; charset=utf-8", body.encode("utf-8"))

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body, indent=2, ensure_ascii=False).encode("utf-8")
        self._send_response(status, "application/json; charset=utf-8", encoded)

    def _send_response(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.client_address[0]} - {format % args}")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Server listening on {HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
