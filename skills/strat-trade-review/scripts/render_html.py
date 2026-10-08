#!/usr/bin/env python3
"""Render an HTML card template to PNG with a headless Chromium-family browser.

A template is one self-contained HTML file (see ../templates/). It holds a placeholder,

    <script id="card-data" type="application/json">{}</script>

that is replaced with the card's data, and declares its size:

    <meta name="card-size" content="1200x675">

The browser is found in this order: Python Playwright (if installed), then a Chrome, Chromium or Edge
binary ($STRAT_CHROME, the PATH, the usual macOS and Windows install paths, Playwright's cache). If none is
found, render() returns False and the caller falls back to the matplotlib images.

  python3 render_html.py --template ../templates/card.html --data share/card.json --out share/card.png
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

SCALE = 2   # device pixels per CSS pixel: 1200x675 renders as 2400x1350, sharp on phones and in Discord


def card_size(html: str) -> tuple[int, int]:
    m = re.search(r'<meta\s+name="card-size"\s+content="(\d+)x(\d+)"', html)
    return (int(m.group(1)), int(m.group(2))) if m else (1200, 675)


def fill(html: str, data: dict) -> str:
    blob = json.dumps(data).replace("</", "<\\/")   # keep "</script>" in a string from closing the tag
    out, n = re.subn(r'(<script id="card-data" type="application/json">).*?(</script>)',
                     lambda m: m.group(1) + blob + m.group(2), html, count=1, flags=re.S)
    if not n:
        raise ValueError('template has no <script id="card-data" type="application/json"> placeholder')
    return out


def find_browser() -> str | None:
    env = os.environ.get("STRAT_CHROME")
    if env and Path(env).exists():
        return env
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge",
                 "microsoft-edge"):
        p = shutil.which(name)
        if p:
            return p
    for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Chromium.app/Contents/MacOS/Chromium",
              "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              "/opt/pw-browsers/chromium"):
        if Path(p).exists():
            return p
    for root in (os.environ.get("PLAYWRIGHT_BROWSERS_PATH"), Path.home() / ".cache/ms-playwright"):
        if root and Path(root).exists():
            hits = sorted(Path(root).glob("chromium-*/chrome-*/chrome")) + \
                   sorted(Path(root).glob("chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"))
            if hits:
                return str(hits[-1])
    return None


def _with_playwright(page_path: Path, out: Path, w: int, h: int) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=SCALE)
            pg.goto(page_path.as_uri(), wait_until="networkidle")
            pg.evaluate("document.fonts.ready")
            pg.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": w, "height": h})
            b.close()
        return out.exists()
    except Exception:
        return False


def _with_cli(browser: str, page_path: Path, out: Path, w: int, h: int) -> bool:
    # headless Chrome's --window-size includes window chrome, so the page area comes out short: shoot a taller
    # window and crop back to the card (the page background fills the extra)
    pad = 240
    cmd = [browser, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
           f"--force-device-scale-factor={SCALE}", f"--window-size={w},{h + pad}",
           "--virtual-time-budget=6000",          # let web fonts load before the shot
           f"--screenshot={out}", page_path.as_uri()]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=90)
    except (subprocess.SubprocessError, OSError):
        return False
    if not out.exists():
        return False
    try:
        from PIL import Image
        with Image.open(out) as im:
            im.crop((0, 0, w * SCALE, h * SCALE)).save(out)
    except ImportError:
        pass   # keep the taller image; the extra is plain background
    return True


def render(template: Path, data: dict, out: Path) -> bool:
    """Fill `template` with `data` and screenshot it to `out`. False if no browser could do it."""
    html = Path(template).read_text(encoding="utf-8")
    w, h = card_size(html)
    out = Path(out).resolve()
    if out.exists():
        out.unlink()
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "card.html"
        page.write_text(fill(html, data), encoding="utf-8")
        if _with_playwright(page, out, w, h):
            return True
        browser = find_browser()
        return bool(browser) and _with_cli(browser, page, out, w, h)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--template", required=True)
    ap.add_argument("--data", required=True, help="JSON file with the card's data")
    ap.add_argument("--out", required=True, help="PNG to write")
    args = ap.parse_args(argv)
    ok = render(Path(args.template), json.loads(Path(args.data).read_text()), Path(args.out))
    print(f"wrote {args.out}" if ok else "no headless browser found (set STRAT_CHROME to a Chrome or Edge binary)")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
