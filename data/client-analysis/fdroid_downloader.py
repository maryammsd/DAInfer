"""
F-Droid APK Downloader
Downloads top 10 APKs from each of the 20 most popular F-Droid categories.
"""

import os
import time
import json
import logging
import hashlib
import requests
from pathlib import Path
from typing import Optional
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/downloader.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

FDROID_API      = "https://f-droid.org/api/v1"
FDROID_REPO     = "https://f-droid.org/repo"
FDROID_INDEX    = "https://f-droid.org/repo/index-v2.json"
APK_DIR         = Path("apks")
META_FILE       = Path("config/downloaded_apps.json")
APPS_PER_CAT    = 10
MAX_APK_MB      = 100          # skip APKs larger than this
REQUEST_TIMEOUT = 60
RETRY_ATTEMPTS  = 3

# 20 target categories (F-Droid uses these tag strings)
TARGET_CATEGORIES = [
    "Internet",
    "Phone & SMS",
    "Navigation",
    "Multimedia",
    "Graphics",
    "Security",
    "Science & Education",
    "System",
    "Development",
    "Writing",
    "Sports & Health",
    "Games",
    "Connectivity",
    "Money",
    "Reading",
    "Time",
    "Theming",
    "Network",
    "Multimedia",
    "Contacts",
]
# de-duplicate while preserving order
TARGET_CATEGORIES = list(dict.fromkeys(TARGET_CATEGORIES))[:20]


def _get(url: str, stream=False, timeout=REQUEST_TIMEOUT):
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            r = requests.get(url, stream=stream, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            log.warning(f"Attempt {attempt}/{RETRY_ATTEMPTS} failed for {url}: {e}")
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed to fetch {url} after {RETRY_ATTEMPTS} attempts")


def fetch_index() -> dict:
    """Fetch and cache the full F-Droid index."""
    cache = Path("config/fdroid_index.json")
    if cache.exists() and (time.time() - cache.stat().st_mtime) < 86400:
        log.info("Using cached F-Droid index")
        return json.loads(cache.read_text())

    log.info("Fetching F-Droid package index (this may take a while)…")
    r = _get(FDROID_INDEX, timeout=120)
    data = r.json()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data))
    log.info(f"Index cached: {len(data.get('packages', {}))} packages")
    return data


def categorise_packages(index: dict) -> dict[str, list[dict]]:
    """Group packages by category, enriched with popularity proxy (installs field or version count)."""
    packages = index.get("packages", {})
    by_cat: dict[str, list[dict]] = {c: [] for c in TARGET_CATEGORIES}

    for pkg_id, pkg_data in packages.items():
        metadata = pkg_data.get("metadata", {})
        cats = metadata.get("categories", [])
        versions = pkg_data.get("versions", {})
        if not versions:
            continue

        # Popularity proxy: number of tagged versions (more active = more popular)
        pop_score = len(versions)

        # Pick the latest stable version
        latest_version = None
        latest_code    = -1
        for vcode, vdata in versions.items():
            vc = int(vcode) if str(vcode).isdigit() else -1
            if vc > latest_code:
                latest_code    = vc
                latest_version = vdata

        if not latest_version:
            continue

        apks = latest_version.get("apks", [])
        if not apks:
            continue
        apk_info = apks[0]

        entry = {
            "packageName":  pkg_id,
            "name":         metadata.get("name", {}).get("en-US", pkg_id),
            "categories":   cats,
            "popularityScore": pop_score,
            "versionCode":  latest_code,
            "apkName":      apk_info.get("name", ""),
            "size":         apk_info.get("size", 0),
            "sha256":       apk_info.get("sha256", ""),
        }

        for cat in cats:
            if cat in by_cat:
                by_cat[cat].append(entry)

    # Sort each category by popularity (descending) and keep top N
    for cat in by_cat:
        by_cat[cat].sort(key=lambda x: x["popularityScore"], reverse=True)
        by_cat[cat] = by_cat[cat][:APPS_PER_CAT]

    return by_cat


def download_apk(entry: dict) -> Optional[Path]:
    """Download a single APK; skip if too large or already present."""
    apk_name = entry["apkName"]
    if not apk_name:
        log.warning(f"No APK name for {entry['packageName']}, skipping")
        return None

    size_mb = entry["size"] / (1024 * 1024) if entry["size"] else 0
    if size_mb > MAX_APK_MB:
        log.info(f"Skipping {apk_name} ({size_mb:.1f} MB > {MAX_APK_MB} MB limit)")
        return None

    dest = APK_DIR / apk_name
    if dest.exists():
        log.info(f"Already downloaded: {apk_name}")
        return dest

    url = f"{FDROID_REPO}/{apk_name}"
    log.info(f"Downloading {apk_name} ({size_mb:.1f} MB) …")
    try:
        r = _get(url, stream=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)

        # Verify SHA-256
        if entry.get("sha256"):
            sha = hashlib.sha256(dest.read_bytes()).hexdigest()
            if sha.lower() != entry["sha256"].lower():
                log.error(f"SHA-256 mismatch for {apk_name}! Removing.")
                dest.unlink()
                return None

        log.info(f"✓ {apk_name}")
        return dest
    except Exception as e:
        log.error(f"Failed to download {apk_name}: {e}")
        if dest.exists():
            dest.unlink()
        return None


def run():
    APK_DIR.mkdir(parents=True, exist_ok=True)
    Path("config").mkdir(parents=True, exist_ok=True)
    Path("logs").mkdir(parents=True, exist_ok=True)

    index      = fetch_index()
    by_cat     = categorise_packages(index)

    downloaded: dict[str, list[dict]] = {}
    total_apps = sum(len(v) for v in by_cat.values())
    log.info(f"Target: {len(by_cat)} categories × up to {APPS_PER_CAT} apps = ~{total_apps} downloads")

    with tqdm(total=total_apps, desc="Downloading APKs") as pbar:
        for cat, entries in by_cat.items():
            downloaded[cat] = []
            for entry in entries:
                path = download_apk(entry)
                if path:
                    entry["localPath"] = str(path)
                    downloaded[cat].append(entry)
                pbar.update(1)
                time.sleep(0.3)   # be polite to F-Droid servers

    # Persist metadata
    META_FILE.write_text(json.dumps(downloaded, indent=2))
    total_dl = sum(len(v) for v in downloaded.values())
    log.info(f"Download complete: {total_dl} APKs across {len(downloaded)} categories")
    return downloaded


if __name__ == "__main__":
    run()
