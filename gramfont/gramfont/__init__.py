"""Compile a grammar into a font that does its own parsing."""
from .grammar import GrammarError, parse, check_regular
from .plan import plan
from .font import Builder

__all__ = ['GrammarError', 'parse', 'check_regular', 'plan', 'Builder', 'compile_font']


def compile_font(source, base_path, out_path, family='gramfont', font_dir=None,
                 copyright=None, version='1.000'):
    grammar = check_regular(parse(source))
    shapes, _ = plan(grammar)
    builder = Builder(grammar, shapes, base_path, family, font_dir, copyright, version)
    builder.build_glyphs()
    return builder.save(out_path)
