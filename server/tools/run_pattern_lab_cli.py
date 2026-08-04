from __future__ import annotations
import argparse, asyncio, json, sys
from pathlib import Path
APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))
from backend.database import init_db
from backend.routes.dev_tools import PatternLabRequest
from backend.pattern_lab import run_pattern_lab
from tools.warm_cache_cli import DEFAULT_150


def _ascii_bar(pct: float, width: int = 34) -> str:
    pct = max(0.0, min(100.0, float(pct or 0)))
    filled = int(round((pct / 100.0) * width))
    return '[' + '#' * filled + '-' * (width - filled) + f'] {pct:6.2f}%'


async def _progress_monitor(job: dict, stop_event: asyncio.Event, label: str = 'Pattern Lab') -> None:
    last_len = 0
    while not stop_event.is_set():
        pct = float(job.get('progress_pct') or 0.0)
        phase = str(job.get('phase') or 'starting')
        ticker = str(job.get('current_ticker') or '-')
        ticker_i = int(job.get('current_ticker_index') or job.get('completed_tickers') or 0)
        ticker_total = int(job.get('total_tickers') or len(job.get('tickers') or []) or 0)
        test_i = int(job.get('current_test_index') or 0)
        test_total = int(job.get('current_ticker_tests') or 0)
        checks = int(job.get('completed_checks') or 0)
        total_checks = int(job.get('total_checks_estimated') or 0)
        detail = ticker
        if ticker_total:
            detail += f' {ticker_i}/{ticker_total}'
        if test_total:
            detail += f' | test {test_i}/{test_total}'
        if total_checks:
            detail += f' | checks {checks}/{total_checks}'
        line = f'\r{label} {_ascii_bar(pct)} | {phase} | {detail}'
        print(line.ljust(last_len), end='', flush=True)
        last_len = max(last_len, len(line))
        await asyncio.sleep(0.5)
    pct = float(job.get('progress_pct') or 100.0)
    line = f'\r{label} {_ascii_bar(pct)} | complete'
    print(line.ljust(last_len), flush=True)

def parse_tickers(text, max_tickers=150):
    out=[]; seen=set()
    for raw in str(text or '').replace('\n', ',').split(','):
        t=''.join(ch for ch in raw.upper().strip() if ch.isalnum() or ch in '.-')
        if t and t not in seen:
            out.append(t); seen.add(t)
        if len(out)>=max_tickers: break
    return out
async def main_async(args):
    init_db()
    if args.ticker_file:
        ticker_text = Path(args.ticker_file).read_text(encoding='utf-8')
    elif args.training150:
        ticker_text = DEFAULT_150
    else:
        ticker_text = args.tickers
    tickers=parse_tickers(ticker_text, args.max_tickers)
    engine_arg = args.engines or args.modes
    modes=[m.strip() for m in engine_arg.split(',') if m.strip()]
    req=PatternLabRequest(tickers=tickers, period=args.period, horizon_days=args.horizon, step=args.step, min_history=args.min_history, max_tests_per_ticker=args.max_tests_per_ticker, data_source=args.data_source, engine_modes=modes)
    job={}
    stop_event=asyncio.Event()
    monitor=asyncio.create_task(_progress_monitor(job, stop_event, label='Pattern Lab'))
    try:
        res=await run_pattern_lab(req, job=job)
    finally:
        stop_event.set()
        await monitor
    slim={k:v for k,v in res.items() if k not in {'rows','baseline_rows'}}
    print('PATTERN LAB HEADLESS RESULTS')
    print('='*48)
    print(json.dumps(slim, indent=2, default=str))
    out=APP_DIR/'data'/'training_logs'
    out.mkdir(parents=True, exist_ok=True)
    p=out/f'pattern_lab_{args.label}.json'
    p.write_text(json.dumps(res, indent=2, default=str), encoding='utf-8')
    print(f'Full result saved: {p}')
    return 0
def main():
    ap=argparse.ArgumentParser(description='Run Pattern Lab without browser.')
    ap.add_argument('--tickers', default='AAPL,MSFT,NVDA,TSLA,AMZN,META,GOOGL,AMD,AVGO,JPM,V,XOM,CVX,UNH,LLY,JNJ,WMT,COST,HD,MCD,NKE,CAT,BA,RTX,NEE,PLTR,CRWD,SPY,QQQ,SMH')
    ap.add_argument('--ticker-file', default='')
    ap.add_argument('--training150', action='store_true')
    ap.add_argument('--max-tickers', type=int, default=150)
    ap.add_argument('--modes', default='official,v8')
    ap.add_argument('--engines', default='', help='Alias for --modes, e.g. official,v8,vai2')
    ap.add_argument('--period', default='5y')
    ap.add_argument('--horizon', type=int, default=10)
    ap.add_argument('--step', type=int, default=3)
    ap.add_argument('--min-history', type=int, default=90)
    ap.add_argument('--max-tests-per-ticker', type=int, default=120)
    ap.add_argument('--data-source', default='cache_only')
    ap.add_argument('--label', default='latest')
    return asyncio.run(main_async(ap.parse_args()))
if __name__=='__main__': raise SystemExit(main())

