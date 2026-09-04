# semantic font

Typography that modulates on meaning instead of on markup. Negative things
render red, important things get heavier, surprising things get highlighted,
hedged things lean, and nothing in the pipeline is a model.

Idea: [#1455](https://github.com/drapoz/0/issues/1455).

```jsx
import { SemanticText } from 'semfont';

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
a *font* rather than as a feature: it can run on every keystroke, in a
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
threshold comes from this text rather than from a global corpus, which is how the
topic terms of a paragraph float up without anyone tagging them.

## API

```js
import { SemanticText, useSemanticText, analyze, themes, styleFor } from 'semfont';
```

`<SemanticText>` props:

| prop | default | |
|---|---|---|
| `text` / `children` | none | the passage |
| `theme` | `'editorial'` | `'editorial'`, `'loud'`, `'monochrome'`, or a theme object |
| `channels` | all four | which channels may style |
| `sensitivity` | `1` | global gain on every score |
| `lexicon` | none | extra entries per channel, merged over the defaults |
| `as` | `'span'` | element to render |
| `debug` | `false` | emit the scores as `data-*` attributes |
| `onAnalyze` | none | passage-level readout |

`useSemanticText(text, options)` returns the scored tokens and the runs, for
rendering it yourself. `analyze(text, options)` is the engine alone, without
React, and `styleFor(token, theme)` is the mapping alone.

Teach it your vocabulary with a lexicon:

```jsx
<SemanticText
  lexicon={{ valence: { flaky: -0.7, oncall: -0.4 }, salience: { rollback: 0.8 } }}
  text={incident}
/>
```

## Taking only the part you want

The four channels are independent all the way down, and there are four places
to cut, from coarsest to finest.

**Pick channels.** Nothing but colour:

```jsx
<SemanticText text={incident} channels={['valence']} />
```

Every other channel scores 0 and emits nothing, so the spans carry exactly one
CSS property. `demo/react.html` mounts the same paragraph three times this
way.

**Pick axes.** A channel's typography is theme data, so weight without the
size change is a theme, not a fork:

```jsx
<SemanticText theme={{ size: { range: 0 } }} text={incident} />
```

`color: null` and `highlight: null` switch those off the same way. That is
all `monochrome` is.

**Keep the scores, render it yourself.** `useSemanticText` hands back the
tokens and runs, so the styling can be your own classes, a `<mark>`, an
ARIA annotation, a minimap, anything.

**Or skip the typography entirely.** `analyze(text)` is the engine alone: no
React, no CSS, four numbers per token. It is also useful as a plain text
signal: sorting a log by salience, flagging hedged sentences in review.

## As a static site

Everything is client-side; there is no server component to any of it.

`src/analyze.js` and `src/theme.js` import nothing at all, so a static page
can load them directly, which is exactly what `demo/index.html` does, and it
needs only a file server (`python3 -m http.server`, GitHub Pages, an S3
bucket). ES modules do need HTTP rather than `file://`.

`SemanticText.js` imports `react` as a bare specifier. Inside any bundler or
static-site generator that resolves itself. In a page with no bundler, one
import map is the whole setup:

```html
<script type="importmap">
  { "imports": { "react": "https://esm.sh/react@18.3.1",
                 "react-dom/client": "https://esm.sh/react-dom@18.3.1/client" } }
</script>
```

See `demo/react.html`, which runs the component with no build step of any
kind. And because `analyze()` is synchronous and pure, the component renders
under `renderToStaticMarkup`, so a static site can prerender the typography
into the HTML and ship no JavaScript at all.

## Themes

`editorial` is deliberately quiet: high thresholds, small ranges, most words
left completely alone. If every word is styled, none of them is emphasised.
`loud` turns the same scores up for a headline or a demo. `monochrome` emits
no colour at all: weight, size and slant carry all four channels, for print,
e-ink, and for the fact that colour alone is not an accessible channel.

## The post

`index.html` at the repo root is the write-up, and the engine sets all of it:
every word of the prose is scored and styled at load, the rail re-runs the
whole page when you change a channel, the sensitivity or the theme, and the box
at the top takes the reader's own text. It imports `src/` directly, so there is
no copy of the engine to keep in sync and no build step. Serve the repo and
open `/`, or turn on GitHub Pages for `main` to publish it as-is. `POST.md` is
the same words in plain Markdown.

## Running it

```bash
node --test test/*.test.js      # engine + theme tests, no dependencies
npm install react react-dom     # only for the React render tests
python3 -m http.server          # then open / for the post, /demo/ for the demo
```

The demo is the fastest way to see it: five sample passages, live editing,
per-channel toggles, and a hover readout of every score.

`src/` has no dependencies and no build step. It is ESM that runs in Node and
in the browser as-is, using `createElement` rather than JSX so it needs no
transform. React is a peer, and only `SemanticText.js` imports it.

## What it gets wrong

Sarcasm, irony, and domain jargon it has not been taught. The lexicons are a
few hundred entries, so anything specialised needs a `lexicon` prop. It scores
English only. And it reads words, not arguments: it will not notice that a
calm sentence is describing a catastrophe.
