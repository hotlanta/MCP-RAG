# extract_pdf_images.py  ← FINAL VERSION (works everywhere)
import fitz
import sys
from pathlib import Path

if len(sys.argv) != 3:
    print("Usage: python extract_pdf_images.py input.pdf output_folder/")
    sys.exit(1)

doc = fitz.open(sys.argv[1])
out = Path(sys.argv[2])
out.mkdir(exist_ok=True)

for page_num, page in enumerate(doc, start=1):
    for img_index, img in enumerate(page.get_images(full=True), start=1):
        xref = img[0]
        pix = fitz.Pixmap(doc, xref)
        if pix.n - pix.alpha < 4:  # ignore CMYK
            img_name = out / f"page{page_num:03d}_img{img_index:02d}.png"
            pix.save(img_name)
            rel_path = img_name.name
            print(f"![Image from page {page_num}]({rel_path} \"Describe this diagram\")")
        pix = None  # free memory