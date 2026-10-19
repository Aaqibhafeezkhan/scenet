# Print PDF emitter spike (#80)

## Decision in brief

Keep print as a third emitter that consumes resolved Core, not as an SVG-to-PDF conversion. The current SVG is a presentation format: it no longer carries reliable semantic distinctions between lettering, balloon borders, neutral backdrop tones and large near-black masses. Print needs those distinctions to assign inks and overprint correctly.

The first implementation should use ReportLab behind an optional `print` extra, provided the prototype proves that its PDF API can express the required black-plate separation and overprint state without private API hooks. Do not add it to the base dependencies. Do not claim PDF/X-1a or PDF/X-4 conformance until a real preflight tool validates the output and an output-intent profile is specified.

This is a design spike and acceptance plan, not evidence that a print-ready PDF has been validated. The one-panel prototype and manual preflight remain required before the issue's spike checkbox can be closed.

## Compared approaches

| Concern | ReportLab (BSD, optional extra) | Direct PDF writer |
|---|---|---|
| Runtime and licence | BSD licence is on the runtime allowlist; can be isolated in `scenet[print]` and kept out of the base/Pyodide install | No runtime dependency or new licence review |
| Vector primitives | Page paths, Bézier curves, clipping and transforms are available through a maintained PDF library | Every primitive, path operator, graphics state and resource dictionary must be written and audited by Scenet |
| CMYK and separations | Has CMYK colour support and documented overprint controls; the prototype must verify the exact separation/overprint behavior needed for lettering | Full control, but Scenet must correctly encode colour spaces, graphics-state dictionaries and resource references |
| Glyph outlines | Can draw paths generated from Core glyph outlines without relying on installed fonts | Can write glyph paths directly, but must own path serialization and graphics-state handling |
| Determinism | Must be demonstrated: normalize timestamps, document IDs, compression and object ordering; pin the library version | More control over bytes, but deterministic object ordering, metadata, streams and IDs become Scenet's responsibility |
| Maintenance and failure surface | Less PDF syntax to own; library behavior still needs focused tests | No dependency, but a larger security/correctness surface and more PDF-spec code to maintain |
| PDF/X | The library does not make a file PDF/X-conformant by itself | A hand-written PDF is not conformant by virtue of being small or deterministic; preflight remains necessary |

The decision is conditional on the prototype, not on API documentation alone. If ReportLab cannot emit a true black-only lettering separation with overprint using supported APIs, compare the maintenance cost of a small direct writer before accepting private ReportLab hooks.

## Minimal prototype to compare

Use one representative compiled panel containing:

- outlined dialogue and a balloon border;
- a neutral grey backdrop;
- a large near-black mass;
- a vector curve and a clipped shape;
- the atmosphere veil, if the fixture can produce one.

Generate the same fixture through both approaches from Panel Core. Do not convert the SVG. The PDF page geometry in this spike may use an explicitly documented temporary trim size and bleed; it must not be presented as the final page contract because #66 owns page dimensions and trim/bleed semantics.

Record for each implementation:

1. Lines of project-owned code and any private-library API use.
2. Repeated-build SHA-256 equality in a clean process, including across two separate invocations.
3. PDF page boxes and dimensions, with trim and bleed values checked against the temporary fixture.
4. Lettering and balloon strokes assigned to 100% K and set to overprint.
5. Grey tones represented as K tints, with large dark masses using the declared rich-black recipe.
6. Whether any unsupported primitive or atmosphere layer is dropped, rasterized or approximated.
7. A preflight report from a PDF/X-capable tool, or a clear record that conformance was not established.

Do not use a generic SVG converter for either prototype: it cannot recover the semantic identity of lettering from arbitrary paths.

## Proposed output contract

- The emitter takes resolved Core and makes no layout decisions.
- The page size, trim box and bleed box come from page Core once #66's contract is available; the emitter must not invent production dimensions.
- Lettering and balloon borders use a 100% K separation with overprint enabled.
- Neutral backdrop greys use K tints. Large near-black masses use an explicitly declared rich-black recipe, subject to the printer's ink limit.
- Non-neutral colours require declared CMYK values or an explicitly selected colour-management conversion. Do not silently convert sRGB values with an undocumented formula.
- Default lettering remains outlined paths. Live text, if ever supported, is a separate contract because it requires font embedding/subsetting.
- Metadata dates and document IDs are fixed or derived deterministically from content. Repeated builds must be byte-identical.
- The first release describes its output as print-oriented PDF, not PDF/X-1a, PDF/X-4 or PDF/UA, unless a suitable preflight check proves the corresponding claim.
- The atmosphere veil currently uses SVG `feTurbulence`, which has no direct PDF equivalent. The prototype must document a deliberate choice: rasterize only that layer, approximate it with vector shapes, or omit it with a diagnostic. It must not silently disappear.

## Dependency and project impact

If ReportLab wins the prototype:

- Add `reportlab` only to a `print` optional dependency group.
- Keep the import lazy so the base package, ordinary CLI commands and Pyodide do not import it.
- Add its exact runtime licence metadata to `.github/allowed-licenses.txt` only after running the existing licence gate against the actual installed package metadata.
- Add the dependency notice to `THIRD_PARTY_NOTICES.md`.
- Add `emit/pdf.py`, a PDF-specific deterministic output test, and the CLI format/output-naming behavior to `docs/reference/cli.md`.
- Keep PDF out of MCP's `render` response; the existing render contract is SVG resources.

If direct writing wins, omit the optional dependency and licence changes, but add focused tests for PDF path operators, colour spaces, overprint state, page boxes, metadata and resource references.

## Work that remains before the spike is complete

- [ ] Implement both minimal one-panel prototypes from the same Core fixture.
- [ ] Inspect the PDFs in a viewer and verify the separations/overprint and page boxes in a PDF/X-capable preflight tool.
- [ ] Record measured code size, deterministic hashes, the preflight tool/version and the observed results here.
- [ ] Resolve the atmosphere decision and whether the project will claim any PDF/X level.
- [ ] Revisit page dimensions and trim/bleed against the page Core contract from #66 before production output is implemented.

Until those checks are recorded, the recommendation above is provisional and the issue's spike is not complete.
