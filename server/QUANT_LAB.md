# Oryntra Quant Lab

Quant Lab is a private, research-only systematic-analysis workspace. It does
not connect to a broker, create orders, or identify a best trade.

## What a run evaluates

- Time-series trend, cross-sectional momentum, mean reversion, and a
  defensive low-volatility comparator.
- Next-session execution timing, configurable transaction costs, and annual
  short-borrow assumptions.
- Gross-exposure and single-name caps, daily/weekly/monthly rebalancing, and
  volatility targeting that only reduces exposure; it never adds leverage.
- Historical drawdown, VaR/expected shortfall, concentration, correlation,
  chronological holdout, regime slices, and source/data-coverage diagnostics.

## Data sources

Smart fallback checks the local database first, then Polygon and configured
Twelve Data. Provider credentials stay in the server environment. A successful
fallback is cached locally so a later cache-only run can be reproduced.

Set `TWELVEDATA_API_KEY` and optionally
`ORYNTRA_ENABLE_TWELVEDATA_FALLBACK=1` in the private server environment. The
client has a shared conservative request limiter; set
`ORYNTRA_TWELVEDATA_CALLS_PER_MINUTE` no higher than the plan allowance.

## Research standard

The tool uses public, general ideas rather than attempting to replicate private
institutional systems: risk-balanced diversification across economic outcomes,
market-mechanics and execution awareness, and out-of-sample/cost discipline.
See [Bridgewater](https://www.bridgewater.com/research-and-insights/the-all-weather-story),
[Jane Street](https://www.janestreet.com/what-we-do/overview/),
[Citadel Securities](https://www.citadelsecurities.com/what-we-do/what-is-a-market-maker/),
[Man AHL](https://www.man.com/ahl?language=en-gb), and
[AQR](https://www.aqr.com/insights/research/journal-article/how-do-factor-premia-vary-over-time-a-century-of-evidence).

Historical outputs are not forecasts. Before treating a result as evidence, use
a point-in-time universe, delisted symbols, realistic liquidity/borrow costs,
pre-registered parameters, and multiple untouched out-of-sample periods.
