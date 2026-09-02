// The whole semantic engine is these tables plus the rules in analyze.js.
// Nothing here calls out to a model; every score is a lookup or an arithmetic
// consequence of one. Weights are on the same -1..1 / 0..1 scales the
// channels use, so a custom lexicon can be merged in without rescaling.

/** valence: how the word feels. -1 hostile, +1 warm. */
export const VALENCE = {
  // negative
  awful: -0.9, terrible: -0.9, horrible: -0.9, disaster: -0.9, catastrophe: -0.95,
  hate: -0.85, hated: -0.85, broken: -0.7, broke: -0.6, fails: -0.7, failed: -0.7,
  failure: -0.75, failing: -0.7, bug: -0.45, bugs: -0.45, crash: -0.7, crashed: -0.7,
  crashes: -0.65, error: -0.5, errors: -0.5, wrong: -0.6, bad: -0.6, worse: -0.7,
  worst: -0.9, ugly: -0.6, painful: -0.7, pain: -0.6, slow: -0.45, sluggish: -0.5,
  confusing: -0.55, confused: -0.5, frustrating: -0.7, frustrated: -0.65,
  annoying: -0.55, angry: -0.7, sad: -0.6, afraid: -0.6, scared: -0.6, fear: -0.6,
  risk: -0.35, risky: -0.5, dangerous: -0.7, fragile: -0.5, brittle: -0.5,
  messy: -0.4, hack: -0.3, hacky: -0.5, bloated: -0.5, leak: -0.5, leaks: -0.5,
  regression: -0.6, outage: -0.8, corrupt: -0.8, corrupted: -0.8, lost: -0.5,
  stuck: -0.5, blocked: -0.5, dead: -0.6, deprecated: -0.35, abandoned: -0.6,
  never: -0.2, cannot: -0.3, unusable: -0.8, unreadable: -0.6, illegible: -0.6,
  noise: -0.35, noisy: -0.4, clutter: -0.4, tedious: -0.5, boring: -0.45,
  // positive
  great: 0.75, good: 0.5, excellent: 0.85, wonderful: 0.85, lovely: 0.7,
  delightful: 0.8, beautiful: 0.8, elegant: 0.75, clean: 0.5, crisp: 0.55,
  fast: 0.55, quick: 0.45, instant: 0.6, smooth: 0.55, simple: 0.5, clear: 0.5,
  readable: 0.5, obvious: 0.35, works: 0.5, working: 0.4, fixed: 0.5, solved: 0.6,
  love: 0.85, loved: 0.8, like: 0.25, enjoy: 0.6, happy: 0.7, glad: 0.55,
  calm: 0.45, safe: 0.5, stable: 0.55, robust: 0.6, reliable: 0.6, solid: 0.55,
  correct: 0.5, right: 0.4, better: 0.5, best: 0.8, improved: 0.55, faster: 0.6,
  win: 0.6, wins: 0.6, useful: 0.55, helpful: 0.55, powerful: 0.6, free: 0.4,
  open: 0.3, tiny: 0.3, small: 0.2, thanks: 0.6, welcome: 0.5, ship: 0.35,
  shipped: 0.5, green: 0.4, passing: 0.45, passed: 0.45, ready: 0.4,
};

/** salience: how much the word is asking to be looked at. 0..1 */
export const SALIENCE = {
  must: 0.8, critical: 0.9, crucial: 0.85, essential: 0.8, required: 0.7,
  mandatory: 0.8, important: 0.75, warning: 0.85, danger: 0.9, caution: 0.7,
  note: 0.5, remember: 0.6, always: 0.65, never: 0.7, only: 0.5, key: 0.6,
  first: 0.4, finally: 0.45, deadline: 0.8, urgent: 0.9, immediately: 0.8,
  now: 0.5, today: 0.45, breaking: 0.85, irreversible: 0.9, permanent: 0.7,
  production: 0.6, security: 0.7, data: 0.35, loss: 0.7, delete: 0.7,
  deleted: 0.7, destroy: 0.85, overwrite: 0.7, do: 0.15, not: 0.3,
};

/** surprise: markers that something has just turned. 0..1 */
export const SURPRISE = {
  suddenly: 0.85, unexpectedly: 0.95, surprisingly: 0.9, surprise: 0.8,
  actually: 0.6, turns: 0.4, apparently: 0.55, somehow: 0.6, oddly: 0.75,
  strangely: 0.8, weirdly: 0.75, inexplicably: 0.9, bizarrely: 0.85,
  wait: 0.6, whoa: 0.8, wow: 0.8, huh: 0.6, nope: 0.5, plot: 0.3,
  instead: 0.45, except: 0.4, contrary: 0.6, ironically: 0.7, twist: 0.6,
};

/** contrast conjunctions: what follows them is the surprising half. */
export const CONTRAST = new Set([
  'but', 'however', 'yet', 'though', 'although', 'nevertheless',
  'nonetheless', 'whereas', 'still', 'except',
]);

/** certainty: -1 hedged, +1 asserted. */
export const CERTAINTY = {
  maybe: -0.7, perhaps: -0.7, possibly: -0.7, probably: -0.4, might: -0.6,
  may: -0.4, could: -0.4, seems: -0.6, seemed: -0.6, appears: -0.5,
  apparently: -0.5, roughly: -0.4, approximately: -0.35, somewhat: -0.5,
  arguably: -0.6, allegedly: -0.7, supposedly: -0.7, unclear: -0.8,
  unsure: -0.8, guess: -0.7, think: -0.35, suspect: -0.5, presumably: -0.6,
  ish: -0.5, sort: -0.4, kind: -0.3, tends: -0.4, usually: -0.25,
  honestly: -0.3, hopefully: -0.5, ideally: -0.4, largely: -0.3,
  definitely: 0.8, certainly: 0.8, obviously: 0.7, clearly: 0.7, proven: 0.8,
  always: 0.6, never: 0.6, must: 0.7, will: 0.4, is: 0.15, guaranteed: 0.85,
  undoubtedly: 0.9, absolutely: 0.85, exactly: 0.7, precisely: 0.75,
};

/** magnitude modifiers applied to whatever content word follows. */
export const INTENSIFIERS = {
  very: 1.35, really: 1.3, extremely: 1.7, incredibly: 1.7, insanely: 1.8,
  absolutely: 1.6, totally: 1.45, completely: 1.5, utterly: 1.6, deeply: 1.4,
  hugely: 1.5, massively: 1.6, super: 1.35, so: 1.25, too: 1.3, quite: 1.15,
  particularly: 1.3, especially: 1.35, remarkably: 1.5, damn: 1.5,
  slightly: 0.6, somewhat: 0.65, mildly: 0.6, barely: 0.5, hardly: 0.5,
  kinda: 0.65, marginally: 0.55, fairly: 0.8, rather: 0.9, mostly: 0.85,
  a: 1, bit: 0.7, little: 0.7,
};

/** negators flip the valence of the next few content words. */
export const NEGATORS = new Set([
  'not', 'no', 'never', 'none', 'nothing', 'nobody', 'neither', 'nor',
  'cannot', 'cant', 'wont', 'dont', 'doesnt', 'didnt', 'isnt', 'arent',
  'wasnt', 'werent', 'without', 'lacks', 'lacking', 'hardly', 'rarely',
]);

// Rarity is the only channel that needs to know about English at large.
// A rank list is enough: everything off the list is treated as rare, which
// is the right default for jargon, names and coinages.
const COMMON = `the be to of and a in that have i it for not on with he as you do at
this but his by from they we say her she or an will my one all would there their what
so up out if about who get which go me when make can like time no just him know take
people into year your good some could them see other than then now look only come its
over think also back after use two how our work first well way even new want because
any these give day most us is are was were been has had did said would could should
where why very much still own too own between under while need thing set way part
number system data code file test run build user page line name value type state
function return error case list find open close read write show change first last
next add remove start stop check try help work done same right left long great little
own point group problem fact place case week month world life hand part child eye
woman man day thing man word question story school state family student mouse
`.split(/\s+/).filter(Boolean);

const RANK = new Map(COMMON.map((w, i) => [w, i + 1]));
const OOV_RANK = 24000;
const LOG_FLOOR = Math.log(120);
const LOG_CEIL = Math.log(OOV_RANK);

// Just enough morphology that the tables can stay small. A lexicon of stems
// covers "fails", "failing" and "failed" without three entries each — and
// without a stemmer library, which would be the only dependency in the repo.
const SUFFIXES = [
  ['ally', ''], ['ically', ''], ['ically', 'e'], ['iness', 'y'], ['ness', ''],
  ['ingly', ''], ['edly', ''], ['ily', 'y'], ['ly', ''],
  ['ing', ''], ['ing', 'e'], ['ies', 'y'], ['ied', 'y'], ['es', ''], ['ed', ''],
  ['ed', 'e'], ['er', ''], ['er', 'e'], ['est', ''], ['s', ''],
  ['ic', 'e'], ['ic', 'y'], ['ical', 'e'], ['ation', 'e'], ['ment', ''],
];

/** Candidate base forms of a word, longest suffix first. */
export function stems(word) {
  const out = [];
  for (const [suffix, replacement] of SUFFIXES) {
    if (word.length > suffix.length + 2 && word.endsWith(suffix)) {
      out.push(word.slice(0, -suffix.length) + replacement);
    }
  }
  // "stopped" -> "stop": undo the doubled consonant.
  const m = /^(.*?)([bdfglmnprt])\2(ed|ing|er|est)$/.exec(word);
  if (m) out.push(m[1] + m[2]);
  return out;
}

/**
 * Look a word up in a channel table, falling back to its stems. A derived
 * form is damped slightly — "failure" is a touch cooler than "fail".
 */
export function lookup(table, word) {
  const exact = table[word];
  if (exact !== undefined) return exact;
  for (const stem of stems(word)) {
    const hit = table[stem];
    if (hit !== undefined) return hit * 0.9;
  }
  return undefined;
}

/**
 * How unusual a word is, 0 (function word) to 1 (never seen).
 * A rank list, not a corpus: cheap, offline, and good enough that the topic
 * terms of a paragraph float to the top of it.
 */
export function rarity(word) {
  let rank = RANK.get(word);
  if (rank === undefined) {
    for (const stem of stems(word)) {
      const r = RANK.get(stem);
      if (r !== undefined) { rank = r * 1.6; break; }
    }
  }
  if (rank === undefined) rank = word.length >= 12 ? OOV_RANK : OOV_RANK * 0.7;
  const r = (Math.log(rank) - LOG_FLOOR) / (LOG_CEIL - LOG_FLOOR);
  return Math.min(1, Math.max(0, r));
}
