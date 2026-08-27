from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


STRATEGIES = {
    "time_series_trend": {"label": "V8 time-series trend", "description": "Long positive trailing returns and short negative trailing returns across each asset.", "how_it_works": "Measures each symbol's trailing return at the close and holds the resulting signal for the following session.", "best_environment": "Persistent, diversified market trends with enough symbols to reduce single-asset noise.", "key_risk": "Whipsaw losses when prices repeatedly reverse in range-bound markets."},
    "cross_sectional_momentum": {"label": "V8 cross-sectional momentum", "description": "Long the strongest trailing-return group and short the weakest group within one universe.", "how_it_works": "Ranks the selected universe by trailing return, then forms a basket from relative leaders and laggards.", "best_environment": "Broad, liquid universes where relative strength persists across many symbols.", "key_risk": "Momentum crashes and high turnover when leadership changes abruptly."},
    "mean_reversion": {"label": "V8 mean-reversion comparator", "description": "A deliberately simple contrarian comparator after unusually large short-horizon moves.", "how_it_works": "Takes the opposite side of unusually large short-window moves after a volatility check.", "best_environment": "Liquid, mean-reverting ranges with contained transaction costs.", "key_risk": "Can fight a genuine breakout and usually has higher turnover."},
    "defensive_low_volatility": {"label": "V8 defensive low-volatility sleeve", "description": "Favors lower realized-volatility symbols and, in long/short research, offsets them with the highest-volatility group.", "how_it_works": "Ranks symbols by trailing realized volatility and constructs a bounded lower-versus-higher volatility basket using only prior returns.", "best_environment": "Broad universes where volatility dispersion persists and execution costs remain controlled.", "key_risk": "Can become concentrated or lag sharply when high-beta leadership dominates."},
}

MODEL_PROFILES = {
    "v8_regime_diversified": {"label": "V8 regime-diversified ensemble", "description": "A transparent mix of trend, relative strength, reversal, and a defensive low-volatility comparator.", "allocations": {"time_series_trend": 35, "cross_sectional_momentum": 30, "mean_reversion": 15, "defensive_low_volatility": 20}},
    "v8_balanced": {"label": "V8 balanced ensemble", "description": "A neutral research profile diversifying across trend, relative momentum, and a contrarian sleeve.", "allocations": {"time_series_trend": 45, "cross_sectional_momentum": 40, "mean_reversion": 15}},
    "v8_trend_first": {"label": "V8 trend-first ensemble", "description": "A profile emphasizing persistent-trend evidence while retaining diversification checks.", "allocations": {"time_series_trend": 65, "cross_sectional_momentum": 25, "mean_reversion": 10}},
    "v8_relative_strength": {"label": "V8 relative-strength ensemble", "description": "A profile emphasizing cross-sectional momentum in a broad liquid universe.", "allocations": {"time_series_trend": 25, "cross_sectional_momentum": 65, "mean_reversion": 10}},
    "equal_weight_baseline": {"label": "Equal-weight rules baseline", "description": "A non-V8 baseline that gives selected strategies equal influence for comparison.", "allocations": {"time_series_trend": 34, "cross_sectional_momentum": 33, "mean_reversion": 33}},
}


@dataclass(frozen=True)
class QuantConfig:
    strategies: tuple[str, ...] = ("time_series_trend", "cross_sectional_momentum", "mean_reversion", "defensive_low_volatility")
    trend_lookback: int = 126
    momentum_lookback: int = 126
    reversal_lookback: int = 5
    cost_bps: float = 12.0
    borrow_bps_annual: float = 50.0
    long_short: bool = True
    model: str = "v8_regime_diversified"
    strategy_weights: dict[str, float] | None = None
    target_annual_volatility: float = 12.0
    max_gross_exposure: float = 1.0
    max_single_name_weight: float = 0.35
    rebalance_frequency: str = "weekly"
    walk_forward_folds: int = 3

    def strategy_allocations_pct(self) -> dict[str, float]:
        selected = [item for item in self.strategies if item in STRATEGIES]
        profile = MODEL_PROFILES.get(self.model, MODEL_PROFILES["v8_regime_diversified"])
        source = self.strategy_weights or profile["allocations"]
        raw = {item: max(0.0, float(source.get(item, 0.0))) for item in selected}
        total = sum(raw.values())
        if total <= 0 and selected:
            raw, total = {item: 1.0 for item in selected}, float(len(selected))
        return {item: round(value / total * 100.0, 3) for item, value in raw.items()} if total else {}

    def as_dict(self) -> dict[str, Any]:
        return {"strategies": list(self.strategies), "trend_lookback": self.trend_lookback, "momentum_lookback": self.momentum_lookback, "reversal_lookback": self.reversal_lookback, "cost_bps": self.cost_bps, "borrow_bps_annual": self.borrow_bps_annual, "long_short": self.long_short, "model": self.model, "strategy_weights": self.strategy_allocations_pct(), "target_annual_volatility": self.target_annual_volatility, "max_gross_exposure": self.max_gross_exposure, "max_single_name_weight": self.max_single_name_weight, "rebalance_frequency": self.rebalance_frequency, "walk_forward_folds": self.walk_forward_folds}


def _normalise_gross(signal: pd.DataFrame) -> pd.DataFrame:
    return signal.div(signal.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)


def _trend(prices: pd.DataFrame, config: QuantConfig) -> pd.DataFrame:
    signal = np.sign(prices.pct_change(config.trend_lookback, fill_method=None)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return _normalise_gross(signal if config.long_short else signal.clip(lower=0.0))


def _momentum(prices: pd.DataFrame, config: QuantConfig) -> pd.DataFrame:
    trailing = prices.pct_change(config.momentum_lookback, fill_method=None)
    ranks, available = trailing.rank(axis=1, pct=True, method="first"), trailing.notna().sum(axis=1)
    signal = (ranks >= .70).astype(float) + (-(ranks <= .30).astype(float) if config.long_short else 0.0)
    signal.loc[available < 4, :] = 0.0
    return _normalise_gross(signal)


def _reversion(prices: pd.DataFrame, config: QuantConfig) -> pd.DataFrame:
    move = prices.pct_change(config.reversal_lookback, fill_method=None)
    z_score = move.div(move.rolling(63, min_periods=20).std().replace(0, np.nan))
    signal = pd.DataFrame(0.0, index=prices.index, columns=prices.columns).mask(z_score >= 1.5, -1.0).mask(z_score <= -1.5, 1.0)
    return _normalise_gross(signal if config.long_short else signal.clip(lower=0.0))


def _low_volatility(prices: pd.DataFrame, config: QuantConfig) -> pd.DataFrame:
    volatility = prices.pct_change(fill_method=None).rolling(63, min_periods=20).std()
    ranks, available = volatility.rank(axis=1, pct=True, method="first"), volatility.notna().sum(axis=1)
    signal = (ranks <= .35).astype(float) + (-(ranks >= .65).astype(float) if config.long_short else 0.0)
    signal.loc[available < 4, :] = 0.0
    return _normalise_gross(signal)


def _controls(target: pd.DataFrame, returns: pd.DataFrame, config: QuantConfig) -> pd.DataFrame:
    controlled = target.clip(-config.max_single_name_weight, config.max_single_name_weight).fillna(0.0)
    scale = (config.max_gross_exposure / controlled.abs().sum(axis=1).replace(0, np.nan)).clip(upper=1.0).fillna(0.0)
    controlled = controlled.mul(scale, axis=0)
    if config.rebalance_frequency in {"weekly", "monthly"}:
        if config.rebalance_frequency == "weekly":
            rebalance = pd.Series(False, index=controlled.index); rebalance.iloc[::5] = True
        else:
            months = controlled.index.to_series().dt.to_period("M")
            rebalance = months.ne(months.shift(1))
        mask = pd.DataFrame(np.repeat(rebalance.to_numpy()[:, None], len(controlled.columns), axis=1), index=controlled.index, columns=controlled.columns)
        controlled = controlled.where(mask, np.nan).ffill().fillna(0.0)
    held = controlled.shift(1).fillna(0.0)
    realized = (held * returns.fillna(0.0)).sum(axis=1).rolling(21, min_periods=10).std(ddof=0) * np.sqrt(252)
    scale = (config.target_annual_volatility / 100.0 / realized).clip(upper=1.0).shift(1).fillna(1.0).clip(0.0, 1.0)
    return controlled.mul(scale, axis=0)


def _summary(net: pd.Series, turnover: pd.Series, weights: pd.DataFrame) -> dict[str, Any]:
    clean = net.replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty: return {"status": "insufficient_data"}
    equity = (1 + clean).cumprod(); drawdown = equity.div(equity.cummax()).sub(1)
    ann = (float(equity.iloc[-1]) ** (252 / len(clean)) - 1) if len(clean) > 1 and float(equity.iloc[-1]) > 0 else None
    vol = float(clean.std(ddof=0) * np.sqrt(252)) if len(clean) > 1 else 0.0
    sharpe = float(clean.mean() / clean.std(ddof=0) * np.sqrt(252)) if clean.std(ddof=0) > 0 else None
    var = float(clean.quantile(.05)) if len(clean) >= 20 else None
    shortfall = float(clean[clean <= var].mean()) if var is not None and not clean[clean <= var].empty else None
    runs = drawdown.lt(0).astype(int).groupby(drawdown.eq(0).cumsum()).sum()
    calmar = ann / abs(float(drawdown.min())) if ann is not None and float(drawdown.min()) < 0 else None
    return {"status": "research_only", "observations": int(len(clean)), "total_return_pct": round((float(equity.iloc[-1]) - 1) * 100, 2), "annualized_return_pct": round(ann * 100, 2) if ann is not None else None, "annualized_volatility_pct": round(vol * 100, 2), "sharpe_zero_cash_rate": round(sharpe, 2) if sharpe is not None and np.isfinite(sharpe) else None, "max_drawdown_pct": round(float(drawdown.min()) * 100, 2), "annualized_turnover": round(float(turnover.reindex(clean.index).mean()) * 252, 2), "average_gross_exposure": round(float(weights.abs().sum(axis=1).reindex(clean.index).mean()), 3), "worst_day_pct": round(float(clean.min()) * 100, 2), "historical_var_95_pct": round(var * 100, 2) if var is not None else None, "historical_expected_shortfall_95_pct": round(shortfall * 100, 2) if shortfall is not None else None, "calmar_ratio": round(calmar, 2) if calmar is not None and np.isfinite(calmar) else None, "longest_drawdown_sessions": int(runs.max()) if not runs.empty else 0, "equity_curve": [{"date": str(index.date()), "value": round(float(value), 4)} for index, value in equity.iloc[::max(1, len(equity) // 260)].items()][-260:]}


def _simulate(target: pd.DataFrame, returns: pd.DataFrame, config: QuantConfig) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    target = target.where(returns.notna(), 0.0).fillna(0.0); held = target.shift(1).fillna(0.0)
    turnover = target.sub(target.shift(1).fillna(0.0)).abs().sum(axis=1)
    gross = (held * returns.fillna(0.0)).sum(axis=1)
    costs = turnover * (config.cost_bps / 10000) + held.clip(upper=0.0).abs().sum(axis=1) * (config.borrow_bps_annual / 10000 / 252)
    return gross.sub(costs), turnover, held


def _regime_breakdown(net: pd.Series, benchmark: pd.Series) -> list[dict[str, Any]]:
    cumulative = (1 + benchmark.fillna(0)).cumprod(); trend = cumulative.pct_change(63)
    vol = benchmark.rolling(21, min_periods=15).std(ddof=0); baseline = vol.rolling(126, min_periods=30).median()
    labels = pd.Series("insufficient history", index=benchmark.index, dtype="object")
    ready = trend.notna() & vol.notna() & baseline.notna()
    labels.loc[ready] = [f"{'uptrend' if t >= 0 else 'downtrend'} · {'high volatility' if v > b else 'contained volatility'}" for t, v, b in zip(trend[ready], vol[ready], baseline[ready])]
    rows = []
    for label, values in net.groupby(labels.reindex(net.index)):
        clean = values.replace([np.inf, -np.inf], np.nan).dropna()
        if not clean.empty: rows.append({"regime": str(label), "sessions": int(len(clean)), "total_return_pct": round(((1 + clean).prod() - 1) * 100, 2), "annualized_volatility_pct": round(float(clean.std(ddof=0) * np.sqrt(252)) * 100, 2) if len(clean) > 1 else 0.0})
    return sorted(rows, key=lambda item: item["regime"])


def _validation(net: pd.Series, folds: int) -> dict[str, Any]:
    clean = net.replace([np.inf, -np.inf], np.nan).dropna()
    if len(clean) < 126: return {"status": "insufficient_history", "message": "At least 126 completed sessions are needed for the chronological holdout report."}
    holdout_sessions = max(63, len(clean) // 5); development, holdout = clean.iloc[:-holdout_sessions], clean.iloc[-holdout_sessions:]
    windows = np.array_split(development, max(1, min(folds, len(development) // 42)))
    return {"status": "chronological_holdout", "note": "Rules are fixed rather than fitted here; this split is a chronological robustness check, not model training.", "development": _summary(development, pd.Series(0., index=development.index), pd.DataFrame(index=development.index)), "holdout": _summary(holdout, pd.Series(0., index=holdout.index), pd.DataFrame(index=holdout.index)), "walk_forward": [{"fold": number, "start": str(window.index.min().date()), "end": str(window.index.max().date()), "sessions": int(len(window)), "total_return_pct": round(((1 + window).prod() - 1) * 100, 2)} for number, window in enumerate(windows, 1) if len(window) >= 21]}


def _risk_report(held: pd.DataFrame, returns: pd.DataFrame) -> dict[str, Any]:
    latest = held.fillna(0.).iloc[-1]; gross = float(latest.abs().sum()); normalized = latest.abs() / gross if gross else latest.abs(); hhi = float((normalized ** 2).sum()) if gross else 0.0
    correlation = returns.tail(126).corr().to_numpy(); off_diagonal = correlation[np.triu_indices_from(correlation, 1)] if correlation.size else np.array([])
    return {"latest_gross_exposure": round(gross, 3), "latest_net_exposure": round(float(latest.sum()), 3), "largest_name_weight_pct": round(float(normalized.max()) * 100, 2) if gross else 0.0, "effective_number_of_positions": round(1 / hhi, 2) if hhi else 0.0, "average_abs_correlation_126_sessions": round(float(np.nanmean(np.abs(off_diagonal))), 3) if off_diagonal.size else None, "latest_positions": [{"symbol": str(symbol), "weight_pct": round(float(weight) * 100, 2)} for symbol, weight in latest.sort_values(key=lambda value: value.abs(), ascending=False).head(10).items() if abs(float(weight)) > .0001]}


def _quality(prices: pd.DataFrame) -> dict[str, Any]:
    return {"symbols": [{"symbol": str(symbol), "bars": int(prices[symbol].notna().sum()), "first_bar": str(prices[symbol].dropna().index.min().date()) if prices[symbol].notna().any() else None, "last_bar": str(prices[symbol].dropna().index.max().date()) if prices[symbol].notna().any() else None, "missing_session_pct": round(float(prices[symbol].isna().mean()) * 100, 2)} for symbol in prices.columns], "complete_overlap_sessions": int(prices.dropna(how="any").shape[0])}


def evaluate_strategies(histories: dict[str, pd.DataFrame], config: QuantConfig) -> dict[str, Any]:
    closes = {ticker: frame["Close"].astype(float).rename(ticker) for ticker, frame in histories.items() if frame is not None and "Close" in frame and len(frame) >= 2}
    if len(closes) < 2: raise ValueError("Quant Lab needs at least two symbols with usable daily closes.")
    prices = pd.concat(closes.values(), axis=1).sort_index().loc[lambda frame: ~frame.index.duplicated(keep="last")]
    returns = prices.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    builders = {"time_series_trend": _trend, "cross_sectional_momentum": _momentum, "mean_reversion": _reversion, "defensive_low_volatility": _low_volatility}
    simulations, results = {}, []
    allocations = config.strategy_allocations_pct()
    for strategy in config.strategies:
        if strategy not in builders: continue
        target = _controls(builders[strategy](prices, config), returns, config); net, turnover, held = _simulate(target, returns, config)
        result = {"id": strategy, "configured_allocation_pct": allocations.get(strategy, 0.), **STRATEGIES[strategy], **_summary(net, turnover, held)}
        if strategy == "cross_sectional_momentum" and len(prices.columns) < 4: result["validation_warning"] = "This strategy needs at least four symbols; no comparison was formed."
        results.append(result); simulations[strategy] = {"target": target, "net": net, "held": held}
    active = [key for key in config.strategies if key in simulations and allocations.get(key, 0) > 0]
    if not active: raise ValueError("At least one selected strategy needs a positive allocation.")
    if len(active) > 1:
        target = _controls(sum(simulations[key]["target"] * (allocations[key] / 100) for key in active), returns, config); net, turnover, held = _simulate(target, returns, config); profile = MODEL_PROFILES.get(config.model, MODEL_PROFILES["v8_regime_diversified"])
        results.insert(0, {"id": "strategy_ensemble", "label": profile["label"], "description": profile["description"], "how_it_works": "Combines selected sleeves, then applies the same next-session timing and cost model to combined holdings.", "best_environment": "Assess only after multiple regimes and a separate chronological holdout.", "key_risk": "A blended historical result can still be overfit and does not predict future returns.", "configured_allocation_pct": 100., "component_allocations_pct": {key: allocations[key] for key in active}, **_summary(net, turnover, held)})
    else:
        first = simulations[active[0]]; net, held = first["net"], first["held"]
    benchmark = returns.mean(axis=1, skipna=True)
    return {"methodology": {"execution_timing": "signal at session close, held for the next session", "portfolio_construction": "weights are capped, rebalanced on the selected schedule, and may only scale down to the requested volatility target", "cash_rate": "0% for displayed Sharpe", "warnings": ["Research simulation only. It does not place orders or identify a best trade.", "Signals use the close of day t and returns begin on day t+1; costs are deducted from every weight change.", "This package does not include point-in-time fundamentals or delisted-security history, so results are not production-grade evidence."], "model_profile": MODEL_PROFILES.get(config.model, MODEL_PROFILES["v8_regime_diversified"])}, "universe": {"symbols": list(prices.columns), "start": str(prices.index.min().date()), "end": str(prices.index.max().date()), "sessions": int(len(prices))}, "results": results, "validation": _validation(net, config.walk_forward_folds), "regime_breakdown": _regime_breakdown(net, benchmark), "portfolio_risk": _risk_report(held, returns), "data_quality": _quality(prices)}
