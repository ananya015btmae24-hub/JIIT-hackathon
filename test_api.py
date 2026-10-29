"""Run while app.py is running (in a second terminal):  python test_api.py <photo-or-video-file>"""
import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()
BASE = "https://jiit-hackathon.onrender.com"  # your Render link, in quotes, no trailing slash
HEADERS = {"X-API-Key": os.getenv("CUSTOM_API_KEY", "")}

if len(sys.argv) < 2 or not os.path.isfile(sys.argv[1]):
    raise SystemExit("Usage: python test_api.py <photo-or-video-file>")

try:
    with open(sys.argv[1], "rb") as f:
        r = requests.post(f"{BASE}/api/post", headers=HEADERS, files={"file": f}, timeout=600)
except requests.ConnectionError:
    raise SystemExit("❌ Can't reach the bot. Start it first in Terminal 1:  python app.py")

try:
    data = r.json()
except ValueError:
    raise SystemExit(f"❌ the bot crashed (status {r.status_code}). Look at the LAST red line in Terminal 1.")
print(("✅ " if data.get("ok") else "❌ ") + str(data))
