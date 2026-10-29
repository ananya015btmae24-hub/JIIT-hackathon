"""Run before starting: python check_setup.py  — tests every key in .env."""
import os
import requests
from dotenv import load_dotenv

load_dotenv()
V = os.getenv("API_VERSION", "v24.0")
ok_all = True


def show(name, ok, info):
    global ok_all
    ok_all &= ok
    print(("✅ " if ok else "❌ ") + name + ": " + info)


needed = ["IG_TOKEN", "IG_USER_ID", "CUSTOM_API_KEY", "GEMINI_API_KEY"]
missing = [k for k in needed if not os.getenv(k) or os.getenv(k, "").startswith(("paste_", "make_up"))]
show(".env file", not missing, "all filled" if not missing else "still empty: " + ", ".join(missing))

r = requests.get(f"https://graph.instagram.com/{V}/me",
                 params={"fields": "user_id,username", "access_token": os.getenv("IG_TOKEN", "")}, timeout=30).json()
if "username" in r:
    same = str(r.get("user_id")) == os.getenv("IG_USER_ID")
    show("Instagram", same, f"logged in as @{r['username']}" + ("" if same else f" — but IG_USER_ID should be {r.get('user_id')}"))
else:
    show("Instagram", False, str(r.get("error", r)))

pub = os.getenv("PUBLIC_BASE_URL", "")
show("PUBLIC_BASE_URL", pub.startswith("http"), pub or "missing - put the public link of this server in .env (ngrok / cloudflared / hosting)")

print("\nAll good — run: python app.py" if ok_all else "\nFix the ❌ lines in your .env, then run this again.")
