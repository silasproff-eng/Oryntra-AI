# iOS Release Status

Last updated: 2026-09-03

> The filename is retained to avoid breaking existing links. This document is now a factual release-status record, not a feature roadmap.

## Current state

The Flutter iOS client declares version `1.0.0+18`. The product owner reported the uploaded build as **Waiting for Review** in App Store Connect on 2026-09-02.

That means Apple had received the selected build and the submission was queued for review at the time of the report. It does not mean the build has been approved, released, or made available in the App Store. The repository has no authenticated App Store Connect integration, so the current Apple-side state must be checked directly before making a new status claim.

## Submitted product boundary

The current source is an educational market-intelligence and historical-research client. It includes account/provider onboarding, Scanner, Watchlist, Paper, Quant Lab, Account, notifications, alerts, device-local research reports, optional ads/consent, TradingView chart presentation, and a latest-scan widget. It does not connect to a brokerage or place trades.

## During review

- Keep the production API, review credentials, and legal/support URLs available.
- Preserve the reviewed binary’s backend contract, especially authentication and browser-upload analysis routes.
- Record any rejection message or requested metadata change verbatim before preparing a replacement build.
- If a replacement binary is required, increment the build number and re-run backend, Flutter, plist, archive, device, and production checks appropriate to the change.
- Do not describe a user-reported review state as independently verified.

## Product ideas are not commitments

No market heatmap, expanded macro dashboard, fire-sale engine, ML portfolio optimizer, or other discussed research idea is approved by this file. The current implementation boundary and explicit non-features are documented in `docs/FEATURES_MODELS_AND_ARCHITECTURE.md`. Future additions should be discussed and accepted before implementation or roadmap language is added.
