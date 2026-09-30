"""Build a semfont .ttf: the valence channel, baked into a font file.

The library styles text at runtime, from the DOM. This does the same job
earlier and in a different place -- every word in the lexicon becomes a
contextual substitution inside the font, and `COLR`/`CPAL` supply the colour.
Set the result on a plain `<div>` and the text comes out coloured with no
script on the page at all.

Only the valence channel fits. Weight, size and tracking are the other things
semfont renders, and a static font cannot vary them per word; a variable font
could, and that is the interesting next step rather than a limitation of the
idea.

The lexicon and the theme are read out of the library at build time, so the
font cannot drift from what `analyze()` would say.

    python3 font/build.py --out semfont.ttf
"""
import argparse
import json
import math
import os
import subprocess
import sys

from fontTools import subset
from fontTools.colorLib.builder import buildCOLR, buildCPAL
from fontTools.feaLib.builder import addOpenTypeFeatures
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LETTERS = 'abcdefghijklmnopqrstuvwxyz'
INK = (0x11, 0x11, 0x11)
Q = chr(39)


# --------------------------------------------------------- read the library

def from_node(module, expression):
    """Evaluate an expression against one of the library's modules.

    The modules are imported one at a time rather than through the package
    entry point, which pulls in React and would make building a font depend on
    having the front end installed.
    """
    script = (f"import('./src/{module}.js').then(m => "
              f"process.stdout.write(JSON.stringify({expression})))")
    out = subprocess.run([os.environ.get('NODE', 'node'), '-e', script],
                         cwd=ROOT, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def read_theme(name):
    theme = from_node('theme', f'm.themes[{name!r}]')
    if theme is None:
        raise SystemExit(f'no theme called {name!r}')
    valence = next((row for row in theme['map']
                    if row['channel'] == 'valence' and row['render'] == 'color'),
                   None)
    if valence is None:
        raise SystemExit(f'theme {name!r} does not render valence as colour')
    return theme['thresholds']['valence'], valence


# ------------------------------------------------------------------- colour
# Reproduce `color-mix(in oklab, <ink>, <accent> pct%)`, which is what the
# stylesheet the library writes does at runtime.

def srgb_to_linear(channel):
    channel /= 255
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def linear_to_srgb(channel):
    value = (12.92 * channel if channel <= 0.0031308
             else 1.055 * (channel ** (1 / 2.4)) - 0.055)
    return max(0, min(255, round(value * 255)))


def rgb_to_oklab(rgb):
    r, g, b = (srgb_to_linear(c) for c in rgb)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def oklab_to_rgb(lab):
    lightness, a, b = lab
    l = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return tuple(linear_to_srgb(v) for v in (
        +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s))


def parse_oklch(text):
    inside = text[text.index('(') + 1:text.rindex(')')].replace('/', ' ')
    lightness, chroma, hue = (float(part) for part in inside.split()[:3])
    angle = math.radians(hue)
    return oklab_to_rgb((lightness, chroma * math.cos(angle), chroma * math.sin(angle)))


def mix(accent, fraction):
    start, end = rgb_to_oklab(INK), rgb_to_oklab(accent)
    return oklab_to_rgb(tuple(a + (b - a) * fraction for a, b in zip(start, end)))


# -------------------------------------------------------------- the choosing

def strength(value, threshold):
    return max(0.0, min(1.0, (abs(value) - threshold) / (1 - threshold)))


def pick_words(valence, threshold, limit, levels):
    """The lexicon, thinned to `limit` words and spread across the levels.

    Every word costs a rule, and a rule costs bytes. Spreading the sample over
    the strength bands rather than taking the strongest keeps the font honest
    about the middle of the range, which is most of the text anyone writes.
    """
    words = [(word, value) for word, value in valence.items()
             if abs(value) >= threshold and word.isalpha() and word.isascii()
             and 2 < len(word) <= 12]
    if limit <= 0 or limit >= len(words):
        return sorted(words)
    buckets = {level: [] for level in range(levels)}
    for word, value in sorted(words):
        buckets[min(levels - 1, int(strength(value, threshold) * levels))].append(
            (word, value))
    per = max(1, limit // levels)
    return sorted(pair for level in range(levels) for pair in buckets[level][:per])


# --------------------------------------------------------------- the font

def build(base_path, words, palette, threshold, levels, out_path, family):
    font = TTFont(base_path)
    options = subset.Options()
    options.layout_features = []      # the calt below is built from scratch
    options.name_IDs = [1, 2, 4, 6]
    options.glyph_names = False
    options.drop_tables += ['MATH', 'FFTM', 'kern']
    options.notdef_outline = True
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=list(range(0x20, 0x7F)) + [
        0xA0, 0x2018, 0x2019, 0x201C, 0x201D, 0x2013, 0x2014, 0x2026])
    subsetter.subset(font)

    glyf, hmtx = font['glyf'], font['hmtx']
    order, colr, added = font.getGlyphOrder()[:], {}, []
    # A COLR glyph paints layers from the palette, so a coloured letter needs
    # no new outline: an empty glyph pointing back at the plain one is enough.
    for char in LETTERS + LETTERS.upper():
        for slot in range(levels * 2):
            name = f'{char}.c{slot}'
            empty = Glyph()
            empty.numberOfContours = 0
            glyf[name] = empty
            hmtx[name] = hmtx[char]
            colr[name] = [(char, slot)]
            added.append(name)
    font.setGlyphOrder(order + added)
    font['maxp'].numGlyphs = len(order) + len(added)
    font['COLR'] = buildCOLR(colr)
    font['CPAL'] = buildCPAL([[(r / 255, g / 255, b / 255, 1.0)
                               for r, g, b in palette]])

    fea = ['@Letter = [%s];' % ' '.join(LETTERS + LETTERS.upper())]
    for slot in range(levels * 2):
        fea.append(f'lookup CLR{slot} {{')
        fea += [f'  sub {char} by {char}.c{slot};' for char in LETTERS + LETTERS.upper()]
        fea.append(f'}} CLR{slot};')
    fea.append('feature calt {')
    for word, value in words:
        slot = (0 if value < 0 else levels) + min(
            levels - 1, int(strength(value, threshold) * levels))
        for form in sorted({word, word.capitalize()}):
            bare = ' '.join(c + Q for c in form)
            marked = ' '.join(f'{c}{Q} lookup CLR{slot}' for c in form)
            # A word only counts on its own. Without these two the rule fires
            # inside longer words and "badge" comes out as red "bad" plus "ge".
            fea.append(f'  ignore sub @Letter {bare};')
            fea.append(f'  ignore sub {bare} @Letter;')
            fea.append(f'  sub {marked};')
    fea.append('} calt;')

    fea_path = os.path.splitext(out_path)[0] + '.fea'
    with open(fea_path, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(fea) + '\n')
    addOpenTypeFeatures(font, fea_path)
    for name_id in (1, 4, 6):
        font['name'].setName(family, name_id, 3, 1, 0x409)
    font.save(out_path)
    woff2 = os.path.splitext(out_path)[0] + '.woff2'
    font.flavor = 'woff2'
    font.save(woff2)
    return out_path, woff2, fea_path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--base', required=True, help='the regular font to build on')
    ap.add_argument('--out', default='semfont.ttf')
    ap.add_argument('--theme', default='editorial')
    ap.add_argument('--levels', type=int, default=4, help='colour steps per sign')
    ap.add_argument('--limit', type=int, default=0,
                    help='cap the number of lexicon words; 0 (the default) is all of them')
    ap.add_argument('--family', default='semfont')
    args = ap.parse_args(argv)

    threshold, row = read_theme(args.theme)
    accents = (parse_oklch(row['negative']), parse_oklch(row['positive']))
    palette = [mix(accent, ((level + 0.5) / args.levels) * row.get('max', 1.0))
               for accent in accents for level in range(args.levels)]
    valence = from_node('lexicon', 'm.VALENCE')
    words = pick_words(valence, threshold, args.limit, args.levels)

    ttf, woff2, _ = build(args.base, words, palette, threshold, args.levels,
                          args.out, args.family)
    negative = sum(1 for _, value in words if value < 0)
    print(f'{len(words)} words ({negative} negative) of {len(valence)} in the lexicon')
    print(f'{ttf} {os.path.getsize(ttf) // 1024} KB, '
          f'{woff2} {os.path.getsize(woff2) // 1024} KB')
    return 0


if __name__ == '__main__':
    sys.exit(main())
