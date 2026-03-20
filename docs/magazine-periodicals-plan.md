# Magazine And Periodicals Support Plan

Branch: `feature/magazine-periodicals-support`

## Goals

- Add PublicationIssue support for periodicals in OPDS parsing and serialization.
- Support OPDS2 magazine linkage through both `belongsTo.series` and custom `belongsTo.Magazine`.
- Add streaming periodical delivery support using Periodical medium.
- Add a feature-configurable top-level Periodicals lane.

## Confirmed Decisions

- Support both OPDS2 linkage inputs:
  - `belongsTo.series`
  - `belongsTo.Magazine`
- Streaming periodicals should infer `Periodical` medium.
- The top-level Periodicals lane should be feature-configurable.

## PR Plan

### PR 1: Publication Type Foundation

- Add `PublicationIssue` to the OPDS schema.org publication type enum.
- Update OPDS2 serializer to emit `PublicationIssue` for Periodical medium.
- Add focused serializer coverage for Periodical output.

### PR 2: OPDS2 Standard Series Import

- Extract `belongsTo.series` into `BibliographicData.series` and `series_position`.
- Normalize numeric issue positions safely.
- Add extractor coverage for standard OPDS2 series linkage.

### PR 3: RWPM Parser Hardening For Magazine Collections

- Extend RWPM `BelongsTo` to support custom `Magazine` data.
- Avoid validation failures from vendor-supplied non-numeric issue labels.
- Add parser tests for standard and custom collection metadata.

### PR 4: Dual-Path Magazine Linkage Extraction

- Update extractor precedence:
  1. `belongsTo.Magazine`
  2. `belongsTo.series`
- Populate `BibliographicData.series` from either source.
- Add precedence and fallback tests.

### PR 5: Streaming Periodical Delivery Mechanism

- Add `STREAMING_PERIODICAL_CONTENT_TYPE`.
- Extend streaming mappings and importer helpers.
- Map streaming periodicals to Periodical medium.
- Add delivery mechanism and extractor coverage.

### PR 6: Library Setting For Top-Level Periodicals Lane

- Add a library setting to enable a top-level Periodicals lane.
- Expose and validate the setting through the existing library configuration flow.
- Add configuration and admin API tests.

### PR 7: Feature-Configurable Top-Level Periodicals Lane

- Preserve current lane behavior when the setting is off.
- Create a dedicated top-level Periodicals lane when the setting is on.
- Add lane ordering and visibility coverage.

### PR 8: End-To-End Regression And Vendor Follow-Up

- Add higher-level fixtures for OPDS2 periodicals.
- Validate parser, serializer, streaming, and lane behavior together.
- Reassess vendor-specific follow-up work if additional gaps appear.

## Risks To Watch

- OPDS2 `position` values may be non-numeric and fail validation early.
- Streaming helper logic exists in multiple importer paths and must stay aligned.
- New streaming periodical delivery may require fulfillability updates depending on client support.
- Some existing metadata and lane assumptions are still book-centric.