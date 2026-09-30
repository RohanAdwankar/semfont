"""Toggles: the part of a markup language that is not a bracket.

A closing `**` does not have to be matched with the `**` that opened it. It
turns bold off because bold was on. So emphasis is not nesting in the sense
that needs a stack; it is a set of independent flags, and tracking k flags is
a finite automaton with 2**k states. That fits in a font, at any depth, with
no per-level unrolling.

The state lives in the glyph stream. Every glyph carries the state it is in as
part of its name, a delimiter is replaced by a zero-width glyph carrying the
state after the flip, and one lookup walking left to right reads its own
output as backtrack. That is the whole machine.
"""
import itertools

from .grammar import GrammarError
from .plan import MAX_TOGGLES

Q = chr(39)


def subsets(names):
    for size in range(len(names) + 1):
        for combo in itertools.combinations(names, size):
            yield frozenset(combo)


class Machine:
    def __init__(self, builder):
        self.builder = builder
        self.grammar = builder.grammar
        self.toggles = self.grammar.toggles
        assert len(self.toggles) <= MAX_TOGGLES   # plan() has already said so
        self.by_name = {t.name: t for t in self.toggles}
        self.order = [t.name for t in self.toggles]
        self.states = list(subsets(self.order))
        self.index = {state: i for i, state in enumerate(self.states)}
        self.delims = {t.name: t.delimiter for t in self.toggles}

    # ------------------------------------------------------------- the glyphs

    def face_for(self, state):
        wanted = frozenset().union(*(self.by_name[n].attrs['face'] for n in state)) \
            if state else frozenset()
        if wanted not in self.grammar.faces:
            have = ', '.join(sorted(' '.join(sorted(k)) or '(plain)'
                                    for k in self.grammar.faces)) or 'none'
            raise GrammarError(
                f'no face declared for {" ".join(sorted(wanted)) or "(plain)"}, '
                f'which {" + ".join(sorted(state))} needs. Declared: {have}.')
        return wanted

    def bars_for(self, state):
        return tuple(sorted(offset for name in state
                            for offset in self.by_name[name].attrs['rule']))

    def colour_for(self, state):
        for name in self.order:
            if name in state and self.by_name[name].attrs['color']:
                return self.by_name[name].attrs['color']
        return None

    def build(self):
        b = self.builder
        faces = {key: b.load_face(self.grammar.faces[key])
                 for key in {self.face_for(s) for s in self.states}}
        face_glyphs = {}
        for number, (key, face) in enumerate(sorted(faces.items(), key=lambda kv: sorted(kv[0]))):
            face_glyphs[key] = b.copy_face(face, f'f{number}')
        bar = b.make_bar_unit()
        for state in self.states:
            b.make_state_glyphs(f's{self.index[state]}', face_glyphs[self.face_for(state)],
                                self.bars_for(state), self.colour_for(state), bar)

    # -------------------------------------------------------------- the rules

    def suffix(self, state):
        return f's{self.index[state]}'

    def cls(self, state, chars=None):
        b = self.builder
        chars = set(b.alphabet) if chars is None else chars
        glyphs = [f'{b.name[c]}.{self.suffix(state)}'
                  for c in b.alphabet if c in chars]
        return '[%s]' % ' '.join(glyphs)

    def all_cls(self, state):
        """Every glyph in a state, the zero-width delimiter stand-in included."""
        return '[%s %s]' % (
            ' '.join(f'{self.builder.name[c]}.{self.suffix(state)}'
                     for c in self.builder.alphabet),
            f'null.{self.suffix(state)}')

    def lines(self):
        b = self.builder
        out = []
        base = self.suffix(frozenset())
        # Every glyph starts in the empty state, so that a rule never has to
        # ask whether there is a glyph behind it.
        out.append(f'@Plain = {b.cls(set(b.alphabet))};')
        out.append(f'lookup PRIME {{ sub @Plain by {self.cls(frozenset())}; }} PRIME;')
        out.append('feature calt { lookup PRIME; } calt;')
        for state in self.states:
            out.append(f'@S{self.index[state]} = {self.all_cls(state)};')
            out.append(f'lookup TO_{self.suffix(state)} '
                       f'{{ sub {self.cls(frozenset())} by {self.cls(state)}; }} '
                       f'TO_{self.suffix(state)};')
            out.append(f'lookup NULL_{self.suffix(state)} '
                       f'{{ sub @Plain by null.{self.suffix(state)}; '
                       f'sub {self.cls(frozenset())} by null.{self.suffix(state)}; }} '
                       f'NULL_{self.suffix(state)};')
        styled = ' '.join(f'@S{self.index[s]}' for s in self.states if s)
        out.append(f'@Styled = [{styled}];')

        rules = []
        for state in self.states:
            rules += self._state_rules(state, backtrack=f'@S{self.index[state]}')
        # Nothing behind the first glyph of a line, so the empty state's
        # transitions need a copy with no backtrack. They go last, after every
        # rule that does have one.
        rules.append(f'ignore sub @Styled {self._any_delim()}{Q};')
        rules += self._state_rules(frozenset(), backtrack=None)
        out.append('lookup TOGGLE {')
        out += ['  ' + rule for rule in rules]
        out.append('} TOGGLE;')
        out.append('feature calt { lookup TOGGLE; } calt;')
        return out

    def _any_delim(self):
        b = self.builder
        first = {t.delimiter[0] for t in self.toggles}
        return '[%s]' % ' '.join(f'{b.name[c]}.{self.suffix(frozenset())}'
                                 for c in sorted(first))

    def _state_rules(self, state, backtrack):
        """One state's transitions, longest delimiter first, then the carry."""
        b, out = self.builder, []
        base = self.suffix(frozenset())
        space = {c for c in b.alphabet if c.isspace()}
        for toggle in sorted(self.toggles, key=lambda t: -len(t.delimiter)):
            target = state ^ {toggle.name}
            glyphs = [f'{b.name[c]}.{base}' for c in toggle.delimiter]
            marked = ' '.join(f'{g}{Q} lookup NULL_{self.suffix(target)}' for g in glyphs)
            if toggle.name in state:
                # Closing. CommonMark wants a non-space before it, which is
                # also what stops `2 * 3` from closing anything.
                if backtrack is None:
                    continue
                # A hidden delimiter is not a space. Leaving `null` out here
                # is what stopped `**bold ~~struck~~**` from closing: the
                # glyph behind the final `**` is the one the `~~` became.
                behind = '[%s %s]' % (
                    self.cls(state, set(b.alphabet) - space)[1:-1],
                    f'null.{self.suffix(state)}')
                out.append(f'sub {behind} {marked};')
                continue
            # Opening. A space after it opens nothing, and neither does a
            # repeat of its own first character, which is what keeps `**` from
            # being read as two `*`.
            ahead = self.cls(frozenset(),
                             set(b.alphabet) - space - {toggle.delimiter[0]})
            for kind, chars in toggle.guards:
                if kind == 'preceded_by' and backtrack is not None:
                    out.append(f'ignore sub {self.cls(state, chars)} '
                               f'{glyphs[0]}{Q} {" ".join(glyphs[1:])};')
                elif kind == 'starts_with':
                    ahead = self.cls(frozenset(),
                                     set(b.alphabet) - space - chars
                                     - {toggle.delimiter[0]})
            out.append(' '.join(x for x in ('sub', backtrack, marked, ahead + ';') if x))
        if state:
            out.append(f'sub @S{self.index[state]} {self.cls(frozenset())}{Q} '
                       f'lookup TO_{self.suffix(state)};')
        return out
