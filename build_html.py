#!/usr/bin/env python3
"""
build_html.py
Converts archived index.md files into styled HTML pages.
Reads images directly from markdown so each step gets its own correct images.
Run from the repo root: python3 build_html.py
"""

import re
import json
from pathlib import Path
from collections import defaultdict

ARCHIVE_DIR   = Path("archive/instructables")
PROJECTS_JSON = Path("projects.json")

with open(PROJECTS_JSON) as f:
    projects = json.load(f)

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    background: #0f0f0f;
    color: #d4cfc8;
    font-family: 'Segoe UI', system-ui, sans-serif;
    font-size: 16px;
    line-height: 1.7;
    max-width: 860px;
    margin: 0 auto;
    padding: 80px 24px 80px;
}
h1 {
    font-size: 2em;
    color: #f0ece6;
    line-height: 1.2;
    margin-bottom: 8px;
    border-bottom: 2px solid #e8a020;
    padding-bottom: 12px;
}
h2 {
    font-size: 1.15em;
    color: #e8a020;
    margin: 40px 0 16px;
    padding: 8px 14px;
    background: #1a1a1a;
    border-left: 3px solid #e8a020;
    display: flex;
    align-items: center;
    gap: 10px;
}
.step-num {
    background: #e8a020;
    color: #000;
    font-size: 10px;
    font-weight: bold;
    font-family: monospace;
    padding: 2px 7px;
    letter-spacing: 0.1em;
    white-space: nowrap;
    flex-shrink: 0;
}
p { margin-bottom: 14px; }
img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 12px 0;
    border: 1px solid #2a2a2a;
    border-radius: 2px;
}
.cover-img {
    width: 100%;
    max-height: 480px;
    object-fit: cover;
    margin: 20px 0 32px;
}
.step-images {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 10px;
    margin: 16px 0 20px;
}
.step-images img {
    margin: 0;
    width: 100%;
    height: 200px;
    object-fit: cover;
    border-radius: 2px;
}
.step-images.single img {
    height: auto;
    max-height: 500px;
    object-fit: contain;
    grid-column: 1 / -1;
}
.source a { color: #e8a020; font-size: 11px; font-family: monospace; }
hr { border: none; border-top: 1px solid #2a2a2a; margin: 32px 0; }
ul, ol { padding-left: 24px; margin-bottom: 14px; }
li { margin-bottom: 4px; }
code { background: #1a1a1a; padding: 2px 6px; font-family: monospace; font-size: 0.9em; color: #e8a020; }
a { color: #a0b4c8; text-decoration: none; }
a:hover { color: #d4cfc8; text-decoration: underline; }
.pdf-download {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: #1a1a1a;
    border: 1px solid #e8a020;
    color: #e8a020;
    font-family: monospace;
    font-size: 11px;
    padding: 6px 14px;
    margin: 4px 4px 4px 0;
    text-decoration: none;
    letter-spacing: 0.05em;
}
.pdf-download:hover {{ background: #e8a020; color: #000; text-decoration: none; }}
.nav {
    position: fixed;
    top: 0; left: 0; right: 0;
    background: rgba(10,10,10,0.95);
    border-bottom: 1px solid #2a2a2a;
    padding: 10px 24px;
    display: flex;
    align-items: center;
    gap: 16px;
    font-family: monospace;
    font-size: 11px;
    letter-spacing: 0.1em;
    z-index: 100;
    backdrop-filter: blur(8px);
}
.nav a { color: #e8a020; text-decoration: none; text-transform: uppercase; }
.nav a:hover { color: #fff; }
.nav-title { color: #666; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
"""


def parse_md(md_text):
    """
    Parse markdown into structured steps.
    Each step contains its own images (from ![...] lines) and text.
    Returns: title, source_url, cover_img, list of step dicts
    """
    lines = md_text.split("\n")
    title = ""
    source_url = ""
    cover_img = None
    steps = []
    current = None

    for line in lines:
        # Page title
        if line.startswith("# ") and not title:
            title = line[2:].strip()
            continue

        # Source URL
        if line.startswith("Source: "):
            source_url = line[8:].strip()
            continue

        # Step heading
        if line.startswith("## "):
            if current is not None:
                steps.append(current)
            current = {"title": line[3:].strip(), "images": [], "lines": []}
            continue

        # Image reference
        img_match = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', line.strip())
        if img_match:
            src = img_match.group(2)
            alt = img_match.group(1)
            if current is None:
                # Before any step -- this is the cover
                if "cover" in src.lower():
                    cover_img = src
            else:
                current["images"].append({"src": src, "alt": alt})
            continue

        # Skip HR
        if line.strip() in ("---", "***", "___"):
            continue

        # Regular text
        if current is not None:
            current["lines"].append(line)
        # (ignore lines before first step heading that aren't title/source/image)

    if current is not None:
        steps.append(current)

    return title, source_url, cover_img, steps


def lines_to_html(lines):
    """Convert text lines to HTML."""
    html = []
    in_list = False
    list_type = None

    def next_nonblank(lst, idx):
        for j in range(idx+1, len(lst)):
            if lst[j].strip(): return lst[j].strip()
        return ""

    for line_idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            if in_list:
                nxt = next_nonblank(lines, line_idx)
                if list_type == "ol" and re.match(r"^\d+\.\s", nxt):
                    continue
                if list_type == "ul" and (nxt.startswith("- ") or nxt.startswith("* ")):
                    continue
                html.append(f"</{list_type}>")
                in_list = False
                list_type = None
            continue

        # Skip Instructables UI artifacts
        UI_ARTIFACTS = {
            "View 3 more", "View 3 more images", "I Made It!", "Add a Comment",
            "View more", "Add Tip", "Ask a Question", "Comment", "Favorite", "Share",
        }
        if stripped in UI_ARTIFACTS:
            continue
        if stripped.startswith("*") and stripped.endswith("images archived*"):
            continue
        # Strip inline UI injections that appear mid-text
        stripped = re.sub(r'View \d+ more(?: images?)?', '', stripped).strip()
        if not stripped:
            continue

        # Inline formatting
        stripped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', stripped)
        stripped = re.sub(r'\*(.+?)\*', r'<em>\1</em>', stripped)
        stripped = re.sub(r'`([^`]+)`', r'<code>\1</code>', stripped)
        stripped = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', stripped)

        if stripped.startswith("- ") or stripped.startswith("* "):
            # PDF download link — render as button
            pdf_m = re.match(r'- \[([^\]]+)\]\((pdfs/[^)]+)\)', stripped)
            if pdf_m:
                if in_list:
                    html.append(f"</{list_type}>")
                    in_list = False
                    list_type = None
                label2, path2 = pdf_m.group(1), pdf_m.group(2)
                html.append(f'<a class="pdf-download" href="{path2}" target="_blank">&#8675; {label2}</a>')
            else:
                if not in_list or list_type != "ul":
                    if in_list:
                        html.append(f"</{list_type}>")
                    html.append("<ul>")
                    in_list = True
                    list_type = "ul"
                html.append(f"<li>{stripped[2:]}</li>")
        elif re.match(r'^\d+\.\s', stripped):
            if not in_list or list_type != "ol":
                if in_list:
                    html.append(f"</{list_type}>")
                html.append("<ol>")
                in_list = True
                list_type = "ol"
            html.append(f"<li>{re.sub(r'^\d+\.\s*', '', stripped)}</li>")
        else:
            if in_list:
                html.append(f"</{list_type}>")
                in_list = False
                list_type = None
            html.append(f"<p>{stripped}</p>")

    if in_list:
        html.append(f"</{list_type}>")

    return "\n".join(html)


def build_page(project_dir, force=False):
    index_md  = project_dir / "index.md"
    index_out = project_dir / "index.html"

    if not index_md.exists():
        return False
    if not force and index_out.exists():
        return False

    md_text = index_md.read_text(encoding="utf-8", errors="ignore")
    title, source_url, cover_img, steps = parse_md(md_text)

    if not title:
        title = project_dir.name.replace("-", " ").title()

    body = []

    # Header
    body.append(f"<h1>{title}</h1>")
    if source_url:
        body.append(f'<div class="source"><a href="{source_url}" target="_blank">View on Instructables &rarr;</a></div>')

    # Cover image
    if cover_img:
        body.append(f'<img class="cover-img" src="{cover_img}" alt="{title}" loading="lazy">')

    body.append("<hr>")

    # Steps
    for step in steps:
        step_title = step["title"]
        step_images = step["images"]
        step_lines = step["lines"]

        # Derive a label from the step title rather than a plain counter.
        # "Introduction"        → INTRO
        # "Supplies" etc        → SUPPLIES
        # "Step 3: Foo"         → STEP 3  (number pulled from the title itself)
        # Anything else         → STEP
        title_lower = step_title.lower()
        if title_lower == "introduction":
            label = "INTRO"
        elif title_lower == "downloads":
            label = "FILES"
        elif title_lower in ("supplies", "parts", "things to gather", "what you need",
                             "materials", "tools", "tools and materials"):
            label = "SUPPLIES"
        else:
            m = re.match(r'step\s+(\d+)', title_lower)
            label = f"STEP {m.group(1)}" if m else "STEP"

        body.append(f'<h2><span class="step-num">{label}</span>{step_title}</h2>')

        # Images for this step
        if step_images:
            grid_class = "step-images single" if len(step_images) == 1 else "step-images"
            body.append(f'<div class="{grid_class}">')
            for img in step_images:
                body.append(
                    f'<img src="{img["src"]}" alt="{img["alt"]}" loading="lazy">'
                )
            body.append('</div>')

        # Text for this step
        text_html = lines_to_html(step_lines)
        if text_html.strip():
            body.append(text_html)

        # PDF download links in this step
        for line in step_lines:
            s = line.strip()
            if s.startswith("- [") and "](pdfs/" in s:
                import re as _re
                m = _re.match(r'- \[([^\]]+)\]\((pdfs/[^)]+)\)', s)
                if m:
                    label, path = m.group(1), m.group(2)
                    body.append(f'<a class="pdf-download" href="{path}" target="_blank">&#8675; {label}</a>')

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>{CSS}</style>
</head>
<body>
<nav class="nav">
  <a href="../../README.html">&larr; All Projects</a>
  <span class="nav-title">{title}</span>
</nav>
{"".join(body)}
</body>
</html>"""

    index_out.write_text(html, encoding="utf-8")
    return True


def build_index(projects):
    by_cat = defaultdict(list)
    for p in projects:
        by_cat[p.get("category", "making")].append(p)

    cat_html = ""
    for cat in sorted(by_cat):
        cat_html += f'<h2>{cat.title()}</h2>\n<ul>\n'
        for p in by_cat[cat]:
            from urllib.parse import urlparse
            slug     = urlparse(p["url"]).path.strip("/").split("/")[-1]
            title    = p["title"]
            views    = p.get("views", 0)
            view_str = f"{views:,} views" if views else ""
            folder   = ARCHIVE_DIR / slug
            if (folder / "index.html").exists():
                cat_html += f'<li><a href="instructables/{slug}/index.html">{title}</a>'
                if view_str:
                    cat_html += f' <span class="views">{view_str}</span>'
                cat_html += '</li>\n'
        cat_html += '</ul>\n'

    index_css = CSS + """
    .views { font-size: 11px; color: #666; font-family: monospace; margin-left: 8px; }
    ul { list-style: none; padding: 0; }
    li { padding: 8px 0; border-bottom: 1px solid #1a1a1a; }
    li a { color: #d4cfc8; text-decoration: none; }
    li a:hover { color: #e8a020; }
    """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>lonesoulsurfer - All Projects</title>
<style>{index_css}</style>
</head>
<body>
<h1>lonesoulsurfer</h1>
<p style="color:#666;font-family:monospace;font-size:12px;margin:8px 0 32px">{len(projects)} Instructables &nbsp;|&nbsp; Local archive</p>
<hr>
{cat_html}
</body>
</html>"""

    out = ARCHIVE_DIR.parent / "README.html"
    out.write_text(html, encoding="utf-8")
    print(f"Wrote index: {out}")


def main():
    print("=" * 60)
    print("Building HTML pages from archive")
    print("=" * 60)

    folders = [f for f in ARCHIVE_DIR.iterdir() if f.is_dir()]
    print(f"Found {len(folders)} project folders")

    success = skipped = 0
    for folder in sorted(folders):
        result = build_page(folder, force=True)
        if result:
            success += 1
        else:
            skipped += 1

    print(f"Built {success} HTML pages, skipped {skipped}")

    build_index(projects)

    print()
    print("Done. Open this file in your browser:")
    print(f"  {ARCHIVE_DIR.parent / 'README.html'}")


if __name__ == "__main__":
    main()
