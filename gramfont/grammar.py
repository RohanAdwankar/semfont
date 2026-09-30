"""Parse a grammar file, and refuse the parts a font cannot run.

The language is an EBNF subset. It is a subset for a reason: an OpenType
`GSUB` feature is a fixed list of lookups, each of which is a finite-state
transducer over the glyph buffer, and composing finite-state transducers
leaves you with a finite-state transducer. So a font recognises exactly the
regular languages. EBNF describes context-free ones. Every production that
needs a stack -- recursion, balanced delimiters, arbitrary nesting -- is
rejected here with the cycle that caused it, rather than compiled into
something that quietly gets the nesting wrong.
"""
import re

BUILTIN = {
    'any': None,            # filled in from the alphabet at expansion time
    'space': set(' '),
    'nonspace': None,
    'word': None,           # letters and digits
    'letter': None,
    'digit': set('0123456789'),
}
# Not classes: they match a position, not a glyph.
ANCHORS = {'line_start'}

STYLE_PROPS = {'font', 'scale', 'color', 'rule', 'from'}


class GrammarError(Exception):
    """A grammar the compiler will not accept, with the line that caused it."""

    def __init__(self, message, line=None):
        super().__init__(f'line {line}: {message}' if line else message)
        self.line = line


# ---------------------------------------------------------------- expressions

class Lit:
    """A literal string. Every character of it is a marker, not content."""

    def __init__(self, text):
        self.text = text


class Ref:
    def __init__(self, name, line):
        self.name, self.line = name, line


class Cat:
    def __init__(self, parts):
        self.parts = parts


class Alt:
    def __init__(self, parts):
        self.parts = parts


class Opt:
    def __init__(self, body):
        self.body = body


class Rep:
    """`{ x }` -- an unbounded run. At most one per alternative."""

    def __init__(self, body):
        self.body = body


# --------------------------------------------------------------------- lexing

TOKEN = re.compile(r'''
      (?P<space>\s+)
    | \(\*(?P<comment>.*?)\*\)
    | \#(?P<hash>[^\n]*)
    | "(?P<string>(?:[^"\\]|\\.)*)"
    | (?P<arrow>->)
    | (?P<name>[A-Za-z_][A-Za-z_0-9]*)
    | (?P<number>-?[0-9]+(?:\.[0-9]+)?)
    | (?P<punct>[=,|\[\]{}();])
''', re.VERBOSE | re.DOTALL)

ESCAPES = {'n': '\n', 't': '\t', '\\': '\\', '"': '"'}


def unescape(text):
    out, i = [], 0
    while i < len(text):
        if text[i] == '\\' and i + 1 < len(text):
            out.append(ESCAPES.get(text[i + 1], text[i + 1]))
            i += 2
        else:
            out.append(text[i])
            i += 1
    return ''.join(out)


def lex(source):
    tokens, pos, line = [], 0, 1
    while pos < len(source):
        m = TOKEN.match(source, pos)
        if not m:
            raise GrammarError(f'cannot read {source[pos]!r}', line)
        line += source.count('\n', pos, m.end())
        pos = m.end()
        kind = m.lastgroup
        if kind in ('space', 'comment', 'hash'):
            continue
        value = m.group(kind)
        tokens.append((kind, unescape(value) if kind == 'string' else value,
                       line - source.count('\n', m.start(), m.end())))
    tokens.append(('end', '', line))
    return tokens


# -------------------------------------------------------------------- parsing

class Rule:
    def __init__(self, name, expr, style, guards, line, keep=False):
        self.name, self.expr, self.style = name, expr, style
        self.guards, self.line, self.keep = guards, line, keep


class Grammar:
    def __init__(self):
        self.alphabet = ''
        self.markers = None     # set by a `markers` declaration, else derived
        self.styles = {}        # name -> {prop: value}
        self.combines = []      # (outer, inner, result) -- one level of nesting
        self.productions = {}   # name -> Expr   (no action)
        self.rules = []         # [Rule]         (has an action)


class Parser:
    def __init__(self, tokens):
        self.tokens, self.i = tokens, 0

    def peek(self, offset=0):
        return self.tokens[min(self.i + offset, len(self.tokens) - 1)]

    def next(self):
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def expect(self, kind, value=None):
        kind_, value_, line = self.next()
        if kind_ != kind or (value is not None and value_ != value):
            want = value if value is not None else kind
            raise GrammarError(f'expected {want!r}, found {value_!r}', line)
        return value_

    def parse(self):
        g = Grammar()
        while self.peek()[0] != 'end':
            kind, value, line = self.peek()
            if kind != 'name':
                raise GrammarError(f'expected a declaration, found {value!r}', line)
            if value == 'alphabet':
                self.next()
                self.expect('punct', '=')
                g.alphabet += expand_ranges(self.expect('string'))
                self.expect('punct', ';')
            elif value == 'markers':
                self.next()
                self.expect('punct', '=')
                g.markers = set(expand_ranges(self.expect('string')))
                self.expect('punct', ';')
            elif value == 'combine':
                self.next()
                outer = self.expect('name')
                self.expect('punct', ',')
                inner = self.expect('name')
                self.expect('punct', '=')
                g.combines.append((outer, inner, self.expect('name')))
                self.expect('punct', ';')
            elif value == 'style':
                self.next()
                name = self.expect('name')
                self.expect('punct', '=')
                g.styles[name] = self.parse_style_props(line)
                self.expect('punct', ';')
            else:
                self.parse_production(g)
        if not g.alphabet:
            raise GrammarError('no alphabet declared')
        return g

    def parse_style_props(self, line):
        props = {}
        while True:
            key = self.expect('name')
            if key not in STYLE_PROPS:
                raise GrammarError(
                    f'unknown style property {key!r}; '
                    f'known ones are {", ".join(sorted(STYLE_PROPS))}', line)
            kind, value, _ = self.next()
            if kind == 'number':
                value = float(value)
            elif kind != 'string' and kind != 'name':
                raise GrammarError(f'{key} needs a value, found {value!r}', line)
            props[key] = value
            if self.peek()[1] != ',':
                return props
            self.next()

    def parse_production(self, g):
        name, line = self.peek()[1], self.peek()[2]
        self.next()
        self.expect('punct', '=')
        expr = self.parse_alt()
        style, guards, keep = None, [], False
        if self.peek()[0] == 'arrow':
            self.next()
            style = self.expect('name')
            if self.peek()[1] == 'keep':
                # A diff marker is part of the line. A Markdown one is not.
                self.next()
                keep = True
        while self.peek()[1] == 'unless':
            self.next()
            guards.append(self.parse_guard())
        self.expect('punct', ';')
        if style is None:
            if guards:
                raise GrammarError('a guard needs a style to guard', line)
            if name in g.productions:
                raise GrammarError(f'{name} is declared twice', line)
            g.productions[name] = expr
        else:
            g.rules.append(Rule(name, expr, style, guards, line, keep))

    def parse_guard(self):
        kind = self.expect('name')
        if kind not in ('preceded_by', 'starts_with'):
            raise GrammarError(
                f'unknown guard {kind!r}; use preceded_by or starts_with',
                self.peek()[2])
        return (kind, self.parse_atom())

    def parse_alt(self):
        parts = [self.parse_cat()]
        while self.peek()[1] == '|':
            self.next()
            parts.append(self.parse_cat())
        return parts[0] if len(parts) == 1 else Alt(parts)

    def parse_cat(self):
        parts = [self.parse_atom()]
        while self.peek()[1] == ',':
            self.next()
            parts.append(self.parse_atom())
        return parts[0] if len(parts) == 1 else Cat(parts)

    def parse_atom(self):
        kind, value, line = self.next()
        if kind == 'string':
            return Lit(value)
        if kind == 'name':
            return Ref(value, line)
        if value == '[':
            body = self.parse_alt()
            self.expect('punct', ']')
            return Opt(body)
        if value == '{':
            body = self.parse_alt()
            self.expect('punct', '}')
            return Rep(body)
        if value == '(':
            body = self.parse_alt()
            self.expect('punct', ')')
            return body
        raise GrammarError(f'expected a pattern, found {value!r}', line)


def expand_ranges(text):
    """`a-z` in an alphabet literal means the range, as in a character class."""
    out, i = [], 0
    while i < len(text):
        if i + 2 < len(text) and text[i + 1] == '-' and text[i + 2] != '-':
            out += [chr(c) for c in range(ord(text[i]), ord(text[i + 2]) + 1)]
            i += 3
        else:
            out.append(text[i])
            i += 1
    return ''.join(dict.fromkeys(out))


def parse(source):
    return Parser(lex(source)).parse()


# ------------------------------------------------------- the regularity check

def literals(expr):
    """Every character that appears in a literal anywhere in an expression.

    These are the grammar's syntax, not its text. They are held out of every
    character class, which is what stops a style propagating across a closing
    marker and what keeps the marker itself unstyled.
    """
    if isinstance(expr, Lit):
        return set(expr.text)
    if isinstance(expr, (Cat, Alt)):
        return set().union(*(literals(p) for p in expr.parts)) if expr.parts else set()
    if isinstance(expr, (Opt, Rep)):
        return literals(expr.body)
    return set()


def marker_chars(grammar):
    """Which characters are syntax rather than text.

    Declare them, or they are taken from every literal in the grammar. The
    declaration exists because a literal can contain a character that is also
    ordinary text: the space in `"# "` opens a heading and is still a space.
    """
    if grammar.markers is not None:
        return grammar.markers
    found = set()
    for expr in list(grammar.productions.values()) + [r.expr for r in grammar.rules]:
        found |= literals(expr)
    return found


def references(expr):
    if isinstance(expr, Ref):
        return [expr]
    if isinstance(expr, (Cat, Alt)):
        return [r for part in expr.parts for r in references(part)]
    if isinstance(expr, (Opt, Rep)):
        return references(expr.body)
    return []


def check_regular(grammar):
    """Reject any production that refers back to itself, however indirectly.

    A cycle is the whole test. An acyclic set of productions expands to a
    finite expression, which is regular; a cycle needs unbounded memory of how
    deep you are, which a lookup does not have.
    """
    for expr in list(grammar.productions.values()) + [r.expr for r in grammar.rules]:
        for ref in references(expr):
            if ref.name not in grammar.productions and ref.name not in BUILTIN \
                    and ref.name not in ANCHORS:
                raise GrammarError(f'{ref.name} is not defined', ref.line)

    state = {}   # name -> 'open' | 'done'

    def walk(name, path):
        if state.get(name) == 'open':
            cycle = ' -> '.join(path[path.index(name):] + [name])
            raise GrammarError(
                f'{name} is defined in terms of itself ({cycle}). A font runs a '
                f'fixed list of substitutions, so it can match regular patterns '
                f'and nothing deeper; recursion needs a stack it does not have. '
                f'Unroll it to a fixed depth, or drop the nesting.')
        if state.get(name) == 'done':
            return
        state[name] = 'open'
        for ref in references(grammar.productions[name]):
            if ref.name in grammar.productions:
                walk(ref.name, path + [name])
        state[name] = 'done'

    for name in grammar.productions:
        walk(name, [])
    for rule in grammar.rules:
        for ref in references(rule.expr):
            if ref.name in grammar.productions:
                walk(ref.name, [rule.name])
    return grammar
