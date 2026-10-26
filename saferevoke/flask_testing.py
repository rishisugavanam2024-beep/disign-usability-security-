"""Configuration for reusing an application's existing Flask pytest tests."""
from __future__ import annotations

from copy import deepcopy
from typing import Callable

from saferevoke.adapters.callback import StateHooks
from saferevoke.model import Grant, Lab


class FlaskTestIntegration:
    """The application's inventory and reset contract, supplied by one fixture.

    ``verify_restored(snapshot)`` must check the actual stores covered by the
    snapshot. Neither Flask TESTING nor this class provides database isolation.
    """

    def __init__(self, app, grants: list[Grant], hooks: StateHooks,
                 verify_restored: Callable, *, roles=None, capabilities=(),
                 action_weights=None):
        if app.config.get("TESTING") is not True or app.config.get("SAFEREVOKE_TEST_ENVIRONMENT") is not True:
            raise ValueError("Enable TESTING and SAFEREVOKE_TEST_ENVIRONMENT on an isolated Flask app")
        grants = list(grants)
        if not grants or len({grant.id for grant in grants}) != len(grants):
            raise ValueError("Supply nonempty, uniquely identified permission grants")
        if not callable(verify_restored):
            raise ValueError("Provide a state-restoration verifier")
        self.app, self.hooks, self.verify_restored = app, hooks, verify_restored
        universe = {(grant.resource, grant.action) for grant in grants
                    if grant.resource != "*" and grant.action != "*"}
        self.lab = Lab({grant.id: grant for grant in grants}, deepcopy(roles or {}), {}, set(),
                       universe | set(capabilities), deepcopy(action_weights or {}), {})

    @classmethod
    def from_store(cls, app, store):
        """Wire an explicitly supplied store using the documented method contract.

        Discovery is limited to this registered object. It does not search global
        objects, import application modules, or guess database tables.
        """
        if app.config.get("TESTING") is not True or app.config.get("SAFEREVOKE_TEST_ENVIRONMENT") is not True:
            raise ValueError("Connect registered stores only on an explicitly isolated test app")
        required = ("inventory", "snapshot", "remove_grants", "restore", "matches_snapshot")
        missing = [name for name in required if not callable(getattr(store, name, None))]
        if missing:
            raise ValueError(f"Permission store is missing methods: {', '.join(missing)}")
        metadata = {}
        for method, argument in (("user_roles", "roles"), ("capability_universe", "capabilities"),
                                 ("action_weights", "action_weights")):
            callback = getattr(store, method, None)
            if callback is not None:
                if not callable(callback):
                    raise ValueError(f"Store {method} must be callable")
                metadata[argument] = callback()
        return cls(app, store.inventory(),
                   StateHooks(store.snapshot, store.remove_grants, store.restore),
                   store.matches_snapshot, **metadata)

    @classmethod
    def from_registered_store(cls, app):
        """Use the one store explicitly registered in app.extensions."""
        store = app.extensions.get("saferevoke")
        if store is None:
            raise ValueError("Register your test permission store in app.extensions['saferevoke']")
        return cls.from_store(app, store)

    @classmethod
    def for_dictionary(cls, app, state: dict, grants: list[Grant], deny: Callable, **kwargs):
        """Convenience reset for self-contained, deepcopy-compatible Python stores.

        The application's denial callback still implements its real permission
        change. This does not restore databases, external effects, or references
        to removed/replaced objects held outside this dictionary.
        """
        if not isinstance(state, dict):
            raise TypeError("The dictionary helper requires a dictionary")

        def restore(snapshot):
            _restore_dict(state, snapshot)

        hooks = StateHooks(lambda: deepcopy(state), deny, restore)
        return cls(app, grants, hooks, lambda snapshot: state == snapshot, **kwargs)


def _restore_dict(target, snapshot):
    """Preserve common nested containers where possible while resetting values."""
    for key in set(target) - snapshot.keys():
        del target[key]
    for key, value in snapshot.items():
        current = target.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            _restore_dict(current, value)
        elif isinstance(current, set) and isinstance(value, set):
            current.clear()
            current.update(deepcopy(value))
        elif isinstance(current, list) and isinstance(value, list):
            current[:] = deepcopy(value)
        else:
            target[key] = deepcopy(value)
