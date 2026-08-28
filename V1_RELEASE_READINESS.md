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
- Browser-direct Polygon / Massive and Twelve Data key connection: keys remain in browser memory, go directly to the chosen provider, and are never received, stored, or logged by Oryntra.
- Public-site configuration boundary: account sign-in is required for analysis and Quant Lab; browser-direct endpoints accept validated daily bars, process them in memory, and return derived research only.
- Terms and Privacy Policy document the browser-direct key path, in-memory raw-bar handling, provider-plan limits, separate provider terms, and the no-redistribution/public-rights boundary.
- Rule Mirror-structured Oryntra account flow with the V1.0 slogan, legal consent, and a required browser-only provider connection before scanner or Quant Lab requests.
- Ad placements are blank by default; web advertising requires the explicit `WEB_ADS_ENABLED=true` and `ADSENSE_VERIFY_ENABLED=true` deployment switches, plus configured slot IDs.

## Verified locally

- 43 backend tests, including browser-direct policy gating, key-storage retirement, validated browser-bar uploads, and explicit Polygon/Twelve Data selection.
- Python compilation, JavaScript syntax validation, diff validation, and a real local `/health` response showing V1.0.
- Account/key API regression checks rerun after the onboarding UI update.

## Required before a V1 tag or GitHub action

1. Leave platform keys empty, set `ORYNTRA_BROWSER_DIRECT_ANALYSIS_ENABLED=true`, register a test account, and confirm the browser sends the provider request directly while Oryntra receives no API key.
2. In a browser, run a browser-direct Quant Lab report, import a small timestamped corporate/macro sample, and verify that coverage, regimes, liquidity diagnostics, attribution, and health sections render.
3. Run one V1.0 Quant training job with real dated outcomes and inspect validation vs untouched test results.
4. Review public-source provenance and the exact data-provider/exchange license restrictions before enabling public derived analysis or Quant Lab.

## Intentionally excluded

No brokerage link, real-money order creation, automated execution, smart-order routing, or investment recommendations. The execution layer is a daily historical cost model used for research and paper simulation only.
