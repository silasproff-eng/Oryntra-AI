# Oryntra V1.0 Release Readiness

Last documentation review: 2026-09-03

## Status

- Repository product version: `1.0.0`.
- Flutter package/build: `1.0.0+18`.
- App Store Connect state: **Waiting for Review**, reported by the product owner on 2026-09-02. This repository cannot live-verify Apple’s current state.
- Public scanner model label: **V1.0 Official Momentum** (`official` internally; older source text also calls the policy V7).
- V8, VAI 1.0, and VAI 2.2 remain research candidates, not public-scanner replacements.
- Quant Lab is a separate V1.0 historical portfolio-research system.

## Submitted mobile feature set

The current Flutter source contains account onboarding, browser-direct provider connection, Scanner, Watchlist, Paper, Quant Lab, Account, TradingView chart presentation, notification preferences, tracked-symbol alerts, local stored Quant Lab reports, optional consent-gated ads, background time for Quant Lab, and the latest-scan iOS widget.

The source does not prove every capability is active in the reviewed binary or production environment. Provider requests require a compatible account/plan and browser/mobile network access. Notifications require user permission plus configured native/server push infrastructure. Ads require consent and explicit unit configuration. Quant Lab requires the matching backend route and analysis policy.

## Verification required for a release claim

| Layer | Required evidence | What it proves |
| --- | --- | --- |
| Backend static | Python compile, full tests, JavaScript syntax, documentation regeneration | Source contracts and parsability |
| Backend runtime | Start intended mode and receive a valid `/health` response | Actual local process and route composition |
| Browser | Signed-in provider setup, scan, watchlist, paper trade, backtest, Quant Lab, settings, narrow/desktop states | User-visible web behavior |
| Flutter static | `flutter analyze`, Flutter tests, plist/privacy lint | Dart/native configuration consistency |
| iOS build | Unsigned release build, then signed Xcode archive | Compilation and signing/archive readiness |
| Device | Provider setup, scan, notification permission/delivery, background Quant Lab, TradingView, widget refresh, account deletion | Real iOS integration behavior |
| Production | Health, auth, provider/upload paths, durable database preservation, legal/support URLs | Deployed environment behavior |
| App Store | App Store Connect status and Apple review result | Submission/approval/publication state |

Passing a lower row is not implied by passing a higher row. In particular, backend tests do not prove a device build, and a successful archive does not prove App Store approval.

## Release boundaries

- No brokerage connection, real-money orders, autonomous execution, or individualized investment advice.
- Browser/mobile direct provider keys remain on the user’s device; Oryntra receives normalized bars for the requested calculation, not the key.
- Public scan payloads exclude raw OHLCV history.
- Private research, server-provider, cache, Pattern Lab, VAI training, and Pro routes must remain behind explicit operating-mode controls.
- Market-data display, storage, and redistribution rights must be evaluated against the actual provider plan.
- Database, market cache, and trained-model artifacts are persistent operational state and must not be overwritten by a source deployment.

## Documentation gate

Before a new build or model label is released:

1. Update `docs/FEATURES_MODELS_AND_ARCHITECTURE.md` for behavioral changes.
2. Update `server/QUANT_LAB.md` for research-mechanics changes.
3. Regenerate `docs/Oryntra_AI_Master_Technical_Documentation.txt`.
4. Record the exact static, runtime, browser, device, deployment, and App Store checks actually performed.
5. Do not convert a research candidate, local model promotion, or favorable historical result into a public-performance claim.
