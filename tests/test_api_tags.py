import io


def _headers(user="user-a"):
    return {"Remote-User": user}


def _upload_route(client, sample_gpx, title="T"):
    resp = client.post(
        "/api/routes",
        data={
            "file": (io.BytesIO(sample_gpx), "t.gpx"),
            "title": title,
        },
        content_type="multipart/form-data",
        headers=_headers(),
    )
    return resp.get_json()["id"]


def _create_category(client, name, user="user-a"):
    resp = client.post(
        "/api/categories",
        json={"name": name},
        headers=_headers(user),
    )
    return resp.get_json()["id"]


def test_set_route_tags(client, sample_gpx):
    route_id = _upload_route(client, sample_gpx)
    resp = client.put(
        f"/api/routes/{route_id}/tags",
        json={"tags": ["Hilly", "Scenic"]},
        headers=_headers(),
    )
    assert resp.status_code == 200
    body = resp.get_json()
    tag_names = [t["name_lower"] for t in body["tags"]]
    assert "hilly" in tag_names
    assert "scenic" in tag_names


def test_set_category_tags(client):
    cat_id = _create_category(client, "Urban Routes")
    resp = client.put(
        f"/api/categories/{cat_id}/tags",
        json={"tags": ["Urban"]},
        headers=_headers(),
    )
    assert resp.status_code == 200
    body = resp.get_json()
    tag_names = [t["name_lower"] for t in body["tags"]]
    assert "urban" in tag_names


def test_tags_auto_created(client, sample_gpx):
    route_id = _upload_route(client, sample_gpx)
    client.put(
        f"/api/routes/{route_id}/tags",
        json={"tags": ["NewTag"]},
        headers=_headers(),
    )
    resp = client.get("/api/tags", headers=_headers())
    assert resp.status_code == 200
    tags = resp.get_json()
    names = [t["name_lower"] for t in tags]
    assert "newtag" in names


def test_tags_case_insensitive_dedup(client, sample_gpx):
    route_id = _upload_route(client, sample_gpx)
    client.put(
        f"/api/routes/{route_id}/tags",
        json={"tags": ["Hilly", "hilly", "HILLY"]},
        headers=_headers(),
    )
    resp = client.get("/api/tags", headers=_headers())
    tags = resp.get_json()
    hilly_tags = [t for t in tags if t["name_lower"] == "hilly"]
    assert len(hilly_tags) == 1


def test_list_tags_with_counts(client, sample_gpx):
    route_id_1 = _upload_route(client, sample_gpx, title="Route A")
    route_id_2 = _upload_route(client, sample_gpx, title="Route B")
    client.put(
        f"/api/routes/{route_id_1}/tags",
        json={"tags": ["Shared"]},
        headers=_headers(),
    )
    client.put(
        f"/api/routes/{route_id_2}/tags",
        json={"tags": ["Shared"]},
        headers=_headers(),
    )
    resp = client.get("/api/tags", headers=_headers())
    tags = resp.get_json()
    shared = next((t for t in tags if t["name_lower"] == "shared"), None)
    assert shared is not None
    assert shared["usage_count"] == 2


def test_delete_tag(client, sample_gpx):
    route_id = _upload_route(client, sample_gpx)
    client.put(
        f"/api/routes/{route_id}/tags",
        json={"tags": ["ToDelete"]},
        headers=_headers(),
    )
    tags = client.get("/api/tags", headers=_headers()).get_json()
    tag = next(t for t in tags if t["name_lower"] == "todelete")
    resp = client.delete(f"/api/tags/{tag['id']}", headers=_headers())
    assert resp.status_code == 204
    tags_after = client.get("/api/tags", headers=_headers()).get_json()
    names_after = [t["name_lower"] for t in tags_after]
    assert "todelete" not in names_after


def test_tags_isolated_by_user(client, sample_gpx):
    # Upload route as user-a and set a tag
    resp = client.post(
        "/api/routes",
        data={
            "file": (io.BytesIO(sample_gpx), "t.gpx"),
            "title": "User A Route",
        },
        content_type="multipart/form-data",
        headers=_headers("user-a"),
    )
    route_id = resp.get_json()["id"]
    client.put(
        f"/api/routes/{route_id}/tags",
        json={"tags": ["PrivateTag"]},
        headers=_headers("user-a"),
    )
    # user-b should see no tags
    resp_b = client.get("/api/tags", headers=_headers("user-b"))
    assert resp_b.status_code == 200
    assert resp_b.get_json() == []
