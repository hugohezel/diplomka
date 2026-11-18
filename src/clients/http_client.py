"""Shared JSON requests to repository and aggregator APIs."""

import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..utils.references import USER_AGENT


def fetch_json(
    url: str,
    *,
    service: str,
    timeout: int = 30,
    token: str | None = None,
    accept: str = "application/json",
    user_agent: str = USER_AGENT,
    form: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = {"Accept": accept, "User-Agent": user_agent}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if form is not None:
        data = urlencode(form).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    with urlopen(Request(url, data=data, headers=headers), timeout=timeout) as response:
        raw_response = response.read()

    try:
        data = json.loads(raw_response)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError(f"{service} didn't return valid JSON.") from error
    if not isinstance(data, dict):
        raise ValueError(f"{service} must return a JSON object.")
    return data
