"""Bounded management-API permission stores for isolated identity-provider tests.

Inject request(method, path, json_body), returning decoded JSON or None for 204.
The application's authenticated transport owns base URL, timeout, TLS, token
refresh and rate limits. No credentials are read or stored by these connectors.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from urllib.parse import quote


class _DirectStore:
    def __init__(self, request, bindings, *, test_environment):
        if test_environment is not True:
            raise ValueError("Provider mutation requires an explicitly isolated test realm or tenant")
        self.request = request
        bindings = list(bindings)
        self.bindings = {item.grant_id: item for item in bindings}
        if not bindings or len(self.bindings) != len(bindings):
            raise ValueError("Provide uniquely identified permission bindings")
        if len({self._key(item) for item in bindings}) != len(bindings):
            raise ValueError("Duplicate provider assignments cannot have separate grant identifiers")
        for item in bindings:
            if not all(isinstance(value, str) and value for value in self._key(item)) or not item.grant_id:
                raise ValueError("Bindings must have nonempty string identifiers")

    def snapshot(self):
        # Read all targets before making any change. Stable copies prevent aliasing.
        return {grant_id: deepcopy(self._read(binding))
                for grant_id, binding in self.bindings.items()}

    def deny(self, grant_ids):
        if grant_ids - self.bindings.keys():
            raise ValueError("Unknown provider grant binding")
        for grant_id in sorted(grant_ids):
            binding = self.bindings[grant_id]
            existing = self._read(binding)
            if existing is not None:
                self._write(binding, existing, add=False)
                if self._read(binding) is not None:
                    raise RuntimeError("Provider removal was not observed; stopping the experiment")

    def restore(self, snapshot):
        if set(snapshot) != set(self.bindings):
            raise ValueError("Provider snapshot does not match configured bindings")
        # Attempt every binding even if one restore fails; never hide the failure.
        failures = []
        for grant_id, binding in self.bindings.items():
            try:
                current, original = self._read(binding), snapshot[grant_id]
                if original is not None and current is None:
                    self._write(binding, deepcopy(original), add=True)
                elif original is None and current is not None:
                    self._write(binding, current, add=False)
                if (self._read(binding) is None) != (original is None):
                    raise RuntimeError("Provider assignment restoration was not observed")
            except Exception:
                failures.append(grant_id)
        if failures:
            raise RuntimeError(f"Provider restoration failed for bindings: {sorted(failures)}")


@dataclass(frozen=True)
class KeycloakRoleBinding:
    grant_id: str
    user_id: str
    role_id: str
    client_uuid: str | None = None


class KeycloakRoleStore(_DirectStore):
    """Remove/restore selected direct user realm or client-role assignments.

    Group membership and composite-role expansion are not modified. Existing
    tokens may still contain the removed role; refreshing test credentials belongs
    in the application's deny/restore hooks, not in this store.
    """

    def __init__(self, request, realm: str, bindings, *, test_environment=False):
        if not isinstance(realm, str) or not realm or realm == "master":
            raise ValueError("Select a dedicated test realm, not the administrative master realm")
        self.realm = realm
        super().__init__(request, bindings, test_environment=test_environment)

    def _key(self, binding):
        return (binding.user_id, binding.client_uuid or "realm", binding.role_id)

    def _path(self, binding):
        suffix = "realm" if binding.client_uuid is None else "clients/" + quote(binding.client_uuid, safe="")
        return (f"/admin/realms/{quote(self.realm, safe='')}/users/"
                f"{quote(binding.user_id, safe='')}/role-mappings/{suffix}")

    def _read(self, binding):
        roles = self.request("GET", self._path(binding), None)
        if not isinstance(roles, list) or not all(isinstance(item, dict) and isinstance(item.get("id"), str) for item in roles):
            raise ValueError("Invalid Keycloak direct role mapping response")
        return next((deepcopy(item) for item in roles if item["id"] == binding.role_id), None)

    def _write(self, binding, value, *, add):
        self.request("POST" if add else "DELETE", self._path(binding), [value])


@dataclass(frozen=True)
class Auth0PermissionBinding:
    grant_id: str
    user_id: str
    api_identifier: str
    permission_name: str


class Auth0PermissionStore(_DirectStore):
    """Remove/restore only directly assigned user permissions, preserving roles.

    Paginate effective permissions and require explicit DIRECT source evidence;
    missing source metadata is rejected rather than mistaken for a direct grant.
    """

    def __init__(self, request, bindings, *, test_environment=False):
        super().__init__(request, bindings, test_environment=test_environment)

    def _key(self, binding):
        return binding.user_id, binding.api_identifier, binding.permission_name

    def _path(self, binding):
        return f"/api/v2/users/{quote(binding.user_id, safe='')}/permissions"

    def _read(self, binding):
        for page in range(100):
            result = self.request("GET", self._path(binding) + f"?page={page}&per_page=100&include_totals=true", None)
            if (not isinstance(result, dict) or not isinstance(result.get("permissions"), list)
                    or type(result.get("total")) is not int or result["total"] < 0):
                raise ValueError("Invalid paginated Auth0 permissions response")
            permissions = result["permissions"]
            for item in permissions:
                if not isinstance(item, dict):
                    raise ValueError("Invalid Auth0 permission entry")
                if (item.get("resource_server_identifier") == binding.api_identifier
                        and item.get("permission_name") == binding.permission_name):
                    sources = item.get("sources")
                    if (not isinstance(sources, list) or not sources
                            or not all(isinstance(source, dict) and isinstance(source.get("source_type"), str) for source in sources)):
                        raise ValueError("Auth0 permission source evidence is required")
                    if any(source["source_type"] == "DIRECT" for source in sources):
                        return {"resource_server_identifier": binding.api_identifier,
                                "permission_name": binding.permission_name}
                    return None
            if (page + 1) * 100 >= result["total"]:
                return None
            if len(permissions) != 100:
                raise ValueError("Auth0 returned incomplete pagination; refusing uncertain mutation")
        raise ValueError("Auth0 pagination limit exceeded; no absence assumption was made")

    def _write(self, binding, value, *, add):
        self.request("POST" if add else "DELETE", self._path(binding), {"permissions": [value]})
