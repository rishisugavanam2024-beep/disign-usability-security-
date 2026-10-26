"""Language-neutral connector to a loopback-only, authenticated test harness."""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, ProxyHandler, build_opener

from saferevoke.model import AccessEvent, WorkflowRun


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HTTPAdapter:
    """Run Node.js, Java, or other apps through the saferevoke.v1 protocol.

    This requires an application-owned test harness. It does not turn arbitrary
    websites into test harnesses, and it does not expose an admin API itself.
    """

    def __init__(self, lab, base_url: str, *, token: str, test_environment=False,
                 timeout=10, max_response_bytes=2_000_000):
        parsed = urlsplit(base_url)
        if test_environment is not True:
            raise ValueError("Explicitly enable an isolated test environment")
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1"}
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("Test harness URL must be HTTP on a literal loopback address")
        if not isinstance(token, str) or len(token) < 32 or "\n" in token or "\r" in token:
            raise ValueError("Provide a test harness token of at least 32 characters")
        if timeout <= 0 or max_response_bytes <= 0:
            raise ValueError("Positive timeout and response size limit are required")
        self.lab, self.base_url, self._token = lab, base_url.rstrip("/"), token
        self.timeout, self.max_response_bytes = timeout, max_response_bytes
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())
        metadata = self._request("GET", "/capabilities")
        if (not isinstance(metadata, dict) or metadata.get("protocol") != "saferevoke.v1"
                or metadata.get("test_environment") is not True):
            raise ValueError("Server did not identify itself as a v1 isolated test harness")

    def _request(self, method, path, body=None):
        request = Request(
            self.base_url + path, method=method,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers={"Authorization": "Bearer " + self._token,
                     "Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                data = response.read(self.max_response_bytes + 1)
        except HTTPError as error:
            status = error.code
            error.close()
            raise RuntimeError(f"Test harness returned HTTP {status}; no retry was attempted") from None
        except (URLError, TimeoutError) as error:
            raise RuntimeError("Test harness unavailable; no mutation retry was attempted") from error
        if len(data) > self.max_response_bytes:
            raise ValueError("Test harness response exceeds configured size limit")
        return json.loads(data)

    def snapshot(self):
        response = self._request("POST", "/snapshot", {})
        if not isinstance(response, dict) or not isinstance(response.get("snapshot"), str) or not response["snapshot"]:
            raise ValueError("Server must return an opaque snapshot identifier")
        return response["snapshot"]

    def deny(self, grant_ids):
        if grant_ids - self.lab.grants.keys():
            raise ValueError("Unknown grants")
        self._request("POST", "/deny", {"grant_ids": sorted(grant_ids)})

    def run(self, workflow):
        response = self._request("POST", "/run", {"workflow_id": workflow.id})
        return decode_run(response, workflow, self.lab)

    def restore(self, snapshot):
        self._request("POST", "/restore", {"snapshot": snapshot})


def decode_run(response, workflow, lab):
    """Validate traces returned by language-neutral test runners."""
    if (not isinstance(response, dict) or response.get("workflow_id") != workflow.id
            or type(response.get("success")) is not bool
            or not isinstance(response.get("output"), str)
            or not isinstance(response.get("events"), list)
            or not isinstance(response.get("message"), str)
            or not isinstance(response.get("side_effects", {}), dict)
            or not isinstance(response.get("validation_errors", []), list)
            or not all(isinstance(item, str) for item in response.get("validation_errors", []))):
        raise ValueError("Invalid workflow response from test harness")
    events = []
    errors = list(response.get("validation_errors", []))
    for item in response["events"]:
        if (not isinstance(item, dict) or item.get("workflow") != workflow.id
                or type(item.get("allowed")) is not bool
                or not all(isinstance(item.get(key), str) and item[key] for key in ("identity", "resource", "action"))
                or not isinstance(item.get("grant_ids"), list)
                or not all(isinstance(value, str) for value in item["grant_ids"])
                or not all(isinstance(item.get(key, ""), str) for key in ("checkpoint", "phase", "note"))
                or type(item.get("ordinal", 0)) is not int
                or item.get("ordinal", 0) < 0 or (not item["allowed"] and item["grant_ids"])):
            raise ValueError("Invalid access event from test harness")
        for grant_id in item["grant_ids"]:
            grant = lab.grants.get(grant_id)
            if grant is None or grant.resource not in (item["resource"], "*") or grant.action not in (item["action"], "*"):
                raise ValueError("Test harness returned an unknown or mismatched grant")
            principal_matches = ((grant.principal_type == "identity" and grant.principal == item["identity"])
                                 or (grant.principal_type == "role" and grant.principal in lab.roles.get(item["identity"], set())))
            if not principal_matches:
                raise ValueError("Test harness grant does not belong to the traced identity")
        if item["allowed"] and not item["grant_ids"]:
            errors.append("Allowed access has no inventoried grant source")
        try:
            events.append(AccessEvent(**item))
        except TypeError:
            raise ValueError("Invalid access event fields from test harness") from None
    return WorkflowRun(workflow.id, response["success"] and not errors,
                       response["output"], events, response["message"],
                       response.get("side_effects", {}), errors)
