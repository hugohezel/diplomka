"""Shared JSON requests to repository and aggregator APIs."""

import json
from typing import Any
from urllib.request import Request, urlopen

from ..utils.references import USER_AGENT


def fetch_json(
    url: str,
    *,
    service: str,
    timeout: int = 30,
    token: str | None = None,
) -> dict[str, Any]:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with urlopen(Request(url, headers=headers), timeout=timeout) as response:
        raw_response = response.read()

    try:
        data = json.loads(raw_response)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError(f"{service} didn't return valid JSON.") from error
    if not isinstance(data, dict):
        raise ValueError(f"{service} must return a JSON object.")
    return data
