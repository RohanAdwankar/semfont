import test from 'node:test';
import assert from 'node:assert/strict';

import { analyze } from '../src/analyze.js';

const v = (text, word, depth = 'deep') => {
  const t = analyze(text, { depth }).tokens.find((tok) => tok.norm === word);
  assert.ok(t, `no token ${word} in ${JSON.stringify(text)}`);
  return t.valence;
};

// The ten sentences the fast tier gets wrong, each a different mechanism.
test('sarcasm: a lone positive opener before bad news', () => {
  const text = 'Great, another outage. Just what I needed today.';
  assert.ok(v(text, 'great', 'fast') > 0, 'fast reads the praise literally');
  assert.ok(v(text, 'great') < 0);
  assert.ok(v(text, 'needed') < 0);
});

test('a resolver flips the harm it resolves', () => {
  const text = 'We fixed the crash and closed the security hole before anyone noticed.';
  assert.ok(v(text, 'crash', 'fast') < 0);
  assert.ok(v(text, 'crash') > 0);
  assert.ok(v(text, 'hole') > 0);
});

test('a one-word "No," is an answer, not a negator (both tiers)', () => {
  const text = 'Did it fail? No, it passed every test.';
  assert.ok(v(text, 'passed', 'fast') > 0);
  assert.ok(v(text, 'passed') > 0);
  assert.ok(v(text, 'fail') < 0);
});

test('recovered from the crash is good news', () => {
  assert.ok(v('The cluster recovered from the crash in under a minute.', 'crash') > 0);
});

test('a risk that was avoided', () => {
  const text = 'We avoided a catastrophic outage by catching the bug in staging.';
  for (const w of ['catastrophic', 'outage', 'bug']) assert.ok(v(text, w) > 0, w);
});

test('negation reaches to the end of the clause', () => {
  const text = 'I would not go so far as to call the new editor great.';
  assert.ok(v(text, 'great', 'fast') > 0, 'fast stops at three words');
  assert.ok(v(text, 'great') < 0);
});

test('less of a bad thing is an improvement', () => {
  const text = 'Less broken than last week, and far fewer complaints.';
  assert.ok(v(text, 'broken') > 0);
  assert.ok(v(text, 'complaints') > 0);
  assert.ok(v('It is less reliable than before.', 'reliable') < 0, 'and less of a good thing is a loss');
});

test('a problem that is gone', () => {
  assert.ok(v('The memory leak is gone.', 'leak') > 0);
});

test('a quoted word the writer rejects', () => {
  const text = 'The reviewer called it "terrible", which is wrong.';
  assert.ok(v(text, 'terrible') > 0);
  assert.equal(v(text, 'wrong'), 0);
  assert.ok(v('The reviewer called it "terrible".', 'terrible') < 0, 'an unrejected quote keeps its sign');
});

test('too turns praise into a complaint', () => {
  const text = 'The API is too simple and the docs are too clever.';
  assert.ok(v(text, 'simple', 'fast') > 0);
  assert.ok(v(text, 'simple') < 0);
});

// What the deep tier must leave alone.
test('a resolver does not reach past a contrast', () => {
  const text = 'We fixed the crash but introduced a worse one.';
  assert.ok(v(text, 'crash') > 0);
  assert.ok(v(text, 'worse') < 0);
});

test('negation stops at the clause', () => {
  const text = 'Not great, but the docs are great.';
  const [first, second] = analyze(text, { depth: 'deep' }).tokens.filter((t) => t.norm === 'great');
  assert.ok(first.valence < 0);
  assert.ok(second.valence > 0);
});

test('two negators cancel', () => {
  assert.ok(v('It is not that it was not working.', 'working') > 0);
});

test('plain sentences score the same in both tiers', () => {
  for (const text of [
    'The migration ran clean on staging. In production it deleted the index, and the rollback failed too.',
    'Absolutely the worst onboarding I have ever suffered through. Support was lovely about it.',
    'It is not broken.',
  ]) {
    const fast = analyze(text, { depth: 'fast' }).tokens.map((t) => t.valence.toFixed(2));
    const deep = analyze(text, { depth: 'deep' }).tokens.map((t) => t.valence.toFixed(2));
    assert.deepEqual(deep, fast, text);
  }
});

test('the deep tier says why', () => {
  const t = analyze('We fixed the crash.', { depth: 'deep' }).tokens.find((tok) => tok.norm === 'crash');
  assert.deepEqual(t.notes, ['resolved by "fixed"']);
});

test('the deep tier is not the expensive kind of deep', () => {
  const page = 'The migration ran clean on staging. In production it deleted the index, and the rollback failed too. '.repeat(30);
  for (let i = 0; i < 5; i++) analyze(page, { depth: 'deep' });
  const started = performance.now();
  for (let i = 0; i < 20; i++) analyze(page, { depth: 'deep' });
  const ms = (performance.now() - started) / 20;
  assert.ok(ms < 30, `${ms.toFixed(1)} ms for ${page.length} characters`);
});
