"""How closely does the font agree with the library it was built from?

Runs the library's own analyze() over a set of sentences, shapes the same text
through the built font with HarfBuzz, and compares word by word which colour
slot each one landed in. The font is a finite-state approximation of a program,
so this is the measurement that says how good the approximation is.

    python3 font/build.py --base Regular.ttf --out /tmp/sf.ttf --names
    python3 font/parity.py /tmp/sf.ttf
"""
import argparse
import json
import os
import re
import subprocess
import sys

import uharfbuzz as hb
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Sentences chosen to exercise the rules a bare word lookup cannot express.
CURATED = [
    "The rollback should have helped, but instead it made things worse.",
    "We fixed the crash that was corrupting user data, and the team is genuinely proud of how quickly it shipped.",
    "It was not great, and honestly not good either.",
    "The deploy is very slow and totally broken, but the new cache is surprisingly fast.",
    "I don't think this is bad at all.",
    "This isn't broken, it just isn't finished.",
    "Nothing is wrong with the build.",
    "We never saw a failure, only slow tests.",
    "She fixed the leak and avoided the outage.",
    "The crash is gone and the tests are fast.",
    "It is not unhappy, not at all.",
    "They solved the bug but missed the regression.",
    "Terrible, awful, horrible; wonderful, lovely, great.",
    "The project failed, and we lost weeks, but the lessons were valuable.",
    "Corrupting data is bad. Recovering from it is hard.",
    "He was hating every minute and loving none of it.",
]


def prose_from_readme():
    text = open(os.path.join(ROOT, 'README.md'), encoding='utf-8').read()
    text = re.sub(r'```.*?```', ' ', text, flags=re.S)
    text = re.sub(r'`[^`]*`', ' ', text)
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'^[#|>\-*\d. ]+', '', text, flags=re.M)
    out = []
    for sentence in re.split(r'(?<=[.!?])\s+', text.replace('\n', ' ')):
        sentence = re.sub(r'\s+', ' ', sentence).strip()
        if 25 <= len(sentence) <= 260 and sentence.isascii():
            out.append(sentence)
    return out


def demo_passages():
    """The five passages the demo page ships, which the library was tuned on."""
    text = open(os.path.join(ROOT, 'demo', 'index.html'), encoding='utf-8').read()
    block = text[text.index('const SAMPLES = {'):text.index('};', text.index('const SAMPLES = {'))]
    out = []
    for match in re.finditer(r"'[^']+':\s*((?:\"(?:[^\"\\]|\\.)*\"\s*\+?\s*)+)", block):
        pieces = re.findall(r'"((?:[^"\\]|\\.)*)"', match.group(1))
        out.append(''.join(pieces))
    return out


def reference(sentences):
    done = subprocess.run(['node', os.path.join(ROOT, 'font', 'reference.mjs')],
                          input=json.dumps(sentences), capture_output=True,
                          text=True, check=True, cwd=ROOT)
    return json.loads(done.stdout)


def palette_slots(font_path):
    """slot index -> (sign, level), read back from the font's own naming."""
    return None


class Shaper:
    def __init__(self, path, levels):
        blob = hb.Blob.from_file_path(path)
        self.face = hb.Face(blob)
        self.font = hb.Font(self.face)
        self.levels = levels
        self.names = {i: self.font.glyph_to_string(i)
                      for i in range(self.face.glyph_count)}

    def slots(self, text):
        levels = self.levels
        """One colour slot per input character, None where it is uncoloured."""
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.font, buf, {'calt': True, 'liga': False, 'kern': False})
        slot_of = [None] * len(text)
        for info in buf.glyph_infos:
            name = self.names[info.codepoint]
            m = re.search(r'\.c(\d+)(?:x\d)?$', name)
            if m and info.cluster < len(text):
                # the slot reserved for resolvers paints the first positive colour
                slot = int(m.group(1))
                slot_of[info.cluster] = levels if slot >= 2 * levels else slot
        return slot_of


def expected_slot(valence, threshold, levels):
    strength = max(0.0, min(1.0, (abs(valence) - threshold) / (1 - threshold)))
    if abs(valence) < threshold:
        return None
    level = min(levels - 1, int(strength * levels))
    return (0 if valence < 0 else levels) + level


def sign_of(slot, levels):
    if slot is None:
        return 0
    return -1 if slot < levels else 1


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('font')
    ap.add_argument('--threshold', type=float, default=0.2)
    ap.add_argument('--levels', type=int, default=6)
    ap.add_argument('--show', type=int, default=25, help='how many disagreements to print')
    ap.add_argument('--readme', action='store_true',
                    help='also use the README prose (its own numbers change the corpus, so off by default)')
    args = ap.parse_args(argv)

    sentences = CURATED + demo_passages() + (prose_from_readme() if args.readme else [])
    shaper = Shaper(args.font, args.levels)
    tally = dict(both_plain=0, exact=0, same_sign=0, wrong_sign=0, missed=0, extra=0)
    misses = []
    for record in reference(sentences):
        slots = shaper.slots(record['text'])
        for word in record['words']:
            want = expected_slot(word['valence'], args.threshold, args.levels)
            got = slots[word['start']] if word['start'] < len(slots) else None
            if want is None and got is None:
                tally['both_plain'] += 1
                continue
            if want is None:
                kind = 'extra'
            elif got is None:
                kind = 'missed'
            elif want == got:
                kind = 'exact'
            elif sign_of(want, args.levels) == sign_of(got, args.levels):
                kind = 'same_sign'
            else:
                kind = 'wrong_sign'
            tally[kind] += 1
            if kind != 'exact':
                misses.append((kind, word['text'], word['valence'], want, got, record['text']))

    styled = sum(tally[k] for k in ('exact', 'same_sign', 'wrong_sign', 'missed'))
    right = tally['exact'] + tally['same_sign']
    print(f"words the library colours: {styled}")
    print(f"  font agrees on sign:     {right}  ({100 * right / max(1, styled):.0f}%)")
    print(f"  of which same level:     {tally['exact']}  ({100 * tally['exact'] / max(1, styled):.0f}%)")
    print(f"  font has the wrong sign: {tally['wrong_sign']}")
    print(f"  font leaves it plain:    {tally['missed']}")
    print(f"words the font colours and the library does not: {tally['extra']}")
    order = {'wrong_sign': 0, 'missed': 1, 'extra': 2, 'same_sign': 3}
    for kind, text, val, want, got, sentence in sorted(misses, key=lambda m: order[m[0]])[:args.show]:
        print(f"  {kind:10} {text:14} lib {val:+.2f} slot {want}  font slot {got}   | {sentence[:70]}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
