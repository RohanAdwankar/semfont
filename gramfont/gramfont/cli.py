"""gramfont <grammar> -o <font.ttf> --base <regular.ttf>"""
import argparse
import os
import sys

from . import compile_font
from .grammar import GrammarError


def main(argv=None):
    ap = argparse.ArgumentParser(prog='gramfont', description=__doc__)
    ap.add_argument('grammar')
    ap.add_argument('-o', '--out', default=None, help='output .ttf (a .woff2 is written beside it)')
    ap.add_argument('--base', required=True, help='the regular font the alphabet comes from')
    ap.add_argument('--family', default=None)
    ap.add_argument('--copyright', default=None,
                    help='the full copyright notice for nameID 0, including the base font\'s own')
    ap.add_argument('--version', default='1.000')
    ap.add_argument('--fonts', default=None,
                    help='where a style\'s font file is looked for (default: beside --base)')
    ap.add_argument('--check', action='store_true', help='validate the grammar and stop')
    args = ap.parse_args(argv)

    source = open(args.grammar, encoding='utf-8').read()
    out = args.out or os.path.splitext(args.grammar)[0] + '.ttf'
    family = args.family or os.path.splitext(os.path.basename(out))[0]
    try:
        if args.check:
            from . import check_regular, parse, plan
            shapes, _ = plan(check_regular(parse(source)))
            print(f'{args.grammar}: {len(shapes)} rule shapes, all regular')
            return 0
        ttf, woff2, fea = compile_font(source, args.base, out, family, args.fonts,
                                         args.copyright, args.version)
    except GrammarError as error:
        print(f'{args.grammar}: {error}', file=sys.stderr)
        return 1
    print(f'{ttf} {os.path.getsize(ttf) // 1024} KB, '
          f'{woff2} {os.path.getsize(woff2) // 1024} KB')
    return 0


if __name__ == '__main__':
    sys.exit(main())
