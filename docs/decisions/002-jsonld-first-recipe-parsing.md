# ADR-002: JSON-LD First Recipe Parsing

## Status

Accepted

## Context

Most modern Swiss recipe sites (Fooby, Migusto, Swissmilk, Schweizer Fleisch) embed schema.org `Recipe` JSON-LD in their pages. This structured data contains title, ingredients, steps, times, yield, images, and keywords in a standardised format.

Custom HTML parsing per site is fragile, expensive to maintain, and breaks on redesigns.

## Decision

The generic JSON-LD parser (using `extruct`) is the default extraction strategy. Per-site HTML-based overrides are added only when:

1. JSON-LD is entirely missing from the page, OR
2. JSON-LD is present but missing critical fields (ingredients, steps) that ARE visible in the HTML.

Before writing any custom HTML parsing code for a source, manually inspect at least 5 representative recipes to validate JSON-LD coverage.

## Consequences

- **Faster adapter development:** a new source with good JSON-LD needs only `discover()` logic; `fetch()` delegates to the generic parser.
- **Lower maintenance:** schema.org JSON-LD is stable across site redesigns (it's typically injected server-side, not in the visual template).
- **Graceful degradation:** if JSON-LD disappears from a source in the future, we add a per-site override at that time — not preemptively.
- **Validation task:** probe each source's JSON-LD coverage before committing to an adapter (documented in docs/03-data-sources.md).
