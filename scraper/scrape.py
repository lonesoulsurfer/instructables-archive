#!/usr/bin/env python3
"""
scrape.py  --  Scrape your Instructables profile and output projects.json

Usage:
    python3 scrape.py

Output:
    ../projects.json   (read by index.html for the website)

Requirements:
    pip install requests beautifulsoup4

Notes:
    - Runs at ~2 req/sec to stay polite. Full scrape of 254 projects takes ~5 min.
    - Safe to re-run: existing projects.json is merged so nothing is lost.
    - Run this whenever you publish a new Instructable.
"""

import json
import re
import time
import sys
import os
from pathlib import Path
from urllib.parse import urljoin

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: Missing dependencies. Run:  pip install requests beautifulsoup4")
    sys.exit(1)

# ── CONFIG ──────────────────────────────────────────────────────────────────
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import USERNAME, DISPLAY_NAME

BASE_URL    = "https://www.instructables.com"
PROFILE_URL = f"{BASE_URL}/member/{USERNAME}/instructables/"
OUTPUT_FILE = Path(__file__).parent.parent / "projects.json"
DELAY       = 0.6   # seconds between requests — be polite

# Map keywords in title/URL to categories.
# First match wins, so put more specific terms first.
CATEGORY_RULES = [
    # Junkbots first — very specific terms, must beat "robot" in electronics
    ("junkbots",    ["junkbot", "mechanical bug",
                     "vacuum tube bug", "typewriter parts", "dancing, magnetic robot",
                     "robot mechanical beetle", "walking robot", "light sensitive junkbot",
                     "ladybug pendant"]),

    # Lamps — anything light/lamp related, checked before electronics so
    # "LED lamp" style titles land here, not in electronics
    ("lamps",       ["lamp", "lantern", "candle", "light bulb", "light globe",
                     "night light", "flashlight", "flash light", "torch",
                     "lighter", "wand", "filament", "jar light", "ring lamp",
                     "light theremin", "light sensor", "led light", "led ring",
                     "led cube", "led candle", "led and copper", "globe hack",
                     "trench lighter", "bird house with night"]),

    # Synths — music/sound generation devices
    ("synths",      ["synth", "drum machine", "sequencer", "oscillator", "beatmaster",
                     "dub siren", "fizzle", "moog", "theremin", "eurorack", "mozzi",
                     "fm synth", "drone synth", "groove box", "bleep drum",
                     "freaq", "mutant", "medusa", "proton -", "elements -", "cigar box",
                     "sound bend", "circuit bend", "echo & reverb", "echo / delay",
                     "metronome", "voice changer"]),

    # Electronics — circuits, microcontrollers, general builds
    ("electronics", ["arduino", "attiny", "raspberry pi", "555 ", "circuit",
                     "battery", "power supply", "oscilloscope", "programmer", "pcb",
                     "cmos", "servo motor", "tetris", "arcade", "yahtzee",
                     "conway", "clock", "sensor", "amp", "headphone", "guitar amp",
                     "resistor", "op amp", "ic tester", "gerber"]),

    # Making — physical builds, crafts, everything else
    ("making",      ["box", "fire", "knife", "wooden", "bracelet",
                     "ring", "pendant", "stand", "holder", "shelf", "table",
                     "secret", "stash", "flask", "book safe", "spudger",
                     "canister", "knob", "display", "camera stand", "frame",
                     "milk crate", "skateboard", "fishing", "bike", "trike",
                     "rocket", "ray gun", "lathe", "soldering", "copper",
                     "brass", "paint can", "spray can", "junk yard", "junkyard",
                     "fish-bone sculpture", "sculpture"]),
]
DEFAULT_CATEGORY = "making"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         BASE_URL,
}


# ── HELPERS ──────────────────────────────────────────────────────────────────

def get(url, session, retries=3):
    """GET with retries and polite delay."""
    for attempt in range(retries):
        try:
            time.sleep(DELAY)
            r = session.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            print(f"  [warn] attempt {attempt+1} failed for {url}: {e}")
            time.sleep(2 ** attempt)
    return None


def categorise(title, url):
    """Assign a category based on title and URL keywords."""
    text = (title + " " + url).lower()
    for cat, keywords in CATEGORY_RULES:
        if any(kw in text for kw in keywords):
            return cat
    return DEFAULT_CATEGORY


def parse_views(text):
    """Convert '4.9K' or '1,234' or '1.2M' to an integer."""
    text = text.strip().lower().replace(",", "")
    try:
        if text.endswith("m"):
            return int(float(text[:-1]) * 1_000_000)
        if text.endswith("k"):
            return int(float(text[:-1]) * 1_000)
        return int(text)
    except ValueError:
        return 0


# ── SCRAPING ──────────────────────────────────────────────────────────────────

def fetch_project_list(session):
    """
    Fetch all project URLs + titles from the profile page.
    Instructables paginates via ?sort=recent&offset=N, 12 per page.
    Returns list of dicts: {title, url}
    """
    projects = []
    offset = 0
    page = 1

    while True:
        url = f"{PROFILE_URL}?sort=recent&offset={offset}"
        print(f"  Fetching profile page {page} (offset={offset}) ...")
        r = get(url, session)
        if not r:
            print("  Failed to fetch profile page. Stopping.")
            break

        soup = BeautifulSoup(r.text, "html.parser")

        # Project cards live in <div class="ible-thumb"> or <article> tags
        # depending on the page version — try both
        cards = soup.select("div.ible-thumb, article.ible-thumb, div[class*='ible']")

        # Profile nav links that look like project URLs -- exclude these
        BLOCKED_URLS = {
            f"{BASE_URL}/member/{USERNAME}/favorites/",
            f"{BASE_URL}/member/{USERNAME}/comments/",
            f"{BASE_URL}/member/{USERNAME}/settings/",
            f"{BASE_URL}/member/{USERNAME}/collections/",
            f"{BASE_URL}/member/{USERNAME}/instructables/",
            f"{BASE_URL}/member/{USERNAME}/",
        }

        # Fallback: find all links that look like project URLs
        if not cards:
            links = soup.find_all("a", href=re.compile(
                r"^https://www\.instructables\.com/[A-Za-z0-9][A-Za-z0-9\-]+/$"
            ))
            # Deduplicate
            seen = set()
            for a in links:
                href = a["href"].rstrip("/") + "/"
                title = a.get_text(strip=True) or a.get("title", "")
                if href in BLOCKED_URLS:
                    continue
                if href not in seen and title and len(title) > 4:
                    seen.add(href)
                    projects.append({"title": title, "url": href})
        else:
            for card in cards:
                a = card.find("a", href=True)
                if not a:
                    continue
                href = urljoin(BASE_URL, a["href"]).rstrip("/") + "/"
                # Get title from img alt or inner text
                img = card.find("img")
                title = (img.get("alt") if img else None) or a.get_text(strip=True)
                if title and len(title) > 4:
                    projects.append({"title": title, "url": href})

        # Check if there's a next page
        next_btn = soup.select_one("a[rel='next'], .next-page, a:contains('Next')")
        if not next_btn:
            # Also check if we got any results -- if 0, we're past the end
            if not cards and len([a for a in soup.find_all("a", href=re.compile(
                r"/[A-Za-z0-9][A-Za-z0-9\-]+/$"))]) == 0:
                break

        offset += 12
        page  += 1

        # Safety: stop after 30 pages (360 projects)
        if page > 30:
            break

    # Deduplicate by URL
    seen = set()
    unique = []
    for p in projects:
        if p["url"] not in seen:
            seen.add(p["url"])
            unique.append(p)

    return unique


def fetch_project_detail(project, session):
    """
    Fetch an individual project page and extract:
    - thumbnail image URL
    - view count
    - category (auto-assigned from title/URL)
    - description (first step intro, truncated)
    Returns the project dict with these fields added.
    """
    url = project["url"]
    print(f"  Scraping: {project['title'][:55]}")
    r = get(url, session)
    if not r:
        project.update({"img": "", "views": 0,
                        "category": categorise(project["title"], url),
                        "description": ""})
        return project

    soup = BeautifulSoup(r.text, "html.parser")

    # -- Thumbnail --
    img_url = ""
    # Try og:image meta first (most reliable)
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        img_url = og["content"]
    else:
        # Fallback: first large img in the header/hero area
        for img in soup.find_all("img", src=True):
            src = img["src"]
            if "content.instructables.com" in src and "pixel.png" not in src:
                img_url = src
                break

    # -- Views --
    views = 0
    # Look for view count in stats bar
    for el in soup.select("span.views-count, div.views, [data-views]"):
        txt = el.get_text(strip=True)
        if txt:
            views = parse_views(txt)
            break
    # Fallback: search for "Views" label nearby
    if not views:
        for el in soup.find_all(string=re.compile(r"^\d[\d,.KkMm]+$")):
            parent = el.parent
            if parent and "view" in (parent.get("class") or [""]):
                views = parse_views(str(el))
                break

    # -- Description (first paragraph of intro step) --
    desc = ""
    intro = soup.select_one("div.step-intro p, section.intro p, div.intro-text p")
    if intro:
        desc = intro.get_text(" ", strip=True)[:200]

    project.update({
        "img":         img_url,
        "views":       views,
        "category":    categorise(project["title"], url),
        "description": desc,
    })
    return project


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(f"{DISPLAY_NAME} Instructables scraper")
    print("=" * 60)

    # Load existing data so we don't lose anything on a re-run
    existing = {}
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE) as f:
                for p in json.load(f):
                    existing[p["url"]] = p
            print(f"Loaded {len(existing)} existing projects from {OUTPUT_FILE.name}")
        except Exception as e:
            print(f"Could not load existing file: {e}")

    session = requests.Session()

    # Step 1: get the full list of project URLs
    print("\n[1/2] Fetching project list from profile ...")
    project_list = fetch_project_list(session)
    print(f"      Found {len(project_list)} projects on profile page")

    # Step 2: for each project, fetch detail (skip if already scraped with an image)
    print("\n[2/2] Fetching project details ...")
    results = []
    new_count = 0

    for i, p in enumerate(project_list, 1):
        url = p["url"]
        sys.stdout.write(f"\r      [{i}/{len(project_list)}] ")
        sys.stdout.flush()

        if url in existing and existing[url].get("img"):
            # Already have full data -- keep it, just update title if changed
            cached = existing[url]
            cached["title"] = p["title"]
            results.append(cached)
        else:
            detail = fetch_project_detail(p, session)
            results.append(detail)
            new_count += 1

    print(f"\n      {new_count} new/updated, {len(results) - new_count} from cache")

    # Sort newest first (profile order)
    # Write output
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nDone. Wrote {len(results)} projects to {OUTPUT_FILE}")
    print("\nNext steps:")
    print("  git add projects.json")
    print("  git commit -m 'update projects'")
    print("  git push")


if __name__ == "__main__":
    main()
