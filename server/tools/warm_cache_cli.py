from __future__ import annotations
import argparse, time, sys
from pathlib import Path
APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))
from backend.fetcher import fetch_ticker_data
from backend.database import init_db, store_ohlcv_bars, get_ohlcv_cache_summary, get_ohlcv_cache_size_bytes

DEFAULT_150 = """AAPL,MSFT,NVDA,TSLA,AMZN,META,GOOGL,AMD,AVGO,JPM,V,XOM,CVX,UNH,LLY,JNJ,WMT,COST,HD,MCD,NKE,CAT,BA,RTX,NEE,PLTR,CRWD,SPY,QQQ,SMH,ORCL,CRM,ADBE,NFLX,INTC,QCOM,TXN,MU,DELL,IBM,SHOP,SNOW,NET,DDOG,PANW,ZS,NOW,UBER,ABNB,COIN,SQ,PYPL,MA,AXP,BAC,GS,MS,C,BLK,SCHW,TGT,LOW,SBUX,DIS,CMCSA,TMO,ABT,MRK,PFE,BMY,AMGN,GILD,ISRG,REGN,VRTX,CI,ELV,HUM,GE,GEV,ETN,HON,DE,LMT,NOC,GD,UPS,FDX,UNP,CSX,LIN,SHW,APD,FCX,NEM,SLB,COP,EOG,OXY,MPC,PSX,ENPH,FSLR,SEDG,DUK,SO,AEP,D,PEG,AMT,PLD,CCI,EQIX,SPG,AMAT,LRCX,KLAC,ASML,TSM,ARM,MRVL,ON,ADI,MPWR,TEAM,WDAY,INTU,ADSK,ANET,TTD,ROKU,HOOD,RBLX,SOFI,AFRM,DKNG,GM,F,FSLY,OKTA,ESTC,PATH,AI,IONQ,RIOT,MARA,CL,KO,PEP,PG,MDLZ,PM,MO"""

def parse_tickers(args):
    if args.ticker_file:
        text = Path(args.ticker_file).read_text(encoding='utf-8')
    elif args.training150:
        text = DEFAULT_150
    else:
        text = args.tickers
    out=[]; seen=set()
    for raw in text.replace('\n', ',').split(','):
        t=''.join(ch for ch in raw.upper().strip() if ch.isalnum() or ch in '.-')
        if t and t not in seen:
            out.append(t); seen.add(t)
        if len(out)>=args.max_tickers: break
    return out

def main():
    ap=argparse.ArgumentParser(description='Warm Oryntra OHLCV cache from terminal.')
    ap.add_argument('--tickers', default='')
    ap.add_argument('--ticker-file', default='')
    ap.add_argument('--training150', action='store_true')
    ap.add_argument('--period', default='5y')
    ap.add_argument('--delay', type=float, default=13.0)
    ap.add_argument('--max-tickers', type=int, default=150)
    args=ap.parse_args()
    init_db()
    tickers=parse_tickers(args)
    print(f'WARM CACHE START: {len(tickers)} tickers period={args.period} delay={args.delay}s')
    for i,t in enumerate(tickers,1):
        try:
            data=fetch_ticker_data(t,args.period)
            hist=data.get('history')
            provider=data.get('provider','unknown')
            if hist is None or hist.empty:
                print(f'[{i}/{len(tickers)}] {t}: NO DATA')
            else:
                stored=store_ohlcv_bars(t,'1d',hist,provider)
                print(f'[{i}/{len(tickers)}] {t}: bars={len(hist)} stored={stored} provider={provider}')
        except Exception as exc:
            print(f'[{i}/{len(tickers)}] {t}: ERROR {exc}')
        if i < len(tickers) and args.delay>0:
            time.sleep(args.delay)
    summary=get_ohlcv_cache_summary(tickers,'1d')
    print('WARM CACHE DONE')
    print(f'Tickers cached: {len(summary)}/{len(tickers)}')
    print(f'DB size MB: {get_ohlcv_cache_size_bytes()/1024/1024:.2f}')
    return 0
if __name__=='__main__': raise SystemExit(main())
