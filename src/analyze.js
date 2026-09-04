// The semantic engine.
//
// Four channels, scored per token by lookup and by rules over the
// neighbourhood of the token. No network, no model, no async: analyze() is a
// pure function from a string to numbers, which is what lets the typography
// update on every keystroke.
//
//   valence    -1 hostile      ..  +1 warm
//   salience    0 background   ..   1 look here
//   surprise    0 expected     ..   1 the sentence just turned
//   certainty  -1 hedged       ..  +1 asserted
//   technicality 0 prose        ..   1 names machinery
//
// A channel is just a number on a token, so adding one costs a lookup per
// token and nothing at all to the themes that ignore it.

import {
  VALENCE, SALIENCE, SURPRISE, CERTAINTY, TECHNICAL, CONTRAST,
  INTENSIFIERS, NEGATORS, lookup, rarity,
} from './lexicon.js';

// Underscores stay inside a word: cluster_config is one identifier, and
// splitting it hides exactly the shape the technicality channel reads.
const TOKEN_RE = /(\s+)|([\p{L}][\p{L}\p{N}_'’-]*)|(\d[\d.,:%]*(?:[\p{L}]{1,3}\b)?)|([^\s])/gu;
const NEGATION_WINDOW = 3;
const INTENSIFIER_WINDOW = 2;
// Below this rarity a word is grammar rather than content: "the", "and", "is".
const FUNCTION_WORD_RARITY = 0.3;

const clamp = (x, lo, hi) => (x < lo ? lo : x > hi ? hi : x);
const clamp01 = (x) => clamp(x, 0, 1);
const normalize = (s) => s.toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');

/** Split into tokens that put back together into exactly the input string. */
function tokenize(text) {
  const tokens = [];
  let m;
  TOKEN_RE.lastIndex = 0;
  while ((m = TOKEN_RE.exec(text)) !== null) {
    const [raw, space, word, number] = m;
    tokens.push({
      text: raw,
      start: m.index,
      kind: space ? 'space' : word ? 'word' : number ? 'number' : 'punct',
      norm: word ? normalize(word) : number ? raw : '',
      index: tokens.length,
      sentence: 0,
      valence: 0,
      salience: 0,
      surprise: 0,
      certainty: 0,
      technicality: 0,
    });
  }
  return tokens;
}

/** Sentence boundaries, and the flags a sentence lends to its words. */
function segment(tokens) {
  const sentences = [];
  let current = { start: 0, end: 0, exclaimed: false, questioned: false, certainty: 0, marks: 0 };
  for (const t of tokens) {
    t.sentence = sentences.length;
    current.end = t.index;
    if (t.kind === 'punct') {
      if (t.text.includes('!')) current.exclaimed = true;
      if (t.text.includes('?')) current.questioned = true;
      if (/[.!?]/.test(t.text)) {
        sentences.push(current);
        current = { start: t.index + 1, end: t.index + 1, exclaimed: false, questioned: false, certainty: 0, marks: 0 };
      }
    }
  }
  if (current.start < tokens.length) sentences.push(current);
  return sentences.length ? sentences : [current];
}

const isContent = (t) => t.kind === 'word' || t.kind === 'number';

/**
 * Does this token name machinery? Shape answers most of it: prose does not
 * contain camelCase, underscores, or letters welded to digits.
 */
function technicality(token, table) {
  if (token.kind === 'number') return /[a-z]/i.test(token.text) ? 0.7 : 0.45;
  const raw = token.text;
  let score = lookup(table, token.norm) ?? 0;
  if (/\p{Ll}\p{Lu}/u.test(raw)) score = Math.max(score, 0.9);
  if (raw.includes('_')) score = Math.max(score, 0.9);
  if (/\p{L}/u.test(raw) && /\d/.test(raw)) score = Math.max(score, 0.8);
  if (raw.length >= 2 && raw === raw.toUpperCase() && /\p{L}/u.test(raw)) {
    score = Math.max(score, 0.55);
  }
  return score;
}

/** Walk back over content words in the same sentence. */
function* lookBehind(tokens, from, span) {
  let seen = 0;
  for (let i = from - 1; i >= 0 && seen < span; i--) {
    const t = tokens[i];
    if (!isContent(t)) continue;
    if (t.sentence !== tokens[from].sentence) return;
    seen++;
    yield t;
  }
}

/**
 * Score a passage.
 * @param {string} text
 * @param {{lexicon?: object, sensitivity?: number}} [options]
 *   lexicon merges extra entries into any of the four tables:
 *   `{ valence: {...}, salience: {...}, surprise: {...}, certainty: {...} }`
 */
export function analyze(text, options = {}) {
  const sensitivity = options.sensitivity ?? 1;
  const ext = options.lexicon ?? {};
  const valence = ext.valence ? { ...VALENCE, ...ext.valence } : VALENCE;
  const salience = ext.salience ? { ...SALIENCE, ...ext.salience } : SALIENCE;
  const surprise = ext.surprise ? { ...SURPRISE, ...ext.surprise } : SURPRISE;
  const certainty = ext.certainty ? { ...CERTAINTY, ...ext.certainty } : CERTAINTY;
  const technical = ext.technicality ? { ...TECHNICAL, ...ext.technicality } : TECHNICAL;

  const tokens = tokenize(text);
  const sentences = segment(tokens);
  const content = tokens.filter(isContent);

  // Pass 1: rarity, repetition, and the passage's own baseline. A word is
  // only remarkable relative to the company it keeps, so the threshold for
  // "rare here" comes from this passage rather than from the rank list.
  const counts = new Map();
  for (const t of content) {
    t.rarity = t.kind === 'number' ? 0.6 : rarity(t.norm);
    counts.set(t.norm, (counts.get(t.norm) ?? 0) + 1);
  }
  const meanRarity = content.length
    ? content.reduce((a, t) => a + t.rarity, 0) / content.length
    : 0;

  // Pass 2: sentence certainty, so a hedge colours its whole clause.
  for (const t of content) {
    const c = lookup(certainty, t.norm);
    if (c !== undefined) {
      const s = sentences[t.sentence];
      if (s) { s.certainty += c; s.marks++; }
    }
  }
  for (const s of sentences) {
    s.certainty = s.marks ? s.certainty / s.marks : 0;
    if (s.questioned) s.certainty -= 0.25;
  }

  // Pass 3: per token.
  let contrastDistance = Infinity;
  let contrastSentence = -1;
  for (const t of tokens) {
    if (!isContent(t)) continue;
    const sentence = sentences[t.sentence] ?? { exclaimed: false, certainty: 0 };

    if (CONTRAST.has(t.norm)) {
      contrastDistance = 0;
      contrastSentence = t.sentence;
    } else if (t.sentence === contrastSentence) {
      contrastDistance++;
    } else {
      contrastDistance = Infinity;
    }

    // magnitude modifiers: an intensifier in front, ALL CAPS, or a "!"
    let gain = 1;
    let steps = 0;
    for (const prev of lookBehind(tokens, t.index, INTENSIFIER_WINDOW)) {
      steps++;
      const f = INTENSIFIERS[prev.norm];
      if (f !== undefined && f !== 1) { gain *= f ** (steps === 1 ? 1 : 0.5); }
    }
    const shouty = t.kind === 'word' && t.text.length > 1 && t.text === t.text.toUpperCase()
      && /\p{L}/u.test(t.text);
    if (shouty) gain *= 1.4;
    if (sentence.exclaimed) gain *= 1.15;

    // valence, then negation flips it. "not great" is mildly bad, not the
    // mirror image of great, hence the damping.
    let v = lookup(valence, t.norm) ?? 0;
    if (v !== 0) {
      for (const prev of lookBehind(tokens, t.index, NEGATION_WINDOW)) {
        if (NEGATORS.has(prev.norm)) { v = -v * 0.74; break; }
      }
      t.valence = clamp(v * gain * sensitivity, -1, 1);
    }

    // salience: asked for by the word, or earned by being this passage's
    // subject: a rare word that keeps coming back is what the text is about.
    const repeats = counts.get(t.norm) ?? 1;
    const repetition = 0.45 + 0.55 * Math.min(1, (repeats - 1) / 2);
    let sal = lookup(salience, t.norm) ?? 0;
    sal = Math.max(sal, 0.55 * t.rarity * repetition);
    if (t.kind === 'number') sal = Math.max(sal, /[%:]/.test(t.text) ? 0.55 : 0.45);
    if (shouty) sal += 0.3;
    if (sentence.exclaimed) sal += 0.08;
    t.salience = clamp01(sal * gain * sensitivity);

    // surprise: a marker, or the clause after a contrast conjunction, or a
    // word much rarer than its neighbours. Function words carry the grammar,
    // not the news, so they are exempt from everything but the marker list.
    // Without this, "but the" lights up as brightly as what follows it.
    let sur = lookup(surprise, t.norm) ?? 0;
    if (t.rarity > FUNCTION_WORD_RARITY) {
      if (contrastDistance > 0 && contrastDistance <= 6) {
        sur = Math.max(sur, 0.45 * 0.82 ** (contrastDistance - 1));
      }
      sur += 0.3 * Math.max(0, t.rarity - meanRarity - 0.25);
    }
    t.surprise = clamp01(sur * sensitivity);

    // certainty: full strength on the hedge itself, a lean on its clause.
    const own = lookup(certainty, t.norm);
    t.certainty = clamp(own !== undefined ? own : sentence.certainty * 0.55, -1, 1);

    t.technicality = clamp01(technicality(t, technical) * sensitivity);
  }

  return { text, tokens, sentences, stats: { meanRarity, words: content.length } };
}

/** Passage-level readout, handy for a document outline or a debug panel. */
export function summarize(result) {
  const words = result.tokens.filter(isContent);
  if (!words.length) return { valence: 0, salience: 0, surprise: 0, certainty: 0 };
  const mean = (k) => words.reduce((a, t) => a + t[k], 0) / words.length;
  return {
    valence: mean('valence'),
    salience: mean('salience'),
    surprise: mean('surprise'),
    certainty: mean('certainty'),
    loudest: [...words].sort((a, b) => b.salience - a.salience).slice(0, 5).map((t) => t.text),
  };
}
