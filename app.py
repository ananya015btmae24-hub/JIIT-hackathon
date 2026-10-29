"""
Instagram posting API (no Cloudinary, no WhatsApp)
--------------------------------------------------
Send a photo or a video to ONE route and it is posted on your Instagram (videos as Reels).
Gemini looks at the photo (or a frame of the video) and writes the caption by itself.

Run it with ONE command:  python app.py

Route (needs header  X-API-Key: <CUSTOM_API_KEY>):
  POST /api/post   multipart form:  file=<photo or video>        (caption=<text> is optional)
  POST /api/post   JSON: {"image_url": "https://...jpg"}  or  {"video_url": "https://...mp4"}
  Leave the caption out and Gemini writes one.

Instagram downloads the media itself, so this server must be reachable from the internet:
put its public address in .env as PUBLIC_BASE_URL (e.g. your ngrok / cloudflared / hosting link).
"""

import base64
import hmac
import os
import threading
import time
import uuid

import cv2
import requests
from dotenv import load_dotenv
from flask import Flask, abort, request, send_from_directory
from PIL import Image, ImageOps

load_dotenv()

# ---------- settings (from the .env file) ----------
API_VERSION = os.getenv("API_VERSION", "v24.0")
IG_TOKEN = os.environ["IG_TOKEN"]
IG_USER_ID = os.environ["IG_USER_ID"]
CUSTOM_API_KEY = os.environ["CUSTOM_API_KEY"]
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
GEMINI_BACKUP_MODELS = ["gemini-3.5-flash-lite", "gemini-flash-latest", "gemini-3.8-flash"]
DEFAULT_HASHTAGS = os.getenv("CAPTION_HASHTAGS", "#newarrival #shopnow #instafashion")
IG_API = f"https://graph.instagram.com/{API_VERSION}"
VIDEO_TYPES = (".mp4", ".mov", ".m4v")
MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")  # temporary files, removed after posting
os.makedirs(MEDIA_DIR, exist_ok=True)
for _old in os.listdir(MEDIA_DIR):  # leftovers from a previous run
    try:
        os.remove(os.path.join(MEDIA_DIR, _old))
    except OSError:
        pass

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # biggest upload accepted: 200 MB


# ---------- Media (what Instagram will download) ----------
def media_url(name):
    return f"{PUBLIC_BASE_URL}/media/{name}"


@app.get("/media/<name>")
def serve_media(name):
    """Instagram (and Gemini) fetch the file from here. Names are random and the file is deleted after posting."""
    return send_from_directory(MEDIA_DIR, name)


def prepare_image(src, dst):
    """Photo -> 1080x1080 JPEG, padded so Instagram never rejects the shape."""
    img = ImageOps.exif_transpose(Image.open(src))
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        flat = Image.new("RGB", img.size, "white")
        flat.paste(img, mask=img.getchannel("A"))
        img = flat
    ImageOps.pad(img.convert("RGB"), (1080, 1080), color="white").save(dst, "JPEG", quality=92)


def video_frame(src, dst):
    """A still frame from the video, for Gemini to look at."""
    cap = cv2.VideoCapture(src)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) // 10)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError("Could not read this video file.")
    h, w = frame.shape[:2]
    if w > 1080:
        frame = cv2.resize(frame, (1080, int(h * 1080 / w)))
    cv2.imwrite(dst, frame)


# ---------- Instagram ----------
def post_to_instagram(media_url, caption, resource_type="image"):
    """Step A: create container -> wait until ready -> Step B: publish. Returns the post ID.
    Videos are posted as Reels."""
    is_video = resource_type == "video"
    media = {"media_type": "REELS", "video_url": media_url} if is_video else {"image_url": media_url}
    r = requests.post(
        f"{IG_API}/{IG_USER_ID}/media",
        data={**media, "caption": caption, "access_token": IG_TOKEN},
        timeout=60,
    ).json()
    if "id" not in r:
        raise RuntimeError(f"Instagram refused the {resource_type}: {r.get('error', r)}")
    container_id = r["id"]

    for _ in range(60 if is_video else 12):  # images ~1 minute, videos take longer to process (~5 minutes)
        status = requests.get(
            f"{IG_API}/{container_id}",
            params={"fields": "status_code", "access_token": IG_TOKEN},
            timeout=30,
        ).json().get("status_code")
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise RuntimeError(f"Instagram could not process this {resource_type}.")
        time.sleep(5)
    else:
        raise RuntimeError(f"Instagram is still processing this {resource_type}; try again in a few minutes.")

    r = requests.post(
        f"{IG_API}/{IG_USER_ID}/media_publish",
        data={"creation_id": container_id, "access_token": IG_TOKEN},
        timeout=60,
    ).json()
    if "id" not in r:
        raise RuntimeError(f"Publishing failed: {r.get('error', r)}")
    return r["id"]


# ---------- AI captions (Gemini looks at the image) ----------
PROMPT = """Write one Instagram caption for this product image.
- 1-2 short, catchy sentences that describe what is actually in the image
- 1-2 fitting emojis
- end with 5-8 relevant hashtags on the same line
- no quotation marks, no explanations, reply with the caption only"""


def fallback_caption():
    return f"Fresh drop, just for you ✨ DM us to order! {DEFAULT_HASHTAGS}"


def gemini_caption(image_url):
    image = base64.b64encode(requests.get(image_url, timeout=30).content).decode()
    body = {
        "contents": [{"parts": [{"inline_data": {"mime_type": "image/jpeg", "data": image}}, {"text": PROMPT}]}],
        "generationConfig": {"thinkingConfig": {"thinkingLevel": "low"}},
    }
    last_error = None
    for model in [GEMINI_MODEL] + [m for m in GEMINI_BACKUP_MODELS if m != GEMINI_MODEL]:
        for _ in range(2):  # a busy model (503/429) gets one quick retry, then we move on to the next
            try:
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
                    json=body,
                    timeout=25,  # a busy model can hang; don't wait on it for long
                ).json()
            except requests.RequestException as e:
                last_error = f"{model}: {e}"
                continue
            if "candidates" in r:
                parts = r["candidates"][0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
                if text:
                    return text
                last_error = f"{model}: empty answer"
                break
            err = r.get("error", {})
            last_error = f"{model}: {err.get('code')} {err.get('message', r)}"
            if err.get("code") not in (429, 500, 503):
                break  # not a "busy" error, retrying the same model won't help
            time.sleep(1)
    raise RuntimeError(last_error)


def generate_caption(image_url):
    """Caption written by Gemini from the picture itself; a simple caption if Gemini is unavailable."""
    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY missing in .env, using simple caption")
        return fallback_caption()
    try:
        return gemini_caption(image_url)[:2200] or fallback_caption()  # 2200 = Instagram's caption limit
    except Exception as e:
        print("Caption AI failed, using simple caption:", e)
        return fallback_caption()


# ---------- Posting ----------
def delete_files(names):
    """Windows keeps a file locked for a moment after it was served, so try a few times."""
    for _ in range(10):
        names = [n for n in names if os.path.exists(os.path.join(MEDIA_DIR, n))]
        for n in names:
            try:
                os.remove(os.path.join(MEDIA_DIR, n))
            except OSError:
                pass
        if not names:
            return
        time.sleep(1)


post_lock = threading.Lock()  # one post at a time


def publish(upload_path, kind, caption=""):
    """upload_path: the received file in MEDIA_DIR. kind: 'image' or 'video'.
    No caption given -> Gemini writes it. Returns (instagram_post_id, caption)."""
    token = uuid.uuid4().hex
    names = []
    try:
        if kind == "video":
            post_name, look_name = f"{token}.mp4", f"{token}.jpg"
            os.replace(upload_path, os.path.join(MEDIA_DIR, post_name))
            names = [post_name, look_name]
            video_frame(os.path.join(MEDIA_DIR, post_name), os.path.join(MEDIA_DIR, look_name))
        else:
            post_name = look_name = f"{token}.jpg"
            names = [post_name]
            prepare_image(upload_path, os.path.join(MEDIA_DIR, post_name))
        with post_lock:
            caption = caption or generate_caption(media_url(look_name))
            post_id = post_to_instagram(media_url(post_name), caption, kind)
        return post_id, caption
    finally:  # the files only exist so Instagram can download them
        threading.Thread(target=delete_files, args=(names + [os.path.basename(upload_path)],), daemon=True).start()


# ---------- Your API ----------
def api_key_ok(req):
    return hmac.compare_digest(req.headers.get("X-API-Key", ""), CUSTOM_API_KEY)


def receive_upload():
    """Save what was sent (a file, or a link to download) into MEDIA_DIR. Returns (path, kind)."""
    path = os.path.join(MEDIA_DIR, f"upload_{uuid.uuid4().hex}")
    body = request.get_json(silent=True) or {}
    link = body.get("image_url") or body.get("video_url")
    if "file" in request.files:
        f = request.files["file"]
        name, mimetype = f.filename or "", f.mimetype or ""
        f.save(path)
    elif link:
        r = requests.get(link, timeout=120)
        r.raise_for_status()
        name, mimetype = link.split("?")[0], r.headers.get("content-type", "")
        with open(path, "wb") as out:
            out.write(r.content)
    else:
        raise ValueError("Send a photo or video as form field 'file', or JSON with image_url / video_url")
    is_video = mimetype.startswith("video/") or name.lower().endswith(VIDEO_TYPES)
    return path, "video" if is_video else "image"


@app.post("/api/post")
def api_post():
    if not api_key_ok(request):
        return {"ok": False, "error": "Missing or wrong X-API-Key"}, 401
    if not PUBLIC_BASE_URL:
        return {"ok": False, "error": "Set PUBLIC_BASE_URL in .env (the public link of this server) so Instagram can download the media"}, 500
    path = None
    try:
        path, kind = receive_upload()
        caption = request.form.get("caption") or (request.get_json(silent=True) or {}).get("caption", "")
        post_id, caption = publish(path, kind, caption)
        return {"ok": True, "type": kind, "instagram_post_id": post_id, "caption": caption}
    except ValueError as e:
        return {"ok": False, "error": str(e)}, 400
    except Exception as e:
        if path and os.path.exists(path):
            os.remove(path)
        return {"ok": False, "error": str(e)}, 500


@app.get("/")
def home():
    return "Instagram API is running ✅"


if __name__ == "__main__":
    if not PUBLIC_BASE_URL:
        print("⚠️  PUBLIC_BASE_URL is not set in .env - Instagram can't download media from this server without it.")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
