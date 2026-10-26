"""Ordinary pytest assertions; no SDK-specific workflow runner needed."""
import pytest


@pytest.mark.parametrize("user", ["alice", "bob"])
def test_staff_reads_orders(client, user):
    response = client.get("/orders", headers={"X-Test-User": user})
    assert response.status_code == 200
    assert response.json == {"orders": 2}


def test_refund_is_approved(client, state):
    response = client.post("/refund", headers={"X-Test-User": "alice"})
    assert response.status_code == 200
    assert response.json == {"approved": True}
    assert state["refunds"] == ["refund-1"]


def test_health(client):
    assert client.get("/health").json == {"healthy": True}
