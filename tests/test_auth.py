from server.auth import get_current_user


def test_user_from_header(app):
    with app.test_request_context(headers={"Remote-User": "PhilG"}):
        assert get_current_user() == "philg"


def test_default_user_anonymous(app):
    with app.test_request_context():
        assert get_current_user() == "anonymous"


def test_custom_header(app):
    app.config["AUTH_USER_HEADER"] = "X-Forwarded-User"
    with app.test_request_context(headers={"X-Forwarded-User": "Alice"}):
        assert get_current_user() == "alice"


def test_whitespace_stripped(app):
    with app.test_request_context(headers={"Remote-User": "  Bob  "}):
        assert get_current_user() == "bob"
