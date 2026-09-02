# iOS release status and market-intelligence roadmap

Last updated: 2026-09-02

## Release status

The Flutter iOS client, version `1.0.0+18`, has been uploaded to App Store Connect and is **Waiting for Review**. This is the current submission status supplied by the product owner. It is not an approval, a public release, or a commitment about Apple's review timing.

No application behavior is changed by this roadmap. During review, keep the production API and the App Review account path available, keep the published legal/support links healthy, and avoid changing the submitted binary's user-facing claims or review access. If a later build is needed, record the new build number and review reason here before upload.

Oryntra remains educational market-analysis and simulated paper-trading software. It does not place orders, connect to brokerages, custody funds, manage money, or provide individualized financial advice.

## Why broaden the research surface

OHLCV is the correct foundation for symbol-level price, trend, volatility, and liquidity observations. It is not enough to explain whether an observed setup is isolated or occurring alongside a broad move, a sector rotation, or a changing macro environment. The next direction is therefore three connected but independently auditable layers:

1. **Symbol layer:** existing normalized OHLCV, indicators, patterns, and setup evidence.
2. **Market-map layer:** derived cross-sectional snapshots and heatmaps that describe breadth, leadership, dispersion, and concentration for a defined universe.
3. **Macro layer:** point-in-time public economic and financial observations that describe the environment in which a research result occurred.

The layers must remain separate. A broad heatmap is not a buy/sell list, and a macro observation is not a causal explanation or a forecast. The user interface should state the measurement window, universe, source coverage, availability time, and missing-data rate beside any visual.

## Existing foundation

The repository already has the important first component of the macro architecture:

- `corporate_repository.py` stores public corporate facts and `macro_observations` with `observation_at`, `available_at`, units, source class, source URL, metadata, and an import timestamp.
- The supported macro panel currently covers policy rate, 2-year and 10-year yields, credit spread, and inflation. `macro_panel()` applies each observation only after `available_at`, preventing a research run from using a fact before it was public.
- Quant Lab records provenance and coverage, while the public payload boundary prevents raw OHLCV arrays from being returned as a public product response.

New work should extend these contracts rather than introduce a disconnected “macro dashboard” or duplicate store.

## Target data model

### Shared observation contract

Every new dataset should use an explicit observation contract, whether it is stored in a new table or mapped through the existing repository:

| Field | Purpose |
| --- | --- |
| `metric_id` and `definition_version` | Stable meaning and calculation version; names alone are insufficient when formulas change. |
| `entity_type` and `entity_id` | Identifies a symbol, sector, industry, ETF, universe, or macro series without overloading ticker strings. |
| `observation_at` | The market or economic period the value describes. |
| `available_at` | The earliest timestamp Oryntra could legitimately use the value. This is the research anti-lookahead boundary. |
| `value`, `units`, and `transform` | Raw published value and any documented derived transform, such as percent change or z-score. |
| `source_class`, `source_url`, `source_version`, and `license_scope` | Provenance and permitted product use; no source should be assumed redistributable. |
| `quality_status` and `coverage` | Missing, stale, revised, partial, or validated state must be queryable rather than hidden. |
| `dataset_fingerprint` | Makes a heatmap or research run reproducible from the source records and calculation version. |

Retain revisions instead of overwriting them. For macro series, a release can be revised after first publication; the record used in a historical run must be the vintage available at that time. Existing `macro_observations` already supports multiple `available_at` records. A migration should add an explicit `revision_id` or source-version field only when the collector begins ingesting revisions, then preserve the existing unique key semantics.

### Market-map records

Build heatmaps from server-side derived snapshots, not client-side bulk raw bars. A future `market_snapshot` header and `market_snapshot_cells` table can represent one repeatable map:

| Record | Essential fields | Notes |
| --- | --- | --- |
| `market_universe` | universe ID, membership version, effective dates, inclusion rule | A heatmap cannot be interpreted without knowing its constituents. |
| `market_snapshot` | snapshot ID, as-of time, universe ID, timeframe, metric version, source/fingerprint, coverage | Header for one reproducible calculation. |
| `market_snapshot_cell` | snapshot ID, entity ID, metric ID, value, rank/percentile, quality flag | One derived value for a symbol, industry, sector, or ETF. |
| `market_aggregate` | snapshot ID, group ID, breadth counts, dispersion, concentration, coverage | Supports sector/industry summaries without exposing all vendor data. |

The first metrics should be derived from data Oryntra already validates: percent of constituents above moving averages, advance/decline counts, new-high/new-low counts, return dispersion, relative volume coverage, sector-relative return, and concentration of gains/losses. Each requires a fixed universe membership version and a declared session-close policy. Do not label any visualization “real time” unless timestamps, exchange calendars, and provider entitlements support that claim.

### Macro expansion

Expand the existing macro catalog in small, source-specific increments rather than importing a broad ungoverned feed. Candidate categories are labor conditions, growth/activity, inflation detail, policy expectations, term structure, credit conditions, and currency/commodity reference series. For every proposed metric, define:

1. authoritative public source and its permitted use;
2. unit, frequency, observation period, release calendar, and revision behavior;
3. `available_at` convention, including an explicit release-time timezone;
4. transformation rules and whether they are level, change, surprise, or percentile;
5. missing/revision handling; and
6. a baseline-ablation test showing whether the feature changes any research conclusion after costs and chronological holdout.

Macro data is likely to be lower frequency and more revision-prone than daily market history. The collector should therefore append vintages, never backfill a historical panel with later revisions, and expose freshness and coverage as first-class fields.

## Service and client boundary

The implementation sequence should be server-first:

1. Add a versioned market-intelligence repository and migrations, with validation tests for universe membership, duplicate timestamps, stale inputs, and point-in-time eligibility.
2. Produce immutable, derived snapshot payloads through authenticated/read-scoped endpoints. Include `as_of`, metric definitions, coverage, provenance summary, and dataset fingerprint in every response.
3. Add a small mobile/web presentation that consumes only the derived contract: heatmap cells, legends, filters, timestamps, and quality notices. It should not receive provider keys or raw bulk market data.
4. Keep heatmap exploration separate from the scanner's educational setup result. Any link between them must describe context (for example, “sector breadth was weak”) and must not turn a research metric into a recommendation.
5. Admit market-map and macro features to Quant Lab only through an as-of feature panel with fixed transformations, chronological holdouts, and ablations against the current OHLCV/corporate baseline.

Feature flags should keep these additions private until data licensing, freshness behavior, and point-in-time tests are verified. Public availability requires a separate review of provider/exchange rights, rate limits, data retention, and the product's no-redistribution boundary.

## Phased roadmap

### Phase 0 — App Store review and release hygiene

- Maintain review access and production-service availability while the current build is Waiting for Review.
- Record the final Apple status and any review feedback; do not treat submission as approval.
- Keep the submission's educational, non-advisory positioning consistent with legal and App Review materials.

### Phase 1 — Market-map foundation

- Define a small, licensed universe and versioned membership rules.
- Implement the shared observation contract and derived market-snapshot schema.
- Calculate a daily end-of-session breadth map with source coverage, staleness, and reproducible fingerprints.
- Test snapshot determinism, universe changes, corporate-action handling, unavailable symbols, and public-payload exclusion of raw bars.

### Phase 2 — Macro provenance and research integration

- Formalize the macro metric registry and collector conventions around the existing `macro_observations` store.
- Preserve release vintages and validate `available_at` against known release timestamps.
- Add a macro context panel with units, source links, last release, next expected release when available, and revision notice.
- Run fixed, chronological ablations to compare the existing baseline with macro/breadth-enriched variants. Report coverage and failure modes, not just headline return.

### Phase 3 — Controlled product surfaces

- Ship a read-only heatmap and macro-context view only after rights, quality, and interaction states are verified.
- Add saved research views and comparison reports with their fingerprints, metric definitions, and observation timestamps.
- Keep experimental ranked views private until they meet the same holdout, audit, legal, and UX standards as any other research feature.

## Acceptance criteria

The roadmap is ready for implementation only when each delivery can demonstrate all of the following:

- A user can identify what every color, rank, and aggregate measures, for which universe, and at what time.
- A historical research replay uses only records with `available_at` no later than the simulated decision time.
- A missing, stale, partial, or revised dataset produces a visible quality state rather than a silently complete-looking map.
- Public endpoints return derived observations and provenance summaries without raw vendor data or provider credentials.
- Added features are evaluated against a fixed OHLCV/corporate baseline with chronological holdouts and modeled costs.
- Copy continues to describe observations and educational research, not personalized recommendations, expected returns, or automated execution.

## Current limitations

This document is a product and architecture direction, not an implementation claim. The repository currently has no dedicated market-heatmap snapshot service, collector, endpoint, or mobile surface. Macro support already exists in Quant Lab for the five supported metrics above, but expanded catalog, release-vintage ingestion, and a user-facing macro panel remain future work. Market-data licensing and redistribution permissions must be verified for each provider and public surface before implementation or release.
