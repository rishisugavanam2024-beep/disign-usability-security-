import pytest


@pytest.fixture
def staff_accounts(db):
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group, Permission
    User = get_user_model()
    alice = User.objects.create_user(username="alice", is_staff=True)
    bob = User.objects.create_user(username="bob", is_staff=True)
    operators = Group.objects.create(name="operators")
    auditors = Group.objects.create(name="auditors")
    operators.permissions.add(Permission.objects.get(content_type__app_label="auth", codename="view_user"))
    auditors.permissions.add(Permission.objects.get(content_type__app_label="auth", codename="view_group"))
    alice.groups.add(operators, auditors)
    bob.groups.add(operators)
    alice.user_permissions.add(Permission.objects.get(content_type__app_label="auth", codename="view_group"))
    alice.user_permissions.add(Permission.objects.get(content_type__app_label="auth", codename="add_group"))
    return {"alice": alice, "bob": bob}


@pytest.fixture
def logged_in_client(client, staff_accounts):
    client.force_login(staff_accounts["alice"])
    return client
