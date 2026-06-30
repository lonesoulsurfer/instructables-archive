#!/usr/bin/env python3
"""
run.py — One-click setup and build for your Instructables archive site.

This is the only script you need to run. It will:
  1. Check/install Python dependencies
  2. Ask for your Instructables + GitHub usernames
  3. Clone (or initialise) your username.github.io repo
  4. Copy the tool files into it
  5. Scrape your Instructables profile
  6. Download your full archive (text, images, PDFs)
  7. Build the HTML site
  8. Commit and push to GitHub

The only thing YOU must do first is create an empty repo on GitHub
named exactly  YOUR_GITHUB_USERNAME.github.io  and enable GitHub Pages.
This script will pause and tell you exactly when and how.
"""
import subprocess
import sys
import os
import shutil
import json
from pathlib import Path

TOOL_FILES = [
    "build_html.py", "check_archive.py", "config.py",
    "setup.py", "update-site.bat", "README.md",
]
TOOL_DIRS = ["scraper"]

HERE = Path(__file__).parent.resolve()


def banner(text):
    print()
    print("=" * 64)
    print(f"  {text}")
    print("=" * 64)
    print()


def ask(prompt, default=None):
    suffix = f" [{default}]" if default else ""
    val = input(f"  {prompt}{suffix}: ").strip()
    return val or default


def run(cmd, cwd=None, check=True):
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    if check and result.returncode != 0:
        print(f"\n  Command failed: {' '.join(cmd)}")
        sys.exit(1)
    return result.returncode == 0


def check_tool(name, version_args=None):
    try:
        subprocess.run(
            [name] + (version_args or ["--version"]),
            capture_output=True, check=True
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def main():
    banner("Instructables Archive — One-Click Setup")

    print("  This will set up your personal Instructables archive site.")
    print("  It will run for a while (1-2 hours during the archive step)")
    print("  so it's a good idea to start this and let it run in the")
    print("  background.")
    print()

    # ── Check prerequisites ──────────────────────────────────────
    banner("Step 1 of 8 — Checking prerequisites")

    if not check_tool("git"):
        print("  Git is not installed. Download it from: https://git-scm.com")
        print("  Install it, then run this script again.")
        sys.exit(1)
    print("  ✓ Git found")

    if sys.version_info < (3, 8):
        print("  Python 3.8+ required. You have:", sys.version)
        sys.exit(1)
    print(f"  ✓ Python {sys.version.split()[0]}")

    # ── Gather info ───────────────────────────────────────────────
    banner("Step 2 of 8 — Your details")

    gh_user = ask("Your GitHub username")
    while not gh_user:
        gh_user = ask("Your GitHub username (required)")

    ig_user = ask("Your Instructables username", default=gh_user)
    display_name = ask("Display name for your site", default=gh_user)

    repo_name = f"{gh_user}.github.io"
    repo_url = f"https://github.com/{gh_user}/{repo_name}"
    site_url = f"https://{gh_user}.github.io"

    # ── The one manual step ──────────────────────────────────────
    banner("Step 3 of 8 — Create your GitHub repo (manual, ~30 seconds)")

    print(f"  Before continuing, you need to create an empty repo on GitHub.")
    print(f"  This is the one step that can't be automated — GitHub requires")
    print(f"  you to be logged in through your browser to create it.")
    print()
    print(f"  1. Go to: https://github.com/new")
    print(f"  2. Repository name:  {repo_name}")
    print(f"     (must match exactly)")
    print(f"  3. Set to Public")
    print(f"  4. Do NOT add a README, .gitignore, or license")
    print(f"  5. Click 'Create repository'")
    print()
    print(f"  Then enable GitHub Pages:")
    print(f"  6. Go to: {repo_url}/settings/pages")
    print(f"  7. Source: 'Deploy from branch'")
    print(f"  8. Branch: main, folder: / (root)  →  Save")
    print()
    input("  Press Enter once you've done this...")

    # ── Clone or init the repo ───────────────────────────────────
    banner("Step 4 of 8 — Setting up your local repo")

    target = Path.home() / repo_name
    if target.exists():
        print(f"  Folder already exists: {target}")
        use_existing = ask("Use this existing folder? (y/n)", default="y")
        if use_existing.lower() != "y":
            print("  Aborting — please remove or rename the existing folder and try again.")
            sys.exit(1)
    else:
        ok = run(["git", "clone", f"{repo_url}.git", str(target)], check=False)
        if not ok:
            print("  Clone failed — the repo might not exist yet, or isn't empty.")
            print(f"  Double check you created it at: https://github.com/new")
            sys.exit(1)

    # ── Copy tool files in ───────────────────────────────────────
    banner("Step 5 of 8 — Installing archive tool files")

    for f in TOOL_FILES:
        src = HERE / f
        if src.exists():
            shutil.copy2(src, target / f)
            print(f"  ✓ {f}")
    for d in TOOL_DIRS:
        src = HERE / d
        if src.exists():
            shutil.copytree(src, target / d, dirs_exist_ok=True)
            print(f"  ✓ {d}/")

    # Write config.py directly — skip the interactive setup.py prompts
    config_content = f'''# config.py — written automatically by run.py
USERNAME = "{ig_user}"
SITE_URL = "{site_url}"
DISPLAY_NAME = "{display_name}"
'''
    (target / "config.py").write_text(config_content, encoding="utf-8")
    print("  ✓ config.py configured")

    # ── Install Python dependencies ──────────────────────────────
    banner("Step 6 of 8 — Installing dependencies")

    run([sys.executable, "-m", "pip", "install", "-q",
         "requests", "beautifulsoup4", "playwright"])
    print("  ✓ Python packages installed")

    run([sys.executable, "-m", "playwright", "install", "chromium"])
    print("  ✓ Playwright browser installed")

    # ── Scrape + archive + build ─────────────────────────────────
    banner("Step 7 of 8 — Scraping and archiving (this takes a while)")

    print("  Scraping your Instructables profile...")
    run([sys.executable, "scraper/scrape.py"], cwd=target)

    print()
    print("  Downloading full archive — text, images, PDFs.")
    print("  This is the slow part: roughly 1-2 hours for ~250 projects.")
    print("  Smaller profiles will be much faster.")
    print()
    run([sys.executable, "scraper/download_archive.py"], cwd=target)

    print()
    print("  Building HTML pages...")
    run([sys.executable, "build_html.py"], cwd=target)

    # ── Push to GitHub ────────────────────────────────────────────
    banner("Step 8 of 8 — Publishing to GitHub")

    run(["git", "add", "."], cwd=target)
    run(["git", "commit", "-m", "initial archive"], cwd=target, check=False)
    run(["git", "push"], cwd=target)

    banner("Done!")
    print(f"  Your site is live at: {site_url}")
    print(f"  (allow a minute or two for GitHub Pages to update)")
    print()
    print(f"  Local folder: {target}")
    print()
    print(f"  To update later after publishing a new Instructable, run")
    print(f"  update-site.bat from inside that folder.")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Cancelled.")
        sys.exit(1)
