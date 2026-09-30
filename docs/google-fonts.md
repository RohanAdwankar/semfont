# Submitting the Markdown font to Google Fonts

`fontbakery check-googlefonts` on the widened build: 0 FAIL, 0 ERROR, 6 WARN.
The warnings are the post table version, average char width, missing kerning,
math sign widths, overlapping path segments inherited from Liberation Sans, and
a check that needs an article page. None blocks a submission.

The checks that read METADATA.pb, the license file and the name table did not
run, because they need the font to sit in a google/fonts family directory.

## What is left

- Pick a family name nobody has. `markfont` is unchecked.
- Add `OFL.txt` with the Liberation copyright lines intact. Liberation is OFL
  1.1 with "Liberation" as a reserved font name, and this font is renamed, so a
  derivative is allowed.
- Generate `METADATA.pb` and the description with `gftools add-font`.
- Open the pull request against google/fonts. That repository is reviewed by
  people, and a font whose outlines are all Liberation Sans is the part most
  likely to be questioned.
