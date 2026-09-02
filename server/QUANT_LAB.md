# Oryntra V1.0 Quant Lab

Quant Lab is a local research and paper-simulation workspace. It has no broker client, does not create orders, and does not decide a real trade for a user.

## The V1 stack

`market history + public corporate disclosures + public macro observations → deterministic sleeves → probabilistic regime weights → portfolio limits → next-session simulated execution → attribution and health reports`

The `Oryntra V1.0 corporate quant system` profile combines four price-based sleeves with a corporate-quality sleeve. Corporate facts and macro records are local, auditable inputs: each needs a public HTTPS source URL, an approved source class, and an `available_at` timestamp. The engine does not use a fact before that timestamp.

## Start it locally

```bash
cd server
PYTHONPATH=. .venv/bin/python3 run.py
```

Set `ORYNTRA_PRIVATE_RESEARCH_ROUTES=true` in the local `.env`, then open the browser workspace. Use Quant Lab to select a universe, choose **Oryntra V1.0 corporate quant system**, set conservative costs and limits, and generate a report. For a signed-in public Quant Lab, keep private research routes off and set `ORYNTRA_PUBLIC_QUANT_LAB_ENABLED=true` only after reviewing the applicable data rights.

## Import public corporate and macro facts

Use the authenticated `POST /quant/corporate/import` endpoint. It accepts `documents`, `facts`, and `macro_observations` arrays. It rejects non-public sources, unsupported metrics, non-HTTPS URLs, and missing availability timestamps.

Example fact:

```json
{
  "ticker": "ACME",
  "metric": "operating_margin",
  "value": 18.4,
  "period_end": "2025-12-31",
  "published_at": "2026-02-05T21:10:00Z",
  "available_at": "2026-02-05T21:10:00Z",
  "source_class": "sec_filing",
  "source_url": "https://www.sec.gov/Archives/example"
}
```

Supported corporate metrics are revenue growth, operating and free-cash-flow margins, earnings surprise, guidance and estimate revisions, insider net buying, share-count growth, and net debt to EBITDA. Supported macro metrics are policy rate, 2-year and 10-year yields, credit spread, and inflation. Company investor-relations PDFs can be recorded as `company_ir_pdf`; central-bank releases and official macro datasets have their own source classes. Do not present an inferred fact as if it were disclosed.

## Reading the report

- `Structured-data coverage`: how much of the selected historical universe actually has eligible corporate or macro facts. Zero means the corresponding sleeve or macro effect was not used.
- `Regime probabilities`: the transparent blend of persistent-trend, stressed, reversal-risk, and normal states. These adjust sleeve weights; they are not forecasts.
- `Liquidity limit breaches`: days where the assumed trade would exceed the selected share of historical daily dollar volume. A high count means the simulated returns deserve less confidence.
- `Factor attribution`: a descriptive market-beta, residual, long/short, and sleeve-return decomposition—not proof of causality.
- `Strategy health`: compares the latest 63 sessions against earlier simulated history. `deteriorating` is a prompt to investigate and retest, not an automatic stop or trade instruction.
- `Correlation-convergence stress`: holds the latest simulated weights and trailing per-symbol volatility fixed, then moves all pairwise correlations partway toward `+1` over a 21-session horizon. It reports the resulting risk change for moderate and severe hypothetical scenarios. It is a diversification-breakdown diagnostic, not a price shock, loss forecast, or allocation instruction. The design follows the stress-testing practice of using documented hypothetical scenarios alongside historical evidence, rather than treating one trailing correlation matrix as stable. See [Basel market-risk stress testing guidance](https://www.bis.org/committees/bcbs/basel-framework/standard/mar/30/inforce/2022-01-01/published/2019-12-15) and the [Bank of England's 2025 CCP stress-test methodology](https://www.bankofengland.co.uk/stress-testing/2025/2025-ccp-stress-test-results-report).

## V1.0 Quant training

The V1.0 Quant training layer uses only deterministic structured inputs. It excludes ticker identity, the scanner score/confidence, and AI explanation text. It fits features on chronological training dates, selects thresholds on later validation dates, leaves a horizon-sized purge gap between partitions, and promotes only if the untouched test score improves on the currently promoted model.

Treat all V1.0 Quant training outputs as experimental research evidence. A successful test score is not proof of future accuracy or profitability.

## Scanner boundary

Run the scanner normally from the **Scanner** tab: enter a ticker, choose its displayed analysis horizon, and review the deterministic setup, risk plan, and any available corporate context. The public scanner may show a current corporate-context panel where locally imported evidence exists. Its deterministic numeric score does not change from an LLM response, and the explanation layer remains descriptive rather than a numeric predictor.
