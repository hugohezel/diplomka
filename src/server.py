import json
import sys
from http.client import HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

if __name__ == "__main__" and not __package__:
    # Support direct execution as well as `python -m src.server`.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "src"

from .adapters import dryad_adapter, figshare_adapter, pdb_adapter, zenodo_adapter
from .utils.references import DOI_HOSTS, extract_doi, resolve_doi


HOST = "0.0.0.0"
PORT = 8080
MAX_REQUEST_BODY_SIZE = 64 * 1024
HTML_PAGE = Path(__file__).with_name("index.html").read_text(encoding="utf-8")
ADAPTERS = (zenodo_adapter, dryad_adapter, figshare_adapter, pdb_adapter)
SERVICE_NAMES = {
    host: adapter.DISPLAY_NAME for adapter in ADAPTERS for host in adapter.HOSTS
}
SERVICE_NAMES.update({host: "DOI resolver" for host in DOI_HOSTS})


class ClientInputError(ValueError):
    """Raised when the submitted reference cannot be processed."""


def recognize_adapter(reference: str) -> ModuleType | None:
    return next((adapter for adapter in ADAPTERS if adapter.can_handle(reference)), None)


def evaluate_reference(reference: str) -> dict[str, Any]:
    adapter = recognize_adapter(reference)
    if adapter is None:
        doi = extract_doi(reference)
        if doi is not None:
            reference = resolve_doi(doi)
            adapter = recognize_adapter(reference)

    if adapter is None:
        raise ClientInputError(
            "Supported records are Zenodo, Dryad, Figshare and RCSB PDB. "
            "Provide DOI, record URL or PDB accession."
        )
    return adapter.fetch(reference)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/":
            self._send_html(200, HTML_PAGE)
            return
        self._send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/evaluate":
            self._send_json(404, {"error": "Not found"})
            return

        try:
            body = self._read_json_body()
            reference = body.get("reference")
            if not isinstance(reference, str) or not reference.strip():
                raise ClientInputError("Enter a DOI, record URL or PDB accession.")

            self._send_json(200, evaluate_reference(reference.strip()))
        except ClientInputError as error:
            self._send_json(400, {"error": str(error)})
        except HTTPError as error:
            service = SERVICE_NAMES.get(urlsplit(error.url).hostname, "Repository")
            status = 404 if error.code == 404 else 502
            self._send_json(status, {"error": f"{service} returned HTTP {error.code}."})
            error.close()
        except (URLError, TimeoutError, ConnectionError, HTTPException):
            self._send_json(
                502, {"error": "Repository or DOI resolver is currently unavailable."}
            )
        except (TypeError, ValueError) as error:
            self._send_json(502, {"error": f"Invalid service response: {error}"})

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
