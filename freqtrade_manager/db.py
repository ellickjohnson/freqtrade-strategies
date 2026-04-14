import asyncio
import aiosqlite
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime
import json
from models import StrategyConfig, StrategyStatus, BacktestResult, FreqAIInsights

DATABASE_PATH = "/data/dashboard.db"


async def init_database(db_path: str = DATABASE_PATH):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS strategies (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                strategy_type TEXT,
                description TEXT,
                strategy_file TEXT NOT NULL,
                config_path TEXT NOT NULL,
                exchange TEXT DEFAULT 'kraken',
                pairs TEXT,
                timeframe TEXT DEFAULT '15m',
                stake_amount REAL DEFAULT 100.0,
                max_open_trades INTEGER DEFAULT 3,
                dry_run INTEGER DEFAULT 1,
                stoploss REAL DEFAULT -0.10,
                trailing_stop INTEGER DEFAULT 0,
                use_freqai INTEGER DEFAULT 0,
                freqai_model TEXT,
                docker_port INTEGER,
                container_id TEXT,
                container_name TEXT,
                enabled INTEGER DEFAULT 1,
                status TEXT DEFAULT 'stopped',
                custom_params TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS backtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT,
                run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                time_range TEXT,
                config_snapshot TEXT,
                results TEXT,
                metrics TEXT,
                FOREIGN KEY (strategy_id) REFERENCES strategies(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS freqai_training (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT,
                trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                model_path TEXT,
                model_type TEXT,
                accuracy REAL,
                precision_val REAL,
                recall REAL,
                feature_importance TEXT,
                regime TEXT,
                FOREIGN KEY (strategy_id) REFERENCES strategies(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS dashboard_config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        await db.execute("""
            INSERT OR IGNORE INTO dashboard_config (key, value) 
            VALUES ('next_port', '7070')
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS strategy_templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                strategy_type TEXT NOT NULL,
                strategy_file TEXT NOT NULL,
                default_config TEXT,
                description TEXT,
                params TEXT
            )
        """)

        await db.commit()


class Database:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path

    async def get_strategies(self) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM strategies ORDER BY created_at DESC"
            )
            rows = await cursor.fetchall()
            strategies = []
            for row in rows:
                strategy = dict(row)
                if strategy.get("pairs"):
                    try:
                        strategy["pairs"] = json.loads(strategy["pairs"])
                    except (json.JSONDecodeError, TypeError):
                        strategy["pairs"] = []
                else:
                    strategy["pairs"] = []
                if strategy.get("custom_params"):
                    try:
                        strategy["custom_params"] = json.loads(
                            strategy["custom_params"]
                        )
                    except (json.JSONDecodeError, TypeError):
                        strategy["custom_params"] = {}
                else:
                    strategy["custom_params"] = {}
                strategies.append(strategy)
            return strategies

    async def get_strategy(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM strategies WHERE id = ?", (strategy_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_strategy(self, strategy: StrategyConfig) -> str:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO strategies (
                    id, name, strategy_type, description, strategy_file, config_path,
                    exchange, pairs, timeframe, stake_amount, max_open_trades,
                    dry_run, stoploss, trailing_stop, use_freqai, freqai_model,
                    docker_port, container_id, container_name, enabled, status,
                    custom_params
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    strategy.id,
                    strategy.name,
                    strategy.strategy_type.value,
                    strategy.description,
                    strategy.strategy_file,
                    strategy.config_path,
                    strategy.exchange,
                    json.dumps(strategy.pairs),
                    strategy.timeframe,
                    strategy.stake_amount,
                    strategy.max_open_trades,
                    1 if strategy.dry_run else 0,
                    strategy.stoploss,
                    1 if strategy.trailing_stop else 0,
                    1 if strategy.use_freqai else 0,
                    strategy.freqai_model,
                    strategy.docker_port,
                    strategy.container_id,
                    strategy.container_name,
                    1 if strategy.enabled else 0,
                    strategy.status.value,
                    json.dumps(strategy.custom_params),
                ),
            )
            await db.commit()
            return strategy.id

    async def update_strategy(self, strategy_id: str, updates: Dict[str, Any]) -> bool:
        updates["updated_at"] = datetime.now().isoformat()
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = []
        for v in updates.values():
            if isinstance(v, (dict, list)):
                values.append(json.dumps(v))
            else:
                values.append(v)
        values.append(strategy_id)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f"UPDATE strategies SET {set_clause} WHERE id = ?", values
            )
            await db.commit()
            return cursor.rowcount > 0

    async def delete_strategy(self, strategy_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM strategies WHERE id = ?", (strategy_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_next_port(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT value FROM dashboard_config WHERE key = 'next_port'"
            )
            row = await cursor.fetchone()
            current_port = int(row[0]) if row else 7070
            next_port = current_port + 1

            await db.execute(
                "UPDATE dashboard_config SET value = ? WHERE key = 'next_port'",
                (str(next_port),),
            )
            await db.commit()
            return current_port

    async def save_backtest_result(self, result: BacktestResult) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO backtest_results (
                    strategy_id, run_at, time_range, config_snapshot, results, metrics
                ) VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    result.strategy_id,
                    result.run_at,
                    result.time_range,
                    json.dumps(result.config_snapshot),
                    json.dumps(result.results),
                    json.dumps(result.metrics),
                ),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_backtest_results(
        self, strategy_id: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if strategy_id:
                cursor = await db.execute(
                    """
                    SELECT * FROM backtest_results 
                    WHERE strategy_id = ?
                    ORDER BY run_at DESC LIMIT ?
                """,
                    (strategy_id, limit),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT * FROM backtest_results 
                    ORDER BY run_at DESC LIMIT ?
                """,
                    (limit,),
                )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def save_freqai_training(self, insights: FreqAIInsights) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO freqai_training (
                    strategy_id, trained_at, model_type, accuracy,
                    precision_val, recall, feature_importance, regime
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    insights.strategy_id,
                    insights.trained_at,
                    insights.model_type,
                    insights.accuracy,
                    insights.precision,
                    insights.recall,
                    json.dumps(insights.feature_importance),
                    insights.regime.value,
                ),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_freqai_training_history(
        self, strategy_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM freqai_training 
                WHERE strategy_id = ?
                ORDER BY trained_at DESC LIMIT ?
            """,
                (strategy_id, limit),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def save_template(
        self, template_id: str, template_data: Dict[str, Any]
    ) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO strategy_templates (
                    id, name, strategy_type, strategy_file, default_config, description, params
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    template_id,
                    template_data["name"],
                    template_data["strategy_type"],
                    template_data["strategy_file"],
                    json.dumps(template_data["default_config"]),
                    template_data.get("description"),
                    json.dumps(template_data.get("params", [])),
                ),
            )
            await db.commit()
            return True

    async def get_templates(self) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM strategy_templates")
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_portfolio_summary(db: Database) -> Dict[str, Any]:
    strategies = await db.get_strategies()

    total_pnl = 0.0
    total_trades = 0
    winning_trades = 0
    open_trades = 0
    strategies_active = 0

    for strategy in strategies:
        if strategy["status"] == "running":
            strategies_active += 1

        user_data_path = Path(f"/user_data/{strategy['id']}")
        db_path = user_data_path / "tradesv3.dryrun.sqlite"

        if db_path.exists():
            async with aiosqlite.connect(str(db_path)) as trade_db:
                trade_db.row_factory = aiosqlite.Row

                cursor = await trade_db.execute("""
                    SELECT 
                        SUM(close_profit_abs) as total_pnl,
                        COUNT(*) as total,
                        SUM(CASE WHEN close_profit_abs > 0 THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN is_open = 1 THEN 1 ELSE 0 END) as open_count
                    FROM trades
                """)
                row = await cursor.fetchone()

                if row:
                    total_pnl += row["total_pnl"] or 0
                    total_trades += row["total"] or 0
                    winning_trades += row["wins"] or 0
                    open_trades += row["open_count"] or 0

    return {
        "total_pnl": total_pnl,
        "total_pnl_percent": 0.0,
        "daily_pnl": 0.0,
        "weekly_pnl": 0.0,
        "monthly_pnl": 0.0,
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": total_trades - winning_trades,
        "win_rate": winning_trades / total_trades if total_trades > 0 else 0,
        "open_trades": open_trades,
        "strategies_active": strategies_active,
        "strategies_stopped": len(strategies) - strategies_active,
        "last_updated": datetime.now().isoformat(),
    }
