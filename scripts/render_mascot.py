"""Draw 맥서기 (a silver pixel Mac mini with cat ears) from one grid and write every copy of it.

Outputs, all generated (edit this file, then re-run; never edit the outputs by hand):
  quietclerk/server/static/seogi.svg        idle, blinks every 4 s
  quietclerk/server/static/seogi-work.svg   processing, eyes glance and the power light pulses
  quietclerk/server/static/seogi-worry.svg  error, shut eyes, wavy mouth, red light, sweat drop
  app/src-tauri/icons/app-icon.svg          source for `tauri icon` (static, dark rounded tile)
  app/src-tauri/icons/tray.png              menu bar template image, 44 px, features are holes
  docs/assets/banner-*.svg                  the block between the mascot:start/end comments

Animations are CSS, so `prefers-reduced-motion: reduce` stops them.
Usage: uv run --no-project --with pillow python scripts/render_mascot.py
"""
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
U = 10  # one grid cell in SVG units

# 20 x 13 cells. # body, i inner ear, d bottom edge, L power light.
BODY = [
    "..##............##..",
    ".#ii#..........#ii#.",
    ".#####........#####.",
    ".##################.",
    "####################",
    "####################",
    "####################",
    "####################",
    "####################",
    "################L###",
    "####################",
    "dddddddddddddddddddd",
    ".dddddddddddddddddd.",
]
COLOUR = {'#': '#c3c8cf', 'i': '#9aa1aa', 'd': '#a7adb6', 'E': '#1e1f1c', 'L': '#2fbf6a',
          'R': '#e0362c', 'S': '#7fb8ff', 'off': '#c3c8cf'}
TILE = '#1e2230'  # app icon background

# Feature cells are (x, y, width, colour key).
EYES = lambda dx=0, dy=0: [(4 + dx, 5 + dy, 2, 'E'), (4 + dx, 6 + dy, 2, 'E'),
                            (14 + dx, 5 + dy, 2, 'E'), (14 + dx, 6 + dy, 2, 'E')]
SHUT = [(4, 6, 2, 'E'), (14, 6, 2, 'E')]
MOUTH = [(8, 8, 4, 'E')]
LIGHT = (16, 9)


def runs(rows):
    cells = []
    for y, row in enumerate(rows):
        x = 0
        while x < len(row):
            ch, w = row[x], 1
            while x + w < len(row) and row[x + w] == ch:
                w += 1
            if ch != '.':
                cells.append((x, y, w, ch))
            x += w
    return cells


def rects(cells):
    return ''.join(f'<rect x="{x * U}" y="{y * U}" width="{w * U}" height="{U}" fill="{COLOUR[c]}"/>'
                   for x, y, w, c in cells)


def layer(cls, cells, hidden=False):
    # Hidden layers carry opacity="0" so renderers without CSS (resvg, tauri icon) draw one frame.
    extra = ' opacity="0"' if hidden else ''
    return f'<g class="{cls}"{extra}>{rects(cells)}</g>'


STYLE = '''<style>
.o{animation:o 4s infinite}.c{animation:c 4s infinite}
.a{animation:a 1.6s infinite}.b{animation:b 1.6s infinite}.p{animation:a .8s infinite}
@keyframes o{0%,90%{opacity:1}91%,95%{opacity:0}96%,100%{opacity:1}}
@keyframes c{0%,90%{opacity:0}91%,95%{opacity:1}96%,100%{opacity:0}}
@keyframes a{0%,49%{opacity:1}50%,100%{opacity:0}}
@keyframes b{0%,49%{opacity:0}50%,100%{opacity:1}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
</style>'''


def figure(pose):
    """Inner SVG content of one pose on the 200 x 130 grid (sweat drop sits above the right ear)."""
    body = rects(runs(BODY))
    if pose == 'idle':
        return body + layer('o', EYES()) + layer('c', SHUT, hidden=True) + rects(MOUTH)
    if pose == 'work':
        return (body + layer('a', EYES(-1, -1)) + layer('b', EYES(1, -1), hidden=True)
                + rects([(9, 8, 2, 'E')]) + layer('p', [(*LIGHT, 1, 'off')], hidden=True))
    if pose == 'worry':
        return (body + rects(SHUT) + rects([(8, 9, 1, 'E'), (9, 8, 1, 'E'), (10, 9, 1, 'E'), (11, 8, 1, 'E')])
                + rects([(*LIGHT, 1, 'R')])
                + rects([(20, -3, 1, 'S'), (20, -2, 1, 'S'), (19, -1, 3, 'S'), (19, 0, 3, 'S'), (20, 1, 1, 'S')]))
    raise ValueError(pose)


def web_svg(pose):
    # 240 x 206 keeps the old 200 x 172 aspect the CSS sizes were written for.
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="-20 -38 240 206" shape-rendering="crispEdges" '
            f'role="img" aria-hidden="true">{STYLE}{figure(pose)}</svg>\n')


def app_icon_svg():
    # macOS icon grid: 824 px tile with a 185 px corner radius centred on a 1024 canvas.
    scale = 3.0  # 200 x 130 grid -> 600 x 390
    x, y = (1024 - 200 * scale) / 2, (1024 - 130 * scale) / 2 + 20
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">'
            f'<rect x="100" y="100" width="824" height="824" rx="185" fill="{TILE}"/>'
            f'<g transform="translate({x} {y}) scale({scale})" shape-rendering="crispEdges">{figure("idle")}</g></svg>\n')


def tray_png(path):
    """44 x 44 template image: 2 px per cell, the face, light and inner ears are transparent holes."""
    holes = {(x + i, y) for x, y, w, _ in EYES() + MOUTH + [(*LIGHT, 1, ''), (2, 1, 2, ''), (16, 1, 2, '')]
             for i in range(w)}
    im = Image.new('RGBA', (44, 44), (0, 0, 0, 0))
    ox, oy = 2, 9
    for y, row in enumerate(BODY):
        for x, ch in enumerate(row):
            if ch != '.' and (x, y) not in holes:
                for dx in range(2):
                    for dy in range(2):
                        im.putpixel((ox + 2 * x + dx, oy + 2 * y + dy), (0, 0, 0, 255))
    im.save(path)


def banner(path):
    text = path.read_text(encoding='utf-8')
    block = ('<!-- mascot:start (scripts/render_mascot.py) -->\n'
             f'  <g transform="translate(70 100) scale(1.25)" shape-rendering="crispEdges">{figure("idle")}</g>\n'
             '  <!-- mascot:end -->')
    new, n = re.subn(r'<!-- mascot:start.*?<!-- mascot:end -->', block, text, flags=re.S)
    if n != 1:
        raise SystemExit(f'{path}: expected one mascot:start/end block')
    path.write_text(new, encoding='utf-8')


def main():
    static = ROOT / 'quietclerk/server/static'
    for pose, name in (('idle', 'seogi.svg'), ('work', 'seogi-work.svg'), ('worry', 'seogi-worry.svg')):
        (static / name).write_text(web_svg(pose), encoding='utf-8')
    icons = ROOT / 'app/src-tauri/icons'
    (icons / 'app-icon.svg').write_text(app_icon_svg(), encoding='utf-8')
    tray_png(icons / 'tray.png')
    for lang in ('en', 'ko'):
        banner(ROOT / f'docs/assets/banner-{lang}.svg')


if __name__ == '__main__':
    main()
