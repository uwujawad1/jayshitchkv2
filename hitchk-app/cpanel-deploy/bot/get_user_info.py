import sys
import json
import os
import requests

def get_bot_token():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                token = config.get("TELEGRAM_BOT_TOKEN", "")
        except Exception:
            pass
    return token

def get_user_info(user_id):
    token = get_bot_token()
    if not token:
        return {"user_id": user_id, "first_name": "", "username": ""}

    try:
        url = f"https://api.telegram.org/bot{token}/getChat"
        r = requests.get(url, params={"chat_id": user_id}, timeout=10)
        data = r.json()
        if data.get("ok"):
            result = data["result"]
            return {
                "user_id": user_id,
                "first_name": result.get("first_name", ""),
                "last_name": result.get("last_name", ""),
                "username": result.get("username", ""),
            }
    except Exception:
        pass

    return {"user_id": user_id, "first_name": "", "username": ""}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: get_user_info.py <user_id>"}))
        sys.exit(1)
    info = get_user_info(sys.argv[1])
    print(json.dumps(info))
