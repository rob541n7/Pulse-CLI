"""Command registry and handler."""

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pulse.cli.app import PulseApp

from pulse.utils.logger import get_logger

log = get_logger(__name__)


class Command:
    """Represents a slash command."""

    def __init__(
        self,
        name: str,
        handler: Callable,
        description: str = "",
        usage: str = "",
        aliases: list[str] | None = None,
    ):
        self.name = name
        self.handler = handler
        self.description = description
        self.usage = usage or f"/{name}"
        self.aliases = aliases or []


class CommandRegistry:
    """Registry for slash commands."""

    def __init__(self, app: "PulseApp"):
        self.app = app
        self._commands: dict[str, Command] = {}
        self._register_builtin_commands()

    def register(
        self,
        name: str,
        handler: Callable,
        description: str = "",
        usage: str = "",
        aliases: list[str] | None = None,
    ) -> None:
        """Register a command."""
        cmd = Command(name, handler, description, usage, aliases)
        self._commands[name.lower()] = cmd

        for alias in aliases or []:
            self._commands[alias.lower()] = cmd

    def get(self, name: str) -> Command | None:
        """Get a command by name."""
        return self._commands.get(name.lower())

    def list_commands(self) -> list[Command]:
        """List all unique commands (excluding aliases)."""
        seen = set()
        commands = []

        for cmd in self._commands.values():
            if cmd.name not in seen:
                seen.add(cmd.name)
                commands.append(cmd)

        return sorted(commands, key=lambda c: c.name)

    async def execute(self, command_str: str) -> str | None:
        """Execute a command string."""
        parts = command_str.strip().split(maxsplit=1)
        cmd_name = parts[0].lstrip("/").lower()
        args = parts[1] if len(parts) > 1 else ""

        cmd = self.get(cmd_name)

        if not cmd:
            return f"Unknown command: /{cmd_name}. Type /help for available commands."

        try:
            result = await cmd.handler(args)
            return result
        except Exception as e:
            log.error(f"Command {cmd_name} failed: {e}")
            raise

    def _register_builtin_commands(self) -> None:
        """Register built-in commands."""

        self.register(
            "help",
            self._cmd_help,
            "Show available commands",
            "/help [command]",
            aliases=["h", "?"],
        )

        self.register(
            "models",
            self._cmd_models,
            "List or switch AI models",
            "/models [model_id]",
            aliases=["model", "m"],
        )

        self.register(
            "analyze",
            self._cmd_analyze,
            "Analyze a stock",
            "/analyze <TICKER>",
            aliases=["a", "stock"],
        )

        self.register(
            "broker",
            self._cmd_broker,
            "View broker flow analysis",
            "/broker <TICKER>",
            aliases=["b", "flow"],
        )

        self.register(
            "technical",
            self._cmd_technical,
            "Technical analysis",
            "/technical <TICKER>",
            aliases=["ta", "tech"],
        )

        self.register(
            "fundamental",
            self._cmd_fundamental,
            "Fundamental analysis",
            "/fundamental <TICKER>",
            aliases=["fa", "fund"],
        )

        self.register(
            "screen",
            self._cmd_screen,
            "Screen stocks",
            "/screen <criteria>",
            aliases=["s", "filter"],
        )

        self.register(
            "sector",
            self._cmd_sector,
            "Sector analysis",
            "/sector <SECTOR>",
            aliases=["sec"],
        )

        self.register(
            "compare",
            self._cmd_compare,
            "Compare stocks",
            "/compare <TICKER1> <TICKER2>",
            aliases=["cmp", "vs"],
        )

        self.register(
            "chart",
            self._cmd_chart,
            "Show price chart",
            "/chart <TICKER> [period]",
            aliases=["c", "grafik"],
        )

        self.register(
            "forecast",
            self._cmd_forecast,
            "Price forecast",
            "/forecast <TICKER> [days]",
            aliases=["fc", "prediksi"],
        )

        self.register(
            "clear",
            self._cmd_clear,
            "Clear chat history",
            "/clear",
            aliases=["cls"],
        )

        self.register(
            "auth",
            self._cmd_auth,
            "Authenticate with Stockbit",
            "/auth",
            aliases=["login"],
        )

        self.register(
            "ihsg",
            self._cmd_ihsg,
            "Show IHSG/index status",
            "/ihsg [index]",
            aliases=["index", "market"],
        )

        self.register(
            "plan",
            self._cmd_plan,
            "Generate trading plan with TP/SL/RR",
            "/plan <TICKER> [account_size]",
            aliases=["tp", "sl", "tradingplan"],
        )

        self.register(
            "sapta",
            self._cmd_sapta,
            "SAPTA PRE-MARKUP detection engine",
            "/sapta <TICKER> | /sapta scan [universe]",
            aliases=["premarkup", "markup"],
        )

        self.register(
            "bandar",
            self._cmd_bandar,
            "Bandarmology analysis (multi-day broker flow)",
            "/bandar <TICKER> [days] | /bandar scan [universe]",
            aliases=["bandarmology", "bm"],
        )

        self.register(
            "universe",
            self._cmd_universe,
            "Big cap universe (free float riil, likuid, non-HSC)",
            "/universe [rebuild [size]]",
            aliases=["bigcap", "uni"],
        )

        self.register(
            "ihsgx",
            self._cmd_ihsgx,
            "IHSG vs IHSG ex-HSC performance",
            "/ihsgx",
            aliases=["exhsc", "hsc"],
        )

        self.register(
            "swing",
            self._cmd_swing,
            "Swing 2-8 minggu: screener, analisa ticker, backtest",
            "/swing [TICKER] | /swing backtest [--nofilter]",
            aliases=["sw"],
        )

        self.register(
            "dashboard",
            self._cmd_dashboard,
            "Update data IDX & buka dashboard HTML",
            "/dashboard",
            aliases=["dash"],
        )

    async def _cmd_help(self, args: str) -> str:
        """Help command handler."""
        if args:
            cmd = self.get(args.strip())
            if cmd:
                aliases_str = ", ".join(f"/{a}" for a in cmd.aliases) if cmd.aliases else "None"
                return f"""/{cmd.name}

Description: {cmd.description}
Usage: {cmd.usage}
Aliases: {aliases_str}
"""
            else:
                return f"Unknown command: /{args}"

        lines = ["Available Commands\n"]

        for cmd in self.list_commands():
            aliases = f" ({', '.join(cmd.aliases)})" if cmd.aliases else ""
            lines.append(f"  /{cmd.name}{aliases} - {cmd.description}")

        lines.append("\nType /help <command> for detailed help.")

        return "\n".join(lines)

    async def _cmd_models(self, args: str) -> str | None:
        """Models command handler."""
        if args:
            model_id = args.strip()
            self.app.ai_client.set_model(model_id)

            model_info = self.app.ai_client.get_current_model()
            return f"Switched to model: {model_info['name']}"

        # No args - show modal
        self.app.show_models_modal()
        return None  # Don't output anything to chat

    async def _cmd_analyze(self, args: str) -> str:
        """Analyze command handler."""
        if not args:
            return "Please specify a ticker. Usage: /analyze BBCA"

        ticker = args.strip().upper()

        from pulse.core.analysis.broker_flow import BrokerFlowAnalyzer
        from pulse.core.analysis.technical import TechnicalAnalyzer
        from pulse.core.data.yfinance import YFinanceFetcher

        fetcher = YFinanceFetcher()
        stock = await fetcher.fetch_stock(ticker)

        if not stock:
            return f"Could not fetch data for {ticker}"

        tech_analyzer = TechnicalAnalyzer()
        technical = await tech_analyzer.analyze(ticker)

        broker_analyzer = BrokerFlowAnalyzer()
        broker = await broker_analyzer.analyze(ticker)

        data = {
            "stock": {
                "ticker": stock.ticker,
                "name": stock.name,
                "price": stock.current_price,
                "change": stock.change,
                "change_percent": stock.change_percent,
                "volume": stock.volume,
                "market_cap": stock.market_cap,
            },
            "technical": technical.to_summary() if technical else None,
            "broker": broker if broker else None,
        }

        response = await self.app.ai_client.analyze_stock(ticker, data)

        return response

    async def _cmd_broker(self, args: str) -> str:
        """Broker flow command handler."""
        if not args:
            return "Please specify a ticker. Usage: /broker BBCA"

        ticker = args.strip().upper()

        from pulse.core.analysis.broker_flow import BrokerFlowAnalyzer

        analyzer = BrokerFlowAnalyzer()

        if not analyzer.client.is_authenticated:
            return "Not authenticated with Stockbit. Run /auth first."

        result = await analyzer.analyze(ticker)

        if not result:
            return f"Could not fetch broker data for {ticker}"

        return analyzer.format_summary_table(result)

    async def _cmd_technical(self, args: str) -> str:
        """Technical analysis command handler."""
        if not args:
            return "Please specify a ticker. Usage: /technical BBCA"

        ticker = args.strip().upper()

        from pulse.core.analysis.technical import TechnicalAnalyzer

        analyzer = TechnicalAnalyzer()
        indicators = await analyzer.analyze(ticker)

        if not indicators:
            return f"Could not analyze {ticker}"

        summary = analyzer.get_indicator_summary(indicators)

        lines = [f"Technical Analysis: {ticker}\n"]

        for item in summary:
            status = f" ({item['status']})" if item.get("status") else ""
            lines.append(f"  {item['name']}: {item['value']}{status}")

        return "\n".join(lines)

    async def _cmd_fundamental(self, args: str) -> str:
        """Fundamental analysis command handler."""
        if not args:
            return "Please specify a ticker. Usage: /fundamental BBCA"

        ticker = args.strip().upper()

        from pulse.core.analysis.fundamental import FundamentalAnalyzer

        analyzer = FundamentalAnalyzer()
        data = await analyzer.analyze(ticker)

        if not data:
            return f"Could not fetch fundamental data for {ticker}"

        summary = analyzer.get_summary(data)
        score_data = analyzer.score_valuation(data)

        lines = [f"Fundamental Analysis: {ticker}\n"]
        lines.append(f"Valuation Score: {score_data['score']}/100\n")

        current_category = ""
        for item in summary:
            if item["category"] != current_category:
                current_category = item["category"]
                lines.append(f"\n{current_category}")

            status = f" ({item['status']})" if item.get("status") else ""
            lines.append(f"  {item['name']}: {item['value']}{status}")

        return "\n".join(lines)

    async def _cmd_screen(self, args: str) -> str:
        """Screen stocks based on technical/fundamental criteria."""
        if not args:
            return """Stock Screening

Usage: /screen <criteria> [--universe=lq45|idx80|popular]

Presets:
  /screen oversold    - RSI < 30 (siap bounce)
  /screen overbought  - RSI > 70 (siap turun)
  /screen bullish     - MACD bullish + price > SMA20
  /screen bearish     - MACD bearish + price < SMA20
  /screen breakout    - Near resistance + volume spike
  /screen momentum    - RSI 50-70 + MACD bullish
  /screen undervalued - PE < 15 + ROE > 10%

Flexible:
  /screen rsi<30
  /screen rsi>70
  /screen pe<15

Universe:
  --universe=lq45    - 43 saham (fast)
  --universe=idx80   - 83 saham (medium)
  --universe=popular - 113 saham (slower)

Example:
  /screen oversold --universe=idx80
"""

        from pulse.core.screener import ScreenPreset, StockScreener, StockUniverse

        # Parse universe option
        universe_type = None
        criteria_str = args

        if "--universe=" in args.lower():
            import re

            match = re.search(r"--universe=(\w+)", args.lower())
            if match:
                universe_map = {
                    "lq45": StockUniverse.LQ45,
                    "idx80": StockUniverse.IDX80,
                    "popular": StockUniverse.POPULAR,
                    "all": StockUniverse.ALL,
                }
                universe_type = universe_map.get(match.group(1))
                criteria_str = re.sub(r"\s*--universe=\w+", "", args).strip()

        screener = StockScreener(universe_type=universe_type)
        args_lower = criteria_str.strip().lower()

        # Check if it's a preset
        preset_names = [p.value for p in ScreenPreset]
        if args_lower in preset_names:
            results = await screener.screen_preset(ScreenPreset(args_lower))
            title = f"Screening: {args_lower.upper()} ({len(screener.universe)} stocks)"
        else:
            # Use flexible criteria
            results = await screener.screen_criteria(criteria_str)
            title = f"Screening: {criteria_str} ({len(screener.universe)} stocks)"

        if not results:
            return f"No stocks found matching: {criteria_str}"

        return screener.format_results(results, title=title, show_details=True)

    async def _cmd_sector(self, args: str) -> str:
        """Sector analysis command handler."""
        from pulse.core.analysis.sector import SectorAnalyzer
        from pulse.utils.constants import IDX_SECTORS

        analyzer = SectorAnalyzer()

        if not args:
            sectors = analyzer.list_sectors()

            lines = ["Available Sectors\n"]
            for s in sectors:
                lines.append(f"  {s['name']} ({s['stock_count']} stocks)")

            lines.append("\nUse /sector <SECTOR> for sector analysis.")

            return "\n".join(lines)

        sector = args.strip().upper()

        if sector not in IDX_SECTORS:
            return f"Unknown sector: {sector}"

        analysis = await analyzer.analyze_sector(sector)

        if not analysis:
            return f"Could not analyze sector {sector}"

        lines = [f"Sector Analysis: {sector}\n"]
        lines.append(f"Stocks Analyzed: {analysis.total_stocks}")
        lines.append(f"Avg Change: {analysis.avg_change_percent:.2f}%\n")

        if analysis.top_gainers:
            lines.append("Top Gainers")
            for g in analysis.top_gainers[:3]:
                lines.append(f"  {g['ticker']}: +{g['change_percent']:.2f}%")

        if analysis.top_losers:
            lines.append("\nTop Losers")
            for l in analysis.top_losers[:3]:
                lines.append(f"  {l['ticker']}: {l['change_percent']:.2f}%")

        return "\n".join(lines)

    async def _cmd_compare(self, args: str) -> str:
        """Compare stocks command handler."""
        if not args:
            return "Please specify tickers. Usage: /compare BBCA BBRI"

        tickers = args.strip().upper().split()

        if len(tickers) < 2:
            return "Please specify at least 2 tickers to compare."

        from pulse.core.data.yfinance import YFinanceFetcher

        fetcher = YFinanceFetcher()
        results = []

        for ticker in tickers[:4]:  # Max 4 tickers
            stock = await fetcher.fetch_stock(ticker)
            if stock:
                results.append(
                    {
                        "ticker": stock.ticker,
                        "name": stock.name or ticker,
                        "price": stock.current_price,
                        "change": stock.change,
                        "change_pct": stock.change_percent,
                        "volume": stock.volume,
                    }
                )

        if len(results) < 2:
            return "Could not fetch enough data for comparison."

        lines = ["Stock Comparison\n"]
        lines.append(f"{'Ticker':<8} {'Price':>12} {'Change':>10} {'Volume':>14}")
        lines.append("-" * 48)

        for r in results:
            change_str = f"{r['change_pct']:+.2f}%"
            vol_str = f"{r['volume']:,.0f}"
            lines.append(f"{r['ticker']:<8} {r['price']:>12,.0f} {change_str:>10} {vol_str:>14}")

        return "\n".join(lines)

    async def _cmd_chart(self, args: str) -> str:
        """Chart command handler - generate and save price chart as PNG."""
        if not args:
            return "Please specify a ticker. Usage: /chart BBCA [1mo|3mo|6mo|1y]"

        parts = args.strip().upper().split()
        ticker = parts[0]
        period = parts[1].lower() if len(parts) > 1 else "3mo"

        # Validate period
        valid_periods = ["1mo", "3mo", "6mo", "1y", "2y"]
        if period not in valid_periods:
            period = "3mo"

        from pulse.core.chart_generator import ChartGenerator
        from pulse.core.data.yfinance import YFinanceFetcher

        fetcher = YFinanceFetcher()
        df = fetcher.get_history_df(ticker, period)

        if df is None or df.empty:
            return f"Could not fetch historical data for {ticker}"

        dates = df.index.strftime("%Y-%m-%d").tolist()
        prices = df["close"].tolist()
        volumes = df["volume"].tolist() if "volume" in df.columns else None

        # Generate PNG chart
        generator = ChartGenerator()
        filepath = generator.price_chart(ticker, dates, prices, volumes, period)

        if not filepath:
            return f"Failed to generate chart for {ticker}"

        # Get current price info
        current = prices[-1]
        prev = prices[-2] if len(prices) > 1 else current
        change = current - prev
        change_pct = (change / prev * 100) if prev else 0

        return f"""{ticker}: Rp {current:,.0f} ({change:+,.0f}, {change_pct:+.2f}%)

Chart saved: {filepath}"""

    async def _cmd_forecast(self, args: str) -> str:
        """Forecast command handler - predict future prices and save chart as PNG."""
        if not args:
            return "Please specify a ticker. Usage: /forecast BBCA [7|14|30]"

        parts = args.strip().upper().split()
        ticker = parts[0]

        # Parse days
        days = 7
        if len(parts) > 1:
            try:
                days = int(parts[1])
                days = min(max(days, 1), 30)  # Clamp between 1-30
            except ValueError:
                days = 7

        from pulse.core.chart_generator import ChartGenerator
        from pulse.core.data.yfinance import YFinanceFetcher
        from pulse.core.forecasting import PriceForecaster

        fetcher = YFinanceFetcher()
        df = fetcher.get_history_df(ticker, "6mo")

        if df is None or df.empty:
            return f"Not enough data for forecasting {ticker}"

        prices = df["close"].tolist()
        dates = df.index.strftime("%Y-%m-%d").tolist()

        forecaster = PriceForecaster()
        result = await forecaster.forecast(ticker, prices, dates, days)

        if not result:
            return f"Forecast failed for {ticker}"

        # Generate PNG chart
        generator = ChartGenerator()
        filepath = generator.forecast_chart(
            ticker=ticker,
            dates=dates,
            historical=prices,
            forecast=result.predictions,
            lower_bound=result.lower_bound,
            upper_bound=result.upper_bound,
            forecast_days=days,
        )

        # Format summary
        current = prices[-1]
        target = result.target_price
        change_pct = (target - current) / current * 100
        trend_icon = "UP" if change_pct > 0 else "DOWN" if change_pct < 0 else "SIDEWAYS"

        summary = f"""Forecast: {ticker} ({days} days)

Current: Rp {current:,.0f}
Target: Rp {target:,.0f} ({change_pct:+.2f}%)
Trend: {trend_icon}
Support: Rp {result.support:,.0f}
Resistance: Rp {result.resistance:,.0f}
Confidence: {result.confidence:.0f}%"""

        if filepath:
            summary += f"\n\nChart saved: {filepath}"

        return summary

    async def _cmd_clear(self, args: str) -> str | None:
        """Clear chat history."""
        self.app.action_clear()
        return None

    async def _cmd_auth(self, args: str) -> str:
        """Authenticate with Stockbit."""
        from pulse.core.data.stockbit import StockbitClient

        client = StockbitClient()
        args_lower = args.strip().lower() if args else ""

        # Check subcommands
        if args_lower.startswith("set-token") or args_lower.startswith("token"):
            # Extract token from args
            parts = args.strip().split(maxsplit=1)
            if len(parts) < 2:
                return """Set Stockbit Token

Usage: /auth set-token <JWT_TOKEN>

How to get token:
1. Open https://stockbit.com in Chrome and login
2. Open DevTools (F12 or Cmd+Option+I)
3. Go to Network tab
4. Click any stock (e.g., BBCA)
5. Find request to exodus.stockbit.com
6. Copy the Authorization header value (without 'Bearer ')

Example:
/auth set-token eyJhbGciOiJSUzI1NiIs...

Note: Token is valid for ~24 hours. Update when expired."""

            token = parts[1].strip()
            # Remove "Bearer " prefix if present
            if token.lower().startswith("bearer "):
                token = token[7:]

            success = client.set_token(token, save=True)
            if success:
                status = client.get_token_status()
                hours = status.get("hours_remaining", 0)
                return f"""✅ Token saved successfully!

Token valid for: {hours:.1f} hours
Saved to: {client.secrets_file}

You can now use /broker command."""
            else:
                return "❌ Invalid token. Make sure you copied the full JWT token."

        if args_lower == "status":
            status = client.get_token_status()
            if not status["has_token"]:
                return """❌ No Stockbit token found.

Set token with: /auth set-token <JWT_TOKEN>
Or set STOCKBIT_TOKEN environment variable."""

            expires = (
                status["expires_at"].strftime("%Y-%m-%d %H:%M")
                if status["expires_at"]
                else "Unknown"
            )
            hours = status["hours_remaining"]
            valid_str = "✅ Valid" if status["is_valid"] else "❌ Expired"

            return f"""Stockbit Auth Status

Status: {valid_str}
Source: {status["source"]}
Expires: {expires}
Hours remaining: {hours:.1f if hours else 0}"""

        # Default - show auth info
        if client.is_authenticated:
            status = client.get_token_status()
            hours = status.get("hours_remaining", 0)
            if status["is_valid"]:
                return f"""✅ Authenticated with Stockbit

Token source: {status["source"]}
Valid for: {hours:.1f} hours

Commands:
  /auth status     - Check token status
  /auth set-token  - Set new token"""
            else:
                return f"""⚠️ Stockbit token expired!

Please update your token:
  /auth set-token <NEW_TOKEN>

How to get token:
1. Login to stockbit.com in browser
2. Open DevTools > Network tab
3. Copy Authorization header from any exodus.stockbit.com request"""

        return """Stockbit Authentication

You need a Stockbit token to use broker flow features.

Commands:
  /auth set-token <TOKEN>  - Set token manually (recommended)
  /auth status             - Check token status

How to get token:
1. Open https://stockbit.com in Chrome and login
2. Open DevTools (F12 or Cmd+Option+I)
3. Go to Network tab
4. Click any stock page
5. Find request to exodus.stockbit.com
6. Copy the Authorization header (after 'Bearer ')

Alternative: Set STOCKBIT_TOKEN environment variable in .env file.

Note: Token is valid for ~24 hours."""

    async def _cmd_ihsg(self, args: str) -> str:
        """Show IHSG or other index status."""
        # Determine which index to show
        index_name = args.strip().upper() if args else "IHSG"

        valid_indices = ["IHSG", "LQ45", "IDX30", "JII"]
        if index_name not in valid_indices:
            return f"""Unknown index: {index_name}

Available indices:
  IHSG  - IDX Composite
  LQ45  - IDX LQ45
  IDX30 - IDX30
  JII   - Jakarta Islamic Index

Usage: /ihsg [index]
Example: /ihsg LQ45
"""

        from pulse.core.chart_generator import ChartGenerator
        from pulse.core.data.yfinance import YFinanceFetcher

        fetcher = YFinanceFetcher()
        index_data = await fetcher.fetch_index(index_name)

        if not index_data:
            return f"Could not fetch data for {index_name}"

        # Generate chart
        yf_ticker = fetcher.INDEX_MAPPING.get(index_name, ("^JKSE", "IHSG"))[0]
        df = fetcher.get_history_df(yf_ticker, "3mo")
        chart_path = None

        if df is not None and not df.empty:
            generator = ChartGenerator()
            dates = df.index.strftime("%Y-%m-%d").tolist()
            prices = df["close"].tolist()
            chart_path = generator.price_chart(index_name, dates, prices, period="3mo")

        # Format response
        change_sign = "+" if index_data.change >= 0 else ""

        result = f"""{index_data.name} ({index_name})

Value: {index_data.current_price:,.2f}
Change: {change_sign}{index_data.change:,.2f} ({change_sign}{index_data.change_percent:.2f}%)
Range: {index_data.day_low:,.2f} - {index_data.day_high:,.2f}
52W Range: {index_data.week_52_low:,.2f} - {index_data.week_52_high:,.2f}"""

        if chart_path:
            result += f"\n\nChart saved: {chart_path}"

        return result

    async def _cmd_plan(self, args: str) -> str:
        """Trading plan command handler."""
        if not args:
            return """Trading Plan - Generate TP/SL/RR analysis

Usage: /plan <TICKER> [account_size]

Examples:
  /plan BBCA              - Trading plan with default account size
  /plan BBRI 50000000     - Trading plan with Rp 50 juta account

Output includes:
  - Entry price (current market)
  - Take Profit levels (TP1, TP2, TP3)
  - Stop Loss with method used
  - Risk/Reward ratio analysis
  - Position sizing suggestion
  - Execution strategy"""

        parts = args.strip().split()
        ticker = parts[0].upper()

        # Parse optional account size
        account_size = None
        if len(parts) > 1:
            try:
                account_size = float(parts[1].replace(",", "").replace(".", ""))
            except ValueError:
                return f"Invalid account size: {parts[1]}"

        from pulse.core.trading_plan import TradingPlanGenerator

        generator = TradingPlanGenerator()
        plan = await generator.generate(ticker)

        if not plan:
            return f"Could not generate trading plan for {ticker}. Make sure the ticker is valid."

        # Format with optional account size
        return generator.format_plan(plan, account_size=account_size)

    async def _cmd_sapta(self, args: str) -> str:
        """SAPTA PRE-MARKUP detection command handler."""
        if not args:
            return """SAPTA - PRE-MARKUP Detection Engine (ML-powered)

Usage:
  /sapta <TICKER>              - Analyze single stock
  /sapta scan [universe]       - Scan for PRE-MARKUP candidates

Universe Options:
  /sapta scan lq45             - Scan LQ45 (45 stocks, fast)
  /sapta scan idx80            - Scan IDX80 (80 stocks)
  /sapta scan popular          - Scan popular stocks (113 stocks)
  /sapta scan all              - Scan ALL 955 stocks (slower)

Options:
  --detailed                   - Show module breakdown

Examples:
  /sapta BBCA                  - Analyze BBCA
  /sapta BBRI --detailed       - Detailed analysis
  /sapta scan all              - Scan semua saham untuk pre-markup

Natural Language (via chat):
  "carikan saham pre-markup"   - Scan LQ45
  "carikan saham pre-markup semua" - Scan all 955 stocks

Status Levels (ML-learned thresholds):
  PRE-MARKUP  (score >= 47)    - Ready to breakout
  SIAP        (score >= 35)    - Almost ready
  WATCHLIST   (score >= 24)    - Monitor
  ABAIKAN     (score < 24)     - Skip

Modules:
  1. Supply Absorption - Smart money accumulation
  2. Compression - Volatility contraction
  3. BB Squeeze - Bollinger Band squeeze
  4. Elliott Wave - Wave position & Fibonacci
  5. Time Projection - Fib time + planetary aspects
  6. Anti-Distribution - Filter distribution patterns
"""

        from pulse.core.sapta import SaptaEngine, SaptaStatus
        from pulse.core.screener import StockScreener, StockUniverse

        engine = SaptaEngine()
        args_lower = args.lower().strip()
        detailed = "--detailed" in args_lower
        args_clean = args_lower.replace("--detailed", "").strip()

        # Check if it's a scan command
        if args_clean.startswith("scan"):
            parts = args_clean.split()
            universe = parts[1] if len(parts) > 1 else "lq45"

            # Check for "all" universe - scan all stocks from tickers.json
            if universe in ["all", "semua", "955"]:
                try:
                    from pulse.core.sapta.ml.data_loader import SaptaDataLoader

                    loader = SaptaDataLoader()
                    tickers = loader.get_all_tickers()
                    universe_name = f"ALL ({len(tickers)} stocks)"
                    min_status = SaptaStatus.SIAP  # Higher threshold for large scan
                except Exception as e:
                    return f"Could not load tickers: {e}"
            else:
                # Select universe using screener's universe logic
                universe_map = {
                    "lq45": StockUniverse.LQ45,
                    "idx80": StockUniverse.IDX80,
                    "popular": StockUniverse.POPULAR,
                }
                universe_type = universe_map.get(universe, StockUniverse.LQ45)
                screener = StockScreener(universe_type=universe_type)
                tickers = screener.universe
                universe_name = universe.upper()
                min_status = SaptaStatus.WATCHLIST

            # Scan
            results = await engine.scan(tickers, min_status=min_status)

            if not results:
                return f"No stocks found in {universe_name} matching SAPTA criteria."

            return engine.format_scan_results(
                results, title=f"SAPTA Scan: {universe_name} ({len(results)} found)"
            )

        # Single stock analysis
        ticker = args_clean.split()[0].upper()

        result = await engine.analyze(ticker)

        if not result:
            return f"Could not analyze {ticker}. Make sure the ticker is valid."

        return engine.format_result(result, detailed=detailed)

    async def _cmd_bandar(self, args: str) -> str:
        """Bandarmology analysis command handler."""
        if not args:
            return """BANDARMOLOGY - Advanced Broker Flow Analysis

Usage:
  /bandar <TICKER>              - Analyze single stock (default 10 days)
  /bandar <TICKER> <days>       - Analyze with custom period
  /bandar scan [universe]       - Scan for markup-ready candidates

Period Options:
  /bandar BBCA                  - Last 10 trading days
  /bandar BBCA 5                - Last 5 trading days
  /bandar BBCA 20               - Last 20 trading days (1 month)

Scan Options:
  /bandar scan                  - Scan LQ45 (default)
  /bandar scan lq45             - Scan LQ45 (45 stocks)
  /bandar scan idx80            - Scan IDX80 (80 stocks)
  /bandar scan popular          - Scan popular stocks

Options:
  --detailed                    - Show daily timeline

Examples:
  /bandar BBCA                  - Analyze BBCA (10 days)
  /bandar BBRI 20               - Analyze BBRI (20 days / ~1 month)
  /bandar ANTM --detailed       - Detailed with daily breakdown
  /bandar scan lq45             - Scan LQ45 for markup candidates

Analysis Includes:
  - Flow Momentum Score (0-100)
  - Markup Readiness Score (0-100)
  - Accumulation Phase Detection
  - Smart Money vs Retail Flow
  - Broker Composition by Profile
  - Pattern Detection (Crossing, Dominasi, Retail Trap, etc.)
  - Top Broker Consistency Tracking
  - Daily Timeline (with --detailed)

Broker Profiles:
  - Smart Money Foreign: AK, BK, MS, GR, LG, KZ, CS, DX
  - Bandar/Gorengan: SQ, MG, EP, DR, BZ
  - Retail: XA, AZ, KI, YO, ZP
  - Local Institutional: CC, NI, OD, TP, IF
"""

        from pulse.core.analysis.bandarmology import BandarmologyEngine
        from pulse.core.screener import StockScreener, StockUniverse

        engine = BandarmologyEngine()
        args_lower = args.lower().strip()
        detailed = "--detailed" in args_lower
        args_clean = args_lower.replace("--detailed", "").strip()

        # Check if it's a scan command
        if args_clean.startswith("scan"):
            parts = args_clean.split()
            universe = parts[1] if len(parts) > 1 else "lq45"

            # Select universe
            universe_map = {
                "lq45": StockUniverse.LQ45,
                "idx80": StockUniverse.IDX80,
                "popular": StockUniverse.POPULAR,
            }
            universe_type = universe_map.get(universe, StockUniverse.LQ45)
            screener = StockScreener(universe_type=universe_type)
            tickers = screener.universe
            universe_name = universe.upper()

            # Scan for markup-ready candidates
            results = await engine.scan_markup_ready(tickers, min_score=60, days=10)

            if not results:
                return f"No markup-ready stocks found in {universe_name}."

            return engine.format_scan_results(
                results, title=f"Bandarmology Scan: {universe_name} ({len(results)} found)"
            )

        # Single stock analysis
        parts = args_clean.split()
        ticker = parts[0].upper()

        # Parse optional days parameter
        days = 10  # Default
        if len(parts) > 1:
            try:
                days = int(parts[1])
                days = min(max(days, 3), 60)  # Clamp between 3-60 days
            except ValueError:
                pass  # Keep default

        result = await engine.analyze(ticker, days=days)

        if not result:
            return f"Could not analyze {ticker}. Make sure the ticker is valid and you have a valid Stockbit token."

        return engine.format_report(result, detailed=detailed)

    async def _cmd_universe(self, args: str) -> str:
        """Show or rebuild the big-cap universe."""
        import asyncio

        from pulse.core.idx.universe import (
            UniverseRules,
            build_universe,
            format_universe,
            load_universe,
        )

        parts = args.lower().split()
        try:
            if parts and parts[0] == "rebuild":
                size = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 70
                u = await asyncio.to_thread(
                    build_universe, UniverseRules(size=size), refresh_ownership=True
                )
            else:
                u = load_universe()
        except FileNotFoundError as e:
            return str(e)
        return format_universe(u)

    async def _cmd_ihsgx(self, args: str) -> str:
        """IHSG vs IHSG ex-HSC."""
        import asyncio

        from pulse.core.idx.benchmark import build_ihsg_ex_hsc, format_benchmark

        try:
            bench = await asyncio.to_thread(build_ihsg_ex_hsc)
        except FileNotFoundError as e:
            return str(e)
        return format_benchmark(bench)

    async def _cmd_swing(self, args: str) -> str:
        """Swing screener / single ticker / backtest."""
        import asyncio

        from pulse.core.idx import swing

        parts = args.split()
        params = swing.SwingParams(market_filter="--nofilter" not in args.lower())
        try:
            ind, bench, mcap = await asyncio.to_thread(swing.load_market, params)
            if parts and parts[0].lower() == "backtest":
                res = await asyncio.to_thread(swing.backtest, ind, mcap, bench, params)
                return swing.format_backtest(res)
            snap = swing.screen(ind, swing.current_universe(), params)
        except FileNotFoundError as e:
            return str(e)
        if parts:
            return swing.format_ticker(parts[0].upper(), snap)
        return swing.format_screen(snap)

    async def _cmd_dashboard(self, args: str) -> str:
        """Merge new IDX files, rebuild and open the HTML dashboard."""
        import asyncio

        from pulse.core.idx.dashboard import build_dashboard

        try:
            path = await asyncio.to_thread(build_dashboard, True)
        except FileNotFoundError as e:
            return str(e)
        return f"Dashboard diperbarui dan dibuka:\n{path}"
