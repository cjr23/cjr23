#!/usr/bin/env python3
"""Generate the SVG visuals of the profile README.

Run it from anywhere:  python assets/src/build.py

Needs Python 3.9+, Pillow and an internet connection: fonts come from Google Fonts
and icons from skillicons.dev. Everything is embedded in the output, so each SVG in
assets/ is self-contained and GitHub renders it without any external request.

To change a text, edit it here and run the script again. Fonts are subset to the
characters actually used, so text edited by hand in an SVG file can show some
letters in a fallback font.
"""

import base64
import io
import re
import tempfile
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape

from PIL import Image, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
SHOTS = HERE / "screenshots"
CACHE = Path(tempfile.gettempdir()) / "cjr23-profile-build"

BG0, BG1, PANEL, BAR = "#070B14", "#0B1220", "#0F172A", "#0E1729"
LINE, LINE2 = "#1E293B", "#26344D"
TEXT, SOFT, MUTED, DIM = "#E6EDF7", "#CBD5E1", "#94A3B8", "#64748B"
TEAL, CYAN, GREEN, AMBER = "#14B8A6", "#22D3EE", "#34D399", "#FBBF24"
INK = "#0F172A"

FAMILIES = {"d": "Space Grotesk", "m": "JetBrains Mono"}
FALLBACKS = {
    "d": "'Segoe UI',-apple-system,Helvetica,Arial,sans-serif",
    "m": "ui-monospace,'Cascadia Code','SF Mono',Menlo,Consolas,monospace",
}
MODERN_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Shared CSS: entrance animation that leaves content visible when animations don't run.
MOTION = """
.in{animation:up .8s cubic-bezier(.2,.7,.2,1) backwards}
@keyframes up{from{opacity:0;transform:translateY(14px)}}
.blink{animation:blink 1.1s steps(1) infinite}
@keyframes blink{50%{opacity:0}}
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
        path = CACHE / f"{font}-{weight}.ttf"
        if not path.exists():
            css = fetch(font_css_url(font, weight)).decode()
            path.write_bytes(fetch(re.search(r"url\((.+?)\)", css).group(1)))
        return path

    def width(self, text, font, weight, size, spacing=0):
        key = (font, weight)
        if key not in self._pil:
            pil = ImageFont.truetype(str(self._ttf(font, weight)), 100)
            try:
                pil.set_variation_by_axes([weight])
            except (OSError, AttributeError):
                pass
            self._pil[key] = pil
        return self._pil[key].getlength(text) * size / 100 + spacing * len(text)

    def face(self, font, weight, chars):
        css = fetch(font_css_url(font, weight, "".join(sorted(chars))), MODERN_UA).decode()
        data = base64.b64encode(fetch(re.search(r"url\((.+?)\)", css).group(1))).decode()
        return (f"@font-face{{font-family:'{FAMILIES[font]}';font-weight:{weight};"
                f"src:url(data:font/woff2;base64,{data}) format('woff2')}}")


class Svg:
    def __init__(self, w, h, label):
        self.w, self.h, self.label = w, h, label
        self.body, self.css = [], [MOTION]
        self.chars = defaultdict(set)

    def add(self, *markup):
        self.body.extend(markup)

    def text(self, x, y, spans, *, font="d", weight=400, size=16, fill=TEXT,
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


def screenshot(name, width):
    im = Image.open(SHOTS / f"{name}.jpg").convert("RGB")
    im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=78, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def card_background(s, rid, glow=(0.85, 0.15)):
    """Rounded dark panel with a soft teal glow; returns the clip-path id to use."""
    s.add(f'<defs><clipPath id="{rid}c"><rect width="{s.w}" height="{s.h}" rx="24"/></clipPath>'
          f'<linearGradient id="{rid}b" x1="0" y1="0" x2="1" y2="1">'
          f'<stop offset="0" stop-color="{BG0}"/><stop offset="1" stop-color="#0C1729"/></linearGradient>'
          f'<radialGradient id="{rid}g" cx="{glow[0]}" cy="{glow[1]}" r="0.6">'
          f'<stop offset="0" stop-color="{TEAL}" stop-opacity=".22"/>'
          f'<stop offset="1" stop-color="{TEAL}" stop-opacity="0"/></radialGradient></defs>'
          f'<g clip-path="url(#{rid}c)"><rect width="{s.w}" height="{s.h}" fill="url(#{rid}b)"/>'
          f'<rect width="{s.w}" height="{s.h}" fill="url(#{rid}g)"/></g>')
    return f"{rid}c"


def card_border(s):
    s.add(f'<rect x=".75" y=".75" width="{s.w - 1.5}" height="{s.h - 1.5}" rx="23.25" '
          f'fill="none" stroke="{LINE2}" stroke-width="1.5"/>')


def chip(s, fonts, x, y, label, *, color=SOFT, h=32, size=14, dot=None, cls=""):
    """Pill with an optional colored dot; returns its width."""
    pad = 14
    dot_w = 16 if dot else 0
    w = pad * 2 + dot_w + fonts.width(label, "m", 500, size)
    s.add(f'<g class="{cls}"><rect x="{x:g}" y="{y:g}" width="{w:.1f}" height="{h}" rx="{h / 2}" '
          f'fill="{PANEL}" stroke="{LINE2}"/>')
    if dot:
        s.add(f'<circle cx="{x + pad + 4:g}" cy="{y + h / 2:g}" r="4" fill="{dot}"/>')
    s.text(x + pad + dot_w, y + h / 2 + size * 0.36, label, font="m", weight=500, size=size, fill=color)
    s.add("</g>")
    return w


def browser_frame(s, rid, x, y, w, url, image):
    """Browser window around a screenshot (1440x840 sources); returns the frame height."""
    bar = 34
    img_h = w * 840 / 1440
    h = bar + img_h
    s.add(f'<defs><clipPath id="{rid}"><rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="12"/></clipPath>'
          f'<filter id="{rid}s" x="-10%" y="-10%" width="120%" height="130%">'
          f'<feDropShadow dx="0" dy="18" stdDeviation="18" flood-color="#000" flood-opacity=".45"/></filter></defs>'
          f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="12" fill="{BAR}" filter="url(#{rid}s)"/>'
          f'<g clip-path="url(#{rid})"><rect x="{x:g}" y="{y:g}" width="{w:g}" height="{bar}" fill="#111C31"/>'
          f'<image x="{x:g}" y="{y + bar:g}" width="{w:g}" height="{img_h:g}" href="{image}" '
          f'preserveAspectRatio="xMidYMin slice"/></g>')
    for i, color in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
        s.add(f'<circle cx="{x + 18 + i * 18:g}" cy="{y + bar / 2:g}" r="5.5" fill="{color}"/>')
    pill_w = min(w - 150, 300)
    pill_x = x + (w - pill_w) / 2
    s.add(f'<rect x="{pill_x:g}" y="{y + 7:g}" width="{pill_w:g}" height="20" rx="10" fill="{BG0}" '
          f'fill-opacity=".7"/>')
    s.text(x + w / 2, y + 21.5, url, font="m", size=12, fill=MUTED, anchor="middle")
    s.add(f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="12" fill="none" '
          f'stroke="{LINE2}"/>')
    return h


# ---------------------------------------------------------------------------
# Header: name, roles and an animated network topology
# ---------------------------------------------------------------------------

NODES = {
    "gateway": (955, 210), "web": (800, 108), "cloud": (975, 72), "iot": (1098, 104),
    "infra": (1135, 248), "data": (1050, 352), "ai": (842, 334), "edtech": (772, 222),
}
LINKS = [("gateway", n) for n in ("web", "cloud", "iot", "infra", "data", "ai", "edtech")] + [
    ("web", "cloud"), ("cloud", "iot"), ("iot", "infra"), ("infra", "data"),
    ("data", "ai"), ("ai", "edtech"), ("edtech", "web"),
]
# (from, to, duration in s, start offset in s)
PACKETS = [
    ("web", "gateway", 2.6, 0), ("gateway", "infra", 2.2, 0.8), ("data", "gateway", 3.0, 1.6),
    ("gateway", "cloud", 2.4, 0.4), ("edtech", "gateway", 2.8, 2.0), ("gateway", "ai", 2.5, 1.2),
    ("iot", "infra", 3.2, 0.6), ("ai", "edtech", 3.4, 2.4), ("cloud", "iot", 3.0, 1.0),
]
LABEL_OFFSETS = {
    "gateway": (0, 44, "middle"), "web": (-14, -16, "end"), "cloud": (0, -20, "middle"),
    "iot": (14, -14, "start"), "infra": (0, 30, "middle"), "data": (14, 24, "start"),
    "ai": (-14, 24, "end"), "edtech": (-16, 5, "end"),
}


def header(fonts):
    s = Svg(1200, 420, "Christian Gilbert Fodé Diouf: network administrator, full-stack developer "
                       "and trainer, founder of Teranga Académie, based in Dakar, Senegal")
    s.add(f"""<defs>
<clipPath id="c"><rect width="1200" height="420" rx="24"/></clipPath>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BG0}"/><stop offset="1" stop-color="#0C1729"/></linearGradient>
<radialGradient id="g1" cx="0.8" cy="0.5" r="0.42"><stop offset="0" stop-color="{TEAL}" stop-opacity=".32"/><stop offset="1" stop-color="{TEAL}" stop-opacity="0"/></radialGradient>
<radialGradient id="g2" cx="0.05" cy="1.05" r="0.5"><stop offset="0" stop-color="{CYAN}" stop-opacity=".12"/><stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></radialGradient>
<radialGradient id="gm" cx="0.78" cy="0.5" r="0.55"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
<mask id="m"><rect width="1200" height="420" fill="url(#gm)"/></mask>
<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="#fff" stroke-opacity=".07"/></pattern>
<linearGradient id="name" x1="0" x2="1"><stop offset="0" stop-color="{TEAL}"/><stop offset="1" stop-color="{CYAN}"/></linearGradient>
<filter id="glow" x="-300%" y="-300%" width="700%" height="700%"><feGaussianBlur stdDeviation="3"/><feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter>
</defs>
<g clip-path="url(#c)">
<rect width="1200" height="420" fill="url(#bg)"/>
<rect width="1200" height="420" fill="url(#grid)" mask="url(#m)"/>
<rect width="1200" height="420" fill="url(#g1)"/><rect width="1200" height="420" fill="url(#g2)"/>""")

    for a, b in LINKS:
        (x1, y1), (x2, y2) = NODES[a], NODES[b]
        core = "gateway" in (a, b)
        s.add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{TEAL}" '
              f'stroke-opacity="{".45" if core else ".22"}" stroke-width="{1.6 if core else 1.2}"/>')
    for a, b, dur, offset in PACKETS:
        (x1, y1), (x2, y2) = NODES[a], NODES[b]
        timing = f'dur="{dur}s" begin="-{offset}s" repeatCount="indefinite"'
        s.add(f'<circle r="3.5" fill="{CYAN}" filter="url(#glow)">'
              f'<animateMotion path="M{x1},{y1} L{x2},{y2}" {timing}/>'
              f'<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;.15;.85;1" {timing}/></circle>')
    gx, gy = NODES["gateway"]
    for begin in (0, 1.3):
        s.add(f'<circle cx="{gx}" cy="{gy}" r="14" fill="none" stroke="{TEAL}" stroke-width="1.5">'
              f'<animate attributeName="r" values="14;46" dur="2.6s" begin="-{begin}s" repeatCount="indefinite"/>'
              f'<animate attributeName="opacity" values=".7;0" dur="2.6s" begin="-{begin}s" repeatCount="indefinite"/></circle>')
    for name, (x, y) in NODES.items():
        r = 14 if name == "gateway" else 7
        s.add(f'<circle cx="{x}" cy="{y}" r="{r + 7}" fill="{TEAL}" fill-opacity=".10"/>'
              f'<circle cx="{x}" cy="{y}" r="{r}" fill="{BG1}" stroke="{TEAL}" stroke-width="2"/>'
              f'<circle cx="{x}" cy="{y}" r="{5 if name == "gateway" else 2.5}" fill="{CYAN}"/>')
        dx, dy, anchor = LABEL_OFFSETS[name]
        s.text(x + dx, y + dy, name, font="m", size=13, fill=DIM if name != "gateway" else MUTED,
               anchor=anchor)

    x0 = 72
    prompt = [("~/dakar", TEAL), (" $ ", DIM), ("whoami", SOFT)]
    s.text(x0, 104, prompt, font="m", weight=500, size=18, cls="in")
    cursor_x = x0 + fonts.width("~/dakar $ whoami", "m", 500, 18) + 6
    s.add(f'<rect x="{cursor_x:.1f}" y="89" width="10" height="19" fill="{TEAL}" class="blink"/>')

    size = 66
    while fonts.width("Christian Gilbert", "d", 700, size) > 600:
        size -= 1
    y1 = 186
    y2 = y1 + round(size * 1.04)
    s.text(x0, y1, "Christian Gilbert", weight=700, size=size, cls="in", attrs='style="animation-delay:.12s"')
    s.text(x0, y2, "Fodé Diouf", weight=700, size=size, fill="url(#name)",
           cls="in", attrs='style="animation-delay:.24s"')
    role = "Network Administrator · Full-Stack Developer · Trainer"
    role_size = 21
    while fonts.width(role, "d", 500, role_size) > 610:
        role_size -= 0.5
    s.text(x0, y2 + 50, role, weight=500, size=role_size, fill=MUTED,
           cls="in", attrs='style="animation-delay:.36s"')

    x = x0
    for i, (label, dot) in enumerate((("Dakar, Senegal", AMBER), ("Founder of Teranga Académie", TEAL),
                                      ("Open to work", GREEN))):
        s.add(f'<g class="in" style="animation-delay:{0.5 + i * 0.1:.2f}s">')
        x += chip(s, fonts, x, 342, label, dot=dot) + 10
        s.add("</g>")

    s.add(f'</g><rect x=".75" y=".75" width="1198.5" height="418.5" rx="23.25" fill="none" '
          f'stroke="{LINE2}" stroke-width="1.5"/>')
    return s


# ---------------------------------------------------------------------------
# About: a neofetch-style terminal
# ---------------------------------------------------------------------------

ABOUT = [
    ("Role", "Network admin · Full-stack developer"),
    ("Founder", "Teranga Académie, e-learning in French"),
    ("Focus", "EdTech for francophone Africa"),
    ("Background", "Networks, IoT, teaching, marketing"),
    ("Education", "UCAO graduate · 3rd year at UNCHK"),
    ("Exploring", "AI agents · LLM integration · Data"),
    ("Open to", "Full-time or freelance · remote too"),
    ("Speaks", "French · English"),
]


def globe(s, cx, cy, r):
    """Wireframe globe with an orbiting node, used as the neofetch logo."""
    s.add(f'<defs><radialGradient id="gl" cx=".35" cy=".3" r=".8"><stop offset="0" stop-color="{TEAL}" '
          f'stop-opacity=".28"/><stop offset="1" stop-color="{TEAL}" stop-opacity="0"/></radialGradient>'
          f'<clipPath id="gc"><circle cx="{cx}" cy="{cy}" r="{r}"/></clipPath></defs>'
          f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#gl)" stroke="{TEAL}" stroke-width="2"/>')
    s.add(f'<g clip-path="url(#gc)" fill="none" stroke="{TEAL}" stroke-opacity=".45" stroke-width="1.3">')
    for rx in (r * 0.33, r * 0.68):
        s.add(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx:.1f}" ry="{r}"/>')
    s.add(f'<line x1="{cx}" y1="{cy - r}" x2="{cx}" y2="{cy + r}"/>')
    for dy in (-0.5, 0, 0.5):
        half = r * (1 - dy * dy) ** 0.5
        s.add(f'<ellipse cx="{cx}" cy="{cy + dy * r:.1f}" rx="{half:.1f}" ry="{half * 0.16:.1f}"/>')
    s.add("</g>")
    points = [(-0.42, -0.38), (0.30, -0.55), (0.55, 0.05), (-0.15, 0.10), (0.20, 0.52), (-0.55, 0.35)]
    pts = [(cx + px * r, cy + py * r) for px, py in points]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        s.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{CYAN}" '
              f'stroke-opacity=".55" stroke-width="1.2"/>')
    for x, y in pts:
        s.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{CYAN}"/>')
    orbit = (f"M{cx - r * 1.32:.1f},{cy} a{r * 1.32:.1f},{r * 0.36:.1f} 0 1,0 {r * 2.64:.1f},0 "
             f"a{r * 1.32:.1f},{r * 0.36:.1f} 0 1,0 {-r * 2.64:.1f},0")
    s.add(f'<g transform="rotate(-18 {cx} {cy})"><path d="{orbit}" fill="none" stroke="{CYAN}" '
          f'stroke-opacity=".35" stroke-dasharray="3 6"/>'
          f'<circle r="6" fill="{AMBER}" filter="url(#tglow)"><animateMotion path="{orbit}" dur="7s" '
          f'repeatCount="indefinite"/></circle></g>')


def terminal(fonts):
    s = Svg(1200, 560, "About me. " + ". ".join(f"{k}: {v}" for k, v in ABOUT))
    s.add('<defs><filter id="tglow" x="-300%" y="-300%" width="700%" height="700%"><feGaussianBlur '
          'stdDeviation="3"/><feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>')
    clip = card_background(s, "t", glow=(0.08, 0.2))
    s.add(f'<g clip-path="url(#{clip})"><rect width="1200" height="52" fill="{BAR}"/>'
          f'<line x1="0" y1="52" x2="1200" y2="52" stroke="{LINE}"/></g>')
    for i, color in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
        s.add(f'<circle cx="{30 + i * 22}" cy="26" r="7" fill="{color}"/>')
    s.text(600, 31, "christian@dakar: ~", font="m", size=14, fill=DIM, anchor="middle")

    prompt = [("christian@dakar", TEAL, 700), (":", DIM), ("~", CYAN), ("$ ", DIM)]
    s.text(56, 104, prompt + [("neofetch", SOFT)], font="m", size=19, cls="in")

    globe(s, 220, 300, 112)

    x, y, step = 440, 158, 33
    s.text(x, y, [("christian", TEAL, 700), ("@", DIM), ("dakar", CYAN, 700)], font="m", size=19,
           cls="in", attrs='style="animation-delay:.15s"')
    s.text(x, y + 26, "-" * 15, font="m", size=19, fill=LINE2,
           cls="in", attrs='style="animation-delay:.2s"')
    key_w = fonts.width(max((k for k, _ in ABOUT), key=len) + "  ", "m", 400, 19)
    for i, (key, value) in enumerate(ABOUT):
        row_y = y + 64 + i * step
        delay = f'style="animation-delay:{0.28 + i * 0.09:.2f}s"'
        s.text(x, row_y, key, font="m", weight=700, size=19, fill=TEAL, cls="in", attrs=delay)
        s.text(x + key_w, row_y, value, font="m", size=19, fill=SOFT, cls="in", attrs=delay)
    swatch_y = y + 64 + len(ABOUT) * step - 6
    s.add(f'<g class="in" style="animation-delay:{0.28 + len(ABOUT) * 0.09:.2f}s">')
    for i, color in enumerate((BG1, TEAL, CYAN, GREEN, AMBER, "#F472B6", "#818CF8", TEXT)):
        s.add(f'<rect x="{x + i * 34}" y="{swatch_y}" width="30" height="20" rx="4" fill="{color}" '
              f'stroke="{LINE2}"/>')
    s.add("</g>")

    s.text(56, 528, prompt, font="m", size=19, cls="in", attrs='style="animation-delay:1.2s"')
    cursor_x = 56 + fonts.width("christian@dakar:~$ ", "m", 400, 19)
    s.add(f'<rect x="{cursor_x:.1f}" y="512" width="11" height="21" fill="{TEAL}" class="blink"/>')
    card_border(s)
    return s


# ---------------------------------------------------------------------------
# Section titles (light and dark versions, picked by GitHub's theme)
# ---------------------------------------------------------------------------

def title(fonts, number, text, comment, dark):
    s = Svg(1200, 84, text)
    fg = TEXT if dark else INK
    s.text(0, 54, f"{number} /", font="m", weight=500, size=17, fill=TEAL)
    tx = fonts.width(f"{number} / ", "m", 500, 17) + 6
    s.text(tx, 56, text, weight=700, size=36, fill=fg)
    line_x = tx + fonts.width(text, "d", 700, 36) + 24
    comment_w = fonts.width(comment, "m", 400, 15)
    s.add(f'<defs><linearGradient id="l" x1="0" x2="1"><stop offset="0" stop-color="{TEAL}"/>'
          f'<stop offset="1" stop-color="{TEAL}" stop-opacity="0"/></linearGradient></defs>'
          f'<rect x="{line_x:.1f}" y="43" width="{1200 - line_x - comment_w - 24:.1f}" height="2" rx="1" fill="url(#l)"/>')
    s.text(1200, 54, comment, font="m", size=15, fill=DIM if dark else MUTED, anchor="end")
    return s


# ---------------------------------------------------------------------------
# Project cards
# ---------------------------------------------------------------------------

def project_wide(fonts, image, url, label, title_text, tagline, chips, cta):
    s = Svg(1200, 470, f"{title_text}: {tagline}")
    clip = card_background(s, "w", glow=(0.95, 0.9))
    s.add(f'<g clip-path="url(#{clip})">')
    browser_frame(s, "f", 600, 64, 680, url, screenshot(image, 1360))
    s.add("</g>")

    x = 56
    chip(s, fonts, x, 56, label, color=TEAL, dot=TEAL, cls="in")
    s.text(x, 162, title_text, weight=700, size=56, cls="in", attrs='style="animation-delay:.1s"')
    for i, line in enumerate(wrap(fonts, tagline, "d", 400, 21, 480)):
        s.text(x, 210 + i * 32, line, size=21, fill=MUTED, cls="in", attrs='style="animation-delay:.2s"')
    cx = x
    for c in chips:
        if cx + fonts.width(c, "m", 500, 14) + 28 > 560:
            break
        cx += chip(s, fonts, cx, 342, c, cls="in") + 8
    s.text(x, 420, [(f"{cta} ", TEAL), ("↗", TEAL)], weight=600, size=18,
           cls="in", attrs='style="animation-delay:.3s"')
    card_border(s)
    return s


def project_small(fonts, name, url, title_text, tagline, chips, label, *, dot=GREEN, cta="Visit"):
    s = Svg(590, 640, f"{title_text}: {tagline}")
    clip = card_background(s, name[0], glow=(0.5, 0.0))
    s.add(f'<g clip-path="url(#{clip})">')
    frame_h = browser_frame(s, f"{name}f", 28, 28, 534, url, screenshot(name, 1080))
    s.add("</g>")
    y = 28 + frame_h + 44
    s.add(f'<circle cx="34" cy="{y - 5}" r="5" fill="{dot}"><animate attributeName="opacity" '
          f'values="1;.35;1" dur="2s" repeatCount="indefinite"/></circle>')
    s.text(48, y, label, font="m", weight=500, size=14, fill=dot, attrs='letter-spacing="1.5"')
    s.text(28, y + 46, title_text, weight=700, size=34)
    for i, line in enumerate(wrap(fonts, tagline, "d", 400, 19, 534)):
        s.text(28, y + 84 + i * 28, line, size=19, fill=MUTED)
    cx = 28
    for c in chips:
        cx += chip(s, fonts, cx, s.h - 64, c) + 8
    s.text(562, s.h - 42, [(f"{cta} ", TEAL), ("↗", TEAL)], weight=600, size=18, anchor="end")
    card_border(s)
    return s


def project_progress(fonts, title_text, tagline):
    """Slim card for a project still being built, with an indeterminate progress bar."""
    s = Svg(1200, 204, f"{title_text}, in progress: {tagline}")
    card_background(s, "p", glow=(1.0, 0.5))
    s.add(f'<circle cx="62" cy="55" r="5" fill="{AMBER}"><animate attributeName="opacity" '
          f'values="1;.35;1" dur="2s" repeatCount="indefinite"/></circle>')
    s.text(76, 60, "IN PROGRESS", font="m", weight=500, size=14, fill=AMBER, attrs='letter-spacing="1.5"')
    s.text(56, 106, title_text, weight=700, size=34)
    for i, line in enumerate(wrap(fonts, tagline, "d", 400, 19, 600)):
        s.text(56, 142 + i * 28, line, size=19, fill=MUTED)
    x, w, bar_y = 760, 384, 108
    s.text(x, bar_y - 20, [("$ ", TEAL), ("teranga-ai ", SOFT), ("--build", MUTED)], font="m", size=16)
    s.add(f'<defs><clipPath id="pb"><rect x="{x}" y="{bar_y}" width="{w}" height="10" rx="5"/></clipPath>'
          f'<linearGradient id="pg" x1="0" x2="1"><stop offset="0" stop-color="{AMBER}" stop-opacity="0"/>'
          f'<stop offset=".5" stop-color="{AMBER}"/><stop offset="1" stop-color="{AMBER}" stop-opacity="0"/>'
          f'</linearGradient></defs>'
          f'<rect x="{x}" y="{bar_y}" width="{w}" height="10" rx="5" fill="{PANEL}" stroke="{LINE2}"/>'
          f'<g clip-path="url(#pb)"><rect x="{x - 160}" y="{bar_y}" width="160" height="10" fill="url(#pg)">'
          f'<animate attributeName="x" values="{x - 160};{x + w}" dur="2.2s" repeatCount="indefinite"/>'
          f'</rect></g>')
    s.text(x, bar_y + 42, "status: work in progress", font="m", size=14, fill=DIM)
    card_border(s)
    return s


# ---------------------------------------------------------------------------
# Tech stack
# ---------------------------------------------------------------------------

# (category, skillicons.dev ids or None, text chips for skills that have no icon)
STACK = [
    ("NETWORK & SECURITY", None, ["Switches", "Firewalls", "VPN", "Linux servers"]),
    ("LANGUAGES", ["js", "ts", "python", "php", "java", "c", "cpp", "bash"], None),
    ("FRONTEND", ["html", "css", "react", "nextjs", "angular", "tailwind", "bootstrap", "sass"], None),
    ("BACKEND & DATA", ["nodejs", "django", "mysql", "postgres", "supabase", "wordpress"], None),
    ("CLOUD · DEVOPS · IOT", ["vercel", "docker", "linux", "aws", "gcp", "arduino", "raspberrypi", "git"], None),
    ("AI & DESIGN", ["tensorflow", "pytorch", "figma", "ps", "ai", "pr", "ae"], None),
]
ICON_NAMES = {
    "supabase": "Supabase", "vercel": "Vercel", "git": "Git",
    "linux": "Linux", "bash": "Bash", "docker": "Docker", "aws": "AWS", "gcp": "Google Cloud",
    "raspberrypi": "Raspberry Pi", "arduino": "Arduino", "html": "HTML", "css": "CSS",
    "js": "JavaScript", "ts": "TypeScript", "react": "React", "nextjs": "Next.js",
    "angular": "Angular", "nodejs": "Node.js", "php": "PHP", "django": "Django",
    "wordpress": "WordPress", "tailwind": "Tailwind CSS", "bootstrap": "Bootstrap", "sass": "Sass",
    "python": "Python", "java": "Java", "c": "C", "cpp": "C++", "mysql": "MySQL",
    "postgres": "PostgreSQL", "tensorflow": "TensorFlow", "pytorch": "PyTorch",
    "ps": "Photoshop", "ai": "Illustrator", "ae": "After Effects", "pr": "Premiere Pro",
    "xd": "Adobe XD", "figma": "Figma",
}


def icon(name):
    path = CACHE / f"icon-{name}.svg"
    if not path.exists():
        path.write_bytes(fetch(f"https://skillicons.dev/icons?i={name}", MODERN_UA))
    return "data:image/svg+xml;base64," + base64.b64encode(path.read_bytes()).decode()


def stack(fonts):
    size, gap, row_h, top = 52, 14, 84, 26
    h = top * 2 + row_h * len(STACK)
    label = "Tech stack. " + ". ".join(
        f"{cat.title()}: {', '.join([ICON_NAMES[i] for i in icons or []] + (chips or []))}"
        for cat, icons, chips in STACK)
    s = Svg(1200, h, label)
    card_background(s, "s", glow=(1.0, 0.0))
    n = 0
    for r, (category, icons, chips) in enumerate(STACK):
        y = top + r * row_h
        if r:
            s.add(f'<line x1="40" y1="{y}" x2="1160" y2="{y}" stroke="{LINE}"/>')
        s.text(48, y + row_h / 2 + 5, category, font="m", weight=700, size=14, fill=TEAL,
               attrs='letter-spacing="1.5"')
        x = 330
        for name in icons or []:
            s.add(f'<image class="in" style="animation-delay:{n * 0.03:.2f}s" x="{x}" '
                  f'y="{y + (row_h - size) / 2:g}" width="{size}" height="{size}" href="{icon(name)}"/>')
            x += size + gap
            n += 1
        for c in chips or []:
            x += chip(s, fonts, x, y + (row_h - 42) / 2, c, h=42, size=16, dot=CYAN) + 12
    card_border(s)
    return s


# ---------------------------------------------------------------------------
# Contact buttons and footer
# ---------------------------------------------------------------------------

BUTTONS = {
    "portfolio": "Portfolio", "academie": "Teranga Académie", "linkedin": "LinkedIn", "email": "Email",
}


def button(fonts, kind):
    """Pill-shaped link button sized to its label."""
    text = BUTTONS[kind]
    w = round(82 + fonts.width(text, "d", 600, 22) + 64)
    s = Svg(w, 76, text)
    s.add(f'<rect x="1" y="1" width="{w - 2}" height="74" rx="37" fill="{BG1}" stroke="{LINE2}" stroke-width="1.5"/>')
    if kind == "portfolio":
        s.add(f'<rect x="26" y="20" width="36" height="36" rx="8" fill="{CYAN}"/>')
        s.text(44, 44, ">_", font="m", weight=700, size=16, fill=BG0, anchor="middle")
    elif kind == "academie":
        s.add(f'<rect x="26" y="20" width="36" height="36" rx="8" fill="{AMBER}"/>'
              f'<path d="M44 28l13 6.5-13 6.5-13-6.5z" fill="{BG0}"/>'
              f'<path d="M37 38v5.5c0 1.8 3.1 3.5 7 3.5s7-1.7 7-3.5V38" fill="none" stroke="{BG0}" stroke-width="2.2"/>'
              f'<path d="M57 34.5v7" stroke="{BG0}" stroke-width="2" stroke-linecap="round"/>')
    elif kind == "linkedin":
        s.add('<rect x="26" y="20" width="36" height="36" rx="8" fill="#0A66C2"/>'
              '<rect x="33" y="35" width="5.5" height="14" fill="#fff"/><circle cx="35.75" cy="29" r="3.4" fill="#fff"/>'
              '<path d="M43 35h5.2v2.1c.8-1.4 2.4-2.5 4.8-2.5 4 0 4.9 2.5 4.9 5.9V49h-5.5v-7.6c0-1.7-.3-3-2-3-1.8 0-2.1 1.4-2.1 3V49H43z" fill="#fff"/>')
    else:
        s.add(f'<rect x="26" y="20" width="36" height="36" rx="8" fill="{TEAL}"/>'
              f'<rect x="33" y="29" width="22" height="16" rx="2.5" fill="none" stroke="{BG0}" stroke-width="2.2"/>'
              f'<path d="M34 31l10 7 10-7" fill="none" stroke="{BG0}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>')
    s.text(82, 46, text, weight=600, size=22)
    s.text(w - 28, 46, "→", weight=600, size=22, fill=DIM, anchor="end")
    return s


def footer(fonts):
    s = Svg(1200, 120, "I build the network, then the apps that run on it")
    card_background(s, "z", glow=(0.5, 1.2))
    xs = [80 + i * 130 for i in range(9)]
    s.add(f'<line x1="{xs[0]}" y1="40" x2="{xs[-1]}" y2="40" stroke="{TEAL}" stroke-opacity=".3" '
          f'stroke-width="1.5"/>')
    for x in xs:
        s.add(f'<circle cx="{x}" cy="40" r="5" fill="{BG1}" stroke="{TEAL}" stroke-width="1.5"/>')
    for dur, offset in ((6, 0), (6, 3)):
        timing = f'dur="{dur}s" begin="-{offset}s" repeatCount="indefinite"'
        s.add(f'<circle r="4" fill="{CYAN}" filter="url(#fg)"><animateMotion path="M{xs[0]},40 L{xs[-1]},40" '
              f'{timing}/></circle>')
    s.add('<defs><filter id="fg" x="-300%" y="-300%" width="700%" height="700%"><feGaussianBlur '
          'stdDeviation="3"/><feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>')
    s.text(600, 88, [("$ ", TEAL), ("echo ", SOFT), ('"I build the network, then the apps that run on it"', MUTED)],
           font="m", size=16, anchor="middle")
    card_border(s)
    return s


def main():
    fonts = Fonts()
    outputs = {
        "header.svg": header(fonts),
        "about.svg": terminal(fonts),
        "project-academie.svg": project_wide(
            fonts, "academie", "terangaacademie.com", "FOUNDER · E-LEARNING PLATFORM",
            "Teranga Académie",
            "French-language online school born in Senegal: web development, office software, "
            "entrepreneurship and languages, with a 24/7 AI tutor and verifiable certificates.",
            ["43 courses", "795 lessons", "AI tutor", "Works offline", "Wave · Orange Money"],
            "terangaacademie.com"),
        "project-bureautique.svg": project_small(
            fonts, "bureautique", "cours-bureautique.vercel.app", "Cours Bureautique",
            "Office software training: Word, Excel, PowerPoint and collaboration tools, with "
            "142 video lessons, PDF exercises and quizzes.",
            ["Word", "Excel", "PowerPoint"], "LIVE WEBSITE"),
        "project-schoolpro.svg": project_small(
            fonts, "schoolpro", "github.com/cjr23/Gestion-Examens-Blancs", "SchoolPro",
            "School management app for Senegalese schools: mock exams (CFEE, BFEM, BAC), "
            "grades, report cards and attendance. Works offline.",
            ["HTML", "CSS", "JavaScript"], "WEB APP · OFFLINE", dot=CYAN, cta="Code"),
        "project-ceshfpt.svg": project_small(
            fonts, "ceshfpt", "ceshfpt.vercel.app", "CESHFPT Tambacounda",
            "Website for a solar energy and vocational training center: courses, solar "
            "installation estimator, photo gallery and WhatsApp contact.",
            ["HTML", "CSS", "JavaScript"], "LIVE WEBSITE"),
        "project-teranga.svg": project_small(
            fonts, "teranga", "terangaconsulting.vercel.app", "Teranga Consulting",
            "Showcase site for an IT, communication and training consultancy serving SMEs "
            "and NGOs in Senegal, with prices in FCFA.",
            ["HTML", "CSS", "JavaScript"], "LIVE WEBSITE"),
        "project-teranga-ai.svg": project_progress(
            fonts, "Teranga AI",
            "A customizable AI-agent platform for professionals, businesses and individuals."),
        "stack.svg": stack(fonts),
        "footer.svg": footer(fonts),
    }
    for kind in BUTTONS:
        outputs[f"button-{kind}.svg"] = button(fonts, kind)
    for number, (slug, text, comment) in enumerate((
            ("projects", "Featured projects", "// recent work"),
            ("stack", "Tech stack", "// tools I work with"),
            ("contact", "Get in touch", "// let's build something together")), start=1):
        for theme in ("dark", "light"):
            outputs[f"title-{slug}-{theme}.svg"] = title(fonts, f"0{number}", text, comment, theme == "dark")
    for filename, svg in outputs.items():
        (OUT / filename).write_text(svg.render(fonts), encoding="utf-8")
        print(f"{filename:28} {(OUT / filename).stat().st_size / 1024:6.1f} KB")


if __name__ == "__main__":
    main()
