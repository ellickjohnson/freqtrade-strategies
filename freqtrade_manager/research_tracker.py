import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import sqlite3
from enum import Enum


class ResearchStatus(Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResearchType(Enum):
    HYPEROPT = "hyperopt"
    BACKTEST_COMPARISON = "backtest_comparison"
    PARAMETER_SENSITIVITY = "parameter_sensitivity"
    STRATEGY_DISCOVERY = "strategy_discovery"
    MARKET_REGIME = "market_regime"
    FEATURE_IMPORTANCE = "feature_importance"
    RISK_OPTIMIZATION = "risk_optimization"


@dataclass
class ResearchRun:
    research_id: str
    strategy_id: str
    strategy_name: str
    research_type: str
    hypothesis: str
    status: str
    start_time: str
    end_time: Optional[str]
    parameters_tested: Dict[str, Any]
    results: Dict[str, Any]
    best_params: Dict[str, Any]
    metrics: Dict[str, float]
    conclusion: str
    recommendations: List[str]
    improvement_pct: float
    epochs_completed: int
    total_epochs: int
    best_epoch: int
    current_best_score: float = 0.0
    gpu_hours_used: float = 0.0
    data_points_analyzed: int = 0


@dataclass
class ResearchSchedule:
    schedule_id: str
    research_type: str
    frequency: str
    next_run: str
    last_run: Optional[str]
    enabled: bool
    config: Dict[str, Any]


class ResearchTracker:
    def __init__(self, db_path: str = "/data/dashboard.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS research_runs (
                research_id TEXT PRIMARY KEY,
                strategy_id TEXT,
                strategy_name TEXT,
                research_type TEXT NOT NULL,
                hypothesis TEXT,
                status TEXT NOT NULL,
                start_time TEXT,
                end_time TEXT,
                parameters_tested TEXT,
                results TEXT,
                best_params TEXT,
                metrics TEXT,
                conclusion TEXT,
                recommendations TEXT,
                improvement_pct REAL,
                epochs_completed INTEGER,
                total_epochs INTEGER,
                best_epoch INTEGER,
                current_best_score REAL,
                gpu_hours_used REAL,
                data_points_analyzed INTEGER,
                applied INTEGER DEFAULT 0,
                applied_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS research_schedule (
                schedule_id TEXT PRIMARY KEY,
                research_type TEXT NOT NULL,
                frequency TEXT,
                next_run TEXT,
                last_run TEXT,
                enabled INTEGER DEFAULT 1,
                config TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS strategy_evolution (
                evolution_id TEXT PRIMARY KEY,
                strategy_id TEXT,
                generation INTEGER,
                parent_strategy_id TEXT,
                mutations_applied TEXT,
                fitness_score REAL,
                backtest_sharpe REAL,
                backtest_win_rate REAL,
                backtest_max_drawdown REAL,
                live_sharpe REAL,
                live_win_rate REAL,
                live_max_drawdown REAL,
                status TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        c.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_logs_strategy ON research_runs(strategy_id)
        """
        )

        # Migration: Add applied columns if they don't exist
        try:
            c.execute("ALTER TABLE research_runs ADD COLUMN applied INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            c.execute("ALTER TABLE research_runs ADD COLUMN applied_at TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        conn.commit()
        conn.close()

    def start_research(
        self,
        strategy_id: str,
        strategy_name: str,
        research_type: str,
        hypothesis: str,
        parameters_tested: Dict[str, Any],
        total_epochs: int,
    ) -> str:
        research_id = (
            f"res_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{strategy_id[:8]}"
        )

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute(
            """
            INSERT INTO research_runs (
                research_id, strategy_id, strategy_name, research_type, hypothesis,
                status, start_time, parameters_tested, total_epochs, epochs_completed,
                current_best_score
            ) VALUES (?, ?, ?, ?, ?, 'running', CURRENT_TIMESTAMP, ?, ?, 0, 0)
        """,
            (
                research_id,
                strategy_id,
                strategy_name,
                research_type,
                hypothesis,
                json.dumps(parameters_tested),
                total_epochs,
            ),
        )

        conn.commit()
        conn.close()

        return research_id

    def update_research_progress(
        self,
        research_id: str,
        epoch: int,
        current_score: float,
        best_score: float,
        best_params: Dict[str, Any],
    ):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute(
            """
            UPDATE research_runs 
            SET epochs_completed = ?, current_best_score = ?, best_params = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE research_id = ?
        """,
            (epoch, best_score, json.dumps(best_params), research_id),
        )

        conn.commit()
        conn.close()

    def complete_research(
        self,
        research_id: str,
        results: Dict[str, Any],
        best_params: Dict[str, Any],
        metrics: Dict[str, float],
        conclusion: str,
        recommendations: List[str],
        improvement_pct: float,
    ):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute(
            """
            UPDATE research_runs 
            SET status = 'completed', end_time = CURRENT_TIMESTAMP, results = ?,
                best_params = ?, metrics = ?, conclusion = ?, recommendations = ?,
                improvement_pct = ?, updated_at = CURRENT_TIMESTAMP
            WHERE research_id = ?
        """,
            (
                json.dumps(results),
                json.dumps(best_params),
                json.dumps(metrics),
                conclusion,
                json.dumps(recommendations),
                improvement_pct,
                research_id,
            ),
        )

        conn.commit()
        conn.close()

    def fail_research(self, research_id: str, error: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute(
            """
            UPDATE research_runs 
            SET status = 'failed', end_time = CURRENT_TIMESTAMP, conclusion = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE research_id = ?
        """,
            (f"Failed: {error}", research_id),
        )

        conn.commit()
        conn.close()

    def get_active_research(self) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute(
            """
            SELECT * FROM research_runs 
            WHERE status = 'running' 
            ORDER BY start_time DESC
        """
        )

        rows = c.fetchall()
        conn.close()

        return [self._parse_research_row(row) for row in rows]

    def get_research_history(
        self, strategy_id: str = None, research_type: str = None, limit: int = 50
    ) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        query = "SELECT * FROM research_runs WHERE 1=1"
        params = []

        if strategy_id:
            query += " AND strategy_id = ?"
            params.append(strategy_id)
        if research_type:
            query += " AND research_type = ?"
            params.append(research_type)

        query += " ORDER BY start_time DESC LIMIT ?"
        params.append(limit)

        c.execute(query, params)
        rows = c.fetchall()
        conn.close()

        return [self._parse_research_row(row) for row in rows]

    def _parse_research_row(self, row) -> Dict:
        result = dict(row)
        result["parameters_tested"] = json.loads(result["parameters_tested"] or "{}")
        result["results"] = json.loads(result["results"] or "{}")
        result["best_params"] = json.loads(result["best_params"] or "{}")
        result["metrics"] = json.loads(result["metrics"] or "{}")
        result["recommendations"] = json.loads(result["recommendations"] or "[]")
        result["applied"] = result.get("applied", 0) == 1
        result["applied_at"] = result.get("applied_at")
        return result

    def get_research_summary(self, days: int = 30) -> Dict:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute(
            """
            SELECT 
                COUNT(*) as total_runs,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                AVG(improvement_pct) as avg_improvement,
                MAX(improvement_pct) as max_improvement,
                SUM(gpu_hours_used) as total_gpu_hours,
                SUM(data_points_analyzed) as total_data_points
            FROM research_runs
            WHERE start_time >= datetime('now', ?)
        """,
            (f"-{days} days",),
        )

        row = c.fetchone()
        conn.close()

        if row:
            return {
                "total_runs": row[0] or 0,
                "completed": row[1] or 0,
                "running": row[2] or 0,
                "failed": row[3] or 0,
                "success_rate": (row[1] / row[0]) if row[0] > 0 else 0,
                "avg_improvement": row[4] or 0.0,
                "max_improvement": row[5] or 0.0,
                "total_gpu_hours": row[6] or 0.0,
                "total_data_points": row[7] or 0,
            }
        return {}

    def get_recent_discoveries(self, limit: int = 10) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute(
            """
            SELECT * FROM research_runs 
            WHERE status = 'completed' AND improvement_pct > 0
            ORDER BY end_time DESC 
            LIMIT ?
        """,
            (limit,),
        )

        rows = c.fetchall()
        conn.close()

        discoveries = []
        for row in rows:
            result = self._parse_research_row(row)
            discoveries.append(
                {
                    "research_id": result["research_id"],
                    "strategy_name": result["strategy_name"],
                    "research_type": result["research_type"],
                    "hypothesis": result["hypothesis"],
                    "improvement": result["improvement_pct"],
                    "best_params": result["best_params"],
                    "conclusion": result["conclusion"],
                    "completed_at": result["end_time"],
                    "recommendations": result["recommendations"],
                    "applied": result.get("applied", False),
                    "applied_at": result.get("applied_at"),
                }
            )

        return discoveries

    def should_apply_findings(self, research_id: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute(
            """
            SELECT improvement_pct, metrics FROM research_runs 
            WHERE research_id = ? AND status = 'completed'
        """,
            (research_id,),
        )

        row = c.fetchone()
        conn.close()

        if not row:
            return False

        improvement = row[0]
        metrics = json.loads(row[1] or "{}")

        if improvement >= 5.0:
            return True

        if metrics.get("sharpe_ratio", 0) > 1.5:
            return True

        if metrics.get("win_rate", 0) > 0.55:
            return True

        return False

    def is_applied(self, research_id: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute(
            "SELECT applied FROM research_runs WHERE research_id = ?",
            (research_id,),
        )

        row = c.fetchone()
        conn.close()

        return row[0] == 1 if row else False

    def mark_applied(self, research_id: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute(
            """
            UPDATE research_runs 
            SET applied = 1, applied_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE research_id = ?
        """,
            (research_id,),
        )

        conn.commit()
        conn.close()

    def get_applicable_research(self, strategy_id: str = None) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        if strategy_id:
            c.execute(
                """
                SELECT * FROM research_runs 
                WHERE strategy_id = ? AND status = 'completed' AND applied = 0
                ORDER BY improvement_pct DESC
            """,
                (strategy_id,),
            )
        else:
            c.execute(
                """
                SELECT * FROM research_runs 
                WHERE status = 'completed' AND applied = 0
                ORDER BY improvement_pct DESC
            """
            )

        rows = c.fetchall()
        conn.close()

        return [self._parse_research_row(row) for row in rows]

    def schedule_research(
        self, research_type: str, frequency: str, config: Dict[str, Any]
    ) -> str:
        import uuid

        schedule_id = str(uuid.uuid4())

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        next_run = self._calculate_next_run(frequency)

        c.execute(
            """
            INSERT INTO research_schedule (
                schedule_id, research_type, frequency, next_run, config
            ) VALUES (?, ?, ?, ?, ?)
        """,
            (schedule_id, research_type, frequency, next_run, json.dumps(config)),
        )

        conn.commit()
        conn.close()

        return schedule_id

    def _calculate_next_run(self, frequency: str) -> str:
        from datetime import timedelta

        now = datetime.utcnow()

        if frequency == "hourly":
            next_run = now + timedelta(hours=1)
        elif frequency == "daily":
            next_run = now + timedelta(days=1)
        elif frequency == "weekly":
            next_run = now + timedelta(weeks=1)
        else:
            next_run = now + timedelta(days=1)

        return next_run.isoformat()

    def get_scheduled_research(self) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute(
            """
            SELECT * FROM research_schedule WHERE enabled = 1
        """
        )

        rows = c.fetchall()
        conn.close()

        results = []
        for row in rows:
            result = dict(row)
            result["config"] = json.loads(result["config"] or "{}")
            results.append(result)

        return results

    def log_discovery(
        self,
        strategy_id: str,
        discovery_type: str,
        finding: str,
        evidence: Dict[str, Any],
        confidence: float,
    ):
        from agent_logger import AgentLogger, LogCategory, LogLevel

        logger = AgentLogger(self.db_path)
        logger.log(
            strategy_id=strategy_id,
            category=LogCategory.RESEARCH,
            level=LogLevel.INFO,
            title=f"Discovery: {discovery_type}",
            message=finding,
            reasoning=json.dumps(evidence),
            data=evidence,
            impact="high" if confidence > 0.8 else "medium",
            confidence=confidence,
        )
