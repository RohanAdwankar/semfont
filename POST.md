# A font that reads what you wrote

*The live version of this post is `index.html`, where the engine sets every
word as you read and the box at the top takes your own text. Serve the repo and
open `/`, or publish it with GitHub Pages.*

Every emphasis in your document is a claim you made by hand. The file keeps the
bold and forgets the reason, so when the sentence changes, the emphasis stays
where it was.

semfont decides the typography from what the text means. Nothing here was
marked up:

> The migration ran clean on staging. In production it **deleted** the index,
> and the rollback <span style="color:#b4443a">failed</span> too. Nobody lost
> data, but the <mark>postmortem</mark> is going to be
> <span style="color:#b4443a">painful</span>.

`clean` went green, `deleted` gained weight, `failed` and `painful` went red,
and `postmortem` is marked because it sits in the clause after `but`, the half
of the sentence that turned.

## Four channels, four axes

Every token gets four scores, and each score drives a different axis, so they
compose rather than collide.

| channel | detects | moves |
|---|---|---|
| valence | how the text feels | colour |
| salience | what it points at | weight, size |
| surprise | where it turns | highlight |
| certainty | how sure it is | slant, opacity |

A word can be negative and hedged and the subject of the paragraph all at once,
and you see all three: dark red, leaning, heavy. Switch a channel off and the
other three carry on, independent down to the CSS.

## Negation, where the naive version dies

These two sentences are made of the same words.

> The launch was great and the numbers were excellent.
>
> The launch was **not** great and the numbers were **not** excellent.

The second goes red, and a paler red than a sentence of genuinely nasty words,
because `not great` registers as a complaint rather than a catastrophe. One
rule does it: on hitting a negator within three content words, flip the sign
and multiply by 0.74. Sentiment analysis has known that number since VADER, and
it still separates a demo from something you would ship.

## One millisecond, no model

Sending the paragraph to a model buys you sarcasm detection, at a few hundred
milliseconds, an API key, a network, and a copy of the reader's draft on
someone else's machine — per keystroke.

Four lexicons and about two hundred lines of rules score a page of prose in
roughly a millisecond, synchronously, offline, with the same answer every time.
Cheap enough to run inside the input event, during a server render, on a plane,
which is what lets it behave the way italics do.

The lexicons are small enough to read in one sitting and to argue with. When
the styling is wrong you can see which entry did it and fix it in a line, or
teach it your own vocabulary.

```jsx
<SemanticText
  lexicon={{ valence: { flaky: -0.7, oncall: -0.4 } }}
  text={incident}
/>
```

## Restraint

The first version styled every word it had an opinion about and looked like a
ransom note. The default thresholds now leave most words alone — a paragraph
gets a handful. Emphasis works by contrast, so it exists only relative to text
that nothing happened to.

Colour also never carries a channel by itself. The `monochrome` theme rides all
four on weight, size, slant and tracking, which is both the accessible answer
and the better looking one in print.

## Where it fails

It reads words rather than arguments, so a calm sentence describing a
catastrophe goes straight past it. Sarcasm defeats it. It speaks only English.
A model beats it on all three, and could never be a font.

---

[github.com/drapoz/semfont](https://github.com/drapoz/semfont) — MIT.
