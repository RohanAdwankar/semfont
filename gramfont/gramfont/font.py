"""Turn a plan into a font file.

Two halves. One builds a styled copy of every glyph in the alphabet, once per
style the grammar declares. The other writes the `GSUB` rules that decide when
each copy gets used. Nothing else is involved at render time: no script, no
stylesheet, no parser. The shaper does the whole job.
"""
import logging
import math
import os
import unicodedata
import warnings

from fontTools.colorLib.builder import buildCOLR, buildCPAL
from fontTools.feaLib.builder import addOpenTypeFeatures
from fontTools.misc.transform import Transform
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools import subset

from .grammar import GrammarError
from .plan import CONTENT, MARKER, RUN
from .toggles import Machine

NULL = 'gramnull'
BAR_THICKNESS = 0.045
Q = chr(39)   # the FEA mark suffix, kept out of the f-strings


def join(*parts):
    return ' '.join(p for p in parts if p)


def hexcolor(text):
    text = text.lstrip('#')
    if len(text) not in (6, 8):
        raise GrammarError(f'{text!r} is not a #rrggbb colour')
    parts = [int(text[i:i + 2], 16) / 255 for i in range(0, len(text), 2)]
    return tuple(parts) if len(parts) == 4 else tuple(parts) + (1.0,)


def redraw(glyphset, name, transform=None, bar=None):
    """Copy an outline, optionally transformed, optionally with a bar added."""
    rec = DecomposingRecordingPen(glyphset)
    glyphset[name].draw(rec)
    pen = TTGlyphPen(None)
    rec.replay(TransformPen(pen, transform) if transform else pen)
    if bar:
        x0, y0, x1, y1 = bar
        pen.moveTo((x0, y0))
        pen.lineTo((x0, y1))
        pen.lineTo((x1, y1))
        pen.lineTo((x1, y0))
        pen.closePath()
    return pen.glyph()


class Builder:
    def __init__(self, grammar, shapes, base_path, family='gramfont', font_dir=None,
                 copyright=None, version='1.000'):
        self.grammar, self.shapes, self.family = grammar, shapes, family
        self.copyright, self.version = copyright, version
        # A style names a font file; a bare name is looked for beside the base.
        self.font_dir = font_dir or os.path.dirname(os.path.abspath(base_path))
        self.font = TTFont(base_path)
        self.alphabet = grammar.alphabet
        self.markers = set(getattr(grammar, 'markers', ()))
        self.text = [c for c in grammar.alphabet if c not in self.markers]
        self._subset()
        self.upem = self.font['head'].unitsPerEm
        self.glyf, self.hmtx = self.font['glyf'], self.font['hmtx']
        self.base_order = self.font.getGlyphOrder()[:]
        self.added, self.colr, self.palette = [], {}, []
        self.machine = Machine(self) if grammar.toggles else None

    def _subset(self):
        logging.getLogger('fontTools.subset').setLevel(logging.ERROR)
        options = subset.Options()
        options.layout_features, options.glyph_names = [], False
        options.drop_tables += ['kern']
        # Hinting instructions do not survive being copied into composites and
        # scaled, and a font this size is read on screens that do not need them.
        options.hinting = False
        options.notdef_outline = True
        sub = subset.Subsetter(options=options)
        sub.populate(unicodes=[ord(c) for c in self.alphabet])
        sub.subset(self.font)
        cmap = self.font.getBestCmap()
        missing = [c for c in self.alphabet if ord(c) not in cmap]
        if missing:
            raise GrammarError('the base font has no glyph for '
                               + ' '.join(repr(c) for c in missing))
        self.name = {c: cmap[ord(c)] for c in self.alphabet}

    # ------------------------------------------------------------- the glyphs

    def build_glyphs(self):
        for style, props in self.grammar.styles.items():
            self._build_style(style, props)
        pen = TTGlyphPen(None)
        self.glyf[NULL] = pen.glyph()
        self.hmtx[NULL] = (0, 0)
        self.added.append(NULL)
        if self.machine:
            self.machine.build()
        self._finish_glyph_order()

    # --------------------------------------------------- glyphs for the states

    def load_face(self, path):
        if not os.path.isabs(path) and not os.path.exists(path):
            path = os.path.join(self.font_dir, path)
        if not os.path.exists(path):
            raise GrammarError(f'no font file at {path}')
        other = TTFont(path)
        return (other.getGlyphSet(), other.getBestCmap(), other['hmtx'],
                other['head'].unitsPerEm)

    def copy_face(self, face, tag):
        """One real outline per character, scaled to this font's em.

        A face that lacks a character the alphabet asks for falls back to the
        base font's glyph for it, with a warning, rather than refusing to
        build: a rare letter missing from one weight should not cost the font.
        """
        source, cmap, hmtx, upem = face
        scale = self.upem / upem
        missing = []
        for char in self.alphabet:
            name = cmap.get(ord(char))
            target = f'{self.name[char]}.{tag}'
            if name is None:
                missing.append(char)
                self.glyf[target] = redraw(self.font.getGlyphSet(), self.name[char])
                self.hmtx[target] = (self.hmtx[self.name[char]][0], 0)
            else:
                self.glyf[target] = redraw(
                    source, name, Transform().scale(scale) if scale != 1 else None)
                self.hmtx[target] = (round(hmtx[name][0] * scale), 0)
            self.added.append(target)
        if missing:
            warnings.warn(
                'a face has no glyph for ' + ' '.join(f'U+{ord(c):04X}' for c in missing)
                + "; the base font's is used instead", stacklevel=2)
        return tag

    def make_bar_unit(self):
        """Bars are shared per advance width, not drawn into every glyph.

        One bar glyph per distinct width is referenced as an untransformed
        component by every ruled state, placed only by a vertical offset.
        Scaling one unit bar would need fewer glyphs, but a scaled component
        is what font validators flag, and the saving is a few dozen outlines.
        """
        self.bars = {}
        return None

    def _bar(self, advance):
        if advance not in self.bars:
            pen = TTGlyphPen(None)
            height = round(self.upem * BAR_THICKNESS)
            pen.moveTo((0, 0))
            pen.lineTo((0, height))
            pen.lineTo((advance, height))
            pen.lineTo((advance, 0))
            pen.closePath()
            name = f'bar{advance}'
            self.glyf[name] = pen.glyph()
            self.hmtx[name] = (advance, 0)
            self.added.append(name)
            self.bars[advance] = name
        return self.bars[advance]

    def make_state_glyphs(self, tag, face_tag, bars, colour, bar_glyph):
        index = None
        if colour:
            index = len(self.palette)
            self.palette.append(hexcolor(colour))
        for char in self.alphabet:
            source = f'{self.name[char]}.{face_tag}'
            advance = self.hmtx[source][0]
            pen = TTGlyphPen(self.glyf.glyphs)
            pen.addComponent(source, (1, 0, 0, 1, 0, 0))
            # A combining accent has no advance, so there is nothing to underline
            # and a zero-width bar would only be a degenerate contour.
            for offset in (bars if advance > 0 else ()):
                pen.addComponent(self._bar(advance), (1, 0, 0, 1, 0,
                                                      round(offset * self.upem)))
            drawn = pen.glyph()
            target = f'{self.name[char]}.{tag}'
            if colour:
                layer = f'{target}.l'
                self.glyf[layer] = drawn
                self.hmtx[layer] = (advance, 0)
                self.added.append(layer)
                self.glyf[target] = TTGlyphPen(None).glyph()
                self.colr[target] = [(layer, index)]
            else:
                self.glyf[target] = drawn
            self.hmtx[target] = (advance, 0)
            self.added.append(target)
        empty = f'null.{tag}'
        self.glyf[empty] = TTGlyphPen(None).glyph()
        self.hmtx[empty] = (0, 0)
        self.added.append(empty)

    def _build_style(self, style, props):
        source, cmap, hmtx, upem = self._source(props)
        scale = float(props.get('scale', 1.0)) * (self.upem / upem)
        bar = props.get('rule')
        colour = props.get('color')
        for c in self.alphabet:
            base = self.name[c]
            target = f'{base}.{style}'
            src_name = cmap.get(ord(c))
            if src_name is None:
                raise GrammarError(
                    f'style {style}: its font has no glyph for {c!r}')
            transform = Transform().scale(scale) if scale != 1 else None
            advance = round(hmtx[src_name][0] * scale)
            box = None
            if bar is not None:
                y = round(float(bar) * self.upem)
                box = (0, y, advance, y + round(self.upem * BAR_THICKNESS))
            self.glyf[target] = redraw(source, src_name, transform, box)
            self.hmtx[target] = (advance, 0)
            self.added.append(target)
        if colour:
            self._paint(style, colour)

    def _source(self, props):
        path = props.get('from') or props.get('font')
        if not path:
            return (self.font.getGlyphSet(), self.font.getBestCmap(),
                    self.font['hmtx'], self.upem)
        if not os.path.isabs(path) and not os.path.exists(path):
            path = os.path.join(self.font_dir, path)
        if not os.path.exists(path):
            raise GrammarError(f'no font file at {path}')
        other = TTFont(path)
        return (other.getGlyphSet(), other.getBestCmap(), other['hmtx'],
                other['head'].unitsPerEm)

    def _paint(self, style, colour):
        """A COLR base glyph cannot be its own layer, so the outline moves to a
        duplicate and the glyph the text uses becomes an empty painted shell."""
        index = len(self.palette)
        self.palette.append(hexcolor(colour))
        for c in self.alphabet:
            target = f'{self.name[c]}.{style}'
            layer = f'{target}l'
            self.glyf[layer] = self.glyf[target]
            self.hmtx[layer] = self.hmtx[target]
            self.added.append(layer)
            self.glyf[target] = TTGlyphPen(None).glyph()
            self.colr[target] = [(layer, index)]

    def _finish_glyph_order(self):
        order = self.base_order + [g for g in self.added if g not in self.base_order]
        assert len(order) == len(set(order)) == len(self.glyf.glyphs)
        self.font.setGlyphOrder(order)
        self.glyf.glyphOrder = order
        self.font['maxp'].numGlyphs = len(order)
        if self.colr:
            self.font['COLR'] = buildCOLR(self.colr)
            self.font['CPAL'] = buildCPAL([self.palette])

    # -------------------------------------------------------------- the rules

    def glyphs(self, chars):
        return [self.name[c] for c in self.alphabet if c in chars]

    def cls(self, chars):
        return '[%s]' % ' '.join(self.glyphs(chars))

    def styled(self, style, chars=None):
        return '[%s]' % ' '.join(f'{g}.{style}'
                                 for g in self.glyphs(chars or set(self.text)))

    def feature(self):
        lines = []
        lines.append(f'@Any = {self.cls(set(self.text))};')
        lines.append(f'@All = {self.cls(set(self.alphabet))};')
        for style in self.grammar.styles:
            # Two classes per style: the text glyphs, which is what a context
            # matches on, and every glyph, which is what the lookup can write.
            # A kept marker is only ever styled by the second one.
            lines.append(f'@Any_{style} = {self.styled(style)};')
            lines.append(f'@All_{style} = {self.styled(style, set(self.alphabet))};')
            lines.append(f'lookup TO_{style} {{ sub @All by @All_{style}; }} TO_{style};')

        # Two things fix the order. A style something nests inside has to run
        # first, or the inner rule consumes the text before the outer one sees
        # it. Otherwise a longer opener goes before a shorter one that prefixes
        # it, or `**` never fires because `*` already took the position.
        depth = self._nesting_depth()
        ordered = sorted(enumerate(self.shapes),
                         key=lambda pair: (depth.get(pair[1].rule.style, 0),
                                           -len(pair[1].prefix), pair[0]))
        names = []
        for index, shape in ordered:
            name = f'R{index}'
            names.append(name)
            lines.append(f'lookup {name} {{')
            lines += ['  ' + rule for rule in self._rules(shape)]
            lines.append(f'}} {name};')
        # Writing a combined style means reading a glyph that is already
        # styled, so each combination needs its own substitution lookup.
        for outer, _, result in self.grammar.combines:
            lines.append(f'lookup TO_{result}_in_{outer} '
                         f'{{ sub @All_{outer} by @All_{result}; }} TO_{result}_in_{outer};')
        # One level of nesting, unrolled. The outer span has already styled
        # everything between its markers, the inner marker included, so this
        # pass only upgrades a sub-range of it to the combined style.
        for outer, inner, result in self.grammar.combines:
            for index, shape in ordered:
                if shape.rule.style != inner or not shape.spans:
                    continue
                name = f'N{outer}_{index}_{result}'
                names.append(name)
                lines.append(f'lookup {name} {{')
                lines += ['  ' + rule for rule
                          in self._rules(shape, host=outer, style=result,
                                         writer=f'TO_{result}_in_{outer}')]
                lines.append(f'}} {name};')
        lines.append('feature calt {')
        lines += [f'  lookup {name};' for name in names]
        lines.append('} calt;')
        lines += self._hide(ordered)
        if self.machine:
            lines += self.machine.lines()
        return '\n'.join(lines) + '\n'

    def _rules(self, shape, host=None, style=None, writer=None):
        """The substitutions for one alternative.

        With `host` set, the same pattern is emitted again over glyphs the
        outer span has already styled, writing the combined style instead.
        """
        style = style or shape.rule.style
        writer = writer or f'TO_{style}'
        suffix_of = (lambda g: f'{g}.{host}') if host else (lambda g: g)
        chars_cls = ((lambda cs: self.styled(host, cs)) if host else self.cls)
        prefix = [suffix_of(self.name[next(iter(a.chars))]) for a in shape.prefix]
        seed_chars = set(shape.body[0].chars)
        backtracks = []
        for kind, chars in shape.rule.guards:
            if kind == 'preceded_by':
                backtracks.append(chars_cls(chars))
            else:
                seed_chars -= chars
        if not seed_chars:
            raise GrammarError(
                f'{shape.rule.name}: the guards rule out every character the '
                f'pattern could start with', shape.rule.line)
        if shape.line_start and not host:
            # OpenType has no line anchor. A shaping run stops at a newline, so
            # "there is nothing to backtrack over" is the same test.
            backtracks.append('@All')
        # A style that carries across markers has to recognise its own styled
        # markers as backtrack too, or the run stops at the first one.
        carries = bool(host) or self._hosts_a_nest(shape.rule.style)
        behind = f'@All_{style}' if carries else f'@Any_{style}'
        # The closing marker looks exactly like the opening one. Without this
        # the rule re-seeds on it and the span never ends.
        backtracks.append(behind)

        seed = chars_cls(seed_chars)
        rules = [join('ignore sub', back, *prefix, seed + Q) + ';'
                 for back in backtracks]
        if shape.spans:
            if carries and shape.suffix:
                # Carrying the style across a marker means the closing one has
                # to be excluded by name, or the span runs to the end of the
                # line instead of stopping there.
                closer = [suffix_of(self.name[next(iter(a.chars))])
                          for a in shape.suffix]
                # A closing marker can also be the start of a longer opening
                # one: `*` ends emphasis and begins `**`. Carry the style over
                # the longer form first, so the nested rule still sees it.
                for longer in self._longer_openers(shape):
                    glyphs = [f'{suffix_of(self.name[c])}{Q} lookup {writer}'
                              for c in longer]
                    rules.append(join('sub', behind, *glyphs) + ';')
                rules.append(join('ignore sub', behind,
                                  closer[0] + Q, *closer[1:]) + ';')
            rules.append(join('sub', *prefix, seed + Q, f'lookup {writer}') + ';')
            over = f'@All_{host}' if host else ('@All' if carries else '@Any')
            rules.append(f'sub {behind} {over}{Q} lookup {writer};')
        else:
            marked = [f'{chars_cls(a.chars)}{Q} lookup {writer}' for a in shape.body]
            tail = [suffix_of(self.name[next(iter(a.chars))]) for a in shape.suffix]
            rules.append(join('sub', *prefix, *marked, *tail) + ';')
        return rules

    def _nesting_depth(self):
        """How deep a style sits: an outer style is 0, what nests in it is 1."""
        inside = {}
        for outer, inner, _ in self.grammar.combines:
            inside.setdefault(inner, set()).add(outer)
        depth = {}

        def of(style):
            if style not in depth:
                depth[style] = 0    # guards against a cycle plan already refused
                depth[style] = max((of(o) + 1 for o in inside.get(style, ())),
                                   default=0)
            return depth[style]

        for style in self.grammar.styles:
            of(style)
        return depth

    def _longer_openers(self, shape):
        """Other rules' opening markers that begin with this one's closer."""
        closer = tuple(next(iter(a.chars)) for a in shape.suffix)
        found = []
        for other in self.shapes:
            opener = tuple(next(iter(a.chars)) for a in other.prefix)
            if len(opener) > len(closer) and opener[:len(closer)] == closer:
                found.append(opener)
        return sorted(set(found), key=len, reverse=True)

    def _hosts_a_nest(self, style):
        return any(outer == style for outer, _, _ in self.grammar.combines)

    def _hide(self, ordered):
        """A marker is only a marker once it has actually styled something.

        Hiding it unconditionally is what eats the asterisks in `2 * 3` and the
        hash in `C#`. Keying the substitution on a styled neighbour leaves every
        delimiter that styled nothing on the page, where it belongs.
        """
        markers = sorted({c for shape in self.shapes if not shape.rule.keep
                          for atom in shape.prefix + shape.suffix
                          for c in atom.chars})
        hide, styled_markers = [], set()
        combos = self.grammar.combines

        def emit(shape, style, host):
            dot = (lambda g: f'{g}.{host}') if host else (lambda g: g)
            for part, template in ((shape.prefix, '  sub {} @Any_{};'),
                                   (shape.suffix, '  sub @Any_{1} {0};')):
                if not part:
                    continue
                for atom in part:
                    if host:
                        styled_markers.add(dot(self.name[next(iter(atom.chars))]))
                marked = ' '.join(f'{dot(self.name[next(iter(a.chars))])}{Q} lookup TO_NULL'
                                  for a in part)
                hide.append(template.format(marked, style))

        for _, shape in ordered:
            if shape.rule.keep:
                continue
            emit(shape, shape.rule.style, None)
            # An outer span can end on a nested run, so its closing marker has
            # to be hidden after the combined style too.
            for outer, inner, result in combos:
                if shape.rule.style == outer and shape.suffix:
                    emit(shape, result, None)
                if shape.rule.style == inner and shape.spans:
                    emit(shape, result, outer)
        lines = []
        if hide:
            lines.append('lookup TO_NULL {')
            lines += [f'  sub {self.name[c]} by {NULL};' for c in markers]
            lines += [f'  sub {g} by {NULL};' for g in sorted(styled_markers)]
            lines.append('} TO_NULL;')
            lines.append('lookup HIDE {')
            lines += hide
            lines.append('} HIDE;')
            lines.append('feature calt { lookup HIDE; } calt;')

        # A kept marker is part of the text, so it takes the style too. This
        # runs after the spans are settled, keyed on a styled neighbour for the
        # same reason the hide pass is.
        kept = []
        for _, shape in ordered:
            if not shape.rule.keep or not shape.prefix:
                continue
            style = shape.rule.style
            opening = ' '.join(
                f'{self.name[next(iter(a.chars))]}{Q} lookup TO_{style}'
                for a in shape.prefix)
            kept.append(f'  sub {opening} @Any_{style};')
        if kept:
            lines.append('lookup MARK {')
            lines += kept
            lines.append('} MARK;')
            lines.append('feature calt { lookup MARK; } calt;')
        return lines

    # ------------------------------------------------------------------ output

    def _finish(self):
        """What a font needs to pass a foundry's checks, none of it grammar.

        Vertical metrics are taken from the glyphs actually drawn, because a
        heading scaled 1.5x reaches well above the base font's ascender and a
        window that clips it shows up as cut-off headings on Windows.
        """
        from fontTools.pens.boundsPen import BoundsPen
        from fontTools.ttLib import newTable
        from fontTools.ttLib.tables import ttProgram
        font = self.font
        glyphs = font.getGlyphSet()
        top, bottom = 0, 0
        for name in font.getGlyphOrder():
            pen = BoundsPen(glyphs)
            glyphs[name].draw(pen)
            if pen.bounds:
                bottom, top = min(bottom, pen.bounds[1]), max(top, pen.bounds[3])
        os2, hhea = font['OS/2'], font['hhea']
        # Line spacing starts as the base font's. Google wants the three metrics
        # to add up to at least 1.2 em, and a base font drawn for tighter lines
        # is padded to it, evenly above and below. The clipping window below is
        # separate, and is what stops scaled headings being cut off.
        ascent, descent = hhea.ascent, hhea.descent
        shortfall = math.ceil(1.2 * self.upem) - (ascent - descent)
        if shortfall > 0:
            ascent += shortfall - shortfall // 2
            descent -= shortfall // 2
        hhea.ascent, hhea.descent = ascent, descent
        hhea.lineGap = 0
        os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = ascent, descent, 0
        os2.usWinAscent, os2.usWinDescent = max(ascent, top), max(-descent, -bottom)
        os2.version = max(os2.version, 4)   # bit 7 is undefined before version 4
        os2.fsSelection |= 1 << 7   # USE_TYPO_METRICS
        # With hinting gone, smart dropout keeps thin strokes from vanishing.
        font['gasp'] = newTable('gasp')
        font['gasp'].version = 1
        font['gasp'].gaspRange = {0xFFFF: 0x000F}
        prep = newTable('prep')
        prep.program = ttProgram.Program()
        prep.program.fromBytecode(bytes([0xb8, 0x01, 0xff, 0x85, 0xb0, 0x04, 0x8d]))
        font['prep'] = prep
        self._ensure_notdef()
        os2.recalcAvgCharWidth(font)
        self._declare_scripts()

    def _set_names(self):
        """Names a font distributed on its own has to carry.

        With `copyright` the notice is replaced by exactly that text, so it
        has to carry the base font's own notice as well: every licence worth
        using requires it. Without `copyright` the base font's notice is left
        as it was.
        """
        table = self.font['name']
        ps = self.family.replace(' ', '') + '-Regular'
        names = {1: self.family, 2: 'Regular', 3: f'{self.version};{ps}',
                 4: f'{self.family} Regular', 5: f'Version {self.version}', 6: ps}
        if self.copyright:
            names[0] = self.copyright.strip()
            names[13] = ('This Font Software is licensed under the SIL Open Font License, '
                         'Version 1.1. This license is available with a FAQ at: '
                         'https://openfontlicense.org')
            names[14] = 'https://openfontlicense.org'
        for name_id, value in names.items():
            table.setName(value, name_id, 3, 1, 0x409)
        self.font['head'].fontRevision = float(self.version)

    def _declare_scripts(self):
        """Say which scripts the font is for, so a shaper does not have to guess.

        Read off the alphabet: a font whose letters are Latin declares Latn.
        """
        from fontTools.ttLib import newTable
        scripts = set()
        for char in self.alphabet:
            name = unicodedata.name(char, '')
            if name.startswith('LATIN') and char.isalpha():
                scripts.add('Latn')
        if scripts:
            tags = ','.join(sorted(scripts))
            table = newTable('meta')
            table.data = {'dlng': tags, 'slng': tags}
            self.font['meta'] = table

    def _ensure_notdef(self):
        glyph = self.glyf['.notdef']
        if glyph.numberOfContours != 0:
            return
        em = self.upem
        pen = TTGlyphPen(None)
        for inset, clockwise in ((0.08, True), (0.14, False)):
            a, b = round(em * inset), round(em * (0.72 - inset * 0.2))
            c = round(em * 0.45)
            pts = [(a, 0), (a, b), (c, b), (c, 0)]
            for i, pt in enumerate(pts if clockwise else pts[::-1]):
                (pen.moveTo if i == 0 else pen.lineTo)(pt)
            pen.closePath()
        self.glyf['.notdef'] = pen.glyph()
        self.hmtx['.notdef'] = (round(em * 0.5), 0)

    def save(self, path, fea_path=None):
        fea = self.feature()
        fea_path = fea_path or os.path.splitext(path)[0] + '.fea'
        with open(fea_path, 'w', encoding='utf-8') as handle:
            handle.write(fea)
        addOpenTypeFeatures(self.font, fea_path)
        self._finish()
        self._set_names()
        self.font.save(path)
        woff2 = os.path.splitext(path)[0] + '.woff2'
        self.font.flavor = 'woff2'
        self.font.save(woff2)
        self.font.flavor = None
        return path, woff2, fea_path
