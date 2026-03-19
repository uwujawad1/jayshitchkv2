import sys
import json
import requests
import os

def send_otp(user_id, otp_code):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        if os.path.exists(config_path):
            with open(config_path) as f:
                config = json.load(f)
                bot_token = config.get("TELEGRAM_BOT_TOKEN", "")

    if not bot_token:
        return {"ok": False, "error": "No bot token configured"}

    text = (
        f"🔐 **Web Login OTP**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Your verification code:\n\n"
        f"```{otp_code}```\n\n"
        f"⏳ Expires in 5 minutes\n"
        f"⚠️ Do not share this code\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 Hit Checker Web Login"
    )

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": int(user_id),
            "text": text,
            "parse_mode": "Markdown"
        }, timeout=10)
        data = resp.json()
        if data.get("ok"):
            return {"ok": True}
        else:
            return {"ok": False, "error": data.get("description", "Unknown error")}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"ok": False, "error": "Usage: send_otp.py <user_id> <otp>"}))
        sys.exit(1)

    result = send_otp(sys.argv[1], sys.argv[2])
    print(json.dumps(result))
