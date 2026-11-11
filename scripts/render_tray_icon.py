"""Render app/src-tauri/icons/tray.png: the menu bar template icon, a Mac mini with cat ears.

A flat, wide box (Mac mini front) with two cat ears. Inner ears, the eyes, a USB-C-shaped mouth
and the power light are holes, so macOS can tint the single solid shape for light and dark menu
bars. Geometry is on a 176-unit grid. Usage:
    uv run --no-project --with pillow python scripts/render_tray_icon.py app/src-tauri/icons/tray.png [preview.png]
"""
import sys
from PIL import Image, ImageDraw

K = 4                       # draw at 4x of the 176-unit design grid, i.e. 704 px
def P(points): return [(x * K, y * K) for x, y in points]

def shape(d, pts, fill, round_w):
    d.polygon(P(pts), fill=fill)
    d.line(P(pts + pts[:1]), fill=fill, width=round_w * K, joint='curve')   # rounded corners
    for x, y in P(pts):
        r = round_w * K / 2
        d.ellipse((x - r, y - r, x + r, y + r), fill=fill)

def icon():
    im = Image.new('L', (176 * K, 176 * K), 0)
    d = ImageDraw.Draw(im)
    left_outer = [(28, 94), (44, 34), (74, 86)]
    left_inner = [(42, 78), (48, 52), (62, 76)]
    mirror = lambda pts: [(176 - x, y) for x, y in pts]
    shape(d, left_outer, 255, 10)
    shape(d, mirror(left_outer), 255, 10)
    d.rounded_rectangle(P([(10, 80), (166, 132)]), 14 * K, fill=255)          # Mac mini front, about 3:1
    shape(d, left_inner, 0, 5)                                                 # inner ears
    shape(d, mirror(left_inner), 0, 5)
    for cx in (62, 114):                                                       # eyes
        d.ellipse(P([(cx - 9, 92), (cx + 9, 110)]), fill=0)
    d.rounded_rectangle(P([(79, 112), (97, 118)]), 3 * K, fill=0)            # mouth, a USB-C port (3:1)
    d.ellipse(P([(146, 118), (154, 126)]), fill=0)                            # power light
    return im

big = icon()
alpha = big.resize((44, 44), Image.LANCZOS)
tray = Image.new('RGBA', (44, 44), (0, 0, 0, 0)); tray.putalpha(alpha)
tray.save(sys.argv[1])
if len(sys.argv) < 3:
    sys.exit(0)
prev = Image.new('RGB', (176 + 2 * 88, 176), (30, 30, 30))
prev.paste((240, 240, 240), (176 + 88, 0, 176 + 176, 176))
large = big.resize((176, 176), Image.LANCZOS)
prev.paste((240, 240, 240), (0, 0, 176, 176), None); prev.paste((0, 0, 0), (0, 0, 176, 176), large)
for x, colour in ((176 + 22, (255, 255, 255)), (176 + 88 + 22, (0, 0, 0))):
    prev.paste(colour, (x, 66, x + 44, 110), alpha)
prev.resize((prev.width * 2, prev.height * 2), Image.NEAREST).save(sys.argv[2])
