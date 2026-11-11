"""Render app/src-tauri/icons/tray.png: the menu bar template icon, a Mac mini with cat ears.

One solid shape; inner ears, eyes and the ω mouth are holes, so macOS can tint it for light and
dark menu bars. Geometry is on a 176-unit grid. Usage:
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
    left_outer = [(30, 88), (46, 28), (76, 80)]
    left_inner = [(44, 72), (50, 46), (64, 70)]
    mirror = lambda pts: [(176 - x, y) for x, y in pts]
    shape(d, left_outer, 255, 10)
    shape(d, mirror(left_outer), 255, 10)
    d.rounded_rectangle(P([(16, 74), (160, 140)]), 20 * K, fill=255)          # Mac mini body
    shape(d, left_inner, 0, 5)                                                 # inner ears
    shape(d, mirror(left_inner), 0, 5)
    for cx in (62, 114):                                                       # eyes
        d.ellipse(P([(cx - 10, 94), (cx + 10, 114)]), fill=0)
    for x0 in (72, 88):                                                        # ω mouth
        d.arc(P([(x0, 104), (x0 + 16, 124)]), 10, 170, fill=0, width=int(4.5 * K))
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
