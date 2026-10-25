"""Existing-style tests: no SafeRevoke workflows or engine calls required."""
import pytest


@pytest.mark.parametrize("identity", ["alice", "bob"])
def test_staff_can_list_users(client, staff_accounts, identity):
    client.force_login(staff_accounts[identity])
    assert client.get("/admin/auth/user/").status_code == 200


def test_staff_can_list_groups(logged_in_client):
    assert logged_in_client.get("/admin/auth/group/").status_code == 200


def test_staff_can_add_group(logged_in_client):
    from django.contrib.auth.models import Group
    response = logged_in_client.post("/admin/auth/group/add/", {"name": "created-by-existing-test"})
    assert response.status_code == 302
    assert Group.objects.filter(name="created-by-existing-test").exists()
