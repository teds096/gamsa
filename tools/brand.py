#!/usr/bin/env python3
"""One brand command: run after any logo or colour change, after adding or renaming a medicine or hub,
and after replacing any downloadable PDF (e.g. a fresh export of the SOP from Word/Writer).

  python3 tools/brand.py          # share images + icons (og_images.py), then logo + stripe on PDFs (pdf_brand.py)
  python3 tools/brand.py pdfs     # PDFs only (no browser needed)
Needs Pillow, Playwright Chromium (CHROME=/path if not bundled) and pymupdf.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import og_images, pdf_brand
if __name__ == "__main__":
    if "pdfs" not in sys.argv[1:]: og_images.main()
    pdf_brand.main()
