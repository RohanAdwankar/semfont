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
