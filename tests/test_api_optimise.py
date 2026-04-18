"""Tests for POST /api/routes/<id>/optimise (M3b)."""


def test_optimise_returns_new_order_and_persists(client, app):
    rid = client.post("/api/routes", json={"title": "Opt"},
                      content_type="application/json").get_json()["id"]
    pts = [(0, 0), (1, 1), (0, 1), (1, 0)]  # crossing seed
    wids = []
    for i, (lat, lon) in enumerate(pts):
        w = client.post(f"/api/routes/{rid}/waypoints", json={
            "name": f"W{i}", "lat": lat, "lon": lon, "kind": "stop",
        }).get_json()
        wids.append(w["id"])

    resp = client.post(f"/api/routes/{rid}/optimise")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "new_order" in body
    assert set(body["new_order"]) == set(wids)

    listed = client.get(f"/api/routes/{rid}/waypoints").get_json()
    listed_ids = [w["id"] for w in listed]
    assert listed_ids == body["new_order"]


def test_optimise_404_on_unknown_route(client):
    resp = client.post("/api/routes/99999/optimise")
    assert resp.status_code == 404


def test_optimise_requires_at_least_two_included(client, app):
    rid = client.post("/api/routes", json={"title": "Opt"},
                      content_type="application/json").get_json()["id"]
    client.post(f"/api/routes/{rid}/waypoints", json={
        "name": "W", "lat": 0, "lon": 0, "kind": "stop",
    })
    resp = client.post(f"/api/routes/{rid}/optimise")
    assert resp.status_code == 400


def test_optimise_parks_excluded_rows_at_tail(client, app):
    rid = client.post("/api/routes", json={"title": "ExOpt"},
                      content_type="application/json").get_json()["id"]
    pts = [(0, 0), (1, 1), (0, 1), (1, 0)]
    wids = []
    for i, (lat, lon) in enumerate(pts):
        w = client.post(f"/api/routes/{rid}/waypoints", json={
            "name": f"W{i}", "lat": lat, "lon": lon, "kind": "stop",
        }).get_json()
        wids.append(w["id"])
    # Exclude W2 before optimising.
    client.patch(f"/api/routes/{rid}/waypoints/{wids[2]}", json={"included": 0})

    resp = client.post(f"/api/routes/{rid}/optimise")
    assert resp.status_code == 200
    body = resp.get_json()
    # new_order contains only included rows.
    assert set(body["new_order"]) == {wids[0], wids[1], wids[3]}
    # Full listing still has all four, with the excluded one at the tail.
    listed = client.get(f"/api/routes/{rid}/waypoints").get_json()
    assert [w["id"] for w in listed][-1] == wids[2]
    assert listed[-1]["included"] == 0


def test_optimise_stamps_last_optimised_at(client, app):
    from server.models import waypoints as wp_model
    rid = client.post("/api/routes", json={"title": "Stamp"},
                      content_type="application/json").get_json()["id"]
    for i in range(3):
        client.post(f"/api/routes/{rid}/waypoints", json={
            "name": f"W{i}", "lat": i, "lon": i, "kind": "stop",
        })
    with app.app_context():
        before = wp_model.get_or_create_options(rid)
        assert before["last_optimised_at"] is None
    client.post(f"/api/routes/{rid}/optimise")
    with app.app_context():
        after = wp_model.get_or_create_options(rid)
        assert after["last_optimised_at"] is not None
