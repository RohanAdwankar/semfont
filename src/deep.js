// The clause pass.
//
// The first pass in analyze.js scores a word from its own lexicon entry and a
// fixed window of two or three neighbours. On its own that reads "fixed the
// crash" as one good word and one bad word, and leaves "great" green six
// words after a "not". This pass runs after it and re-derives valence over
// clauses instead of windows. Still no model, still synchronous and
// deterministic, and about half the total cost of analyze().
//
// Five rules, none of which a fixed window can express:
//
//   scope       a negator flips everything to the end of its clause, fading
//               with distance, and cancels against a second negator
//   resolvers   "fixed", "recovered from", "avoided", "is gone": the bad thing
//               after (or before) one of these is the thing that got better
//   comparatives "less broken", "fewer complaints": less of a bad thing is good
//   too         "too simple" is a complaint, whatever "simple" is on its own
//   discourse   a lone "Great," before bad news is sarcasm; a quoted word the
//               writer then calls wrong is not the writer's word
//
// Every change it makes is written to token.notes, so a debug panel can say
// why a word came out the colour it did.

import { lookup } from './lexicon.js';

const NEGATORS = new Set([
  'not', 'no', 'never', 'none', 'nothing', 'nobody', 'neither', 'nor',
  'cannot', 'cant', 'wont', 'dont', 'doesnt', 'didnt', 'isnt', 'arent',
  'wasnt', 'werent', 'without', 'lacks', 'lacking', 'hardly', 'rarely',
  'nt',
]);

// Verbs whose object is the thing that stopped being a problem. Values are
// how much relief the object earns relative to the harm it named.
export const RESOLVERS = {
  fix: 0.7, solve: 0.7, resolve: 0.7, repair: 0.7, patch: 0.6, recover: 0.7,
  avoid: 0.7, avert: 0.7, prevent: 0.7, survive: 0.7, catch: 0.5, handle: 0.5,
  mitigate: 0.6, eliminate: 0.7, remove: 0.5, escape: 0.6, dodge: 0.6,
  withstand: 0.7, overcome: 0.7, contain: 0.5, defuse: 0.7, cure: 0.7, close: 0.5,
};

// "the leak is gone": a state word after the bad thing that says it ended.
const ENDED = new Set(['gone', 'over', 'away', 'disappeared', 'vanished', 'stopped', 'ended', 'history']);
const COPULA = new Set(['is', 'was', 'are', 'were', 'be', 'been', 'went', 'got', 'has', 'have', 'had', 'now', 'finally']);

const LESS = new Set(['less', 'fewer', 'lesser', 'reduced', 'reduces', 'reduce', 'reducing', 'fewest', 'least']);

// A positive word standing alone at the front of a sentence, followed by bad
// news, is not praise.
const SARCASM_CUES = new Set(['another', 'again', 'yet', 'always', 'still', 'now', 'course']);
const SARCASM_PHRASES = [
  ['just', 'what', 'i', 'needed'], ['thanks', 'a', 'lot'], ['nice', 'going'],
  ['good', 'luck', 'with', 'that'], ['how', 'wonderful'], ['oh', 'good'], ['oh', 'great'],
];

// After a quotation: words that say the quote is not the writer's view.
const REJECTS = new Set(['wrong', 'false', 'untrue', 'nonsense', 'unfair', 'mistaken', 'incorrect', 'disagree', 'rubbish', 'absurd', 'baseless']);

// Clause breaks: punctuation, and the conjunctions that start a new one.
const CLAUSE_WORDS = new Set([
  'and', 'but', 'or', 'because', 'since', 'while', 'although', 'though',
  'whereas', 'unless', 'until', 'if', 'when', 'which', 'who', 'yet', 'however',
  'then', 'except',
]);
const CLAUSE_PUNCT = /[,;:()\[\]—–]|--/;

const isContent = (t) => t.kind === 'word' || t.kind === 'number';
const clamp = (x, lo, hi) => (x < lo ? lo : x > hi ? hi : x);

function note(t, why) {
  (t.notes ??= []).push(why);
}

/** Group a sentence's tokens into clauses. Each clause is a list of tokens. */
function clauses(tokens, sentence) {
  const out = [];
  let current = [];
  for (let i = sentence.start; i <= sentence.end && i < tokens.length; i++) {
    const t = tokens[i];
    const breaks = (t.kind === 'punct' && CLAUSE_PUNCT.test(t.text))
      || (t.kind === 'word' && CLAUSE_WORDS.has(t.norm));
    if (breaks && current.some(isContent)) {
      out.push(current);
      current = [];
    }
    current.push(t);
  }
  if (current.some(isContent)) out.push(current);
  return out;
}

/** The next content token after index i, within the same clause. */
function nextContent(clause, i) {
  for (let j = i + 1; j < clause.length; j++) if (isContent(clause[j])) return clause[j];
  return null;
}

/** Is this negator the one-word answer "No," rather than a scope opener? */
function isAnswerParticle(tokens, t) {
  const next = tokens[t.index + 1];
  return t.norm === 'no' && next && next.kind === 'punct' && next.text.startsWith(',');
}

/**
 * Re-derive valence over clauses. Mutates the tokens of a first-pass result
 * and returns it. Needs `token.raw` (the lexicon value) and `token.gain`
 * (intensifier and shouting), which analyze() records for this purpose.
 */
export function deepen(result, options = {}) {
  const { tokens, sentences } = result;
  const sensitivity = options.sensitivity ?? 1;
  const resolvers = options.lexicon?.resolvers
    ? { ...RESOLVERS, ...options.lexicon.resolvers } : RESOLVERS;

  for (const t of tokens) {
    if (!isContent(t)) continue;
    t.deep = t.raw ?? 0;
    t.notes = undefined;
  }

  for (let si = 0; si < sentences.length; si++) {
    const sentence = sentences[si];
    const parts = clauses(tokens, sentence);

    for (let ci = 0; ci < parts.length; ci++) {
      const clause = parts[ci];
      const words = clause.filter(isContent);

      // 1. scope: a negator flips what follows it in the clause, fading with
      //    distance; a second negator cancels the first.
      let negator = null;
      let steps = 0;
      for (const t of words) {
        if (NEGATORS.has(t.norm) && !isAnswerParticle(tokens, t)) {
          negator = negator ? null : t;
          steps = 0;
          continue;
        }
        if (negator && t.deep !== 0) {
          steps++;
          t.deep = -t.deep * 0.74 * 0.93 ** (steps - 1);
          note(t, `negated by "${negator.text}"`);
        }
      }

      // 2. resolvers: the harm named after "fixed" is what got fixed. And a
      //    bad thing that "is gone" is the good outcome.
      let resolver = null;
      for (const t of words) {
        const r = lookup(resolvers, t.norm);
        if (r !== undefined) {
          resolver = { t, r };
          if (t.deep <= 0) { t.deep = Math.max(t.deep, 0.35); note(t, 'resolves what follows'); }
          continue;
        }
        if (resolver && t.deep < 0) {
          t.deep = -t.deep * resolver.r;
          note(t, `resolved by "${resolver.t.text}"`);
        }
      }
      for (let i = 0; i < words.length; i++) {
        const t = words[i];
        const prev = words[i - 1];
        if (ENDED.has(t.norm) && prev && COPULA.has(prev.norm)) {
          for (let j = 0; j < i; j++) {
            if (words[j].deep < 0) {
              words[j].deep = -words[j].deep * 0.6;
              note(words[j], `ended: "${prev.text} ${t.text}"`);
            }
          }
          if (t.deep <= 0) { t.deep = 0.3; note(t, 'the problem ended'); }
        }
      }

      // 3. comparatives: less of a bad thing is an improvement, less of a
      //    good thing is a loss.
      for (let i = 0; i < clause.length; i++) {
        const t = clause[i];
        if (!isContent(t) || !LESS.has(t.norm)) continue;
        let n = nextContent(clause, i);
        if (n && n.deep === 0) n = nextContent(clause, clause.indexOf(n));
        if (n && n.deep !== 0) {
          n.deep = -n.deep * 0.6;
          note(n, `${t.text} of it`);
        }
      }

      // 4. too: "too simple" is a complaint.
      for (let i = 0; i < clause.length; i++) {
        const t = clause[i];
        if (!isContent(t) || t.norm !== 'too') continue;
        const n = nextContent(clause, i);
        if (n && n.deep > 0) {
          n.deep = -n.deep * 0.8;
          note(n, 'too much of it');
        }
      }
    }

    // 5a. sarcasm: a lone positive opener followed by bad news.
    const first = parts[0]?.filter(isContent) ?? [];
    const opener = first.length === 1 ? first[0]
      : (first.length === 2 && ['oh', 'well', 'just', 'how'].includes(first[0].norm)) ? first[1] : null;
    if (opener && opener.deep >= 0.4 && parts.length >= 1) {
      const restTokens = [
        ...parts.slice(1).flat(),
        ...(sentences[si + 1] ? tokens.slice(sentences[si + 1].start, sentences[si + 1].end + 1) : []),
      ].filter(isContent);
      const badNews = restTokens.some((t) => t.deep < -0.3)
        || restTokens.some((t) => SARCASM_CUES.has(t.norm));
      if (badNews) {
        opener.deep = -opener.deep * 0.9;
        note(opener, 'sarcasm: praise, then bad news');
      }
    }
    const sentenceWords = tokens.slice(sentence.start, sentence.end + 1).filter(isContent);
    const norms = sentenceWords.map((t) => t.norm);
    for (const phrase of SARCASM_PHRASES) {
      for (let i = 0; i + phrase.length <= norms.length; i++) {
        if (phrase.every((w, k) => norms[i + k] === w)) {
          const t = sentenceWords[i + phrase.length - 1];
          if (t.deep >= 0) { t.deep = -0.45; note(t, 'sarcasm: a set phrase'); }
        }
      }
    }

    // 5b. a quoted word the writer then rejects is not the writer's word.
    const span = tokens.slice(sentence.start, sentence.end + 1);
    let open = -1;
    for (let i = 0; i < span.length; i++) {
      const t = span[i];
      if (t.kind !== 'punct' || !/["“”]/.test(t.text)) continue;
      if (open < 0) { open = i; continue; }
      const quoted = span.slice(open + 1, i).filter(isContent);
      const after = span.slice(i + 1).filter(isContent);
      const reject = after.find((w) => REJECTS.has(w.norm)
        || (w.norm === 'not' && after[after.indexOf(w) + 1] && ['true', 'fair', 'right', 'so'].includes(after[after.indexOf(w) + 1].norm)));
      if (reject) {
        for (const q of quoted) {
          if (q.deep !== 0) { q.deep = -q.deep * 0.6; note(q, `quoted, then called "${reject.text}"`); }
        }
        reject.deep = 0;
        note(reject, 'about the quote, not the subject');
      }
      open = -1;
    }
  }

  for (const t of tokens) {
    if (!isContent(t)) continue;
    t.valence = clamp(t.deep * (t.gain ?? 1) * sensitivity, -1, 1);
    delete t.deep;
  }
  return result;
}
