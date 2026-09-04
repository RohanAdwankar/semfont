# A font that reads what you wrote

*The live version of this post is `index.html` — same words, but every
specimen is rendered by the engine and the opening one is editable. Serve the
repo and open it, or publish it with GitHub Pages.*

Every emphasis in your document is a lie you told by hand. You bolded the
word because it mattered — but the file only records the bold, not the
mattering. Change the sentence and the emphasis stays where it was.

`semfont` inverts that. You hand it plain text; it decides the
typography from what the text means:

> The migration ran clean on staging. In production it **deleted** the index,
> and the rollback <span style="color:#b4443a">failed</span> too. Nobody lost
> data, but the <mark>postmortem</mark> is going to be
> <span style="color:#b4443a">painful</span>.

Nothing in that paragraph was marked up. `clean` went green, `deleted` gained
weight, `failed` and `painful` went red, and `postmortem` got highlighted
because it sits in the clause after `but` — the half of the sentence that
turned.

The engine is not a model. It is four lexicons and about two hundred lines of
rules, which is the whole point.

## Four channels, four axes

A single "sentiment colour" is a gimmick. What makes this read like typography
rather than like a highlighter is that the scores are independent and land on
different axes, so they compose:

| channel | what it detects | what it moves |
|---|---|---|
| valence | how the text feels | colour |
| salience | what it is pointing at | weight and size |
| surprise | where it turns | highlight |
| certainty | how sure it is | slant |

A word can be negative *and* hedged *and* the subject of the paragraph, and
you can see all three at once: dark red, leaning, heavy. Try doing that with
bold and italic.

## Four cases where this is more than a toy

**1. Incident reports and log tails.** Severity is already in the words —
`crash`, `corrupt`, `rollback`, `WARNING`. A log viewer that renders it means
you find the bad line by looking, not by reading.

**2. Confirming a dangerous command.** Every `rm -rf` prompt looks the same as
every harmless one, which is exactly why nobody reads them. Feed the
confirmation text through the same engine and the danger sizes itself:

> **WARNING**: this operation is **irreversible**. It will drop **1.2TB** of
> **production** user data **immediately** and there is no undo.

`WARNING`, `irreversible` and `immediately` are in the salience lexicon;
`1.2TB` is a magnitude; `production` earned its weight by being the word the
sentence keeps circling. Nobody wrote the styling.

**3. Seeing your own hedging.** Run a draft through the certainty channel and
every `might`, `maybe`, `seems`, `arguably` leans away from you, and drags its
clause with it:

> I think this *might* be the culprit, though honestly the profiler output is
> unreadable. *Maybe* the allocator is fine. The regression is definitely
> real: p99 doubled and never came back.

The first two sentences visibly lean; the third stands up straight. That is a
writing tool nobody has to be told how to use.

**4. Negation, which is where naive versions die.** The two halves here are
the same words:

> The launch was great and the numbers were excellent.
> The launch was **not** great and the numbers were **not** excellent.

The first renders green. The second renders red — but *paler* red than a
sentence full of genuinely nasty words, because `not great` is a complaint,
not a catastrophe. The rule is one line: on hitting a negator within three
content words, flip the sign and multiply by 0.74. Sentiment analysis has
known that number since VADER; it is still the difference between a demo and
a thing you would ship.

## Why the boring engine is the feature

The obvious 2026 implementation is: send the paragraph to a model, get spans
back. It would handle sarcasm. It would also cost 400ms, an API key, a
network, and a copy of the user's draft on someone else's machine — per
keystroke.

`analyze()` is synchronous and pure. A page of prose scores in about a
millisecond, so the typography can update inside the input event, during SSR,
in a `useMemo`, offline. That gap is not an optimisation; it is the difference
between a feature you invoke and a *font* — something that is simply how the
text looks, the way italics are.

The lexicons are small enough to read in one sitting and to argue with, which
matters more than it sounds: when the styling is wrong you can see exactly
which entry did it and fix it in one line. Nobody has ever fixed a model that
way.

```jsx
<SemanticText
  lexicon={{ valence: { flaky: -0.7, oncall: -0.4 } }}
  text={incident}
/>
```

## Restraint is the design

The first version styled every word it had an opinion about, and it looked
like a ransom note. Every threshold in the default theme is now high enough
that most words come out untouched — a paragraph typically styles four or five
of them. Emphasis is a contrast effect: it only exists relative to text that
was left alone.

The other constraint is that colour is never the only signal. The
`monochrome` theme carries all four channels on weight, size, slant and
tracking with no colour at all — which is both the accessible answer and,
honestly, the better looking one in print.

## Where it fails

It reads words, not arguments. It will not notice that a perfectly calm
sentence is describing a catastrophe, it does not get sarcasm, and it only
speaks English. A model would beat it on all three.

It would also never be a font.

---

Code, demo and tests: [drapoz/semfont](https://github.com/drapoz/semfont) — idea
[#1455](https://github.com/drapoz/0/issues/1455).
