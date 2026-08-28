# Oryntra V1.0 Release Candidate — local review

Status: **local release candidate; not committed, pushed, or submitted to GitHub.**

## Included

- Public corporate-data repository with source provenance, disclosure timestamps, point-in-time eligibility, and a local import API.
- Rates/yield-curve, credit-spread, inflation, and policy-rate inputs, used only after their recorded availability time.
- Corporate-quality sleeve, probabilistic regime engine, and regime-conditioned sleeve weights.
- Portfolio caps, volatility scale-down, liquidity-aware next-session cost proxy, factor/relative-value attribution, and strategy-health/alpha-decay diagnostics.
- V1.0 Quant chronological train/validation/test separation, outcome-horizon purge gaps, train-only categories, and removal of ticker/legacy-scanner-confidence features.
- Scanner corporate context as structured display evidence only; no LLM-driven numeric prediction.
- Visible product branding and public analysis labels standardized as **Oryntra V1.0**; historical internal engine identifiers remain only as compatibility IDs.
- Account-scoped Polygon and Twelve Data key settings, encrypted at rest, never returned after save, and used only for the signed-in user's provider request.
- Public-site configuration boundary: account sign-in required for analysis and Quant Lab; user-owned provider keys can be required on cache misses to avoid using platform credentials.
- Terms and Privacy Policy updated for optional user-owned provider keys, provider-plan limits, separate provider terms, removal, and the no-redistribution/public-rights boundary.
- Rule Mirror-structured Oryntra account flow with the V1.0 slogan, legal consent, and a required provider-key onboarding step before scanner or Quant Lab requests.
- Ad placements are blank by default; web advertising requires the explicit `WEB_ADS_ENABLED=true` and `ADSENSE_VERIFY_ENABLED=true` deployment switches, plus configured slot IDs.

## Verified locally

- 33 backend tests, including encrypted provider-key isolation, authenticated API save/status/remove checks, and explicit Polygon/Twelve Data selection with only the requesting user's key.
- Python compilation, JavaScript syntax validation, diff validation, and a real local `/health` response showing V1.0.
- Account/key API regression checks rerun after the onboarding UI update.

## Required before a V1 tag or GitHub action

1. Configure the encryption key through the deployment secret manager, register a test account, save/remove each provider key, and confirm neither key is returned or written to logs.
2. In a browser, run a cache-only Quant Lab report, import a small timestamped corporate/macro sample, and verify that coverage, regimes, liquidity diagnostics, attribution, and health sections render.
3. Run one V1.0 Quant training job with real dated outcomes and inspect validation vs untouched test results.
4. Review public-source provenance and the exact data-provider/exchange license restrictions before enabling public derived analysis or Quant Lab.

## Intentionally excluded

No brokerage link, real-money order creation, automated execution, smart-order routing, or investment recommendations. The execution layer is a daily historical cost model used for research and paper simulation only.
