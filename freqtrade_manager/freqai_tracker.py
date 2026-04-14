import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import sqlite3


@dataclass
class FreqAIModelStatus:
    model_id: str
    strategy_id: str
    model_type: str
    version: str
    training_start: str
    training_end: str
    train_period_days: int
    backtest_period_days: int
    status: str
    accuracy: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1_score: Optional[float] = None
    profit_factor: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    win_rate: Optional[float] = None
    avg_trade_duration: Optional[float] = None
    total_trades: Optional[int] = None
    features_importance: Dict[str, float] = None
    hyperparameters: Dict[str, Any] = None
    last_prediction: Optional[float] = None
    prediction_confidence: Optional[float] = None
    prediction_time: Optional[str] = None
    model_size_mb: Optional[float] = None
    inference_time_ms: Optional[float] = None
    retraining_due: Optional[str] = None
    data_points_used: Optional[int] = None


@dataclass
class FreqAITrainingProgress:
    training_id: str
    strategy_id: str
    model_type: str
    start_time: str
    current_epoch: int
    total_epochs: int
    current_loss: float
    best_loss: float
    validation_accuracy: float
    estimated_completion: str
    status: str
    gpu_utilization: Optional[float] = None
    memory_usage_mb: Optional[float] = None


@dataclass
class FreqAIPrediction:
    prediction_id: str
    strategy_id: str
    model_id: str
    timestamp: str
    pair: str
    timeframe: str
    prediction: float
    confidence: float
    direction: str
    features_used: Dict[str, float]
    feature_importance: Dict[str, float]
    actual_outcome: Optional[float] = None
    actual_direction: Optional[str] = None
    profit_loss: Optional[float] = None
    trade_id: Optional[str] = None


class FreqAITracker:
    def __init__(self, db_path: str = "/data/dashboard.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS freqai_models (
                model_id TEXT PRIMARY KEY,
                strategy_id TEXT NOT NULL,
                model_type TEXT NOT NULL,
                version TEXT,
                training_start TEXT,
                training_end TEXT,
                train_period_days INTEGER,
                backtest_period_days INTEGER,
                status TEXT,
                accuracy REAL,
                precision REAL,
                recall REAL,
                f1_score REAL,
                profit_factor REAL,
                sharpe_ratio REAL,
                max_drawdown REAL,
                win_rate REAL,
                avg_trade_duration REAL,
                total_trades INTEGER,
                features_importance TEXT,
                hyperparameters TEXT,
                last_prediction REAL,
                prediction_confidence REAL,
                prediction_time TEXT,
                model_size_mb REAL,
                inference_time_ms REAL,
                retraining_due TEXT,
                data_points_used INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS freqai_training_progress (
                training_id TEXT PRIMARY KEY,
                strategy_id TEXT NOT NULL,
                model_type TEXT NOT NULL,
                start_time TEXT,
                current_epoch INTEGER,
                total_epochs INTEGER,
                current_loss REAL,
                best_loss REAL,
                validation_accuracy REAL,
                estimated_completion TEXT,
                status TEXT,
                gpu_utilization REAL,
                memory_usage_mb REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS freqai_predictions (
                prediction_id TEXT PRIMARY KEY,
                strategy_id TEXT NOT NULL,
                model_id TEXT,
                timestamp TEXT,
                pair TEXT,
                timeframe TEXT,
                prediction REAL,
                confidence REAL,
                direction TEXT,
                features_used TEXT,
                feature_importance TEXT,
                actual_outcome REAL,
                actual_direction TEXT,
                profit_loss REAL,
                trade_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        c.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_freqai_models_strategy ON freqai_models(strategy_id)
        """
        )
        c.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_freqai_training_strategy ON freqai_training_progress(strategy_id)
        """
        )
        c.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_freqai_predictions_strategy ON freqai_predictions(strategy_id)
        """
        )
        c.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_freqai_predictions_timestamp ON freqai_predictions(timestamp)
        """
        )

        conn.commit()
        conn.close()

    def save_model_status(self, status: FreqAIModelStatus) -> str:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute(
            """
            INSERT OR REPLACE INTO freqai_models (
                model_id, strategy_id, model_type, version, training_start, training_end,
                train_period_days, backtest_period_days, status, accuracy, precision,
                recall, f1_score, profit_factor, sharpe_ratio, max_drawdown, win_rate,
                avg_trade_duration, total_trades, features_importance, hyperparameters,
                last_prediction, prediction_confidence, prediction_time, model_size_mb,
                inference_time_ms, retraining_due, data_points_used, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
            (
                status.model_id,
                status.strategy_id,
                status.model_type,
                status.version,
                status.training_start,
                status.training_end,
                status.train_period_days,
                status.backtest_period_days,
                status.status,
                status.accuracy,
                status.precision,
                status.recall,
                status.f1_score,
                status.profit_factor,
                status.sharpe_ratio,
                status.max_drawdown,
                status.win_rate,
                status.avg_trade_duration,
                status.total_trades,
                json.dumps(status.features_importance or {}),
                json.dumps(status.hyperparameters or {}),
                status.last_prediction,
                status.prediction_confidence,
                status.prediction_time,
                status.model_size_mb,
                status.inference_time_ms,
                status.retraining_due,
                status.data_points_used,
            ),
        )

        conn.commit()
        conn.close()
        return status.model_id

    def save_training_progress(self, progress: FreqAITrainingProgress) -> str:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute(
            """
            INSERT OR REPLACE INTO freqai_training_progress (
                training_id, strategy_id, model_type, start_time, current_epoch,
                total_epochs, current_loss, best_loss, validation_accuracy,
                estimated_completion, status, gpu_utilization, memory_usage_mb
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                progress.training_id,
                progress.strategy_id,
                progress.model_type,
                progress.start_time,
                progress.current_epoch,
                progress.total_epochs,
                progress.current_loss,
                progress.best_loss,
                progress.validation_accuracy,
                progress.estimated_completion,
                progress.status,
                progress.gpu_utilization,
                progress.memory_usage_mb,
            ),
        )

        conn.commit()
        conn.close()
        return progress.training_id

    def save_prediction(self, prediction: FreqAIPrediction) -> str:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute(
            """
            INSERT INTO freqai_predictions (
                prediction_id, strategy_id, model_id, timestamp, pair, timeframe,
                prediction, confidence, direction, features_used, feature_importance,
                actual_outcome, actual_direction, profit_loss, trade_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                prediction.prediction_id,
                prediction.strategy_id,
                prediction.model_id,
                prediction.timestamp,
                prediction.pair,
                prediction.timeframe,
                prediction.prediction,
                prediction.confidence,
                prediction.direction,
                json.dumps(prediction.features_used),
                json.dumps(prediction.feature_importance),
                prediction.actual_outcome,
                prediction.actual_direction,
                prediction.profit_loss,
                prediction.trade_id,
            ),
        )

        conn.commit()
        conn.close()
        return prediction.prediction_id

    def get_model_status(self, strategy_id: str) -> Optional[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute(
            """
            SELECT * FROM freqai_models 
            WHERE strategy_id = ? 
            ORDER BY updated_at DESC 
            LIMIT 1
        """,
            (strategy_id,),
        )

        row = c.fetchone()
        conn.close()

        if row:
            result = dict(row)
            result["features_importance"] = json.loads(
                result["features_importance"] or "{}"
            )
            result["hyperparameters"] = json.loads(result["hyperparameters"] or "{}")
            return result
        return None

    def get_training_progress(self, strategy_id: str) -> Optional[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute(
            """
            SELECT * FROM freqai_training_progress 
            WHERE strategy_id = ? AND status != 'completed'
            ORDER BY start_time DESC 
            LIMIT 1
        """,
            (strategy_id,),
        )

        row = c.fetchone()
        conn.close()

        return dict(row) if row else None

    def get_predictions(
        self, strategy_id: str, limit: int = 100, include_outcomes: bool = False
    ) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        if include_outcomes:
            c.execute(
                """
                SELECT * FROM freqai_predictions 
                WHERE strategy_id = ? AND actual_outcome IS NOT NULL
                ORDER BY timestamp DESC 
                LIMIT ?
            """,
                (strategy_id, limit),
            )
        else:
            c.execute(
                """
                SELECT * FROM freqai_predictions 
                WHERE strategy_id = ?
                ORDER BY timestamp DESC 
                LIMIT ?
            """,
                (strategy_id, limit),
            )

        rows = c.fetchall()
        conn.close()

        results = []
        for row in rows:
            r = dict(row)
            r["features_used"] = json.loads(r["features_used"] or "{}")
            r["feature_importance"] = json.loads(r["feature_importance"] or "{}")
            results.append(r)

        return results

    def get_model_performance_history(self, strategy_id: str) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute(
            """
            SELECT model_id, version, accuracy, sharpe_ratio, win_rate, 
                   profit_factor, max_drawdown, training_end, total_trades
            FROM freqai_models 
            WHERE strategy_id = ?
            ORDER BY training_end DESC
        """,
            (strategy_id,),
        )

        rows = c.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_feature_importance_evolution(self, strategy_id: str) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute(
            """
            SELECT model_id, version, features_importance, training_end
            FROM freqai_models 
            WHERE strategy_id = ?
            ORDER BY training_end DESC
            LIMIT 10
        """,
            (strategy_id,),
        )

        rows = c.fetchall()
        conn.close()

        results = []
        for row in rows:
            results.append(
                {
                    "model_id": row["model_id"],
                    "version": row["version"],
                    "features_importance": json.loads(
                        row["features_importance"] or "{}"
                    ),
                    "training_end": row["training_end"],
                }
            )

        return results

    def update_prediction_outcome(
        self,
        strategy_id: str,
        prediction_id: str,
        actual_outcome: float,
        actual_direction: str,
        profit_loss: float,
        trade_id: str = None,
    ):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute(
            """
            UPDATE freqai_predictions 
            SET actual_outcome = ?, actual_direction = ?, profit_loss = ?, trade_id = ?
            WHERE prediction_id = ? AND strategy_id = ?
        """,
            (
                actual_outcome,
                actual_direction,
                profit_loss,
                trade_id,
                prediction_id,
                strategy_id,
            ),
        )

        conn.commit()
        conn.close()

    def get_prediction_accuracy_stats(self, strategy_id: str) -> Dict:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute(
            """
            SELECT 
                COUNT(*) as total_predictions,
                SUM(CASE WHEN actual_direction = direction THEN 1 ELSE 0 END) as correct_predictions,
                AVG(profit_loss) as avg_profit,
                AVG(confidence) as avg_confidence
            FROM freqai_predictions 
            WHERE strategy_id = ? AND actual_outcome IS NOT NULL
        """,
            (strategy_id,),
        )

        row = c.fetchone()
        conn.close()

        if row and row[0] > 0:
            return {
                "total_predictions": row[0],
                "correct_predictions": row[1],
                "accuracy": row[1] / row[0] if row[0] > 0 else 0,
                "avg_profit": row[2],
                "avg_confidence": row[3],
            }
        return {
            "total_predictions": 0,
            "correct_predictions": 0,
            "accuracy": 0,
            "avg_profit": 0,
            "avg_confidence": 0,
        }
