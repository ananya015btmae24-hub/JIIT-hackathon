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


needed = ["IG_TOKEN", "IG_USER_ID", "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY",
          "CLOUDINARY_API_SECRET", "CUSTOM_API_KEY"]
missing = [k for k in needed if not os.getenv(k) or os.getenv(k, "").startswith(("paste_", "make_up"))]
show(".env file", not missing, "all filled" if not missing else "still empty: " + ", ".join(missing))

r = requests.get(f"https://graph.instagram.com/{V}/me",
                 params={"fields": "user_id,username", "access_token": os.getenv("IG_TOKEN", "")}, timeout=30).json()
if "username" in r:
    same = str(r.get("user_id")) == os.getenv("IG_USER_ID")
    show("Instagram", same, f"logged in as @{r['username']}" + ("" if same else f" — but IG_USER_ID should be {r.get('user_id')}"))
else:
    show("Instagram", False, str(r.get("error", r)))

try:
    import cloudinary, cloudinary.api
    cloudinary.config(cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"), api_key=os.getenv("CLOUDINARY_API_KEY"),
                      api_secret=os.getenv("CLOUDINARY_API_SECRET"))
    cloudinary.api.ping()
    folder = os.getenv("CLOUDINARY_FOLDER", "insta")
    try:
        n = len(cloudinary.api.resources_by_asset_folder(folder, max_results=500)["resources"])
    except Exception:
        n = 0
    if n == 0:
        n = len(cloudinary.api.resources(type="upload", prefix=folder + "/", max_results=500)["resources"])
    if n == 0:
        show("Cloudinary images", False, f"no images found in folder '{folder}'")
        try:
            names = [f["name"] for f in cloudinary.api.root_folders().get("folders", [])]
            print("   Folders in your Cloudinary:", names if names else "none")
        except Exception as e:
            print("   Could not list folders:", e)
        try:
            some = cloudinary.api.resources(type="upload", max_results=5).get("resources", [])
            print("   Some images in your account:")
            for r in some:
                print("     -", r["public_id"], "| folder:", r.get("asset_folder", r.get("folder", "")) or "(top level)")
            if not some:
                print("     none at all — upload images in Cloudinary first")
        except Exception as e:
            print("   Could not list images:", e)
        print(f"   → Put CLOUDINARY_FOLDER=<one of the folder names above> in .env, or move images into '{folder}'")
    show("Cloudinary", True, f"connected, {n} image(s) in folder '{folder}'")
except Exception as e:
    show("Cloudinary", False, str(e))

print("\nAll good — run: python app.py" if ok_all else "\nFix the ❌ lines in your .env, then run this again.")
