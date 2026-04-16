from flask import current_app, request


def get_current_user() -> str:
    header = current_app.config["AUTH_USER_HEADER"]
    value = request.headers.get(header, "").strip()
    if not value:
        return "anonymous"
    return value.lower()
