# Submitting the Markdown font to Google Fonts

## Where it stands

The family name `Markfont` is free. It was checked against all 1,950 families
in Google's public catalogue, exact and near matches both. A trademark search
was not done.

`fontbakery check-googlefonts` on the widened build reports no failures. One
warning is expected and stays: `name/rfn`, because the copyright line quotes
Liberation's own "Reserved Font Name Liberation". That is Liberation's
reservation and the licence asks for its notices to be kept as written. This
font reserves no name.

The checks that read METADATA.pb need the font inside a google/fonts family
directory and have not run. Google Fonts has accepted unusual functional fonts
before, Wavefont among them, so the idea is not what will be questioned. The
outlines are all Liberation Sans, and that is.

## One input is missing

Google requires the first line of OFL.txt, and nameID 0 in the font, to read
`Copyright YEAR The Markfont Project Authors (git url)`, with the URL of the
repository the font is maintained in. That repository does not exist yet, so
the URL is an argument and nothing here guesses it.

```
python3 google-fonts/prepare.py \
    --repo-url https://github.com/<owner>/<repo> \
    --base /usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf
```

That writes `google-fonts/ofl/markfont/Markfont-Regular.ttf` and `OFL.txt`,
then runs the thirteen license and name checks and prints the result of each.
The Liberation notices are carried on the first line, because Google's checks
accept changes to that line only and the licence requires the originals.

## Then

- Run `gftools add-font` against a checkout of google/fonts to generate
  METADATA.pb and the description. It needs the checkout, which is why it is
  not done here.
- Open the pull request against google/fonts.
