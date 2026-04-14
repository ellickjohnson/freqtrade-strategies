import json
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum
import sqlite3


class LogLevel(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LogCategory(Enum):
    STRATEGY_ANALYSIS = "strategy_analysis"
    TRADE_SIGNAL = "trade_signal"
    RISK_MANAGEMENT = "risk_management"
    FREQAI_PREDICTION = "freqai_prediction"
    MARKET_ANALYSIS = "market_analysis"
    PARAMETER_UPDATE = "parameter_update"
    RESEARCH = "research"
    BACKTEST = "backtest"
    SYSTEM = "system"


@dataclass
class AgentLog:
    timestamp: str
    strategy_id: str
    strategy_name: str
    category: str
    level: str
    title: str
    message: str
    reasoning: str
    data: Dict[str, Any]
    impact: str
    confidence: Optional[float] = None


class AgentLogger:
    def __init__(self, db_path: str = "/data/dashboard.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                strategy_name TEXT,
                category TEXT NOT NULL,
                level TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT,
                reasoning TEXT,
                data TEXT,
                impact TEXT,
                confidence REAL
            )
        """
        )
        c.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_logs_strategy ON agent_logs(strategy_id)
        """
        )
        c.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON agent_logs(timestamp)
        """
        )
        conn.commit()
        conn.close()

    def log(
        self,
        strategy_id: str,
        category: LogCategory,
        level: LogLevel,
        title: str,
        message: str,
        reasoning: str,
        data: Dict[str, Any] = None,
        impact: str = "none",
        confidence: float = None,
        strategy_name: str = None,
    ) -> AgentLog:
        entry = AgentLog(
            timestamp=datetime.utcnow().isoformat(),
            strategy_id=strategy_id,
            strategy_name=strategy_name or strategy_id[:8],
            category=category.value,
            level=level.value,
            title=title,
            message=message,
            reasoning=reasoning,
            data=data or {},
            impact=impact,
            confidence=confidence,
        )

        self._save_log(entry)
        return entry

    def _save_log(self, entry: AgentLog):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO agent_logs (
                timestamp, strategy_id, strategy_name, category, level,
                title, message, reasoning, data, impact, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                entry.timestamp,
                entry.strategy_id,
                entry.strategy_name,
                entry.category,
                entry.level,
                entry.title,
                entry.message,
                entry.reasoning,
                json.dumps(entry.data),
                entry.impact,
                entry.confidence,
            ),
        )
        conn.commit()
        conn.close()

    def get_logs(
        self,
        strategy_id: str = None,
        category: str = None,
        level: str = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        query = "SELECT * FROM agent_logs WHERE 1=1"
        params = []

        if strategy_id:
            query += " AND strategy_id = ?"
            params.append(strategy_id)
        if category:
            query += " AND category = ?"
            params.append(category)
        if level:
            query += " AND level = ?"
            params.append(level)

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        c.execute(query, params)
        rows = c.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_recent_reasoning(self, strategy_id: str, hours: int = 24) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute(
            """
            SELECT * FROM agent_logs
            WHERE strategy_id = ?
            AND timestamp >= datetime('now', ?)
            AND category IN ('strategy_analysis', 'trade_signal', 'freqai_prediction')
            ORDER BY timestamp DESC
            LIMIT 50
        """,
            (strategy_id, f"-{hours} hours"),
        )

        rows = c.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def log_strategy_analysis(
        self,
        strategy_id: str,
        strategy_name: str,
        analysis_type: str,
        findings: Dict[str, Any],
        recommendation: str,
    ):
        return self.log(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            category=LogCategory.STRATEGY_ANALYSIS,
            level=LogLevel.INFO,
            title=f"Strategy Analysis: {analysis_type}",
            message=f"Analyzed {analysis_type} for {strategy_name}",
            reasoning=recommendation,
            data=findings,
            impact="medium",
        )

    def log_trade_signal(
        self,
        strategy_id: str,
        strategy_name: str,
        signal_type: str,
        pair: str,
        price: float,
        indicators: Dict[str, Any],
        reasoning_steps: List[str],
        confidence: float,
    ):
        return self.log(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            category=LogCategory.TRADE_SIGNAL,
            level=LogLevel.INFO,
            title=f"{signal_type} Signal: {pair}",
            message=f"Generated {signal_type} signal for {pair} @ {price}",
            reasoning=" → ".join(reasoning_steps),
            data={"pair": pair, "price": price, "indicators": indicators},
            impact="high",
            confidence=confidence,
        )

    def log_freqai_prediction(
        self,
        strategy_id: str,
        strategy_name: str,
        prediction: float,
        confidence: float,
        features: Dict[str, float],
        model_version: str,
    ):
        recommendation = (
            "BUY" if prediction > 0.6 else "SELL" if prediction < 0.4 else "HOLD"
        )

        return self.log(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            category=LogCategory.FREQAI_PREDICTION,
            level=LogLevel.INFO,
            title=f"FreqAI Prediction: {recommendation}",
            message=f"Model v{model_version} predicts {prediction:.2f} with {confidence * 100:.1f}% confidence",
            reasoning=f"Feature importance: {self._get_top_features(features)}",
            data={
                "prediction": prediction,
                "confidence": confidence,
                "features": features,
                "model_version": model_version,
                "recommendation": recommendation,
            },
            impact="high",
            confidence=confidence,
        )

    def _get_top_features(self, features: Dict[str, float], top_n: int = 3) -> str:
        sorted_features = sorted(
            features.items(), key=lambda x: abs(x[1]), reverse=True
        )[:top_n]
        return ", ".join([f"{k}: {v:.3f}" for k, v in sorted_features])

    def log_risk_decision(
        self,
        strategy_id: str,
        strategy_name: str,
        risk_type: str,
        action: str,
        reasoning: str,
        metrics: Dict[str, Any],
    ):
        return self.log(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            category=LogCategory.RISK_MANAGEMENT,
            level=LogLevel.WARNING,
            title=f"Risk Alert: {risk_type}",
            message=f"Taking action: {action}",
            reasoning=reasoning,
            data=metrics,
            impact="high",
        )

    def log_market_analysis(
        self,
        strategy_id: str,
        strategy_name: str,
        market_condition: str,
        observations: List[str],
        impact_analysis: str,
    ):
        return self.log(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            category=LogCategory.MARKET_ANALYSIS,
            level=LogLevel.INFO,
            title=f"Market Analysis: {market_condition}",
            message=f"Detected {market_condition}",
            reasoning=impact_analysis,
            data={"observations": observations},
            impact="medium",
        )

    def log_research_activity(
        self,
        strategy_id: str,
        strategy_name: str,
        research_type: str,
        hypothesis: str,
        findings: str,
        conclusion: str,
        metrics: Dict[str, float] = None,
    ):
        return self.log(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            category=LogCategory.RESEARCH,
            level=LogLevel.INFO,
            title=f"Research: {research_type}",
            message=f"Testing hypothesis: {hypothesis}",
            reasoning=f"Findings: {findings}. Conclusion: {conclusion}",
            data={
                "hypothesis": hypothesis,
                "findings": findings,
                "metrics": metrics or {},
            },
            impact="medium",
        )

    def clear_old_logs(self, days: int = 30):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "DELETE FROM agent_logs WHERE timestamp < datetime('now', ?)",
            (f"-{days} days",),
        )
        conn.commit()
        conn.close()
