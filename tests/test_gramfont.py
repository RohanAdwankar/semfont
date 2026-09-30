"""What the compiler accepts, what it refuses, and what the font then does."""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gramfont import Builder, GrammarError, check_regular, parse, plan  # noqa: E402

LIBERATION = Path('/usr/share/fonts/truetype/liberation')
BASE = LIBERATION / 'LiberationSans-Regular.ttf'

HEAD = 'alphabet = "a-z *";\nmarkers = "*";\nstyle bold = from "%s";\n' % (
    LIBERATION / 'LiberationSans-Bold.ttf')


def build(source):
    return plan(check_regular(parse(HEAD + source)))


class GrammarTest(unittest.TestCase):
    def test_a_recursive_production_is_refused_with_its_cycle(self):
        """The whole reason the language is a subset. A font runs a fixed list
        of finite-state lookups, so nesting to arbitrary depth is not on."""
        with self.assertRaises(GrammarError) as caught:
            build('nested = "*" , nested , "*";\n'
                  'strong = "*" , nested , "*" -> bold;')
        self.assertIn('nested -> nested', str(caught.exception))
        self.assertIn('stack', str(caught.exception))

    def test_an_indirect_cycle_is_refused_too(self):
        with self.assertRaises(GrammarError) as caught:
            build('a = b;\nb = c;\nc = a;\nr = "*" , a -> bold;')
        self.assertIn('is defined in terms of itself', str(caught.exception))

    def test_an_undefined_name_is_named(self):
        with self.assertRaises(GrammarError) as caught:
            build('r = "*" , mystery -> bold;')
        self.assertIn('mystery is not defined', str(caught.exception))

    def test_a_pattern_with_no_opener_is_refused(self):
        with self.assertRaises(GrammarError) as caught:
            build('r = { any } -> bold;')
        self.assertIn('nothing in front', str(caught.exception))

    def test_two_unbounded_runs_are_refused(self):
        with self.assertRaises(GrammarError) as caught:
            build('r = "*" , { any } , "*" , { any } -> bold;')
        self.assertIn('two unbounded runs', str(caught.exception))

    def test_repetition_of_more_than_one_class_is_refused(self):
        with self.assertRaises(GrammarError) as caught:
            build('r = "*" , { letter , digit } -> bold;')
        self.assertIn('single character class', str(caught.exception))

    def test_alternation_expands_into_one_shape_each(self):
        shapes, _ = build('r = ( "*" | "**" ) , { any } -> bold;')
        self.assertEqual(sorted(len(s.prefix) for s in shapes), [1, 2])

    def test_an_optional_part_expands_both_ways(self):
        shapes, _ = build('r = "*" , [ "*" ] , { any } -> bold;')
        self.assertEqual(sorted(len(s.prefix) for s in shapes), [1, 2])

    def test_a_marker_character_is_held_out_of_every_class(self):
        """A class that contained the closing delimiter would style straight
        through it and the span would never end."""
        _, classes = build('r = "*" , { any } , "*" -> bold;')
        self.assertNotIn('*', classes['any'])
        self.assertIn('a', classes['any'])

    def test_nesting_both_ways_is_refused(self):
        """Whichever lookup runs first would win every time, which renders
        wrong rather than rendering nothing."""
        extra = 'style em = from "%s";\nstyle both = from "%s";\n' % (
            LIBERATION / 'LiberationSans-Italic.ttf',
            LIBERATION / 'LiberationSans-BoldItalic.ttf')
        with self.assertRaises(GrammarError) as caught:
            build(extra + 'combine bold , em = both;\ncombine em , bold = both;\n'
                  'r = "*" , { any } , "*" -> bold;')
        self.assertIn('nests inside itself', str(caught.exception))

    def test_guards_narrow_the_seed_rather_than_the_whole_class(self):
        shapes, _ = build('r = "*" , { any } , "*" -> bold unless starts_with space;')
        self.assertEqual(shapes[0].rule.guards, [('starts_with', {' '})])


TOGGLE_HEAD = 'alphabet = "a-z *_";\nface = "%s";\nface bold = "%s";\n' % (
    LIBERATION / 'LiberationSans-Regular.ttf', LIBERATION / 'LiberationSans-Bold.ttf')


class ToggleTest(unittest.TestCase):
    def test_too_many_toggles_is_refused_with_the_state_count(self):
        """Every state needs a copy of every glyph, so the states are the
        budget, not the toggles."""
        body = ''.join(f'toggle t{i} = "{c}" -> bold;\n'
                       for i, c in enumerate('abcdefg'))
        with self.assertRaises(GrammarError) as caught:
            plan(check_regular(parse(TOGGLE_HEAD.replace('a-z', 'a-z') + body)))
        self.assertIn('128 states', str(caught.exception))

    def test_a_missing_face_names_the_combination_that_needed_it(self):
        source = (TOGGLE_HEAD + 'toggle bold = "*" -> bold;\n'
                  'toggle em = "_" -> italic;')
        grammar = check_regular(parse(source))
        shapes, _ = plan(grammar)
        with self.assertRaises(GrammarError) as caught:
            Builder(grammar, shapes, str(BASE)).build_glyphs()
        self.assertIn('no face declared for', str(caught.exception))
        self.assertIn('italic', str(caught.exception))

    def test_a_toggle_guard_is_resolved_to_characters(self):
        grammar = check_regular(parse(
            TOGGLE_HEAD + 'toggle bold = "*" -> bold unless preceded_by word;'))
        plan(grammar)
        self.assertEqual(grammar.toggles[0].guards[0][0], 'preceded_by')
        self.assertIn('a', grammar.toggles[0].guards[0][1])
        self.assertNotIn(' ', grammar.toggles[0].guards[0][1])


@unittest.skipUnless(BASE.exists(), 'Liberation fonts are not installed')
class FontTest(unittest.TestCase):
    def compile(self, source):
        grammar = check_regular(parse(HEAD + source))
        shapes, _ = plan(grammar)
        builder = Builder(grammar, shapes, str(BASE))
        builder.build_glyphs()
        return builder

    def test_the_markdown_example_compiles(self):
        source = (ROOT / 'examples' / 'markdown.gram').read_text(encoding='utf-8')
        grammar = check_regular(parse(source))
        shapes, _ = plan(grammar)
        self.assertEqual(len(shapes), 3)   # the three headings; the rest are toggles
        builder = Builder(grammar, shapes, str(BASE))
        builder.build_glyphs()
        self.assertIn('feature calt', builder.feature())

    def test_the_markdown_example_is_a_state_machine_over_its_toggles(self):
        """Five toggles is thirty-two states, and every glyph carries the one
        it is in, which is what makes the depth unlimited."""
        source = (ROOT / 'examples' / 'markdown.gram').read_text(encoding='utf-8')
        grammar = check_regular(parse(source))
        shapes, _ = plan(grammar)
        builder = Builder(grammar, shapes, str(BASE))
        builder.build_glyphs()
        fea = builder.feature()
        self.assertEqual(len(grammar.toggles), 5)
        self.assertIn('@S31 =', fea)
        self.assertNotIn('@S32 =', fea)
        self.assertIn('lookup PRIME', fea)
        self.assertIn('lookup TOGGLE', fea)
        names = set(builder.font.getGlyphOrder())
        self.assertIn('null.s31', names)
        self.assertIn('a.s31', names)

    def test_a_nested_span_reads_the_outer_style_and_writes_the_combined_one(self):
        extra = 'style em = from "%s";\nstyle both = from "%s";\n' % (
            LIBERATION / 'LiberationSans-Italic.ttf',
            LIBERATION / 'LiberationSans-BoldItalic.ttf')
        grammar = check_regular(parse(
            HEAD + extra + 'combine bold , em = both;\n'
            'b = "**" , { any } , "**" -> bold;\n'
            'e = "*" , { any } , "*" -> em;'))
        shapes, _ = plan(grammar)
        builder = Builder(grammar, shapes, str(BASE))
        builder.build_glyphs()
        fea = builder.feature()
        self.assertIn('sub @All_bold by @All_both;', fea)
        self.assertIn('asterisk.bold', fea)
        # The outer span has to carry over the inner marker to reach the text
        # after it, so it reads its own styled markers as backtrack.
        self.assertIn("sub @All_bold @All' lookup TO_bold;", fea)

    def test_the_diff_example_compiles_and_keeps_its_markers(self):
        source = (ROOT / 'examples' / 'diff.gram').read_text(encoding='utf-8')
        grammar = check_regular(parse(source))
        shapes, _ = plan(grammar)
        builder = Builder(grammar, shapes, str(LIBERATION / 'LiberationMono-Regular.ttf'))
        builder.build_glyphs()
        fea = builder.feature()
        self.assertIn('lookup MARK {', fea)
        self.assertNotIn('lookup HIDE', fea)

    def test_the_nested_example_is_the_one_that_is_refused(self):
        source = (ROOT / 'examples' / 'nested.gram').read_text(encoding='utf-8')
        with self.assertRaises(GrammarError) as caught:
            plan(check_regular(parse(source)))
        self.assertIn('defined in terms of itself', str(caught.exception))

    def test_a_kept_marker_is_not_substituted_away(self):
        fea = self.compile('r = "*" , { any } -> bold keep;').feature()
        self.assertNotIn(f'sub asterisk by', fea)
        self.assertIn('lookup MARK {', fea)

    def test_a_span_gets_a_seed_and_a_propagate_rule(self):
        fea = self.compile('r = "*" , { any } , "*" -> bold;').feature()
        self.assertIn('lookup TO_bold;', fea)
        self.assertIn('sub @Any_bold @Any\' lookup TO_bold;', fea)

    def test_the_closing_marker_cannot_re_seed_the_span(self):
        """Without this the second `*` looks exactly like the first one."""
        fea = self.compile('r = "*" , { any } , "*" -> bold;').feature()
        self.assertTrue(any(line.startswith('  ignore sub @Any_bold ')
                            for line in fea.splitlines()))

    def test_a_marker_is_hidden_only_beside_a_styled_glyph(self):
        """An unconditional substitution is what eats the asterisks in 2 * 3."""
        fea = self.compile('r = "*" , { any } , "*" -> bold;').feature()
        hide = fea.split('lookup HIDE {')[1].split('} HIDE;')[0]
        for line in hide.strip().splitlines():
            self.assertIn('@Any_bold', line)

    def test_a_longer_opener_is_emitted_before_a_shorter_one(self):
        fea = self.compile('one = "*" , { any } -> bold;\n'
                           'two = "**" , { any } -> bold;').feature()
        order = [line for line in fea.splitlines() if line.startswith('lookup R')]
        self.assertTrue(order[0].startswith('lookup R1'), order)

    def test_the_font_saves_and_reloads(self):
        import tempfile
        from fontTools.ttLib import TTFont
        builder = self.compile('r = "*" , { any } , "*" -> bold;')
        with tempfile.TemporaryDirectory() as tmp:
            ttf, woff2, _ = builder.save(os.path.join(tmp, 'x.ttf'))
            font = TTFont(ttf)
            self.assertIn('GSUB', font)
            self.assertTrue(os.path.getsize(woff2) > 0)


if __name__ == '__main__':
    unittest.main()
