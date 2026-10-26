"""Flask test-client connector; application permission/reset hooks are required."""
from saferevoke.adapters.web import WebAdapter


class FlaskAdapter(WebAdapter):
    def __init__(self, app, lab, hooks):
        enabled = app.config.get("TESTING") is True and app.config.get("SAFEREVOKE_TEST_ENVIRONMENT") is True
        super().__init__(lab, hooks, app.test_client, test_environment=enabled)
