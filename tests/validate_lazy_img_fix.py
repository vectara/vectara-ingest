#!/usr/bin/env python3
"""
Standalone validation confirming the root cause and fix for TI forum image extraction.

Root cause: Docling's _resolve_relative_path treats root-relative paths (/path) as
protocol-relative (//host/path), producing "https:/path" (one slash, no domain).
Requests fails silently; image is skipped.

Fix: Override _resolve_relative_path to reconstruct origin from base_path.

Secondary issue: image data must be validated with PIL before returning (truncated
data causes OSError in Docling's _create_image_ref which doesn't catch it).

Usage:
    python tests/validate_lazy_img_fix.py
"""

import os
import re
import sys
import tempfile
from urllib.parse import urlparse

import requests as req_lib

TI_URL = (
    "https://e2e.ti.com/support/data-converters-group/data-converters/f/"
    "data-converters-forum/1084390/ads42lb49-analog-interface-dc-couple"
)

IMAGE_ACCEPT = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": IMAGE_ACCEPT,
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": TI_URL,
}


def fetch_page(url: str):
    """Fetch HTML + cookies via Playwright. Returns (html, cookies_dict, img_srcs)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        def route_handler(route):
            if route.request.resource_type in ["image", "font", "media"]:
                route.abort()
            else:
                route.continue_()

        page.route("**/*", route_handler)
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(5_000)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(2_000)
        html = page.content()
        cookies = {c["name"]: c["value"] for c in context.cookies()}
        img_srcs = page.evaluate("""
            () => [...document.querySelectorAll('img[src]')]
                .map(i => i.src).filter(s => s.startsWith('http'))
        """)
        browser.close()
    return html, cookies, img_srcs


def probe_url(label: str, img_url: str, cookies: dict = None):
    """Try to fetch an image URL and report what TI returns."""
    sess = req_lib.Session()
    if cookies:
        sess.cookies.update(cookies)
    try:
        r = sess.get(img_url, headers=BROWSER_HEADERS, timeout=15, allow_redirects=True)
        ct = r.headers.get("content-type", "?")
        print(f"  [{label:30s}] {r.status_code}  content-type={ct!r}  len={len(r.content)}")
        return r
    except Exception as e:
        print(f"  [{label:30s}] ERROR: {e}")
        return None


def make_backend(base_url: str, cookies: dict, fix_resolve: bool):
    """Return a configured HTMLDocumentBackend subclass."""
    from docling.backend.html_backend import HTMLDocumentBackend
    from PIL import Image
    from io import BytesIO
    from typing import Optional

    sess = req_lib.Session()
    if cookies:
        sess.cookies.update(cookies)

    class TestBackend(HTMLDocumentBackend):
        def __init__(self, in_doc, path_or_stream, options=None):
            super().__init__(in_doc, path_or_stream, options)
            # Always set base_path so relative URL resolution has a domain to work with
            self.base_path = base_url

        def _resolve_relative_path(self, loc: str) -> str:
            if fix_resolve and loc.startswith("/") and not loc.startswith("//"):
                # Fix: reconstruct correct absolute URL from origin + root-relative path
                parsed = urlparse(self.base_path)
                if parsed.scheme and parsed.netloc:
                    resolved = f"{parsed.scheme}://{parsed.netloc}{loc}"
                    return resolved
            return super()._resolve_relative_path(loc)

        def _load_image_data(self, src_loc: str) -> Optional[bytes]:
            if HTMLDocumentBackend._is_remote_url(src_loc):
                try:
                    r = sess.get(src_loc, headers=BROWSER_HEADERS, timeout=10, stream=True)
                    r.raise_for_status()
                    if r.headers.get("content-type", "").startswith("image/"):
                        data = r.content
                        # Validate image is complete — prevents OSError in Docling's
                        # _create_image_ref which doesn't catch PIL truncation errors
                        img = Image.open(BytesIO(data))
                        img.load()
                        return data
                except Exception:
                    pass
                return None
            return super()._load_image_data(src_loc)

    return TestBackend


def count_pictures(html: str, backend_cls) -> int:
    """Run Docling with given backend and return number of PictureItems with image data."""
    from docling.datamodel.backend_options import HTMLBackendOptions
    from docling.datamodel.pipeline_options import PaginatedPipelineOptions
    from docling.document_converter import DocumentConverter, HTMLFormatOption, InputFormat
    from docling_core.types.doc import PictureItem

    html_opts = PaginatedPipelineOptions()
    html_opts.generate_page_images = False
    backend_opts = HTMLBackendOptions(fetch_images=True, enable_remote_fetch=True)

    converter = DocumentConverter(
        allowed_formats=[InputFormat.HTML],
        format_options={
            InputFormat.HTML: HTMLFormatOption(
                backend=backend_cls,
                pipeline_options=html_opts,
                backend_options=backend_opts,
            ),
        },
    )

    with tempfile.NamedTemporaryFile(
        suffix=".html", mode="w", encoding="utf-8", delete=False
    ) as f:
        f.write(html)
        tmp = f.name

    try:
        result = converter.convert(tmp)
        doc = result.document
        return sum(
            1 for item, _ in doc.iterate_items()
            if isinstance(item, PictureItem) and item.image is not None
        )
    finally:
        os.unlink(tmp)


def main() -> int:
    print("=" * 60)
    print("Step 1: Fetch page via Playwright")
    print("=" * 60)
    html, cookies, img_srcs = fetch_page(TI_URL)
    html_bytes = html.encode("utf-8")

    ri_in_src = re.findall(
        rb'\bsrc=["\']([^"\']*resized-image[^"\']*)["\']', html_bytes, re.IGNORECASE
    )
    print(f"  HTML size            : {len(html_bytes):,} bytes")
    print(f"  'resized-image' in src=  : {len(ri_in_src)}")
    for v in ri_in_src:
        print(f"    -> {v.decode()}")
    print(f"  Browser cookies      : {len(cookies)}")

    # Resolve to absolute URLs for probing
    target_urls = [u for u in img_srcs if "resized-image" in u]
    if not target_urls:
        base_origin = "https://e2e.ti.com"
        target_urls = [base_origin + v.decode() for v in ri_in_src if v.startswith(b"/")]

    print()
    print("=" * 60)
    print("Step 2: Probe what TI returns for circuit diagram URLs")
    print("=" * 60)
    for img_url in target_urls[:2]:
        print(f"  {img_url[:80]}")
        probe_url("no cookies", img_url)
        probe_url("with Playwright cookies", img_url, cookies=cookies)
        print()

    print("=" * 60)
    print("Step 3: Docling — vanilla (broken _resolve, no PIL validation)")
    print("= (expected: 0 circuit images or crash)")
    print("=" * 60)
    broken_cls = make_backend(TI_URL, cookies={}, fix_resolve=False)
    try:
        n_broken = count_pictures(html, broken_cls)
        print(f"  Images: {n_broken}")
    except Exception as e:
        print(f"  CRASHED: {e}")
        n_broken = "crash"

    print()
    print("=" * 60)
    print("Step 4: Docling — fixed _resolve_relative_path, no cookies")
    print("= (expected: attempt correct URLs but may fail if cookies needed)")
    print("=" * 60)
    fixed_no_cookies = make_backend(TI_URL, cookies={}, fix_resolve=True)
    n_fixed_nc = count_pictures(html, fixed_no_cookies)
    print(f"  Images: {n_fixed_nc}")

    print()
    print("=" * 60)
    print("Step 5: Docling — fixed _resolve_relative_path + Playwright cookies")
    print("= (expected: circuit diagram images extracted)")
    print("=" * 60)
    fixed_with_cookies = make_backend(TI_URL, cookies=cookies, fix_resolve=True)
    n_fixed_wc = count_pictures(html, fixed_with_cookies)
    print(f"  Images: {n_fixed_wc}")

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Broken (original)               : {n_broken}")
    print(f"  Fixed resolve, no cookies        : {n_fixed_nc}")
    print(f"  Fixed resolve + Playwright cookies: {n_fixed_wc}")
    print()

    if n_fixed_wc > (n_broken if isinstance(n_broken, int) else 0):
        print("✓ FIX CONFIRMED: _resolve_relative_path fix works.")
        if n_fixed_wc > n_fixed_nc:
            print("  → Session cookies are also needed for the actual image fetch.")
        else:
            print("  → No session cookies needed — browser headers are sufficient.")
        return 0
    else:
        print("✗ STILL FAILING — investigate Step 2 probe output for clues.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
