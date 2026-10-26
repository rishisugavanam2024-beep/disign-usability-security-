import pytest

from examples.flask_pytest.app import GRANTS, ROLES, create_app
from saferevoke.flask_testing import FlaskTestIntegration


@pytest.fixture
def state():
    return {"grants": {grant.id for grant in GRANTS}, "refunds": []}


@pytest.fixture
def app(state):
    return create_app(state)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def saferevoke_flask(app, state):
    return FlaskTestIntegration.for_dictionary(
        app, state, GRANTS,
        deny=lambda removed: state["grants"].difference_update(removed),
        roles=ROLES, capabilities={("users", "delete")},
        action_weights={"read": 1, "approve": 3, "delete": 5},
    )


@pytest.fixture(autouse=True)
def check_cleanup(request, state):
    yield
    if request.config.getoption("saferevoke_flask", default=False):
        assert state == {"grants": {grant.id for grant in GRANTS}, "refunds": []}
