// Channels in, typography out.
//
// A theme is data: thresholds below which a token is left completely alone,
// and the range each channel is allowed to move its axis through. Restraint
// is the whole design — if every word is styled, none of them is emphasised,
// so the thresholds are deliberately high and the ranges deliberately small.
//
// Colour is expressed with color-mix against `currentColor`, so the text
// stays legible in light and dark without the theme knowing which it is in.

const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);

/** How far past its threshold a score got, on a fresh 0..1 scale. */
const past = (value, threshold) =>
  clamp01((Math.abs(value) - threshold) / (1 - threshold));

export const baseTheme = {
  name: 'editorial',
  thresholds: { valence: 0.2, salience: 0.3, surprise: 0.35, certainty: 0.35 },
  weight: { base: 400, range: 300 },     // salience -> wght
  size: { range: 0.13 },                 // salience -> em
  color: {
    negative: 'oklch(0.58 0.19 25)',     // valence -> hue
    positive: 'oklch(0.55 0.13 155)',
    max: 0.85,                           // strongest mix with currentColor
  },
  highlight: { color: 'oklch(0.85 0.16 92)', max: 0.42 },  // surprise -> mark
  slant: { max: -9, opacity: 0.28 },     // hedging -> slnt + a step back
  tracking: { max: -0.012 },             // assertion -> tighter setting
  variableAxes: true,
};

export const themes = {
  editorial: baseTheme,

  // Everything turned up, for a demo or a headline.
  loud: {
    ...baseTheme,
    name: 'loud',
    thresholds: { valence: 0.1, salience: 0.18, surprise: 0.22, certainty: 0.25 },
    weight: { base: 380, range: 480 },
    size: { range: 0.34 },
    color: { negative: 'oklch(0.55 0.24 27)', positive: 'oklch(0.52 0.17 150)', max: 1 },
    highlight: { color: 'oklch(0.85 0.19 92)', max: 0.7 },
    slant: { max: -14, opacity: 0.35 },
  },

  // No colour at all: weight, size, slant and tracking carry every channel.
  // Print, e-ink, and the honest answer to "colour is not an accessible
  // channel on its own".
  monochrome: {
    ...baseTheme,
    name: 'monochrome',
    color: null,
    highlight: null,
    weight: { base: 380, range: 400 },
    size: { range: 0.18 },
    valenceSlant: 8,        // negative valence leans back instead of reddening
    tracking: { max: -0.02 },
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
  const th = theme.thresholds;
  const style = {};
  const axes = {};
  let touched = false;

  const salience = past(token.salience, th.salience);
  if (salience > 0) {
    const wght = Math.round(theme.weight.base + salience * theme.weight.range);
    axes.wght = wght;
    style.fontWeight = wght;
    if (theme.size.range) style.fontSize = `${(1 + salience * theme.size.range).toFixed(3)}em`;
    touched = true;
  }

  const valence = past(token.valence, th.valence);
  if (valence > 0) {
    if (theme.color) {
      const accent = token.valence < 0 ? theme.color.negative : theme.color.positive;
      const mix = Math.round(valence * theme.color.max * 100);
      style.color = `color-mix(in oklab, currentColor, ${accent} ${mix}%)`;
    }
    if (theme.valenceSlant && token.valence < 0) {
      axes.slnt = (axes.slnt ?? 0) + theme.valenceSlant;
    }
    touched = true;
  }

  const surprise = past(token.surprise, th.surprise);
  if (surprise > 0 && theme.highlight) {
    const alpha = Math.round(surprise * theme.highlight.max * 100);
    style.background = `color-mix(in oklab, transparent, ${theme.highlight.color} ${alpha}%)`;
    style.borderRadius = '0.18em';
    style.boxShadow = '0 0 0 0.12em ' + style.background;
    touched = true;
  }

  const certainty = past(token.certainty, th.certainty);
  if (certainty > 0) {
    if (token.certainty < 0) {
      axes.slnt = (axes.slnt ?? 0) + theme.slant.max * certainty;
      style.opacity = (1 - certainty * theme.slant.opacity).toFixed(3);
      if (!theme.variableAxes) style.fontStyle = 'italic';
    } else {
      style.letterSpacing = `${(certainty * theme.tracking.max).toFixed(4)}em`;
      if (!style.fontWeight) style.fontWeight = Math.round(theme.weight.base + certainty * 120);
    }
    touched = true;
  }

  if (!touched) return null;

  if (theme.variableAxes) {
    const parts = [];
    if (axes.wght) parts.push(`"wght" ${axes.wght}`);
    if (axes.slnt) parts.push(`"slnt" ${axes.slnt.toFixed(1)}`);
    if (parts.length) style.fontVariationSettings = parts.join(', ');
    // Fonts without a slnt axis still need to lean.
    if (axes.slnt && axes.slnt < 0) style.fontStyle = 'italic';
  }

  return { style, axes };
}
