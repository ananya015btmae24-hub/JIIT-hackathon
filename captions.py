"""
Automatic Instagram captions (uses Claude to look at the image)
---------------------------------------------------------------
Works next to app.py without changing it. Uses ANTHROPIC_API_KEY (paid, pip install anthropic)
or GEMINI_API_KEY (free) from .env. Without either it falls back to a simple caption.

  python captions.py                 -> show the caption for the next unposted image
  python captions.py <image_id>      -> show the caption for that image
  python captions.py --post          -> generate caption, then post via the running app.py
"""

import base64
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-5-5"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_BACKUP_MODELS = ["gemini-flash-latest", "gemini-3.5-flash", "gemini-3.5-flash-lite"]
DEFAULT_HASHTAGS = os.getenv("CAPTION_HASHTAGS", "#newarrival #shopnow #instafashion")

PROMPT = """Write one Instagram caption for this product image.
- 1-2 short, catchy sentences that describe what is actually in the image
- 1-2 fitting emojis
- end with 5-8 relevant hashtags on the same line
- no quotation marks, no explanations, reply with the caption only"""


def fallback_caption():
    return f"Fresh drop, just for you ✨ DM us to order! {DEFAULT_HASHTAGS}"


def gemini_caption(image_url, prompt):
    """Free option: Google Gemini (free key, no card, from aistudio.google.com)."""
    image = base64.b64encode(requests.get(image_url, timeout=30).content).decode()
    body = {
        "contents": [{"parts": [{"inline_data": {"mime_type": "image/jpeg", "data": image}}, {"text": prompt}]}],
        "generationConfig": {"thinkingConfig": {"thinkingLevel": "low"}},
    }
    last_error = None
    for model in [GEMINI_MODEL] + [m for m in GEMINI_BACKUP_MODELS if m != GEMINI_MODEL]:
        for attempt in range(2):  # free models are often busy (503/429): retry once, then try the next model
            try:
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
                    json=body,
                    timeout=90,
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
            time.sleep(3)
    raise RuntimeError(last_error)


def generate_caption(image_url, extra_info=""):
    """Caption for a public image URL. extra_info: e.g. 'Cotton kurti, ₹799, sizes M and L'."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        if not os.getenv("GEMINI_API_KEY"):
            return fallback_caption()
        try:
            prompt = PROMPT + (f"\nProduct details from the seller: {extra_info}" if extra_info else "")
            return gemini_caption(image_url, prompt)[:2200] or fallback_caption()
        except Exception as e:
            print("Caption AI failed, using simple caption:", e)
            return fallback_caption()
    try:
        import anthropic

        prompt = PROMPT + (f"\nProduct details from the seller: {extra_info}" if extra_info else "")
        response = anthropic.Anthropic().beta.messages.create(
            model=MODEL,
            max_tokens=2000,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "url", "url": image_url}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        if response.stop_reason == "refusal":
            return fallback_caption()
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        return text[:2200] or fallback_caption()  # Instagram's caption limit
    except Exception as e:
        print("Caption AI failed, using simple caption:", e)
        return fallback_caption()


if __name__ == "__main__":
    import app  # reuses the Cloudinary helpers from app.py

    args = [a for a in sys.argv[1:] if a != "--post"]
    image_id = args[0] if args else app.next_unposted()
    if not image_id:
        raise SystemExit("Nothing left to post.")

    caption = generate_caption(app.insta_ready_url(image_id))
    print(f"Image:   {image_id}\nCaption: {caption}")

    if "--post" in sys.argv:
        r = requests.post(
            f"http://127.0.0.1:{os.getenv('PORT', 5000)}/api/post",
            headers={"X-API-Key": os.getenv("CUSTOM_API_KEY", "")},
            json={"image_id": image_id, "caption": caption},
            timeout=120,
        )
        print("Post:", r.json())
