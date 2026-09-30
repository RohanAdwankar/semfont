// What the library says about each word, for font/parity.py to compare against.
// Reads a JSON array of strings on stdin, writes one record per string.
import { analyze } from '../src/analyze.js';

let input = '';
for await (const chunk of process.stdin) input += chunk;
const out = JSON.parse(input).map((text) => ({
  text,
  words: analyze(text).tokens
    .filter((t) => t.kind === 'word')
    .map((t) => ({ text: t.text, start: t.start, norm: t.norm, valence: t.valence })),
}));
process.stdout.write(JSON.stringify(out));
