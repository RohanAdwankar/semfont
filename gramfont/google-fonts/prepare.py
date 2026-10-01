"""Lay out the Markdown font the way google/fonts expects it, and check it.

    python3 google-fonts/prepare.py --repo-url https://github.com/<owner>/<repo> \\
        --base /path/to/LiberationSans-Regular.ttf

Writes ofl/markfont/{Markfont-Regular.ttf,OFL.txt} next to this script. The
repository URL goes into the copyright line, which Google's checks require and
which has to name the repository the font is maintained in, so it is an
argument rather than a guess.

The font is built from Liberation Sans, so the upstream notices travel with it,
on the first line of OFL.txt and in nameID 0. Google's checks want everything
after that first line to match their template exactly.

Afterwards, run `gftools add-font` against a checkout of google/fonts to write
METADATA.pb, and open the pull request there.
"""
import argparse
import datetime
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from gramfont import compile_font  # noqa: E402

FAMILY = 'Markfont'
# Verbatim from Liberation's own licence file. "Reserved Font Name" is
# Liberation's reservation, not this font's, and the licence asks for the
# notices to be kept as written.
UPSTREAM = ('Digitized data copyright (c) 2010 Google Corporation with Reserved Font '
            'Arimo, Tinos and Cousine, and Copyright (c) 2012 Red Hat, Inc. with '
            'Reserved Font Name Liberation.')
CHECKS = [
    'googlefonts/family/has_license', 'googlefonts/font_copyright',
    'googlefonts/license/OFL_body_text', 'googlefonts/license/OFL_copyright',
    'googlefonts/name/license', 'googlefonts/name/license_url',
    'googlefonts/name/rfn', 'googlefonts/name/mandatory_entries',
    'googlefonts/name/version_format', 'googlefonts/vendor_id',
    'opentype/font_version', 'name/char_restrictions',
    'opentype/name/match_familyname_fullfont',
]


def notice(repo_url, year):
    return (f'Copyright {year} The {FAMILY} Project Authors ({repo_url}), '
            f'with portions {UPSTREAM}')


def run_checks(folder, font):
    for check in CHECKS:
        done = subprocess.run(
            ['fontbakery', 'check-googlefonts', font, '-c', check, '-l', 'PASS', '-C',
             '--no-progress'], cwd=folder, capture_output=True, text=True)
        result = re.search(r'Result: (\w+)', done.stdout)
        print(f'  {result.group(1) if result else "?":5} {check}')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--repo-url', required=True, help='the git repository the font is maintained in')
    ap.add_argument('--base', required=True, help='LiberationSans-Regular.ttf')
    ap.add_argument('--year', type=int, default=datetime.date.today().year)
    ap.add_argument('--no-checks', action='store_true')
    args = ap.parse_args(argv)

    if not re.fullmatch(r'https://(github|gitlab)\.com/[\w.-]+/[\w.-]+', args.repo_url):
        raise SystemExit('--repo-url should look like https://github.com/<owner>/<repo>')

    folder = os.path.join(HERE, 'ofl', FAMILY.lower())
    os.makedirs(folder, exist_ok=True)
    line = notice(args.repo_url, args.year)
    template = open(os.path.join(HERE, 'OFL.template.txt'), encoding='utf-8').read()
    with open(os.path.join(folder, 'OFL.txt'), 'w', encoding='utf-8') as handle:
        handle.write(template.replace('{copyright}', line))

    source = open(os.path.join(ROOT, 'examples', 'markdown.gram'), encoding='utf-8').read()
    font = os.path.join(folder, f'{FAMILY}-Regular.ttf')
    compile_font(source, args.base, font, FAMILY, copyright=line)
    for extra in ('.woff2', '.fea'):
        os.remove(os.path.join(folder, f'{FAMILY}-Regular{extra}'))
    print(f'wrote {folder}/ ({os.path.getsize(font) // 1024} KB)')
    if not args.no_checks:
        print("Google's checks:")
        run_checks(folder, f'{FAMILY}-Regular.ttf')
    return 0


if __name__ == '__main__':
    sys.exit(main())
