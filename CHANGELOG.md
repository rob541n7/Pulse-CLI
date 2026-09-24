# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `pulse.core.idx` package: IDX Ringkasan Saham Excel loader + foreign-flow history,
  free float (BEI) & >=1% ownership (KSEI), HSC list, cached OHLCV panel
- Big cap universe (`/universe`): top-N market cap, non-HSC, real free float >= 12.5%, liquid
- IHSG ex-HSC benchmark (`/ihsgx`)
- Swing 2-8 week screener and Relative-Strength Breakout backtest (`/swing`)
- Batch entry point `python -m pulse.core.idx` for scheduled daily updates
- Self-contained HTML dashboard (`/dashboard`, `update_dashboard.bat`): market regime,
  IHSG vs ex-HSC, screener with detail panel, sector rotation (RRG), foreign flow, backtest
- Fundamentals & disclosures from idx.co.id via in-browser extractor
  (`scripts/idx_browser_extract.js`): XBRL TTM valuation (PE, PBV, ROE, growth, DER, OCF/NI)
  with USD->IDR conversion, quality flags, and filtered important announcements in the dashboard
- Per-stock factors shown side by side: stage (MA150), RS 13w, CMF 20, VWAP 20,
  foreign net 20d, big-lot ratio
- Initial public release preparation
- Comprehensive README documentation
- Contributing guidelines
- License file (MIT)

## [0.1.0] - 2024-01-15

### Added

#### Core Features
- **TUI Application**: Beautiful terminal interface using Textual framework
- **Smart Agent**: True agentic AI flow with data gathering before analysis
- **Natural Language Support**: Indonesian and English language processing
- **Command Palette**: Autocomplete for slash commands

#### Analysis Modules
- **Technical Analysis**: RSI, MACD, SMA, EMA, Bollinger Bands, Stochastic, ATR
- **Fundamental Analysis**: PE, PB, ROE, ROA, Debt/Equity, Dividend Yield
- **Broker Flow Analysis**: Stockbit integration for broker summary data
- **Sector Analysis**: Sector-level aggregation and comparison

#### SAPTA Engine
- **Pre-Markup Detection**: ML-powered detection of accumulation phase
- **6 Analysis Modules**: Absorption, Compression, BB Squeeze, Elliott, Time Projection, Anti-Distribution
- **Trained Model**: XGBoost classifier with learned thresholds
- **Batch Scanning**: Scan multiple stocks for pre-markup candidates

#### Trading Tools
- **Trading Plan Generator**: Complete TP/SL/RR calculations
- **Position Sizing**: Risk-based lot size recommendations
- **Price Forecast**: Statistical price predictions with confidence intervals
- **Chart Generation**: Export charts as PNG files

#### Stock Screening
- **Preset Screeners**: Oversold, Overbought, Bullish, Bearish, Breakout, Momentum
- **Flexible Criteria**: Natural language to technical criteria parsing
- **Multiple Universes**: LQ45, IDX80, Popular, All (955 stocks)

#### Data Sources
- **Yahoo Finance**: Real-time and historical price data
- **Stockbit Integration**: Broker flow and sentiment data
- **Disk Caching**: Reduce API calls with smart caching

#### AI Integration
- **Multiple Models**: Support for various AI models via CLIProxyAPI
- **Conversation History**: Context-aware follow-up questions
- **Stock Analysis Prompts**: Specialized prompts for financial analysis

### Technical
- Python 3.11+ support
- Pydantic v2 for data validation
- Async/await architecture
- Type hints throughout codebase
- pytest test suite

---

## Version History

| Version | Date | Description |
|---------|------|-------------|
| 0.1.0 | 2024-01-15 | Initial alpha release |

---

## Roadmap

### v0.2.0 (Planned)
- [ ] Watchlist management
- [ ] Portfolio tracking
- [ ] Alert notifications
- [ ] Performance improvements

### v0.3.0 (Planned)
- [ ] Backtesting framework
- [ ] Strategy builder
- [ ] Historical performance analysis

### v0.4.0 (Planned)
- [ ] Multi-market support (US stocks)
- [ ] Cryptocurrency support
- [ ] Options analysis

### v1.0.0 (Planned)
- [ ] Stable API
- [ ] Full documentation
- [ ] Production ready
