import sys
import json
import asyncio
import os
import time
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "gates"))
from skool_accounts import (
    _make_fresh_client, _do_login, _validate_session, _preflight,
    _load_statuses, _save_statuses, _account_statuses, _close_client,
)

STATUS_FILE = os.path.join(os.path.dirname(__file__), "skool_status.json")


def load_status():
    try:
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_status(data):
    with open(STATUS_FILE, "w") as f:
        json.dump(data, f)


async def check_account(email, password):
    client = _make_fresh_client()
    try:
        await _preflight(client)
        await asyncio.sleep(random.uniform(0.3, 0.8))

        r = await _do_login(client, email, password)

        if r.status_code == 200:
            session_cookies = dict(client.cookies) if hasattr(client, "cookies") else {}
            auth_token = session_cookies.get("auth_token")
            if auth_token:
                return {"status": "active", "detail": "Login successful"}
            if session_cookies:
                valid = await _validate_session(client)
                if valid:
                    return {"status": "active", "detail": "Session validated"}
            try:
                body = r.json()
                err = str(body)[:100]
            except Exception:
                err = r.text[:100]
            return {"status": "dead", "detail": f"Login returned 200 but no auth: {err}"}

        elif r.status_code == 401:
            return {"status": "dead", "detail": "Invalid credentials"}

        elif r.status_code == 403:
            return {"status": "unknown", "detail": "Blocked by anti-bot (403)"}

        elif r.status_code == 429:
            return {"status": "unknown", "detail": "Rate limited (429)"}

        else:
            try:
                body = r.text[:100]
            except Exception:
                body = "?"
            return {"status": "dead", "detail": f"HTTP {r.status_code}: {body}"}

    except Exception as e:
        return {"status": "unknown", "detail": f"Error: {str(e)[:100]}"}
    finally:
        await _close_client(client)


async def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: web_check_skool.py <email> <password>"}))
        return

    email = sys.argv[1]
    password = sys.argv[2]

    result = await check_account(email, password)

    status_data = load_status()
    status_data[email] = result["status"]
    save_status(status_data)

    result["email"] = email
    print(json.dumps(result))


if __name__ == "__main__":
    asyncio.run(main())
