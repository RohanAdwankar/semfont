// Time analyze() on real prose and report milliseconds per hundred words.
//
//   node test/bench.mjs [file ...]
//
// With no files it scores this repository's README. The budget the engine is
// held to is one millisecond per hundred words on a laptop, linear in the
// length of the text.

import { readFileSync } from 'node:fs';
import { analyze } from '../src/analyze.js';

const files = process.argv.slice(2);
const texts = files.length
  ? files.map((f) => [f, readFileSync(f, 'utf8')])
  : [['README.md', readFileSync(new URL('../README.md', import.meta.url), 'utf8')]];

for (const [name, raw] of texts) {
  const text = raw.replace(/```[\s\S]*?```/g, '');
  const words = text.split(/\s+/).filter(Boolean).length;
  for (let i = 0; i < 30; i++) analyze(text);
  const runs = 200;
  const started = performance.now();
  for (let i = 0; i < runs; i++) analyze(text);
  const ms = (performance.now() - started) / runs;
  console.log(`${name}: ${words} words in ${ms.toFixed(2)} ms, ${(ms / words * 100).toFixed(2)} ms per hundred words`);
}
