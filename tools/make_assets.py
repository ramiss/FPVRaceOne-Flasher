"""Generate the flasher's GUI image and Windows icon from the product render.

Source: the firmware repo's screenshots/FPVRaceOne_Product.png (full product
shot on a white/transparent background).

Outputs (committed to flasher/assets/):
  - product.png   trimmed full-product image for the GUI sidebar
  - icon.png      square, stripes-only crop (the "FPV RACE ONE" text removed)
  - icon.ico      multi-resolution Windows icon built from icon.png

Re-run after updating the source render:
  python tools/make_assets.py [path/to/FPVRaceOne_Product.png]
"""

import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "flasher" / "assets"
DEFAULT_SRC = REPO.parent / "FPV_Lap_Timer" / "screenshots" / "FPVRaceOne_Product.png"


def is_yellow(r, g, b, a):
    return a > 128 and r > 150 and g > 120 and b < 110


def is_opaque(a):
    return a > 16


def yellow_row_bands(px, w, h, step=2, min_count=3):
    """Return [(y0, y1, xmin, xmax), ...] contiguous vertical bands of yellow."""
    bands = []
    start = None
    sxmn = w
    sxmx = 0
    for y in range(h):
        cnt = xmn = 0
        xmn = w
        xmx = 0
        for x in range(0, w, step):
            r, g, b, a = px[x, y]
            if is_yellow(r, g, b, a):
                cnt += 1
                xmn = min(xmn, x)
                xmx = max(xmx, x)
        on = cnt > min_count
        if on and start is None:
            start = y
            sxmn, sxmx = xmn, xmx
        elif on:
            sxmn, sxmx = min(sxmn, xmn), max(sxmx, xmx)
        elif (not on) and start is not None:
            bands.append((start, y - 1, sxmn, sxmx))
            start = None
    if start is not None:
        bands.append((start, h - 1, sxmn, sxmx))
    return bands


def opaque_bbox(im):
    """Bounding box of non-transparent (and non-white) content."""
    bg = Image.new("RGBA", im.size, (255, 255, 255, 0))
    diff = Image.alpha_composite(bg, im)
    return diff.getbbox()


def make_product(src_im):
    """Trim transparent margins; leave the full product intact."""
    im = src_im.copy()
    box = im.getbbox()  # trims fully-transparent border
    if box:
        im = im.crop(box)
    # Cap height so the GUI doesn't load a 1500px image.
    max_h = 420
    if im.height > max_h:
        w = round(im.width * max_h / im.height)
        im = im.resize((w, max_h), Image.LANCZOS)
    im.save(ASSETS / "product.png")
    print(f"product.png  {im.size}")


def make_icon(src_im):
    """Crop the stripes block (topmost yellow band group) into a square icon,
    excluding the 'FPV RACE ONE' text lower on the panel."""
    px = src_im.load()
    w, h = src_im.size
    bands = yellow_row_bands(px, w, h)
    if not bands:
        raise SystemExit("No yellow stripes detected — check the source image.")

    # The diagonal stripes overlap in row-space and merge into one tall band;
    # the "FPV" / "RACE" / "ONE" text lines below are separate, much shorter
    # bands.  The stripes block is therefore simply the tallest band.
    stripes = max(bands, key=lambda b: b[1] - b[0])
    y0, y1, x0, x1 = stripes

    # Clamp vertical padding so it never bleeds into a neighbouring yellow band
    # (the text). Leave a 6px margin shy of any adjacent band edge.
    above = max((b[1] for b in bands if b[1] < y0), default=0)
    below = min((b[0] for b in bands if b[0] > y1), default=h)
    pad_x = int((x1 - x0) * 0.12)
    pad_y = int((y1 - y0) * 0.12)
    x0, x1 = max(0, x0 - pad_x), min(w, x1 + pad_x)
    y0 = max(0, above + 6, y0 - pad_y)
    y1 = min(h, below - 6, y1 + pad_y)

    crop = src_im.crop((x0, y0, x1, y1))

    # Centre on a square canvas filled with the panel's blue so the icon reads
    # well at small sizes.  Sample the blue from a corner of the crop.
    blue = crop.getpixel((2, 2))
    if blue[3] < 200 or blue[2] < 100:  # corner wasn't solid blue — use brand blue
        blue = (20, 60, 200, 255)
    side = max(crop.size)
    canvas = Image.new("RGBA", (side, side), blue)
    canvas.paste(crop, ((side - crop.width) // 2, (side - crop.height) // 2), crop)

    canvas.save(ASSETS / "icon.png")
    canvas.save(
        ASSETS / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"icon.png/.ico  crop=({x0},{y0},{x1},{y1}) square={side}")


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
    if not src.is_file():
        raise SystemExit(f"Source image not found: {src}")
    ASSETS.mkdir(parents=True, exist_ok=True)
    im = Image.open(src).convert("RGBA")
    make_product(im)
    make_icon(im)
    print(f"Wrote assets to {ASSETS}")


if __name__ == "__main__":
    main()
