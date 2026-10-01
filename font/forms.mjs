// What the library's own lookup() returns for each candidate word, stem
// fallback and damping included, and the word lists the clause pass uses.
//
//   {"table": "VALENCE" | "RESOLVERS", "words": [...]}   ->   {word: value}
//   {"lists": true}                                      ->   {negators, clauseWords}
import { VALENCE, lookup } from '../src/lexicon.js';
import { RESOLVERS, NEGATORS, CLAUSE_WORDS } from '../src/deep.js';

let input = '';
for await (const chunk of process.stdin) input += chunk;
const request = JSON.parse(input);
const out = {};
if (request.lists) {
  out.negators = [...NEGATORS];
  out.clauseWords = [...CLAUSE_WORDS];
  out.resolvers = Object.keys(RESOLVERS);
} else {
  const table = request.table === 'RESOLVERS' ? RESOLVERS : VALENCE;
  for (const word of request.words) {
    const value = lookup(table, word);
    if (value !== undefined) out[word] = value;
  }
}
process.stdout.write(JSON.stringify(out));
