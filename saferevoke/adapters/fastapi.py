"""FastAPI TestClient connector, including its application lifespan context."""
from saferevoke.adapters.web import WebAdapter


class FastAPIAdapter(WebAdapter):
    def __init__(self, app, lab, hooks):
        enabled = getattr(app.state, "saferevoke_test_environment", False) is True
        if not enabled:
            raise ValueError("Enable saferevoke_test_environment only on an isolated test app")
        try:
            from fastapi.testclient import TestClient
        except ImportError as error:
            raise ImportError("The FastAPI connector requires fastapi and httpx") from error
        super().__init__(lab, hooks, lambda: TestClient(app), test_environment=enabled)
