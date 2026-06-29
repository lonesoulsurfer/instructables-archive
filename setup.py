#!/usr/bin/env python3
"""
setup.py  —  First-time setup for your Instructables archive site.
Run this once after cloning the repo.
"""
import subprocess
import sys
import os
from pathlib import Path

print()
print("=" * 60)
print("  Instructables Archive — Setup")
print("=" * 60)
print()
print("This will configure your personal archive site.")
print("You'll need your Instructables username and GitHub username.")
print()

# Get username
while True:
    username = input("  Your Instructables username: ").strip()
    if username:
        break
    print("  Please enter a username.")

# Get display name
display_name = input(f"  Display name on site [{username}]: ").strip() or username

# Get GitHub username (may differ from Instructables)
gh_user = input(f"  Your GitHub username [{username}]: ").strip() or username

site_url = f"https://{gh_user}.github.io"
print(f"\n  Site URL will be: {site_url}")

# Write config.py
config = f'''# ─────────────────────────────────────────────────────────────
#  config.py  —  Your personal settings
#  Edit this file if you need to change anything later.
# ─────────────────────────────────────────────────────────────

# Your Instructables username
USERNAME = "{username}"

# Your GitHub Pages URL
SITE_URL = "{site_url}"

# Display name shown on the site
DISPLAY_NAME = "{display_name}"
'''

Path("config.py").write_text(config, encoding="utf-8")
print("\n  ✓ config.py written")

# Check Python dependencies
print("\n  Checking dependencies...")
deps = ["requests", "beautifulsoup4", "playwright"]
missing = []
for dep in deps:
    try:
        __import__(dep.replace("-", "_").split("[")[0])
        print(f"    ✓ {dep}")
    except ImportError:
        print(f"    ✗ {dep} (missing)")
        missing.append(dep)

if missing:
    print(f"\n  Installing missing packages: {', '.join(missing)}")
    subprocess.run([sys.executable, "-m", "pip", "install"] + missing, check=True)

# Check playwright browsers
print("\n  Checking Playwright browsers...")
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        browser.close()
    print("    ✓ Playwright browsers installed")
except Exception:
    print("    Installing Playwright browsers (this may take a minute)...")
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    print("    ✓ Done")

print()
print("=" * 60)
print("  Setup complete!")
print("=" * 60)
print()
print("  Next steps:")
print()
print("  1. Scrape your Instructables profile:")
print("       python scraper/scrape.py")
print()
print("  2. Download your archive:")
print("       python scraper/download_archive.py")
print()
print("  3. Build HTML pages:")
print("       python build_html.py")
print()
print("  4. Push to GitHub:")
print("       git add .")
print('       git commit -m "initial archive"')
print("       git push")
print()
print(f"  Your site will be live at: {site_url}")
print()
