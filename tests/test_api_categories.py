import io


def _headers(user="user-a"):
    return {"Remote-User": user}


def _get_categories(client, user="user-a"):
    return client.get("/api/categories", headers=_headers(user))


def _create_category(client, name, description="", user="user-a"):
    return client.post(
        "/api/categories",
        json={"name": name, "description": description},
        headers=_headers(user),
    )


def _upload_route(client, sample_gpx, category_id, user="user-a"):
    return client.post(
        "/api/routes",
        data={
            "file": (io.BytesIO(sample_gpx), "t.gpx"),
            "title": "T",
            "category_id": str(category_id),
        },
        content_type="multipart/form-data",
        headers=_headers(user),
    )


def _find_category(categories, name):
    return next((c for c in categories if c["name"] == name), None)


def test_default_category_exists(client):
    resp = _get_categories(client)
    assert resp.status_code == 200
    body = resp.get_json()
    default = _find_category(body, "Default")
    assert default is not None


def test_create_category(client):
    resp = _create_category(client, "Touring")
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["name"] == "Touring"


def test_create_duplicate_category(client):
    _create_category(client, "Touring")
    resp = _create_category(client, "Touring")
    assert resp.status_code == 409


def test_rename_category(client):
    create_resp = _create_category(client, "Touring")
    cat_id = create_resp.get_json()["id"]
    resp = client.patch(
        f"/api/categories/{cat_id}",
        json={"name": "Road Touring"},
        headers=_headers(),
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["name"] == "Road Touring"


def test_rename_default_category_fails(client):
    cats = _get_categories(client).get_json()
    default = _find_category(cats, "Default")
    resp = client.patch(
        f"/api/categories/{default['id']}",
        json={"name": "Something Else"},
        headers=_headers(),
    )
    assert resp.status_code == 400


def test_delete_empty_category(client):
    cat_id = _create_category(client, "Touring").get_json()["id"]
    resp = client.delete(f"/api/categories/{cat_id}", headers=_headers())
    assert resp.status_code == 204


def test_delete_default_category_fails(client):
    cats = _get_categories(client).get_json()
    default = _find_category(cats, "Default")
    resp = client.delete(f"/api/categories/{default['id']}", headers=_headers())
    assert resp.status_code == 400


def test_delete_nonempty_category_fails(client, sample_gpx):
    cat_id = _create_category(client, "Touring").get_json()["id"]
    upload_resp = _upload_route(client, sample_gpx, cat_id)
    assert upload_resp.status_code == 201
    resp = client.delete(f"/api/categories/{cat_id}", headers=_headers())
    assert resp.status_code == 400


def test_delete_nonempty_with_move_to_default(client, sample_gpx):
    cat_id = _create_category(client, "Touring").get_json()["id"]
    _upload_route(client, sample_gpx, cat_id)
    resp = client.delete(
        f"/api/categories/{cat_id}?move_to_default=true",
        headers=_headers(),
    )
    assert resp.status_code == 204
    # Route should still exist (now in Default)
    routes = client.get("/api/routes", headers=_headers()).get_json()
    assert len(routes) == 1


def test_update_category_description(client):
    cat_id = _create_category(client, "Touring").get_json()["id"]
    resp = client.patch(
        f"/api/categories/{cat_id}",
        json={"description": "Weekend rides"},
        headers=_headers(),
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["description"] == "Weekend rides"


def test_categories_isolated_by_user(client):
    _create_category(client, "Touring", user="user-a")
    resp = _get_categories(client, user="user-b")
    body = resp.get_json()
    touring = _find_category(body, "Touring")
    assert touring is None
