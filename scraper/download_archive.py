#!/usr/bin/env python3
"""
download_archive.py  --  Download all Instructables with per-step images.

Strategy:
- Use Playwright to render each page
- Extract step sections via section[class*="_step_"]
- For each step, only take FULL SIZE images (those with frame= in URL)
- Skip width=270 thumbnails entirely
- For the intro section, use og:image cover + first unique full-size images

Usage:
    python3 download_archive.py                    # archive everything
    python3 download_archive.py --new-only         # only new/incomplete
    python3 download_archive.py --url <URL>        # one project
    python3 download_archive.py --force            # re-archive everything
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: Run:  pip install requests beautifulsoup4")
    sys.exit(1)

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from config import USERNAME, DISPLAY_NAME

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ERROR: Run:  pip install playwright && python3 -m playwright install chromium")
    sys.exit(1)

# ── CONFIG ───────────────────────────────────────────────────────────────────
PROJECTS_JSON = Path(__file__).parent.parent / "projects.json"
ARCHIVE_DIR   = Path(__file__).parent.parent / "archive" / "instructables"
PAGE_TIMEOUT  = 45000
SCROLL_WAIT   = 2000
IMG_DELAY     = 0.15
MAX_IMG_SIZE  = 15 * 1024 * 1024

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


# ── HELPERS ──────────────────────────────────────────────────────────────────

def slug_from_url(url):
    path = urlparse(url).path.strip("/")
    return path.split("/")[-1] if path else url

def extract_ext(url):
    path = urlparse(url).path
    ext = os.path.splitext(path)[1].lower()
    return ext if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp") else ".jpg"

def is_full_size(url):
    """Full size images have frame= in URL. Thumbnails have width=270."""
    return "frame=" in url or ("content.instructables.com" in url and "width=" not in url)

def base_url(url):
    """Strip query params to get base image identifier."""
    return url.split("?")[0]

def download_image(url, dest, session):
    if dest.exists():
        return True
    try:
        time.sleep(IMG_DELAY)
        r = session.get(url, headers=HEADERS, timeout=20, stream=True)
        r.raise_for_status()
        size = int(r.headers.get("content-length", 0))
        if size > MAX_IMG_SIZE:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return True
    except Exception:
        return False


def download_pdf_link(a, pdfs_dir, session, seen_hrefs):
    """Download a single PDF link element. Returns dict or None."""
    try:
        href = a.get_attribute('href') or ''
        if not href or '.pdf' not in href.lower():
            return None
        if href.startswith('/'):
            href = 'https://www.instructables.com' + href
        elif not href.startswith('http'):
            return None
        if href in seen_hrefs:
            return None
        seen_hrefs.add(href)
        label = a.inner_text().strip()
        url_fname = Path(href.split('?')[0]).name
        if not label or label.lower() in ('download', 'pdf', ''):
            label = url_fname if url_fname.endswith('.pdf') else 'Download'
        clean = re.sub(r'[^\w\-. ]', '_', label).strip()
        if not clean.lower().endswith('.pdf'):
            clean += '.pdf'
        fname = clean[:80]
        pdfs_dir.mkdir(exist_ok=True)
        dest = pdfs_dir / fname
        if dest.exists() or download_image(href, dest, session):
            return {'label': label.replace('.pdf', ''), 'file': f'pdfs/{fname}'}
        return None
    except Exception:
        return None


def download_pdfs(page, project_dir, session):
    """Find and download all PDF links, grouped by step section."""
    try:
        pdfs_dir = project_dir / "pdfs"
        seen_hrefs = set()
        sections = page.query_selector_all('section[class*="_step_"]')
        if sections:
            result = []
            for section in sections:
                h2 = section.query_selector('h2')
                title = h2.inner_text().strip() if h2 else ''
                links = section.query_selector_all('a[href*=".pdf"]')
                step_pdfs = []
                for a in links:
                    pdf = download_pdf_link(a, pdfs_dir, session, seen_hrefs)
                    if pdf:
                        step_pdfs.append(pdf)
                if step_pdfs:
                    result.append((title, step_pdfs))
            return result
        return []
    except Exception as e:
        print(f"    [warn] PDF download: {e}")
        return []


# ── STEP EXTRACTION ───────────────────────────────────────────────────────────

def extract_page_data(page, url):
    """
    Use Playwright JS evaluation to extract all step data directly from DOM.
    Returns dict with title, cover_url, steps list.
    Each step: {title, text, images: [url, ...]}
    """
    page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
    page.wait_for_timeout(SCROLL_WAIT)
    # Scroll to trigger lazy loading of full-size images
    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
    page.wait_for_timeout(500)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight * 2 / 3)")
    page.wait_for_timeout(500)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1500)

    try:
        data = page.evaluate("""
        () => {
            const result = { title: '', coverUrl: '', steps: [] };

            const h1 = document.querySelector('h1');
            result.title = h1 ? h1.innerText.trim() : document.title.split('|')[0].trim();

            const og = document.querySelector('meta[property="og:image"]');
            result.coverUrl = og ? og.content : '';

            const sections = document.querySelectorAll('section[class*="_step_"]');

            sections.forEach(function(section) {
                const h2 = section.querySelector('h2');
                const title = h2 ? h2.innerText.trim() : 'Introduction';

                if (title.includes('People Made This') || title === 'Recommendations') return;

                const imgs = [];
                const seenBases = new Set();
                section.querySelectorAll('img').forEach(function(img) {
                    const src = img.src || img.getAttribute('data-src') || '';
                    if (!src.includes('content.instructables.com')) return;
                    const base = src.split('?')[0];
                    if (seenBases.has(base)) return;
                    seenBases.add(base);
                    imgs.push(base);
                });

                const bodyEl = section.querySelector('[class*="_stepBody_"]') || section;
                const parts = [];

                // Convert element content to markdown, preserving <a href> as [text](url)
                function inlineMd(el) {
                    let out = '';
                    const kids = Array.from(el.childNodes);
                    for (let ci = 0; ci < kids.length; ci++) {
                        const child = kids[ci];
                        if (child.nodeType === 3) {
                            out += child.textContent;
                        } else if (child.nodeType === 1) {
                            const tag = child.tagName.toLowerCase();
                            if (tag === 'a') {
                                const href = child.getAttribute('href') || '';
                                const label = child.innerText.trim();
                                if (href.indexOf('http') === 0 && label) {
                                    out += '[' + label + '](' + href + ')';
                                } else {
                                    out += child.innerText || '';
                                }
                            } else if (tag === 'br') {
                                out += ' ';
                            } else if (tag !== 'script' && tag !== 'style') {
                                out += inlineMd(child);
                            }
                        }
                    }
                    return out.replace(/\s+/g, ' ').trim();
                }

                function nodeToMd(el) {
                    const kids = Array.from(el.childNodes);
                    for (let ci = 0; ci < kids.length; ci++) {
                        const child = kids[ci];
                        if (child.nodeType === 3) {
                            const t = child.textContent.replace(/\s+/g, ' ').trim();
                            if (t) parts.push(t);
                        } else if (child.nodeType === 1) {
                            const tag = child.tagName.toLowerCase();
                            if (tag === 'p') {
                                const pt = inlineMd(child);
                                if (pt) { parts.push(pt); parts.push(''); }
                            } else if (tag === 'ul') {
                                const lis = child.querySelectorAll(':scope > li');
                                for (let i = 0; i < lis.length; i++) {
                                    parts.push('- ' + inlineMd(lis[i]));
                                }
                                parts.push('');
                            } else if (tag === 'ol') {
                                const lis = child.querySelectorAll(':scope > li');
                                for (let i = 0; i < lis.length; i++) {
                                    parts.push((i + 1) + '. ' + inlineMd(lis[i]));
                                }
                                parts.push('');
                            } else if (tag === 'li') {
                                parts.push('- ' + inlineMd(child));
                            } else if (tag === 'h3' || tag === 'h4' || tag === 'h5') {
                                const ht = inlineMd(child);
                                if (ht) { parts.push('**' + ht + '**'); parts.push(''); }
                            } else if (tag === 'br') {
                                parts.push('');
                            } else if (tag !== 'script' && tag !== 'style' && tag !== 'img' && tag !== 'h2') {
                                nodeToMd(child);
                            }
                        }
                    }
                }

                nodeToMd(bodyEl);
                const text = parts.join('\\n').replace(/\\n\\n\\n+/g, '\\n\\n').trim();
                result.steps.push({ title: title, images: imgs, text: text });
            });

            return result;
        }
    """)
    except Exception:
        data = {"title": "", "coverUrl": "", "steps": []}

    return data


# ── GET INTRO IMAGES ──────────────────────────────────────────────────────────

def get_intro_images(page, cover_url):
    """
    Get intro/hero images from the _mobilePhotoset_ container.
    This is the intro image carousel at the top of the page.
    """
    imgs = page.evaluate("""
        () => {
            const imgs = [];
            const seenBases = new Set();

            // The intro images live in _mobilePhotoset_ divs
            // This is the only reliable container for hero shots
            const photoset = document.querySelector('[class*="_mobilePhotoset_"]');
            if (!photoset) return imgs;

            photoset.querySelectorAll('img').forEach(function(img) {
                const src = img.src || '';
                if (!src.includes('content.instructables.com')) return;

                const base = src.split('?')[0];
                if (seenBases.has(base)) return;
                seenBases.add(base);
                imgs.push(base);
            });

            return imgs;
        }
    """)

    # Exclude cover image
    cover_base = cover_url.split("?")[0] if cover_url else ""
    return [i for i in imgs if i != cover_base][:6]


def get_view_count(page):
    """Extract the view count using the data-testid attribute (JS-rendered)."""
    try:
        el = page.query_selector('[data-testid="project-view-count"]')
        if el:
            text = el.inner_text().strip()
            text = text.lower().replace(",", "")
            if text.endswith("m"):
                return int(float(text[:-1]) * 1_000_000)
            if text.endswith("k"):
                return int(float(text[:-1]) * 1_000)
            return int(text)
    except Exception:
        pass
    return 0


def archive_project(url, project_title, page, session, force=False):
    folder_name = slug_from_url(url)
    project_dir = ARCHIVE_DIR / folder_name
    index_path  = project_dir / "index.md"
    images_dir  = project_dir / "images"

    # Skip if already done with per-step images
    if not force and index_path.exists():
        step_imgs = list(images_dir.glob("step*")) if images_dir.exists() else []
        if len(step_imgs) > 0:
            print(f"  [skip] {folder_name}")
            return True

    print(f"  Archiving: {project_title[:60]}")
    project_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    try:
        data = extract_page_data(page, url)
    except Exception as e:
        print(f"    [error] page load: {e}")
        return False

    title     = data.get("title") or project_title
    views     = get_view_count(page)

    # Update the view count in projects.json for this URL
    try:
        projects_path = Path(__file__).parent.parent / "projects.json"
        if projects_path.exists():
            import json as _json
            with open(projects_path, encoding="utf-8") as f:
                all_projects = _json.load(f)
            changed = False
            for p in all_projects:
                if p.get("url") == url and views:
                    if p.get("views") != views:
                        p["views"] = views
                        changed = True
                    break
            if changed:
                with open(projects_path, "w", encoding="utf-8") as f:
                    _json.dump(all_projects, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"    [warn] could not update projects.json views: {e}")

    cover_url = data.get("coverUrl", "")
    steps     = data.get("steps", [])

    # Get intro images
    intro_images = get_intro_images(page, cover_url)

    lines = []
    lines.append(f"# {title}\n")
    lines.append(f"Source: {url}\n")
    lines.append("---\n")

    # Download cover image
    if cover_url and "content.instructables.com" in cover_url:
        ext   = extract_ext(cover_url)
        fname = f"cover{ext}"
        if download_image(cover_url, images_dir / fname, session):
            lines.append(f"![Cover](images/{fname})\n")

    total_imgs = 0

    # Add intro section — images from _mobilePhotoset_, text from the DOM intro step
    intro_text = ""
    for step in steps:
        if step.get("title") == "Introduction":
            intro_text = step.get("text", "")
            break

    # Fallback: if page.evaluate failed, extract all step text via Playwright Python API
    SKIP_TEXT = {"I Made It!", "Add a Comment", "Favorite", "Share", "Add Tip", "Ask a Question"}
    if not steps or all(not s.get("text") for s in steps):
        try:
            all_sections = page.query_selector_all('section[class*="_step_"]')
            for section in all_sections:
                h2 = section.query_selector('h2')
                title = h2.inner_text().strip() if h2 else 'Introduction'
                if 'People Made This' in title or title == 'Recommendations':
                    continue
                # Get images
                img_els = section.query_selector_all('img')
                img_urls = []
                seen = set()
                for img in img_els:
                    src = img.get_attribute('src') or ''
                    if 'content.instructables.com' not in src:
                        continue
                    base = src.split('?')[0]
                    if base not in seen:
                        seen.add(base)
                        img_urls.append(base)
                # Get text — paragraphs, list items, headings
                body = section.query_selector('[class*="_stepBody_"]') or section
                els = body.query_selector_all('p, li, h3, h4, h5') if body else []
                parts = []
                for el in els:
                    tag = el.evaluate('el => el.tagName.toLowerCase()')
                    if tag == 'li':
                        # Skip nested li (parent is another li)
                        is_nested = el.evaluate('el => el.parentElement && el.parentElement.parentElement && el.parentElement.parentElement.tagName.toLowerCase() === "li"')
                        if is_nested:
                            continue
                        # Get direct text only, exclude nested list text
                        t = el.evaluate("""el => {
                            var out = '';
                            el.childNodes.forEach(function(n) {
                                if (n.nodeType === 3) out += n.textContent;
                                else if (n.nodeType === 1) {
                                    var nt = n.tagName.toLowerCase();
                                    if (nt !== 'ul' && nt !== 'ol') out += (n.innerText || '');
                                }
                            });
                            return out.trim();
                        }""")
                        # Preserve links
                        try:
                            links = el.query_selector_all('a')
                            for a in links:
                                href = a.get_attribute('href') or ''
                                lbl = a.inner_text().strip()
                                if href.startswith('http') and lbl:
                                    t = t.replace(lbl, f'[{lbl}]({href})', 1)
                        except Exception:
                            pass
                    else:
                        t = el.inner_text().strip()
                        if tag == 'p':
                            try:
                                links = el.query_selector_all('a')
                                for a in links:
                                    href = a.get_attribute('href') or ''
                                    lbl = a.inner_text().strip()
                                    if href.startswith('http') and lbl:
                                        t = t.replace(lbl, f'[{lbl}]({href})', 1)
                            except Exception:
                                pass
                    if not t or t in SKIP_TEXT:
                        continue
                    if tag == 'li':
                        parts.append('- ' + t)
                    elif tag in ('h3', 'h4', 'h5'):
                        parts.append('**' + t + '**')
                        parts.append('')
                    else:
                        parts.append(t)
                        parts.append('')

                # Fallback for older pages with no <p>/<li> tags — use raw inner_text
                if not parts:
                    try:
                        raw = section.inner_text().strip()
                        h2 = section.query_selector('h2')
                        if h2:
                            raw = raw[len(h2.inner_text()):].strip()
                        # Collect links to inject back into text
                        link_map = {}
                        try:
                            for a in section.query_selector_all('a'):
                                href = a.get_attribute('href') or ''
                                lbl = a.inner_text().strip()
                                if href.startswith('http') and lbl:
                                    link_map[lbl] = href
                        except Exception:
                            pass
                        for para in raw.split('\n\n'):
                            para = para.strip().replace('\xa0', ' ')
                            if not para or para in SKIP_TEXT or len(para) <= 3:
                                continue
                            # Inject markdown links
                            for lbl, href in link_map.items():
                                if lbl in para:
                                    para = para.replace(lbl, f'[{lbl}]({href})', 1)
                            parts.append(para)
                            parts.append('')
                    except Exception:
                        pass

                text = "\n".join(parts).strip()
                steps.append({"title": title, "images": img_urls, "text": text})
        except Exception as e:
            print(f"    [warn] fallback extraction: {e}")

    # Extract intro text from steps list
    if not intro_text:
        for step in steps:
            if step.get("title") == "Introduction":
                intro_text = step.get("text", "")
                break

    if intro_images or intro_text:
        lines.append("\n## Introduction\n")
        img_count = 0
        for img_url in intro_images:
            img_count += 1
            ext   = extract_ext(img_url)
            fname = f"intro_{img_count:02d}{ext}"
            if download_image(img_url, images_dir / fname, session):
                lines.append(f"![Intro {img_count}](images/{fname})\n")
                total_imgs += 1
        if intro_text:
            lines.append(intro_text + "\n")

    # Download PDFs grouped by step
    pdf_by_step = download_pdfs(page, project_dir, session)
    pdf_lookup_norm = {t.lower().strip(): ps for t, ps in pdf_by_step}
    all_pdfs = [(t, p) for t, ps in pdf_by_step for p in ps]
    total_pdfs = len(all_pdfs)

    # Process each step — use a separate counter so skipped steps don't offset it
    real_step_idx = 0
    pending_pdfs = list(pdf_lookup_norm.get("introduction", []))
    if pending_pdfs:
        for pdf in pending_pdfs:
            lines.append(f"- [{pdf['label']}]({pdf['file']})")
        lines.append("")

    for step in steps:
        step_title  = step.get("title", "")
        step_images = step.get("images", [])
        step_text   = step.get("text", "")

        # Skip intro (handled above) and junk sections
        if step_title in ("Introduction", "5 People Made This Project!", "Recommendations"):
            continue

        real_step_idx += 1
        lines.append(f"\n## {step_title}\n")

        # Download images for this step
        img_count = 0
        for img_url in step_images:
            img_count += 1
            ext   = extract_ext(img_url)
            fname = f"step{real_step_idx:02d}_{img_count:02d}{ext}"
            if download_image(img_url, images_dir / fname, session):
                lines.append(f"![{step_title} image {img_count}](images/{fname})\n")
                total_imgs += 1

        # Write step text with paragraph breaks preserved
        if step_text:
            cleaned = re.sub(r'\n{3,}', '\n\n', step_text).strip()
            lines.append(cleaned + "\n")

        # Inject PDFs that belong to this step
        norm = step_title.lower().strip()
        if norm in pdf_lookup_norm:
            lines.append("")
            for pdf in pdf_lookup_norm[norm]:
                lines.append(f"- [{pdf['label']}]({pdf['file']})")

    # Always add a Downloads section listing every PDF found
    if all_pdfs:
        lines.append("\n## Downloads\n")
        for _, pdf in all_pdfs:
            lines.append(f"- [{pdf['label']}]({pdf['file']})")

    lines.append(f"\n---\n*{total_imgs} images archived*\n")

    with open(index_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"    {len(steps)} steps, {total_imgs} images, {total_pdfs} PDFs")
    return True


# ── ARCHIVE INDEX ─────────────────────────────────────────────────────────────

def write_archive_index(projects):
    from collections import defaultdict
    index_path = ARCHIVE_DIR.parent / "README.md"
    lines = [f"# {DISPLAY_NAME} -- Instructables Archive\n\n"]
    by_cat = defaultdict(list)
    for p in projects:
        by_cat[p.get("category", "making")].append(p)
    for cat in sorted(by_cat):
        lines.append(f"\n## {cat.title()}\n")
        for p in by_cat[cat]:
            slug     = slug_from_url(p["url"])
            views    = p.get("views", 0)
            view_str = f"{views:,}" if views else "--"
            lines.append(f"- [{p['title']}](instructables/{slug}/index.md) ({view_str} views)\n")
    with open(index_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"Wrote archive index: {index_path}")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--new-only", action="store_true")
    parser.add_argument("--url",      type=str)
    parser.add_argument("--force",    action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print(f"{DISPLAY_NAME} archive downloader (per-step images)")
    print("=" * 60)

    session = requests.Session()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page    = browser.new_page()
        page.set_default_timeout(PAGE_TIMEOUT)

        if args.url:
            title = args.url.rstrip("/").split("/")[-1].replace("-", " ").title()
            archive_project(args.url.rstrip("/") + "/", title, page, session, force=True)
            browser.close()
            return

        if not PROJECTS_JSON.exists():
            print(f"ERROR: {PROJECTS_JSON} not found.")
            browser.close()
            sys.exit(1)

        with open(PROJECTS_JSON) as f:
            projects = json.load(f)

        print(f"Loaded {len(projects)} projects")

        to_process = []
        for proj in projects:
            folder    = ARCHIVE_DIR / slug_from_url(proj["url"])
            imgs_dir  = folder / "images"
            step_imgs = list(imgs_dir.glob("step*")) if imgs_dir.exists() else []
            if args.force or not folder.exists() or len(step_imgs) == 0:
                to_process.append(proj)

        print(f"  {len(projects) - len(to_process)} already archived")
        print(f"  {len(to_process)} to process")

        if not to_process:
            print("Nothing to do.")
            browser.close()
            return

        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        success = fail = 0

        for i, proj in enumerate(to_process, 1):
            print(f"\n[{i}/{len(to_process)}]")
            ok = archive_project(
                proj["url"], proj["title"], page, session, force=args.force
            )
            if ok:
                success += 1
            else:
                fail += 1

        browser.close()

    with open(PROJECTS_JSON) as f:
        all_projects = json.load(f)
    write_archive_index(all_projects)

    print(f"\n{'='*60}")
    print(f"Done. {success} archived, {fail} failed.")
    print("Run: python3 build_html.py")
    print("="*60)


if __name__ == "__main__":
    main()
