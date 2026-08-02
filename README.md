<div align="center">
  <img src="brand-assets/oryntra-ai-master-logo.png" alt="Oryntra AI" width="520">

  # Oryntra AI

  **Alpaca-connected market research, technical analysis, and simulated trade planning.**

  [Website](https://oryntraai.com) · [Methodology](https://oryntraai.com/methodology)
</div>

> [!IMPORTANT]
> This is a **public source-available repository, not an open-source project**. GitHub users may view and fork the repository through GitHub as permitted by GitHub's Terms of Service. No broader permission to use, modify, deploy, redistribute, commercialize, train models on, or create competing products from this code is granted. See [LICENSE](LICENSE).

## Overview

Oryntra AI is a mobile-first market-research application that combines technical indicators, pattern detection, structured setup scoring, educational explanations, watchlists, and simulated paper-trading tools.

This repository contains the Alpaca-ready application architecture:

- **`server/`** — Python/FastAPI backend, Alpaca Connect OAuth, analysis engine, legal pages, private research utilities, and maintenance mode.
- **`ios-app/`** — Flutter mobile application and native iOS integration.
- **`brand-assets/`** — Oryntra branding used by this repository.

## Current integration model

Oryntra uses **Alpaca Connect OAuth** so users authorize access to their own Alpaca accounts. The Alpaca client secret and connected-account access tokens stay on the server and must never be embedded in the mobile application.

The public mobile application:

- Requests derived Oryntra analysis from the authenticated server API.
- Does not receive downloadable OHLCV arrays, raw candle history, provider responses, or Alpaca credentials.
- Displays a separately hosted TradingView widget for public chart visualization.
- Supports Alpaca connection, connection status, paper/live account labeling, authorization errors, and disconnect flows.

Alpaca application registration and written approval may be required before commercial release, advertising, paid features, or access by other users. This repository does not itself grant Alpaca API or market-data rights.

## Core capabilities

- User-authorized Alpaca Connect integration
- Technical indicators and market-context summaries
- Candlestick, chart-pattern, structure, and fair-value-gap analysis
- Setup classification and confidence scoring
- Structured entry, stop, target, and risk/reward planning
- Educational AI-assisted explanations
- Watchlists and multi-ticker workflows
- Simulated paper-trading tools
- Private historical testing and model-research utilities
- Responsive TradingView-hosted chart presentation
- Reusable maintenance-mode website

## Required server configuration

Copy the example configuration:

```bash
cd server
cp .env.example .env
```

Set at minimum:

```env
PUBLIC_API_BASE_URL=https://api.oryntraai.com
ALPACA_OAUTH_CLIENT_ID=YOUR_APPROVED_CLIENT_ID
ALPACA_OAUTH_CLIENT_SECRET=YOUR_APPROVED_CLIENT_SECRET
ALPACA_OAUTH_REDIRECT_URI=https://api.oryntraai.com/api/alpaca/callback
ORYNTRA_TOKEN_ENCRYPTION_KEY=YOUR_GENERATED_ENCRYPTION_KEY
ALPACA_DATA_FEED=iex
ORYNTRA_PRIVATE_RESEARCH_ROUTES=false
```

Generate the token-encryption key locally:

```bash
python3 tools/generate_token_encryption_key.py
```

Never commit `.env`, OAuth secrets, access tokens, databases, signing materials, or production logs.

## Run the server locally

```bash
cd server
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python run.py
```

Production deployments should use the included system-service or startup configuration appropriate to the host rather than exposing a development server directly.

## Run the Flutter app

```bash
cd ios-app
flutter pub get
flutter run \
  --dart-define=ORYNTRA_API_URL=https://api.oryntraai.com \
  --dart-define=ORYNTRA_PREVIEW_MODE=false \
  --dart-define=ADMOB_TEST_MODE=true
```

The mobile application must receive only the public server URL. Do not add the Alpaca client secret or connected-user tokens to Dart, iOS property lists, Android resources, build arguments, or bundled assets.

## OAuth addresses

Proposed production values:

```text
OAuth callback: https://api.oryntraai.com/api/alpaca/callback
Mobile deep link: oryntra://oauth/alpaca/complete
```

The callback registered with Alpaca must exactly match the server configuration. The client secret is used only by the backend during the authorization-code exchange.

## Security and repository hygiene

The root `.gitignore` excludes:

- Environment and credential files
- OAuth tokens and private keys
- SQLite databases and runtime research state
- Python virtual environments and caches
- Flutter, CocoaPods, Xcode, Gradle, and Android build artifacts
- Signing certificates and provisioning profiles
- Local editor and operating-system files

Before publishing changes, review `git status` and run a secret scan. Rotating a credential is required if it was ever committed, even if it is later deleted from the current branch.

## Third-party services

Oryntra may integrate with third-party services including Alpaca and TradingView. Their names, APIs, widgets, data, trademarks, and services remain subject to their own terms, permissions, availability, attribution requirements, and commercial approvals. This repository is not affiliated with or endorsed by Alpaca or TradingView unless a separate written agreement states otherwise.

## Financial and technology disclaimer

Oryntra AI is intended for informational, research, demonstration, and educational purposes only. It is not a broker-dealer, investment adviser, fiduciary, financial planner, or tax, legal, or accounting professional. It does not provide personalized investment advice or guarantee any result.

Market data, indicators, patterns, scores, signals, forecasts, explanations, backtests, simulations, and trade plans may be delayed, incomplete, inaccurate, unavailable, or unsuitable for a user or market condition. Simulated results do not represent actual execution and may omit spreads, liquidity limits, latency, fees, slippage, taxes, corporate actions, and other real-world effects. Past performance and backtested performance do not guarantee future results. Users remain solely responsible for their decisions and losses.

## Security reports

Do not publicly disclose exploitable vulnerabilities, credentials, private user information, OAuth tokens, or instructions for bypassing access controls. Use the contact channel published at [oryntraai.com](https://oryntraai.com).

## License

Copyright © 2026 Oryntra AI. All rights reserved.

The repository is governed by the [Oryntra AI Proprietary Source-Available License](LICENSE). It is not licensed as open source.
