"""
check_archive.py
Run from the repo root to check how complete the archive is.
Usage: python3 check_archive.py
"""
import json
import os
from pathlib import Path
from urllib.parse import urlparse

ARCHIVE_DIR = Path("archive/instructables")
PROJECTS_FILE = Path("projects.json")

with open(PROJECTS_FILE) as f:
    projects = json.load(f)

print("=" * 60)
print("Archive completeness check")
print("=" * 60)
print()

missing_folder = []
missing_index  = []
missing_images = []
empty_index    = []
ok             = []

for p in projects:
    url    = p["url"]
    title  = p["title"]
    slug   = urlparse(url).path.strip("/").split("/")[-1]
    folder = ARCHIVE_DIR / slug
    index  = folder / "index.md"
    images = folder / "images"

    if not folder.exists():
        missing_folder.append(title)
        continue

    if not index.exists():
        missing_index.append(title)
        continue

    if index.stat().st_size < 100:
        empty_index.append(title)

    img_files = list(images.glob("*")) if images.exists() else []
    if not img_files:
        missing_images.append(title)
    else:
        ok.append((title, len(img_files)))

print(f"Total projects in projects.json : {len(projects)}")
print(f"Fully archived (with images)    : {len(ok)}")
print(f"Archived but no images          : {len(missing_images)}")
print(f"Missing index.md                : {len(missing_index)}")
print(f"Folder missing entirely         : {len(missing_folder)}")
print(f"Index too small (may be empty)  : {len(empty_index)}")
print()

if missing_folder:
    print("MISSING FOLDERS (not archived at all):")
    for t in missing_folder:
        print(f"  - {t}")
    print()

if missing_images:
    print("ARCHIVED BUT NO IMAGES:")
    for t in missing_images:
        print(f"  - {t}")
    print()

if empty_index:
    print("POSSIBLY EMPTY INDEX FILES:")
    for t in empty_index:
        print(f"  - {t}")
    print()

total_images = sum(c for _, c in ok)
print(f"Total images downloaded: {total_images}")

if ok:
    best = max(ok, key=lambda x: x[1])
    print(f"Most images: {best[0]} ({best[1]} images)")

print()
print("=" * 60)
if not missing_folder and not missing_index:
    print("All projects have been archived.")
else:
    print(f"{len(missing_folder) + len(missing_index)} projects need attention.")
    print("Run: python3 scraper/download_archive.py to fix missing ones.")
print("=" * 60)
