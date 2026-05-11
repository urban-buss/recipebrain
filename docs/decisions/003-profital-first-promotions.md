# ADR-003: Profital-First Promotions

## Status

Proposed (validate Profital coverage before committing)

## Context

Swiss grocery retailers (Migros, Coop, Denner, TopCC) each publish promotion data differently:

- **Migros:** weekly flyer as PDF + partial web listings
- **Coop:** weekly flyer as PDF + web listings + Supercard offers
- **Denner:** weekly flyer PDF
- **TopCC:** weekly PDF catalogue

Building per-retailer scrapers is expensive and fragile. Aggregators exist:

- **Profital:** aggregates most Swiss retailer leaflets in digital form
- **Bring!:** shopping list app with deal integration
- **Blattabock:** leaflet digitisation service

## Decision

v1 ships a single Profital adapter only. Per-retailer adapters are added later only if Profital coverage proves inadequate for the meal-planning use case (e.g., missing specific product prices or categories needed for ingredient matching).

## Consequences

- **Single point of failure:** if Profital changes their data format or access method, promotions are unavailable until the adapter is updated.
- **Coverage gaps:** Profital may not cover all retailers or all promotion types (e.g., app-only Supercard deals).
- **Simpler v1:** one adapter to build, test, and maintain instead of 4+.
- **Validation needed:** before committing, verify that Profital provides sufficient product-level detail for ingredient matching (not just "20% off meat" but specific products).
