from fastapi import APIRouter, HTTPException
from ..backtest import BacktestRequest, run_backtest

router = APIRouter()


@router.post("/run")
async def backtest_endpoint(req: BacktestRequest):
    try:
        return await run_backtest(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest error: {str(e)}")


@router.get("/quick/{ticker}")
async def quick_backtest(ticker: str, period: str = "1y", min_score: float = 55):
    req = BacktestRequest(ticker=ticker.upper(), period=period, min_score=min_score)
    try:
        return await run_backtest(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

