"""JSON transport, with no retries of stateful operations."""
import json
from urllib.request import Request, urlopen


def request_json(url, payload=None, headers=None, timeout=120):
    data = None if payload is None else json.dumps(payload, allow_nan=False).encode()
    request = Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    with urlopen(request, timeout=timeout) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise RuntimeError("server response must be a JSON object")
    if "error" in value:
        raise RuntimeError(str(value["error"]))
    return value
