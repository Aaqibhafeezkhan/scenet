# Native print PDF emitter (#80)

The `scenet build --pdf` path emits directly from resolved Panel Core and Page Core. It does not parse or convert SVG. Install the optional dependency with `pip install 'scenet[print]'`.

## Implemented in this branch

- CMYK PDF output through ReportLab, kept out of base dependencies.
- Vector geometry for tonal masses, actors, face marks, balloons, captions, and outlined glyphs.
- Neutral colours map to K-only tints; non-neutral RGB values are converted to process CMYK using a deterministic formula.
- 3 mm bleed around the trim region; page aspect ratio is preserved and fitted within a letter-sized maximum.
- Creation/modification metadata is derived from `SOURCE_DATE_EPOCH` (default epoch zero), and the document ID is derived from Core JSON.
- `--pdf` writes a single multi-page PDF; without page layout, each panel becomes a PDF page.

## Known limitations

- This is print-oriented CMYK PDF, **not certified PDF/X-1a or PDF/X-4**. No output-intent ICC profile or external preflight is supplied.
- PDF/X requirements for 100% K lettering overprint and large rich-black recipes are not yet complete. Current outlines are K-only, but overprint state and rich-black intent need implementation.
- The Core atmosphere veil is omitted because the source stores turbulence parameters rather than a PDF-ready image; no substitute texture is silently generated.
- Supplied raster images are not yet embedded by this emitter.
- This initial page geometry is a letter-sized maximum, not a printer-specific production specification. Bleed defaults to 3 mm.
- The emitter has not been executed or preflighted in this change.

The output must not be described as PDF/X-conformant until a PDF/X-aware preflight validates the exact printer profile, boxes, colour spaces, transparency policy, and overprint behavior.
