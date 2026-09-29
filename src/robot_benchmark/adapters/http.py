"""JSON transport, with no retries of stateful operations."""
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def request_json(url, payload=None, headers=None, timeout=120, with_metadata=False):
    data = None if payload is None else json.dumps(payload, allow_nan=False).encode()
    request = Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urlopen(request, timeout=timeout) as response:
            value = json.load(response)
            metadata = {"status": response.status, "headers": dict(response.headers.items())}
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {body}") from error
    if not isinstance(value, dict):
        raise RuntimeError("server response must be a JSON object")
    if "error" in value:
        raise RuntimeError(str(value["error"]))
    return (value, metadata) if with_metadata else value
