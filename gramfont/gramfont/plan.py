"""Expand a grammar into the shapes a lookup can actually run.

`check_regular` has already established that the grammar is regular. That is
necessary and not sufficient: plenty of regular patterns still do not fit a
chained contextual substitution. This stage flattens every rule into concrete
alternatives and either classifies one as a shape the compiler emits, or says
which part of it does not fit.
"""
from .grammar import (Alt, Cat, GrammarError, Lit, Opt, Ref, Rep, ANCHORS,
                      BUILTIN, marker_chars)

MARKER, CONTENT, RUN, ANCHOR = 'marker', 'content', 'run', 'anchor'
# Beyond this the glyph count runs away: every state holds the whole alphabet.
MAX_TOGGLES = 6


class Atom:
    def __init__(self, kind, chars=None, anchor=None):
        self.kind, self.chars, self.anchor = kind, chars, anchor

    def __repr__(self):
        if self.kind == ANCHOR:
            return f'<{self.anchor}>'
        body = ''.join(sorted(self.chars))
        return f'{self.kind}({body if len(body) < 12 else str(len(body)) + " chars"})'


def classes(alphabet, markers=()):
    """The builtin character classes, resolved against this alphabet.

    Marker characters are excluded from all of them. A class that contained
    its own closing delimiter would carry the style straight through it.
    """
    chars = set(alphabet) - set(markers)
    resolved = dict(BUILTIN)
    resolved['any'] = chars
    resolved['space'] = {c for c in chars if c.isspace()}
    resolved['nonspace'] = {c for c in chars if not c.isspace()}
    resolved['word'] = {c for c in chars if c.isalnum()}
    resolved['letter'] = {c for c in chars if c.isalpha()}
    resolved['digit'] = {c for c in chars if c.isdigit()}
    resolved['punct'] = {c for c in chars if not c.isalnum() and not c.isspace()}
    return resolved


def flatten(expr, grammar, cls, seen=()):
    """Expression -> list of alternatives, each a list of Atom."""
    if isinstance(expr, Lit):
        if not expr.text:
            return [[]]
        return [[Atom(MARKER, {c}) for c in expr.text]]
    if isinstance(expr, Ref):
        if expr.name in ANCHORS:
            return [[Atom(ANCHOR, anchor=expr.name)]]
        if expr.name in cls:
            return [[Atom(CONTENT, set(cls[expr.name]))]]
        return flatten(grammar.productions[expr.name], grammar, cls, seen)
    if isinstance(expr, Alt):
        return [alt for part in expr.parts for alt in flatten(part, grammar, cls, seen)]
    if isinstance(expr, Opt):
        return [[]] + flatten(expr.body, grammar, cls, seen)
    if isinstance(expr, Rep):
        inner = flatten(expr.body, grammar, cls, seen)
        if len(inner) != 1 or len(inner[0]) != 1 or inner[0][0].kind != CONTENT:
            raise GrammarError(
                'an unbounded repetition must wrap a single character class, '
                'for example { any }. A lookup can carry one style forward '
                'across a run of glyphs; it cannot count, so it cannot repeat '
                'a multi-character pattern.')
        return [[Atom(RUN, inner[0][0].chars)]]
    if isinstance(expr, Cat):
        out = [[]]
        for part in expr.parts:
            out = [head + tail for head in out
                   for tail in flatten(part, grammar, cls, seen)]
        return out
    raise GrammarError(f'cannot flatten {expr!r}')


class Shape:
    """One alternative of one rule, split into the parts a lookup needs.

    `prefix` opens the match, `body` is what gets styled, `suffix` closes it.
    A body holding the unbounded run is a span: the compiler seeds the first
    glyph after the prefix and lets a second rule carry the style along. A body
    of fixed-width atoms is styled position by position.
    """

    def __init__(self, rule, prefix, body, suffix, line_start):
        self.rule, self.prefix, self.body = rule, prefix, body
        self.suffix, self.line_start = suffix, line_start

    @property
    def spans(self):
        return any(a.kind == RUN for a in self.body)


def shape(rule, atoms):
    line_start = False
    while atoms and atoms[0].kind == ANCHOR:
        line_start = line_start or atoms[0].anchor == 'line_start'
        atoms = atoms[1:]
    for atom in atoms:
        if atom.kind == ANCHOR:
            raise GrammarError(
                f'{rule.name}: line_start only means anything at the very '
                f'start of a pattern', rule.line)
    if sum(a.kind == RUN for a in atoms) > 1:
        raise GrammarError(
            f'{rule.name}: two unbounded runs in one pattern. The font cannot '
            f'tell where the first one ends without counting.', rule.line)

    prefix = []
    while atoms and atoms[0].kind == MARKER:
        prefix.append(atoms.pop(0))
    suffix = []
    while atoms and atoms[-1].kind == MARKER:
        suffix.insert(0, atoms.pop())
    body = atoms
    if not body:
        raise GrammarError(
            f'{rule.name}: the pattern is all literal, so there is nothing to '
            f'style.', rule.line)
    if any(a.kind == MARKER for a in body):
        raise GrammarError(
            f'{rule.name}: a literal in the middle of the styled part. Split '
            f'this into one rule per side of it.', rule.line)
    if not prefix and not line_start:
        raise GrammarError(
            f'{rule.name}: the pattern has nothing in front of the styled '
            f'part, so it would match everywhere. Give it an opening literal '
            f'or anchor it with line_start.', rule.line)
    if any(a.kind == RUN for a in body) and len(body) != 1:
        raise GrammarError(
            f'{rule.name}: an unbounded run has to be the whole styled part. '
            f'A lookup carries the style to the end of the run and cannot see '
            f'past it.', rule.line)
    return Shape(rule, prefix, body, suffix, line_start)


def check_nesting_is_one_way(grammar):
    """Nesting has to run one way, because the lookups run in one order.

    A rule's lookup either fires before the one it nests inside or after it,
    and the font has no way to choose per occurrence. So `a` inside `b` and
    `b` inside `a` cannot both hold: whichever lookup runs first wins every
    time, which is a silently wrong render rather than a missing feature.
    """
    edges = {}
    for outer, inner, _ in grammar.combines:
        edges.setdefault(outer, set()).add(inner)
    state = {}

    def walk(style, path):
        if state.get(style) == 'open':
            cycle = ' inside '.join(reversed(path[path.index(style):] + [style]))
            raise GrammarError(
                f'{style} nests inside itself ({cycle}). Lookups run in one '
                f'fixed order, so only one direction of a pair can work; drop '
                f'the combine for the other one.')
        if state.get(style) == 'done':
            return
        state[style] = 'open'
        for nested in edges.get(style, ()):
            walk(nested, path + [style])
        state[style] = 'done'

    for style in list(edges):
        walk(style, [])


def resolve_class(expr, grammar, cls, rule):
    """A guard has to name one character class, not a pattern."""
    alts = flatten(expr, grammar, cls)
    if len(alts) != 1 or len(alts[0]) != 1 or alts[0][0].kind == RUN:
        raise GrammarError(
            f'{rule.name}: a guard takes one character class or one literal '
            f'character', rule.line)
    return set(alts[0][0].chars)


def plan(grammar):
    """Every rule, as the list of shapes the compiler will emit."""
    grammar.markers = marker_chars(grammar)
    cls = classes(grammar.alphabet, grammar.markers)
    if grammar.toggles and not grammar.rules:
        # A toggle grammar has no spans, so nothing needs markers held out of
        # the classes; `word` has to mean word for the underscore guard.
        cls = classes(grammar.alphabet)
    for rule in grammar.rules:
        if rule.style not in grammar.styles:
            raise GrammarError(f'{rule.name}: no style called {rule.style!r}',
                               rule.line)
        rule.guards = [(kind, resolve_class(expr, grammar, cls, rule))
                       for kind, expr in rule.guards]
    for outer, inner, result in grammar.combines:
        for name in (outer, inner, result):
            if name not in grammar.styles:
                raise GrammarError(f'combine names {name!r}, which is not a style')
    check_nesting_is_one_way(grammar)
    if len(grammar.toggles) > MAX_TOGGLES:
        raise GrammarError(
            f'{len(grammar.toggles)} toggles is {2 ** len(grammar.toggles)} '
            f'states, and every state needs a copy of every glyph. Keep it to '
            f'{MAX_TOGGLES}.')
    for toggle in grammar.toggles:
        toggle.guards = [(kind, resolve_class(expr, grammar, cls, toggle))
                         for kind, expr in toggle.guards]
    shapes = []
    for rule in grammar.rules:
        for alt in flatten(rule.expr, grammar, cls):
            shapes.append(shape(rule, list(alt)))
    return shapes, cls
