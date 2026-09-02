// The React binding.
//
// Written with createElement rather than JSX on purpose: the package has no
// build step and no dependency beyond React itself, so it can be dropped into
// a bundler, a <script type="module">, or a server render unchanged.

import { createElement as h, useEffect, useMemo } from 'react';
import { analyze, summarize } from './analyze.js';
import { themes, baseTheme, styleFor } from './theme.js';

const ALL_CHANNELS = ['valence', 'salience', 'surprise', 'certainty'];

function resolveTheme(theme) {
  if (!theme) return baseTheme;
  if (typeof theme === 'string') return themes[theme] ?? baseTheme;
  return { ...baseTheme, ...theme, thresholds: { ...baseTheme.thresholds, ...theme.thresholds } };
}

/**
 * Score `text` and turn it into a list of runs ready to render. Unstyled
 * tokens are coalesced, so a plain paragraph comes back as one string and
 * only the words that actually earned typography get their own element.
 */
export function useSemanticText(text, options = {}) {
  const { theme, lexicon, sensitivity, channels } = options;
  // Themes and lexicons are plain data, so one stringify is a sound cache key
  // and callers do not have to memoize the objects they pass in.
  const key = JSON.stringify([text, theme, lexicon, sensitivity, channels]);

  return useMemo(() => {
    const resolved = resolveTheme(theme);
    const enabled = channels ?? ALL_CHANNELS;
    const result = analyze(text ?? '', { lexicon, sensitivity });

    for (const t of result.tokens) {
      for (const c of ALL_CHANNELS) if (!enabled.includes(c)) t[c] = 0;
    }

    const runs = [];
    let plain = '';
    for (const token of result.tokens) {
      const styled = styleFor(token, resolved);
      if (!styled) { plain += token.text; continue; }
      if (plain) { runs.push({ text: plain }); plain = ''; }
      runs.push({ text: token.text, token, ...styled });
    }
    if (plain) runs.push({ text: plain });

    return { runs, tokens: result.tokens, summary: summarize(result), theme: resolved };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
}

/**
 * Typography that modulates on meaning.
 *
 *   <SemanticText>Everything was fine. Then the migration failed.</SemanticText>
 *
 * @param {object} props
 * @param {string} [props.text] the passage; `children` works too
 * @param {string|object} [props.theme] 'editorial' | 'loud' | 'monochrome', or a theme object
 * @param {object} [props.lexicon] extra entries, per channel, merged over the defaults
 * @param {number} [props.sensitivity] global gain on every score, default 1
 * @param {string[]} [props.channels] which channels may style, default all four
 * @param {string} [props.as] element to render, default 'span'
 * @param {boolean} [props.debug] emit data-* attributes with the scores
 * @param {(summary: object) => void} [props.onAnalyze] passage-level readout
 */
export function SemanticText({
  text,
  children,
  theme,
  lexicon,
  sensitivity,
  channels,
  as = 'span',
  debug = false,
  onAnalyze,
  className,
  style,
  ...rest
}) {
  const source = typeof text === 'string' ? text : childrenToString(children);
  const { runs, summary } = useSemanticText(source, { theme, lexicon, sensitivity, channels });

  useEffect(() => {
    if (onAnalyze) onAnalyze(summary);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [summary]);

  return h(
    as,
    { className, style, ...rest },
    runs.map((run, i) => {
      if (!run.token) return run.text;
      const props = { key: i, style: run.style };
      if (debug) {
        props['data-valence'] = run.token.valence.toFixed(2);
        props['data-salience'] = run.token.salience.toFixed(2);
        props['data-surprise'] = run.token.surprise.toFixed(2);
        props['data-certainty'] = run.token.certainty.toFixed(2);
      }
      return h('span', props, run.text);
    }),
  );
}

function childrenToString(children) {
  if (typeof children === 'string') return children;
  if (typeof children === 'number') return String(children);
  if (Array.isArray(children)) return children.map(childrenToString).join('');
  return '';
}

export default SemanticText;
