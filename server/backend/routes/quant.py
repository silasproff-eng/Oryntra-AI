from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from ..market_repository import get_market_repository, normalize_ticker
from ..quant_research import MODEL_PROFILES, STRATEGIES, QuantConfig, evaluate_strategies

router = APIRouter()


class QuantResearchRequest(BaseModel):
    tickers: list[str] = Field(default_factory=lambda: ["SPY", "QQQ", "IWM", "GLD", "TLT", "XLE"])
    period: str = "2y"
    data_source: str = "cache_first"
    data_provider: str | None = "auto"
    model: str = "v8_regime_diversified"
    strategy_weights: dict[str, float] = Field(default_factory=dict)
    strategies: list[str] = Field(default_factory=lambda: list(STRATEGIES))
    trend_lookback: int = Field(default=126, ge=21, le=252)
    momentum_lookback: int = Field(default=126, ge=21, le=252)
    reversal_lookback: int = Field(default=5, ge=2, le=30)
    cost_bps: float = Field(default=12, ge=0, le=250)
    borrow_bps_annual: float = Field(default=50, ge=0, le=2000)
    long_short: bool = True
    target_annual_volatility: float = Field(default=12, ge=1, le=50)
    max_gross_exposure: float = Field(default=1, ge=.1, le=2)
    max_single_name_weight: float = Field(default=.35, ge=.02, le=1)
    rebalance_frequency: str = "weekly"
    walk_forward_folds: int = Field(default=3, ge=2, le=6)

    @field_validator("period")
    @classmethod
    def validate_period(cls, value: str) -> str:
        if value not in {"1y", "2y", "5y", "all"}:
            raise ValueError("period must be one of 1y, 2y, 5y, or all")
        return value

    @field_validator("data_provider")
    @classmethod
    def validate_provider(cls, value: str | None) -> str | None:
        if value is not None and value not in {"cache_only", "auto", "polygon", "twelvedata"}:
            raise ValueError("data_provider must be cache_only, auto, polygon, or twelvedata")
        return value

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        if value not in MODEL_PROFILES:
            raise ValueError("Choose a supported Quant Lab model profile.")
        return value

    @field_validator("rebalance_frequency")
    @classmethod
    def validate_rebalance(cls, value: str) -> str:
        if value not in {"daily", "weekly", "monthly"}:
            raise ValueError("rebalance_frequency must be daily, weekly, or monthly")
        return value

    @field_validator("strategy_weights")
    @classmethod
    def validate_weights(cls, value: dict[str, float]) -> dict[str, float]:
        clean = {}
        for key, weight in value.items():
            if key in STRATEGIES:
                numeric = float(weight)
                if not 0 <= numeric <= 100:
                    raise ValueError("Strategy allocations must be between 0 and 100 percent.")
                clean[key] = numeric
        return clean


@router.get("/catalog")
async def catalog():
    return {"strategies": [{"id": key, **value} for key, value in STRATEGIES.items()], "models": [{"id": key, **value} for key, value in MODEL_PROFILES.items()], "providers": [{"id": "cache_only", "label": "Local database only"}, {"id": "auto", "label": "Smart fallback"}, {"id": "polygon", "label": "Polygon fallback"}, {"id": "twelvedata", "label": "Twelve Data fallback"}], "guardrails": ["No broker execution or order creation.", "Performance is net of configured turnover and borrow assumptions.", "Volatility targeting can reduce exposure only; it does not apply leverage.", "Chronological holdout and regime reports are diagnostics, not proof of future profitability."]}


@router.post("/run")
async def run_research(request: QuantResearchRequest):
    tickers: list[str] = []
    for raw in request.tickers[:40]:
        try:
            ticker = normalize_ticker(raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if ticker not in tickers:
            tickers.append(ticker)
    if len(tickers) < 2:
        raise HTTPException(status_code=400, detail="Choose at least two unique symbols.")
    strategy_ids = tuple(item for item in request.strategies if item in STRATEGIES)
    if not strategy_ids:
        raise HTTPException(status_code=400, detail="Choose at least one supported research strategy.")
    provider = request.data_provider or ("cache_only" if request.data_source == "cache_only" else "auto")
    config = QuantConfig(strategies=strategy_ids, trend_lookback=request.trend_lookback, momentum_lookback=request.momentum_lookback, reversal_lookback=request.reversal_lookback, cost_bps=request.cost_bps, borrow_bps_annual=request.borrow_bps_annual, long_short=request.long_short, model=request.model, strategy_weights=request.strategy_weights, target_annual_volatility=request.target_annual_volatility, max_gross_exposure=request.max_gross_exposure, max_single_name_weight=request.max_single_name_weight, rebalance_frequency=request.rebalance_frequency, walk_forward_folds=request.walk_forward_folds)
    repository, histories, metadata, errors = get_market_repository(), {}, {}, []
    minimum_bars = max(config.trend_lookback, config.momentum_lookback, 63) + 5
    for ticker in tickers:
        try:
            item = await asyncio.to_thread(repository.get_history, ticker, period=request.period, minimum_bars=minimum_bars, allow_api=provider != "cache_only", provider_preference=provider)
            histories[ticker], metadata[ticker] = item.history, item.metadata.__dict__
        except Exception as exc:
            errors.append({"ticker": ticker, "error": str(exc)})
    if len(histories) < 2:
        raise HTTPException(status_code=400, detail={"message": "Not enough usable histories for a comparison.", "errors": errors})
    try:
        report = await asyncio.to_thread(evaluate_strategies, histories, config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    report.update({"ok": True, "run_at": datetime.now(timezone.utc).isoformat(), "configuration": config.as_dict(), "data_source": request.data_source, "data_provider": provider, "source_metadata": metadata, "errors": errors, "dataset_fingerprint": repository.dataset_fingerprint(histories, configuration=config.as_dict())})
    return report
