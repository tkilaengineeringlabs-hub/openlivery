"""Encrypt every persisted HTTP header value; never return saved values."""
import copy
import json
from ...security import encrypt_secret, decrypt_secret

STORED = "••••••••"


def public_actions(actions):
    result = copy.deepcopy(actions)
    for action in result:
        if action["type"] == "http_request":
            headers = json.loads(decrypt_secret(action.pop("encrypted_headers")))
            action["headers"] = {key: STORED for key in headers}
    return result


def store_actions(actions, previous=()):
    previous_by_id = {a["id"]: a for a in previous}
    result = copy.deepcopy(actions)
    for action in result:
        if action["type"] != "http_request":
            continue
        headers = action.pop("headers", {})
        old = previous_by_id.get(action["id"], {})
        saved = json.loads(decrypt_secret(old["encrypted_headers"])) if old.get("encrypted_headers") else {}
        for key, value in headers.items():
            if value == STORED:
                if key not in saved:
                    raise ValueError("Missing saved header")
                headers[key] = saved[key]
        action["encrypted_headers"] = encrypt_secret(json.dumps(headers))
    return result
