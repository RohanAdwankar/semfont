# semantic font

Typography that modulates on meaning instead of on markup. Negative things
render red, important things get heavier, surprising things get highlighted,
hedged things lean — and nothing in the pipeline is a model.

Idea: [#1455](https://github.com/drapoz/0/issues/1455).

```jsx
import { SemanticText } from 'semantic-font';

<SemanticText as="p">
  The migration ran clean on staging. In production it deleted the index,
  and the rollback failed too.
</SemanticText>
```

No markup went in. `clean` comes out green, `deleted` heavier, `failed` red,
and the clause after `but` is highlighted, because the engine read the
sentence.

## Why not an LLM

Because typography has to keep up with typing. `analyze()` is a pure
synchronous function over lexicons and local rules: about a millisecond for a
page of prose, no network, no key, no async, nothing leaving the browser, and
the same input always gives the same output. That is what makes it usable as
a *font* rather than as a feature — it can run on every keystroke, in a
`useMemo`, during SSR, on a plane.

An LLM would read sarcasm better. It could not run 60 times a second inside a
textarea.

## The four channels

Every token gets four scores, and each drives a different typographic axis so
they compose instead of collide:

| channel | range | signals | typography |
|---|---|---|---|
| `valence` | −1..1 | sentiment lexicon, negation, intensifiers | colour |
| `salience` | 0..1 | emphasis lexicon, ALL CAPS, numerals, repeated rare words | weight (`wght`), size |
| `surprise` | 0..1 | surprise markers, contrast conjunctions, local rarity spikes | highlight |
| `certainty` | −1..1 | hedges and assertions, spread over the clause | slant (`slnt`), opacity |

Two rules do most of the work. **Negation flips and damps**: `not great` is
mildly negative, not the mirror image of `great`. **Rarity is relative to the
passage**: a word is only remarkable next to the company it keeps, so the
threshold comes from this text, not from a global corpus — which is how the
topic terms of a paragraph float up without anyone tagging them.

## API

```js
import { SemanticText, useSemanticText, analyze, themes, styleFor } from 'semantic-font';
```

`<SemanticText>` props:

| prop | default | |
|---|---|---|
| `text` / `children` | — | the passage |
| `theme` | `'editorial'` | `'editorial'`, `'loud'`, `'monochrome'`, or a theme object |
| `channels` | all four | which channels may style |
| `sensitivity` | `1` | global gain on every score |
| `lexicon` | — | extra entries per channel, merged over the defaults |
| `as` | `'span'` | element to render |
| `debug` | `false` | emit the scores as `data-*` attributes |
| `onAnalyze` | — | passage-level readout |

`useSemanticText(text, options)` returns the scored tokens and the runs, for
rendering it yourself. `analyze(text, options)` is the engine alone — no React
— and `styleFor(token, theme)` is the mapping alone.

Teach it your vocabulary with a lexicon:

```jsx
<SemanticText
  lexicon={{ valence: { flaky: -0.7, oncall: -0.4 }, salience: { rollback: 0.8 } }}
  text={incident}
/>
```

## Themes

`editorial` is deliberately quiet: high thresholds, small ranges, most words
left completely alone. If every word is styled, none of them is emphasised.
`loud` turns the same scores up for a headline or a demo. `monochrome` emits
no colour at all — weight, size and slant carry all four channels, for print,
e-ink, and for the fact that colour alone is not an accessible channel.

## Running it

```bash
node --test test/*.test.js      # engine + theme tests, no dependencies
npm install react react-dom     # only for the React render tests
python3 -m http.server          # then open /demo/
```

The demo is the fastest way to see it: five sample passages, live editing,
per-channel toggles, and a hover readout of every score.

`src/` has no dependencies and no build step — it is ESM that runs in Node and
in the browser as-is, using `createElement` rather than JSX so it needs no
transform. React is a peer, and only `SemanticText.js` imports it.

## What it gets wrong

Sarcasm, irony, and domain jargon it has not been taught — the lexicons are a
few hundred entries, so anything specialised needs a `lexicon` prop. It scores
English only. And it reads words, not arguments: it will not notice that a
calm sentence is describing a catastrophe.
