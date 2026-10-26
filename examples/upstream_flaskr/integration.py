"""Observe original Flaskr object ownership checks; never replace their decision.

Loaded explicitly for the pinned upstream tutorial's update/delete tests only.
No upstream application source or assertion is edited.
"""
from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from saferevoke.adapters.sqlite import SQLiteTestState
from saferevoke.adapters.web import record_access
from saferevoke.flask_testing import FlaskTestIntegration
from saferevoke.model import Grant


@pytest.fixture
def saferevoke_flask(app, monkeypatch):
    from flask import g
    from werkzeug.exceptions import Forbidden
    from flaskr import blog

    if app.config.get("TESTING") is not True:
        raise ValueError("Only the upstream isolated pytest application is supported")
    path = Path(app.config["DATABASE"]).resolve(strict=True)
    app.config["SAFEREVOKE_TEST_ENVIRONMENT"] = True
    grant_id = "flaskr:post:1:author:test"
    grant = Grant(grant_id, "test", "identity", "test", "post:1", "modify", "Author may edit/delete post 1")
    original = blog.get_post

    def observed(post_id, check_author=True):
        identity = str(g.user["username"]) if g.user is not None else "anonymous"
        try:
            post = original(post_id, check_author=check_author)
        except Forbidden:
            if check_author:
                record_access(identity, f"post:{post_id}", "modify", False)
            raise
        if check_author:
            record_access(identity, f"post:{post_id}", "modify", True,
                          [grant_id] if post_id == 1 and identity == "test" else [])
        return post

    monkeypatch.setattr(blog, "get_post", observed)

    def deny(ids):
        if ids != {grant_id}:
            raise ValueError("Unknown upstream fixture ownership grant")
        with closing(sqlite3.connect(path)) as connection:
            # The upstream suite itself uses this ownership change to test 403.
            connection.execute("UPDATE post SET author_id=2 WHERE id=1")
            connection.commit()

    state = SQLiteTestState(path, test_root=path.parent, remove_grants=deny, test_environment=True)
    return FlaskTestIntegration(app, [grant], state.hooks, state.matches_snapshot)
