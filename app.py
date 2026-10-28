"""
Instagram posting API (no WhatsApp)
-----------------------------------
A small web server that posts images from Cloudinary to Instagram.
Your teammates (WhatsApp bot, website, anything) call this API to post.

Endpoints (every request needs header  X-API-Key: <CUSTOM_API_KEY>):
  GET  /api/images                       -> list images in your Cloudinary folder
  POST /api/post  {"image_id": "insta/dog1", "caption": "..."}
  POST /api/post  {"image_url": "https://...jpg", "caption": "..."}
  POST /api/post  {"next": true, "caption": "..."}
"""

import hmac
import os
import time

import cloudinary
import cloudinary.api
import cloudinary.uploader
import cloudinary.utils
import requests
from dotenv import load_dotenv
from flask import Flask, request

load_dotenv()

# ---------- settings (from the .env file) ----------
API_VERSION = os.getenv("API_VERSION", "v24.0")
IG_TOKEN = os.environ["IG_TOKEN"]
IG_USER_ID = os.environ["IG_USER_ID"]
CUSTOM_API_KEY = os.environ["CUSTOM_API_KEY"]

cloudinary.config(
    cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
    api_key=os.environ["CLOUDINARY_API_KEY"],
    api_secret=os.environ["CLOUDINARY_API_SECRET"],
    secure=True,
)
FOLDER = os.getenv("CLOUDINARY_FOLDER", "insta")
IG_API = f"https://graph.instagram.com/{API_VERSION}"

app = Flask(__name__)


# ---------- Cloudinary ----------
def insta_ready_url(public_id):
    """Image link as a 1080x1080 JPEG, padded so Instagram never rejects the shape."""
    url, _ = cloudinary.utils.cloudinary_url(
        public_id,
        format="jpg",
        transformation=[{"width": 1080, "height": 1080, "crop": "pad", "background": "white"}],
    )
    return url


def folder_resources(limit=500):
    """All images in FOLDER, with their tags. Works for both kinds of Cloudinary account
    (new 'dynamic folders' accounts and older 'fixed folders' accounts)."""
    try:
        res = cloudinary.api.resources_by_asset_folder(FOLDER, max_results=limit, tags=True)
        items = res.get("resources", [])
        if items:
            return items
    except Exception:
        pass
    res = cloudinary.api.resources(type="upload", prefix=f"{FOLDER}/", max_results=limit, tags=True)
    return res.get("resources", [])


def list_images(limit=50):
    return [r["public_id"] for r in folder_resources()][:limit]


def next_unposted():
    """Oldest image in FOLDER that isn't tagged 'posted' yet."""
    fresh = [r for r in folder_resources() if "posted" not in r.get("tags", [])]
    fresh.sort(key=lambda r: r.get("created_at", ""))
    return fresh[0]["public_id"] if fresh else None


def mark_posted(public_id):
    cloudinary.uploader.add_tag("posted", [public_id])


# ---------- Instagram ----------
def post_to_instagram(image_url, caption):
    """Step A: create container -> wait until ready -> Step B: publish. Returns the post ID."""
    r = requests.post(
        f"{IG_API}/{IG_USER_ID}/media",
        data={"image_url": image_url, "caption": caption, "access_token": IG_TOKEN},
        timeout=60,
    ).json()
    if "id" not in r:
        raise RuntimeError(f"Instagram refused the image: {r.get('error', r)}")
    container_id = r["id"]

    for _ in range(12):  # wait up to ~1 minute
        status = requests.get(
            f"{IG_API}/{container_id}",
            params={"fields": "status_code", "access_token": IG_TOKEN},
            timeout=30,
        ).json().get("status_code")
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise RuntimeError("Instagram could not process this image.")
        time.sleep(5)

    r = requests.post(
        f"{IG_API}/{IG_USER_ID}/media_publish",
        data={"creation_id": container_id, "access_token": IG_TOKEN},
        timeout=60,
    ).json()
    if "id" not in r:
        raise RuntimeError(f"Publishing failed: {r.get('error', r)}")
    return r["id"]


# ---------- Your API ----------
def api_key_ok(req):
    return hmac.compare_digest(req.headers.get("X-API-Key", ""), CUSTOM_API_KEY)


@app.post("/api/post")
def api_post():
    if not api_key_ok(request):
        return {"ok": False, "error": "Missing or wrong X-API-Key"}, 401
    body = request.get_json(silent=True) or {}
    caption = body.get("caption", "")
    try:
        if body.get("image_url"):
            pid = cloudinary.uploader.upload(body["image_url"], folder=FOLDER, asset_folder=FOLDER)["public_id"]
        elif body.get("image_id"):
            pid = body["image_id"]
        elif body.get("next"):
            pid = next_unposted()
            if not pid:
                return {"ok": False, "error": "Nothing left to post"}, 404
        else:
            return {"ok": False, "error": "Send image_id, image_url or next"}, 400
        post_id = post_to_instagram(insta_ready_url(pid), caption)
        mark_posted(pid)
        return {"ok": True, "image_id": pid, "instagram_post_id": post_id}
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


@app.get("/api/images")
def api_images():
    if not api_key_ok(request):
        return {"ok": False, "error": "Missing or wrong X-API-Key"}, 401
    try:
        return {"ok": True, "images": list_images()}
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


@app.get("/")
def home():
    return "Instagram API is running ✅"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))