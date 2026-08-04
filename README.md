<div align="center">
  <img src="brand-assets/oryntra-ai-master-logo.png" alt="Oryntra AI" width="520">

  # Oryntra AI

  FastAPI and Flutter market-analysis platform with server-side data processing and TradingView-hosted charts.
</div>

## Status

This repository is a development build. It is configured for private research by default.

The backend can process market data, calculate indicators, detect patterns, rank setups, and return a reduced analysis payload. Raw candle history stays on the server. TradingView supplies the chart independently.

Public or paid analysis must remain disabled until the market-data provider has approved the intended commercial and end-user use in writing.

## Main features

- FastAPI backend
- Browser dashboard
- Flutter and iOS client
- TradingView embedded chart
- RSI, EMA, SMA, MACD, stochastic, Bollinger Bands, ATR, ADX, VWAP, and momentum analysis
- Candlestick and chart-pattern detection
- Fair-value-gap and liquidity-sweep detection
- Market-structure analysis
- Setup scoring and trade-plan generation
- Watchlists and paper-trading records
- Backtesting and Pattern Lab research tools
- Per-user analysis quotas
- Server-side response filtering

## Repository layout

```text
brand-assets/   logos and app artwork
ios-app/        Flutter and iOS project
server/         FastAPI backend, browser client, tests, and research tools
```

## Local setup

### Server

```bash
cd server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

The local dashboard runs at:

```text
http://127.0.0.1:8001
```

### Flutter client

```bash
cd ios-app
flutter pub get
flutter run
```

For an iOS build:

```bash
cd ios-app
./prepare_ios_project.sh
open ios/Runner.xcworkspace
```

## Configuration

The server reads `server/.env`.

Required for private provider-backed analysis:

```env
POLYGON_API_KEY=YOUR_PRIVATE_POLYGON_KEY
ORYNTRA_MARKET_DATA_LICENSE_MODE=personal_research
ORYNTRA_OWNER_EMAILS=your-email@example.com
ORYNTRA_PUBLIC_DERIVED_ANALYSIS_ENABLED=false
```

Do not commit `.env`, API keys, signing files, databases, sessions, or generated build folders.

The public-analysis settings should only be enabled after the provider has approved the deployed use case:

```env
ORYNTRA_MARKET_DATA_LICENSE_MODE=business_approved
ORYNTRA_PUBLIC_DERIVED_ANALYSIS_ENABLED=true
```

Those settings are an application guard. They do not replace a data license.

## Public analysis API

```text
GET  /api/intelligence/status
GET  /api/intelligence/quota
POST /api/intelligence/scan
POST /api/intelligence/scan-multiple
```

The public response builder excludes raw candle arrays, OHLCV histories, provider payloads, downloadable bars, and server cache contents.

## Tests

```bash
cd server
source venv/bin/activate
pytest -q
```

Individual test files can be run while working on a subsystem:

```bash
pytest -q tests/test_public_payload_boundary.py
pytest -q tests/test_analysis_access_policy.py
pytest -q tests/test_intelligence_route.py
```

## Development notes

The production analysis path and the research tools are separate. Pattern Lab and backtesting code should not replace the public engine without review and testing.

TradingView is used only for hosted visualization. The application does not read or scrape the TradingView iframe.

Indicator values, confidence scores, entries, stops, and targets are analytical outputs. They are not brokerage quotes or guaranteed trading outcomes.

## License

This project is source-available under the terms in [LICENSE](LICENSE). No permission is granted beyond that license.
