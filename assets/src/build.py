#!/usr/bin/env python3
"""Generate the bento tiles of the profile README.

Run it from anywhere:  python assets/src/build.py

Needs Python 3.9+, Pillow and an internet connection: fonts come from Google Fonts
and icons from skillicons.dev. Everything is embedded in the output, so each SVG in
assets/ is self-contained and GitHub renders it without any external request.

Layout: every row of the README is 1200 units wide. Tiles keep a transparent margin
of GAP / 2 on each side (and PAD_Y above and below), so tiles placed side by side in
separate images line up with tiles drawn together in one image.

To change a text, edit it here and run the script again. Fonts are subset to the
characters actually used, so text edited by hand in an SVG file can show some
letters in a fallback font.
"""

import base64
import io
import math
import re
import tempfile
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape

from PIL import Image, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
SHOTS = HERE / "screenshots"
CACHE = Path(tempfile.gettempdir()) / "cjr23-profile-build"

# Teranga palette, taken from Teranga Académie and Teranga Consulting.
NAVY, NAVY2, INK = "#0B1B3A", "#132A55", "#0A1530"
YELLOW, SKY, CREAM, CORAL = "#FFC83D", "#5CBDF9", "#FFF4DE", "#E8613C"
GREEN, WHITE, LINKEDIN = "#2BB673", "#FFFFFF", "#0A66C2"
MIST, SLATE = "#C7D3EA", "#4A5672"
LINE_DARK, LINE_LIGHT = "#2A4174", "#EADBBD"

FAMILIES = {"d": "Bricolage Grotesque", "m": "JetBrains Mono"}
FALLBACKS = {
    "d": "'Segoe UI',-apple-system,Helvetica,Arial,sans-serif",
    "m": "ui-monospace,'Cascadia Code','SF Mono',Menlo,Consolas,monospace",
}
MODERN_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

W, GAP, PAD_Y, R = 1200, 24, 10, 28
X0, X1 = GAP // 2, W - GAP // 2

# Entrance animation that leaves content visible when animations don't run.
MOTION = """
.in{animation:up .8s cubic-bezier(.2,.7,.2,1) backwards}
@keyframes up{from{opacity:0;transform:translateY(14px)}}
.pulse{animation:pulse 2s ease-in-out infinite}
@keyframes pulse{50%{opacity:.35}}
.twinkle{animation:twinkle 3s ease-in-out infinite}
@keyframes twinkle{50%{opacity:.15}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
"""


def fetch(url, ua=None):
    headers = {"User-Agent": ua} if ua else {}
    with urlopen(Request(url, headers=headers), timeout=30) as resp:
        return resp.read()


def font_css_url(font, weight, text=None):
    url = f"https://fonts.googleapis.com/css2?family={quote(FAMILIES[font])}:wght@{weight}"
    return url + ("&text=" + quote(text, safe="") if text else "")


class Fonts:
    """Measures text with the real fonts and builds subset @font-face rules."""

    def __init__(self):
        CACHE.mkdir(exist_ok=True)
        self._pil = {}

    def _ttf(self, font, weight):
        path = CACHE / f"{font}-{FAMILIES[font].replace(' ', '')}-{weight}.ttf"
        if not path.exists():
            css = fetch(font_css_url(font, weight)).decode()
            path.write_bytes(fetch(re.search(r"url\((.+?)\)", css).group(1)))
        return path

    def width(self, text, font, weight, size, spacing=0):
        key = (font, weight)
        if key not in self._pil:
            self._pil[key] = ImageFont.truetype(str(self._ttf(font, weight)), 100)
        return self._pil[key].getlength(text) * size / 100 + spacing * len(text)

    def fit(self, text, font, weight, size, max_width):
        """Largest size (down from size) at which text fits in max_width."""
        while size > 8 and self.width(text, font, weight, size) > max_width:
            size -= 1
        return size

    def face(self, font, weight, chars):
        try:
            css = fetch(font_css_url(font, weight, "".join(sorted(chars))), MODERN_UA).decode()
            data = base64.b64encode(fetch(re.search(r"url\((.+?)\)", css).group(1))).decode()
        except HTTPError:  # none of these characters exist in the font: fallback font it is
            return ""
        return (f"@font-face{{font-family:'{FAMILIES[font]}';font-weight:{weight};"
                f"src:url(data:font/woff2;base64,{data}) format('woff2')}}")


class Svg:
    def __init__(self, w, h, label):
        self.w, self.h, self.label = w, h, label
        self.body, self.css = [], [MOTION]
        self.chars = defaultdict(set)

    def add(self, *markup):
        self.body.extend(markup)

    def text(self, x, y, spans, *, font="d", weight=400, size=16, fill=INK,
             anchor="start", cls="", attrs=""):
        """spans: a string, or a list of (text, color) / (text, color, weight) tuples."""
        if isinstance(spans, str):
            spans = [(spans, None)]
        inner = []
        for span in spans:
            s, color, w = (span + (None,))[:3]
            self.chars[(font, w or weight)].update(s)
            tspan_attrs = (f' fill="{color}"' if color else "") + (f' font-weight="{w}"' if w else "")
            inner.append(f"<tspan{tspan_attrs}>{escape(s)}</tspan>" if tspan_attrs else escape(s))
        classes = f"{font} {cls}".strip()
        self.add(f'<text x="{x:g}" y="{y:g}" class="{classes}" font-weight="{weight}" '
                 f'font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
                 f'xml:space="preserve" {attrs}>{"".join(inner)}</text>')

    def caption(self, x, y, text, color):
        """Small uppercase mono label used at the top of tiles."""
        self.text(x, y, text, font="m", weight=700, size=14, fill=color, attrs='letter-spacing="2.5"')

    def render(self, fonts):
        faces = "".join(fonts.face(f, w, c) for (f, w), c in sorted(self.chars.items()))
        families = "".join(f".{k}{{font-family:'{v}',{FALLBACKS[k]}}}" for k, v in FAMILIES.items())
        label = escape(self.label, {'"': "&quot;"})
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{label}">'
                f"<title>{escape(self.label)}</title>"
                f"<style>{faces}{families}{''.join(self.css)}</style>{''.join(self.body)}</svg>")


def wrap(fonts, text, font, weight, size, max_width):
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if line and fonts.width(candidate, font, weight, size) > max_width:
            lines.append(line)
            line = word
        else:
            line = candidate
    return lines + [line]


def jpeg_data(im, width, quality=80):
    im = im.convert("RGB")
    im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def screenshot(name, width):
    return jpeg_data(Image.open(SHOTS / f"{name}.jpg"), width)


def tile(s, x, y, w, h, fill, rid, stroke=None):
    """Rounded tile; returns the id of a clip path matching it."""
    border = f' stroke="{stroke}" stroke-width="1.5"' if stroke else ""
    s.add(f'<defs><clipPath id="{rid}"><rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{R}"/>'
          f'</clipPath></defs><rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{R}" fill="{fill}"{border}/>')
    return rid


def chip(s, fonts, x, y, label, *, fg, bg, border=None, h=38, size=15, dot=None, bg_opacity=1):
    """Pill with an optional colored dot; returns its width."""
    pad, dot_w = 15, (16 if dot else 0)
    w = pad * 2 + dot_w + fonts.width(label, "m", 500, size)
    stroke = f' stroke="{border}"' if border else ""
    s.add(f'<rect x="{x:g}" y="{y:g}" width="{w:.1f}" height="{h}" rx="{h / 2}" fill="{bg}" '
          f'fill-opacity="{bg_opacity}"{stroke}/>')
    if dot:
        s.add(f'<circle cx="{x + pad + 4:g}" cy="{y + h / 2:g}" r="4.5" fill="{dot}"/>')
    s.text(x + pad + dot_w, y + h / 2 + size * 0.36, label, font="m", weight=500, size=size, fill=fg)
    return w


def arrow(s, x, y, size, color, width=2.6):
    """North-east arrow drawn as a path, so it never depends on a font glyph; (x, y) is its bottom-left."""
    s.add(f'<path d="M{x:g} {y:g}L{x + size:g} {y - size:g}M{x + size * 0.3:g} {y - size:g}H{x + size:g}'
          f'V{y - size * 0.7:g}" fill="none" stroke="{color}" stroke-width="{width}" '
          f'stroke-linecap="round" stroke-linejoin="round"/>')


def chips_row(s, fonts, x, y, labels, max_x, **style):
    """Lays out chips left to right, dropping the ones that would pass max_x."""
    for label in labels:
        if x + fonts.width(label, "m", 500, style.get("size", 15)) + 30 > max_x:
            break
        x += chip(s, fonts, x, y, label, **style) + 10
    return x


def diamond_pattern(s, pid, color, opacity):
    """Wax-print inspired motif: diamonds with a dot, tiled."""
    s.add(f'<defs><pattern id="{pid}" width="56" height="56" patternUnits="userSpaceOnUse">'
          f'<path d="M28 6L50 28 28 50 6 28z" fill="none" stroke="{color}" stroke-opacity="{opacity}" stroke-width="2.5"/>'
          f'<circle cx="28" cy="28" r="5" fill="{color}" fill-opacity="{opacity}"/>'
          f'<circle cx="0" cy="0" r="3" fill="{color}" fill-opacity="{opacity}"/>'
          f'<circle cx="56" cy="0" r="3" fill="{color}" fill-opacity="{opacity}"/>'
          f'<circle cx="0" cy="56" r="3" fill="{color}" fill-opacity="{opacity}"/>'
          f'<circle cx="56" cy="56" r="3" fill="{color}" fill-opacity="{opacity}"/></pattern></defs>')


def fade_mask(s, mid, x, y, w, h, cx, cy, r=0.75):
    s.add(f'<defs><radialGradient id="{mid}g" cx="{cx}" cy="{cy}" r="{r}">'
          f'<stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
          f'<mask id="{mid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" fill="url(#{mid}g)"/></mask></defs>')


def dot_field(s, x0, y0, cols, rows, step, color, accent):
    """Dotted wave like the one on Teranga Académie, with a few twinkling accent dots."""
    for row in range(rows):
        for col in range(cols):
            cx = x0 + col * step
            cy = y0 + row * step + math.sin(col * 0.45 + row * 0.6) * 5
            r = 1.4 + 1.2 * (row / max(rows - 1, 1))
            if (col * 7 + row * 3) % 11 == 0:
                delay = ((col + row) % 6) * 0.5
                s.add(f'<circle class="twinkle" style="animation-delay:{delay}s" cx="{cx:.1f}" cy="{cy:.1f}" '
                      f'r="{r + 0.8:.1f}" fill="{accent}"/>')
            else:
                s.add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{color}" fill-opacity=".35"/>')


# ---------------------------------------------------------------------------
# Row 1: hero
# ---------------------------------------------------------------------------

def row_hero(fonts):
    h = 500
    s = Svg(W, h + 2 * PAD_Y, "Christian Gilbert Fodé Diouf: network administrator and full-stack "
                              "developer, founder of Teranga Académie and trainer, based in Dakar, "
                              "Senegal, open to work. Motto: I build the network, then the apps that run on it.")
    y = PAD_Y
    left_w = 752
    clip = tile(s, X0, y, left_w, h, NAVY, "a")
    s.add(f'<g clip-path="url(#{clip})">')
    fade_mask(s, "dm", X0 + 300, y, 460, 200, 0.85, 0.15, 0.8)
    s.add('<g mask="url(#dm)">')
    dot_field(s, X0 + 330, y + 30, 16, 6, 26, MIST, YELLOW)
    s.add("</g></g>")

    x = X0 + 56
    s.caption(x, y + 84, "HELLO, I'M", YELLOW)
    size = min(fonts.fit("Christian Gilbert", "d", 800, 78, 640), fonts.fit("Fodé Diouf", "d", 800, 78, 640))
    y1 = y + 84 + round(size * 1.15)
    y2 = y1 + round(size * 1.02)
    s.text(x, y1, "Christian Gilbert", weight=800, size=size, fill=WHITE, cls="in",
           attrs='style="animation-delay:.1s" letter-spacing="-1"')
    s.text(x, y2, "Fodé Diouf", weight=800, size=size, fill=YELLOW, cls="in",
           attrs='style="animation-delay:.2s" letter-spacing="-1"')
    role_y = y2 + 62
    for i, line in enumerate(("Network administrator & full-stack developer",
                              "Founder of Teranga Académie · Trainer")):
        s.text(x, role_y + i * 36, line, weight=500, size=25, fill=MIST, cls="in",
               attrs=f'style="animation-delay:{0.3 + i * 0.08:.2f}s"')

    cx = x
    chip_y = y + h - 52 - 38
    s.add('<g class="in" style="animation-delay:.5s">')
    s.add(f'<circle class="pulse" cx="{cx + 19}" cy="{chip_y + 19}" r="9" fill="{GREEN}" fill-opacity=".35"/>')
    cx += chip(s, fonts, cx, chip_y, "Open to work", fg=WHITE, bg=NAVY2, border=LINE_DARK, dot=GREEN) + 10
    cx += chip(s, fonts, cx, chip_y, "Dakar, Senegal", fg=WHITE, bg=NAVY2, border=LINE_DARK, dot=YELLOW) + 10
    chip(s, fonts, cx, chip_y, "FR · EN", fg=WHITE, bg=NAVY2, border=LINE_DARK, dot=SKY)
    s.add("</g>")

    rx = X0 + left_w + GAP
    rw = X1 - rx
    clip = tile(s, rx, y, rw, h, YELLOW, "b")
    diamond_pattern(s, "wax", INK, 0.14)
    fade_mask(s, "wm", rx, y, rw, h, 1.0, 1.0, 0.75)
    s.add(f'<g clip-path="url(#{clip})"><rect x="{rx}" y="{y}" width="{rw}" height="{h}" fill="url(#wax)" '
          f'mask="url(#wm)"/></g>')
    ax, ay, ar = rx + 44 + 58, y + 44 + 58, 58
    avatar = jpeg_data(Image.open(HERE / "avatar.png"), 240, 88)
    s.add(f'<defs><clipPath id="av"><circle cx="{ax}" cy="{ay}" r="{ar}"/></clipPath></defs>'
          f'<circle cx="{ax}" cy="{ay}" r="{ar + 5}" fill="{WHITE}"/>'
          f'<image x="{ax - ar}" y="{ay - ar}" width="{ar * 2}" height="{ar * 2}" href="{avatar}" clip-path="url(#av)"/>')
    qx = rx + 44
    s.text(qx - 4, y + 254, "“", weight=800, size=120, fill=CORAL)
    quote = "I build the network, then the apps that run on it."
    for q_size in range(36, 27, -1):  # largest size that leaves no single word on the last line
        quote_lines = wrap(fonts, quote, "d", 800, q_size, rw - 88)
        if len(quote_lines[-1].split()) > 1:
            break
    for i, line in enumerate(quote_lines):
        s.text(qx, y + 262 + i * round(q_size * 1.24), line, weight=800, size=q_size, fill=INK, cls="in",
               attrs=f'style="animation-delay:{0.3 + i * 0.08:.2f}s" letter-spacing="-.5"')
    s.text(qx, y + h - 40, "— how I work", font="m", weight=500, size=15, fill=INK, attrs='fill-opacity=".7"')
    return s


# ---------------------------------------------------------------------------
# Row 2: key figures
# ---------------------------------------------------------------------------

STATS = [
    ("43", "courses in French", "TERANGA ACADÉMIE", CREAM, INK, CORAL),
    ("795", "video lessons & quizzes", "TERANGA ACADÉMIE", SKY, INK, INK),
    ("20+", "clients supported", "FREELANCE", NAVY, WHITE, YELLOW),
    ("4+", "years of experience", "NETWORK & WEB", CORAL, WHITE, CREAM),
]


def row_stats(fonts):
    h = 200
    s = Svg(W, h + 2 * PAD_Y, "Key figures. " + ". ".join(f"{n} {label}" for n, label, *_ in STATS))
    tw = (X1 - X0 - GAP * (len(STATS) - 1)) / len(STATS)
    for i, (number, label, caption, bg, fg, accent) in enumerate(STATS):
        x = X0 + i * (tw + GAP)
        tile(s, x, PAD_Y, tw, h, bg, f"s{i}")
        s.caption(x + 28, PAD_Y + 48, caption, accent)
        s.text(x + 26, PAD_Y + 136, number, weight=800, size=84, fill=fg, cls="in",
               attrs=f'style="animation-delay:{i * 0.08:.2f}s" letter-spacing="-2"')
        s.text(x + 28, PAD_Y + 174, label, weight=500, size=fonts.fit(label, "d", 500, 19, tw - 56), fill=fg)
    return s


# ---------------------------------------------------------------------------
# Row 3: about and right now
# ---------------------------------------------------------------------------

ABOUT = ("I configure switches, firewalls, VPNs and Linux servers, then I build the web apps "
         "that run on top of them. I founded Teranga Académie, an online school in French for "
         "francophone Africa, and I train people in digital skills.")
NOW = [
    "Building Teranga AI, an AI-agent platform",
    "Exploring AI agents and LLM integration",
    "3rd year at UNCHK, UCAO graduate",
    "Working in French and English",
]


def row_about(fonts):
    h = 340
    s = Svg(W, h + 2 * PAD_Y, f"About me: {ABOUT} Right now: " + ". ".join(NOW) + ".")
    tw = (X1 - X0 - GAP) / 2
    tile(s, X0, PAD_Y, tw, h, CREAM, "c")
    s.caption(X0 + 44, PAD_Y + 60, "ABOUT ME", CORAL)
    for i, line in enumerate(wrap(fonts, ABOUT, "d", 500, 23, tw - 88)):
        s.text(X0 + 44, PAD_Y + 112 + i * 36, line, weight=500, size=23, fill=INK)

    x = X0 + tw + GAP
    tile(s, x, PAD_Y, tw, h, NAVY, "n")
    s.caption(x + 44, PAD_Y + 60, "RIGHT NOW", YELLOW)
    for i, item in enumerate(NOW):
        iy = PAD_Y + 116 + i * 54
        s.add(f'<path d="M{x + 52} {iy - 15}l8 8-8 8-8-8z" fill="{YELLOW}"/>')
        s.text(x + 76, iy, item, weight=500, size=fonts.fit(item, "d", 500, 22, tw - 120), fill=WHITE,
               cls="in", attrs=f'style="animation-delay:{i * 0.08:.2f}s"')
    return s


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def project_featured(fonts):
    h = 470
    tagline = ("French-language online school born in Senegal: web development, office software, "
               "entrepreneurship and languages, with a 24/7 AI tutor and verifiable certificates.")
    s = Svg(W, h + 2 * PAD_Y, f"Featured project, Teranga Académie: {tagline} 43 courses, 795 lessons, "
                              f"works offline. terangaacademie.com")
    y = PAD_Y
    clip = tile(s, X0, y, X1 - X0, h, NAVY, "f")
    sx, sy, sw = 596, y + 64, 680
    sh = sw * 840 / 1440
    s.add(f'<defs><clipPath id="fs"><rect x="{sx}" y="{sy}" width="{sw}" height="{sh:g}" rx="18"/></clipPath>'
          f'<radialGradient id="fg" cx=".8" cy=".6" r=".6"><stop offset="0" stop-color="{SKY}" stop-opacity=".28"/>'
          f'<stop offset="1" stop-color="{SKY}" stop-opacity="0"/></radialGradient></defs>'
          f'<g clip-path="url(#{clip})"><rect x="{X0}" y="{y}" width="{X1 - X0}" height="{h}" fill="url(#fg)"/>'
          f'<g clip-path="url(#fs)"><image x="{sx}" y="{sy}" width="{sw}" height="{sh:g}" '
          f'href="{screenshot("academie", 1360)}"/></g>'
          f'<rect x="{sx}" y="{sy}" width="{sw}" height="{sh:g}" rx="18" fill="none" stroke="{LINE_DARK}" stroke-width="2"/></g>')
    x = X0 + 48
    chip(s, fonts, x, y + 48, "FEATURED · FOUNDER", fg=INK, bg=YELLOW, size=14, h=34)
    s.text(x, y + 156, "Teranga Académie", weight=800, size=fonts.fit("Teranga Académie", "d", 800, 58, 500),
           fill=WHITE, cls="in", attrs='style="animation-delay:.1s" letter-spacing="-1"')
    for i, line in enumerate(wrap(fonts, tagline, "d", 400, 21, 480)):
        s.text(x, y + 202 + i * 32, line, size=21, fill=MIST, cls="in", attrs='style="animation-delay:.2s"')
    chips_row(s, fonts, x, y + 340, ["43 courses", "795 lessons", "AI tutor", "Works offline"], 560,
              fg=WHITE, bg=NAVY2, border=LINE_DARK, size=14, h=36)
    s.text(x, y + 424, "terangaacademie.com", weight=700, size=20, fill=YELLOW)
    arrow(s, x + fonts.width("terangaacademie.com", "d", 700, 20) + 10, y + 422, 12, YELLOW)
    return s


def project_card(fonts, name, title_text, tagline, tags, label, bg, *, cta="Visit"):
    """Half-width project tile: screenshot on top, text below."""
    h = 620
    tw = W / 2 - GAP
    s = Svg(W // 2, h + 2 * PAD_Y, f"{title_text}: {tagline}")
    dark = bg == NAVY
    fg, soft = (WHITE, MIST) if dark else (INK, SLATE)
    accent = {SKY: INK, CREAM: CORAL}.get(bg, YELLOW)
    y = PAD_Y
    tile(s, X0, y, tw, h, bg, "t")
    sx, sy, sw = X0 + 20, y + 20, tw - 40
    sh = sw * 840 / 1440
    s.add(f'<defs><clipPath id="ts"><rect x="{sx}" y="{sy}" width="{sw}" height="{sh:g}" rx="18"/></clipPath></defs>'
          f'<g clip-path="url(#ts)"><image x="{sx}" y="{sy}" width="{sw}" height="{sh:g}" '
          f'href="{screenshot(name, 1080)}"/></g>'
          f'<rect x="{sx}" y="{sy}" width="{sw}" height="{sh:g}" rx="18" fill="none" stroke="{INK}" '
          f'stroke-opacity=".12" stroke-width="2"/>')
    ty = sy + sh + 50
    s.caption(X0 + 32, ty, label, accent)
    s.text(X0 + 30, ty + 48, title_text, weight=800, size=fonts.fit(title_text, "d", 800, 36, tw - 64),
           fill=fg, attrs='letter-spacing="-.5"')
    for i, line in enumerate(wrap(fonts, tagline, "d", 400, 19, tw - 64)[:3]):
        s.text(X0 + 32, ty + 86 + i * 28, line, size=19, fill=soft)
    by = y + h - 60
    chips_row(s, fonts, X0 + 32, by, tags, X0 + tw - 110, fg=fg, bg=WHITE, bg_opacity=0.55, size=14, h=34)
    arrow(s, X0 + tw - 32 - 12, by + 23, 12, fg)
    s.text(X0 + tw - 32 - 22, by + 24, cta, weight=700, size=19, fill=fg, anchor="end")
    return s


def project_progress(fonts):
    h = 180
    tagline = "A customizable AI-agent platform for professionals, businesses and individuals."
    s = Svg(W, h + 2 * PAD_Y, f"Teranga AI, in progress: {tagline}")
    y = PAD_Y
    tile(s, X0, y, X1 - X0, h, CORAL, "p")
    s.add(f'<circle class="pulse" cx="{X0 + 52}" cy="{y + 50}" r="6" fill="{WHITE}"/>')
    s.caption(X0 + 68, y + 55, "IN PROGRESS", CREAM)
    s.text(X0 + 44, y + 106, "Teranga AI", weight=800, size=40, fill=WHITE, attrs='letter-spacing="-.5"')
    s.text(X0 + 44, y + 144, tagline, size=fonts.fit(tagline, "d", 400, 20, 640), fill=CREAM)
    x, w, bar_y = 790, 350, y + 96
    s.text(x, bar_y - 22, [("$ ", CREAM), ("teranga-ai ", WHITE), ("--build", CREAM)], font="m", weight=500, size=16)
    s.add(f'<defs><clipPath id="pb"><rect x="{x}" y="{bar_y}" width="{w}" height="12" rx="6"/></clipPath>'
          f'<linearGradient id="pg" x1="0" x2="1"><stop offset="0" stop-color="{WHITE}" stop-opacity="0"/>'
          f'<stop offset=".5" stop-color="{WHITE}"/><stop offset="1" stop-color="{WHITE}" stop-opacity="0"/>'
          f'</linearGradient></defs>'
          f'<rect x="{x}" y="{bar_y}" width="{w}" height="12" rx="6" fill="{WHITE}" fill-opacity=".22"/>'
          f'<g clip-path="url(#pb)"><rect x="{x - 150}" y="{bar_y}" width="150" height="12" fill="url(#pg)">'
          f'<animate attributeName="x" values="{x - 150};{x + w}" dur="2.2s" repeatCount="indefinite"/></rect></g>')
    s.text(x, bar_y + 44, "status: work in progress", font="m", weight=500, size=14, fill=CREAM)
    return s


# ---------------------------------------------------------------------------
# Tech stack
# ---------------------------------------------------------------------------

# (category, skillicons.dev ids, text chips for skills without an icon); two columns.
STACK = [
    [("NETWORK & SECURITY", [], ["Switches", "Firewalls", "VPN", "Linux servers"]),
     ("LANGUAGES", ["js", "ts", "python", "php", "java", "c", "cpp", "bash"], []),
     ("FRONTEND", ["html", "css", "react", "nextjs", "angular", "tailwind", "bootstrap", "sass"], [])],
    [("BACKEND & DATA", ["nodejs", "django", "mysql", "postgres", "supabase", "wordpress"], []),
     ("CLOUD · DEVOPS · IOT", ["vercel", "docker", "linux", "aws", "gcp", "arduino", "raspberrypi", "git"], []),
     ("AI & DESIGN", ["tensorflow", "pytorch", "figma", "ps", "ai", "pr", "ae"], [])],
]
ICON_NAMES = {
    "js": "JavaScript", "ts": "TypeScript", "python": "Python", "php": "PHP", "java": "Java",
    "c": "C", "cpp": "C++", "bash": "Bash", "html": "HTML", "css": "CSS", "react": "React",
    "nextjs": "Next.js", "angular": "Angular", "tailwind": "Tailwind CSS", "bootstrap": "Bootstrap",
    "sass": "Sass", "nodejs": "Node.js", "django": "Django", "mysql": "MySQL", "postgres": "PostgreSQL",
    "supabase": "Supabase", "wordpress": "WordPress", "vercel": "Vercel", "docker": "Docker",
    "linux": "Linux", "aws": "AWS", "gcp": "Google Cloud", "arduino": "Arduino",
    "raspberrypi": "Raspberry Pi", "git": "Git", "tensorflow": "TensorFlow", "pytorch": "PyTorch",
    "figma": "Figma", "ps": "Photoshop", "ai": "Illustrator", "pr": "Premiere Pro", "ae": "After Effects",
}


def icon(name):
    path = CACHE / f"icon-{name}.svg"
    if not path.exists():
        path.write_bytes(fetch(f"https://skillicons.dev/icons?i={name}", MODERN_UA))
    return "data:image/svg+xml;base64," + base64.b64encode(path.read_bytes()).decode()


def row_stack(fonts):
    h, size, gap, block_h = 470, 48, 12, 112
    groups = [g for column in STACK for g in column]
    label = "Tech stack. " + ". ".join(
        f"{cat.title()}: {', '.join([ICON_NAMES[i] for i in icons] + chips)}" for cat, icons, chips in groups)
    s = Svg(W, h + 2 * PAD_Y, label)
    y = PAD_Y
    tile(s, X0, y, X1 - X0, h, NAVY, "k")
    s.caption(X0 + 48, y + 58, "TECH STACK", YELLOW)
    s.text(X1 - 48, y + 58, "tools I work with", font="m", weight=500, size=14, fill=MIST, anchor="end")
    s.add(f'<line x1="{X0 + 48}" y1="{y + 84}" x2="{X1 - 48}" y2="{y + 84}" stroke="{LINE_DARK}"/>')
    n = 0
    for c, column in enumerate(STACK):
        cx = X0 + 48 + c * 580
        for b, (category, icons, chips) in enumerate(column):
            by = y + 128 + b * block_h
            s.text(cx, by, category, font="m", weight=700, size=13, fill=SKY, attrs='letter-spacing="2"')
            x = cx
            for name in icons:
                s.add(f'<image class="in" style="animation-delay:{n * 0.025:.2f}s" x="{x}" y="{by + 16}" '
                      f'width="{size}" height="{size}" href="{icon(name)}"/>')
                x += size + gap
                n += 1
            if chips:
                chips_row(s, fonts, x, by + 20, chips, cx + 560, fg=WHITE, bg=NAVY2, border=LINE_DARK,
                          dot=YELLOW, size=15, h=40)
    return s


# ---------------------------------------------------------------------------
# Call to action and contact tiles
# ---------------------------------------------------------------------------

def row_cta(fonts):
    h = 150
    s = Svg(W, h + 2 * PAD_Y, "Let's build something together. Open to full-time roles and freelance missions.")
    y = PAD_Y
    clip = tile(s, X0, y, X1 - X0, h, CREAM, "z")
    diamond_pattern(s, "zp", CORAL, 0.18)
    fade_mask(s, "zm", X0, y, X1 - X0, h, 1.0, 0.5, 0.4)
    s.add(f'<g clip-path="url(#{clip})"><rect x="{X0}" y="{y}" width="{X1 - X0}" height="{h}" fill="url(#zp)" '
          f'mask="url(#zm)"/></g>')
    title_text = "Let's build something together."
    s.text(X0 + 48, y + 92, title_text, weight=800, size=fonts.fit(title_text, "d", 800, 46, 680),
           fill=INK, attrs='letter-spacing="-1"')
    x = 790
    s.add(f'<circle class="pulse" cx="{x + 6}" cy="{y + 64}" r="11" fill="{GREEN}" fill-opacity=".3"/>'
          f'<circle cx="{x + 6}" cy="{y + 64}" r="6" fill="{GREEN}"/>')
    s.text(x + 26, y + 70, "Open to full-time roles", weight=600, size=20, fill=INK)
    s.text(x + 26, y + 98, "and freelance missions", size=20, fill=SLATE)
    return s


CONTACTS = {
    "portfolio": ("Portfolio", "my work and services", YELLOW, INK),
    "academie": ("Teranga Académie", "terangaacademie.com", NAVY, WHITE),
    "linkedin": ("LinkedIn", "let's connect", LINKEDIN, WHITE),
    "email": ("Email", "christiandiouf23@gmail.com", CORAL, WHITE),
}


def contact(fonts, kind):
    h = 170
    title_text, sub, bg, fg = CONTACTS[kind]
    tw = W / 4 - GAP
    s = Svg(W // 4, h + 2 * PAD_Y, f"{title_text}: {sub}")
    y = PAD_Y
    tile(s, X0, y, tw, h, bg, "q")
    ix, iy = X0 + 26, y + 26
    if kind == "portfolio":
        s.add(f'<rect x="{ix}" y="{iy}" width="52" height="52" rx="14" fill="{INK}"/>')
        s.text(ix + 26, iy + 33, ">_", font="m", weight=700, size=20, fill=YELLOW, anchor="middle")
    elif kind == "academie":
        s.add(f'<rect x="{ix}" y="{iy}" width="52" height="52" rx="14" fill="{YELLOW}"/>'
              f'<path d="M{ix + 26} {iy + 13}l18 9-18 9-18-9z" fill="{INK}"/>'
              f'<path d="M{ix + 16} {iy + 27}v8c0 2.5 4.5 5 10 5s10-2.5 10-5v-8" fill="none" stroke="{INK}" stroke-width="3"/>'
              f'<path d="M{ix + 44} {iy + 22}v10" stroke="{INK}" stroke-width="2.5" stroke-linecap="round"/>')
    elif kind == "linkedin":
        s.add(f'<rect x="{ix}" y="{iy}" width="52" height="52" rx="14" fill="{WHITE}"/>'
              f'<rect x="{ix + 13}" y="{iy + 21}" width="7" height="19" fill="{LINKEDIN}"/>'
              f'<circle cx="{ix + 16.5}" cy="{iy + 14}" r="4.3" fill="{LINKEDIN}"/>'
              f'<path d="M{ix + 24} {iy + 21}h6.8v2.8c1-1.8 3.1-3.3 6.3-3.3 5.3 0 6.4 3.3 6.4 7.8V{iy + 40}h-7.2v-10c0-2.3-.4-4-2.6-4-2.4 0-2.8 1.8-2.8 4v10H{ix + 24}z" fill="{LINKEDIN}"/>')
    else:
        s.add(f'<rect x="{ix}" y="{iy}" width="52" height="52" rx="14" fill="{WHITE}"/>'
              f'<rect x="{ix + 11}" y="{iy + 15}" width="30" height="22" rx="3.5" fill="none" stroke="{CORAL}" stroke-width="3"/>'
              f'<path d="M{ix + 13} {iy + 18}l13 9.5 13-9.5" fill="none" stroke="{CORAL}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>')
    arrow(s, X0 + tw - 26 - 18, y + 26 + 18 + 8, 18, fg, width=3)
    s.text(X0 + 26, y + 126, title_text, weight=800, size=fonts.fit(title_text, "d", 800, 27, tw - 52),
           fill=fg, attrs='letter-spacing="-.5"')
    s.text(X0 + 26, y + 150, sub, font="m", weight=500, size=fonts.fit(sub, "m", 500, 13, tw - 52),
           fill=fg, attrs='fill-opacity=".8"')
    return s


def main():
    fonts = Fonts()
    outputs = {
        "hero.svg": row_hero(fonts),
        "stats.svg": row_stats(fonts),
        "about.svg": row_about(fonts),
        "project-academie.svg": project_featured(fonts),
        "project-bureautique.svg": project_card(
            fonts, "bureautique", "Cours Bureautique",
            "Office software training: Word, Excel, PowerPoint and collaboration tools, with 142 "
            "video lessons, PDF exercises and quizzes.",
            ["Word", "Excel", "PowerPoint"], "LIVE · E-LEARNING", CREAM),
        "project-schoolpro.svg": project_card(
            fonts, "schoolpro", "SchoolPro",
            "School management app for Senegalese schools: mock exams (CFEE, BFEM, BAC), grades, "
            "report cards and attendance. Works offline.",
            ["HTML", "CSS", "JavaScript"], "WEB APP · OFFLINE", SKY, cta="Code"),
        "project-ceshfpt.svg": project_card(
            fonts, "ceshfpt", "CESHFPT Tambacounda",
            "Website for a solar energy and vocational training center: courses, solar installation "
            "estimator, photo gallery and WhatsApp contact.",
            ["HTML", "CSS", "JavaScript"], "LIVE · WEBSITE", SKY),
        "project-teranga.svg": project_card(
            fonts, "teranga", "Teranga Consulting",
            "Showcase site for an IT, communication and training consultancy serving SMEs and NGOs "
            "in Senegal, with prices in FCFA.",
            ["HTML", "CSS", "JavaScript"], "LIVE · WEBSITE", CREAM),
        "project-teranga-ai.svg": project_progress(fonts),
        "stack.svg": row_stack(fonts),
        "cta.svg": row_cta(fonts),
    }
    for kind in CONTACTS:
        outputs[f"contact-{kind}.svg"] = contact(fonts, kind)
    for filename, svg in outputs.items():
        (OUT / filename).write_text(svg.render(fonts), encoding="utf-8")
        print(f"{filename:28} {(OUT / filename).stat().st_size / 1024:6.1f} KB")
    for old in sorted(set(p.name for p in OUT.glob("*.svg")) - set(outputs)):
        (OUT / old).unlink()
        print(f"removed {old}")


if __name__ == "__main__":
    main()
