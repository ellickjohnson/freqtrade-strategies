import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import shutil


class ConfigParser:
    def __init__(
        self, configs_dir: str = "/configs", user_data_dir: str = "/user_data"
    ):
        self.configs_dir = Path(configs_dir)
        self.user_data_dir = Path(user_data_dir)

    def load_config(self, config_path: str) -> Dict[str, Any]:
        path = Path(config_path)
        if not path.exists():
            path = self.configs_dir / config_path

        with open(path, "r") as f:
            return json.load(f)

    def save_config(self, config_path: str, config: Dict[str, Any]) -> bool:
        path = Path(config_path)
        if not path.is_absolute():
            path = self.configs_dir / config_path

        try:
            backup_path = path.with_suffix(
                f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            if path.exists():
                shutil.copy(path, backup_path)

            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False

    def update_strategy_params(
        self, config: Dict[str, Any], params: Dict[str, Any]
    ) -> Dict[str, Any]:
        config["stoploss"] = params.get("stoploss", config.get("stoploss", -0.10))
        config["max_open_trades"] = params.get(
            "max_open_trades", config.get("max_open_trades", 3)
        )
        config["stake_amount"] = params.get(
            "stake_amount", config.get("stake_amount", 100)
        )

        if "trailing_stop" in params:
            config["trailing_stop"] = params["trailing_stop"]
            if params.get("trailing_stop_positive"):
                config["trailing_stop_positive"] = params["trailing_stop_positive"]
            if params.get("trailing_stop_positive_offset"):
                config["trailing_stop_positive_offset"] = params[
                    "trailing_stop_positive_offset"
                ]

        if params.get("use_freqai"):
            config["freqai"] = {
                "enabled": True,
                "purge_old_models": True,
                "save_metadata": True,
                "identifier": params.get("freqai_model", "lightgbm"),
                "train_period_days": 90,
                "backtest_period_days": 7,
                "feature_parameters": {
                    "feature_buffers": {
                        "rsi": {"lookback": 14},
                        "volume": {"lookback": 20},
                        "atr": {"lookback": 14},
                    }
                },
            }

        strategy_params = {
            k: v
            for k, v in params.items()
            if k
            not in [
                "stoploss",
                "max_open_trades",
                "stake_amount",
                "trailing_stop",
                "use_freqai",
                "freqai_model",
            ]
        }

        if strategy_params:
            if "strategy_params" not in config:
                config["strategy_params"] = {}
            config["strategy_params"].update(strategy_params)

        return config

    def create_config(
        self,
        strategy_file: str,
        exchange: str,
        pairs: List[str],
        timeframe: str,
        stake_amount: float,
        max_open_trades: int,
        dry_run: bool = True,
        port: int = 7070,
        custom_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        config = {
            "max_open_trades": max_open_trades,
            "stake_currency": "USDT",
            "stake_amount": stake_amount,
            "tradable_balance_ratio": 0.99,
            "fiat_display_currency": "USD",
            "dry_run": dry_run,
            "dry_run_wallet": 1000,
            "cancel_open_orders_on_exit": False,
            "unfilledtimeout": {"entry": 10, "exit": 10, "exit_timeout_count": 12},
            "entry_pricing": {
                "price_side": "same",
                "use_order_book": True,
                "order_book_top": 1,
                "price_last_balance": 0.0,
                "check_depth_of_market": {
                    "asks_orderbook_min": 1,
                    "bids_orderbook_max": 1,
                },
            },
            "exit_pricing": {
                "price_side": "same",
                "use_order_book": True,
                "order_book_top": 1,
            },
            "exchange": {
                "name": exchange,
                "key": "",
                "secret": "",
                "ccxt_config": {},
                "ccxt_async_config": {},
                "pair_whitelist": pairs,
                "pair_blacklist": [],
            },
            "pairlists": [{"method": "StaticPairList"}],
            "telegram": {"enabled": False, "token": "", "chat_id": ""},
            "api_server": {
                "enabled": True,
                "listen_ip_address": "0.0.0.0",
                "listen_port": port,
                "verbosity": "error",
                "enable_openapi": True,
                "jwt_secret_key": "somethingrandom",
                "ws_token": "somethingrandom",
                "CORS_origins": [],
                "username": "freqtrader",
                "password": "freqtrader",
            },
            "bot_name": f"freqtrade_{strategy_file.lower()}",
            "strategy": strategy_file,
            "db_url": f"sqlite:///user_data/tradesv3.dryrun.sqlite",
            "user_data_dir": "user_data",
            "timeframe": timeframe,
            "stoploss": -0.10,
            "trailing_stop": False,
            "trailing_stop_positive": 0.01,
            "trailing_stop_positive_offset": 0.02,
            "trailing_only_offset_is_reached": False,
            "initial_state": "running",
            "force_entry_enable": False,
            "internals": {"process_only_new_candles": False},
        }

        if custom_params:
            config = self.update_strategy_params(config, custom_params)

        return config

    def detect_existing_configs(self) -> List[Dict[str, Any]]:
        configs = []

        for config_file in self.configs_dir.glob("config*.json"):
            try:
                config = self.load_config(config_file)

                strategy_name = config.get("strategy", "Unknown")
                pairs = config.get("exchange", {}).get("pair_whitelist", [])
                timeframe = config.get("timeframe", "15m")
                exchange = config.get("exchange", {}).get("name", "kraken")
                stake_amount = config.get("stake_amount", 100)
                max_open_trades = config.get("max_open_trades", 3)

                port = config.get("api_server", {}).get("listen_port", 7070)

                configs.append(
                    {
                        "config_path": str(config_file),
                        "strategy_file": strategy_name,
                        "pairs": pairs,
                        "timeframe": timeframe,
                        "exchange": exchange,
                        "stake_amount": stake_amount,
                        "max_open_trades": max_open_trades,
                        "port": port,
                        "dry_run": config.get("dry_run", True),
                        "use_freqai": "freqai" in config,
                        "name": f"{strategy_name} ({config_file.stem})",
                    }
                )
            except Exception as e:
                print(f"Error parsing {config_file}: {e}")
                continue

        return configs

    def get_strategy_params(self, strategy_file: str) -> Dict[str, Any]:
        strategies_dir = Path("/strategies")
        strategy_path = strategies_dir / f"{strategy_file}.py"

        if not strategy_path.exists():
            return {}

        params = {}

        try:
            with open(strategy_path, "r") as f:
                content = f.read()

            import re

            rsi_match = re.search(r"rsi.*?(\d+)", content, re.IGNORECASE)
            if rsi_match:
                params["rsi_period"] = int(rsi_match.group(1))

            ema_match = re.search(r"EMA.*?(\d+)", content)
            if ema_match:
                params["ema_period"] = int(ema_match.group(1))

            stoploss_match = re.search(r"stoploss\s*=\s*(-?\d+\.?\d*)", content)
            if stoploss_match:
                params["stoploss"] = float(stoploss_match.group(1))

        except Exception as e:
            print(f"Error parsing strategy file: {e}")

        return params
