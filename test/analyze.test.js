import test from 'node:test';
import assert from 'node:assert/strict';

import { analyze, summarize } from '../src/analyze.js';
import { styleFor, themes } from '../src/theme.js';

const score = (text, word, channel) => {
  const t = analyze(text).tokens.find((tok) => tok.norm === word);
  assert.ok(t, `no token ${word} in ${JSON.stringify(text)}`);
  return t[channel];
};

test('tokens reassemble into the original text', () => {
  for (const text of [
    'Hello, world!',
    '  leading and trailing  ',
    'em—dashes, "quotes", 3.14% and emoji 🙂 all survive',
    '',
  ]) {
    assert.equal(analyze(text).tokens.map((t) => t.text).join(''), text);
  }
});

test('valence separates the two halves of a sentence', () => {
  const text = 'The release was beautiful. The migration was a disaster.';
  assert.ok(score(text, 'beautiful', 'valence') > 0.5);
  assert.ok(score(text, 'disaster', 'valence') < -0.5);
});

test('negation flips valence and damps it', () => {
  const plain = score('this is great', 'great', 'valence');
  const negated = score('this is not great', 'great', 'valence');
  assert.ok(negated < 0, 'not great reads negative');
  assert.ok(Math.abs(negated) < plain, 'and reads weaker than plain great');
});

test('negation does not reach across a sentence boundary', () => {
  assert.ok(score('it is not ready. shipping was great', 'great', 'valence') > 0);
});

test('intensifiers scale, downtoners shrink', () => {
  const plain = score('it was slow', 'slow', 'valence');
  assert.ok(score('it was extremely slow', 'slow', 'valence') < plain);
  assert.ok(score('it was slightly slow', 'slow', 'valence') > plain);
});

test('shouting raises salience', () => {
  const quiet = score('do not delete the volume', 'delete', 'salience');
  const loud = score('do not DELETE the volume', 'delete', 'salience');
  assert.ok(loud > quiet);
});

test('a repeated rare word becomes the subject of the passage', () => {
  const once = score('the kubelet then waits for the next tick', 'kubelet', 'salience');
  const thrice = score(
    'the kubelet waits. the kubelet retries. then the kubelet gives up.',
    'kubelet',
    'salience',
  );
  assert.ok(thrice > once);
});

test('common words stay out of the way', () => {
  for (const w of ['the', 'and', 'for', 'with']) {
    assert.ok(score('the code and the tests for a build with it', w, 'salience') < 0.2, w);
  }
});

test('contrast conjunctions make what follows surprising', () => {
  const text = 'The tests passed but the deploy rolled back.';
  assert.ok(score(text, 'deploy', 'surprise') > score(text, 'tests', 'surprise'));
});

test('hedges lean the whole clause, assertions do not', () => {
  assert.ok(score('this might be the culprit', 'culprit', 'certainty') < 0);
  assert.ok(score('this is definitely the culprit', 'culprit', 'certainty') > 0);
});

test('a question is less certain than a statement', () => {
  assert.ok(
    score('is the cache warm?', 'cache', 'certainty')
    < score('the cache is warm.', 'cache', 'certainty'),
  );
});

test('styleFor leaves ordinary words alone', () => {
  const { tokens } = analyze('the file is in the folder with the other one');
  const styled = tokens.filter((t) => styleFor(t, themes.editorial));
  assert.equal(styled.length, 0);
});

test('styleFor emits colour for valence and weight for salience', () => {
  const { tokens } = analyze('this is an absolutely catastrophic regression');
  const bad = tokens.find((t) => t.norm === 'catastrophic' || t.norm === 'regression');
  const out = styleFor(bad, themes.loud);
  assert.ok(out.style.color?.startsWith('color-mix('));
  assert.ok(out.style.fontWeight > 400);
});

test('the monochrome theme never emits colour', () => {
  const { tokens } = analyze('an absolutely catastrophic, surprisingly slow disaster!');
  for (const t of tokens) {
    const out = styleFor(t, themes.monochrome);
    if (!out) continue;
    assert.equal(out.style.color, undefined);
    assert.equal(out.style.background, undefined);
  }
});

// A scored token, straight into styleFor, so one channel can be moved at a
// time. Going through analyze() makes it very hard to isolate a channel, which
// is part of why the theme maps were only ever tested for what they do not do.
const scored = (channels) => ({
  kind: 'word',
  text: 'word',
  valence: 0,
  salience: 0,
  surprise: 0,
  certainty: 0,
  technicality: 0,
  ...channels,
});

test('the monochrome theme carries all four channels, not just three', () => {
  // The point of this theme is that colour is not an accessible channel on its
  // own, which is worth nothing if taking colour away silently drops one.
  for (const channel of ['valence', 'salience', 'surprise', 'certainty']) {
    const out = styleFor(scored({ [channel]: -0.9 }), themes.monochrome)
      ?? styleFor(scored({ [channel]: 0.9 }), themes.monochrome);
    assert.ok(out, `monochrome renders nothing at all for ${channel}`);
    assert.ok(Object.keys(out.style).length > 0, `monochrome emits no property for ${channel}`);
  }
});

test('slant axes only go negative, in every theme', () => {
  // `slnt` is 0..-10 on Roboto Flex and 0..-15 on Recursive. A positive value
  // is clamped to 0 by the font, so the row renders as nothing at all.
  //
  // One channel at a time on purpose. Scoring two of them together is what hid
  // this: monochrome's positive valence slant and negative certainty slant
  // summed to a negative number, so a token carrying both looked fine.
  for (const [name, theme] of Object.entries(themes)) {
    for (const channel of ['valence', 'salience', 'surprise', 'certainty', 'technicality']) {
      for (const sign of [-0.9, 0.9]) {
        const slnt = styleFor(scored({ [channel]: sign }), theme)?.axes.slnt;
        if (slnt === undefined) continue;
        assert.ok(slnt <= 0, `${name} puts ${channel} at slnt ${slnt}, which no font can render`);
      }
    }
  }
});

test('no theme drives one axis from two different channels', () => {
  // Rows accumulate per axis, so two channels on one axis do not merely become
  // ambiguous, they add: monochrome had valence and certainty both on `slnt`
  // with opposite signs, and a word that was negative *and* hedged came out
  // upright because the two cancelled.
  for (const [name, theme] of Object.entries(themes)) {
    const owner = new Map();
    for (const row of theme.map) {
      const held = owner.get(row.render);
      assert.ok(
        held === undefined || held === row.channel,
        `${name} drives ${row.render} from both ${held} and ${row.channel}`,
      );
      owner.set(row.render, row.channel);
    }
  }
});

test('a second channel never cancels the first on a shared axis', () => {
  // The behavioural half of the rule above, in the case that actually bit.
  const hedged = styleFor(scored({ certainty: -0.9 }), themes.monochrome);
  const hedgedAndNegative = styleFor(scored({ certainty: -0.9, valence: -0.9 }), themes.monochrome);
  const lean = (out) => Math.abs(out?.axes.slnt ?? 0);
  assert.ok(
    lean(hedgedAndNegative) >= lean(hedged),
    'adding negative valence reduced the lean instead of leaving it alone',
  );
});

test('technicality is decided by shape, not by a word list alone', () => {
  const shaped = 'the readFileSync call and the cluster_config value and p99 itself';
  const { tokens } = analyze(shaped);
  const tech = Object.fromEntries(tokens.filter((t) => t.technicality > 0.5).map((t) => [t.norm, 1]));
  for (const w of ['readfilesync', 'clusterconfig', 'p99']) assert.ok(tech[w], w);
  for (const w of ['the', 'call', 'value', 'itself']) assert.ok(!tech[w], w);
});

test('a theme map row can be added, and only that row fires', () => {
  const { tokens } = analyze('the readFileSync call failed');
  const bare = { ...themes.editorial, map: [{ channel: 'technicality', render: 'mono' }] };
  const styled = tokens.map((t) => styleFor(t, bare)).filter(Boolean);
  assert.equal(styled.length, 1);
  assert.match(styled[0].style.fontVariationSettings, /"MONO"/);
  assert.equal(styled[0].style.color, undefined);
});

test('the technical theme drives five channels across five axes', () => {
  const { tokens } = analyze('The kubelet might have deleted the p99 dashboard, which is a disaster.');
  const axes = new Set();
  for (const t of tokens) {
    const out = styleFor(t, themes.technical);
    if (out) for (const k of Object.keys(out.axes)) axes.add(k);
  }
  assert.ok(axes.has('MONO'), [...axes].join(','));
  assert.ok(axes.has('wght'), [...axes].join(','));
  assert.ok(axes.has('slnt'), [...axes].join(','));
});

test('sensitivity scales the whole readout', () => {
  const text = 'the deploy failed and the rollback failed too';
  const quiet = summarize(analyze(text, { sensitivity: 0.5 }));
  const loud = summarize(analyze(text, { sensitivity: 1.5 }));
  assert.ok(Math.abs(loud.valence) > Math.abs(quiet.valence));
});

test('a custom lexicon overrides the built-in one', () => {
  const opts = { lexicon: { valence: { kubernetes: -0.9 } } };
  const t = analyze('kubernetes again', opts).tokens.find((x) => x.norm === 'kubernetes');
  assert.ok(t.valence < -0.5);
});

test('summarize reports the loudest words', () => {
  const s = summarize(analyze('WARNING: the production database will be deleted immediately.'));
  assert.ok(s.loudest.length > 0);
  assert.ok(s.loudest.some((w) => /WARNING|deleted|database/.test(w)));
});

test('analysis is linear enough for a keystroke', () => {
  const text = 'the kubelet waits and then it retries after the backoff expires. '.repeat(400);
  const started = performance.now();
  analyze(text);
  const ms = performance.now() - started;
  assert.ok(ms < 250, `analysis of ${text.length} chars took ${ms.toFixed(0)}ms`);
});
