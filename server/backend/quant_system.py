"""Reusable research-only portfolio, risk, execution, and monitoring primitives."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def probabilistic_regimes(benchmark_returns: pd.Series, macro_features: pd.DataFrame | None = None) -> pd.DataFrame:
    """Transparent probability-like state weights from completed market and PIT macro data."""
    returns = benchmark_returns.fillna(0.0)
    trend = returns.rolling(63, min_periods=21).sum()
    short_vol = returns.rolling(21, min_periods=10).std(ddof=0)
    long_vol = returns.rolling(126, min_periods=30).std(ddof=0)
    vol_z = short_vol.div(long_vol.replace(0, np.nan)).fillna(1.0) - 1.0
    reversal = -returns.rolling(5, min_periods=5).sum() * np.sign(trend.fillna(0.0))
    macro = (macro_features.reindex(returns.index).ffill() if macro_features is not None else pd.DataFrame(index=returns.index))
    curve = (macro.get("yield_10y", pd.Series(0.0, index=returns.index)) - macro.get("yield_2y", pd.Series(0.0, index=returns.index))).fillna(0.0)
    credit = macro.get("credit_spread_bps", pd.Series(0.0, index=returns.index)).ffill().fillna(0.0)
    inflation = macro.get("inflation_yoy", pd.Series(0.0, index=returns.index)).ffill().fillna(0.0)
    policy = macro.get("policy_rate", pd.Series(0.0, index=returns.index)).ffill().fillna(0.0)
    credit_stress = ((credit - credit.rolling(126, min_periods=20).median()) / 100.0).clip(-2, 2).fillna(0.0)
    restrictive = (((policy + inflation) - (policy + inflation).rolling(126, min_periods=20).median()).clip(-4, 4) / 4.0).fillna(0.0)
    curve_pressure = (-curve).clip(-4, 4) / 4.0
    logits = pd.DataFrame({
        "persistent_trend": np.clip(trend.fillna(0.0) * 9.0 - vol_z.clip(lower=0) * 0.4, -4, 4),
        "stressed": np.clip(vol_z * 3.5 - trend.abs().fillna(0.0) * 1.5 + credit_stress * 0.55 + restrictive * 0.20, -4, 4),
        "reversal_risk": np.clip(reversal.fillna(0.0) * 14.0 + vol_z.clip(lower=0) * 0.8 + curve_pressure * 0.20, -4, 4),
        "normal": 0.0,
    }, index=returns.index)
    exponent = np.exp(logits.sub(logits.max(axis=1), axis=0))
    return exponent.div(exponent.sum(axis=1), axis=0).fillna(0.25)


def regime_conditioned_weights(
    base_allocations_pct: dict[str, float],
    regimes: pd.DataFrame,
) -> pd.DataFrame:
    """Reweight sleeves without leverage; all rows sum to 1 after normalization."""
    base = pd.Series({name: max(0.0, float(weight)) / 100.0 for name, weight in base_allocations_pct.items()})
    if base.empty or base.sum() <= 0:
        return pd.DataFrame(index=regimes.index, columns=base.index, dtype=float)
    multipliers = pd.DataFrame(1.0, index=regimes.index, columns=base.index)
    def adjust(name: str, trend: float, stress: float, reversal: float) -> None:
        if name in multipliers:
            multipliers[name] = 1 + regimes["persistent_trend"] * trend + regimes["stressed"] * stress + regimes["reversal_risk"] * reversal
    adjust("time_series_trend", 0.50, 0.12, -0.34)
    adjust("cross_sectional_momentum", 0.28, -0.22, -0.40)
    adjust("mean_reversion", -0.25, 0.12, 0.55)
    adjust("defensive_low_volatility", -0.08, 0.60, 0.18)
    adjust("corporate_quality", 0.12, 0.28, 0.08)
    weighted = multipliers.mul(base, axis=1).clip(lower=0.0)
    return weighted.div(weighted.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)


def liquidity_execution_costs(
    target: pd.DataFrame,
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    *,
    base_cost_bps: float,
    portfolio_value: float = 1_000_000.0,
    impact_coefficient_bps: float = 18.0,
    max_adv_participation_pct: float = 2.0,
) -> tuple[pd.Series, dict[str, Any]]:
    """Model simple, conservative liquidity costs from historical price and volume only."""
    changes = target.sub(target.shift(1).fillna(0.0)).abs().fillna(0.0)
    adv = prices.mul(volumes).rolling(20, min_periods=5).median().replace(0, np.nan)
    participation = changes.mul(float(portfolio_value)).div(adv)
    participation = participation.replace([np.inf, -np.inf], np.nan)
    impact_rate = np.sqrt(participation.clip(lower=0.0)).mul(float(impact_coefficient_bps) / 10000.0)
    fallback = pd.DataFrame(float(base_cost_bps) / 10000.0, index=changes.index, columns=changes.columns)
    rate = fallback.add(impact_rate.fillna(0.0))
    costs = (changes * rate).sum(axis=1)
    latest = participation.iloc[-1] if len(participation) else pd.Series(dtype=float)
    max_participation = float(np.nanmax(participation.to_numpy())) if participation.notna().any().any() else None
    breached = int((participation > float(max_adv_participation_pct) / 100.0).sum().sum())
    return costs.fillna(0.0), {
        "model": "base_cost_plus_sqrt_adv_participation_impact",
        "portfolio_value_assumption": float(portfolio_value),
        "base_cost_bps": float(base_cost_bps),
        "impact_coefficient_bps": float(impact_coefficient_bps),
        "max_adv_participation_pct": float(max_adv_participation_pct),
        "maximum_estimated_adv_participation_pct": round(max_participation * 100, 3) if max_participation is not None else None,
        "participation_limit_breaches": breached,
        "latest_name_participation_pct": [{"symbol": str(symbol), "participation_pct": round(float(value) * 100, 3)} for symbol, value in latest.dropna().sort_values(ascending=False).head(10).items()],
        "note": "Estimated from daily dollar volume. This is a research cost proxy, not a live-fill or market-impact guarantee.",
    }


def liquidity_capacity_scenarios(
    target: pd.DataFrame,
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    *,
    base_cost_bps: float,
    portfolio_value: float,
    impact_coefficient_bps: float,
    max_adv_participation_pct: float,
) -> dict[str, Any]:
    """Re-run the same daily-ADV proxy at larger hypothetical portfolio sizes."""
    scenarios = []
    for multiplier in (1.0, 2.0, 5.0):
        costs, details = liquidity_execution_costs(
            target, prices, volumes,
            base_cost_bps=base_cost_bps,
            portfolio_value=portfolio_value * multiplier,
            impact_coefficient_bps=impact_coefficient_bps,
            max_adv_participation_pct=max_adv_participation_pct,
        )
        scenarios.append({
            "portfolio_value_assumption": float(portfolio_value * multiplier),
            "portfolio_value_multiple": multiplier,
            "estimated_total_cost_pct": round(float(costs.sum()) * 100, 3),
            "maximum_estimated_adv_participation_pct": details["maximum_estimated_adv_participation_pct"],
            "participation_limit_breaches": details["participation_limit_breaches"],
        })
    return {
        "scenarios": scenarios,
        "note": "Sensitivity of the same daily ADV-participation proxy to assumed portfolio size. It does not model a multi-day liquidation, order-book depth, fire-sale feedback, or a live execution decision.",
    }


def factor_and_relative_value_attribution(
    held: pd.DataFrame,
    returns: pd.DataFrame,
    benchmark_returns: pd.Series,
    component_returns: dict[str, pd.Series] | None = None,
) -> dict[str, Any]:
    portfolio = (held.shift(1).fillna(0.0) * returns.fillna(0.0)).sum(axis=1)
    benchmark = benchmark_returns.reindex(portfolio.index).fillna(0.0)
    variance = float(benchmark.var(ddof=0))
    beta = float(portfolio.cov(benchmark) / variance) if variance > 1e-12 else 0.0
    residual = portfolio - beta * benchmark
    latest = held.iloc[-1].fillna(0.0) if len(held) else pd.Series(dtype=float)
    long_leg = latest.clip(lower=0.0)
    short_leg = latest.clip(upper=0.0).abs()
    components = []
    for name, series in (component_returns or {}).items():
        clean = series.reindex(portfolio.index).fillna(0.0)
        components.append({"component": name, "total_return_pct": round(((1 + clean).prod() - 1) * 100, 2), "average_daily_contribution_bps": round(float(clean.mean()) * 10000, 3)})
    return {
        "market_beta_126_sessions": round(beta, 3),
        "market_component_total_return_pct": round(((1 + beta * benchmark).prod() - 1) * 100, 2),
        "residual_component_total_return_pct": round(((1 + residual).prod() - 1) * 100, 2),
        "latest_long_gross_pct": round(float(long_leg.sum()) * 100, 2),
        "latest_short_gross_pct": round(float(short_leg.sum()) * 100, 2),
        "latest_relative_value_net_pct": round(float(latest.sum()) * 100, 2),
        "strategy_component_attribution": components,
        "note": "Attribution is a descriptive historical decomposition, not a causal claim about returns.",
    }


def strategy_health(component_returns: dict[str, pd.Series], window: int = 63) -> list[dict[str, Any]]:
    rows = []
    for name, series in component_returns.items():
        clean = series.replace([np.inf, -np.inf], np.nan).dropna()
        recent = clean.tail(window)
        historical = clean.iloc[:-len(recent)] if len(clean) > len(recent) else pd.Series(dtype=float)
        recent_mean = float(recent.mean()) if len(recent) else 0.0
        earlier_mean = float(historical.mean()) if len(historical) else 0.0
        recent_sharpe = recent_mean / float(recent.std(ddof=0)) * np.sqrt(252) if len(recent) > 4 and float(recent.std(ddof=0)) > 1e-12 else None
        decay = recent_mean - earlier_mean if len(historical) else None
        label = "insufficient_history" if len(recent) < 21 else ("deteriorating" if decay is not None and decay < -0.00025 else "stable_or_improving")
        rows.append({"strategy": name, "recent_sessions": int(len(recent)), "recent_mean_daily_bps": round(recent_mean * 10000, 3), "prior_mean_daily_bps": round(earlier_mean * 10000, 3) if len(historical) else None, "alpha_decay_daily_bps": round(decay * 10000, 3) if decay is not None else None, "recent_sharpe": round(float(recent_sharpe), 2) if recent_sharpe is not None and np.isfinite(recent_sharpe) else None, "status": label})
    return sorted(rows, key=lambda row: row["strategy"])
