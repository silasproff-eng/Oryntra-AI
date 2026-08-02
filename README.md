<div align="center">

<img src="brand-assets/oryntra-ai-master-logo.png" width="520">

# Oryntra AI

### Institutional-grade market analysis architecture for intelligent trade research

**Private Research Platform • AI Analysis • Technical Intelligence • Mobile Trading Companion**

[Website](https://oryntraai.com) •
[Methodology](https://oryntraai.com/methodology)

</div>

---

> [!IMPORTANT]
> **Oryntra AI is proprietary software.**
>
> This repository is published for transparency, technical review, portfolio demonstration, and collaboration discussions.
>
> Viewing through GitHub is permitted under GitHub's Terms of Service. No license is granted to use, modify, deploy, redistribute, commercialize, train AI models on, or create derivative or competing products from any portion of this repository.
>
> See **LICENSE** for complete terms.

---

# Executive Summary

Oryntra AI is a research platform designed to bridge institutional technical analysis, artificial intelligence, quantitative scoring, and modern mobile software architecture.

Rather than acting as a brokerage or charting platform, Oryntra operates as an independent market-intelligence layer that evaluates price structure, trend quality, momentum, volatility, participation, and statistical context before presenting structured trade research to the user.

The project was designed around one primary engineering principle:

> **Raw market data should remain separate from proprietary analysis.**

Instead of exposing downloadable historical datasets, Oryntra transforms authorized market information into derived intelligence that can be interpreted by human traders while respecting provider boundaries and maintaining a secure client/server architecture.

---

# System Architecture

```
                 ┌───────────────────────┐
                 │   Flutter Mobile App  │
                 └────────────┬──────────┘
                              │
                              │ HTTPS
                              ▼
                 ┌────────────────────────┐
                 │    FastAPI Backend     │
                 │ Authentication Layer   │
                 │ OAuth Management       │
                 │ Analysis Engine        │
                 └────────────┬───────────┘
                              │
               ┌──────────────┴──────────────┐
               ▼                             ▼
      Alpaca Connect OAuth          Internal Analysis
      Account Authorization          Indicator Engine
      User Data Access               Pattern Detection
                                     AI Explanation
                                     Risk Modeling
```

The client never communicates directly with external market providers.

All authentication, authorization, caching, analysis, and provider integrations occur exclusively within the backend.

---

# Engineering Goals

Oryntra was designed around several architectural objectives.

## Separation of Concerns

The application deliberately separates

- User Interface
- Authentication
- Market Data
- Analysis
- AI Interpretation
- Trading Logic
- Persistence
- Provider Integrations

into independent layers.

Each subsystem can evolve independently without affecting the others.

---

## Secure OAuth Architecture

User brokerage accounts are connected through OAuth.

Sensitive credentials never leave the backend.

The mobile application never receives

- API secrets
- OAuth client secrets
- refresh tokens
- provider credentials
- market-provider authentication keys

All privileged operations occur exclusively within authenticated backend services.

---

## Provider Abstraction

The analysis engine is intentionally isolated from any specific data provider.

Instead of depending directly on one brokerage, Oryntra operates through an internal provider abstraction layer allowing future integrations without modifying analytical logic.

Current architecture supports integration with services such as

- Alpaca
- Polygon
- Twelve Data
- Interactive Brokers
- additional institutional feeds

without redesigning higher-level analysis.

---

# Analysis Engine

The research engine combines multiple independent analytical subsystems.

These include

## Market Structure

- Higher High / Lower Low detection
- Break of Structure
- Change of Character
- Trend continuation
- Trend exhaustion

---

## Trend Evaluation

Multiple moving-average systems

- SMA
- EMA
- trend alignment
- crossover confirmation
- slope analysis

---

## Momentum Analysis

- RSI
- MACD
- Stochastic Oscillator
- Momentum acceleration
- Divergence detection

---

## Volume Intelligence

- Relative Volume
- VWAP
- Anchored VWAP
- Volume participation
- Institutional accumulation analysis

---

## Volatility

- ATR
- expansion / contraction
- stop distance estimation
- volatility normalization

---

## Pattern Recognition

Current architecture supports recognition of numerous classical technical structures including

- Double Tops
- Double Bottoms
- Triple Tops
- Triple Bottoms
- Flags
- Pennants
- Channels
- Wedges
- Cup & Handle
- Head & Shoulders
- Fair Value Gaps
- Engulfing
- Hammer
- BOS
- CHoCH

Each detector operates independently before contributing to the overall analytical confidence score.

---

# Decision Framework

Rather than allowing one indicator to dominate predictions, Oryntra evaluates dozens of independent observations simultaneously.

Each observation contributes weighted evidence toward

- Bullish probability
- Bearish probability
- Confidence
- Risk
- Trade quality

The engine intentionally avoids deterministic "buy" or "sell" logic.

Instead it attempts to explain

- why
- how
- where

a setup exists while leaving execution decisions entirely to the user.

---

# Artificial Intelligence Layer

Artificial intelligence operates as an explanation engine rather than an autonomous trading system.

Its responsibilities include

- translating quantitative analysis into natural language
- explaining conflicting signals
- summarizing technical context
- assisting educational understanding
- reducing information overload

The AI does not execute trades or guarantee outcomes.

---

# Mobile Architecture

The Flutter application serves as a secure presentation layer.

Responsibilities include

- authentication
- portfolio visualization
- AI interaction
- research display
- watchlists
- notifications
- paper-trading interface
- TradingView visualization

The application intentionally avoids embedding privileged logic that belongs within backend services.

---

# Security Model

Security principles include

- backend-only OAuth secrets
- encrypted token storage
- isolated authentication layer
- HTTPS-only communication
- principle of least privilege
- server-side authorization
- provider abstraction
- restricted public APIs

---

# Scalability

The architecture was designed to support future expansion including

- multiple broker integrations
- cloud deployment
- distributed caching
- additional AI models
- institutional data feeds
- strategy optimization
- portfolio analytics
- quantitative research modules

without redesigning the client application.

---

# Repository Structure

```
server/
    Authentication
    OAuth
    Analysis Engine
    AI Services
    API
    Market Providers
    Private Research

ios-app/
    Flutter UI
    Native Integrations
    TradingView
    Authentication
    Portfolio Views

brand-assets/
```

---

# Disclaimer

Oryntra AI is an educational and research platform.

It is not a broker-dealer, investment adviser, fiduciary, or financial planner.

All analytical output represents algorithmic interpretation of available information and should not be construed as investment advice.

Past performance, simulations, and backtests do not guarantee future results.

---

# License

Copyright © 2026 Oryntra AI

All Rights Reserved.

This repository is governed by the **Oryntra AI Proprietary Source-Available License**.
