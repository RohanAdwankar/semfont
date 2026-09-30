"""Build a semfont .ttf: the valence channel, baked into a font file.

The library styles text at runtime, from the DOM. This does the same job
earlier and in a different place -- every word in the lexicon becomes a
contextual substitution inside the font, and `COLR`/`CPAL` supply the colour.
Set the result on a plain `<div>` and the text comes out coloured with no
script on the page at all.

Three layers, all substitutions:

  words      every lexicon word, and every real inflected form of one, is
             matched letter by letter and painted its colour
  clauses    a negator ("not", "never", "don't") flips the colour of what
             follows it in the clause, a resolver ("fixed", "avoided") turns
             the harm after it into relief, and both stop at a clause break
  state      the clause state rides along in the glyph stream, one bit for
             "negated" and one for "resolved", so the font needs no memory
             beyond the glyph it is looking at

Only the valence channel is here. Weight, size and tracking are the other
things semfont renders, and a static font cannot vary them per word.

The lexicon, the theme, and the negator, resolver and clause-break lists are
read out of the library at build time, so the font cannot drift from what
`analyze()` would say. `font/parity.py` measures how closely it agrees.

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
from fontTools.pens.ttGlyphPen import TTGlyphPen
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


# The library's stemmer, run backwards. lexicon.js turns a form into candidate
# bases by stripping a suffix and optionally restoring a letter; generating the
# forms means doing the reverse for every base. Whether a generated form really
# resolves to its base is left to the library's own lookup(), not to this table.
SUFFIXES = [
    ('ally', ''), ('ically', ''), ('ically', 'e'), ('iness', 'y'), ('ness', ''),
    ('ingly', ''), ('edly', ''), ('ily', 'y'), ('ly', ''),
    ('ing', ''), ('ing', 'e'), ('ies', 'y'), ('ied', 'y'), ('es', ''), ('ed', ''),
    ('ed', 'e'), ('er', ''), ('er', 'e'), ('est', ''), ('s', ''),
    ('ic', 'e'), ('ic', 'y'), ('ical', 'e'), ('ation', 'e'), ('ment', ''),
]
DOUBLING = 'bdfglmnprt'


def candidate_forms(bases):
    out = set()
    for base in bases:
        for suffix, restore in SUFFIXES:
            if restore and not base.endswith(restore):
                continue
            form = base[:len(base) - len(restore)] + suffix
            if len(form) > len(suffix) + 2:
                out.add(form)
        if base[-1] in DOUBLING:
            for suffix in ('ed', 'ing', 'er', 'est'):
                out.add(base + base[-1] + suffix)
    return sorted(out - set(bases))


# Below this, a generated form is noise. The library's stemmer accepts anything
# that ends in a known suffix, so "goodic" and "braveried" would be scored; a
# frequency list is what says which forms people actually write. Zipf 2.0 is
# about one occurrence in a hundred thousand words.
MIN_ZIPF = 2.0


def real_words(candidates):
    try:
        from wordfreq import zipf_frequency
    except ImportError:
        raise SystemExit('inflected forms need the wordfreq package: pip install wordfreq '
                         '(or pass --exact-only)')
    return [w for w in candidates if zipf_frequency(w, 'en') >= MIN_ZIPF]


def library_lookup(table, candidates):
    """Ask the library what each candidate scores in `table`."""
    done = subprocess.run(
        [os.environ.get('NODE', 'node'), os.path.join(ROOT, 'font', 'forms.mjs')],
        input=json.dumps({'table': table, 'words': candidates}),
        capture_output=True, text=True, check=True, cwd=ROOT)
    return json.loads(done.stdout)


def with_inflections(valence, table='VALENCE'):
    """The lexicon plus every real inflected form the library would also score."""
    merged = dict(valence)
    merged.update(library_lookup(table, real_words(candidate_forms(list(valence)))))
    return merged


def library_lists():
    done = subprocess.run(
        [os.environ.get('NODE', 'node'), os.path.join(ROOT, 'font', 'forms.mjs')],
        input=json.dumps({'lists': True}), capture_output=True, text=True,
        check=True, cwd=ROOT)
    return json.loads(done.stdout)


def pick_words(valence, threshold, limit, levels):
    """The lexicon, thinned to `limit` words and spread across the levels.

    Every word costs a rule, and a rule costs bytes. Spreading the sample over
    the strength bands rather than taking the strongest keeps the font honest
    about the middle of the range, which is most of the text anyone writes.
    """
    words = [(word, value) for word, value in valence.items()
             if abs(value) >= threshold and word.isalpha() and word.isascii()
             and 2 < len(word) <= 14]
    if limit <= 0 or limit >= len(words):
        return sorted(words)
    buckets = {level: [] for level in range(levels)}
    for word, value in sorted(words):
        buckets[min(levels - 1, int(strength(value, threshold) * levels))].append(
            (word, value))
    per = max(1, limit // levels)
    return sorted(pair for level in range(levels) for pair in buckets[level][:per])


# --------------------------------------------------------------- the font

# ------------------------------------------------------------ the clause state

NEGATED, RESOLVED = 1, 2          # bits of the state a glyph carries
STATES = (0, NEGATED, RESOLVED, NEGATED | RESOLVED)
NEGATION_DAMPING = 0.74           # deep.js: "not great" is mildly bad
RESOLVER_RELIEF = 0.7             # deep.js: most resolvers give 0.7
# Punctuation that ends a clause. A glyph that is not a carrier never takes on
# a state, so the state stops at it without any rule saying so.
BREAKERS = set(',;:()[].!?') | {'–', '—', '…'}


def after_context(value, state):
    """deep.js's negation and resolver rules, applied to one value."""
    if state & NEGATED:
        value = -value * NEGATION_DAMPING
    if state & RESOLVED and value < 0:
        value = -value * RESOLVER_RELIEF
    return value


def slot_of(value, threshold, levels):
    if abs(value) < threshold:
        return None
    return (0 if value < 0 else levels) + min(
        levels - 1, int(strength(value, threshold) * levels))


def bin_value(slot, threshold, levels):
    """The middle of a slot's strength band, as a signed value."""
    level = slot % levels
    magnitude = threshold + ((level + 0.5) / levels) * (1 - threshold)
    return -magnitude if slot < levels else magnitude


def seed_forms(words, shouted=True):
    """Spellings of a word as the font will meet it, apostrophes included.

    The tokenizer keeps an apostrophe inside a word and drops it from the
    normalised form, so "dont" is also "don't" and "don’t".
    """
    out = set()
    for word in words:
        forms = {word}
        if word.endswith('nt') and len(word) > 3:
            forms |= {word[:-1] + "'" + 't', word[:-1] + '’' + 't'}
        for form in forms:
            out |= {form, form.capitalize()} | ({form.upper()} if shouted else set())
    return sorted(out, key=lambda f: (-len(f), f))


def build(base_path, words, palette, threshold, levels, out_path, family,
          keep_names=False, resolvers=(), negators=(), clause_words=()):
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
    cmap = font.getBestCmap()
    lifted = levels * 2      # a slot no context can repaint: see the resolver rules
    slots = range(levels * 2 + 1)
    palette = list(palette) + [palette[levels]]   # same colour as the first positive slot
    letters = LETTERS + LETTERS.upper()
    name_of = {chr(cp): glyph for cp, glyph in cmap.items()
               if cp < 0x7F or cp in (0xA0, 0x2018, 0x2019, 0x201C, 0x201D, 0x2013, 0x2014, 0x2026)}
    carriers = [c for c in name_of if c not in BREAKERS and c >= ' ']
    non_letters = [c for c in carriers if c not in letters]

    def shell(name, like):
        empty = Glyph()
        empty.numberOfContours = 0
        glyf[name] = empty
        hmtx[name] = hmtx[like]
        added.append(name)

    def alias(name, base):
        """A glyph that draws exactly like `base`, at the cost of one component."""
        if glyf[base].numberOfContours == 0:
            shell(name, base)
            return
        pen = TTGlyphPen(glyf.glyphs)
        pen.addComponent(base, (1, 0, 0, 1, 0, 0))
        glyf[name] = pen.glyph()
        hmtx[name] = hmtx[base]
        added.append(name)

    # State 0: a letter painted a colour. A COLR glyph paints layers from the
    # palette, so it needs no outline of its own: an empty glyph pointing back
    # at the plain letter is enough.
    def painted(char, slot, state):
        suffix = f'x{state}' if state else ''
        return f'{name_of[char]}.c{slot}{suffix}'

    def plain(char, state):
        return name_of[char] if not state else f'{name_of[char]}.x{state}'

    for char in letters:
        for slot in slots:
            shell(painted(char, slot, 0), name_of[char])
            colr[painted(char, slot, 0)] = [(name_of[char], slot)]
    # States 1-3: every carrier again, and every painted letter again, so the
    # state can travel through both a coloured word and a plain one.
    for state in STATES[1:]:
        for char in carriers:
            alias(plain(char, state), name_of[char])
        for char in letters:
            for slot in slots:
                shell(painted(char, slot, state), name_of[char])
                colr[painted(char, slot, state)] = [(name_of[char], slot)]

    font.setGlyphOrder(order + added)
    font['maxp'].numGlyphs = len(order) + len(added)
    font['COLR'] = buildCOLR(colr)
    font['CPAL'] = buildCPAL([[(r / 255, g / 255, b / 255, 1.0)
                               for r, g, b in palette]])

    # ---- the rules
    def cls(glyphs):
        return '[%s]' % ' '.join(glyphs)

    def letter_glyphs(state):
        return [plain(c, state) for c in letters] + [
            painted(c, k, state) for c in letters for k in slots]

    def carrier_glyphs(state):
        return letter_glyphs(state) + [plain(c, state) for c in non_letters]

    fea = []
    fea.append('@Letter = %s;' % cls(list(letters)))
    fea.append('@AnyLetter = %s;' % cls(g for st in STATES for g in letter_glyphs(st)))
    fea.append('@NonLetter = %s;' % cls(name_of[c] for c in name_of if c not in letters))
    for state in STATES:
        fea.append(f'@Car{state} = {cls(carrier_glyphs(state))};')
    for slot in slots:
        fea.append(f'lookup CLR{slot} {{')
        fea += [f'  sub {char} by {painted(char, slot, 0)};' for char in letters]
        fea.append(f'}} CLR{slot};')

    # Moving a glyph into a state. A painted letter is repainted on the way in:
    # negation flips its sign and softens it, a resolver turns harm into relief,
    # and a word that ends up below the threshold is left plain.
    for state in STATES[1:]:
        fea.append(f'lookup IN{state} {{')
        for char in letters:
            fea.append(f'  sub {name_of[char]} by {plain(char, state)};')
            for slot in slots:
                if slot == lifted:
                    target = painted(char, lifted, state)
                else:
                    moved = slot_of(after_context(bin_value(slot, threshold, levels), state),
                                    threshold, levels)
                    target = plain(char, state) if moved is None else painted(char, moved, state)
                fea.append(f'  sub {painted(char, slot, 0)} by {target};')
        for char in non_letters:
            fea.append(f'  sub {name_of[char]} by {plain(char, state)};')
        fea.append(f'}} IN{state};')

    # A resolver is lifted to mild relief *after* negation has had its say, so
    # "not fixed" is still good news. deep.js: negate first, then if the result
    # is not positive, raise it to +0.35. The letters go straight into the
    # state the word starts in, painted in a slot no later state can repaint.
    for state in STATES:
        fea.append(f'lookup LIFT{state} {{')
        for char in letters:
            fea.append(f'  sub {plain(char, 0)} by {painted(char, lifted, state)};')
            for slot in range(levels * 2):
                value = bin_value(slot, threshold, levels)
                if state & NEGATED:
                    value = -value * NEGATION_DAMPING
                moved = lifted if value <= 0 else slot_of(value, threshold, levels)
                target = plain(char, state) if moved is None else painted(char, moved, state)
                fea.append(f'  sub {painted(char, slot, 0)} by {target};')
        fea.append(f'}} LIFT{state};')

    # -- layer 1: words
    fea.append('lookup WORDS {')
    # Longest word first. An `ignore` rule for "broke" matches "broken" (it is
    # followed by a letter) and ends the lookup at that position, so a shorter
    # word listed earlier silently shadows every longer word it begins.
    for word, value in sorted(words, key=lambda wv: (-len(wv[0]), wv[0])):
        slot = slot_of(value, threshold, levels)
        for form in sorted({word, word.capitalize()}):
            bare = ' '.join(c + Q for c in form)
            marked = ' '.join(f'{c}{Q} lookup CLR{slot}' for c in form)
            # A word only counts on its own. Without these two the rule fires
            # inside longer words and "badge" comes out as red "bad" plus "ge".
            fea.append(f'  ignore sub @Letter {bare};')
            fea.append(f'  ignore sub {bare} @Letter;')
            fea.append(f'  sub {marked};')
    fea.append('} WORDS;')

    # -- layers 2 and 3: clauses, and the state that carries them
    def word_class(char, state):
        """One position of a word: the letter as plain or painted, in a state."""
        if char in letters:
            return cls([plain(char, state)] + [painted(char, k, state) for k in slots])
        return cls([plain(char, state)])

    def spelled(form, state):
        return ' '.join(word_class(c, state) for c in form)

    def glyph_ok(form):
        return all(c in name_of for c in form)

    fea.append('lookup CONTEXT {')
    # Flip a bit on the space after the word. Longest first, for the same
    # reason as above: "cannot" ends in "not".
    seeds = [(form, 'flip') for form in seed_forms(negators) if glyph_ok(form)]
    seeds += [(form, 'set') for form in seed_forms(resolvers, shouted=False) if glyph_ok(form)]
    space = name_of[' ']
    for form, kind in sorted(seeds, key=lambda fs: (-len(fs[0]), fs[0])):
        if kind == 'set':
            # Paint the resolver while its letters are still unassigned, in the
            # state the glyph before it is carrying.
            fea.append('  ignore sub @AnyLetter ' + ' '.join(f'{word_class(c, 0)}{Q}' for c in form)
                       + ' @NonLetter;')
            for state in reversed(STATES):
                marked = ' '.join(f'{word_class(c, 0)}{Q} lookup LIFT{state}' for c in form)
                lead = f'@Car{state} ' if state else ''
                fea.append(f'  sub {lead}{marked} @NonLetter;')
        for state in STATES:
            target = state ^ NEGATED if kind == 'flip' else state | RESOLVED
            fea.append(f'  ignore sub @AnyLetter {spelled(form, state)} {space}{Q};')
            if target == 0:
                fea.append(f'  ignore sub {spelled(form, state)} {space}{Q};')
            elif target != state:
                fea.append(f'  sub {spelled(form, state)} {space}{Q} lookup IN{target};')
    # A conjunction opens a new clause, so the state must not enter it.
    for form in seed_forms(clause_words):
        if not glyph_ok(form):
            continue
        for state in STATES[1:]:
            marked = ' '.join(f'{word_class(c, 0)}{Q}' for c in form)
            fea.append(f'  ignore sub @Car{state} {marked} @NonLetter;')
    # Everything else inherits the state of the glyph before it.
    for state in STATES[1:]:
        fea.append(f'  sub @Car{state} @Car0{Q} lookup IN{state};')
    fea.append('} CONTEXT;')
    fea.append('feature calt { lookup WORDS; lookup CONTEXT; } calt;')

    fea_path = os.path.splitext(out_path)[0] + '.fea'
    with open(fea_path, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(fea) + '\n')
    addOpenTypeFeatures(font, fea_path)
    for name_id in (1, 4, 6):
        font['name'].setName(family, name_id, 3, 1, 0x409)
    if keep_names:
        font['post'].formatType = 2.0
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
    ap.add_argument('--levels', type=int, default=6, help='colour steps per sign')
    ap.add_argument('--limit', type=int, default=0,
                    help='cap the number of lexicon words; 0 (the default) is all of them')
    ap.add_argument('--family', default='semfont')
    ap.add_argument('--exact-only', action='store_true',
                    help='only the lexicon entries themselves, no inflected forms')
    ap.add_argument('--no-clauses', action='store_true',
                    help='words only: no negation or resolver state')
    ap.add_argument('--names', action='store_true',
                    help='keep glyph names, so font/parity.py can read what the shaper chose')
    args = ap.parse_args(argv)

    threshold, row = read_theme(args.theme)
    accents = (parse_oklch(row['negative']), parse_oklch(row['positive']))
    palette = [mix(accent, ((level + 0.5) / args.levels) * row.get('max', 1.0))
               for accent in accents for level in range(args.levels)]
    valence = from_node('lexicon', 'm.VALENCE')
    if not args.exact_only:
        valence = with_inflections(valence)
    words = pick_words(valence, threshold, args.limit, args.levels)

    lists = library_lists()
    resolvers = []
    if not args.no_clauses:
        table = {w: 1 for w in lists['resolvers']}
        resolvers = sorted(with_inflections(table, 'RESOLVERS'))
    ttf, woff2, _ = build(
        args.base, words, palette, threshold, args.levels, args.out, args.family,
        keep_names=args.names, resolvers=resolvers,
        negators=[] if args.no_clauses else lists['negators'],
        clause_words=[] if args.no_clauses else lists['clauseWords'])
    negative = sum(1 for _, value in words if value < 0)
    print(f'{len(words)} words ({negative} negative) of {len(valence)} in the lexicon')
    print(f'{ttf} {os.path.getsize(ttf) // 1024} KB, '
          f'{woff2} {os.path.getsize(woff2) // 1024} KB')
    return 0


if __name__ == '__main__':
    sys.exit(main())
