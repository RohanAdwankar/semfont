"""Lay out the Markdown font the way google/fonts expects it, and check it.

    python3 google-fonts/prepare.py --repo-url https://github.com/<owner>/<repo> \\
        --base /path/to/LiberationSans-Regular.ttf

Writes ofl/markfont/{Markfont-Regular.ttf,OFL.txt} next to this script and runs
Google's fontbakery profile over the font. The
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


def notice(repo_url, year):
    return (f'Copyright {year} The {FAMILY} Project Authors ({repo_url}), '
            f'with portions {UPSTREAM}')


def run_checks(folder, font):
    """Google's whole fontbakery profile, summarised.

    A partial run is the trap here. Without the profile's optional packages
    installed, fontbakery quietly runs about two thirds of the checks and says
    so only in its last lines, which is how a missing-glyphs failure once
    went unseen. So the count of checks that ran is printed, and a partial
    run is called out.
    """
    done = subprocess.run(
        ['fontbakery', 'check-googlefonts', font, '-l', 'PASS', '-C', '--no-progress'],
        cwd=folder, capture_output=True, text=True)
    out = done.stdout + done.stderr
    sections = re.split(r'\n >> ', '\n' + out)[1:]
    found = {}
    for section in sections:
        name = section.split('\n', 1)[0].strip()
        result = re.search(r'Result: (\w+)', section)
        if result:
            found.setdefault(result.group(1), []).append(name)
    for level in ('ERROR', 'FAIL', 'WARN'):
        for name in found.get(level, []):
            print(f'  {level:5} {name}')
    ran = sum(len(v) for k, v in found.items() if k != 'SKIP')
    summary = ', '.join(f'{len(v)} {k}' for k, v in sorted(found.items())
                        if k in ('PASS', 'WARN', 'FAIL', 'ERROR'))
    print(f'  {ran} checks ran: {summary or "none"}')
    if "googlefonts' extra" in out:
        print("  PARTIAL RUN: install fontbakery's googlefonts extra, or this misses checks.")
    return not found.get('FAIL') and not found.get('ERROR')


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
        return 0 if run_checks(folder, f'{FAMILY}-Regular.ttf') else 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
