import asyncio
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
import json
import uuid

from models import StrategyConfig, StrategyStatus, StrategyType
from db import Database, init_database, get_portfolio_summary
from config_parser import ConfigParser
from container_manager import ContainerManager
from backtest_runner import BacktestRunner
from freqai_adapter import FreqAIAdapter
from slack_notifier import SlackNotifier


class FreqtradeManager:
    def __init__(
        self,
        db: Database,
        config_parser: ConfigParser,
        container_manager: ContainerManager,
        backtest_runner: BacktestRunner,
        freqai_adapter: FreqAIAdapter,
        slack_notifier: SlackNotifier,
        trade_monitor=None,
        templates_dir: str = "/templates",
    ):
        self.db = db
        self.config_parser = config_parser
        self.container_manager = container_manager  # May be None
        self.backtest_runner = backtest_runner
        self.freqai_adapter = freqai_adapter
        self.slack = slack_notifier
        self.trade_monitor = trade_monitor
        self.templates = self._load_templates(templates_dir)

    def _load_templates(self, templates_dir: str) -> Dict[str, Any]:
        default_templates = {
            "grid_dca": {
                "name": "GridDCA (Mean Reversion)",
                "strategy_type": StrategyType.GRID_DCA,
                "strategy_file": "GridDCA",
                "description": "Best performer: 68.6% win rate. RSI oversold entry with DCA positioning.",
                "default_config": {
                    "stoploss": -0.10,
                    "max_open_trades": 3,
                    "stake_amount": 100,
                    "timeframe": "15m",
                    "trailing_stop": False,
                },
                "params": [
                    {
                        "name": "rsi_oversold",
                        "label": "RSI Oversold",
                        "type": "slider",
                        "min": 20,
                        "max": 35,
                        "default": 25,
                    },
                    {
                        "name": "rsi_overbought",
                        "label": "RSI Overbought",
                        "type": "slider",
                        "min": 65,
                        "max": 80,
                        "default": 75,
                    },
                    {
                        "name": "take_profit_pct",
                        "label": "Take Profit %",
                        "type": "number",
                        "default": 2.0,
                    },
                ],
            },
            "oscillator_confluence": {
                "name": "OscillatorConfluence (Multi-Indicator)",
                "strategy_type": StrategyType.OSCILLATOR_CONFLUENCE,
                "strategy_file": "OscillatorConfluence",
                "description": "Enter when 2+ oscillators show oversold. EMA200 uptrend filter + ADX confirmation.",
                "default_config": {
                    "stoploss": -0.05,
                    "max_open_trades": 3,
                    "stake_amount": 330,
                    "timeframe": "15m",
                    "trailing_stop": True,
                    "trailing_stop_positive": 0.02,
                    "trailing_stop_positive_offset": 0.03,
                    "minimal_roi": {"0": 0.10, "120": 0.05, "240": 0.03},
                },
                "params": [
                    {
                        "name": "confluence_threshold",
                        "label": "Confluence Threshold",
                        "type": "number",
                        "default": 2,
                    },
                    {
                        "name": "adx_threshold",
                        "label": "ADX Threshold",
                        "type": "slider",
                        "min": 15,
                        "max": 30,
                        "default": 20,
                    },
                ],
            },
            "scalping_quick": {
                "name": "ScalpingQuick (High-Frequency)",
                "strategy_type": StrategyType.SCALPING_QUICK,
                "strategy_file": "ScalpingQuick",
                "description": "5min scalping with momentum + volume spike entries. 0.5-1.5% targets.",
                "default_config": {
                    "stoploss": -0.015,
                    "max_open_trades": 5,
                    "stake_amount": 50,
                    "timeframe": "5m",
                    "trailing_stop": True,
                    "trailing_stop_positive": 0.005,
                    "trailing_stop_positive_offset": 0.008,
                    "minimal_roi": {"0": 0.015, "5": 0.012, "10": 0.008, "15": 0.005},
                },
                "params": [
                    {
                        "name": "rsi_entry",
                        "label": "RSI Entry Level",
                        "type": "slider",
                        "min": 35,
                        "max": 50,
                        "default": 40,
                    },
                    {
                        "name": "volume_mult",
                        "label": "Volume Multiplier",
                        "type": "number",
                        "default": 1.5,
                    },
                ],
            },
            "breakout_momentum": {
                "name": "BreakoutMomentum (Resistance Breakout)",
                "strategy_type": StrategyType.BREAKOUT_MOMENTUM,
                "strategy_file": "BreakoutMomentum",
                "description": "20-candle high breakout with volume confirmation. ATR trailing stop.",
                "default_config": {
                    "stoploss": -0.05,
                    "max_open_trades": 3,
                    "stake_amount": 100,
                    "timeframe": "15m",
                    "trailing_stop": True,
                    "trailing_stop_positive": 0.008,
                    "trailing_stop_positive_offset": 0.012,
                    "minimal_roi": {"0": 0.06, "30": 0.03, "60": 0.015, "120": 0.005},
                },
                "params": [
                    {
                        "name": "breakout_period",
                        "label": "Breakout Period",
                        "type": "number",
                        "default": 20,
                    },
                    {
                        "name": "adx_threshold",
                        "label": "ADX Threshold",
                        "type": "slider",
                        "min": 18,
                        "max": 30,
                        "default": 22,
                    },
                    {
                        "name": "volume_mult",
                        "label": "Volume Multiplier",
                        "type": "number",
                        "default": 1.8,
                    },
                ],
            },
            "trend_momentum": {
                "name": "TrendMomentum (Trend Following)",
                "strategy_type": StrategyType.TREND_MOMENTUM,
                "strategy_file": "TrendMomentum",
                "description": "Trade in direction of 1h EMA200 on pullbacks with momentum confirmation.",
                "default_config": {
                    "stoploss": -0.05,
                    "max_open_trades": 3,
                    "stake_amount": 100,
                    "timeframe": "15m",
                    "trailing_stop": True,
                    "trailing_stop_positive": 0.01,
                },
                "params": [
                    {
                        "name": "ema_period",
                        "label": "EMA Period",
                        "type": "select",
                        "default": 50,
                        "options": [
                            {"value": 20, "label": "20 (Fast)"},
                            {"value": 50, "label": "50 (Medium)"},
                        ],
                    },
                    {
                        "name": "adx_threshold",
                        "label": "ADX Threshold",
                        "type": "slider",
                        "min": 15,
                        "max": 30,
                        "default": 20,
                    },
                    {
                        "name": "rsi_min",
                        "label": "RSI Minimum",
                        "type": "slider",
                        "min": 40,
                        "max": 55,
                        "default": 45,
                    },
                ],
            },
            "grid_dca_freqai": {
                "name": "GridDCA + FreqAI (ML Enhanced)",
                "strategy_type": StrategyType.GRID_DCA,
                "strategy_file": "GridDCA_hyperopted",
                "description": "FreqAI-enhanced strategy with ML predictions, regime detection, and auto-adjusting parameters.",
                "default_config": {
                    "stoploss": -0.10,
                    "max_open_trades": 4,
                    "stake_amount": 100,
                    "timeframe": "15m",
                    "use_freqai": True,
                    "freqai_model": "lightgbm",
                    "trailing_stop": False,
                },
                "params": [
                    {
                        "name": "rsi_oversold",
                        "label": "RSI Oversold",
                        "type": "slider",
                        "min": 25,
                        "max": 35,
                        "default": 30,
                    },
                    {
                        "name": "take_profit_pct",
                        "label": "Take Profit %",
                        "type": "number",
                        "default": 3.0,
                    },
                ],
            },
            "swing_dca": {
                "name": "SwingDCA 1H (Mean Reversion Swing)",
                "strategy_type": StrategyType.GRID_DCA,
                "strategy_file": "SwingDCA",
                "description": "1-hour timeframe mean reversion with DCA. Captures bigger swings, wider stops, longer holds.",
                "default_config": {
                    "stoploss": -0.08,
                    "max_open_trades": 3,
                    "stake_amount": 100,
                    "timeframe": "1h",
                    "trailing_stop": True,
                    "trailing_stop_positive": 0.015,
                    "trailing_stop_positive_offset": 0.02,
                    "trailing_only_offset_is_reached": True,
                    "minimal_roi": {"0": 0.04, "60": 0.02, "240": 0.01},
                },
                "params": [
                    {
                        "name": "rsi_oversold",
                        "label": "RSI Oversold",
                        "type": "slider",
                        "min": 25,
                        "max": 45,
                        "default": 40,
                    },
                    {
                        "name": "take_profit_pct",
                        "label": "Take Profit %",
                        "type": "number",
                        "default": 3.5,
                    },
                ],
            },
        }

        templates_path = Path(templates_dir)
        if templates_path.exists():
            for template_file in templates_path.glob("*.json"):
                try:
                    with open(template_file, "r") as f:
                        template_data = json.load(f)
                        default_templates[template_file.stem] = template_data
                except Exception as e:
                    print(f"Error loading template {template_file}: {e}")

        return default_templates

    async def auto_detect_strategies(self) -> List[Dict[str, Any]]:
        existing_configs = self.config_parser.detect_existing_configs()

        detected = []
        for config_info in existing_configs:
            strategy_id = str(uuid.uuid4())

            existing = await self.db.get_strategy(strategy_id)
            if existing:
                continue

            strategy = StrategyConfig(
                id=strategy_id,
                name=config_info["name"],
                strategy_type=StrategyType.CUSTOM,
                strategy_file=config_info["strategy_file"],
                config_path=config_info["config_path"],
                exchange=config_info["exchange"],
                pairs=config_info["pairs"],
                timeframe=config_info["timeframe"],
                stake_amount=config_info["stake_amount"],
                max_open_trades=config_info["max_open_trades"],
                docker_port=config_info["port"],
                use_freqai=config_info["use_freqai"],
                dry_run=config_info["dry_run"],
                status=StrategyStatus.STOPPED,
            )

            detected.append(strategy.dict())

        return detected

    async def create_strategy_from_template(
        self, template_id: str, customizations: Dict[str, Any]
    ) -> str:
        if template_id not in self.templates:
            raise ValueError(f"Template {template_id} not found")

        template = self.templates[template_id]

        strategy_id = str(uuid.uuid4())
        name = customizations.get("name", template["name"])
        pairs = customizations.get("pairs", ["BTC/USDT"])
        exchange = customizations.get("exchange", "kraken")

        port = await self.db.get_next_port()

        default_config = template["default_config"].copy()
        params = {}

        for param in template.get("params", []):
            param_name = param["name"]
            if param_name in customizations:
                params[param_name] = customizations[param_name]
            else:
                params[param_name] = param.get("default")

        config = self.config_parser.create_config(
            strategy_file=template["strategy_file"],
            exchange=customizations.get("exchange", "kraken"),
            pairs=pairs,
            timeframe=default_config.get("timeframe", "15m"),
            stake_amount=default_config.get("stake_amount", 100),
            max_open_trades=default_config.get("max_open_trades", 3),
            dry_run=customizations.get("dry_run", True),
            port=port,
            custom_params=params,
        )

        if default_config.get("use_freqai"):
            config["use_freqai"] = True
            config["freqai_model"] = default_config.get("freqai_model", "lightgbm")

        config_path = f"/configs/{strategy_id}.json"
        self.config_parser.save_config(config_path, config)

        strategy = StrategyConfig(
            id=strategy_id,
            name=name,
            strategy_type=template["strategy_type"],
            description=template.get("description"),
            strategy_file=template["strategy_file"],
            config_path=config_path,
            exchange=exchange,
            pairs=pairs,
            timeframe=default_config.get("timeframe", "15m"),
            stake_amount=default_config.get("stake_amount", 100),
            max_open_trades=default_config.get("max_open_trades", 3),
            docker_port=port,
            use_freqai=default_config.get("use_freqai", False),
            freqai_model=default_config.get("freqai_model"),
            custom_params=params,
            status=StrategyStatus.STOPPED,
        )

        await self.db.create_strategy(strategy)

        await self.slack.send_strategy_started(name, pairs, port)

        return strategy_id

    async def update_strategy_config(
        self, strategy_id: str, config_updates: Dict[str, Any]
    ) -> bool:
        strategy = await self.db.get_strategy(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")

        config = self.config_parser.load_config(strategy["config_path"])
        config = self.config_parser.update_strategy_params(config, config_updates)

        STRATEGY_PARAM_KEYS = {
            "rsi_entry_threshold",
            "rsi_entry",
            "rsi_oversold",
            "rsi_overbought",
            "volume_factor",
            "volume_mult",
            "stoploss",
            "minimal_roi",
            "trailing_stop_positive",
            "trailing_stop_positive_offset",
            "max_open_trades",
            "stake_amount",
            "pairs_to_add",
            "pairs_to_remove",
            "take_profit_pct",
            "cooldown_candles",
            "breakout_period",
            "adx_threshold",
            "rsi_min",
            "rsi_max",
        }
        params_to_inject = {}
        for key, value in config_updates.items():
            if key in STRATEGY_PARAM_KEYS:
                params_to_inject[key] = value
        if params_to_inject:
            existing_params = config.get("strategy_params", {})
            existing_params.update(params_to_inject)
            config["strategy_params"] = existing_params

        if "pairs_to_add" in config_updates or "pairs_to_remove" in config_updates:
            current_pairs = config.get("exchange", {}).get("pair_whitelist", [])
            pairs_to_add = config_updates.get("pairs_to_add", [])
            pairs_to_remove = config_updates.get("pairs_to_remove", [])
            for pair in pairs_to_add:
                if pair not in current_pairs:
                    current_pairs.append(pair)
            for pair in pairs_to_remove:
                if pair in current_pairs:
                    current_pairs.remove(pair)
            config["exchange"]["pair_whitelist"] = current_pairs

        self.config_parser.save_config(strategy["config_path"], config)

        db_updates = {"updated_at": datetime.now()}
        if "max_open_trades" in config_updates:
            db_updates["max_open_trades"] = config_updates["max_open_trades"]
        if "stake_amount" in config_updates:
            db_updates["stake_amount"] = config_updates["stake_amount"]
        if "stoploss" in config_updates:
            db_updates["stoploss"] = config_updates["stoploss"]
        if "trailing_stop" in config_updates:
            db_updates["trailing_stop"] = 1 if config_updates["trailing_stop"] else 0

        await self.db.update_strategy(strategy_id, db_updates)

        if self.container_manager:
            try:
                container_status = await self.container_manager.get_container_status(
                    strategy_id
                )
                if container_status and container_status.get("status") == "running":
                    await self.container_manager.restart_container(strategy_id)
            except Exception as e:
                print(
                    f"Warning: Failed to restart container after config update for {strategy_id}: {e}"
                )

        return True

    async def start_strategy(self, strategy_id: str) -> Dict[str, Any]:
        strategy = await self.db.get_strategy(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")

        if not self.container_manager:
            raise ValueError("Container manager not available - Docker not accessible")

        config = self.config_parser.load_config(strategy["config_path"])

        port = strategy.get("docker_port")
        if not port:
            port = await self.db.get_next_port()
            await self.db.update_strategy(strategy_id, {"docker_port": port})

        container_id = await self.container_manager.create_container(
            strategy_id=strategy_id,
            config={
                "config_path": strategy["config_path"],
                "image": "freqtradeorg/freqtrade:stable",
            },
            port=port,
            strategy_file=strategy["strategy_file"],
        )

        await self.container_manager.start_container(strategy_id)

        await self.db.update_strategy(
            strategy_id,
            {
                "status": StrategyStatus.RUNNING.value,
                "container_id": container_id,
                "container_name": f"freqtrade-{strategy_id}",
            },
        )

        await self.slack.send_strategy_started(
            strategy["name"],
            json.loads(strategy["pairs"])
            if isinstance(strategy["pairs"], str)
            else strategy["pairs"],
            port,
        )

        if self.trade_monitor:
            await self.trade_monitor.start_monitoring(strategy_id)

        return {
            "strategy_id": strategy_id,
            "status": "running",
            "container_id": container_id,
            "port": port,
        }

    async def stop_strategy(self, strategy_id: str) -> Dict[str, Any]:
        strategy = await self.db.get_strategy(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")

        if not self.container_manager:
            raise ValueError("Container manager not available - Docker not accessible")

        await self.container_manager.stop_container(strategy_id)
        await self.container_manager.remove_container(strategy_id)

        await self.db.update_strategy(
            strategy_id,
            {
                "status": StrategyStatus.STOPPED.value,
                "container_id": None,
                "container_name": None,
            },
        )

        await self.slack.send_strategy_stopped(strategy["name"])

        if self.trade_monitor:
            await self.trade_monitor.stop_monitoring(strategy_id)

        return {"strategy_id": strategy_id, "status": "stopped"}

    async def get_strategy_status(self, strategy_id: str) -> Dict[str, Any]:
        strategy = await self.db.get_strategy(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")

        status = {"strategy": strategy, "container": None, "trades": [], "freqai": None}

        if self.container_manager:
            try:
                container_status = await self.container_manager.get_container_status(
                    strategy_id
                )
                status["container"] = container_status
            except Exception as e:
                print(f"Warning: Could not get container status: {e}")

        if strategy["use_freqai"]:
            freqai_info = self.freqai_adapter.get_latest_model_info(strategy_id)
            status["freqai"] = freqai_info

        return status

    async def get_all_strategies(self) -> List[Dict[str, Any]]:
        strategies = await self.db.get_strategies()

        enriched = []
        for strategy in strategies:
            if self.container_manager:
                try:
                    container = await self.container_manager.get_container_status(
                        strategy["id"]
                    )
                    strategy["container_status"] = container
                except Exception as e:
                    print(
                        f"Warning: Could not get container status for {strategy['id']}: {e}"
                    )
                    strategy["container_status"] = None
            else:
                strategy["container_status"] = None

            perf = await self._get_strategy_performance(strategy["id"])
            strategy["win_rate"] = perf.get("win_rate", 0)
            strategy["sharpe"] = perf.get("sharpe", 0)
            strategy["profit_pct"] = perf.get("profit_pct", 0)
            strategy["total_trades"] = perf.get("total_trades", 0)
            strategy["max_drawdown"] = perf.get("max_drawdown", 0)

            enriched.append(strategy)

        return enriched

    async def _get_strategy_performance(self, strategy_id: str) -> Dict[str, Any]:
        """Get performance metrics for a strategy from its Freqtrade trade DB."""
        import sqlite3
        from pathlib import Path

        perf = {
            "win_rate": 0,
            "sharpe": 0,
            "profit_pct": 0,
            "total_trades": 0,
            "max_drawdown": 0,
        }

        try:
            trade_db_path = Path(f"/user_data/{strategy_id}/tradesv3.dryrun.sqlite")
            if not trade_db_path.exists():
                trade_db_path = Path(f"/user_data/{strategy_id}/tradesv3.sqlite")

            if not trade_db_path.exists():
                return perf

            import aiosqlite

            async with aiosqlite.connect(str(trade_db_path)) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("""
                    SELECT
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN close_profit > 0 THEN 1 ELSE 0 END) as wins,
                        SUM(close_profit_abs) as total_profit,
                        AVG(close_profit) as avg_profit
                    FROM trades
                    WHERE is_open = 0
                """)
                row = await cursor.fetchone()

                if row and row["total_trades"] and row["total_trades"] > 0:
                    perf["total_trades"] = row["total_trades"]
                    perf["win_rate"] = (row["wins"] or 0) / row["total_trades"]
                    perf["profit_pct"] = row["total_profit"] or 0

                    profits_cursor = await db.execute(
                        "SELECT close_profit FROM trades WHERE is_open = 0 ORDER BY close_date DESC LIMIT 200"
                    )
                    profit_rows = await profits_cursor.fetchall()
                    profits = [
                        r["close_profit"]
                        for r in profit_rows
                        if r["close_profit"] is not None
                    ]

                    if len(profits) > 1:
                        avg_p = sum(profits) / len(profits)
                        std_p = (
                            sum((p - avg_p) ** 2 for p in profits) / len(profits)
                        ) ** 0.5
                        perf["sharpe"] = (
                            (avg_p / std_p * (365**0.5)) if std_p > 0 else 0
                        )

                        cumulative = []
                        running = 0
                        for p in profits:
                            running += p
                            cumulative.append(running)
                        peak = float("-inf")
                        max_dd = 0
                        for c in cumulative:
                            if c > peak:
                                peak = c
                            if peak != 0:
                                dd = (peak - c) / abs(peak)
                                if dd > max_dd:
                                    max_dd = dd
                        perf["max_drawdown"] = max_dd
        except Exception as e:
            print(f"Warning: Could not get performance for {strategy_id}: {e}")

        return perf

    async def run_backtest(
        self, strategy_id: str, timerange: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        strategy = await self.db.get_strategy(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")

        result = await self.backtest_runner.run_backtest(
            strategy=strategy["strategy_file"],
            config_path=strategy["config_path"],
            timerange=timerange,
            params=params,
        )

        if result.get("success"):
            await self.slack.send_backtest_complete(
                strategy_name=strategy["name"],
                profit_pct=result.get("profit_total_percent", 0),
                trades=result.get("total_trades", 0),
                win_rate=result.get("win_rate", 0),
                sharpe=result.get("sharpe", None),
            )

        return result

    async def get_portfolio_summary(self) -> Dict[str, Any]:
        return await get_portfolio_summary(self.db)

    async def get_templates(self) -> Dict[str, Any]:
        return self.templates

    async def delete_strategy(self, strategy_id: str) -> bool:
        strategy = await self.db.get_strategy(strategy_id)
        if not strategy:
            return False

        if strategy["status"] == "running":
            await self.stop_strategy(strategy_id)

        config_path = Path(strategy["config_path"])
        if config_path.exists():
            config_path.unlink()

        await self.db.delete_strategy(strategy_id)

        return True
