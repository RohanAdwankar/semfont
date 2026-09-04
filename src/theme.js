// Channels in, typography out.
//
// A theme is data: a threshold per channel, below which a token is left
// completely alone, and a `map` of rows saying which channel drives which
// rendering. Rows are independent and additive, so "how many modulation
// options do you want" is answered by how many rows you write. Adding one
// costs an arithmetic step per styled token: for a page of prose the whole
// map runs in about 0.2ms against 1.4ms of scoring, so the ceiling here is
// legibility rather than speed.
//
// Colour is expressed with color-mix against `currentColor`, so text stays
// legible in light and dark without the theme knowing which it is in.

const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);

/** How far past its threshold a score got, on a fresh 0..1 scale. */
const past = (value, threshold) =>
  clamp01((Math.abs(value) - threshold) / (1 - threshold));

// Each renderer takes the strength (0..1, already past the threshold), the
// signed score, the row's own options, and the accumulating style and axes.
// A renderer that touches a variable axis writes to `axes`; the caller turns
// those into one font-variation-settings declaration at the end.
export const renderers = {
  color(strength, signed, row, style) {
    const accent = signed < 0 ? row.negative : row.positive;
    if (!accent) return;
    style.color = `color-mix(in oklab, currentColor, ${accent} ${Math.round(strength * (row.max ?? 0.85) * 100)}%)`;
  },
  weight(strength, signed, row, style, axes) {
    const wght = Math.round((row.base ?? 400) + strength * (row.range ?? 300));
    axes.wght = wght;
    style.fontWeight = wght;
  },
  size(strength, signed, row, style) {
    style.fontSize = `${(1 + strength * (row.range ?? 0.13)).toFixed(3)}em`;
  },
  highlight(strength, signed, row, style) {
    const paint = `color-mix(in oklab, transparent, ${row.color} ${Math.round(strength * (row.max ?? 0.42) * 100)}%)`;
    style.background = paint;
    style.borderRadius = '0.18em';
    style.boxShadow = `0 0 0 0.12em ${paint}`;
  },
  slant(strength, signed, row, style, axes) {
    axes.slnt = (axes.slnt ?? 0) + strength * (row.max ?? -9);
  },
  tracking(strength, signed, row, style) {
    style.letterSpacing = `${(strength * (row.max ?? -0.012)).toFixed(4)}em`;
  },
  fade(strength, signed, row, style) {
    style.opacity = (1 - strength * (row.max ?? 0.28)).toFixed(3);
  },
  underline(strength, signed, row, style) {
    style.textDecoration = 'underline';
    style.textDecorationThickness = `${(0.03 + strength * (row.max ?? 0.06)).toFixed(3)}em`;
    style.textUnderlineOffset = '0.16em';
    if (row.style) style.textDecorationStyle = row.style;
  },
  // Recursive's own axes. MONO shifts proportional letterforms toward
  // monospace and CASL toward its casual, single-storey shapes; CRSV swaps in
  // true cursive forms. They reflow, so they suit signals that are rare in a
  // passage rather than ones that fire on every other word.
  mono(strength, signed, row, style, axes) { axes.MONO = strength * (row.max ?? 1); },
  casual(strength, signed, row, style, axes) { axes.CASL = strength * (row.max ?? 1); },
  cursive(strength, signed, row, style, axes) { axes.CRSV = strength * (row.max ?? 1); },
};

const EDITORIAL_MAP = [
  { channel: 'valence', render: 'color', negative: 'oklch(0.58 0.19 25)', positive: 'oklch(0.55 0.13 155)', max: 0.85 },
  { channel: 'salience', render: 'weight', base: 400, range: 300 },
  { channel: 'salience', render: 'size', range: 0.13 },
  { channel: 'surprise', render: 'highlight', color: 'oklch(0.85 0.16 92)', max: 0.42 },
  { channel: 'certainty', render: 'slant', side: 'negative', max: -9 },
  { channel: 'certainty', render: 'fade', side: 'negative', max: 0.28 },
  { channel: 'certainty', render: 'tracking', side: 'positive', max: -0.012 },
];

export const baseTheme = {
  name: 'editorial',
  thresholds: { valence: 0.2, salience: 0.3, surprise: 0.35, certainty: 0.35, technicality: 0.5 },
  map: EDITORIAL_MAP,
  variableAxes: true,
};

export const themes = {
  editorial: baseTheme,

  // Everything turned up, for a demo or a headline.
  loud: {
    name: 'loud',
    thresholds: { valence: 0.1, salience: 0.18, surprise: 0.22, certainty: 0.25, technicality: 0.4 },
    variableAxes: true,
    map: [
      { channel: 'valence', render: 'color', negative: 'oklch(0.55 0.24 27)', positive: 'oklch(0.52 0.17 150)', max: 1 },
      { channel: 'salience', render: 'weight', base: 380, range: 480 },
      { channel: 'salience', render: 'size', range: 0.34 },
      { channel: 'surprise', render: 'highlight', color: 'oklch(0.85 0.19 92)', max: 0.7 },
      { channel: 'certainty', render: 'slant', side: 'negative', max: -14 },
      { channel: 'certainty', render: 'fade', side: 'negative', max: 0.35 },
      { channel: 'certainty', render: 'tracking', side: 'positive', max: -0.02 },
    ],
  },

  // No colour at all: weight, size, slant and tracking carry every channel.
  // Print, e-ink, and the honest answer to "colour is not an accessible
  // channel on its own".
  monochrome: {
    name: 'monochrome',
    thresholds: { valence: 0.2, salience: 0.3, surprise: 0.35, certainty: 0.35, technicality: 0.5 },
    variableAxes: true,
    map: [
      { channel: 'valence', render: 'slant', side: 'negative', max: 8 },
      { channel: 'salience', render: 'weight', base: 380, range: 400 },
      { channel: 'salience', render: 'size', range: 0.18 },
      { channel: 'surprise', render: 'underline', max: 0.06 },
      { channel: 'certainty', render: 'slant', side: 'negative', max: -9 },
      { channel: 'certainty', render: 'fade', side: 'negative', max: 0.28 },
      { channel: 'certainty', render: 'tracking', side: 'positive', max: -0.02 },
    ],
  },

  // Five channels on five axes, two of them Recursive's own. Technical tokens
  // shift toward monospace and hedges toward the casual letterforms, which is
  // as far as this goes before a paragraph stops having a normal state to
  // contrast against.
  technical: {
    name: 'technical',
    thresholds: { valence: 0.2, salience: 0.3, surprise: 0.35, certainty: 0.35, technicality: 0.45 },
    variableAxes: true,
    map: [
      ...EDITORIAL_MAP,
      { channel: 'technicality', render: 'mono', max: 1 },
      { channel: 'certainty', render: 'casual', side: 'negative', max: 0.8 },
    ],
  },
};

/**
 * Turn one scored token into a style object (React-shaped, camelCase) plus
 * the raw axis values, for callers that would rather drive a variable font
 * themselves.
 *
 * Returns null when the token said nothing worth setting differently.
 */
export function styleFor(token, theme = baseTheme) {
  if (token.kind !== 'word' && token.kind !== 'number') return null;
  const style = {};
  const axes = {};
  let touched = false;

  for (const row of theme.map) {
    const signed = token[row.channel];
    if (signed === undefined) continue;
    if (row.side === 'negative' && signed >= 0) continue;
    if (row.side === 'positive' && signed <= 0) continue;
    const strength = past(signed, theme.thresholds[row.channel] ?? 0.3);
    if (strength <= 0) continue;
    const render = renderers[row.render];
    if (!render) continue;
    render(strength, signed, row, style, axes);
    touched = true;
  }

  if (!touched) return null;

  // A row may have set weight through the tracking path only; keep the two
  // consistent so a font without a wght axis still shifts.
  if (axes.wght && !style.fontWeight) style.fontWeight = Math.round(axes.wght);

  if (theme.variableAxes) {
    const parts = [];
    if (axes.wght) parts.push(`"wght" ${Math.round(axes.wght)}`);
    if (axes.slnt) parts.push(`"slnt" ${axes.slnt.toFixed(1)}`);
    if (axes.MONO) parts.push(`"MONO" ${axes.MONO.toFixed(2)}`);
    if (axes.CASL) parts.push(`"CASL" ${axes.CASL.toFixed(2)}`);
    if (axes.CRSV) parts.push(`"CRSV" ${axes.CRSV.toFixed(2)}`);
    if (parts.length) style.fontVariationSettings = parts.join(', ');
    // Fonts without a slnt axis still need to lean.
    if (axes.slnt && axes.slnt < 0) style.fontStyle = 'italic';
  } else if (axes.slnt && axes.slnt < 0) {
    style.fontStyle = 'italic';
  }

  return { style, axes };
}
