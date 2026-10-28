"""Run while app.py is running (in a second terminal): python test_api.py"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()
BASE = f"http://127.0.0.1:{os.getenv('PORT', 5000)}"
HEADERS = {"X-API-Key": os.getenv("CUSTOM_API_KEY", "")}


def show(label, r):
    try:
        data = r.json()
    except ValueError:
        print(f"{label}: ❌ the bot crashed (status {r.status_code}). Look at the LAST red line in Terminal 1.")
        return None
    print(f"{label}:", ("✅ " if data.get("ok") else "❌ ") + str(data))
    return data


try:
    images = show("Images", requests.get(f"{BASE}/api/images", headers=HEADERS, timeout=30))
except requests.ConnectionError:
    raise SystemExit("❌ Can't reach the bot. Start it first in Terminal 1:  python app.py")

if images and images.get("ok"):
    if not images["images"]:
        raise SystemExit("❌ No images in your Cloudinary folder. Upload some into the 'insta' folder first.")
    show("Post", requests.post(f"{BASE}/api/post", headers=HEADERS,
                               json={"next": True, "caption": "Posted through my own API"}, timeout=120))